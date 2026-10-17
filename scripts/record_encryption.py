"""Record L5 live, read-only: the evidence bucket's default encryption (SSE-KMS under the
customer-managed evidence key, bucket key setting) and head-object on the newest object of each
prefix, showing aws:kms under that same key. Key identifiers are masked.

Usage: python -m scripts.record_encryption
"""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import boto3

from infra.names import EVIDENCE_BUCKET_PREFIX, EVIDENCE_KEY_ALIAS, PREFIX_WRITERS
from scripts import gateway_client as gc
from scripts.redact import find_unredacted, known_values, redact


def main() -> int:
    session = boto3.Session(region_name="us-east-1")
    account = session.client("sts").get_caller_identity()["Account"]
    bucket = f"{EVIDENCE_BUCKET_PREFIX}-{account}"
    s3, kms = session.client("s3"), session.client("kms")
    key = kms.describe_key(KeyId=EVIDENCE_KEY_ALIAS)["KeyMetadata"]
    rule = s3.get_bucket_encryption(Bucket=bucket)["ServerSideEncryptionConfiguration"]["Rules"][0]
    default = rule["ApplyServerSideEncryptionByDefault"]
    objects = {}
    for prefix in PREFIX_WRITERS:
        listed = s3.list_objects_v2(Bucket=bucket, Prefix=prefix).get("Contents", [])
        if not listed:
            objects[prefix] = None
            continue
        newest = max(listed, key=lambda o: o["LastModified"])
        head = s3.head_object(Bucket=bucket, Key=newest["Key"])
        objects[prefix] = {"key": newest["Key"], "sse": head.get("ServerSideEncryption"),
                           "kms_key_is_the_evidence_key": head.get("SSEKMSKeyId") == key["Arn"],
                           "bucket_key_enabled": head.get("BucketKeyEnabled")}
    record = {
        "label": "L5: live, read-only", "date": date.today().isoformat(),
        "sha": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
        "evidence_key": {"alias": EVIDENCE_KEY_ALIAS, "key_manager": key["KeyManager"], "key_state": key["KeyState"],
                         "key_spec": key.get("KeySpec"), "arn": key["Arn"]},
        "bucket_default_encryption": {"sse_algorithm": default["SSEAlgorithm"],
                                      "kms_master_key_is_the_evidence_key": default.get("KMSMasterKeyID") in (
                                          key["Arn"], key["KeyId"]),
                                      "bucket_key_enabled": rule.get("BucketKeyEnabled")},
        "objects": objects,
    }
    record["passed"] = (key["KeyManager"] == "CUSTOMER" and key["KeyState"] == "Enabled"
                        and default["SSEAlgorithm"] == "aws:kms"
                        and record["bucket_default_encryption"]["kms_master_key_is_the_evidence_key"]
                        and all(o and o["sse"] == "aws:kms" and o["kms_key_is_the_evidence_key"] for o in objects.values()))
    named = {**known_values(gc.outputs()), bucket: "<evidence-bucket>", account: "<account>", key["Arn"]: "<kms-key-arn>",
             key["KeyId"]: "<kms-key-id>"}
    text = redact(json.dumps(record, indent=2, sort_keys=True, default=str), named)
    assert not find_unredacted(text)
    path = Path(f"evidence/{record['date']}/encryption-live.json")
    path.write_text(text + "\n")
    print(text)
    return 0 if record["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
