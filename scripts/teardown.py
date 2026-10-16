"""Remove everything this project deployed except the budgets, then verify.

Usage: python -m scripts.teardown --yes
"""

import argparse
import subprocess
import sys

import boto3
from botocore.exceptions import ClientError

from infra.names import CDK_CLI, LOG_GROUPS, TEARDOWN_STACKS
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
        found = inventory.inventory(session)
        logs = session.client("logs")
        # Only the exact log groups this project names; never by pattern.
        for name in LOG_GROUPS:
            try:
                logs.delete_log_group(logGroupName=name)
            except logs.exceptions.ResourceNotFoundException:
                pass
        secrets = session.client("secretsmanager")
        for name in found["secret"]:  # prefix AND project tag
            secrets.delete_secret(SecretId=name, ForceDeleteWithoutRecovery=True)
        transaction_search.restore(session.client("xray"))
    except ClientError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return verify_teardown.main()


if __name__ == "__main__":
    sys.exit(main())
