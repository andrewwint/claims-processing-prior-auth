"""Lambda target for the agent's gateway: exactly five tools.

record_approval is the approval service: it never trusts the caller. Other
tools are synthetic stubs until case-packet-and-failure-routing.
"""

import json
import logging

from tools import approval
from tools.schemas import AGENT_TOOLS

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DELIMITER = "___"
TOOL_NAMES = {t["name"] for t in AGENT_TOOLS}
_STORES = None


def _stores():
    global _STORES
    if _STORES is None:
        _STORES = approval.load_fixtures()
    return _STORES


def tool_name(context) -> str:
    full = context.client_context.custom["bedrockAgentCoreToolName"]
    return full[full.index(DELIMITER) + len(DELIMITER):]


def record_approval(event: dict) -> dict:
    packet_id, claimed = event.get("packet_id"), event.get("packet_hash")
    trusted, stored = _stores()
    failures = approval.review(packet_id, claimed, packets=stored, trusted=trusted)
    # Identifiers and outcome only; never packet contents.
    logger.info(json.dumps({"tool": "record_approval", "packet_id": packet_id,
                            "packet_hash": claimed, "approved": not failures, "failure_count": len(failures)}))
    if failures:
        return {"approved": False, "status": "refused", "packet_id": packet_id, "reasons": failures}
    return {"approved": True, "status": "recorded", "packet_id": packet_id, "packet_hash": claimed}


def _stub(name: str, event: dict) -> dict:
    return {"tool": name, "synthetic": True, "result": "stub", "input_keys": sorted(event)}


def handler(event, context):
    name = tool_name(context)
    if name not in TOOL_NAMES:
        return {"error": f"unknown tool: {name}"}
    if name == "record_approval":
        return record_approval(event)
    return _stub(name, event)
