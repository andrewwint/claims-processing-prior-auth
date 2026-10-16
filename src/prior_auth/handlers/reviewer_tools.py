"""Lambda target for the reviewer gateway: the clinician-only decision tools.

Each decision writes a write-once decision record chained to the run's
recommendation record (its hash recomputed from the stored object). The reviewer
is named as the clinician app reports it (validation is deferred; README).
"""

import json
import logging
import os

import boto3

from prior_auth import evidence_store, records

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DELIMITER = "___"


def _decide(event: dict, decision: str, reason, s3=None) -> dict:
    case_id = event.get("case_id")
    bucket = os.environ.get("EVIDENCE_BUCKET")
    if not bucket:
        return {"recorded": True, "status": "recorded", "decision": decision, "case_id": case_id, "synthetic": True}
    s3 = s3 or boto3.client("s3")
    queued = evidence_store.get_queue_entry(s3, bucket, case_id)
    if not queued or not queued.get("run_id"):
        return {"recorded": False, "status": "refused", "reasons": ["case is not in the review queue"]}
    key = evidence_store.recommendation_key(case_id, queued["run_id"])
    rec_hash = evidence_store.stored_hash(s3, bucket, key)
    if rec_hash is None:
        return {"recorded": False, "status": "refused", "reasons": ["no recommendation record for this run"]}
    record = records.decision_record(
        case_id=case_id, run_id=queued["run_id"], decision=decision, reason=reason,
        reviewer_identity=str(event.get("reviewer") or "unknown"), reviewer_identity_source="clinician-app",
        recommendation_key=key, recommendation_record_hash=rec_hash, decided_at=records.now())
    try:
        decision_hash = evidence_store.put_decision(s3, bucket, record)
    except evidence_store.AlreadyExists:
        return {"recorded": False, "status": "refused", "reasons": ["this run already has a decision"]}
    return {"recorded": True, "status": "recorded", "decision": decision, "case_id": case_id,
            "run_id": queued["run_id"], "decision_record_hash": decision_hash, "recommendation_record_hash": rec_hash}


def record_adverse_determination(event: dict, s3=None) -> dict:
    reason = event.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return {"recorded": False, "status": "refused", "reasons": ["a specific reason is required"]}
    return _decide(event, "adverse_determination", reason, s3)


def record_clinician_approval(event: dict, s3=None) -> dict:
    if not isinstance(event.get("case_id"), str) or not event["case_id"].strip():
        return {"recorded": False, "status": "refused", "reasons": ["case_id is required"]}
    return _decide(event, "clinician_approval", None, s3)


TOOLS = {"record_adverse_determination": record_adverse_determination,
         "record_clinician_approval": record_clinician_approval}


def handler(event, context):
    full = context.client_context.custom["bedrockAgentCoreToolName"]
    name = full[full.index(DELIMITER) + len(DELIMITER):]
    tool = TOOLS.get(name)
    if tool is None:
        return {"error": f"unknown tool: {name}"}
    result = tool(event)
    # Identifiers and hashes only; never the reason text.
    logger.info(json.dumps({"tool": name, "case_id": event.get("case_id"), "recorded": result["recorded"],
                            "decision_record_sha256": result.get("decision_record_hash")}))
    return result
