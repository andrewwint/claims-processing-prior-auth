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


SHAPE_KEYS = ("sub", "client_id", "token_use", "scope", "cognito:groups", "username", "iss", "aud")


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


def main() -> int:
    session = boto3.Session(region_name="us-east-1")
    out = gc.outputs()
    named = known_values(out)
    {"state": state, "smoke": smoke, "tokens": tokens}[sys.argv[1]](session, out, named)
    return 0


if __name__ == "__main__":
    sys.exit(main())
