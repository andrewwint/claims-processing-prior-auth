"""Record the evidence bucket's controls (L4, L5, L8) on the deployed system.

Facts from real records (head-object: SSE-KMS key, Object Lock mode and
retain-until date), plus refusals evaluated by the IAM policy simulator
against each role's deployed policies and the deployed bucket policy. The tool
and runtime roles trust only their service principals, so they cannot be
assumed for a live call; these are simulations, labeled as such.

Usage: python -m scripts.record_storage_controls <case_id> <run_id>
"""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import boto3

from infra.names import EVIDENCE_BUCKET_PREFIX, EVIDENCE_KEY_ALIAS, ROLE_NAMES
from prior_auth import evidence_store
from scripts import gateway_client as gc
from scripts.redact import find_unredacted, known_values, redact

# (role, action, prefix, key, expected[, headers]). key "evidence" is the evidence key, "other" is aws/s3.
# PutObject is simulated as a conditional create (If-None-Match: *) unless headers say otherwise.
EXPECTED = [
    # L8: only the two decision writers may write decisions/.
    ("runtime", "s3:PutObject", "decisions/", "evidence", "explicitDeny"),
    ("agent_tools", "s3:PutObject", "decisions/", "evidence", "explicitDeny"),
    ("approval_service", "s3:PutObject", "decisions/", "evidence", "allowed"),
    ("reviewer_tools", "s3:PutObject", "decisions/", "evidence", "allowed"),
    # L4: the agent's roles cannot delete, shorten retention, or bypass governance.
    ("runtime", "s3:DeleteObject", "recommendations/", "evidence", "explicitDeny"),
    # No one, not even teardown, may hide a record behind a delete marker.
    ("teardown", "s3:DeleteObject", "decisions/", "evidence", "implicitDeny"),
    ("reviewer_tools", "s3:DeleteObject", "decisions/", "evidence", "explicitDeny"),
    ("runtime", "s3:DeleteObjectVersion", "recommendations/", "evidence", "explicitDeny"),
    ("runtime", "s3:BypassGovernanceRetention", "recommendations/", "evidence", "explicitDeny"),
    ("runtime", "s3:PutObjectRetention", "recommendations/", "evidence", "explicitDeny"),
    ("agent_tools", "s3:BypassGovernanceRetention", "queue/", "evidence", "explicitDeny"),
    ("reviewer_tools", "s3:BypassGovernanceRetention", "decisions/", "evidence", "explicitDeny"),
    ("teardown", "s3:BypassGovernanceRetention", "decisions/", "evidence", "allowed"),
    # L5: a write under any other key is refused, even by a permitted writer.
    ("reviewer_tools", "s3:PutObject", "decisions/", "other", "explicitDeny"),
    ("runtime", "s3:PutObject", "recommendations/", "other", "explicitDeny"),
    # L4: write-once is enforced by the bucket: a permitted writer may not replace a record.
    ("runtime", "s3:PutObject", "recommendations/", "evidence", "allowed", {"if-none-match": "*"}),
    ("runtime", "s3:PutObject", "recommendations/", "evidence", "explicitDeny", {}),
    ("reviewer_tools", "s3:PutObject", "decisions/", "evidence", "explicitDeny", {}),
    ("approval_service", "s3:PutObject", "decisions/", "evidence", "explicitDeny", {}),
    ("reviewer_tools", "s3:PutObject", "decisions/", "evidence", "explicitDeny",
     {"if-none-match": "*", "if-match": "\"etag\""}),
    # Packets and queue entries are not records: overwriting them is allowed (and refused nowhere).
    ("runtime", "s3:PutObject", "packets/", "evidence", "allowed", {}),
]


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    case_id, run_id = sys.argv[1:]
    session = boto3.Session(region_name="us-east-1")
    account = session.client("sts").get_caller_identity()["Account"]
    bucket = f"{EVIDENCE_BUCKET_PREFIX}-{account}"
    s3, iam, kms = session.client("s3"), session.client("iam"), session.client("kms")
    keys = {"evidence": kms.describe_key(KeyId=EVIDENCE_KEY_ALIAS)["KeyMetadata"]["Arn"],
            "other": kms.describe_key(KeyId="alias/aws/s3")["KeyMetadata"]["Arn"]}
    policy = s3.get_bucket_policy(Bucket=bucket)["Policy"]
    lock = s3.get_object_lock_configuration(Bucket=bucket)["ObjectLockConfiguration"]
    stored = {}
    for name, key in (("recommendation", evidence_store.recommendation_key(case_id, run_id)),
                      ("decision", evidence_store.decision_key(case_id, run_id))):
        head = s3.head_object(Bucket=bucket, Key=key)
        stored[name] = {"key": key, "sse": head.get("ServerSideEncryption"),
                        "kms_key_is_evidence_key": head.get("SSEKMSKeyId") == keys["evidence"],
                        "object_lock_mode": head.get("ObjectLockMode"),
                        "retain_until": head.get("ObjectLockRetainUntilDate")}
    simulated = []
    for role, action, prefix, key, expected, *rest in EXPECTED:
        headers = rest[0] if rest else {"if-none-match": "*"}
        arn = f"arn:aws:iam::{account}:role/{ROLE_NAMES[role]}"
        context = [{"ContextKeyName": "aws:PrincipalArn", "ContextKeyValues": [arn], "ContextKeyType": "string"}]
        if action == "s3:PutObject":
            context.append({"ContextKeyName": "s3:x-amz-server-side-encryption-aws-kms-key-id",
                            "ContextKeyValues": [keys[key]], "ContextKeyType": "string"})
            context += [{"ContextKeyName": f"s3:{h}", "ContextKeyValues": [v], "ContextKeyType": "string"}
                        for h, v in headers.items()]
        got = iam.simulate_principal_policy(
            PolicySourceArn=arn, ActionNames=[action], ResourcePolicy=policy, ContextEntries=context,
            ResourceArns=[f"arn:aws:s3:::{bucket}/{prefix}{case_id}/simulated.json"])["EvaluationResults"][0]
        simulated.append({"role": ROLE_NAMES[role], "action": action, "prefix": prefix, "kms_key": key,
                          "headers": headers if action == "s3:PutObject" else None,
                          "expected": expected, "decision": got["EvalDecision"], "ok": got["EvalDecision"] == expected})
    record = {
        "date": date.today().isoformat(),
        "sha": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
        "method": "head-object on real records; refusals by iam:SimulatePrincipalPolicy with the deployed bucket policy",
        "object_lock_default": lock.get("Rule", {}).get("DefaultRetention"),
        "stored_records": stored, "simulated": simulated,
        "passed": all(s["ok"] for s in simulated) and all(
            r["sse"] == "aws:kms" and r["kms_key_is_evidence_key"] and r["object_lock_mode"] == "GOVERNANCE"
            for r in stored.values()),
    }
    named = {**known_values(gc.outputs()), bucket: "<evidence-bucket>", account: "<account>"}
    for k in keys.values():
        named[k] = "<kms-key-arn>"
    text = redact(json.dumps(record, indent=2, sort_keys=True, default=str), named)
    assert not find_unredacted(text)
    path = Path(f"evidence/{record['date']}/storage-controls.json")
    path.write_text(text + "\n")
    print(json.dumps({"passed": record["passed"], "failed": [s for s in simulated if not s["ok"]]}, indent=2))
    print("->", path)
    return 0 if record["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
