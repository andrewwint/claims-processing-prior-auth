"""Record "Object Lock: live" (L4): deleting a locked object version is refused.

Two live attempts on one locked version, neither sending the governance-bypass header:
1. the operator (account administrator), whom the bucket policy also denies
   s3:DeleteObjectVersion and s3:BypassGovernanceRetention;
2. the teardown role, which the bucket policy allows to delete versions, so the
   refusal can only come from the Object Lock retention itself.
The target is a stray queue entry (a run under a mistyped case ID), so nothing a
claim relies on is at risk if a refusal fails. Retention is checked first; the
script refuses to run on a version whose retention has passed.

Usage: python -m scripts.record_object_lock_live <key>
"""

import json
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from infra.names import EVIDENCE_BUCKET_PREFIX, ROLE_NAMES
from scripts import gateway_client as gc
from scripts.redact import find_unredacted, known_values, redact


def attempt(s3, bucket: str, key: str, version: str) -> dict:
    try:
        s3.delete_object(Bucket=bucket, Key=key, VersionId=version)
        return {"refused": False}
    except ClientError as e:
        # The caller's principal ARN names the operator's SSO role; it is not evidence.
        message = re.sub(r"User: \S+ is", "User: <operator> is", e.response["Error"]["Message"])
        return {"refused": True, "code": e.response["Error"]["Code"], "message": message}


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    key = sys.argv[1]
    session = boto3.Session(region_name="us-east-1")
    account = session.client("sts").get_caller_identity()["Account"]
    bucket = f"{EVIDENCE_BUCKET_PREFIX}-{account}"
    s3 = session.client("s3")
    version = s3.list_object_versions(Bucket=bucket, Prefix=key)["Versions"][0]["VersionId"]
    head = s3.head_object(Bucket=bucket, Key=key, VersionId=version)
    if head.get("ObjectLockMode") != "GOVERNANCE" or head["ObjectLockRetainUntilDate"] <= datetime.now(timezone.utc):
        print("refusing: the version is not under governance retention", file=sys.stderr)
        return 1
    creds = session.client("sts").assume_role(
        RoleArn=f"arn:aws:iam::{account}:role/{ROLE_NAMES['teardown']}", RoleSessionName="object-lock-live")["Credentials"]
    teardown_s3 = boto3.client("s3", region_name="us-east-1", aws_access_key_id=creds["AccessKeyId"],
                               aws_secret_access_key=creds["SecretAccessKey"], aws_session_token=creds["SessionToken"])
    attempts = {"operator_without_bypass": attempt(s3, bucket, key, version),
                "teardown_role_without_bypass_header": attempt(teardown_s3, bucket, key, version)}
    still_there = s3.head_object(Bucket=bucket, Key=key, VersionId=version)["ObjectLockMode"] == "GOVERNANCE"
    record = {"label": "Object Lock: live", "date": date.today().isoformat(),
              "sha": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
              "key": key, "version_id": version, "object_lock_mode": head["ObjectLockMode"],
              "retain_until": head["ObjectLockRetainUntilDate"], "attempts": attempts,
              "version_still_present": still_there,
              "passed": all(a["refused"] for a in attempts.values()) and still_there}
    named = {**known_values(gc.outputs()), bucket: "<evidence-bucket>", account: "<account>"}
    text = redact(json.dumps(record, indent=2, sort_keys=True, default=str), named)
    assert not find_unredacted(text)
    path = Path(f"evidence/{record['date']}/object-lock-live.json")
    path.write_text(text + "\n")
    print(text)
    return 0 if record["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
