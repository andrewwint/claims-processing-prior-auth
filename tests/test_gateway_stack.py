import json

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Template

from infra.gateway_stack import GatewayStack

FIVE = ["check_eligibility", "fetch_policy_criteria", "extract_clinical_evidence", "record_approval", "route_to_reviewer"]


@pytest.fixture(scope="module")
def template():
    app = cdk.App()
    return Template.from_stack(GatewayStack(app, "G", env=cdk.Environment(region="us-east-1"), domain_prefix="prior-auth-test"))


def _one(template, rtype, **match):
    found = [r for r in template.find_resources(rtype).values()
             if all(r["Properties"].get(k) == v for k, v in match.items())]
    assert len(found) == 1, (rtype, match, len(found))
    return found[0]["Properties"]


def _client_ref(template, name):
    return {"Ref": next(k for k, r in template.find_resources("AWS::Cognito::UserPoolClient").items()
                        if r["Properties"]["ClientName"] == name)}


def test_self_signup_is_disabled(template):
    pool = _one(template, "AWS::Cognito::UserPool", UserPoolName="prior-auth-users")
    assert pool["AdminCreateUserConfig"]["AllowAdminCreateUserOnly"] is True


def test_agent_is_a_client_credentials_client_not_a_user(template):
    agent = _one(template, "AWS::Cognito::UserPoolClient", ClientName="prior-auth-agent")
    assert agent["AllowedOAuthFlows"] == ["client_credentials"]
    assert agent["GenerateSecret"] is True
    clinician = _one(template, "AWS::Cognito::UserPoolClient", ClientName="prior-auth-clinician")
    assert "AllowedOAuthFlows" not in clinician or clinician["AllowedOAuthFlows"] != ["client_credentials"]


def test_groups(template):
    names = sorted(r["Properties"]["GroupName"] for r in template.find_resources("AWS::Cognito::UserPoolGroup").values())
    assert names == ["clinician", "tenant-a", "tenant-b"]


def test_reviewer_gateway_admits_the_clinician_client_only(template):
    gw = _one(template, "AWS::BedrockAgentCore::Gateway", Name="prior-auth-reviewer")
    jwt = gw["AuthorizerConfiguration"]["CustomJWTAuthorizer"]
    assert jwt["AllowedClients"] == [_client_ref(template, "prior-auth-clinician")]
    assert gw["AuthorizerType"] == "CUSTOM_JWT" and gw["ProtocolType"] == "MCP"


def test_agent_gateway_admits_the_agent_client_only(template):
    gw = _one(template, "AWS::BedrockAgentCore::Gateway", Name="prior-auth-agent")
    assert gw["AuthorizerConfiguration"]["CustomJWTAuthorizer"]["AllowedClients"] == [_client_ref(template, "prior-auth-agent")]


def _tools(target):
    return [t["Name"] for t in target["TargetConfiguration"]["Mcp"]["Lambda"]["ToolSchema"]["InlinePayload"]]


def _gateway_logical_id(template, name):
    return next(k for k, r in template.find_resources("AWS::BedrockAgentCore::Gateway").items()
                if r["Properties"]["Name"] == name)


def _targets_of(template, gateway_name):
    gid = _gateway_logical_id(template, gateway_name)
    return [r["Properties"] for r in template.find_resources("AWS::BedrockAgentCore::GatewayTarget").values()
            if r["Properties"]["GatewayIdentifier"] == {"Fn::GetAtt": [gid, "GatewayIdentifier"]}]


def test_agent_gateway_registers_exactly_five_tools_on_two_targets(template):
    targets = _targets_of(template, "prior-auth-agent")
    assert sorted(t["Name"] for t in targets) == ["AgentTools", "ApprovalService"]
    assert sorted(n for t in targets for n in _tools(t)) == sorted(FIVE)
    assert _tools(_one(template, "AWS::BedrockAgentCore::GatewayTarget", Name="ApprovalService")) == ["record_approval"]


def test_reviewer_gateway_has_only_the_denial_target(template):
    assert [t["Name"] for t in _targets_of(template, "prior-auth-reviewer")] == ["ReviewerTools"]


def test_approval_service_has_its_own_function_and_role(template):
    fns = {r["Properties"]["FunctionName"]: r["Properties"] for r in template.find_resources("AWS::Lambda::Function").values()}
    assert set(fns) == {"prior-auth-agent-tools", "prior-auth-approval-service", "prior-auth-reviewer-tools",
                        "prior-auth-pre-token"}
    assert fns["prior-auth-approval-service"]["Handler"] == "prior_auth.handlers.approval_service.handler"
    roles = {json.dumps(f["Role"]) for f in fns.values()}
    assert len(roles) == 4


def test_reviewer_target_is_named_for_the_article_snippet(template):
    assert _tools(_one(template, "AWS::BedrockAgentCore::GatewayTarget", Name="ReviewerTools")) == [
        "record_adverse_determination", "record_clinician_approval"]


def test_record_approval_schema_has_no_booleans(template):
    payload = _one(template, "AWS::BedrockAgentCore::GatewayTarget", Name="ApprovalService")["TargetConfiguration"]["Mcp"]["Lambda"]["ToolSchema"]["InlinePayload"]
    approval = next(t for t in payload if t["Name"] == "record_approval")["InputSchema"]
    assert {k: v["Type"] for k, v in approval["Properties"].items()} == {"packet_id": "string", "packet_hash": "string"}
    assert "boolean" not in json.dumps(payload)


def test_every_target_uses_the_gateway_role_and_holds_no_secret(template):
    targets = template.find_resources("AWS::BedrockAgentCore::GatewayTarget").values()
    assert len(targets) == 3
    for t in targets:
        assert t["Properties"]["CredentialProviderConfigurations"] == [{"CredentialProviderType": "GATEWAY_IAM_ROLE"}]


def test_lambda_log_groups_are_explicit_and_destroyed(template):
    groups = template.find_resources("AWS::Logs::LogGroup")
    names = sorted(g["Properties"]["LogGroupName"] for g in groups.values())
    assert names == ["/aws/lambda/prior-auth-agent-tools", "/aws/lambda/prior-auth-approval-service",
                     "/aws/lambda/prior-auth-pre-token", "/aws/lambda/prior-auth-reviewer-tools"]
    assert all(g["DeletionPolicy"] == "Delete" for g in groups.values())


def test_gateway_roles_can_authorize_policy_decisions(template):
    statements = [s for p in template.find_resources("AWS::IAM::Policy").values()
                  for s in p["Properties"]["PolicyDocument"]["Statement"]]
    authz = [s for s in statements if "bedrock-agentcore:AuthorizeAction" in s["Action"]]
    assert len(authz) == 2
    for s in authz:
        assert set(s["Action"]) == {"bedrock-agentcore:AuthorizeAction", "bedrock-agentcore:PartiallyAuthorizeActions",
                                    "bedrock-agentcore:GetPolicyEngine"}


def test_no_lambda_environment_holds_a_secret(template):
    for fn in template.find_resources("AWS::Lambda::Function").values():
        assert "Environment" not in fn["Properties"]


def test_lambda_asset_contains_only_the_prior_auth_package(tmp_path):
    import shutil
    from pathlib import Path

    from aws_cdk import CopyOptions, FileSystem
    from infra.gateway_stack import ASSET_EXCLUDE, ASSET_ROOT

    root = Path(__file__).resolve().parent.parent / ASSET_ROOT
    out = tmp_path / "asset"
    FileSystem.copy_directory(str(root), str(out), CopyOptions(exclude=ASSET_EXCLUDE))
    files = sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file())
    assert files and all(f.startswith("prior_auth/") for f in files), files
    core = Path("prior_auth") / "checks" / "core.py"
    assert (out / core).read_bytes() == (root / core).read_bytes()
    assert not any("/." in f or f.startswith(".") for f in files)
    shutil.rmtree(out)


# Security review fixes (E1-E4, E7, hardening)
def test_reviewer_gateway_requires_the_clinician_group_claim(template):
    jwt = _one(template, "AWS::BedrockAgentCore::Gateway", Name="prior-auth-reviewer")["AuthorizerConfiguration"]["CustomJWTAuthorizer"]
    assert jwt["CustomClaims"] == [{
        "InboundTokenClaimName": "pa_role",
        "InboundTokenClaimValueType": "STRING",
        "AuthorizingClaimMatchValue": {"ClaimMatchOperator": "EQUALS", "ClaimMatchValue": {"MatchValueString": "clinician"}},
    }]


def test_agent_gateway_requires_the_tools_scope(template):
    jwt = _one(template, "AWS::BedrockAgentCore::Gateway", Name="prior-auth-agent")["AuthorizerConfiguration"]["CustomJWTAuthorizer"]
    assert jwt["AllowedScopes"] == ["prior-auth/tools"]


def test_clinician_client_uses_code_flow_with_localhost_callback_only(template):
    clinician = _one(template, "AWS::Cognito::UserPoolClient", ClientName="prior-auth-clinician")
    assert clinician["AllowedOAuthFlows"] == ["code"]
    assert clinician["CallbackURLs"] == ["http://localhost:8765/callback"]
    assert sorted(clinician["AllowedOAuthScopes"]) == ["aws.cognito.signin.user.admin", "openid"]
    assert "GenerateSecret" not in clinician or clinician["GenerateSecret"] is False


def test_clinician_password_fallback_is_srp_only(template):
    clinician = _one(template, "AWS::Cognito::UserPoolClient", ClientName="prior-auth-clinician")
    assert "ALLOW_USER_PASSWORD_AUTH" not in clinician["ExplicitAuthFlows"]
    assert "ALLOW_USER_SRP_AUTH" in clinician["ExplicitAuthFlows"]


def test_clinician_client_cannot_write_user_attributes(template):
    clinician = _one(template, "AWS::Cognito::UserPoolClient", ClientName="prior-auth-clinician")
    assert clinician["WriteAttributes"] == []


def test_agent_client_has_no_user_sign_in_flow(template):
    agent = _one(template, "AWS::Cognito::UserPoolClient", ClientName="prior-auth-agent")
    assert agent["ExplicitAuthFlows"] == ["ALLOW_REFRESH_TOKEN_AUTH"]


def test_clients_prevent_user_existence_errors(template):
    for c in template.find_resources("AWS::Cognito::UserPoolClient").values():
        assert c["Properties"]["PreventUserExistenceErrors"] == "ENABLED"


def test_gateway_roles_are_bound_to_their_own_gateway(template):
    roles = [r["Properties"]["AssumeRolePolicyDocument"]["Statement"][0] for r in template.find_resources("AWS::IAM::Role").values()
             if r["Properties"]["AssumeRolePolicyDocument"]["Statement"][0]["Principal"].get("Service") == "bedrock-agentcore.amazonaws.com"]
    assert len(roles) == 2
    arns = sorted(json.dumps(s["Condition"]["ArnLike"]["aws:SourceArn"]) for s in roles)
    assert "gateway/prior-auth-agent-*" in arns[0] and "gateway/prior-auth-reviewer-*" in arns[1]
    assert all("aws:SourceAccount" in s["Condition"]["StringEquals"] for s in roles)


def test_domain_prefix_comes_from_deploy_context(template):
    domain = next(iter(template.find_resources("AWS::Cognito::UserPoolDomain").values()))
    assert domain["Properties"]["Domain"] == "prior-auth-test"



def test_second_pass_binds_roles_to_exact_gateways():
    app = cdk.App()
    t = Template.from_stack(GatewayStack(app, "G2", env=cdk.Environment(region="us-east-1"), domain_prefix="p",
                                         gateway_ids={"prior-auth-agent": "prior-auth-agent-abc123",
                                                      "prior-auth-reviewer": "prior-auth-reviewer-def456"}))
    text = json.dumps(t.to_json())
    assert "gateway/prior-auth-agent-abc123" in text and "gateway/prior-auth-reviewer-def456" in text
    assert "gateway/prior-auth-agent-*" not in text and "gateway/prior-auth-reviewer-*" not in text



def test_pool_runs_the_pre_token_trigger_v2(template):
    pool = _one(template, "AWS::Cognito::UserPool", UserPoolName="prior-auth-users")
    cfg = pool["LambdaConfig"]["PreTokenGenerationConfig"]
    assert cfg["LambdaVersion"] == "V2_0"
    assert pool["UserPoolTier"] == "ESSENTIALS"


# D3: gateway tracing, traces only
def test_gateways_deliver_traces_to_xray_and_never_application_logs(template):
    sources = [r["Properties"] for r in template.find_resources("AWS::Logs::DeliverySource").values()]
    assert sorted(s["Name"] for s in sources) == ["prior-auth-agent-traces", "prior-auth-reviewer-traces"]
    assert {s["LogType"] for s in sources} == {"TRACES"}
    dests = [r["Properties"] for r in template.find_resources("AWS::Logs::DeliveryDestination").values()]
    assert [d["DeliveryDestinationType"] for d in dests] == ["XRAY"]
    template.resource_count_is("AWS::Logs::Delivery", 2)
    assert "APPLICATION_LOGS" not in json.dumps(template.to_json())


# D4: the temporary B4 layer-2 test configuration
def test_b4_test_config_admits_agent_and_drops_claim_check_only_when_flagged():
    app = cdk.App()
    t = Template.from_stack(GatewayStack(app, "G3", env=cdk.Environment(region="us-east-1"), domain_prefix="p",
                                         b4_layer2_test=True))
    gw = _one(t, "AWS::BedrockAgentCore::Gateway", Name="prior-auth-reviewer")
    jwt = gw["AuthorizerConfiguration"]["CustomJWTAuthorizer"]
    assert len(jwt["AllowedClients"]) == 2 and "CustomClaims" not in jwt
    assert gw["PolicyEngineConfiguration"]["Mode"] == "ENFORCE"


def test_normal_config_is_clinician_only(template):
    jwt = _one(template, "AWS::BedrockAgentCore::Gateway", Name="prior-auth-reviewer")["AuthorizerConfiguration"]["CustomJWTAuthorizer"]
    assert jwt["AllowedClients"] == [_client_ref(template, "prior-auth-clinician")] and jwt["CustomClaims"]


# F4: operator alarm, no SNS
def test_operator_alarm_on_model_access_denied(template):
    alarm = _one(template, "AWS::CloudWatch::Alarm", AlarmName="prior-auth-model-access-denied")
    assert alarm["Namespace"] == "PriorAuth/Operator" and alarm["MetricName"] == "ModelAccessDenied"
    assert alarm["Threshold"] == 1 and "AlarmActions" not in alarm


def test_emit_model_access_denied_writes_the_alarm_metric():
    from prior_auth.agent.operator import emit_model_access_denied
    sent = []

    class CW:
        def put_metric_data(self, **kw):
            sent.append(kw)

    emit_model_access_denied(CW(), "amazon.nova-pro-v1:0")
    assert sent[0]["Namespace"] == "PriorAuth/Operator"
    assert sent[0]["MetricData"][0]["MetricName"] == "ModelAccessDenied"
