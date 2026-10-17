"""Resource names. Every project resource name normalizes to a 'priorauth' prefix,
so teardown verification can find leftovers by name."""

import re

BUDGET_STACK = "PriorAuthBudgets"
TEARDOWN_STACKS = ("PriorAuthRuntime", "PriorAuthPolicy", "PriorAuthGateways", "PriorAuthEvidence")  # deletion order
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

# Evidence bucket and its writers (deterministic names, no cross-stack exports).
EVIDENCE_BUCKET_PREFIX = "prior-auth-evidence"
EVIDENCE_KEY_ALIAS = "alias/prior-auth-evidence"
ROLE_NAMES = {
    "runtime": "prior-auth-runtime-role",
    "agent_tools": "prior-auth-agent-tools-role",
    "approval_service": "prior-auth-approval-service-role",
    "reviewer_tools": "prior-auth-reviewer-tools-role",
    "teardown": "prior-auth-teardown",
}
# Who may write which prefix (the bucket policy denies everyone else).
PREFIX_WRITERS = {
    "packets/": ("runtime",),
    "recommendations/": ("runtime",),
    "queue/": ("agent_tools",),
    "decisions/": ("reviewer_tools", "approval_service"),
}
# Records are created once and never replaced (enforced by the bucket policy).
WRITE_ONCE_PREFIXES = ("recommendations/", "decisions/")
RUNTIME_NAME = "prior_auth_agent"
IDENTITY_PROVIDER_NAME = "prior-auth-agent-m2m"
EXTRACTION_MODEL_ID = "amazon.nova-pro-v1:0"
