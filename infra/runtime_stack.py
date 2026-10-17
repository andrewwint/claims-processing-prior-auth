"""Stack (beat 2): the Strands agent on AgentCore Runtime.

CodeZip ARM64 (build/runtime from scripts/build_runtime.py), HTTP protocol, a JWT
authorizer that admits only the intake client, public network mode, and an
execution role scoped to: the allow-listed model, the packet and recommendation
prefixes, the operator metric, and AgentCore Identity's M2M token. The
telemetry content settings are pinned from prior_auth.agent.telemetry.
"""

from aws_cdk import Aws, Stack, aws_bedrock_agentcore_alpha as agentcore, aws_iam as iam
from constructs import Construct

from infra.evidence_stack import bucket_name
from infra.names import (EVIDENCE_KEY_ALIAS, EXTRACTION_MODEL_ID, IDENTITY_PROVIDER_NAME, MODELS, OPT_IN_MODELS,
                         ROLE_NAMES, RUNTIME_NAME)
from prior_auth.agent import operator
from prior_auth.agent.telemetry import RUNTIME_TELEMETRY_ENV

RUNTIME_CODE = "build/runtime"
# AgentCore Identity keeps the provider's client secret in a managed secret; the runtime role
# may let Identity use that one secret on its behalf (the runtime never handles the value).
IDENTITY_SECRET_ACTION = "secretsmanager:GetSecretValue"


def model_resources(model_ids, account: str) -> list[str]:
    """The exact ARNs for the allow-listed models: foundation models in their named Regions,
    plus the inference profile for a profile model."""
    arns = []
    for model_id in model_ids:
        m = MODELS[model_id]
        arns += [f"arn:aws:bedrock:{r}::foundation-model/{m['foundation_model']}" for r in m["regions"]]
        if m["profile"]:
            arns.append(f"arn:aws:bedrock:us-east-1:{account}:inference-profile/{model_id}")
    return arns


class RuntimeStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, user_pool_id: str, intake_client_id: str,
                 agent_gateway_url: str, code_path: str = RUNTIME_CODE, opt_in_models=(), **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        region, account = Aws.REGION, Aws.ACCOUNT_ID
        role = iam.Role(self, "RuntimeRole", role_name=ROLE_NAMES["runtime"],
                        assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com", conditions={
                            "StringEquals": {"aws:SourceAccount": account},
                            "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock-agentcore:{region}:{account}:*"}}))
        bucket = bucket_name()
        unknown = set(opt_in_models) - set(OPT_IN_MODELS)
        if unknown:
            raise ValueError(f"not opt-in models: {sorted(unknown)}")
        allowed = (EXTRACTION_MODEL_ID, *opt_in_models)
        statements = [
            # M9: the allow-listed models only, each in its named Regions.
            iam.PolicyStatement(actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                                resources=model_resources(allowed, account)),
            iam.PolicyStatement(actions=["s3:PutObject"],
                                resources=[f"arn:aws:s3:::{bucket}/packets/*", f"arn:aws:s3:::{bucket}/recommendations/*"]),
            iam.PolicyStatement(actions=["kms:GenerateDataKey", "kms:Encrypt"], resources=["*"],
                                conditions={"ForAnyValue:StringEquals": {"kms:ResourceAliases": EVIDENCE_KEY_ALIAS}}),
            iam.PolicyStatement(actions=["cloudwatch:PutMetricData"], resources=["*"],
                                conditions={"StringEquals": {"cloudwatch:namespace": [operator.NAMESPACE, "bedrock-agentcore"]}}),
            iam.PolicyStatement(actions=["bedrock-agentcore:GetWorkloadAccessToken",
                                         "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
                                         "bedrock-agentcore:GetWorkloadAccessTokenForUserId",
                                         "bedrock-agentcore:GetResourceOauth2Token"],
                                resources=[f"arn:aws:bedrock-agentcore:{region}:{account}:workload-identity-directory/default",
                                           f"arn:aws:bedrock-agentcore:{region}:{account}:workload-identity-directory/default/workload-identity/*",
                                           f"arn:aws:bedrock-agentcore:{region}:{account}:token-vault/default",
                                           f"arn:aws:bedrock-agentcore:{region}:{account}:token-vault/default/oauth2credentialprovider/{IDENTITY_PROVIDER_NAME}"]),
            iam.PolicyStatement(actions=[IDENTITY_SECRET_ACTION],
                                resources=[f"arn:aws:secretsmanager:{region}:{account}:secret:bedrock-agentcore-identity!default/oauth2/{IDENTITY_PROVIDER_NAME}*"]),
            iam.PolicyStatement(actions=["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents",
                                         "logs:DescribeLogStreams", "logs:DescribeLogGroups"],
                                resources=[f"arn:aws:logs:{region}:{account}:log-group:/aws/bedrock-agentcore/runtimes/*"]),
            # Spans go to the agent's own log group; AgentCore uses this to let X-Ray deliver them there.
            iam.PolicyStatement(actions=["logs:PutResourcePolicy", "logs:DescribeResourcePolicies"],
                                resources=[f"arn:aws:logs:{region}:{account}:log-group:/aws/bedrock-agentcore/runtimes/*"]),
            iam.PolicyStatement(actions=["xray:PutTraceSegments", "xray:PutTelemetryRecords",
                                         "xray:GetSamplingRules", "xray:GetSamplingTargets"], resources=["*"]),
            # Memory is not used for patient data.
            iam.PolicyStatement(effect=iam.Effect.DENY, actions=["bedrock-agentcore:CreateMemory",
                                                                 "bedrock-agentcore:CreateEvent",
                                                                 "bedrock-agentcore:RetrieveMemoryRecords"],
                                resources=["*"]),
        ]
        for st in statements:
            role.add_to_policy(st)
        self.runtime = agentcore.Runtime(
            self, "Runtime", runtime_name=RUNTIME_NAME, execution_role=role,
            agent_runtime_artifact=agentcore.AgentRuntimeArtifact.from_code_asset(
                # ADOT auto-instrumentation: without this prefix a CodeZip runtime emits no spans.
                path=code_path, runtime=agentcore.AgentCoreRuntime.PYTHON_3_13,
                entrypoint=["opentelemetry-instrument", "main.py"]),
            authorizer_configuration=agentcore.RuntimeAuthorizerConfiguration.using_jwt(
                discovery_url=f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/openid-configuration",
                allowed_clients=[intake_client_id]),
            environment_variables={**RUNTIME_TELEMETRY_ENV, "AGENT_GATEWAY_URL": agent_gateway_url,
                                   "EVIDENCE_BUCKET": bucket, "IDENTITY_PROVIDER_NAME": IDENTITY_PROVIDER_NAME,
                                   "MODEL_ID": EXTRACTION_MODEL_ID, "MODEL_ALLOW_LIST": ",".join(allowed)},
        )
