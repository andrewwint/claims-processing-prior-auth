import json

import pytest

from infra.names import BUDGET_NAMES, is_project_name
from scripts import deploy, transaction_search
from scripts.verify_teardown import problems

CLEAN = {"lambda function": [], "lambda log group": [], "agentcore gateway": []}


def test_project_names_match_every_convention():
    for name in ["PriorAuthGateways", "prior-auth-agent", "prior_auth_engine", "priorauth-role"]:
        assert is_project_name(name)
    assert not is_project_name("other-gateway")


def test_verifier_passes_on_clean_account():
    assert problems(CLEAN, list(BUDGET_NAMES), True) == []


def test_verifier_fails_on_leftover_resource():
    found = {**CLEAN, "agentcore gateway": ["prior-auth-reviewer"]}
    assert problems(found, list(BUDGET_NAMES), True) == ["leftover agentcore gateway: prior-auth-reviewer"]


def test_verifier_fails_on_leftover_log_group():
    found = {**CLEAN, "lambda log group": ["prior-auth-agent-tools"]}
    assert problems(found, list(BUDGET_NAMES), True) == ["leftover lambda log group: prior-auth-agent-tools"]


def test_verifier_fails_if_a_budget_was_removed():
    assert problems(CLEAN, [BUDGET_NAMES[0]], True) == [f"missing budget: {BUDGET_NAMES[1]}"]


def test_verifier_fails_if_transaction_search_not_restored():
    assert problems(CLEAN, list(BUDGET_NAMES), False) == [
        "transaction search differs from, or has no, recorded pre-project values for this account"
    ]


def test_deploy_refuses_without_budgets():
    with pytest.raises(deploy.BudgetsMissing):
        deploy.require_budgets([BUDGET_NAMES[0]])
    deploy.require_budgets(list(BUDGET_NAMES))


def test_deploy_main_refuses_before_running_cdk(monkeypatch):
    monkeypatch.setattr(deploy, "dirty_paths", lambda: [])
    monkeypatch.setattr(deploy, "head_sha", lambda: "abc")
    monkeypatch.setattr(deploy, "present_budgets", lambda session: [])
    monkeypatch.setattr(deploy, "_stack_exists", lambda name: False)
    monkeypatch.setattr(deploy.subprocess, "run", lambda *a, **k: pytest.fail("cdk must not run"))
    assert deploy.main(["PriorAuthGateways", "-c", "cognito_domain_prefix=x"]) == 1


class FakeXRay:
    def __init__(self, destination, pct):
        self.destination, self.pct = destination, pct

    def can_paginate(self, op):
        return False

    def get_trace_segment_destination(self):
        return {"Destination": self.destination, "Status": "ACTIVE"}

    def get_indexing_rules(self):
        return {"IndexingRules": [{"Name": "Default", "Rule": {"Probabilistic": {"DesiredSamplingPercentage": self.pct}}}]}

    def update_indexing_rule(self, Name, Rule):
        self.pct = Rule["Probabilistic"]["DesiredSamplingPercentage"]

    def update_trace_segment_destination(self, Destination):
        self.destination = Destination


def test_transaction_search_record_restore_roundtrip(tmp_path):
    xray = FakeXRay("XRay", 1.0)
    ev = tmp_path / "evidence.json"
    assert transaction_search.record(xray, "111111111111", tmp_path, ev) == {"destination": "XRay", "indexing_percentage": {"Default": 1.0}}
    with pytest.raises(FileExistsError):
        transaction_search.record(xray, "111111111111", tmp_path, ev)
    xray.destination, xray.pct = "CloudWatchLogs", 100.0
    assert transaction_search.compare(xray, "111111111111", tmp_path)[2] is False
    transaction_search.restore(xray, "111111111111", tmp_path)
    assert (xray.destination, xray.pct) == ("XRay", 1.0)
    assert transaction_search.compare(xray, "111111111111", tmp_path)[2] is True
    assert json.loads(ev.read_text())["destination"] == "XRay"


def test_another_accounts_record_is_never_used(tmp_path):
    xray = FakeXRay("XRay", 1.0)
    transaction_search.record(xray, "111111111111", tmp_path, None)
    assert transaction_search.compare(xray, "222222222222", tmp_path)[2] is False
    with pytest.raises(transaction_search.NoRecord):
        transaction_search.restore(xray, "222222222222", tmp_path)


def test_local_records_are_git_ignored():
    from pathlib import Path
    assert ".local/" in (Path(__file__).resolve().parent.parent / ".gitignore").read_text().split()


def test_teardown_deletes_exact_secret_names_only():
    from scripts.teardown import SECRETS
    from scripts.create_users import USERS
    assert SECRETS == ("prior-auth/agent-client", *(f"prior-auth/users/{u}" for u in USERS))


def test_generated_passwords_meet_policy_and_differ():
    from scripts.create_users import generate_password
    a, b = generate_password(), generate_password()
    assert a != b and len(a) == 24
    assert any(c.isupper() for c in a) and any(c.islower() for c in a) and any(c.isdigit() for c in a)


def test_create_user_stores_password_only_in_secrets_manager(capsys):
    from scripts.create_users import create_user

    calls = []

    class Rec:
        class exceptions:
            class UsernameExistsException(Exception):
                pass

            class ResourceExistsException(Exception):
                pass

        def __getattr__(self, name):
            return lambda **kw: calls.append((name, kw))

    create_user(Rec(), Rec(), "pool", "syn-clinician-1", ["clinician"])
    secret = next(kw for n, kw in calls if n == "create_secret")
    assert secret["Name"] == "prior-auth/users/syn-clinician-1"
    created = next(kw for n, kw in calls if n == "admin_create_user")
    assert created["MessageAction"] == "SUPPRESS"
    assert capsys.readouterr().out == ""


def test_store_agent_secret_never_prints_and_tags_the_secret(capsys):
    from scripts.store_agent_secret import store

    calls = []

    class Cognito:
        def describe_user_pool_client(self, **kw):
            return {"UserPoolClient": {"ClientSecret": "s3cr3t"}}

    class SM:
        class exceptions:
            class ResourceExistsException(Exception):
                pass

        def create_secret(self, **kw):
            calls.append(kw)

    store(Cognito(), SM(), "pool", "client")
    assert calls[0]["Name"] == "prior-auth/agent-client"
    assert calls[0]["Tags"] == [{"Key": "project", "Value": "prior-auth-agentcore"}]
    assert "s3cr3t" not in capsys.readouterr().out


def test_teardown_deletes_only_exact_log_group_names():
    from infra.names import LOG_GROUPS
    assert LOG_GROUPS == ("/aws/lambda/prior-auth-agent-tools", "/aws/lambda/prior-auth-approval-service",
                          "/aws/lambda/prior-auth-reviewer-tools", "/aws/lambda/prior-auth-pre-token")
    import inspect
    from scripts import teardown
    src = inspect.getsource(teardown)
    assert 'found["lambda log group"]' not in src and "for name in LOG_GROUPS" in src


def test_deploy_requires_private_context_for_gateways_and_policies():
    assert deploy.missing_context("PriorAuthGateways", [], {}) == ["cognito_domain_prefix"]
    assert deploy.missing_context("PriorAuthGateways", ["-c", "cognito_domain_prefix=x"], {}) == []
    assert deploy.missing_context("PriorAuthPolicy", [], {"cognito_domain_prefix": "x"}) == [
        "agent_sub", "clinician_tag_shape", "policy_engine_id", "agent_gateway_id", "reviewer_gateway_id"]
    assert deploy.missing_context("PriorAuthGateways", ["-c", "cognito_domain_prefix="], {}) == ["cognito_domain_prefix"]
    assert deploy.missing_context("PriorAuthGateways", [], {"cognito_domain_prefix": ""}) == ["cognito_domain_prefix"]
    assert deploy.missing_context("PriorAuthBudgets", [], {}) == []



# Third security review, finding 5
def test_deploys_are_exclusive():
    assert deploy.cdk_args("PriorAuthPolicy", [])[:3] == ["deploy", "PriorAuthPolicy", "--exclusively"]


def test_redeploying_existing_gateways_without_exact_ids_is_refused():
    saved = {"cognito_domain_prefix": "x"}
    assert deploy.refuses_gateway_revert("PriorAuthGateways", [], saved, stack_exists=True)
    assert not deploy.refuses_gateway_revert("PriorAuthGateways", [], saved, stack_exists=False)
    ids = ["-c", "agent_gateway_id=a", "--context", "reviewer_gateway_id=b"]
    assert not deploy.refuses_gateway_revert("PriorAuthGateways", ids, saved, stack_exists=True)


def test_deploy_fails_cleanly_when_credentials_are_expired(monkeypatch):
    from botocore.exceptions import TokenRetrievalError

    def expired(session):
        raise TokenRetrievalError(provider="sso", error_msg="Token has expired")

    monkeypatch.setattr(deploy, "dirty_paths", lambda: [])
    monkeypatch.setattr(deploy, "head_sha", lambda: "abc")
    monkeypatch.setattr(deploy, "present_budgets", expired)
    monkeypatch.setattr(deploy.subprocess, "run", lambda *a, **k: pytest.fail("cdk must not run"))
    assert deploy.main(["PriorAuthGateways", "-c", "cognito_domain_prefix=x"]) == 1



# Targeted review, E4: deploy-guard bypasses
def test_unknown_or_glob_stack_names_are_refused():
    with pytest.raises(deploy.Refused):
        deploy.check("PriorAuthGate*", [], {"cognito_domain_prefix": "x"}, stack_exists=True)


def test_only_context_flags_count_as_context():
    args = ["--tags", "agent_gateway_id=a", "--parameters", "reviewer_gateway_id=b"]
    assert deploy.cli_context(args) == {}
    assert deploy.refuses_gateway_revert("PriorAuthGateways", args, {"cognito_domain_prefix": "x"}, stack_exists=True)


def test_empty_cli_value_overrides_saved_ids():
    saved = {"cognito_domain_prefix": "x", "agent_gateway_id": "a", "reviewer_gateway_id": "b"}
    assert not deploy.refuses_gateway_revert("PriorAuthGateways", [], saved, stack_exists=True)
    assert deploy.refuses_gateway_revert("PriorAuthGateways", ["-c", "agent_gateway_id="], saved, stack_exists=True)


def test_describe_errors_other_than_missing_stack_refuse(monkeypatch):
    from botocore.exceptions import ClientError

    class CFN:
        def describe_stacks(self, StackName):
            raise ClientError({"Error": {"Code": "AccessDenied", "Message": "denied"}}, "DescribeStacks")

    class S:
        def __init__(self, **kw):
            pass

        def client(self, name):
            return CFN()

    monkeypatch.setattr(deploy.boto3, "Session", S)
    with pytest.raises(ClientError):
        deploy._stack_exists("PriorAuthGateways")


def test_wildcard_trust_is_detected_in_a_template():
    tpl = {"Resources": {"R": {"Type": "AWS::IAM::Role", "Properties": {"AssumeRolePolicyDocument": {"Statement": [
        {"Condition": {"ArnLike": {"aws:SourceArn": "arn:aws:bedrock-agentcore:us-east-1:1:gateway/prior-auth-agent-*"}}}]}}}}}
    assert deploy.wildcard_trust(tpl) == ["R"]
    tpl["Resources"]["R"]["Properties"]["AssumeRolePolicyDocument"]["Statement"][0]["Condition"]["ArnLike"]["aws:SourceArn"] = \
        "arn:aws:bedrock-agentcore:us-east-1:1:gateway/prior-auth-agent-abc123"
    assert deploy.wildcard_trust(tpl) == []



# PM, 2026-10-16: deploys only from a clean tree, with the SHA recorded
def test_deploy_refuses_a_dirty_tree(monkeypatch):
    monkeypatch.setattr(deploy, "dirty_paths", lambda: ["src/prior_auth/decide.py"])
    monkeypatch.setattr(deploy, "present_budgets", lambda session: pytest.fail("no AWS call on a dirty tree"))
    monkeypatch.setattr(deploy.subprocess, "run", lambda *a, **k: pytest.fail("cdk must not run"))
    assert deploy.main(["PriorAuthGateways"]) == 2


def test_deploy_records_the_sha(tmp_path):
    log = tmp_path / "deploys.jsonl"
    deploy.record_deploy("PriorAuthGateways", "abc123", 0, log)
    deploy.record_deploy("PriorAuthPolicy", "abc123", 1, log)
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    assert [(r["stack"], r["sha"], r["result"]) for r in rows] == [
        ("PriorAuthGateways", "abc123", "deployed"), ("PriorAuthPolicy", "abc123", "failed (1)")]
