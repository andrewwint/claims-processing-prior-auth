"""Inline tool schemas for the two gateway targets.

The agent's target has exactly five tools and no denial tool. The denial tool
exists only on the reviewer target.
"""

AGENT_TARGET = "AgentTools"
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


AGENT_TOOLS = [
    _tool("check_eligibility", "Coverage and benefits for the member and service.",
          {"member_id": _s("Synthetic member ID"), "cpt_code": _s("CPT code of the requested service")}),
    _tool("fetch_policy_criteria", "Verified criteria for the CPT code and payer.",
          {"cpt_code": _s("CPT code"), "payer_id": _s("Synthetic payer ID")}),
    _tool("extract_clinical_evidence", "Findings from the record for one criterion, each with its source.",
          {"case_id": _s("Case ID"), "criterion_id": _s("Criterion ID from the compiled policy")}),
    _tool("record_approval",
          "Approve a stored case packet. The approval service loads the packet, verifies the hash and re-runs every check before recording anything.",
          {"packet_id": _s("ID of the stored case packet"), "packet_hash": _s("SHA-256 of the packet's canonical JSON")}),
    _tool("route_to_reviewer", "Send the case packet to a clinician queue with the gaps marked.",
          {"case_id": _s("Case ID"), "reason": _s("Why the case needs a clinician"),
           "gaps": {"type": "array", "description": "Criteria not met or checks failed", "items": {"type": "string"}}},
          required=["case_id", "reason"]),
]

REVIEWER_TOOLS = [
    _tool("record_adverse_determination", "Record a clinician's adverse determination with a specific reason.",
          {"case_id": _s("Case ID"), "reason": _s("The specific reason for the determination")}),
]
