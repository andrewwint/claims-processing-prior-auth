"""Lambda target for the agent's four case tools (synthetic stubs until
case-packet-and-failure-routing). record_approval is not here: it is the
approval service's own target."""

import logging

from tools.schemas import CASE_TOOLS

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DELIMITER = "___"
TOOL_NAMES = {t["name"] for t in CASE_TOOLS}


def tool_name(context) -> str:
    full = context.client_context.custom["bedrockAgentCoreToolName"]
    return full[full.index(DELIMITER) + len(DELIMITER):]


def _stub(name: str, event: dict) -> dict:
    return {"tool": name, "synthetic": True, "result": "stub", "input_keys": sorted(event)}


def handler(event, context):
    name = tool_name(context)
    if name not in TOOL_NAMES:
        return {"error": f"unknown tool: {name}"}
    return _stub(name, event)
