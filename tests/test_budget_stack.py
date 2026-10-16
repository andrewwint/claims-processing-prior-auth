import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template

from infra.budget_stack import TIERS_USD, BudgetStack, offset_thresholds

EMAIL = "alerts@example.com"


def _template(baseline=35.12):
    app = cdk.App()
    stack = BudgetStack(app, "B", alert_email=EMAIL, baseline_usd=baseline)
    return Template.from_stack(stack)


def _thresholds(budget):
    return sorted(n["Notification"]["Threshold"] for n in budget["Properties"]["NotificationsWithSubscribers"])


def _by_name(template):
    return {
        b["Properties"]["Budget"]["BudgetName"]: b
        for b in template.find_resources("AWS::Budgets::Budget").values()
    }


def test_tiers_are_20_50_100_500():
    assert TIERS_USD == (20, 50, 100, 500)


def test_offset_thresholds_round_up_over_baseline():
    assert offset_thresholds(35.12) == [56, 86, 136, 536]
    assert offset_thresholds(0) == [20, 50, 100, 500]
    with pytest.raises(ValueError):
        offset_thresholds(-1)


def test_account_budget_uses_offset_thresholds():
    budget = _by_name(_template())["prior-auth-agentcore-account"]
    assert _thresholds(budget) == [56, 86, 136, 536]
    assert "CostFilters" not in budget["Properties"]["Budget"]


def test_project_budget_is_tag_scoped_at_exact_tiers():
    budget = _by_name(_template())["prior-auth-agentcore-project"]
    assert _thresholds(budget) == [20, 50, 100, 500]
    assert budget["Properties"]["Budget"]["CostFilters"] == {
        "TagKeyValue": ["user:project$prior-auth-agentcore"]
    }


def test_every_notification_is_actual_absolute_email():
    template = _template()
    template.resource_count_is("AWS::Budgets::Budget", 2)
    for budget in _by_name(template).values():
        for n in budget["Properties"]["NotificationsWithSubscribers"]:
            assert n["Notification"]["NotificationType"] == "ACTUAL"
            assert n["Notification"]["ThresholdType"] == "ABSOLUTE_VALUE"
            assert n["Subscribers"] == [{"SubscriptionType": "EMAIL", "Address": EMAIL}]
