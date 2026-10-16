"""Cedar policy text. Pure functions, so the exact text is testable.

The article's snippet is copied from the deployed forbid text (B5), never typed.
"""

from tools.schemas import APPROVAL_TARGET, CASE_TARGET, CASE_TOOLS, REVIEWER_TARGET

DELIMITER = "___"
ROLE_CLAIM = "pa_role"
CLINICIAN_ROLE = "clinician"
# Observed live: Cedar sees the cognito:groups array as one String tag, so the
# set test failed validation. A pre-token trigger restates membership as the
# scalar claim pa_role, compared exactly. Free-text Cedar is never accepted.
CLINICIAN_TESTS = {
    "pa_role": f'principal.hasTag("{ROLE_CLAIM}") && principal.getTag("{ROLE_CLAIM}") == "{CLINICIAN_ROLE}"',
}


def clinician_test(tag_shape: str) -> str:
    if tag_shape not in CLINICIAN_TESTS:
        raise ValueError(f"unknown tag shape {tag_shape!r}; record it from a real token first")
    return CLINICIAN_TESTS[tag_shape]
DENIAL_TOOL = "record_adverse_determination"


def action(target: str, tool: str) -> str:
    return f'AgentCore::Action::"{target}{DELIMITER}{tool}"'


def oauth_user(sub: str) -> str:
    return f'AgentCore::OAuthUser::"{sub}"'


def gateway(arn: str) -> str:
    return f'AgentCore::Gateway::"{arn}"'


def forbid_denial(agent_sub: str, reviewer_arn: str, clinician_test: str) -> str:
    """The one forbid on the denial tool: the agent, or anyone who is not a clinician.

    The validator rejected a separate, unconditional agent forbid as "Overly
    Restrictive" (it denies every request for that principal, which was its
    point). Merged, the forbid still names the agent explicitly, needs no
    validation bypass, and is what the article's snippet copies (B5).
    """
    # Scoped to OAuthUser: a CUSTOM_JWT gateway produces no other principal type,
    # and an unscoped forbid was flagged for IAM principals nothing permits.
    return (
        "forbid(\n"
        "  principal is AgentCore::OAuthUser,\n"
        f"  action == {action(REVIEWER_TARGET, DENIAL_TOOL)},\n"
        f"  resource == {gateway(reviewer_arn)}\n"
        f") when {{ principal == {oauth_user(agent_sub)} || !({clinician_test}) }};"
    )


def permit_clinician_denial(reviewer_arn: str, clinician_test: str) -> str:
    return (
        "permit(\n"
        "  principal is AgentCore::OAuthUser,\n"
        f"  action == {action(REVIEWER_TARGET, DENIAL_TOOL)},\n"
        f"  resource == {gateway(reviewer_arn)}\n"
        f") when {{ {clinician_test} }};"
    )


CASE_TOOL_NAMES = [t["name"] for t in CASE_TOOLS]


def permit_agent_case_tools(agent_sub: str, agent_arn: str) -> str:
    actions = ", ".join(action(CASE_TARGET, t) for t in CASE_TOOL_NAMES)
    return (
        "permit(\n"
        f"  principal == {oauth_user(agent_sub)},\n"
        f"  action in [{actions}],\n"
        f"  resource == {gateway(agent_arn)}\n"
        ");"
    )


def permit_agent_record_approval(agent_sub: str, agent_arn: str) -> str:
    return (
        "permit(\n"
        f"  principal == {oauth_user(agent_sub)},\n"
        f"  action == {action(APPROVAL_TARGET, 'record_approval')},\n"
        f"  resource == {gateway(agent_arn)}\n"
        ") when { context.input has packet_id && context.input has packet_hash };"
    )


def all_policies(*, agent_sub: str, agent_arn: str, reviewer_arn: str, tag_shape: str) -> dict[str, str]:
    """Policy name -> Cedar statement. Every permit constrains its principal."""
    if not agent_sub or any(c in agent_sub for c in '"\\;{}() \n'):
        raise ValueError("agent_sub must be a bare identifier recorded from a real token")
    clinician_test_expr = clinician_test(tag_shape)
    return {
        "prior_auth_permit_agent_case_tools": permit_agent_case_tools(agent_sub, agent_arn),
        "prior_auth_permit_agent_record_approval": permit_agent_record_approval(agent_sub, agent_arn),
        "prior_auth_permit_clinician_denial": permit_clinician_denial(reviewer_arn, clinician_test_expr),
        "prior_auth_forbid_denial": forbid_denial(agent_sub, reviewer_arn, clinician_test_expr),
    }
