import re

import aws_cdk as cdk

from infra.budget_stack import PROJECT_TAG_KEY, PROJECT_TAG_VALUE, BudgetStack
from infra.gateway_stack import GatewayStack
from infra.policy_stack import PolicyStack

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
    # Deploy-time only (kept in the git-ignored cdk.context.json): the Cognito domain prefix.
    domain_prefix = app.node.try_get_context("cognito_domain_prefix") or "prior-auth-synth-only"
    gateways = GatewayStack(app, "PriorAuthGateways", env=env, domain_prefix=domain_prefix)
    # D2 needs the principal values recorded from real tokens after D1 (task 3.2).
    agent_sub = app.node.try_get_context("agent_sub")
    clinician_test = app.node.try_get_context("clinician_test")
    if agent_sub and clinician_test:
        PolicyStack(
            app, "PriorAuthPolicy", env=env,
            engine_id=gateways.engine.attr_policy_engine_id,
            agent_arn=gateways.agent_gateway.attr_gateway_arn,
            reviewer_arn=gateways.reviewer_gateway.attr_gateway_arn,
            agent_sub=agent_sub, clinician_test=clinician_test,
        )
    cdk.Tags.of(app).add(PROJECT_TAG_KEY, PROJECT_TAG_VALUE)
    app.synth()


if __name__ == "__main__":
    main()
