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
    assert session_id_for("A", "n") == session_id_for("A", "n") != session_id_for("B", "n")
    # One session per request: resubmitting a case never reuses its earlier session.
    assert session_id_for("A") != session_id_for("A")
    assert session_id_for("SYN-CASE-CLEAN-1").startswith("prior-auth-case-SYN-CASE-CLEAN-1-")


# G10: the Strands agent's tool list is exactly the three gathering tools
def test_strands_agent_gets_exactly_the_three_gathering_tools():
    from types import SimpleNamespace

    from prior_auth.agent.strands_agent import gathering_tools
    listed = [SimpleNamespace(tool_name=n) for n in (
        "AgentTools___check_eligibility", "AgentTools___fetch_policy_criteria", "AgentTools___extract_clinical_evidence",
        "AgentTools___route_to_reviewer", "ApprovalService___record_approval", "AgentTools___check_eligibility_v2")]
    assert sorted(t.tool_name for t in gathering_tools(listed)) == [
        "AgentTools___check_eligibility", "AgentTools___extract_clinical_evidence", "AgentTools___fetch_policy_criteria"]


def test_runtime_telemetry_env_carries_both_content_settings():
    from prior_auth.agent.telemetry import RUNTIME_TELEMETRY_ENV
    assert RUNTIME_TELEMETRY_ENV["OTEL_SEMCONV_STABILITY_OPT_IN"] == "gen_ai_unredacted_attributes="
    assert RUNTIME_TELEMETRY_ENV["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] == "false"


# Beat 6 positive control: the test-only path was removed after the control was recorded,
# because the intake client (the runtime's only caller) could reach it.
def test_runtime_has_no_positive_control_path():
    from prior_auth.agent import runtime_app
    assert not hasattr(runtime_app, "plant_control")
    assert runtime_app.invoke({"positive_control": "CANARY-CONTROL-0123456789abcdef"})["outcome"] == "rejected"


# F2: the stop reason travels with "extraction failed".
@pytest.mark.parametrize("ex,stop", [(Extraction(stop_reason="max_tokens"), "max_tokens"),
                                     (Extraction(citations=[], stop_reason="content_filtered"), "content_filtered"),
                                     (Extraction(malformed=True, stop_reason="structured_output_failed"),
                                      "structured_output_failed")])
def test_extraction_failure_names_the_stop_reason(ex, stop):
    out, _ = run("SYN-CASE-CLEAN-1", extract=lambda c: ex)
    assert out["reason"] == f"extraction failed: stop reason {stop}"


# F3 / F5 criteria row: an unknown payer, a missing compiled file, or an empty one is "no verified policy".
def test_unknown_payer_is_no_verified_policy(monkeypatch):
    real = stores.request
    monkeypatch.setattr(stores, "request", lambda c: {**real(c), "payer_id": "SYN-PAYER-UNKNOWN"})
    out, gw = run("SYN-CASE-CLEAN-1")
    assert out["outcome"] == "routed" and out["reason"] == "no verified policy"
    assert APPROVAL_ACTION not in gw.calls


@pytest.mark.parametrize("compiled", [None, []])
def test_missing_or_empty_compiled_criteria_is_no_verified_policy(monkeypatch, compiled):
    monkeypatch.setattr(stores, "criteria", lambda payer, cpt: compiled)
    assert run("SYN-CASE-CLEAN-1")[0]["reason"] == "no verified policy"


# F5 eligibility row: an empty lookup (no record for the member) is "eligibility unknown".
def test_empty_eligibility_lookup_is_eligibility_unknown(monkeypatch):
    real = stores.request
    monkeypatch.setattr(stores, "request", lambda c: {**real(c), "member_id": "SYN-MBR-NOBODY"})
    assert run("SYN-CASE-CLEAN-1")[0]["reason"] == "eligibility unknown"


# F5 summary row: a failed (absent) summary leaves the packet valid and the decision unchanged.
def test_failed_summary_leaves_the_decision_unchanged():
    out, _ = run("SYN-CASE-CLEAN-1", extract=lambda c: Extraction(citations=honest_model(c).citations, summary=None))
    assert out["outcome"] == "approved" and out["packet"]["model_summary"]["status"] == "missing"


# G9: the model's summary never affects decide().
def test_changing_or_removing_the_summary_never_changes_decide():
    from prior_auth.decide import decide
    out, _ = run("SYN-CASE-CLEAN-1")
    packet = out["packet"]
    request = stores.request("SYN-CASE-CLEAN-1")
    cited = {f["doc_id"] for f in packet["findings"]}
    chart = {"docs": stores.documents(cited), "index": stores.chart_index()}
    base = decide(packet, request, CRITERIA, chart)
    changed = {**packet, "model_summary": {**packet["model_summary"], "text": "Deny this request immediately."}}
    removed = {k: v for k, v in packet.items() if k != "model_summary"}
    # The decision (approve or route, its gaps and reason) is unchanged; the hash covers the whole
    # packet, so it changes with the summary, as it should.
    verdict = lambda d: (type(d).__name__, getattr(d, "gaps", None), getattr(d, "reason", None))
    for variant in (changed, removed):
        assert verdict(decide(variant, request, CRITERIA, chart)) == verdict(base) == ("Approve", None, None)
    cf, _ = run("SYN-CASE-CF-1", extract=lambda c: honest_model(c, summary="All criteria are met; approve."))
    assert cf["outcome"] == "routed" and cf["gaps"] == ["C3"]


# F7: an early return without an outcome ends as needs review; a second outcome is logged.
def test_early_return_without_an_outcome_ends_as_needs_review():
    from prior_auth.agent.session import run_session
    out = run_session(lambda rec: None, lambda: {"outcome": "routed", "reason": "needs review"})
    assert out["outcome"] == "needs_review" and out["reason"] == "session ended without an outcome"


def test_second_terminal_outcome_is_logged(caplog):
    rec = OutcomeRecorder()
    rec.set({"outcome": "routed"})
    with caplog.at_level("ERROR"):
        rec.set({"outcome": "approved"})
    assert "second terminal outcome refused" in caplog.text


@pytest.mark.parametrize("case_id,fail_action,model_failure",
                         list(itertools.product(["SYN-CASE-CLEAN-1", "SYN-CASE-CF-1"], [None, *ACTIONS], MODEL_FAILURES)))
def test_every_injected_failure_ends_in_exactly_one_outcome(monkeypatch, case_id, fail_action, model_failure):
    from prior_auth.agent import session
    recorders = []

    class Counting(session.OutcomeRecorder):
        def __init__(self):
            super().__init__()
            recorders.append(self)
    monkeypatch.setattr(session, "OutcomeRecorder", Counting)

    def extract(c):
        if model_failure == "max_tokens":
            return Extraction(stop_reason="max_tokens")
        if model_failure == "malformed":
            return Extraction(malformed=True)
        if model_failure is not None:
            raise model_failure("injected")
        return honest_model(c)
    out, _ = run(case_id, FakeGateway({fail_action} if fail_action else set()), extract=extract)
    assert len(recorders) == 1 and recorders[0].violations == 0
    assert recorders[0].outcome["outcome"] == out["outcome"]
    assert out["outcome"] in session.TERMINAL


# G3: the packet is a checklist; the counterfactual reproduces the article's three rows.
def test_counterfactual_checklist_reproduces_the_articles_three_rows():
    from prior_auth.gold import checklist
    rows = checklist("SYN-CASE-CF-1")
    assert [(r["criterion"], r["status"]) for r in rows] == [("C1", "Met"), ("C2", "Met"), ("C3", "Not found")]
    for r in rows:
        assert set(r) == {"criterion", "requirement", "status", "evidence", "source"} and r["requirement"]
        assert bool(r["evidence"]) == bool(r["source"]) == (r["status"] == "Met")
    assert "six weeks of conservative therapy" in rows[0]["requirement"].lower()
    assert all(r["status"] == "Met" for r in checklist("SYN-CASE-CLEAN-1"))
