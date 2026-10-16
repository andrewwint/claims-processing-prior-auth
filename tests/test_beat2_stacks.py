"""CDK assertions for the beat 2 stacks: the evidence bucket and the runtime."""

import json

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Template

from infra.evidence_stack import EvidenceStack
from infra.runtime_stack import RuntimeStack

ENV = cdk.Environment(region="us-east-1")


@pytest.fixture(scope="module")
def evidence():
    return Template.from_stack(EvidenceStack(cdk.App(), "E", env=ENV))


@pytest.fixture(scope="module")
def runtime(tmp_path_factory):
    code = tmp_path_factory.mktemp("runtime")
    (code / "main.py").write_text("print('placeholder')\n")
    return Template.from_stack(RuntimeStack(cdk.App(), "R", env=ENV, user_pool_id="us-east-1_TEST",
                                            intake_client_id="INTAKECLIENT", agent_gateway_url="https://gw/mcp",
                                            code_path=str(code)))


def _statements(template, rtype="AWS::S3::BucketPolicy"):
    return [s for r in template.find_resources(rtype).values() for s in r["Properties"]["PolicyDocument"]["Statement"]]


def test_bucket_is_object_locked_versioned_and_kms_encrypted(evidence):
    bucket = next(iter(evidence.find_resources("AWS::S3::Bucket").values()))["Properties"]
    assert bucket["ObjectLockEnabled"] is True
    assert bucket["ObjectLockConfiguration"]["Rule"]["DefaultRetention"] == {"Mode": "GOVERNANCE", "Days": 1}
    assert bucket["VersioningConfiguration"]["Status"] == "Enabled"
    enc = bucket["BucketEncryption"]["ServerSideEncryptionConfiguration"][0]
    assert enc["ServerSideEncryptionByDefault"]["SSEAlgorithm"] == "aws:kms" and enc["BucketKeyEnabled"] is True
    evidence.resource_count_is("AWS::KMS::Key", 1)


@pytest.mark.parametrize("prefix,writers", [("packets/", ["prior-auth-runtime-role"]),
                                            ("recommendations/", ["prior-auth-runtime-role"]),
                                            ("queue/", ["prior-auth-agent-tools-role"]),
                                            ("decisions/", ["prior-auth-reviewer-tools-role", "prior-auth-approval-service-role"])])
def test_each_prefix_has_only_its_writers(evidence, prefix, writers):
    st = next(s for s in _statements(evidence) if s.get("Sid") == f"OnlyWriters{prefix.strip('/').title()}")
    assert st["Effect"] == "Deny" and st["Action"] == "s3:PutObject"
    allowed = json.dumps(st["Condition"]["ArnNotEquals"]["aws:PrincipalArn"])
    assert all(w in allowed for w in writers) and allowed.count(":role/") == len(writers)


def test_only_the_teardown_role_bypasses_retention(evidence):
    st = next(s for s in _statements(evidence) if s.get("Sid") == "OnlyTeardownBypassesRetention")
    assert "s3:BypassGovernanceRetention" in st["Action"] and "prior-auth-teardown" in json.dumps(st["Condition"])


def test_runtime_admits_only_the_intake_client(runtime):
    rt = next(iter(runtime.find_resources("AWS::BedrockAgentCore::Runtime").values()))["Properties"]
    assert rt["AuthorizerConfiguration"]["CustomJWTAuthorizer"]["AllowedClients"] == ["INTAKECLIENT"]


def test_runtime_carries_both_telemetry_settings_and_no_secret(runtime):
    env = next(iter(runtime.find_resources("AWS::BedrockAgentCore::Runtime").values()))["Properties"]["EnvironmentVariables"]
    assert env["OTEL_SEMCONV_STABILITY_OPT_IN"] == "gen_ai_unredacted_attributes="
    assert env["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] == "false"
    assert not any(k for k in env if "SECRET" in k or "PASSWORD" in k or "TOKEN" in k)


def test_runtime_role_invokes_only_the_allow_listed_model_and_denies_memory(runtime):
    statements = _statements(runtime, "AWS::IAM::Policy")
    invoke = next(s for s in statements if "bedrock:InvokeModel" in s["Action"])
    assert json.dumps(invoke["Resource"]).count("foundation-model/") == 1 and "amazon.nova-pro-v1:0" in json.dumps(invoke["Resource"])
    deny = next(s for s in statements if s["Effect"] == "Deny")
    assert "bedrock-agentcore:CreateMemory" in deny["Action"]


def test_mmdsv2_update_copies_every_field_and_only_adds_the_setting():
    from scripts.require_mmdsv2 import update_request
    current = {"agentRuntimeId": "R", "agentRuntimeArtifact": {"a": 1}, "roleArn": "arn", "environmentVariables": {"K": "V"},
               "authorizerConfiguration": {"customJWTAuthorizer": {}}, "networkConfiguration": {"networkMode": "PUBLIC"},
               "status": "READY", "agentRuntimeArn": "x"}
    req = update_request(current)
    assert req["metadataConfiguration"] == {"requireMMDSV2": True}
    assert req["environmentVariables"] == {"K": "V"} and req["authorizerConfiguration"] == {"customJWTAuthorizer": {}}
    assert "status" not in req and "agentRuntimeArn" not in req


def test_identity_provider_config_points_at_the_pool_discovery_url():
    from scripts.create_identity_provider import provider_config
    cfg = provider_config({"UserPoolId": "us-east-1_X", "AgentClientId": "C"}, "s")["customOauth2ProviderConfig"]
    assert cfg["oauthDiscovery"]["discoveryUrl"].endswith("/us-east-1_X/.well-known/openid-configuration")
    assert cfg["clientId"] == "C"



def test_runtime_entry_point_is_instrumented(runtime):
    rt = next(iter(runtime.find_resources("AWS::BedrockAgentCore::Runtime").values()))["Properties"]
    assert rt["AgentRuntimeArtifact"]["CodeConfiguration"]["EntryPoint"] == ["opentelemetry-instrument", "main.py"]
