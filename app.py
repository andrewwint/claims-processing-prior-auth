import re

import aws_cdk as cdk

from infra.budget_stack import PROJECT_TAG_KEY, PROJECT_TAG_VALUE, BudgetStack
from infra.gateway_stack import GatewayStack

REGION = "us-east-1"


def _context(app: cdk.App, key: str) -> str:
    value = app.node.try_get_context(key)
    if not value:
        raise SystemExit(f"missing -c {key}=...")
    return str(value)


def main() -> None:
    app = cdk.App()
    env = cdk.Environment(region=REGION)
    # The budget stack needs deploy-time values; other stacks synthesize without them.
    if app.node.try_get_context("alert_email") is not None:
        alert_email = _context(app, "alert_email")
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", alert_email):
            raise SystemExit("alert_email is not an email address")
        baseline_usd = float(_context(app, "baseline_usd"))
        BudgetStack(app, "PriorAuthBudgets", env=env, alert_email=alert_email, baseline_usd=baseline_usd)
    GatewayStack(app, "PriorAuthGateways", env=env)
    cdk.Tags.of(app).add(PROJECT_TAG_KEY, PROJECT_TAG_VALUE)
    app.synth()


if __name__ == "__main__":
    main()
