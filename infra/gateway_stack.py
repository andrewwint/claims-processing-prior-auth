"""Stack A (approval gate D1): identity, the tool Lambdas, and two gateways.

- Agent gateway: five tools; admits the agent app client only.
- Reviewer gateway: the denial tool; admits the clinician app client only.
Both Lambda targets authenticate with the gateway's own IAM role.
"""

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack, aws_bedrockagentcore as agentcore
from aws_cdk import aws_iam as iam, aws_lambda as lambda_, aws_logs as logs
from constructs import Construct

from infra.identity import Identity
from tools.schemas import AGENT_TARGET, AGENT_TOOLS, REVIEWER_TARGET, REVIEWER_TOOLS

ASSET_EXCLUDE = ["*", ".*", "**/.*", "!tools", "!tools/**", "tools/**/__pycache__", "tools/**/.*"]


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
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        self.identity = Identity(self, "Identity")
        self.agent_gateway = self._gateway(
            "Agent", name="prior-auth-agent", allowed_client=self.identity.agent_client.user_pool_client_id,
            target=AGENT_TARGET, tools=AGENT_TOOLS, handler="tools.agent_tools.handler",
            function_name="prior-auth-agent-tools",
        )
        self.reviewer_gateway = self._gateway(
            "Reviewer", name="prior-auth-reviewer", allowed_client=self.identity.clinician_client.user_pool_client_id,
            target=REVIEWER_TARGET, tools=REVIEWER_TOOLS, handler="tools.reviewer_tools.handler",
            function_name="prior-auth-reviewer-tools",
        )
        for key, value in {
            "UserPoolId": self.identity.pool.user_pool_id,
            "AgentClientId": self.identity.agent_client.user_pool_client_id,
            "ClinicianClientId": self.identity.clinician_client.user_pool_client_id,
            "TokenDomain": self.identity.domain.base_url(),
            "AgentGatewayUrl": self.agent_gateway.attr_gateway_url,
            "AgentGatewayArn": self.agent_gateway.attr_gateway_arn,
            "ReviewerGatewayUrl": self.reviewer_gateway.attr_gateway_url,
            "ReviewerGatewayArn": self.reviewer_gateway.attr_gateway_arn,
        }.items():
            CfnOutput(self, key, value=value)

    def _gateway(self, prefix, *, name, allowed_client, target, tools, handler, function_name):
        log_group = logs.LogGroup(
            self, f"{prefix}ToolsLogs", log_group_name=f"/aws/lambda/{function_name}",
            retention=logs.RetentionDays.ONE_WEEK, removal_policy=RemovalPolicy.DESTROY,
        )
        fn = lambda_.Function(
            self, f"{prefix}Tools", function_name=function_name,
            runtime=lambda_.Runtime.PYTHON_3_13, architecture=lambda_.Architecture.ARM_64,
            handler=handler, code=lambda_.Code.from_asset(".", exclude=ASSET_EXCLUDE),
            timeout=Duration.seconds(15), memory_size=256, log_group=log_group,
        )
        role = iam.Role(
            self, f"{prefix}GatewayRole",
            assumed_by=iam.ServicePrincipal(
                "bedrock-agentcore.amazonaws.com",
                conditions={"StringEquals": {"aws:SourceAccount": self.account}},
            ),
        )
        fn.grant_invoke(role)
        role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock-agentcore:AuthorizeAction", "bedrock-agentcore:PartiallyAuthorizeActions",
                     "bedrock-agentcore:GetPolicyEngine"],
            resources=[f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:gateway/*",
                       f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:policy-engine/*"],
        ))
        gateway = agentcore.CfnGateway(
            self, f"{prefix}Gateway", name=name, protocol_type="MCP", authorizer_type="CUSTOM_JWT",
            role_arn=role.role_arn,
            authorizer_configuration=agentcore.CfnGateway.AuthorizerConfigurationProperty(
                custom_jwt_authorizer=agentcore.CfnGateway.CustomJWTAuthorizerConfigurationProperty(
                    discovery_url=self.identity.discovery_url, allowed_clients=[allowed_client],
                )
            ),
        )
        gateway.node.add_dependency(role)
        agentcore.CfnGatewayTarget(
            self, f"{prefix}Target", name=target, gateway_identifier=gateway.attr_gateway_identifier,
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
        return gateway
