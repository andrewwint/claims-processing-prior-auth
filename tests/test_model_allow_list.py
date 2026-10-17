"""M9 (one allow-list, in code and in IAM) and M5 (sampling settings as sent)."""

import json

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Template

from infra.names import EXTRACTION_MODEL_ID, MODELS
from infra.runtime_stack import RuntimeStack

ENV = cdk.Environment(account="000000000000", region="us-east-1")


def _model_arns(tmp_path, opt_in=()):
    (tmp_path / "main.py").write_text("print('placeholder')\n")
    t = Template.from_stack(RuntimeStack(cdk.App(), "R", env=ENV, user_pool_id="us-east-1_TEST",
                                         intake_client_id="INTAKECLIENT", agent_gateway_url="https://gw/mcp",
                                         code_path=str(tmp_path), opt_in_models=opt_in))
    policy = next(iter(t.find_resources("AWS::IAM::Policy").values()))["Properties"]["PolicyDocument"]
    invoke = next(s for s in policy["Statement"] if "bedrock:InvokeModel" in s["Action"])
    runtime = next(iter(t.find_resources("AWS::BedrockAgentCore::Runtime").values()))["Properties"]
    return json.dumps(invoke["Resource"]), runtime["EnvironmentVariables"]["MODEL_ALLOW_LIST"]


def test_default_allows_only_nova_pro_in_us_east_1(tmp_path):
    arns, allow = _model_arns(tmp_path)
    assert allow == EXTRACTION_MODEL_ID
    assert arns == json.dumps(f"arn:aws:bedrock:us-east-1::foundation-model/{EXTRACTION_MODEL_ID}")


def test_sonnet_opt_in_adds_exactly_its_profile_and_three_regions(tmp_path):
    arns, allow = _model_arns(tmp_path, ("us.anthropic.claude-sonnet-4-6",))
    assert allow == f"{EXTRACTION_MODEL_ID},us.anthropic.claude-sonnet-4-6"
    for region in ("us-east-1", "us-east-2", "us-west-2"):
        assert f"arn:aws:bedrock:{region}::foundation-model/anthropic.claude-sonnet-4-6" in arns
    assert "inference-profile/us.anthropic.claude-sonnet-4-6" in arns and arns.count("arn:aws:bedrock") == 5


def test_an_unlisted_opt_in_is_refused_at_synth(tmp_path):
    (tmp_path / "main.py").write_text("x\n")
    with pytest.raises(ValueError):
        RuntimeStack(cdk.App(), "R", env=ENV, user_pool_id="p", intake_client_id="c", agent_gateway_url="u",
                     code_path=str(tmp_path), opt_in_models=("anthropic.claude-opus-x",))


def test_runtime_rejects_a_model_off_the_allow_list(monkeypatch):
    from prior_auth.agent import runtime_app
    monkeypatch.setenv("MODEL_ID", EXTRACTION_MODEL_ID)
    monkeypatch.setenv("MODEL_ALLOW_LIST", EXTRACTION_MODEL_ID)
    out = runtime_app.invoke({"case_id": "SYN-CASE-CLEAN-1", "model_id": "us.anthropic.claude-sonnet-4-6"})
    assert out == {"outcome": "rejected", "reason": "model is not on the allow-list"}


@pytest.mark.parametrize("model_id", list(MODELS))
def test_sampling_recorded_is_what_the_request_sends(model_id):
    from strands.models import BedrockModel
    from prior_auth.agent.strands_agent import SAMPLING, sampling_sent
    model = BedrockModel(model_id=model_id, region_name="us-east-1", **SAMPLING)
    sent = sampling_sent(model)
    assert sent == {"maxTokens": SAMPLING["max_tokens"], "temperature": SAMPLING["temperature"]}
