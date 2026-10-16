"""Deploy one stack, but only if the budget alerts exist.

Usage: python -m scripts.deploy <StackName> [cdk context args...]
"""

import json
import subprocess
import sys
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from infra.names import BUDGET_NAMES, BUDGET_STACK, CDK_CLI
from scripts.inventory import present_budgets


class BudgetsMissing(RuntimeError):
    pass


REQUIRED_CONTEXT = {
    "PriorAuthGateways": ("cognito_domain_prefix",),
    # Policies deploy after D1 is recorded, so the exact gateway IDs are known and
    # required: a policy deploy must never revert the roles to the name-prefix wildcard.
    "PriorAuthPolicy": ("cognito_domain_prefix", "agent_sub", "clinician_tag_shape",
                        "agent_gateway_id", "reviewer_gateway_id"),
}


def missing_context(stack: str, args: list[str], saved: dict) -> list[str]:
    given = {k for k, _, v in (a.partition("=") for a in args) if v} | {k for k, v in saved.items() if v}
    return [k for k in REQUIRED_CONTEXT.get(stack, ()) if k not in given]


GATEWAY_ID_KEYS = ("agent_gateway_id", "reviewer_gateway_id")


def cdk_args(stack: str, extra: list[str]) -> list[str]:
    # Deploy only the named stack; never redeploy a dependency as a side effect.
    return ["deploy", stack, "--exclusively", "--require-approval", "never", *extra]


def refuses_gateway_revert(stack: str, args: list[str], saved: dict, stack_exists: bool) -> bool:
    """Once the gateway stack exists, redeploying it without the exact IDs would
    widen the gateway roles back to the name-prefix wildcard."""
    if stack != "PriorAuthGateways" or not stack_exists:
        return False
    given = {k for k, _, v in (a.partition("=") for a in args) if v} | {k for k, v in saved.items() if v}
    return not set(GATEWAY_ID_KEYS) <= given


def _stack_exists(name: str) -> bool:
    cfn = boto3.Session(region_name="us-east-1").client("cloudformation")
    try:
        status = cfn.describe_stacks(StackName=name)["Stacks"][0]["StackStatus"]
    except ClientError:
        return False
    return status != "DELETE_COMPLETE"


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
    args, saved = [a for a in extra if not a.startswith("-")], _saved_context()
    missing = missing_context(stack, args, saved)
    if missing:
        print(f"refusing to deploy {stack}: missing context {', '.join(missing)}", file=sys.stderr)
        return 2
    try:
        exists = _stack_exists(stack)
    except BotoCoreError as e:
        print(f"refusing to deploy {stack}: cannot reach AWS ({e})", file=sys.stderr)
        return 1
    if refuses_gateway_revert(stack, args, saved, exists):
        print(f"refusing to redeploy {stack} without -c agent_gateway_id and -c reviewer_gateway_id", file=sys.stderr)
        return 2
    if stack != BUDGET_STACK:
        try:
            require_budgets(present_budgets(boto3.Session(region_name="us-east-1")))
        except (BudgetsMissing, ClientError, BotoCoreError) as e:
            print(f"refusing to deploy {stack}: {e}", file=sys.stderr)
            return 1
    return subprocess.run(["npx", "-y", CDK_CLI, *cdk_args(stack, extra)]).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
