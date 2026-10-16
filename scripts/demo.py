"""The five-minute demo, one subcommand per beat.

Usage: python -m scripts.demo <1-6>

1  Both gateways side by side (tool lists).
2  Clean case: the Strands agent builds a cited packet; decide() approves.
3  One-note-removed counterfactual: routed to the reviewer, gap marked.
4  The agent refused at the reviewer gateway (authorizer, then Cedar).
5  The clinician succeeds with the same tool (workbench).
6  A trace with no chart text (canary scan with a positive control).
Beats 4 and 5 are shown back to back.
"""

import sys

import boto3

from scripts import gateway_client as gc

DENIAL = "ReviewerTools___record_adverse_determination"


def _names(response: dict) -> list[str]:
    body = response["body"]
    return sorted(t["name"] for t in body.get("result", {}).get("tools", [])) if isinstance(body, dict) else []


def beat1(session, out) -> None:
    agent = gc.agent_token(out, session)
    clinician = gc.user_token(out, session, "syn-clinician-1")
    print("Agent gateway (agent identity):")
    for n in _names(gc.mcp(out["AgentGatewayUrl"], agent, "tools/list")):
        print("  ", n)
    print("Reviewer gateway (clinician identity):")
    for n in _names(gc.mcp(out["ReviewerGatewayUrl"], clinician, "tools/list")):
        print("  ", n)


def beat4(session, out) -> None:
    agent = gc.agent_token(out, session)
    r = gc.mcp(out["ReviewerGatewayUrl"], agent, "tools/call",
               {"name": DENIAL, "arguments": {"case_id": "SYN-CASE-1", "reason": "demo"}})
    print(f"Agent calls {DENIAL} on the reviewer gateway -> HTTP {r['http_status']}: {r['body'].get('error', r['body'])}")
    print("Layer 2 (Cedar forbid) evidence: evidence/2026-10-16/d1/b4-layer2-agent-call.json")


def _run_case(case_id: str):
    def run(session, out) -> None:
        import json as _json
        from pathlib import Path as _Path

        from scripts.intake import intake_token, invoke
        arn = _json.loads(_Path(".local/runtime.json").read_text())["arn"]
        result = invoke(case_id, arn, intake_token(out, session))
        print(f"{case_id} -> {result['outcome']}" + (f" (gaps: {', '.join(result['gaps'])})" if result.get("gaps") else ""))
    return run


def not_built(beat: int, change: str):
    def run(session, out) -> None:
        print(f"Beat {beat} is delivered by `{change}` and is not built yet.")
    return run


BEATS = {
    "1": beat1,
    "2": _run_case("SYN-CASE-CLEAN-1"),
    "3": _run_case("SYN-CASE-CF-1"),
    "4": beat4,
    "5": not_built(5, "clinician-workbench"),
    "6": not_built(6, "evidence-record-and-trace"),
}


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in BEATS:
        print(__doc__, file=sys.stderr)
        return 2
    BEATS[argv[0]](boto3.Session(region_name="us-east-1"), gc.outputs())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
