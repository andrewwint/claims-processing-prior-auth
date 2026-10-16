"""Record the deployed D1 state as redacted evidence.

Usage:
    python -m scripts.record_d1 state|smoke|tokens
"""

import json
import sys
import time
from datetime import date
from pathlib import Path

import boto3

from scripts import gateway_client as gc
from scripts.redact import find_unredacted, known_values, redact

OUT = Path(f"evidence/{date.today().isoformat()}/d1")


def save(name: str, payload, named: dict) -> None:
    text = redact(json.dumps(payload, indent=2, sort_keys=True, default=str), named)
    leftovers = find_unredacted(text, list(named))
    if leftovers:
        raise RuntimeError(f"unredacted identifiers in {name}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(text + "\n")


def state(session, out, named) -> None:
    ac = session.client("bedrock-agentcore-control")
    for key in ("AgentGatewayId", "ReviewerGatewayId"):
        for _ in range(60):
            gw = ac.get_gateway(gatewayIdentifier=out[key])
            if gw["status"] in ("READY", "FAILED"):
                break
            time.sleep(5)
        targets = [ac.get_gateway_target(gatewayIdentifier=out[key], targetId=t["targetId"])
                   for t in ac.get_paginator("list_gateway_targets").paginate(gatewayIdentifier=out[key]).search("items[]")]
        keep = {k: gw.get(k) for k in ("name", "status", "protocolType", "authorizerType", "authorizerConfiguration",
                                         "policyEngineConfiguration", "roleArn", "gatewayArn")}
        keep["targets"] = [{k: t.get(k) for k in ("name", "status", "credentialProviderConfigurations")} |
                           {"tools": [x["name"] for x in t["targetConfiguration"]["mcp"]["lambda"]["toolSchema"]["inlinePayload"]]}
                           for t in targets]
        save(f"get-gateway-{gw['name']}.json", keep, named)
        print(gw["name"], gw["status"], gw.get("policyEngineConfiguration", {}).get("mode"),
              [(t["name"], t["status"]) for t in targets])
    engine = ac.get_policy_engine(policyEngineId=out["PolicyEngineId"])
    pols = list(ac.get_paginator("list_policies").paginate(policyEngineId=out["PolicyEngineId"]).search("policies[]"))
    save("policy-engine.json", {"name": engine["name"], "status": engine["status"], "policy_count": len(pols)}, named)
    print("engine", engine["status"], "policies:", len(pols))


def _summary(response: dict) -> str:
    body = response["body"]
    detail = body.get("result", body.get("error")) if isinstance(body, dict) else str(body)
    return f"{response['http_status']} {json.dumps(detail, default=str)[:240]}"


def smoke(session, out, named) -> None:
    """Fail-closed check: with the engine attached and no policies, every call is denied."""
    agent = gc.agent_token(out, session)
    clinician = gc.user_token(out, session, "syn-clinician-1")
    results = {
        "agent_tools_list": gc.mcp(out["AgentGatewayUrl"], agent, "tools/list"),
        "agent_call_check_eligibility": gc.mcp(out["AgentGatewayUrl"], agent, "tools/call",
            {"name": "AgentTools___check_eligibility", "arguments": {"member_id": "SYN-MBR-1", "cpt_code": "63030"}}),
        "clinician_tools_list": gc.mcp(out["ReviewerGatewayUrl"], clinician, "tools/list"),
        "clinician_call_denial_tool": gc.mcp(out["ReviewerGatewayUrl"], clinician, "tools/call",
            {"name": "ReviewerTools___record_adverse_determination", "arguments": {"case_id": "SYN-CASE-1", "reason": "smoke"}}),
        "agent_token_on_reviewer_gateway": gc.mcp(out["ReviewerGatewayUrl"], agent, "tools/list"),
        "no_token_on_agent_gateway": gc.mcp(out["AgentGatewayUrl"], None, "tools/list"),
    }
    save("smoke-fail-closed.json", results, named)
    for k, v in results.items():
        print(k, _summary(v))


SHAPE_KEYS = ("sub", "client_id", "token_use", "scope", "cognito:groups", "pa_role", "pa_tenant", "username", "iss", "aud")


def _shape(c: dict) -> dict:
    """Claim names, types and safe values; identifiers stay for redaction to replace."""
    return {k: {"type": type(c[k]).__name__, "value": c[k]} for k in SHAPE_KEYS if k in c} | {
        "other_claims": sorted(k for k in c if k not in SHAPE_KEYS and k not in ("exp", "iat", "auth_time", "jti", "origin_jti", "event_id", "version"))}


def tokens(session, out, named) -> None:
    """Task 3.2: record the agent and clinician token formats (never the tokens)."""
    agent = gc.claims(gc.agent_token(out, session))
    clinician = gc.claims(gc.user_token(out, session, "syn-clinician-1"))
    staff = gc.claims(gc.user_token(out, session, "syn-tenant-a-staff"))
    record = {
        "agent": _shape(agent),
        "agent_sub_equals_client_id": agent.get("sub") == agent.get("client_id") == out["AgentClientId"],
        "clinician": _shape(clinician),
        "tenant_staff": _shape(staff),
        "groups_claim_is_json_array": isinstance(clinician.get("cognito:groups"), list),
    }
    save("token-formats.json", record, named)
    print("agent sub == client_id == AgentClientId:", record["agent_sub_equals_client_id"])
    print("agent claims:", sorted(agent))
    print("clinician cognito:groups:", clinician.get("cognito:groups"), "| type:", type(clinician.get("cognito:groups")).__name__)
    print("tenant staff cognito:groups:", staff.get("cognito:groups"))
    print("clinician token_use/scope:", clinician.get("token_use"), clinician.get("scope"))


def policies(session, out, named) -> None:
    """B3, B5: the deployed policy text and status, redacted to the article's placeholders."""
    ac = session.client("bedrock-agentcore-control")
    named = {**named, out["AgentClientId"]: "<agent-client-id>"}
    rows = []
    for p in ac.get_paginator("list_policies").paginate(policyEngineId=out["PolicyEngineId"]).search("policies[]"):
        full = ac.get_policy(policyEngineId=out["PolicyEngineId"], policyId=p["policyId"])
        rows.append({k: full.get(k) for k in ("name", "status", "enforcementMode", "definition")})
    save("policies.json", sorted(rows, key=lambda r: r["name"]), named)
    forbid = next(r for r in rows if "forbid" in r["name"])
    text = redact(forbid["definition"]["cedar"]["statement"], named)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "forbid-deployed-redacted.cedar").write_text(text + "\n")
    for r in rows:
        print(r["name"], r["status"], r["enforcementMode"])


def _approval_args(packet_id: str) -> dict:
    from prior_auth.checks import packet_hash
    from prior_auth.handlers.approval import load_fixtures
    _, packets = load_fixtures()
    return {"packet_id": packet_id, "packet_hash": packet_hash(packets[packet_id])}


def calls(session, out, named, filename: str = "calls.json") -> None:
    """Allowed, refused and denied calls through the live boundary."""
    agent = gc.agent_token(out, session)
    clinician = gc.user_token(out, session, "syn-clinician-1")
    staff = gc.user_token(out, session, "syn-tenant-a-staff")
    A, R = out["AgentGatewayUrl"], out["ReviewerGatewayUrl"]
    deny_args = {"case_id": "SYN-CASE-1", "reason": "No functional limitation measure documented (synthetic)."}
    results = {
        "B1_B2_agent_tools_list": gc.mcp(A, agent, "tools/list"),
        "agent_call_check_eligibility": gc.mcp(A, agent, "tools/call",
            {"name": "AgentTools___check_eligibility", "arguments": {"member_id": "SYN-MBR-1", "cpt_code": "63030"}}),
        "B6_record_approval_passing_packet": gc.mcp(A, agent, "tools/call",
            {"name": "ApprovalService___record_approval", "arguments": _approval_args("SYN-PKT-PASS")}),
        "B6_record_approval_failing_packet_refused_server_side": gc.mcp(A, agent, "tools/call",
            {"name": "ApprovalService___record_approval", "arguments": _approval_args("SYN-PKT-FAIL")}),
        "B6_record_approval_forged_packet_refused_server_side": gc.mcp(A, agent, "tools/call",
            {"name": "ApprovalService___record_approval", "arguments": _approval_args("SYN-PKT-FORGED")}),
        "B6_record_approval_missing_hash_denied_by_policy": gc.mcp(A, agent, "tools/call",
            {"name": "ApprovalService___record_approval", "arguments": {"packet_id": "SYN-PKT-PASS"}}),
        "B8_clinician_tools_list": gc.mcp(R, clinician, "tools/list"),
        "B8_clinician_records_adverse_determination": gc.mcp(R, clinician, "tools/call",
            {"name": "ReviewerTools___record_adverse_determination", "arguments": deny_args}),
        "B4_layer1_agent_token_on_reviewer": gc.mcp(R, agent, "tools/call",
            {"name": "ReviewerTools___record_adverse_determination", "arguments": deny_args}),
        "layer1_non_clinician_staff_on_reviewer": gc.mcp(R, staff, "tools/call",
            {"name": "ReviewerTools___record_adverse_determination", "arguments": deny_args}),
    }
    save(filename, results, named)
    for k, v in results.items():
        print(k, _summary(v))


def reviewer_gateway(session, out, named, label: str) -> dict:
    """D4: the reviewer gateway's authorizer before, during and after the test configuration."""
    gw = session.client("bedrock-agentcore-control").get_gateway(gatewayIdentifier=out["ReviewerGatewayId"])
    jwt = gw["authorizerConfiguration"]["customJWTAuthorizer"]
    state = {"label": label, "status": gw["status"], "allowedClients": jwt.get("allowedClients"),
             "customClaims": jwt.get("customClaims"), "policy_mode": gw["policyEngineConfiguration"]["mode"]}
    save(f"b4-reviewer-gateway-{label}.json", state, named)
    clinician_only = jwt.get("allowedClients") == [out["ClinicianClientId"]] and bool(jwt.get("customClaims"))
    print(label, gw["status"], "clinician-only:", clinician_only, "| clients:", len(jwt.get("allowedClients", [])),
          "| claim check:", bool(jwt.get("customClaims")))
    return {"clinician_only": clinician_only}


def b4_call(session, out, named) -> None:
    agent = gc.agent_token(out, session)
    r = gc.mcp(out["ReviewerGatewayUrl"], agent, "tools/call",
               {"name": "ReviewerTools___record_adverse_determination",
                "arguments": {"case_id": "SYN-CASE-1", "reason": "B4 layer 2 test (synthetic)"}})
    save("b4-layer2-agent-call.json", r, named)
    print("B4 layer 2 agent call:", _summary(r))


def beat1(session, out, named) -> None:
    """Beat 1 plus the approval-service checks, after the combined deploy."""
    agent = gc.agent_token(out, session)
    clinician = gc.user_token(out, session, "syn-clinician-1")
    A, R = out["AgentGatewayUrl"], out["ReviewerGatewayUrl"]
    approve = lambda pid: gc.mcp(A, agent, "tools/call", {"name": "ApprovalService___record_approval",
                                                           "arguments": _approval_args(pid)})
    deny_args = {"case_id": "SYN-CASE-1", "reason": "No functional limitation measure documented (synthetic)."}
    results = {
        "beat1_agent_gateway_tools_list": gc.mcp(A, agent, "tools/list"),
        "beat1_reviewer_gateway_tools_list_clinician": gc.mcp(R, clinician, "tools/list"),
        "approval_passing_packet_approved": approve("SYN-PKT-PASS"),
        "approval_failing_packet_refused": approve("SYN-PKT-FAIL"),
        "approval_forged_value_packet_refused": approve("SYN-PKT-FORGED-VALUE"),
        "agent_rejected_at_reviewer_denial_tool": gc.mcp(R, agent, "tools/call",
            {"name": "ReviewerTools___record_adverse_determination", "arguments": deny_args}),
        "agent_rejected_at_reviewer_approval_tool": gc.mcp(R, agent, "tools/call",
            {"name": "ReviewerTools___record_clinician_approval", "arguments": {"case_id": "SYN-CASE-1"}}),
        "clinician_records_approval": gc.mcp(R, clinician, "tools/call",
            {"name": "ReviewerTools___record_clinician_approval", "arguments": {"case_id": "SYN-CASE-1"}}),
    }
    import subprocess
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    results = {"deployed_sha": sha, "tree_clean": not subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, text=True).stdout.strip(), **results}
    save(f"beat1-and-approval-checks-{sha}.json", results, named)
    for k, v in results.items():
        print(k, _summary(v) if isinstance(v, dict) else v)


def main() -> int:
    session = boto3.Session(region_name="us-east-1")
    out = gc.outputs()
    named = known_values(out)
    if sys.argv[1] == "reviewer":
        result = reviewer_gateway(session, out, named, sys.argv[2])
        if len(sys.argv) > 3 and sys.argv[3] == "--require-clinician-only" and not result["clinician_only"]:
            print("FAIL: the reviewer gateway is not back to clinician-only", file=sys.stderr)
            return 1
        return 0
    if sys.argv[1] == "calls" and len(sys.argv) > 2:
        calls(session, out, named, sys.argv[2])
        return 0
    {"state": state, "smoke": smoke, "tokens": tokens, "policies": policies, "calls": calls,
     "b4call": b4_call, "beat1": beat1}[sys.argv[1]](session, out, named)
    return 0


if __name__ == "__main__":
    sys.exit(main())
