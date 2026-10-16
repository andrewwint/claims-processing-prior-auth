"""Lambda target for the approval service: record_approval only.

It has its own function and role, separate from the agent's case tools, so
that it alone (with the reviewer service) may later write decision records.
It never trusts the caller or the packet; see tools/approval.py.
"""

import json
import logging

from tools import approval

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DELIMITER = "___"
_STORES = None


def _stores():
    global _STORES
    if _STORES is None:
        _STORES = approval.load_fixtures()
    return _STORES


def record_approval(event: dict) -> dict:
    packet_id, claimed = event.get("packet_id"), event.get("packet_hash")
    trusted, stored = _stores()
    failures = approval.review(packet_id, claimed, packets=stored, trusted=trusted)
    # Identifiers and outcome only; never packet contents.
    logger.info(json.dumps({"tool": "record_approval", "packet_id": packet_id,
                            "packet_hash": claimed, "approved": not failures, "failure_count": len(failures)}))
    if failures:
        return {"approved": False, "status": "refused", "packet_id": packet_id, "reasons": failures}
    return {"approved": True, "status": "recorded", "packet_id": packet_id, "packet_hash": claimed,
            "case_id": approval.case_for(packet_id, trusted)}


def handler(event, context):
    full = context.client_context.custom["bedrockAgentCoreToolName"]
    name = full[full.index(DELIMITER) + len(DELIMITER):]
    if name != "record_approval":
        return {"error": f"unknown tool: {name}"}
    return record_approval(event)
