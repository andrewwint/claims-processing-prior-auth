"""Inline tool schemas for the gateway targets.

The agent's gateway has exactly five tools on two targets, and no denial tool:
four case tools, and record_approval on the approval service's own target
(its own Lambda and role). The denial tool exists only on the reviewer target.
"""

CASE_TARGET = "AgentTools"
APPROVAL_TARGET = "ApprovalService"
REVIEWER_TARGET = "ReviewerTools"


def _tool(name, description, properties, required=None):
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": required if required is not None else list(properties),
        },
    }


def _s(description):
    return {"type": "string", "description": description}


CASE_TOOLS = [
    _tool("check_eligibility", "Coverage for the member and service (CPT).",
          {"member_id": _s("Synthetic member ID"), "cpt_code": _s("CPT code of the requested service")}),
    _tool("fetch_policy_criteria", "Verified criteria for the CPT code and payer.",
          {"cpt_code": _s("CPT code"), "payer_id": _s("Synthetic payer ID")}),
    _tool("extract_clinical_evidence",
          "The case's documents, line by line with document, page and line numbers, for the agent to cite.",
          {"case_id": _s("Case ID")}),
    _tool("route_to_reviewer", "Send the case packet to a clinician queue with the gaps marked.",
          {"case_id": _s("Case ID"), "reason": _s("Why the case needs a clinician"),
           "gaps": {"type": "array", "description": "Criteria not met or checks failed", "items": {"type": "string"}}},
          required=["case_id", "reason"]),
]

APPROVAL_TOOLS = [
    _tool("record_approval",
          "Approve a stored case packet. The approval service loads the packet, verifies the hash and re-runs every check before recording anything.",
          {"packet_id": _s("ID of the stored case packet"), "packet_hash": _s("SHA-256 of the packet's canonical JSON")}),
]

AGENT_TOOLS = CASE_TOOLS + APPROVAL_TOOLS
TOOL_TARGETS = {**{t["name"]: CASE_TARGET for t in CASE_TOOLS}, **{t["name"]: APPROVAL_TARGET for t in APPROVAL_TOOLS}}

REVIEWER_TOOLS = [
    _tool("record_adverse_determination", "Record a clinician's adverse determination with a specific reason.",
          {"case_id": _s("Case ID"), "reason": _s("The specific reason for the determination")}),
    _tool("record_clinician_approval", "Record a clinician's approval of a routed case.",
          {"case_id": _s("Case ID")}),
]
