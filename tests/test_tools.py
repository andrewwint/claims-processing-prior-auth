import copy
from types import SimpleNamespace

import pytest

from tools import agent_tools, packets, reviewer_tools
from tools.schemas import AGENT_TARGET, AGENT_TOOLS, REVIEWER_TARGET, REVIEWER_TOOLS

FIVE = {"check_eligibility", "fetch_policy_criteria", "extract_clinical_evidence", "record_approval", "route_to_reviewer"}
STORE = packets.load_fixture()
PASS, FAIL = STORE["SYN-PKT-PASS"], STORE["SYN-PKT-FAIL"]


def ctx(target, tool):
    return SimpleNamespace(client_context=SimpleNamespace(custom={"bedrockAgentCoreToolName": f"{target}___{tool}"}))


def call(tool, event):
    return agent_tools.handler(event, ctx(AGENT_TARGET, tool))


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


# B6: the approval service
def test_well_formed_call_for_failing_packet_is_refused_server_side():
    out = call("record_approval", {"packet_id": "SYN-PKT-FAIL", "packet_hash": packets.packet_hash(FAIL)})
    assert out["approved"] is False and out["status"] == "refused"
    assert out["reasons"] == ["criterion not met: Functional limitation documented"]


def test_passing_packet_is_recorded():
    out = call("record_approval", {"packet_id": "SYN-PKT-PASS", "packet_hash": packets.packet_hash(PASS)})
    assert out == {"approved": True, "status": "recorded", "packet_id": "SYN-PKT-PASS",
                   "packet_hash": packets.packet_hash(PASS)}


def test_hash_mismatch_is_refused():
    out = call("record_approval", {"packet_id": "SYN-PKT-PASS", "packet_hash": packets.packet_hash(FAIL)})
    assert out["approved"] is False
    assert out["reasons"][0].startswith("hash mismatch")


def test_unknown_packet_is_refused():
    out = call("record_approval", {"packet_id": "SYN-PKT-NONE", "packet_hash": "0" * 64})
    assert out["approved"] is False and out["reasons"] == ["unknown packet: SYN-PKT-NONE"]


def test_missing_fields_are_refused_even_if_policy_let_them_through():
    assert call("record_approval", {})["approved"] is False


def test_hash_is_canonical():
    reordered = dict(reversed(list(PASS.items())))
    assert packets.packet_hash(reordered) == packets.packet_hash(PASS)


@pytest.mark.parametrize("mutate,expected", [
    (lambda p: p["criteria"][1].update(evidence="no such finding"), "source match: Imaging confirms the diagnosis evidence not found in MRI-001"),
    (lambda p: p["sources"]["MRI-001"].update(patient_id="SYN-PAT-0002"), "same patient: Imaging confirms the diagnosis cites another patient's record"),
    (lambda p: p.pop("policy_version"), "schema: missing policy_version"),
    (lambda p: p["criteria"][0].update(source_id="NOPE"), "source match: Six weeks of conservative therapy cites unknown source NOPE"),
])
def test_each_check_refuses(mutate, expected):
    p = copy.deepcopy(PASS)
    mutate(p)
    assert packets.verify_for_approval({"X": p}, "X", packets.packet_hash(p)) == [expected]


def test_stubs_answer_each_other_tool():
    for tool in FIVE - {"record_approval"}:
        assert call(tool, {"case_id": "SYN-CASE-1"})["synthetic"] is True


def test_unknown_tool_is_an_error():
    assert "error" in call("record_adverse_determination", {})


def test_reviewer_tool_records_with_reason_and_refuses_without():
    c = ctx(REVIEWER_TARGET, "record_adverse_determination")
    assert reviewer_tools.handler({"case_id": "C", "reason": "No functional measure"}, c)["recorded"] is True
    assert reviewer_tools.handler({"case_id": "C", "reason": " "}, c)["recorded"] is False
