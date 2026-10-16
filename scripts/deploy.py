"""Deploy one stack, but only if the budget alerts exist.

Usage: python -m scripts.deploy <StackName> [cdk context args...]
"""

import json
import subprocess
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from infra.names import BUDGET_NAMES, BUDGET_STACK, CDK_CLI
from scripts.inventory import present_budgets


class BudgetsMissing(RuntimeError):
    pass


REQUIRED_CONTEXT = {
    "PriorAuthGateways": ("cognito_domain_prefix",),
    "PriorAuthPolicy": ("cognito_domain_prefix", "agent_sub", "clinician_test"),
}


def missing_context(stack: str, args: list[str], saved: dict) -> list[str]:
    given = {a.split("=", 1)[0] for a in args if "=" in a} | set(saved)
    return [k for k in REQUIRED_CONTEXT.get(stack, ()) if k not in given]


def _saved_context() -> dict:
    path = Path("cdk.context.json")
    return json.loads(path.read_text()) if path.exists() else {}


def require_budgets(present: list[str]) -> None:
    missing = [b for b in BUDGET_NAMES if b not in present]
    if missing:
        raise BudgetsMissing(f"budget alerts missing: {', '.join(missing)}; deploy {BUDGET_STACK} first")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    stack, extra = argv[0], argv[1:]
    missing = missing_context(stack, [a for a in extra if not a.startswith("-")], _saved_context())
    if missing:
        print(f"refusing to deploy {stack}: missing context {', '.join(missing)}", file=sys.stderr)
        return 2
    if stack != BUDGET_STACK:
        try:
            require_budgets(present_budgets(boto3.Session(region_name="us-east-1")))
        except (BudgetsMissing, ClientError) as e:
            print(f"refusing to deploy {stack}: {e}", file=sys.stderr)
            return 1
    return subprocess.run(["npx", "-y", CDK_CLI, "deploy", stack, "--require-approval", "never", *extra]).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
