"""Deploy one stack, but only if the budget alerts exist.

Usage: python -m scripts.deploy <StackName> [cdk context args...]
"""

import subprocess
import sys

import boto3
from botocore.exceptions import ClientError

from infra.names import BUDGET_NAMES, BUDGET_STACK, CDK_CLI
from scripts.inventory import present_budgets


class BudgetsMissing(RuntimeError):
    pass


def require_budgets(present: list[str]) -> None:
    missing = [b for b in BUDGET_NAMES if b not in present]
    if missing:
        raise BudgetsMissing(f"budget alerts missing: {', '.join(missing)}; deploy {BUDGET_STACK} first")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    stack, extra = argv[0], argv[1:]
    if stack != BUDGET_STACK:
        try:
            require_budgets(present_budgets(boto3.Session(region_name="us-east-1")))
        except (BudgetsMissing, ClientError) as e:
            print(f"refusing to deploy {stack}: {e}", file=sys.stderr)
            return 1
    return subprocess.run(["npx", "-y", CDK_CLI, "deploy", stack, "--require-approval", "never", *extra]).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
