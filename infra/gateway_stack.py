"""Stack A (approval gate D1): identity, the policy engine, the tool Lambdas, and two gateways.

- Agent gateway: five tools on two targets (four case tools; the approval
  service, with its own Lambda and role); admits the agent app client only.
- Reviewer gateway: the denial tool; admits the clinician group on the clinician client only.
Every Lambda target authenticates with its gateway's own IAM role.
"""

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack, aws_bedrockagentcore as agentcore
from aws_cdk import aws_iam as iam, aws_lambda as lambda_, aws_logs as logs
from constructs import Construct

from infra.identity import RESOURCE_SERVER, SCOPE, Identity
from tools.schemas import (APPROVAL_TARGET, APPROVAL_TOOLS, CASE_TARGET, CASE_TOOLS, REVIEWER_TARGET,
                           REVIEWER_TOOLS)

ASSET_EXCLUDE = ["*", ".*", "**/.*", "!tools", "!tools/**", "!checks", "!checks/**", "**/__pycache__", "**/.*"]


# Layer 1 on the reviewer gateway: the clinician client AND membership of the clinician group.
CLINICIAN_GROUP_CLAIM = agentcore.CfnGateway.CustomClaimValidationTypeProperty(
    inbound_token_claim_name="cognito:groups",
    inbound_token_claim_value_type="STRING_ARRAY",
    authorizing_claim_match_value=agentcore.CfnGateway.AuthorizingClaimMatchValueTypeProperty(
        claim_match_operator="CONTAINS",
        claim_match_value=agentcore.CfnGateway.ClaimMatchValueTypeProperty(match_value_string="clinician"),
    ),
)


def _schema(d: dict) -> agentcore.CfnGatewayTarget.SchemaDefinitionProperty:
    return agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
        type=d["type"],
        description=d.get("description"),
        properties={k: _schema(v) for k, v in d["properties"].items()} if "properties" in d else None,
        required=d.get("required"),
        items=_schema(d["items"]) if "items" in d else None,
    )


def _tool(t: dict) -> agentcore.CfnGatewayTarget.ToolDefinitionProperty:
    return agentcore.CfnGatewayTarget.ToolDefinitionProperty(
        name=t["name"], description=t["description"], input_schema=_schema(t["inputSchema"])
    )


class GatewayStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, domain_prefix: str,
                 gateway_ids: dict[str, str] | None = None, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        # First pass: roles are bound to the gateway name prefix. Second pass (after
        # D1 records the real IDs): bound to the exact gateway.
        self.gateway_ids = gateway_ids or {}
        self.identity = Identity(self, "Identity", domain_prefix=domain_prefix)
        # Attached in ENFORCE mode from the first deploy. With no policies yet,
        # every tool call is denied by default until the policy stack (D2) lands.
        self.engine = agentcore.CfnPolicyEngine(self, "PolicyEngine", name="prior_auth_engine")
        self.functions: dict[str, lambda_.Function] = {}
        self.agent_gateway = self._gateway(
            "Agent", name="prior-auth-agent", allowed_client=self.identity.agent_client.user_pool_client_id,
            targets=[
                ("AgentTools", CASE_TARGET, CASE_TOOLS, "tools.agent_tools.handler", "prior-auth-agent-tools"),
                ("ApprovalService", APPROVAL_TARGET, APPROVAL_TOOLS, "tools.approval_service.handler",
                 "prior-auth-approval-service"),
            ],
            allowed_scopes=[f"{RESOURCE_SERVER}/{SCOPE}"],
        )
        self.reviewer_gateway = self._gateway(
            "Reviewer", name="prior-auth-reviewer", allowed_client=self.identity.clinician_client.user_pool_client_id,
            targets=[("ReviewerTools", REVIEWER_TARGET, REVIEWER_TOOLS, "tools.reviewer_tools.handler",
                      "prior-auth-reviewer-tools")],
            custom_claims=[CLINICIAN_GROUP_CLAIM],
        )
        for key, value in {
            "UserPoolId": self.identity.pool.user_pool_id,
            "AgentClientId": self.identity.agent_client.user_pool_client_id,
            "ClinicianClientId": self.identity.clinician_client.user_pool_client_id,
            "TokenDomain": self.identity.domain.base_url(),
            "AgentGatewayId": self.agent_gateway.attr_gateway_identifier,
            "PolicyEngineId": self.engine.attr_policy_engine_id,
            "ReviewerGatewayId": self.reviewer_gateway.attr_gateway_identifier,
            "AgentGatewayUrl": self.agent_gateway.attr_gateway_url,
            "AgentGatewayArn": self.agent_gateway.attr_gateway_arn,
            "ReviewerGatewayUrl": self.reviewer_gateway.attr_gateway_url,
            "ReviewerGatewayArn": self.reviewer_gateway.attr_gateway_arn,
        }.items():
            CfnOutput(self, key, value=value)

    def _gateway_arn_pattern(self, name: str) -> str:
        exact = self.gateway_ids.get(name)
        return f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:gateway/{exact or name + '-*'}"

    def _function(self, construct_id: str, handler: str, function_name: str) -> lambda_.Function:
        log_group = logs.LogGroup(
            self, f"{construct_id}Logs", log_group_name=f"/aws/lambda/{function_name}",
            retention=logs.RetentionDays.ONE_WEEK, removal_policy=RemovalPolicy.DESTROY,
        )
        fn = lambda_.Function(
            self, construct_id, function_name=function_name,
            runtime=lambda_.Runtime.PYTHON_3_13, architecture=lambda_.Architecture.ARM_64,
            handler=handler, code=lambda_.Code.from_asset(".", exclude=ASSET_EXCLUDE),
            timeout=Duration.seconds(15), memory_size=256, log_group=log_group,
        )
        self.functions[function_name] = fn
        return fn

    def _gateway(self, prefix, *, name, allowed_client, targets, allowed_scopes=None, custom_claims=None):
        """targets: (construct id, target name, tools, handler, function name) per Lambda target."""
        role = iam.Role(
            self, f"{prefix}GatewayRole",
            assumed_by=iam.ServicePrincipal(
                "bedrock-agentcore.amazonaws.com",
                conditions={
                    "StringEquals": {"aws:SourceAccount": self.account},
                    # Confused-deputy guard: only this project's named gateway may assume the role.
                    "ArnLike": {"aws:SourceArn": self._gateway_arn_pattern(name)},
                },
            ),
        )
        role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock-agentcore:AuthorizeAction", "bedrock-agentcore:PartiallyAuthorizeActions",
                     "bedrock-agentcore:GetPolicyEngine"],
            resources=[self._gateway_arn_pattern(name),
                       self.engine.attr_policy_engine_arn],
        ))
        gateway = agentcore.CfnGateway(
            self, f"{prefix}Gateway", name=name, protocol_type="MCP", authorizer_type="CUSTOM_JWT",
            role_arn=role.role_arn,
            authorizer_configuration=agentcore.CfnGateway.AuthorizerConfigurationProperty(
                custom_jwt_authorizer=agentcore.CfnGateway.CustomJWTAuthorizerConfigurationProperty(
                    discovery_url=self.identity.discovery_url, allowed_clients=[allowed_client],
                    allowed_scopes=allowed_scopes, custom_claims=custom_claims,
                )
            ),
            policy_engine_configuration=agentcore.CfnGateway.GatewayPolicyEngineConfigurationProperty(
                arn=self.engine.attr_policy_engine_arn, mode="ENFORCE",
            ),
        )
        gateway.node.add_dependency(role)
        for construct_id, target, tools, handler, function_name in targets:
            fn = self._function(construct_id, handler, function_name)
            fn.grant_invoke(role)
            self._target(construct_id, gateway, target, tools, fn)
        return gateway

    def _target(self, construct_id, gateway, target, tools, fn):
        agentcore.CfnGatewayTarget(
            self, f"{construct_id}Target", name=target, gateway_identifier=gateway.attr_gateway_identifier,
            target_configuration=agentcore.CfnGatewayTarget.TargetConfigurationProperty(
                mcp=agentcore.CfnGatewayTarget.McpTargetConfigurationProperty(
                    lambda_=agentcore.CfnGatewayTarget.McpLambdaTargetConfigurationProperty(
                        lambda_arn=fn.function_arn,
                        tool_schema=agentcore.CfnGatewayTarget.ToolSchemaProperty(
                            inline_payload=[_tool(t) for t in tools]
                        ),
                    )
                )
            ),
            credential_provider_configurations=[
                agentcore.CfnGatewayTarget.CredentialProviderConfigurationProperty(
                    credential_provider_type="GATEWAY_IAM_ROLE"
                )
            ],
        )
