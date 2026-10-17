"""Record beat 5 on the deployed system: a clinician decides the routed case.

A fresh run of the counterfactual case is submitted, then, through the reviewer
gateway: a whitespace-only denial is refused by the Lambda; the agent's token is
refused at the authorizer; the clinician's denial is recorded; a second decision
on the same run is refused (write-once). The chain is verified from stored bytes,
and the bucket policy is simulated for each role writing decisions/.

The clinician here signs in by SRP (the scripted fallback); the workbench page
calls the same tool with a hosted-UI token.

Usage: python -m scripts.record_beat5
"""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import boto3

from infra.names import EVIDENCE_KEY_ALIAS, ROLE_NAMES
from prior_auth.agent.pipeline import session_id_for
from scripts import gateway_client as gc
from scripts import verify_chain
from scripts.intake import intake_token, invoke
from scripts.redact import find_unredacted, known_values, redact
from scripts.workbench import APPROVE_TOOL, DENY_TOOL, tool_result

CASE = "SYN-CASE-CF-1"
CLINICIAN = "syn-clinician-1"


def simulate_decision_writes(session: boto3.Session, account: str, bucket: str) -> dict:
    iam, s3 = session.client("iam"), session.client("s3")
    policy = s3.get_bucket_policy(Bucket=bucket)["Policy"]
    # The writes are SSE-KMS with the evidence key; the simulator needs that stated, since it
    # does not skip a StringNotEqualsIfExists condition whose key is absent.
    key_arn = session.client("kms").describe_key(KeyId=EVIDENCE_KEY_ALIAS)["KeyMetadata"]["Arn"]
    resource = f"arn:aws:s3:::{bucket}/decisions/{CASE}/simulated.json"
    results = {}
    for key in ("runtime", "agent_tools", "approval_service", "reviewer_tools"):
        arn = f"arn:aws:iam::{account}:role/{ROLE_NAMES[key]}"
        r = iam.simulate_principal_policy(
            PolicySourceArn=arn, ActionNames=["s3:PutObject"], ResourceArns=[resource], ResourcePolicy=policy,
            ContextEntries=[{"ContextKeyName": "aws:PrincipalArn", "ContextKeyValues": [arn],
                             "ContextKeyType": "string"},
                            {"ContextKeyName": "s3:x-amz-server-side-encryption-aws-kms-key-id",
                             "ContextKeyValues": [key_arn], "ContextKeyType": "string"},
                            {"ContextKeyName": "s3:if-none-match", "ContextKeyValues": ["*"],
                             "ContextKeyType": "string"}])["EvaluationResults"][0]
        results[ROLE_NAMES[key]] = r["EvalDecision"]
    return results


def main() -> int:
    session = boto3.Session(region_name="us-east-1")
    out = gc.outputs()
    account = session.client("sts").get_caller_identity()["Account"]
    bucket = f"prior-auth-evidence-{account}"
    runtime = json.loads(Path(".local/runtime.json").read_text())
    session_id = session_id_for(CASE)
    routed = invoke(CASE, runtime["arn"], intake_token(out, session), session_id)
    assert routed["outcome"] == "routed", routed
    run_id = routed["run_id"]
    R = out["ReviewerGatewayUrl"]
    clinician, agent = gc.user_token(out, session, CLINICIAN), gc.agent_token(out, session)
    reason = "Criterion C3 is not documented in the submitted chart; resubmit with the imaging report."
    call = lambda token, name, args: gc.mcp(R, token, "tools/call", {"name": name, "arguments": args})
    calls = {
        "whitespace_reason_refused_by_lambda": call(clinician, DENY_TOOL, {"case_id": CASE, "run_id": run_id,
                                                                           "reason": "   ", "reviewer": CLINICIAN}),
        "agent_token_refused_at_authorizer": call(agent, DENY_TOOL, {"case_id": CASE, "run_id": run_id,
                                                                     "reason": reason}),
        "decision_on_another_run_refused": call(clinician, DENY_TOOL, {"case_id": CASE, "run_id": "20200101T000000Z-stale",
                                                                       "reason": reason, "reviewer": CLINICIAN}),
        "clinician_denial_recorded": call(clinician, DENY_TOOL, {"case_id": CASE, "run_id": run_id, "reason": reason,
                                                                 "reviewer": CLINICIAN}),
        "second_decision_refused_write_once": call(clinician, APPROVE_TOOL, {"case_id": CASE, "run_id": run_id,
                                                                             "reviewer": CLINICIAN}),
    }
    record = {
        "date": date.today().isoformat(),
        "sha": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
        "case_id": CASE, "session_id": session_id, "routed": routed,
        "clinician_sign_in": "SRP (scripted fallback); the workbench uses the hosted UI with PKCE and state",
        "calls": {k: {"http_status": v["http_status"], "result": tool_result(v)} for k, v in calls.items()},
        "chain": verify_chain.verify(session, CASE, run_id),
        "bucket_policy_simulation_put_decisions": simulate_decision_writes(session, account, bucket),
    }
    c = record["calls"]
    record["expectations_met"] = {
        "whitespace_refused": c["whitespace_reason_refused_by_lambda"]["result"].get("recorded") is False,
        "agent_refused_at_authorizer": c["agent_token_refused_at_authorizer"]["http_status"] == 403,
        "other_run_refused": c["decision_on_another_run_refused"]["result"].get("recorded") is False,
        "clinician_recorded": c["clinician_denial_recorded"]["result"].get("recorded") is True,
        "write_once": c["second_decision_refused_write_once"]["result"].get("recorded") is False,
        # Spans and trace summaries arrive minutes later; those links are checked by scripts.verify_chain then.
        "records_chained": all(v for k, v in record["chain"]["checks"].items()
                               if not k.startswith("span_") and k != "decision_trace_carries_decision_hash"),
        "only_decision_writers_allowed": {k: v == "allowed" for k, v in
                                          record["bucket_policy_simulation_put_decisions"].items()} == {
            ROLE_NAMES["runtime"]: False, ROLE_NAMES["agent_tools"]: False,
            ROLE_NAMES["approval_service"]: True, ROLE_NAMES["reviewer_tools"]: True},
    }
    named = {**known_values(out), bucket: "<evidence-bucket>", runtime["arn"]: "<runtime-arn>", account: "<account>"}
    text = redact(json.dumps(record, indent=2, sort_keys=True, default=str), named)
    assert not find_unredacted(text)
    path = Path(f"evidence/{date.today().isoformat()}/beat5-clinician-decision.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n")
    print(json.dumps(record["expectations_met"], indent=2))
    print("->", path)
    return 0 if all(v for v in record["expectations_met"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
