"""Rerun the boundary smoke checks after a deploy and compare them with the recorded evidence.

Checks (PM, 2026-10-16): both tool lists, the approval allow/refuse pair, the
forged packet refused, the packet without a hash denied by Cedar, and the agent
rejected at the reviewer gateway. Each response is reduced to its outcome
(HTTP status, JSON-RPC error code, tool names, approved/status/refusal reasons)
and compared with the latest recorded evidence for that check (BASELINE). Any difference fails.

Usage: python -m scripts.boundary_smoke   (exit 1 on any difference: roll back and stop)
"""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import boto3

from scripts import gateway_client as gc
from scripts.record_d1 import _approval_args
from scripts.redact import find_unredacted, known_values, redact

D1 = Path("evidence/2026-10-16/d1")
# check -> (baseline file, key in it). The baseline is the latest recorded at a clean SHA
# (beat 1, 9a45b1b); the Cedar missing-hash denial is recorded only in the D1 calls.
BASELINE = {
    "agent_tools_list": ("beat1-and-approval-checks-9a45b1b.json", "beat1_agent_gateway_tools_list"),
    "reviewer_tools_list_clinician": ("beat1-and-approval-checks-9a45b1b.json", "beat1_reviewer_gateway_tools_list_clinician"),
    "approval_passing_packet_approved": ("beat1-and-approval-checks-9a45b1b.json", "approval_passing_packet_approved"),
    "approval_failing_packet_refused": ("beat1-and-approval-checks-9a45b1b.json", "approval_failing_packet_refused"),
    "approval_forged_value_packet_refused": ("beat1-and-approval-checks-9a45b1b.json", "approval_forged_value_packet_refused"),
    "approval_missing_hash_denied_by_cedar": ("calls.json", "B6_record_approval_missing_hash_denied_by_policy"),
    "agent_rejected_at_reviewer_denial_tool": ("beat1-and-approval-checks-9a45b1b.json", "agent_rejected_at_reviewer_denial_tool"),
    "agent_rejected_at_reviewer_approval_tool": ("beat1-and-approval-checks-9a45b1b.json", "agent_rejected_at_reviewer_approval_tool"),
}


def outcome(response: dict) -> dict:
    body = response.get("body")
    o = {"http_status": response.get("http_status")}
    if not isinstance(body, dict):
        return o
    if "error" in body:
        o["error_code"] = body["error"].get("code")
        return o
    result = body.get("result", {})
    if "tools" in result:
        o["tools"] = sorted(t["name"] for t in result["tools"])
    for item in result.get("content", []):
        if item.get("type") == "text":
            tool = json.loads(item["text"])
            o.update({k: tool[k] for k in ("approved", "recorded", "status", "reasons") if k in tool})
    return o


def run_checks(session, out) -> dict:
    agent = gc.agent_token(out, session)
    clinician = gc.user_token(out, session, "syn-clinician-1")
    A, R = out["AgentGatewayUrl"], out["ReviewerGatewayUrl"]
    approve = lambda args: gc.mcp(A, agent, "tools/call", {"name": "ApprovalService___record_approval", "arguments": args})
    on_reviewer = lambda tool, args: gc.mcp(R, agent, "tools/call", {"name": f"ReviewerTools___{tool}", "arguments": args})
    return {
        "agent_tools_list": gc.mcp(A, agent, "tools/list"),
        "reviewer_tools_list_clinician": gc.mcp(R, clinician, "tools/list"),
        "approval_passing_packet_approved": approve(_approval_args("SYN-PKT-PASS")),
        "approval_failing_packet_refused": approve(_approval_args("SYN-PKT-FAIL")),
        "approval_forged_value_packet_refused": approve(_approval_args("SYN-PKT-FORGED-VALUE")),
        "approval_missing_hash_denied_by_cedar": approve({"packet_id": "SYN-PKT-PASS"}),
        "agent_rejected_at_reviewer_denial_tool": on_reviewer("record_adverse_determination",
                                                              {"case_id": "SYN-CASE-1", "reason": "synthetic"}),
        "agent_rejected_at_reviewer_approval_tool": on_reviewer("record_clinician_approval", {"case_id": "SYN-CASE-1"}),
    }


def main() -> int:
    session = boto3.Session(region_name="us-east-1")
    out = gc.outputs()
    files = {f: json.loads((D1 / f).read_text()) for f, _ in BASELINE.values()}
    live = run_checks(session, out)
    compared = {k: {"baseline": f"{f}#{key}", "recorded": outcome(files[f][key]), "live": outcome(live[k])}
                for k, (f, key) in BASELINE.items()}
    for v in compared.values():
        v["same"] = v["recorded"] == v["live"]
    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    record = {"date": date.today().isoformat(), "sha": sha, "checks": compared,
              "all_same": all(v["same"] for v in compared.values())}
    text = redact(json.dumps(record, indent=2, sort_keys=True), known_values(out))
    assert not find_unredacted(text)
    path = Path(f"evidence/{record['date']}/boundary-smoke-{sha[:12]}.json")
    path.write_text(text + "\n")
    for k, v in compared.items():
        print("same" if v["same"] else "DIFFERS", k, "" if v["same"] else json.dumps(v))
    print("->", path)
    return 0 if record["all_same"] else 1


if __name__ == "__main__":
    sys.exit(main())
