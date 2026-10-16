"""Remove everything this project deployed except the budgets, then verify.

Usage: python -m scripts.teardown --yes
"""

import argparse
import subprocess
import sys

import boto3
from botocore.exceptions import ClientError

from infra.names import AGENT_SECRET, CDK_CLI, LOG_GROUPS, SECRET_PREFIX, TEARDOWN_STACKS
from scripts.create_users import USERS

# Exact secret names this project creates; nothing is deleted by search.
SECRETS = (AGENT_SECRET, *(f"{SECRET_PREFIX}users/{u}" for u in USERS))
from scripts import inventory, transaction_search, verify_teardown


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true", help="required: confirms the teardown was approved")
    if not parser.parse_args().yes:
        print("refusing to tear down without --yes", file=sys.stderr)
        return 2
    session = boto3.Session(region_name="us-east-1")
    for stack in TEARDOWN_STACKS:
        if subprocess.run(["npx", "-y", CDK_CLI, "destroy", stack, "--force"]).returncode != 0:
            print(f"cdk destroy {stack} failed; stopping before any other deletion", file=sys.stderr)
            return 1
    try:
        logs = session.client("logs")
        # Only the exact log groups this project names; never by pattern.
        for name in LOG_GROUPS:
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
        account_id = session.client("sts").get_caller_identity()["Account"]
        transaction_search.restore(session.client("xray"), account_id)
    except (ClientError, transaction_search.NoRecord) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return verify_teardown.main()


if __name__ == "__main__":
    sys.exit(main())
