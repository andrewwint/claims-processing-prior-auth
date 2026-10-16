"""Lambda target for the reviewer gateway: the clinician-only denial tool (stub)."""

import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DELIMITER = "___"


def handler(event, context):
    full = context.client_context.custom["bedrockAgentCoreToolName"]
    name = full[full.index(DELIMITER) + len(DELIMITER):]
    if name != "record_adverse_determination":
        return {"error": f"unknown tool: {name}"}
    if not event.get("reason", "").strip():
        return {"recorded": False, "status": "refused", "reasons": ["a specific reason is required"]}
    logger.info(json.dumps({"tool": name, "case_id": event.get("case_id"), "recorded": True}))
    return {"recorded": True, "status": "recorded", "case_id": event.get("case_id"), "synthetic": True}
