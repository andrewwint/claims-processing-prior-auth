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


def record_approval(event: dict) -> dict:
    packet_id, claimed = event.get("packet_id"), event.get("packet_hash")
    failures, case_id = _review(packet_id, claimed)
    # Identifiers and outcome only; never packet contents.
    logger.info(json.dumps({"tool": "record_approval", "packet_id": packet_id,
                            "packet_hash": claimed, "approved": not failures, "failure_count": len(failures)}))
    if failures:
        return {"approved": False, "status": "refused", "packet_id": packet_id, "reasons": failures}
    return {"approved": True, "status": "recorded", "packet_id": packet_id, "packet_hash": claimed,
            "case_id": case_id}


def handler(event, context):
    full = context.client_context.custom["bedrockAgentCoreToolName"]
    name = full[full.index(DELIMITER) + len(DELIMITER):]
    if name != "record_approval":
        return {"error": f"unknown tool: {name}"}
    return record_approval(event)
