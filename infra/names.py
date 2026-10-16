"""Resource names. Every project resource name normalizes to a 'priorauth' prefix,
so teardown verification can find leftovers by name."""

import re

BUDGET_STACK = "PriorAuthBudgets"
TEARDOWN_STACKS = ("PriorAuthPolicy", "PriorAuthGateways")  # deletion order
BUDGET_NAMES = ("prior-auth-agentcore-account", "prior-auth-agentcore-project")
SECRET_PREFIX = "prior-auth/"
CDK_CLI = "aws-cdk@2.1145.0"


def is_project_name(name: str) -> bool:
    return re.sub(r"[^a-z0-9]", "", name.lower()).startswith("priorauth")
