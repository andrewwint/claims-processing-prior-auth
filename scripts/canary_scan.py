"""Beat 6: scan every telemetry sink for chart text, with a positive control first.

Needles: each chart document's canary and every chart line of 24 or more
characters (so a leaked finding value is caught, not only a leaked header).

Sinks, over the run's time window:
- the runtime log group, every stream (runtime logs, `spans`, OTel logs);
- `aws/spans` (Transaction Search);
- X-Ray traces (BatchGetTraces over the window's trace summaries);
- every tool Lambda log group.

Modes:
  control  plant a control token through the runtime's test-only path (one span
           attribute, one log line) and a control line in each Lambda log group,
           then require the scan to find the token in every sink it was planted in.
  clean    run all six cases fresh, wait for their spans, then require zero hits.

Usage: python -m scripts.canary_scan control|clean
"""

import json
import secrets
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import boto3

from infra.names import LAMBDA_FUNCTIONS, RUNTIME_NAME
from prior_auth import stores
from prior_auth.agent.pipeline import session_id_for
from scripts import gateway_client as gc
from scripts.intake import intake_token, invoke, invoke_payload
from scripts.redact import find_unredacted, known_values, redact

MIN_LINE = 24
SPANS_GROUP = "aws/spans"
WAIT_S, POLL_S = 900, 30


def needles() -> dict[str, str]:
    """needle -> where it comes from (canaries and chart lines)."""
    found = {}
    for path in sorted(Path("data/charts").glob("SYN-DOC-*.json")):
        doc = json.loads(path.read_text())
        for p, page in enumerate(doc["pages"], start=1):
            for n, line in enumerate(page, start=1):
                if len(line.strip()) >= MIN_LINE:
                    found[line.strip()] = f"{doc['doc_id']} p{p} l{n}"
        for token in (w.rstrip(".,") for w in " ".join(doc["pages"][0]).split()):
            if token.startswith("CANARY-"):
                found[token] = f"{doc['doc_id']} canary"
    return found


def runtime_group(logs) -> str:
    return logs.describe_log_groups(
        logGroupNamePrefix=f"/aws/bedrock-agentcore/runtimes/{RUNTIME_NAME}")["logGroups"][0]["logGroupName"]


def lambda_groups() -> list[str]:
    return [f"/aws/lambda/{name}" for name in LAMBDA_FUNCTIONS]


def log_events(logs, group: str, start_ms: int, end_ms: int) -> list[str]:
    try:
        pages = logs.get_paginator("filter_log_events").paginate(
            logGroupName=group, startTime=start_ms, endTime=end_ms)
        return [e["message"] for page in pages for e in page["events"]]
    except logs.exceptions.ResourceNotFoundException:
        return []


def xray_documents(xray, start: datetime, end: datetime) -> list[str]:
    ids = [s["Id"] for page in xray.get_paginator("get_trace_summaries").paginate(StartTime=start, EndTime=end)
           for s in page["TraceSummaries"]]
    docs = []
    for i in range(0, len(ids), 5):
        for trace in xray.batch_get_traces(TraceIds=ids[i:i + 5])["Traces"]:
            docs.extend(seg["Document"] for seg in trace["Segments"])
    return docs


def collect(session, start: datetime, end: datetime) -> dict[str, list[str]]:
    logs, xray = session.client("logs"), session.client("xray")
    s, e = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    sinks = {"runtime": log_events(logs, runtime_group(logs), s, e), SPANS_GROUP: log_events(logs, SPANS_GROUP, s, e),
             "xray": xray_documents(xray, start, end)}
    for group in lambda_groups():
        sinks[group] = log_events(logs, group, s, e)
    return sinks


def scan(sinks: dict[str, list[str]], wanted: dict[str, str]) -> dict:
    hits = {}
    for sink, events in sinks.items():
        for text in events:
            for needle, origin in wanted.items():
                if needle in text:
                    hits.setdefault(sink, set()).add(origin)
    return {"events_scanned": {k: len(v) for k, v in sinks.items()},
            "hits": {k: sorted(v) for k, v in hits.items()}}


def spans_for(session, start: datetime, marker: str) -> int:
    logs = session.client("logs")
    s = int(start.timestamp() * 1000)
    return sum(1 for m in log_events(logs, runtime_group(logs), s, int(time.time() * 1000)) if marker in m
               and '"spanId"' in m)


def wait_for_spans(session, start: datetime, markers: list[str]) -> dict:
    deadline = time.time() + WAIT_S
    while True:
        seen = {m: spans_for(session, start, m) for m in markers}
        if all(seen.values()) or time.time() > deadline:
            return seen
        time.sleep(POLL_S)


def run(mode: str) -> dict:
    session = boto3.Session(region_name="us-east-1")
    out = gc.outputs()
    runtime = json.loads(Path(".local/runtime.json").read_text())
    token = intake_token(out, session)
    start = datetime.now(timezone.utc)
    record = {"mode": mode, "date": date.today().isoformat(),
              "sha": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
              "span_source": "runtime log group `spans` stream (ADOT via X-Ray Transaction Search), "
                             "plus aws/spans and X-Ray BatchGetTraces"}
    if mode == "control":
        control = "CANARY-CONTROL-" + secrets.token_hex(8)
        record["runtime_response"] = invoke_payload({"positive_control": control}, runtime["arn"], token,
                                                    session_id_for("positive-control"))
        logs = session.client("logs")
        for group in lambda_groups():
            stream = f"positive-control-{control[-8:]}"
            logs.create_log_stream(logGroupName=group, logStreamName=stream)
            logs.put_log_events(logGroupName=group, logStreamName=stream, logEvents=[
                {"timestamp": int(time.time() * 1000), "message": json.dumps({"positive_control": control})}])
        record["spans_seen"] = wait_for_spans(session, start, [control])
        sinks = collect(session, start, datetime.now(timezone.utc))
        result = scan(sinks, {control: "control"})
        planted = ["runtime", *lambda_groups()]
        record["control_token"] = control
        record["scan"] = result
        record["found_in_every_planted_sink"] = all(s in result["hits"] for s in planted)
        record["found_in_runtime_span"] = record["spans_seen"][control] > 0
        record["passed"] = record["found_in_every_planted_sink"] and record["found_in_runtime_span"]
    else:
        runs = {}
        for case_id in stores.cases():
            result = invoke(case_id, runtime["arn"], token, session_id_for(case_id))
            runs[case_id] = {k: result.get(k) for k in ("outcome", "reason", "gaps", "run_id")}
        record["runs"] = runs
        record["spans_seen"] = wait_for_spans(session, start, [r["run_id"] for r in runs.values() if r["run_id"]])
        wanted = needles()
        record["needles"] = {"canaries": sum(1 for k in wanted if k.startswith("CANARY-")),
                             "chart_lines": sum(1 for k in wanted if not k.startswith("CANARY-"))}
        record["scan"] = scan(collect(session, start, datetime.now(timezone.utc)), wanted)
        record["passed"] = record["scan"]["hits"] == {} and all(record["spans_seen"].values())
    return record


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in ("control", "clean"):
        print(__doc__, file=sys.stderr)
        return 2
    record = run(sys.argv[1])
    out = gc.outputs()
    runtime = json.loads(Path(".local/runtime.json").read_text())
    named = {**known_values(out), runtime["arn"]: "<runtime-arn>"}
    text = redact(json.dumps(record, indent=2, sort_keys=True, default=str), named)
    assert not find_unredacted(text)
    path = Path(f"evidence/{record['date']}/canary-scan-{record['mode']}.json")
    path.write_text(text + "\n")
    print(json.dumps({k: record[k] for k in ("passed", "spans_seen")} | {"scan": record["scan"]}, indent=2))
    print("->", path)
    return 0 if record["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
