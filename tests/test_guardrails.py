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
        "transaction search differs from the recorded pre-project values"
    ]


def test_deploy_refuses_without_budgets():
    with pytest.raises(deploy.BudgetsMissing):
        deploy.require_budgets([BUDGET_NAMES[0]])
    deploy.require_budgets(list(BUDGET_NAMES))


def test_deploy_main_refuses_before_running_cdk(monkeypatch):
    monkeypatch.setattr(deploy, "present_budgets", lambda session: [])
    monkeypatch.setattr(deploy.subprocess, "run", lambda *a, **k: pytest.fail("cdk must not run"))
    assert deploy.main(["PriorAuthGateways"]) == 1


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
    path = tmp_path / "ts.json"
    xray = FakeXRay("XRay", 1.0)
    assert transaction_search.record(xray, path) == {"destination": "XRay", "indexing_percentage": {"Default": 1.0}}
    with pytest.raises(FileExistsError):
        transaction_search.record(xray, path)
    xray.destination, xray.pct = "CloudWatchLogs", 100.0
    assert transaction_search.compare(xray, path)[2] is False
    transaction_search.restore(xray, path)
    assert (xray.destination, xray.pct) == ("XRay", 1.0)
    assert transaction_search.compare(xray, path)[2] is True
    assert json.loads(path.read_text())["destination"] == "XRay"


def test_transaction_search_never_recorded_counts_as_unchanged(tmp_path):
    assert transaction_search.compare(FakeXRay("XRay", 1.0), tmp_path / "none.json")[2] is True


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
