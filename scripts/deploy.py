"""Deploy one known stack, only if every guard passes.

Usage: python -m scripts.deploy <StackName> [-c key=value ...] [--outputs-file path]

Guards:
- the stack name is one of the project's stacks (no globs);
- the budget alerts exist;
- required context is present and non-empty (command-line -c/--context values
  override cdk.context.json; nothing else counts as context);
- once the gateway stack exists, its exact gateway IDs are required, and the
  synthesized template must not bind any gateway role to a wildcard;
- AWS errors refuse the deploy instead of skipping a guard;
- the working tree is clean, so every deploy maps to a commit; the deployed SHA
  is appended to evidence/deploys.jsonl.
"""

import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from infra.names import BUDGET_NAMES, BUDGET_STACK, CDK_CLI
from scripts.inventory import present_budgets

GATEWAY_STACK, POLICY_STACK = "PriorAuthGateways", "PriorAuthPolicy"
EVIDENCE_STACK, RUNTIME_STACK = "PriorAuthEvidence", "PriorAuthRuntime"
KNOWN_STACKS = (BUDGET_STACK, EVIDENCE_STACK, GATEWAY_STACK, POLICY_STACK, RUNTIME_STACK)
GATEWAY_ID_KEYS = ("agent_gateway_id", "reviewer_gateway_id")
REQUIRED_CONTEXT = {
    GATEWAY_STACK: ("cognito_domain_prefix",),
    # Policies deploy after D1 is recorded, so the exact gateway IDs are known and
    # required: a policy deploy must never revert the roles to the name-prefix wildcard.
    POLICY_STACK: ("cognito_domain_prefix", "agent_sub", "clinician_tag_shape", "policy_engine_id", *GATEWAY_ID_KEYS),
    RUNTIME_STACK: ("cognito_domain_prefix", "intake_client_id", "user_pool_id", "agent_gateway_url", *GATEWAY_ID_KEYS),
}


class BudgetsMissing(RuntimeError):
    pass


class Refused(RuntimeError):
    pass


def require_budgets(present: list[str]) -> None:
    missing = [b for b in BUDGET_NAMES if b not in present]
    if missing:
        raise BudgetsMissing(f"budget alerts missing: {', '.join(missing)}; deploy {BUDGET_STACK} first")


def cli_context(args: list[str]) -> dict[str, str]:
    """Only values given with -c/--context count; anything else (tags, parameters) never does."""
    out, i = {}, 0
    while i < len(args):
        a = args[i]
        pair = None
        if a in ("-c", "--context") and i + 1 < len(args):
            pair, i = args[i + 1], i + 1
        elif a.startswith("--context="):
            pair = a[len("--context="):]
        if pair is not None and "=" in pair:
            k, _, v = pair.partition("=")
            out[k] = v
        i += 1
    return out


def effective_context(args: list[str], saved: dict) -> dict:
    return {**{k: str(v) for k, v in saved.items()}, **cli_context(args)}


def missing_context(stack: str, args: list[str], saved: dict) -> list[str]:
    ctx = effective_context(args, saved)
    return [k for k in REQUIRED_CONTEXT.get(stack, ()) if not ctx.get(k)]


def refuses_gateway_revert(stack: str, args: list[str], saved: dict, stack_exists: bool) -> bool:
    """Once the gateway stack exists, redeploying it without the exact IDs would
    widen the gateway roles back to the name-prefix wildcard."""
    if stack != GATEWAY_STACK or not stack_exists:
        return False
    ctx = effective_context(args, saved)
    return not all(ctx.get(k) for k in GATEWAY_ID_KEYS)


def wildcard_trust(template: dict) -> list[str]:
    """Gateway roles whose trust is bound to a name-prefix wildcard."""
    hits = []
    for name, res in template.get("Resources", {}).items():
        if res.get("Type") != "AWS::IAM::Role":
            continue
        for st in res["Properties"].get("AssumeRolePolicyDocument", {}).get("Statement", []):
            arn = json.dumps(st.get("Condition", {}).get("ArnLike", {}).get("aws:SourceArn", ""))
            if ":gateway/" in arn and "-*" in arn:
                hits.append(name)
    return hits


DEPLOY_LOG = Path("evidence/deploys.jsonl")


def dirty_paths() -> list[str]:
    out = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True).stdout
    return [line[3:] for line in out.splitlines() if line.strip()]


def head_sha() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()


# Command-line context whose values are configuration, not identifiers, so the log can carry them.
LOGGED_CONTEXT_VALUES = ("model_opt_in", "b4_layer2_test")


def logged_context(extra: list[str]) -> dict:
    """Command-line context keys; values only for LOGGED_CONTEXT_VALUES (others are identifiers)."""
    return {k: (v if k in LOGGED_CONTEXT_VALUES else "<set>") for k, v in cli_context(extra).items()}


def record_deploy(stack: str, sha: str, returncode: int, log: Path = DEPLOY_LOG, extra: list[str] = ()) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    entry = {"stack": stack, "sha": sha, "result": "deployed" if returncode == 0 else f"failed ({returncode})",
             "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    context = logged_context(list(extra))
    if context:
        entry["context"] = context
    with log.open("a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def cdk_args(stack: str, extra: list[str]) -> list[str]:
    # Deploy only the named stack; never redeploy a dependency as a side effect.
    return ["deploy", stack, "--exclusively", "--require-approval", "never", *extra]


def _stack_exists(name: str) -> bool:
    cfn = boto3.Session(region_name="us-east-1").client("cloudformation")
    try:
        status = cfn.describe_stacks(StackName=name)["Stacks"][0]["StackStatus"]
    except ClientError as e:
        if "does not exist" in str(e):
            return False
        raise  # AccessDenied, throttling and the like refuse; they never switch a guard off
    return status != "DELETE_COMPLETE"


def _saved_context() -> dict:
    path = Path("cdk.context.json")
    return json.loads(path.read_text()) if path.exists() else {}


def _synth_template(stack: str, extra: list[str]) -> dict:
    ctx = [a for k, v in cli_context(extra).items() for a in ("-c", f"{k}={v}")]
    with tempfile.TemporaryDirectory() as out:
        subprocess.run(["npx", "-y", CDK_CLI, "synth", stack, "--exclusively", "-q", "-o", out, *ctx],
                       check=True, capture_output=True)
        return json.loads((Path(out) / f"{stack}.template.json").read_text())


def check(stack: str, extra: list[str], saved: dict, stack_exists: bool) -> None:
    if stack not in KNOWN_STACKS:
        raise Refused(f"unknown stack {stack!r}; expected one of {', '.join(KNOWN_STACKS)}")
    missing = missing_context(stack, extra, saved)
    if missing:
        raise Refused(f"missing context {', '.join(missing)}")
    if refuses_gateway_revert(stack, extra, saved, stack_exists):
        raise Refused("redeploying the gateway stack needs -c agent_gateway_id and -c reviewer_gateway_id")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    stack, extra = argv[0], argv[1:]
    saved = _saved_context()
    dirty = dirty_paths()
    if dirty:
        print(f"refusing to deploy {stack}: the working tree is not clean ({', '.join(dirty[:5])})", file=sys.stderr)
        return 2
    sha = head_sha()
    try:
        if stack != BUDGET_STACK:
            require_budgets(present_budgets(boto3.Session(region_name="us-east-1")))
        exists = _stack_exists(stack) if stack in KNOWN_STACKS else False
        check(stack, extra, saved, exists)
        if stack == GATEWAY_STACK and exists:
            wild = wildcard_trust(_synth_template(stack, extra))
            if wild:
                raise Refused(f"synthesized gateway roles still use a wildcard trust: {', '.join(wild)}")
    except (BudgetsMissing, Refused, ClientError, BotoCoreError, subprocess.CalledProcessError) as e:
        print(f"refusing to deploy {stack}: {e}", file=sys.stderr)
        return 1 if not isinstance(e, Refused) else 2
    rc = subprocess.run(["npx", "-y", CDK_CLI, *cdk_args(stack, extra)]).returncode
    record_deploy(stack, sha, rc, extra=extra)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
