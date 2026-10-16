"""Stack A (approval gate D1): identity, the policy engine, the tool Lambdas, and two gateways.

- Agent gateway: five tools on two targets (four case tools; the approval
  service, with its own Lambda and role); admits the agent app client only.
- Reviewer gateway: the denial tool; admits the clinician group on the clinician client only.
Every Lambda target authenticates with its gateway's own IAM role.
"""

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack, aws_bedrockagentcore as agentcore
from aws_cdk import aws_cloudwatch as cloudwatch, aws_cognito as cognito, aws_iam as iam, aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from constructs import Construct

from infra.identity import RESOURCE_SERVER, SCOPE, Identity
from prior_auth.agent import operator
from prior_auth.handlers.schemas import (APPROVAL_TARGET, APPROVAL_TOOLS, CASE_TARGET, CASE_TOOLS, REVIEWER_TARGET,
                           REVIEWER_TOOLS)

# Lambda code is bundled from src/: only the prior_auth package, no caches or dotfiles.
ASSET_ROOT = "src"
ASSET_EXCLUDE = ["*", ".*", "**/.*", "!prior_auth", "!prior_auth/**", "**/__pycache__", "**/.*"]


# Layer 1 on the reviewer gateway: the clinician client AND pa_role == "clinician",
# the scalar claim the pre-token trigger derives from group membership.
CLINICIAN_GROUP_CLAIM = agentcore.CfnGateway.CustomClaimValidationTypeProperty(
    inbound_token_claim_name="pa_role",
    inbound_token_claim_value_type="STRING",
    authorizing_claim_match_value=agentcore.CfnGateway.AuthorizingClaimMatchValueTypeProperty(
        claim_match_operator="EQUALS",
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
                 gateway_ids: dict[str, str] | None = None, b4_layer2_test: bool = False, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        # First pass: roles are bound to the gateway name prefix. Second pass (after
        # D1 records the real IDs): bound to the exact gateway.
        self.gateway_ids = gateway_ids or {}
        self.functions: dict[str, lambda_.Function] = {}
        self.identity = Identity(self, "Identity", domain_prefix=domain_prefix)
        self.identity.pool.add_trigger(
            cognito.UserPoolOperation.PRE_TOKEN_GENERATION_CONFIG,
            self._function("PreToken", "prior_auth.handlers.pre_token.handler", "prior-auth-pre-token"),
            cognito.LambdaVersion.V2_0,
        )
        # Attached in ENFORCE mode from the first deploy. With no policies yet,
        # every tool call is denied by default until the policy stack (D2) lands.
        self.engine = agentcore.CfnPolicyEngine(self, "PolicyEngine", name="prior_auth_engine")
        self.agent_gateway = self._gateway(
            "Agent", name="prior-auth-agent", allowed_clients=[self.identity.agent_client.user_pool_client_id],
            targets=[
                ("AgentTools", CASE_TARGET, CASE_TOOLS, "prior_auth.handlers.agent_tools.handler", "prior-auth-agent-tools"),
                ("ApprovalService", APPROVAL_TARGET, APPROVAL_TOOLS, "prior_auth.handlers.approval_service.handler",
                 "prior-auth-approval-service"),
            ],
            allowed_scopes=[f"{RESOURCE_SERVER}/{SCOPE}"],
        )
        # D4 only: a temporary test configuration that lets the agent's token past
        # layer 1 so the Cedar forbid (layer 2) can be shown to deny it. Reverted
        # by redeploying without the flag.
        reviewer_clients = [self.identity.clinician_client.user_pool_client_id]
        if b4_layer2_test:
            reviewer_clients.append(self.identity.agent_client.user_pool_client_id)
        self.reviewer_gateway = self._gateway(
            "Reviewer", name="prior-auth-reviewer", allowed_clients=reviewer_clients,
            targets=[("ReviewerTools", REVIEWER_TARGET, REVIEWER_TOOLS, "prior_auth.handlers.reviewer_tools.handler",
                      "prior-auth-reviewer-tools")],
            custom_claims=None if b4_layer2_test else [CLINICIAN_GROUP_CLAIM],
        )
        self._traces_only()
        # F4: the operator alert. No SNS (PM, 2026-10-16); the alarm state change is the evidence.
        cloudwatch.Alarm(
            self, "ModelAccessDeniedAlarm", alarm_name="prior-auth-model-access-denied",
            metric=cloudwatch.Metric(namespace=operator.NAMESPACE, metric_name=operator.METRIC,
                                     statistic="Sum", period=Duration.minutes(1)),
            threshold=1, evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
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

    def _traces_only(self) -> None:
        """Gateway tracing (approval gate D3): TRACES to X-Ray only.

        Gateway APPLICATION_LOGS include full request and response bodies, which
        here are tool arguments quoting synthetic chart text, so they are never
        enabled. Spans carry only operational attributes (contract notes).
        """
        destination = logs.CfnDeliveryDestination(
            self, "TracesDestination", name="prior-auth-traces-xray", delivery_destination_type="XRAY")
        for prefix, gw in (("Agent", self.agent_gateway), ("Reviewer", self.reviewer_gateway)):
            source = logs.CfnDeliverySource(
                self, f"{prefix}TracesSource", name=f"prior-auth-{prefix.lower()}-traces",
                log_type="TRACES", resource_arn=gw.attr_gateway_arn)
            delivery = logs.CfnDelivery(
                self, f"{prefix}TracesDelivery", delivery_source_name=source.name,
                delivery_destination_arn=destination.attr_arn)
            delivery.add_dependency(source)
            delivery.add_dependency(destination)

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
            handler=handler, code=lambda_.Code.from_asset(ASSET_ROOT, exclude=ASSET_EXCLUDE),
            timeout=Duration.seconds(15), memory_size=256, log_group=log_group,
        )
        self.functions[function_name] = fn
        return fn

    def _gateway(self, prefix, *, name, allowed_clients, targets, allowed_scopes=None, custom_claims=None):
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
                    discovery_url=self.identity.discovery_url, allowed_clients=allowed_clients,
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
