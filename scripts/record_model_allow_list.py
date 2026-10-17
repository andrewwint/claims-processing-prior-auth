"""Record the deployed model allow-list (M9): the runtime role's model grants, the
runtime's MODEL_ALLOW_LIST, and a live call naming a model off the list.

Usage: python -m scripts.record_model_allow_list <label>
"""

import fnmatch
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import boto3

from infra.names import ROLE_NAMES
from prior_auth.agent.pipeline import session_id_for
from scripts import gateway_client as gc
from scripts.intake import intake_token, invoke_payload
from scripts.redact import find_unredacted, known_values, redact

OFF_LIST = "us.anthropic.claude-sonnet-4-6"


def main() -> int:
    label = sys.argv[1] if len(sys.argv) > 1 else "deployed"
    session = boto3.Session(region_name="us-east-1")
    iam = session.client("iam")
    role = ROLE_NAMES["runtime"]
    documents = [("inline:" + n, iam.get_role_policy(RoleName=role, PolicyName=n)["PolicyDocument"])
                 for n in iam.list_role_policies(RoleName=role)["PolicyNames"]]
    attached = iam.list_attached_role_policies(RoleName=role)["AttachedPolicies"]
    for a in attached:
        version = iam.get_policy(PolicyArn=a["PolicyArn"])["Policy"]["DefaultVersionId"]
        documents.append(("managed:" + a["PolicyName"], iam.get_policy_version(
            PolicyArn=a["PolicyArn"], VersionId=version)["PolicyVersion"]["Document"]))
    grants = []
    for source, doc in documents:
        for st in doc["Statement"]:
            if st.get("Effect") != "Allow":
                continue
            actions = st.get("Action", [])
            actions = actions if isinstance(actions, list) else [actions]
            # Anything that could invoke a model: InvokeModel*, bedrock:Invoke*, bedrock:*, *.
            if any(fnmatch.fnmatch("bedrock:InvokeModel", a) or fnmatch.fnmatch("bedrock:InvokeModelWithResponseStream", a)
                   or a in ("*", "bedrock:*") for a in actions) or "NotAction" in st:
                grants.append({"source": source, "actions": actions,
                               "resources": st.get("Resource") if isinstance(st.get("Resource"), list) else [st.get("Resource")],
                               "condition": st.get("Condition")})
    runtime = json.loads(Path(".local/runtime.json").read_text())
    env = session.client("bedrock-agentcore-control").get_agent_runtime(
        agentRuntimeId=runtime["id"])["environmentVariables"]
    out = gc.outputs()
    probe = invoke_payload({"case_id": "SYN-CASE-CLEAN-1", "model_id": OFF_LIST}, runtime["arn"],
                           intake_token(out, session), session_id_for("allow-list-probe"))
    resources = [r for g in grants for r in g["resources"]]
    record = {"label": label, "date": date.today().isoformat(),
              "sha": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
              "policies_read": [s for s, _ in documents], "runtime_role_model_grants": grants, "model_allow_list_env": env.get("MODEL_ALLOW_LIST"),
              "probe_off_list_model": {"model_id": OFF_LIST, "response": probe}}
    record["nova_pro_only"] = (resources == ["arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-pro-v1:0"]
                               and record["model_allow_list_env"] == "amazon.nova-pro-v1:0"
                               and probe == {"outcome": "rejected", "reason": "model is not on the allow-list"})
    named = {**known_values(out), runtime["arn"]: "<runtime-arn>"}
    text = redact(json.dumps(record, indent=2, sort_keys=True, default=str), named)
    assert not find_unredacted(text)
    path = Path(f"evidence/{record['date']}/model-allow-list-{label}.json")
    path.write_text(text + "\n")
    print(text)
    return 0 if record["nova_pro_only"] else 1


if __name__ == "__main__":
    sys.exit(main())
