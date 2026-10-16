"""The decision is code (G10). decide() is the only caller of record_approval and
route_to_reviewer; the model never chooses which tool ends the case."""

from dataclasses import dataclass, field

from prior_auth import checks

APPROVAL_ACTION = "ApprovalService___record_approval"
ROUTE_ACTION = "AgentTools___route_to_reviewer"


@dataclass(frozen=True)
class Approve:
    packet_id: str
    packet_hash: str


@dataclass(frozen=True)
class Route:
    reason: str
    gaps: list = field(default_factory=list)


def decide(packet: dict, request: dict, criteria: list[dict], chart: dict) -> Approve | Route:
    verdict = checks.recompute(packet, request, criteria, chart)
    if verdict.approvable:
        return Approve(packet["packet_id"], checks.packet_hash(packet))
    reason = "no verified policy" if verdict.failures == ["no verified policy"] else (
        "criteria not met" if verdict.gaps and not verdict.failures else "checks failed")
    return Route(reason, verdict.gaps)


class GatewayError(RuntimeError):
    """A tool call failed: denied by Cedar, rejected, or errored."""


def act(decision: Approve | Route, case_id: str, call, store_packet=None, packet: dict | None = None) -> dict:
    """Carry out the decision through the gateway (D6 rows for the ending tools).

    call(action, arguments) returns the tool result or raises GatewayError.
    Returns {"outcome": approved | routed | operator_alert, ...}.
    """
    if isinstance(decision, Approve):
        try:
            if store_packet is not None:
                store_packet(packet)
            result = call(APPROVAL_ACTION, {"packet_id": decision.packet_id, "packet_hash": decision.packet_hash})
            if result.get("approved") is True:
                return {"outcome": "approved", "case_id": result.get("case_id", case_id)}
            reason = "approval service refused: " + "; ".join(result.get("reasons", []))
        except GatewayError as e:
            reason = f"approval call failed: {e}"
        # decide() approved but the service did not: route, and count the disagreement.
        routed = route_case(case_id, reason, [], call)
        return {**routed, "disagreement": True}
    return route_case(case_id, decision.reason, decision.gaps, call)


def route_case(case_id: str, reason: str, gaps: list, call) -> dict:
    try:
        call(ROUTE_ACTION, {"case_id": case_id, "reason": reason, "gaps": gaps})
    except GatewayError as e:
        # The case cannot reach a person: an operator must act.
        return {"outcome": "operator_alert", "reason": f"route_to_reviewer failed: {e}", "gaps": gaps}
    return {"outcome": "routed", "reason": reason, "gaps": gaps}
