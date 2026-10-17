"""Lambda target for the approval service: record_approval only.

It has its own function and role, separate from the agent's case tools, so
that it alone (with the reviewer service) may later write decision records.
It never trusts the caller or the packet; see prior_auth/handlers/approval.py.
"""

import json
import logging
import os

from prior_auth.handlers import approval

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DELIMITER = "___"
_STORES = None


def _stores():
    global _STORES
    if _STORES is None:
        _STORES = approval.load_fixtures()
    return _STORES


def _review(packet_id, claimed):
    """Live packets (PKT-<case_id>) come from the evidence bucket and are checked against the
    bundled trusted stores; the D1 fixture packets (SYN-PKT-*) keep their fixture path."""
    if isinstance(packet_id, str) and packet_id.startswith("PKT-") and os.environ.get("EVIDENCE_BUCKET"):
        import boto3

        from prior_auth.evidence_store import get_packet
        s3 = boto3.client("s3")
        failures, case_id = approval.review_stored(
            packet_id, claimed, lambda pid: get_packet(s3, os.environ["EVIDENCE_BUCKET"], pid))
        return failures, case_id
    trusted, stored = _stores()
    return approval.review(packet_id, claimed, packets=stored, trusted=trusted), approval.case_for(packet_id, trusted)


def _record_auto_approval(packet_id: str, case_id: str, s3=None) -> tuple[list[str], dict]:
    """Write the auto-approval's decision record, chained to the run's recommendation record."""
    import boto3

    from prior_auth import evidence_store, records
    bucket = os.environ.get("EVIDENCE_BUCKET")
    if not bucket or not packet_id.startswith("PKT-"):
        return [], {}
    s3 = s3 or boto3.client("s3")
    run_id = (evidence_store.get_packet(s3, bucket, packet_id) or {}).get("run_id")
    key = evidence_store.recommendation_key(case_id, run_id) if run_id else None
    rec_hash = evidence_store.stored_hash(s3, bucket, key) if key else None
    if rec_hash is None:
        return ["no recommendation record for this run"], {}
    record = records.decision_record(
        case_id=case_id, run_id=run_id, decision="auto_approval", reason=None, reviewer_identity="approval-service",
        reviewer_identity_source="service", recommendation_key=key, recommendation_record_hash=rec_hash,
        decided_at=records.now())
    try:
        decision_hash = evidence_store.put_decision(s3, bucket, record)
    except evidence_store.AlreadyExists:
        return ["this run already has a decision"], {}
    from prior_auth import trace_mark
    trace_mark.mark_decision("prior-auth-auto-approval", decision_hash, rec_hash, run_id)
    return [], {"decision_record_hash": decision_hash, "recommendation_record_hash": rec_hash, "run_id": run_id}


def record_approval(event: dict) -> dict:
    packet_id, claimed = event.get("packet_id"), event.get("packet_hash")
    failures, case_id = _review(packet_id, claimed)
    chain = {}
    if not failures:
        failures, chain = _record_auto_approval(packet_id, case_id)
    # Identifiers and outcome only; never packet contents.
    logger.info(json.dumps({"tool": "record_approval", "packet_id": packet_id,
                            "packet_hash": claimed, "approved": not failures, "failure_count": len(failures)}))
    if failures:
        return {"approved": False, "status": "refused", "packet_id": packet_id, "reasons": failures}
    return {"approved": True, "status": "recorded", "packet_id": packet_id, "packet_hash": claimed,
            "case_id": case_id, **chain}


def handler(event, context):
    full = context.client_context.custom["bedrockAgentCoreToolName"]
    name = full[full.index(DELIMITER) + len(DELIMITER):]
    if name != "record_approval":
        return {"error": f"unknown tool: {name}"}
    return record_approval(event)
