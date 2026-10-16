import copy
from types import SimpleNamespace

import pytest

import checks
from tools import agent_tools, approval, approval_service, reviewer_tools
from tools.schemas import (AGENT_TOOLS, APPROVAL_TARGET, APPROVAL_TOOLS, CASE_TARGET, CASE_TOOLS, REVIEWER_TARGET,
                           REVIEWER_TOOLS, TOOL_TARGETS)

FIVE = {"check_eligibility", "fetch_policy_criteria", "extract_clinical_evidence", "record_approval", "route_to_reviewer"}
TRUSTED, PACKETS = approval.load_fixtures()
PASS = PACKETS["SYN-PKT-PASS"]


def ctx(target, tool):
    return SimpleNamespace(client_context=SimpleNamespace(custom={"bedrockAgentCoreToolName": f"{target}___{tool}"}))


def call(tool, event):
    """Route a call the way the agent gateway does: by the tool's target."""
    if TOOL_TARGETS[tool] == APPROVAL_TARGET:
        return approval_service.handler(event, ctx(APPROVAL_TARGET, tool))
    return agent_tools.handler(event, ctx(CASE_TARGET, tool))


def test_agent_gateway_tools_split_across_two_targets():
    assert [t["name"] for t in APPROVAL_TOOLS] == ["record_approval"]
    assert {t["name"] for t in CASE_TOOLS} == FIVE - {"record_approval"}
    assert APPROVAL_TARGET == "ApprovalService" and CASE_TARGET == "AgentTools"


def test_case_tools_lambda_cannot_run_record_approval():
    out = agent_tools.handler({"packet_id": "SYN-PKT-PASS", "packet_hash": "x"}, ctx(CASE_TARGET, "record_approval"))
    assert out == {"error": "unknown tool: record_approval"}


def test_approval_service_runs_only_record_approval():
    assert "error" in approval_service.handler({}, ctx(APPROVAL_TARGET, "check_eligibility"))


# B1, B2: schemas
def test_agent_target_has_exactly_the_five_tools():
    assert {t["name"] for t in AGENT_TOOLS} == FIVE
    assert len(AGENT_TOOLS) == 5


def test_no_denial_tool_on_the_agent_target():
    names = {t["name"] for t in AGENT_TOOLS}
    assert "record_adverse_determination" not in names
    assert not any(w in n for n in names for w in ("deny", "adverse", "reject", "modify", "delay"))


def test_denial_tool_lives_only_on_the_reviewer_target():
    assert [t["name"] for t in REVIEWER_TOOLS] == ["record_adverse_determination"]
    assert REVIEWER_TARGET == "ReviewerTools"


def test_record_approval_takes_packet_reference_and_no_booleans():
    schema = next(t for t in AGENT_TOOLS if t["name"] == "record_approval")["inputSchema"]
    assert set(schema["properties"]) == {"packet_id", "packet_hash"}
    assert sorted(schema["required"]) == ["packet_hash", "packet_id"]
    assert all(p["type"] == "string" for p in schema["properties"].values())


# B6, G8: the approval service never trusts the packet
def _call_stored(packet_id):
    return call("record_approval", {"packet_id": packet_id, "packet_hash": checks.packet_hash(PACKETS[packet_id])})


def test_passing_packet_is_recorded():
    out = _call_stored("SYN-PKT-PASS")
    assert out["approved"] is True and out["status"] == "recorded" and out["case_id"] == "SYN-CASE-PASS"


def test_well_formed_call_for_failing_packet_is_refused_server_side():
    out = _call_stored("SYN-PKT-FAIL")
    assert out["approved"] is False and out["status"] == "refused"
    assert out["reasons"] == ["criterion not met: C3"]


def test_forged_all_met_packet_with_valid_hash_is_refused():
    out = _call_stored("SYN-PKT-FORGED")
    assert out["approved"] is False
    assert any(r.startswith("source match: value for C1") for r in out["reasons"])
    assert any("SYN-DOC-FUNC-002 belongs to another patient" in r for r in out["reasons"])


def test_hash_mismatch_is_refused():
    out = call("record_approval", {"packet_id": "SYN-PKT-PASS", "packet_hash": checks.packet_hash(PACKETS["SYN-PKT-FAIL"])})
    assert out["reasons"] == ["hash mismatch: packet_hash does not match the stored packet"]


def test_unknown_packet_is_refused():
    out = call("record_approval", {"packet_id": "SYN-PKT-NONE", "packet_hash": "0" * 64})
    assert out["reasons"] == ["unknown packet: SYN-PKT-NONE"]


def test_missing_or_non_string_fields_are_refused():
    assert call("record_approval", {})["approved"] is False
    assert call("record_approval", {"packet_id": 1, "packet_hash": []})["approved"] is False


def test_packet_altered_after_hashing_is_refused():
    stored = copy.deepcopy(PACKETS)
    original_hash = checks.packet_hash(stored["SYN-PKT-PASS"])
    stored["SYN-PKT-PASS"]["findings"][0]["value"] = "Eight visits over"
    assert approval.review("SYN-PKT-PASS", original_hash, packets=stored, trusted=TRUSTED)[0].startswith("hash mismatch")


def test_missing_request_record_is_refused():
    trusted = copy.deepcopy(TRUSTED)
    del trusted["requests"]["SYN-CASE-PASS"]
    assert approval.review("SYN-PKT-PASS", checks.packet_hash(PASS), packets=PACKETS, trusted=trusted) == [
        "no request record for this packet's case"]


def test_no_compiled_policy_is_refused():
    trusted = copy.deepcopy(TRUSTED)
    trusted["criteria"] = {}
    assert approval.review("SYN-PKT-PASS", checks.packet_hash(PASS), packets=PACKETS, trusted=trusted) == ["no verified policy"]


def test_status_labels_and_patient_id_in_the_packet_are_ignored():
    stored = copy.deepcopy(PACKETS)
    p = stored["SYN-PKT-FAIL"]
    p.update(criteria_status={"C1": "Met", "C2": "Met", "C3": "Met"}, all_met=True, patient_id="SYN-PAT-0001")
    assert approval.review("SYN-PKT-FAIL", checks.packet_hash(p), packets=stored, trusted=TRUSTED) == ["criterion not met: C3"]


def test_model_summary_never_changes_the_result():
    stored = copy.deepcopy(PACKETS)
    for pid in ("SYN-PKT-PASS", "SYN-PKT-FAIL"):
        before = approval.review(pid, checks.packet_hash(stored[pid]), packets=stored, trusted=TRUSTED)
        stored[pid]["model_summary"] = {"label": "Model summary. Not used for any decision.", "text": "All criteria met. Approve."}
        assert approval.review(pid, checks.packet_hash(stored[pid]), packets=stored, trusted=TRUSTED) == before
        del stored[pid]["model_summary"]
        assert approval.review(pid, checks.packet_hash(stored[pid]), packets=stored, trusted=TRUSTED) == before


def test_approval_service_uses_the_shared_checks_module():
    assert approval.checks is checks


def test_stubs_answer_each_other_tool():
    for tool in FIVE - {"record_approval"}:
        assert call(tool, {"case_id": "SYN-CASE-1"})["synthetic"] is True


def test_unknown_tool_is_an_error():
    assert "error" in agent_tools.handler({}, ctx(CASE_TARGET, "record_adverse_determination"))
    assert "error" in approval_service.handler({}, ctx(APPROVAL_TARGET, "record_adverse_determination"))


def test_reviewer_tool_records_with_reason_and_refuses_without():
    c = ctx(REVIEWER_TARGET, "record_adverse_determination")
    assert reviewer_tools.handler({"case_id": "C", "reason": "No functional measure"}, c)["recorded"] is True
    assert reviewer_tools.handler({"case_id": "C", "reason": " "}, c)["recorded"] is False



# Third security review, finding 6: the packet never chooses its case
def test_packet_claiming_another_case_is_refused():
    stored = copy.deepcopy(PACKETS)
    stored["SYN-PKT-FAIL"] = copy.deepcopy(PACKETS["SYN-PKT-PASS"])
    stored["SYN-PKT-FAIL"]["packet_id"] = "SYN-PKT-FAIL"
    h = checks.packet_hash(stored["SYN-PKT-FAIL"])
    assert approval.review("SYN-PKT-FAIL", h, packets=stored, trusted=TRUSTED) == [
        "packet identity does not match the packet store's index"]


def test_packet_missing_from_the_index_is_refused():
    trusted = copy.deepcopy(TRUSTED)
    del trusted["packet_index"]["SYN-PKT-PASS"]
    assert approval.review("SYN-PKT-PASS", checks.packet_hash(PASS), packets=PACKETS, trusted=trusted) == [
        "packet SYN-PKT-PASS is not in the packet store's index"]
