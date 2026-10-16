"""Resource names. Every project resource name normalizes to a 'priorauth' prefix,
so teardown verification can find leftovers by name."""

import re

BUDGET_STACK = "PriorAuthBudgets"
TEARDOWN_STACKS = ("PriorAuthPolicy", "PriorAuthGateways")  # deletion order
BUDGET_NAMES = ("prior-auth-agentcore-account", "prior-auth-agentcore-project")
SECRET_PREFIX = "prior-auth/"
PROJECT_TAG = ("project", "prior-auth-agentcore")
# Every name this project creates. Teardown deletes only these, never by pattern.
LAMBDA_FUNCTIONS = ("prior-auth-agent-tools", "prior-auth-approval-service", "prior-auth-reviewer-tools",
                    "prior-auth-pre-token")
LOG_GROUPS = tuple(f"/aws/lambda/{f}" for f in LAMBDA_FUNCTIONS)
USER_POOLS = ("prior-auth-users",)
GATEWAYS = ("prior-auth-agent", "prior-auth-reviewer")
AGENT_SECRET = "prior-auth/agent-client"
CDK_CLI = "aws-cdk@2.1145.0"


def is_project_name(name: str) -> bool:
    return re.sub(r"[^a-z0-9]", "", name.lower()).startswith("priorauth")
