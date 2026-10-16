"""Cedar policy text. Pure functions, so the exact text is testable.

The agent-principal forbid is formatted exactly like the article's snippet:
B5 compares the redacted deployed text with it character for character.
"""

from tools.schemas import AGENT_TARGET, AGENT_TOOLS, REVIEWER_TARGET

DELIMITER = "___"
DENIAL_TOOL = "record_adverse_determination"


def action(target: str, tool: str) -> str:
    return f'AgentCore::Action::"{target}{DELIMITER}{tool}"'


def oauth_user(sub: str) -> str:
    return f'AgentCore::OAuthUser::"{sub}"'


def gateway(arn: str) -> str:
    return f'AgentCore::Gateway::"{arn}"'


def forbid_agent_denial(agent_sub: str, reviewer_arn: str) -> str:
    """The article's snippet."""
    return (
        "forbid(\n"
        f"  principal == {oauth_user(agent_sub)},\n"
        f"  action == {action(REVIEWER_TARGET, DENIAL_TOOL)},\n"
        f"  resource == {gateway(reviewer_arn)}\n"
        ");"
    )


def forbid_non_clinician_denial(reviewer_arn: str, clinician_test: str) -> str:
    return (
        "forbid(\n"
        "  principal,\n"
        f"  action == {action(REVIEWER_TARGET, DENIAL_TOOL)},\n"
        f"  resource == {gateway(reviewer_arn)}\n"
        f") unless {{ {clinician_test} }};"
    )


def permit_clinician_denial(reviewer_arn: str, clinician_test: str) -> str:
    return (
        "permit(\n"
        "  principal,\n"
        f"  action == {action(REVIEWER_TARGET, DENIAL_TOOL)},\n"
        f"  resource == {gateway(reviewer_arn)}\n"
        f") when {{ {clinician_test} }};"
    )


CASE_TOOLS = [t["name"] for t in AGENT_TOOLS if t["name"] != "record_approval"]


def permit_agent_case_tools(agent_sub: str, agent_arn: str) -> str:
    actions = ", ".join(action(AGENT_TARGET, t) for t in CASE_TOOLS)
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
        f"  action == {action(AGENT_TARGET, 'record_approval')},\n"
        f"  resource == {gateway(agent_arn)}\n"
        ") when { context.input has packet_id && context.input has packet_hash };"
    )


def all_policies(*, agent_sub: str, agent_arn: str, reviewer_arn: str, clinician_test: str) -> dict[str, str]:
    """Policy name -> Cedar statement. Every permit constrains its principal."""
    return {
        "prior_auth_permit_agent_case_tools": permit_agent_case_tools(agent_sub, agent_arn),
        "prior_auth_permit_agent_record_approval": permit_agent_record_approval(agent_sub, agent_arn),
        "prior_auth_permit_clinician_denial": permit_clinician_denial(reviewer_arn, clinician_test),
        "prior_auth_forbid_non_clinician_denial": forbid_non_clinician_denial(reviewer_arn, clinician_test),
        "prior_auth_forbid_agent_denial": forbid_agent_denial(agent_sub, reviewer_arn),
    }
