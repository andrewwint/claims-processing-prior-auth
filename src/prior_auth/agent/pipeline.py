"""One case, end to end: gather, extract (model), build the packet, decide, act.

The model sits behind extract(); everything that decides is code. Each step
follows its row in docs/empty-output-rules.md.
"""

from dataclasses import dataclass, field

from prior_auth import checks, records, stores
from prior_auth.agent import operator
from prior_auth.agent.session import run_session
from prior_auth.decide import GatewayError, act, decide, route_case

ELIGIBILITY = "AgentTools___check_eligibility"
CRITERIA = "AgentTools___fetch_policy_criteria"
EXTRACT = "AgentTools___extract_clinical_evidence"


@dataclass
class Extraction:
    citations: list = field(default_factory=list)
    summary: str = ""
    stop_reason: str = "end_turn"
    malformed: bool = False


class ModelAccessDenied(RuntimeError):
    pass


class ModelUnavailable(RuntimeError):
    """Throttled or timed out after retries."""


SUMMARY_LABEL = "Model summary. Not used for any decision."


def session_id_for(case_id: str, nonce: str | None = None) -> str:
    """runtimeSessionId must be 33-256 characters. Readable by case, but unique per request:
    a reused session ID lands on the same microVM, which can still be running an earlier deploy."""
    import hashlib
    import uuid
    nonce = nonce or uuid.uuid4().hex
    return f"prior-auth-case-{case_id}-{hashlib.sha256(case_id.encode()).hexdigest()[:8]}-{nonce}"


def packet_id_for(case_id: str) -> str:
    """The packet store key encodes its case, so a packet can never choose another case."""
    return f"PKT-{case_id}"


def _mark_span(name: str, value: str) -> None:
    try:
        from opentelemetry import trace
        trace.get_current_span().set_attribute(name, value)
    except Exception:  # telemetry must never change an outcome
        pass


def run_case(case_id: str, call, extract, store_packet, cloudwatch=None, model_id: str = "",
             record_recommendation=None) -> dict:
    """call(action, args) -> result | raises GatewayError; extract(case_id) -> Extraction;
    store_packet(packet) writes the packet before approval; record_recommendation(record) -> hash
    writes the recommendation record before the decision is acted on (every outcome)."""
    request = stores.request(case_id)
    received_at = records.now()  # server-generated; never from the model or the packet
    run_id = records.new_run_id(received_at)
    _mark_span("pa.case_id", case_id)
    _mark_span("pa.run_id", run_id)

    def recommend(packet, decision: dict, policy_version=None) -> None:
        if record_recommendation is None:
            return
        record = records.recommendation_record(
            case_id=case_id, run_id=run_id, packet=packet or {"packet_id": None, "findings": []},
            decision=decision, policy_version=policy_version, received_at=received_at, recommended_at=records.now())
        _mark_span("pa.recommendation_record_sha256", record_recommendation(record))

    def route(reason, gaps=()):
        recommend(None, {"decision": "route", "reason": reason, "gaps": list(gaps)})
        return route_case(case_id, reason, list(gaps), call, run_id)

    def body(rec):
        if request is None:
            rec.set(route("no request record"))
            return
        try:
            elig = call(ELIGIBILITY, {"member_id": request["member_id"], "cpt_code": request["cpt_code"]})
        except GatewayError:
            elig = None
        if not elig or not elig.get("eligible"):
            rec.set(route("eligibility unknown"))
            return
        crit = stores.criteria(request["payer_id"], request["cpt_code"])
        try:
            listed = call(CRITERIA, {"payer_id": request["payer_id"], "cpt_code": request["cpt_code"]})
        except GatewayError:
            listed = {"verified_policy": False}
        if not crit or not listed.get("verified_policy"):
            rec.set(route("no verified policy"))
            return
        try:
            ex = extract(case_id)
        except ModelAccessDenied:
            if cloudwatch is not None:
                operator.emit_model_access_denied(cloudwatch, model_id)
            rec.set({"outcome": "operator_alert", "reason": "model access denied"})
            return
        except ModelUnavailable as e:
            rec.set(route(f"extraction failed: {type(e).__name__}"))
            return
        if ex.malformed or ex.stop_reason == "max_tokens" or (not ex.citations and ex.stop_reason != "end_turn"):
            rec.set(route(f"extraction failed: stop reason {ex.stop_reason}"))
            return
        case_docs = stores.cases()[case_id]["documents"]
        docs = stores.documents(case_docs)
        packet = {
            "packet_id": packet_id_for(case_id),
            "case_id": case_id,
            "run_id": run_id,
            "findings": checks.findings_from_citations(ex.citations, docs),
            "model_summary": {"label": SUMMARY_LABEL, "text": ex.summary or None,
                              "status": "present" if ex.summary else "missing"},
        }
        chart = {"docs": docs, "index": stores.chart_index()}
        decision = decide(packet, request, crit, chart)
        recommend(packet, {"decision": "approve"} if hasattr(decision, "packet_hash")
                  else {"decision": "route", "reason": decision.reason, "gaps": decision.gaps},
                  crit[0]["policy_version"])
        rec.set(act(decision, case_id, call, store_packet, packet, run_id) | {"packet": packet, "run_id": run_id})

    return run_session(body, lambda: route("needs review"))
