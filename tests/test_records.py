"""L3 and L7: the two record schemas, and the decision clock from server-side timestamps."""

from datetime import datetime, timedelta, timezone

from prior_auth import records
from prior_auth.checks import canonical_hash
from tests.test_pipeline import FakeGateway, honest_model
from prior_auth.agent.pipeline import run_case

PACKET = {"packet_id": "PKT-X", "findings": [{"criterion_id": "C1", "doc_id": "D", "page": 1, "line": 2, "value": "v"}]}


def test_recommendation_record_schema():
    r = records.recommendation_record(case_id="X", run_id="R", packet=PACKET, decision={"decision": "approve"},
                                      policy_version="v1", received_at="a", recommended_at="b")
    assert set(r) == {"record_type", "case_id", "run_id", "packet_id", "packet_hash", "recommendation", "citations",
                      "policy_version", "received_at", "recommended_at"}
    assert r["packet_hash"] == canonical_hash(PACKET)
    assert r["citations"] == [{"criterion_id": "C1", "doc_id": "D", "page": 1, "line": 2}]  # no chart text


def test_decision_record_schema():
    d = records.decision_record(case_id="X", run_id="R", decision="adverse_determination", reason="why",
                                reviewer_identity="c", reviewer_identity_source="clinician-app",
                                recommendation_key="k", recommendation_record_hash="h", decided_at="t")
    assert set(d) == {"record_type", "case_id", "run_id", "decision", "reason", "reviewer_identity",
                      "reviewer_identity_source", "recommendation_key", "recommendation_record_hash", "decided_at"}


def _at(start: str, seconds: int) -> str:
    return (datetime.fromisoformat(start) + timedelta(seconds=seconds)).isoformat()


def test_decision_clock_windows_and_boundaries():
    t0 = "2026-10-16T12:00:00+00:00"
    assert records.within_window(t0, _at(t0, records.STANDARD_WINDOW_S))
    assert not records.within_window(t0, _at(t0, records.STANDARD_WINDOW_S + 1))
    assert records.within_window(t0, _at(t0, records.EXPEDITED_WINDOW_S), expedited=True)
    assert not records.within_window(t0, _at(t0, records.EXPEDITED_WINDOW_S + 1), expedited=True)
    assert records.STANDARD_WINDOW_S == 7 * 86400 and records.EXPEDITED_WINDOW_S == 72 * 3600


def test_received_at_is_server_generated():
    """The recommendation record's timestamps come from the server clock, whatever the model says."""
    seen = []
    gw = FakeGateway()
    before = datetime.now(timezone.utc).replace(microsecond=0)
    run_case("SYN-CASE-CLEAN-1", gw, lambda c: honest_model(c, summary="Received 1999-01-01T00:00:00Z."),
             gw.store_packet, record_recommendation=lambda r: seen.append(r) or "h")
    after = datetime.now(timezone.utc)
    received = datetime.fromisoformat(seen[0]["received_at"])
    assert before <= received <= after
    assert "1999" not in seen[0]["received_at"] + seen[0]["recommended_at"]
