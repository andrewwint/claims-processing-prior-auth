"""Telemetry check (case-packet task 0.2): which instrumentation attaches content, and
proof that the runtime's settings remove it.

Each configuration runs the Strands agent on one synthetic case in a fresh process,
with Strands telemetry and ADOT's botocore instrumentation exporting to memory.
The case's charts carry canaries, which reach the model through
extract_clinical_evidence, so a canary in telemetry means chart content leaked.

Usage: python -m scripts.telemetry_check
"""

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

CASE = "SYN-CASE-CLEAN-1"
CHART_PHRASES = ("visits over seven weeks", "nerve root compression", "Oswestry Disability Index")

CONFIGS = {
    # Positive control: what the runtime would do with ADOT's defaults and no Strands redaction.
    "control_adot_defaults": {"AGENT_OBSERVABILITY_ENABLED": "true"},
    # Isolation: only the botocore Bedrock content capture turned off (Strands unredacted).
    "botocore_capture_off_only": {"AGENT_OBSERVABILITY_ENABLED": "true",
                                  "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "false"},
    # Isolation: only Strands redaction on (ADOT's botocore content capture left at its default).
    "strands_redaction_only": {"AGENT_OBSERVABILITY_ENABLED": "true",
                               "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai_unredacted_attributes="},
    # The runtime's settings (case-packet design D7).
    "runtime_settings": {
        "AGENT_OBSERVABILITY_ENABLED": "true",
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "false",
        "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai_unredacted_attributes=",
    },
}


def child() -> None:
    """Run in a fresh process: instrument, run one case, dump every attribute, event and log body."""
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    if os.environ.get("AGENT_OBSERVABILITY_ENABLED") == "true":
        # Apply the same environment defaults the ADOT distro applies (setdefault semantics).
        os.environ.setdefault("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "true")
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    # GenAI instrumentation emits message content as log records (events API), which ADOT ships
    # over OTLP; capture those too, not just spans.
    from opentelemetry._logs import set_logger_provider
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor
    log_exporter = InMemoryLogRecordExporter()
    logger_provider = LoggerProvider()
    logger_provider.add_log_record_processor(SimpleLogRecordProcessor(log_exporter))
    set_logger_provider(logger_provider)
    from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
    BotocoreInstrumentor().instrument()

    import boto3
    from strands.tools.mcp import MCPClient

    from prior_auth.agent.strands_agent import make_extract
    from scripts import gateway_client as gc

    out = gc.outputs()
    session = boto3.Session(region_name="us-east-1")
    client = MCPClient(url=out["AgentGatewayUrl"], headers={"Authorization": f"Bearer {gc.agent_token(out, session)}"})
    with client:
        result = make_extract(client)(CASE)
    dumped = []
    for span in exporter.get_finished_spans():
        dumped.append({"name": span.name, "attributes": dict(span.attributes or {}),
                       "events": [{"name": e.name, "attributes": dict(e.attributes or {})} for e in span.events]})
    logs = []
    for item in log_exporter.get_finished_logs():
        rec = getattr(item, "log_record", item)
        logs.append({"event": getattr(rec, "event_name", None) or (rec.attributes or {}).get("event.name"),
                     "attributes": dict(rec.attributes or {}), "body": rec.body})
    print(json.dumps({"citations": len(result.citations), "spans": dumped, "logs": logs}, default=str))


def scan(spans: list, logs: list, canaries: list[str]) -> dict:
    text = json.dumps([spans, logs], default=str)
    hits = {c: text.count(c) for c in canaries if c in text}
    phrases = {p: text.count(p) for p in CHART_PHRASES if p in text}
    content_attrs = sorted({k for s in spans for k in s["attributes"] if "message" in k or "content" in k or "prompt" in k
                            or "completion" in k or "tool.call" in k})
    by_source = {}
    for sp in spans:
        blob = json.dumps(sp, default=str)
        if any(c in blob for c in canaries) or any(p in blob for p in CHART_PHRASES):
            source = "botocore" if sp["attributes"].get("rpc.system") == "aws-api" else "strands"
            where = "events" if any(any(c in json.dumps(e, default=str) for c in [*canaries, *CHART_PHRASES])
                                    for e in sp["events"]) else "attributes"
            by_source.setdefault(f"{source} span '{sp['name']}' ({where})", 0)
            by_source[f"{source} span '{sp['name']}' ({where})"] += 1
    leaking_logs = {}
    for lg in logs:
        blob = json.dumps(lg, default=str)
        if any(c in blob for c in canaries) or any(p in blob for p in CHART_PHRASES):
            leaking_logs[str(lg["event"])] = leaking_logs.get(str(lg["event"]), 0) + 1
    return {"span_count": len(spans), "log_record_count": len(logs), "canary_hits": hits, "chart_phrase_hits": phrases,
            "content_attribute_names": content_attrs, "leaking_spans": by_source, "leaking_log_records": leaking_logs}


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        child()
        return 0
    from prior_auth import stores
    canaries = [stores.document(d)["pages"][0][0].split("chart reference ")[1].rstrip(".")
                for d in stores.cases()[CASE]["documents"]]
    report = {"case": CASE, "date": date.today().isoformat(), "configs": {}}
    for name, env in CONFIGS.items():
        clean_env = {k: v for k, v in os.environ.items() if not k.startswith(("OTEL_", "AGENT_OBSERVABILITY"))}
        proc = subprocess.run([sys.executable, "-m", "scripts.telemetry_check", "--child"],
                              env={**clean_env, **env}, capture_output=True, text=True)
        line = next((l for l in reversed(proc.stdout.splitlines()) if l.startswith("{")), None)
        if line is None:
            print(proc.stderr[-2000:], file=sys.stderr)
            return 1
        data = json.loads(line)
        report["configs"][name] = {"env": env, "citations": data["citations"], **scan(data["spans"], data["logs"], canaries)}
        r = report["configs"][name]
        print(f"{name}: spans={r['span_count']} canary_hits={sum(r['canary_hits'].values())} "
              f"chart_phrase_hits={sum(r['chart_phrase_hits'].values())} logs={r['log_record_count']} "
              f"leaking_spans={r['leaking_spans']} leaking_logs={r['leaking_log_records']}")
    control, runtime = report["configs"]["control_adot_defaults"], report["configs"]["runtime_settings"]
    report["positive_control_found_content"] = bool(control["canary_hits"] or control["chart_phrase_hits"])
    report["runtime_settings_clean"] = not runtime["canary_hits"] and not runtime["chart_phrase_hits"]
    path = Path(f"evidence/{date.today().isoformat()}/telemetry-check.json")
    path.write_text(json.dumps(report, indent=2) + "\n")
    print("positive control found content:", report["positive_control_found_content"],
          "| runtime settings clean:", report["runtime_settings_clean"], "->", path)
    return 0 if report["positive_control_found_content"] and report["runtime_settings_clean"] else 1


if __name__ == "__main__":
    sys.exit(main())
