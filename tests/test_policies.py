import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Template

from infra.cedar import all_policies, forbid_agent_denial
from infra.gateway_stack import GatewayStack
from infra.policy_stack import PolicyStack
from scripts.redact import redact

ARTICLE_SNIPPET = """forbid(
  principal == AgentCore::OAuthUser::"<agent-client-id>",
  action == AgentCore::Action::"ReviewerTools___record_adverse_determination",
  resource == AgentCore::Gateway::"<reviewer-gateway-arn>"
);"""
TEST = 'principal.hasTag("cognito:groups") && principal.getTag("cognito:groups") like "*clinician*"'
P = all_policies(agent_sub="AGENT", agent_arn="AGENT_ARN", reviewer_arn="REVIEWER_ARN", clinician_test=TEST)


def test_agent_forbid_matches_the_article_snippet_after_redaction():
    sub = "4f1k2l3m4n5o6p7q8r9s0t1u2v"
    arn = "arn:aws:bedrock-agentcore:us-east-1:123456789012:gateway/prior-auth-reviewer-abc123"
    deployed = forbid_agent_denial(sub, arn)
    assert redact(deployed, {sub: "<agent-client-id>", arn: "<reviewer-gateway-arn>"}) == ARTICLE_SNIPPET


def test_five_policies_two_forbids_on_the_denial_tool():
    assert len(P) == 5
    forbids = [s for s in P.values() if s.startswith("forbid(")]
    assert len(forbids) == 2
    assert all("ReviewerTools___record_adverse_determination" in s for s in forbids)


def test_every_permit_constrains_its_principal():
    for name, s in P.items():
        if s.startswith("permit("):
            assert 'principal == AgentCore::OAuthUser::"AGENT"' in s or f"when {{ {TEST} }}" in s, name


def test_agent_permits_never_reach_the_reviewer_gateway():
    for name in ("prior_auth_permit_agent_case_tools", "prior_auth_permit_agent_record_approval"):
        assert "REVIEWER_ARN" not in P[name] and "AGENT_ARN" in P[name]


def test_record_approval_permit_requires_both_fields():
    s = P["prior_auth_permit_agent_record_approval"]
    assert "context.input has packet_id && context.input has packet_hash" in s


def test_case_tools_permit_excludes_record_approval_and_denial():
    s = P["prior_auth_permit_agent_case_tools"]
    assert "record_approval" not in s and "adverse" not in s
    assert s.count("AgentTools___") == 4


def test_policy_names_are_valid():
    import re
    assert all(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,47}", n) for n in P)


@pytest.fixture(scope="module")
def stacks():
    app = cdk.App()
    env = cdk.Environment(region="us-east-1")
    g = GatewayStack(app, "G", env=env, domain_prefix="prior-auth-test")
    p = PolicyStack(app, "P", env=env, engine_id=g.engine.attr_policy_engine_id,
                    agent_arn=g.agent_gateway.attr_gateway_arn, reviewer_arn=g.reviewer_gateway.attr_gateway_arn,
                    agent_sub="AGENT", clinician_test=TEST)
    return Template.from_stack(g), Template.from_stack(p)


def test_both_gateways_attach_the_engine_in_enforce_mode(stacks):
    g, _ = stacks
    gws = g.find_resources("AWS::BedrockAgentCore::Gateway").values()
    assert len(gws) == 2
    for gw in gws:
        assert gw["Properties"]["PolicyEngineConfiguration"]["Mode"] == "ENFORCE"
    g.resource_count_is("AWS::BedrockAgentCore::PolicyEngine", 1)


def test_policies_are_active_and_use_default_validation(stacks):
    _, p = stacks
    pols = p.find_resources("AWS::BedrockAgentCore::Policy").values()
    assert len(pols) == 5
    for pol in pols:
        assert pol["Properties"]["EnforcementMode"] == "ACTIVE"
        assert "ValidationMode" not in pol["Properties"]
