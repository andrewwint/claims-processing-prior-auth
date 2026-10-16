"""Remove everything this project deployed except the budgets, then verify.

Usage: python -m scripts.teardown --yes
"""

import argparse
import subprocess
import sys

import boto3
from botocore.exceptions import ClientError

from infra.names import CDK_CLI, TEARDOWN_STACKS
from scripts import inventory, transaction_search, verify_teardown


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true", help="required: confirms the teardown was approved")
    if not parser.parse_args().yes:
        print("refusing to tear down without --yes", file=sys.stderr)
        return 2
    session = boto3.Session(region_name="us-east-1")
    for stack in TEARDOWN_STACKS:
        subprocess.run(["npx", "-y", CDK_CLI, "destroy", stack, "--force"], check=False)
    try:
        found = inventory.inventory(session)
        logs = session.client("logs")
        for name in found["lambda log group"]:
            logs.delete_log_group(logGroupName=f"/aws/lambda/{name}")
        secrets = session.client("secretsmanager")
        for name in found["secret"]:
            secrets.delete_secret(SecretId=name, ForceDeleteWithoutRecovery=True)
        transaction_search.restore(session.client("xray"))
    except ClientError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return verify_teardown.main()


if __name__ == "__main__":
    sys.exit(main())
