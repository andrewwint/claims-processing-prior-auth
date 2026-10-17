"""Put a decision's hashes on the Lambda's X-Ray trace (L6: decision -> span).

Sends one segment under the invocation's trace (from _X_AMZN_TRACE_ID), with the
hashes as annotations so the trace can be found by them. Identifiers and hashes
only. Telemetry never changes an outcome, so every failure here is swallowed.
"""

import json
import os
import secrets
import time

ANNOTATION = "decision_record_sha256"


def _trace_header() -> dict:
    parts = dict(p.split("=", 1) for p in os.environ.get("_X_AMZN_TRACE_ID", "").split(";") if "=" in p)
    return {"root": parts.get("Root"), "parent": parts.get("Parent")}


def segment(name: str, annotations: dict) -> dict | None:
    header = _trace_header()
    if not header["root"]:
        return None
    now = time.time()
    doc = {"name": name, "id": secrets.token_hex(8), "trace_id": header["root"], "start_time": now,
           "end_time": now, "annotations": {k: v for k, v in annotations.items() if v is not None}}
    if header["parent"]:
        doc["parent_id"] = header["parent"]
    return doc


def mark_decision(name: str, decision_hash: str, recommendation_hash: str, run_id: str, xray=None) -> None:
    try:
        doc = segment(name, {ANNOTATION: decision_hash, "recommendation_record_sha256": recommendation_hash,
                             "run_id": run_id})
        if doc is None:
            return
        if xray is None:
            import boto3
            xray = boto3.client("xray")
        xray.put_trace_segments(TraceSegmentDocuments=[json.dumps(doc)])
    except Exception:  # telemetry must never change an outcome
        pass
