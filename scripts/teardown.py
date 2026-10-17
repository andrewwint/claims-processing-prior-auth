"""Remove everything this project deployed except the budgets, then verify.

Order (each step stops the teardown if it fails):
1. cdk destroy the runtime, policy and gateway stacks.
2. Empty the evidence bucket as the teardown role (every version and delete
   marker, by version ID, with the governance bypass that only that role holds),
   then delete it. This runs before the evidence stack goes, because that stack
   owns the role.
3. cdk destroy the evidence stack (its KMS key is scheduled for deletion).
4. Delete the AgentCore Identity provider, the runtime's log group, the Lambda
   log groups and the project's secrets, all by exact name.
5. Restore the account's Transaction Search settings to the recorded values.

Nothing is deleted by search or pattern. Usage: python -m scripts.teardown --yes
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from infra.names import (AGENT_SECRET, CDK_CLI, EVIDENCE_BUCKET_PREFIX, IDENTITY_PROVIDER_NAME, LOG_GROUPS,
                         ROLE_NAMES, SECRET_PREFIX, TEARDOWN_STACKS)
from scripts.create_users import USERS

# Exact secret names this project creates; nothing is deleted by search.
SECRETS = (AGENT_SECRET, *(f"{SECRET_PREFIX}users/{u}" for u in USERS))
EVIDENCE_STACK = "PriorAuthEvidence"
RUNTIME_RECORD = Path(".local/runtime.json")
from scripts import inventory, transaction_search, verify_teardown  # noqa: E402


def destroy(stack: str) -> bool:
    return subprocess.run(["npx", "-y", CDK_CLI, "destroy", stack, "--force", "--exclusively"]).returncode == 0


def runtime_log_group() -> str | None:
    """The runtime's own log group, named from its recorded ID (AgentCore creates it)."""
    try:
        return f"/aws/bedrock-agentcore/runtimes/{json.loads(RUNTIME_RECORD.read_text())['id']}-DEFAULT"
    except (OSError, ValueError, KeyError):
        return None


def empty_evidence_bucket(session: boto3.Session, account_id: str) -> int:
    """Delete every version and delete marker as the teardown role; returns how many."""
    bucket = f"{EVIDENCE_BUCKET_PREFIX}-{account_id}"
    creds = session.client("sts").assume_role(
        RoleArn=f"arn:aws:iam::{account_id}:role/{ROLE_NAMES['teardown']}", RoleSessionName="teardown")["Credentials"]
    s3 = boto3.client("s3", region_name="us-east-1", aws_access_key_id=creds["AccessKeyId"],
                      aws_secret_access_key=creds["SecretAccessKey"], aws_session_token=creds["SessionToken"])
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchBucket"):
            return 0
        raise
    deleted = 0
    for page in s3.get_paginator("list_object_versions").paginate(Bucket=bucket):
        batch = [{"Key": v["Key"], "VersionId": v["VersionId"]}
                 for v in page.get("Versions", []) + page.get("DeleteMarkers", [])]
        if batch:
            result = s3.delete_objects(Bucket=bucket, Delete={"Objects": batch, "Quiet": True},
                                       BypassGovernanceRetention=True)
            if result.get("Errors"):
                raise RuntimeError(f"could not delete {len(result['Errors'])} evidence object versions")
            deleted += len(batch)
    s3.delete_bucket(Bucket=bucket)
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true", help="required: confirms the teardown was approved")
    if not parser.parse_args().yes:
        print("refusing to tear down without --yes", file=sys.stderr)
        return 2
    session = boto3.Session(region_name="us-east-1")
    account_id = session.client("sts").get_caller_identity()["Account"]
    log_groups = (*LOG_GROUPS, *filter(None, [runtime_log_group()]))
    for stack in (s for s in TEARDOWN_STACKS if s != EVIDENCE_STACK):
        if not destroy(stack):
            print(f"cdk destroy {stack} failed; stopping before any other deletion", file=sys.stderr)
            return 1
    try:
        print(f"evidence bucket: deleted {empty_evidence_bucket(session, account_id)} object versions")
    except (ClientError, RuntimeError) as e:
        print(f"emptying the evidence bucket failed; stopping: {e}", file=sys.stderr)
        return 1
    if not destroy(EVIDENCE_STACK):
        print(f"cdk destroy {EVIDENCE_STACK} failed; stopping", file=sys.stderr)
        return 1
    try:
        control = session.client("bedrock-agentcore-control")
        try:
            control.delete_oauth2_credential_provider(name=IDENTITY_PROVIDER_NAME)
        except control.exceptions.ResourceNotFoundException:
            pass
        logs = session.client("logs")
        # Only the exact log groups this project names; never by pattern.
        for name in log_groups:
            try:
                logs.delete_log_group(logGroupName=name)
            except logs.exceptions.ResourceNotFoundException:
                pass
        secrets = session.client("secretsmanager")
        for name in SECRETS:
            try:
                secrets.delete_secret(SecretId=name, ForceDeleteWithoutRecovery=True)
            except secrets.exceptions.ResourceNotFoundException:
                pass
        transaction_search.restore(session.client("xray"), account_id)
    except (ClientError, transaction_search.NoRecord) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return verify_teardown.main()


if __name__ == "__main__":
    sys.exit(main())
