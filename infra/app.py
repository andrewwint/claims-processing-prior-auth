import re
from pathlib import Path

import aws_cdk as cdk

from scripts.stage_bundle import stage

from infra.budget_stack import PROJECT_TAG_KEY, PROJECT_TAG_VALUE, BudgetStack
from infra.evidence_stack import EvidenceStack
from infra.gateway_stack import GatewayStack
from infra.policy_stack import PolicyStack
from infra.runtime_stack import RUNTIME_CODE, RuntimeStack

REGION = "us-east-1"


def _context(app: cdk.App, key: str) -> str:
    value = app.node.try_get_context(key)
    if not value:
        raise SystemExit(f"missing -c {key}=...")
    return str(value)


def main() -> None:
    stage()  # the deployed bundle is always rebuilt from the code and committed data
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
    domain_prefix = app.node.try_get_context("cognito_domain_prefix")
    if not domain_prefix:
        raise SystemExit("missing -c cognito_domain_prefix=<private value>; it is never committed")
    gateway_ids = {k: v for k, v in {
        "prior-auth-agent": app.node.try_get_context("agent_gateway_id"),
        "prior-auth-reviewer": app.node.try_get_context("reviewer_gateway_id"),
    }.items() if v}
    b4_test = str(app.node.try_get_context("b4_layer2_test")).lower() == "true"
    gateways = GatewayStack(app, "PriorAuthGateways", env=env, domain_prefix=domain_prefix, gateway_ids=gateway_ids,
                            b4_layer2_test=b4_test)
    EvidenceStack(app, "PriorAuthEvidence", env=env)
    # Beat 2: the runtime takes D1's recorded values explicitly, like the policy stack.
    intake_client_id = app.node.try_get_context("intake_client_id")
    user_pool_id = app.node.try_get_context("user_pool_id")
    agent_gateway_url = app.node.try_get_context("agent_gateway_url")
    if intake_client_id and user_pool_id and agent_gateway_url and Path(RUNTIME_CODE).is_dir():
        RuntimeStack(app, "PriorAuthRuntime", env=env, user_pool_id=user_pool_id,
                     intake_client_id=intake_client_id, agent_gateway_url=agent_gateway_url)
    # D2 takes D1's recorded values explicitly (no cross-stack exports, which would
    # also lock the gateway stack against updates): the engine ID, the exact gateway
    # IDs, and the principal values recorded from real tokens (task 3.2).
    agent_sub = app.node.try_get_context("agent_sub")
    tag_shape = app.node.try_get_context("clinician_tag_shape")
    engine_id = app.node.try_get_context("policy_engine_id")
    if agent_sub and tag_shape and engine_id and len(gateway_ids) == 2:
        PolicyStack(
            app, "PriorAuthPolicy", env=env, engine_id=engine_id,
            agent_gateway_id=gateway_ids["prior-auth-agent"],
            reviewer_gateway_id=gateway_ids["prior-auth-reviewer"],
            agent_sub=agent_sub, tag_shape=tag_shape,
        )
    cdk.Tags.of(app).add(PROJECT_TAG_KEY, PROJECT_TAG_VALUE)
    app.synth()


if __name__ == "__main__":
    main()
