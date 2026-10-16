"""Beats 2 and 3 end to end with fakes for the gateway and the model, plus every
row of docs/empty-output-rules.md, the session invariant (F7) and the F6 property."""

import itertools
import re
from pathlib import Path

import pytest

from data.cases import generate
from prior_auth import stores
from prior_auth.agent.pipeline import (Extraction, ModelAccessDenied, ModelUnavailable, run_case,
                                       session_id_for)
from prior_auth.agent.session import OutcomeRecorder
from prior_auth.decide import APPROVAL_ACTION, ROUTE_ACTION, GatewayError
from prior_auth.handlers import agent_tools, approval

ROOT = Path(__file__).resolve().parent.parent
CRITERIA = stores.criteria("SYN-PAYER-LARKSPUR", "63030")


class FakeGateway:
    """Dispatches to the real handlers; records ending-tool calls; can inject failures."""

    def __init__(self, fail=()):
        self.fail, self.calls, self.packets = set(fail), [], {}

    def store_packet(self, packet):
        self.packets[packet["packet_id"]] = packet

    def __call__(self, action, args):
        self.calls.append(action)
        if action in self.fail:
            raise GatewayError(f"injected failure on {action}")
        if action == APPROVAL_ACTION:
            failures, case_id = approval.review_stored(args.get("packet_id"), args.get("packet_hash"), self.packets.get)
            return {"approved": not failures, "reasons": failures, "case_id": case_id}
        tool = action.split("___", 1)[1]
        return agent_tools.TOOLS[tool](args)


def honest_model(case_id, summary="Synthetic summary."):
    case = stores.cases()[case_id]
    docs = {d: stores.document(d) for d in case["documents"]}
    cites = []
    for crit in CRITERIA:
        rule = crit["evidence_rule"]
        for doc_id, d in docs.items():
            if d and d["kind"] in rule["doc_kinds"]:
                for n, line in enumerate(d["pages"][0], start=1):
                    if re.search(rule["pattern"], line):
                        cites.append({"criterion_id": crit["id"], "doc_id": doc_id, "page": 1, "line": n,
                                      "value": "ignored by code"})
                        break
    return Extraction(citations=cites, summary=summary)


def run(case_id, gw=None, extract=None, cloudwatch=None):
    gw = gw or FakeGateway()
    return run_case(case_id, gw, extract or honest_model, gw.store_packet, cloudwatch=cloudwatch, model_id="m"), gw


# Beats 2 and 3
@pytest.mark.parametrize("case_id", ["SYN-CASE-CLEAN-1", "SYN-CASE-CLEAN-2"])
def test_beat2_clean_case_is_approved_by_decide(case_id):
    out, gw = run(case_id)
    assert out["outcome"] == "approved" and out["case_id"] == case_id
    assert gw.calls.count(APPROVAL_ACTION) == 1 and ROUTE_ACTION not in gw.calls


def test_beat3_one_note_removed_is_routed_with_the_gap_marked():
    out, gw = run("SYN-CASE-CF-1")
    assert out["outcome"] == "routed" and out["gaps"] == ["C3"] and out["reason"] == "criteria not met"
    assert APPROVAL_ACTION not in gw.calls


@pytest.mark.parametrize("case_id", ["SYN-CASE-CF-2", "SYN-CASE-WRONG-PATIENT", "SYN-CASE-FORGED"])
def test_every_needs_review_case_is_routed(case_id):
    out, _ = run(case_id)
    assert out["outcome"] == "routed"


def test_values_in_the_packet_come_from_the_chart_not_the_model():
    out, _ = run("SYN-CASE-CLEAN-1")
    assert all(f["value"] != "ignored by code" for f in out["packet"]["findings"])


# docs/empty-output-rules.md, one test per row
def test_eligibility_unknown():
    assert run("SYN-CASE-CLEAN-1", FakeGateway({"AgentTools___check_eligibility"}))[0]["reason"] == "eligibility unknown"


def test_no_verified_policy():
    assert run("SYN-CASE-CLEAN-1", FakeGateway({"AgentTools___fetch_policy_criteria"}))[0]["reason"] == "no verified policy"


def test_zero_findings_for_a_criterion_is_not_found():
    out, _ = run("SYN-CASE-CLEAN-1", extract=lambda c: Extraction(
        citations=[x for x in honest_model(c).citations if x["criterion_id"] != "C2"]))
    assert out["outcome"] == "routed" and out["gaps"] == ["C2"]


@pytest.mark.parametrize("ex", [Extraction(stop_reason="max_tokens"), Extraction(malformed=True),
                                Extraction(citations=[], stop_reason="content_filtered")])
def test_no_text_malformed_or_truncated_is_extraction_failed(ex):
    out, _ = run("SYN-CASE-CLEAN-1", extract=lambda c: ex)
    assert out["outcome"] == "routed" and out["reason"].startswith("extraction failed")


def test_throttled_or_timed_out_is_extraction_failed():
    def boom(c):
        raise ModelUnavailable("throttled")
    assert run("SYN-CASE-CLEAN-1", extract=boom)[0]["reason"] == "extraction failed: ModelUnavailable"


def test_access_denied_is_operator_alert_and_emits_the_metric():
    sent = []

    class CW:
        def put_metric_data(self, **kw):
            sent.append(kw)

    def denied(c):
        raise ModelAccessDenied()
    out, _ = run("SYN-CASE-CLEAN-1", extract=denied, cloudwatch=CW())
    assert out["outcome"] == "operator_alert" and sent[0]["MetricData"][0]["MetricName"] == "ModelAccessDenied"


def test_missing_summary_leaves_the_packet_valid_and_the_decision_unchanged():
    out, _ = run("SYN-CASE-CLEAN-1", extract=lambda c: honest_model(c, summary=""))
    assert out["outcome"] == "approved" and out["packet"]["model_summary"]["status"] == "missing"


def test_unexpected_exception_ends_as_needs_review():
    def crash(c):
        raise KeyError("boom")
    out, _ = run("SYN-CASE-CLEAN-1", extract=crash)
    assert out["outcome"] == "needs_review"


def test_record_approval_failure_routes_and_counts_a_disagreement():
    out, _ = run("SYN-CASE-CLEAN-1", FakeGateway({APPROVAL_ACTION}))
    assert out["outcome"] == "routed" and out["disagreement"] is True


def test_record_approval_refused_routes_and_counts_a_disagreement():
    class Tamper(FakeGateway):
        def store_packet(self, packet):
            super().store_packet({**packet, "case_id": "SYN-CASE-CLEAN-2"})
    out, _ = run("SYN-CASE-CLEAN-1", Tamper())
    assert out["outcome"] == "routed" and out["disagreement"] is True and "refused" in out["reason"]


def test_route_to_reviewer_failure_is_operator_alert():
    out, _ = run("SYN-CASE-CF-1", FakeGateway({ROUTE_ACTION}))
    assert out["outcome"] == "operator_alert"


# F7: exactly one terminal outcome
def test_second_terminal_outcome_is_refused():
    rec = OutcomeRecorder()
    assert rec.set({"outcome": "routed"}) is True
    assert rec.set({"outcome": "approved"}) is False and rec.violations == 1
    assert rec.outcome == {"outcome": "routed"}


# F6: a failure may slow a case down, never push it toward approval or denial
ACTIONS = ["AgentTools___check_eligibility", "AgentTools___fetch_policy_criteria", APPROVAL_ACTION, ROUTE_ACTION]
MODEL_FAILURES = [None, ModelAccessDenied, ModelUnavailable, KeyError, "max_tokens", "malformed"]


@pytest.mark.parametrize("case_id,fail_action,model_failure",
                         list(itertools.product(["SYN-CASE-CLEAN-1", "SYN-CASE-CF-1"], [None, *ACTIONS], MODEL_FAILURES)))
def test_no_injected_failure_produces_an_approval_or_denial(case_id, fail_action, model_failure):
    if fail_action is None and model_failure is None:
        pytest.skip("no failure injected")

    def extract(c):
        if model_failure in ("max_tokens",):
            return Extraction(stop_reason="max_tokens")
        if model_failure == "malformed":
            return Extraction(malformed=True)
        if model_failure is not None:
            raise model_failure("injected")
        return honest_model(c)

    out, gw = run(case_id, FakeGateway({fail_action} if fail_action else set()), extract=extract)
    triggered = model_failure is not None or fail_action in gw.calls
    assert out["outcome"] != "adverse_determination"
    if triggered:
        assert out["outcome"] in ("routed", "needs_review", "operator_alert")
    else:
        # The injected failure was never reached, so the outcome matches a run with no failure.
        assert out["outcome"] == run(case_id)[0]["outcome"]


# G10: only decide() calls the two ending tools
def test_only_decide_calls_the_ending_tools():
    offenders = []
    for path in (ROOT / "src").rglob("*.py"):
        text = path.read_text()
        for needle in ("APPROVAL_ACTION", "ROUTE_ACTION", "___record_approval", "___route_to_reviewer"):
            if needle in text and path.name not in ("decide.py", "schemas.py"):
                if not (path.name == "pipeline.py" and needle in ("APPROVAL_ACTION", "ROUTE_ACTION")):
                    offenders.append(f"{path.name}:{needle}")
    pipeline = (ROOT / "src/prior_auth/agent/pipeline.py").read_text()
    assert offenders == [] and "APPROVAL_ACTION" not in pipeline and "ROUTE_ACTION" not in pipeline


def test_session_ids_meet_the_runtime_minimum():
    assert len(session_id_for("")) >= 33 and len(session_id_for("SYN-CASE-CLEAN-1")) <= 256
    assert session_id_for("A") == session_id_for("A") != session_id_for("B")
