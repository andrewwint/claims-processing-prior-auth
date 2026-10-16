import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Template

from infra.cedar import CLINICIAN_TESTS, all_policies, clinician_test, forbid_agent_denial
from infra.gateway_stack import GatewayStack
from infra.policy_stack import PolicyStack
from scripts.redact import redact

ARTICLE_SNIPPET = """forbid(
  principal == AgentCore::OAuthUser::"<agent-client-id>",
  action == AgentCore::Action::"ReviewerTools___record_adverse_determination",
  resource == AgentCore::Gateway::"<reviewer-gateway-arn>"
);"""
TEST = CLINICIAN_TESTS["pa_role"]
P = all_policies(agent_sub="AGENT", agent_arn="AGENT_ARN", reviewer_arn="REVIEWER_ARN", tag_shape="pa_role")


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
            assert ('principal == AgentCore::OAuthUser::"AGENT"' in s
                    or ("principal is AgentCore::OAuthUser" in s and f"when {{ {TEST} }}" in s)), name


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
    p = PolicyStack(app, "P", env=env, engine_id="prior_auth_engine-abc",
                    agent_gateway_id="prior-auth-agent-abc", reviewer_gateway_id="prior-auth-reviewer-def",
                    agent_sub="AGENT", tag_shape="pa_role")
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



# X3 (second security review)
def test_clinician_test_is_built_from_a_recorded_shape_never_free_text():
    with pytest.raises(ValueError):
        clinician_test('principal.hasTag("cognito:groups")')
    with pytest.raises(ValueError):
        clinician_test("set")
    for expr in CLINICIAN_TESTS.values():
        assert '"clinician"' in expr and "like" not in expr and ";" not in expr and ".contains(" not in expr


@pytest.mark.parametrize("sub", ['x" };permit(principal,action,resource);//', "", "a b", "a;b", "a}b"])
def test_agent_sub_cannot_inject_cedar(sub):
    with pytest.raises(ValueError):
        all_policies(agent_sub=sub, agent_arn="A", reviewer_arn="R", tag_shape="pa_role")


def test_each_policy_is_a_single_statement():
    for s in P.values():
        assert s.count(";") == 1 and s.rstrip().endswith(";")


def test_record_approval_permit_names_the_approval_service_action():
    s = P["prior_auth_permit_agent_record_approval"]
    assert 'action == AgentCore::Action::"ApprovalService___record_approval"' in s



def test_policy_stack_has_no_cross_stack_imports(stacks):
    import json
    _, p = stacks
    text = json.dumps(p.to_json())
    assert "Fn::ImportValue" not in text
    assert "gateway/prior-auth-agent-abc" in text and "gateway/prior-auth-reviewer-def" in text
