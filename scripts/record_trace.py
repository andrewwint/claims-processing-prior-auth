"""Record one deployed run's trace (L1): every span's name, duration and attribute keys, and the
values of the attributes the claim names (identifiers, model, token counts, stop reason, latency,
hashes). No other value is exported, so no content can enter the evidence file.

Usage: python -m scripts.record_trace <run_id>
"""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import boto3

from infra.names import RUNTIME_NAME
from scripts import gateway_client as gc
from scripts.redact import find_unredacted, known_values, redact

KEPT_VALUES = ("pa.case_id", "pa.run_id", "pa.recommendation_record_sha256", "gen_ai.request.model",
               "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens", "gen_ai.usage.completion_tokens",
               "gen_ai.usage.prompt_tokens", "gen_ai.response.finish_reasons", "gen_ai.server.request.duration",
               "gen_ai.tool.name", "gen_ai.operation.name", "http.status_code")


def reduce(span: dict) -> dict:
    attrs = span.get("attributes", {})
    return {"name": span.get("name"),
            "seconds": round((span.get("endTimeUnixNano", 0) - span.get("startTimeUnixNano", 0)) / 1e9, 3),
            "attribute_keys": sorted(attrs),
            "values": {k: attrs[k] for k in KEPT_VALUES if k in attrs}}


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    run_id = sys.argv[1]
    logs = boto3.Session(region_name="us-east-1").client("logs")
    group = logs.describe_log_groups(
        logGroupNamePrefix=f"/aws/bedrock-agentcore/runtimes/{RUNTIME_NAME}")["logGroups"][0]["logGroupName"]
    first = logs.filter_log_events(logGroupName=group, logStreamNames=["spans"], filterPattern=f'"{run_id}"')["events"]
    trace_id = json.loads(first[0]["message"])["traceId"]
    spans = [json.loads(e["message"]) for page in logs.get_paginator("filter_log_events").paginate(
        logGroupName=group, logStreamNames=["spans"], filterPattern=f'"{trace_id}"') for e in page["events"]]
    record = {"run_id": run_id, "trace_id": trace_id, "date": date.today().isoformat(),
              "sha": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
              "source": "the runtime log group's spans stream", "spans": [reduce(s) for s in spans]}
    text = redact(json.dumps(record, indent=2, sort_keys=True), known_values(gc.outputs()))
    assert not find_unredacted(text)
    path = Path(f"evidence/{record['date']}/trace-{run_id}.json")
    path.write_text(text + "\n")
    print(f"{len(spans)} spans -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
