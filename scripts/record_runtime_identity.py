"""Record A4 and A5, read-only: the deployed runtime's configuration (environment, authorizer,
memory) and the runtime role's Memory deny, plus the account's AgentCore Memory listing.

Usage: python -m scripts.record_runtime_identity
"""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import boto3

from infra.names import ROLE_NAMES
from scripts import gateway_client as gc
from scripts.redact import find_unredacted, known_values, redact


def main() -> int:
    session = boto3.Session(region_name="us-east-1")
    control, iam = session.client("bedrock-agentcore-control"), session.client("iam")
    runtime_ids = json.loads(Path(".local/runtime.json").read_text())
    rt = control.get_agent_runtime(agentRuntimeId=runtime_ids["id"])
    jwt = rt.get("authorizerConfiguration", {}).get("customJWTAuthorizer", {})
    role = ROLE_NAMES["runtime"]
    denies = []
    for name in iam.list_role_policies(RoleName=role)["PolicyNames"]:
        for st in iam.get_role_policy(RoleName=role, PolicyName=name)["PolicyDocument"]["Statement"]:
            actions = st["Action"] if isinstance(st["Action"], list) else [st["Action"]]
            if st.get("Effect") == "Deny" and any("Memory" in a or "Event" in a for a in actions):
                denies.append({"actions": actions, "resource": st.get("Resource")})
    memories = control.list_memories().get("memories", [])
    out = gc.outputs()
    record = {
        "date": date.today().isoformat(),
        "sha": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
        "runtime": {"status": rt.get("status"), "environment": rt.get("environmentVariables", {}),
                    "authorizer_allowed_clients": jwt.get("allowedClients"),
                    "network_mode": rt.get("networkConfiguration", {}).get("networkMode"),
                    "has_memory_configuration": any("memory" in k.lower() for k in rt)},
        "app_clients": {"agent": out.get("AgentClientId"), "clinician": out.get("ClinicianClientId"),
                        "intake": out.get("IntakeClientId")},
        "runtime_role_memory_denies": denies,
        "agentcore_memories_in_account": [m.get("id") or m.get("arn") for m in memories],
    }
    named = {**known_values(out), runtime_ids["arn"]: "<runtime-arn>", runtime_ids["id"]: "<runtime-id>"}
    if out.get("IntakeClientId"):
        named[out["IntakeClientId"]] = "<intake-client-id>"
    text = redact(json.dumps(record, indent=2, sort_keys=True, default=str), named)
    assert not find_unredacted(text)
    path = Path(f"evidence/{record['date']}/runtime-identity-and-memory.json")
    path.write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
