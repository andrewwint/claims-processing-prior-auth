"""Verify one run's record chain: decision -> trace, and decision -> recommendation -> runtime span.

Every hash is recomputed from stored bytes; nothing recorded in a record is
trusted on its own. The span is found in the runtime log group's `spans`
stream by the recommendation hash it carries (pa.recommendation_record_sha256);
the decision's trace segment is found in X-Ray by its `decision_record_sha256`
annotation (written by the reviewer or approval Lambda).

Usage: python -m scripts.verify_chain <case_id> <run_id> [--out path]
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import boto3

from infra.names import EVIDENCE_BUCKET_PREFIX, RUNTIME_NAME
from prior_auth import evidence_store

SPAN_ATTRIBUTE = "pa.recommendation_record_sha256"


def find_span(logs, recommendation_hash: str) -> dict | None:
    group = logs.describe_log_groups(
        logGroupNamePrefix=f"/aws/bedrock-agentcore/runtimes/{RUNTIME_NAME}")["logGroups"][0]["logGroupName"]
    pages = logs.get_paginator("filter_log_events").paginate(
        logGroupName=group, logStreamNames=["spans"], filterPattern=f'"{recommendation_hash}"')
    for page in pages:
        for event in page["events"]:
            span = json.loads(event["message"])
            if span.get("attributes", {}).get(SPAN_ATTRIBUTE) == recommendation_hash:
                return {"trace_id": span.get("traceId"), "span_id": span.get("spanId"), "name": span.get("name"),
                        "run_id": span["attributes"].get("pa.run_id")}
    return None


def find_decision_segment(xray, decision_hash: str, decided_at: str) -> dict | None:
    at = datetime.fromisoformat(decided_at)
    pages = xray.get_paginator("get_trace_summaries").paginate(
        StartTime=at - timedelta(minutes=5), EndTime=at + timedelta(minutes=60),
        FilterExpression=f'annotation.decision_record_sha256 = "{decision_hash}"')
    for page in pages:
        for summary in page["TraceSummaries"]:
            return {"trace_id": summary["Id"]}
    return None


def verify(session: boto3.Session, case_id: str, run_id: str) -> dict:
    s3, logs = session.client("s3"), session.client("logs")
    bucket = f"{EVIDENCE_BUCKET_PREFIX}-{session.client('sts').get_caller_identity()['Account']}"
    decision_key = evidence_store.decision_key(case_id, run_id)
    decision = evidence_store._get(s3, bucket, decision_key)
    result = {"case_id": case_id, "run_id": run_id, "decision_key": decision_key, "checks": {}}
    checks = result["checks"]
    checks["decision_exists"] = decision is not None
    if decision is None:
        result["verified"] = False
        return result
    result["decision"] = decision["decision"]
    decision_hash = evidence_store.stored_hash(s3, bucket, decision_key)
    result["decision_record_sha256"] = decision_hash
    segment = find_decision_segment(session.client("xray"), decision_hash, decision["decided_at"])
    result["decision_segment"] = segment
    checks["decision_trace_carries_decision_hash"] = segment is not None
    rec_key = evidence_store.recommendation_key(case_id, run_id)
    rec_hash = evidence_store.stored_hash(s3, bucket, rec_key)
    result["recommendation_record_sha256"] = rec_hash
    checks["decision_names_this_run"] = decision["case_id"] == case_id and decision["run_id"] == run_id
    checks["decision_points_at_recommendation"] = decision["recommendation_key"] == rec_key
    checks["recommendation_hash_matches_stored_bytes"] = (rec_hash is not None
                                                          and decision["recommendation_record_hash"] == rec_hash)
    span = find_span(logs, rec_hash) if rec_hash else None
    result["span"] = span
    checks["span_carries_recommendation_hash"] = span is not None
    checks["span_names_this_run"] = bool(span) and span.get("run_id") == run_id
    result["verified"] = all(checks.values())
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_id")
    parser.add_argument("run_id")
    parser.add_argument("--out")
    args = parser.parse_args()
    result = verify(boto3.Session(region_name="us-east-1"), args.case_id, args.run_id)
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + "\n")
    print(text)
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    sys.exit(main())
