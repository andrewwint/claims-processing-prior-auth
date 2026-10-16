"""Lambda target for the reviewer gateway: the clinician-only decision tools.

Decision records chained to the recommendation record arrive with
evidence-record-and-trace; until then the tools validate and acknowledge.
"""

import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DELIMITER = "___"


def record_adverse_determination(event: dict) -> dict:
    reason = event.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return {"recorded": False, "status": "refused", "reasons": ["a specific reason is required"]}
    return {"recorded": True, "status": "recorded", "decision": "adverse_determination",
            "case_id": event.get("case_id"), "synthetic": True}


def record_clinician_approval(event: dict) -> dict:
    if not isinstance(event.get("case_id"), str) or not event["case_id"].strip():
        return {"recorded": False, "status": "refused", "reasons": ["case_id is required"]}
    return {"recorded": True, "status": "recorded", "decision": "clinician_approval",
            "case_id": event["case_id"], "synthetic": True}


TOOLS = {"record_adverse_determination": record_adverse_determination,
         "record_clinician_approval": record_clinician_approval}


def handler(event, context):
    full = context.client_context.custom["bedrockAgentCoreToolName"]
    name = full[full.index(DELIMITER) + len(DELIMITER):]
    tool = TOOLS.get(name)
    if tool is None:
        return {"error": f"unknown tool: {name}"}
    result = tool(event)
    # Identifiers and outcome only; never the reason text.
    logger.info(json.dumps({"tool": name, "case_id": event.get("case_id"), "recorded": result["recorded"]}))
    return result
