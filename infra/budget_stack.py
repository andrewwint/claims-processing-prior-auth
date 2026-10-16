"""Budget alerts. Deployed before anything else and kept across teardowns."""

import math

from aws_cdk import Stack, aws_budgets as budgets
from constructs import Construct

TIERS_USD = (20, 50, 100, 500)
PROJECT_TAG_KEY = "project"
PROJECT_TAG_VALUE = "prior-auth-agentcore"


def offset_thresholds(baseline_usd: float, tiers=TIERS_USD) -> list[int]:
    """Account-wide thresholds that fire at the same project spend as each tier.

    The account already has spend this month, so each tier is added to the
    month-to-date baseline recorded at deploy time.
    """
    if baseline_usd < 0:
        raise ValueError("baseline must be non-negative")
    return [math.ceil(baseline_usd + tier) for tier in tiers]


def _budget(scope, construct_id, *, name, thresholds, alert_email, cost_filters=None):
    return budgets.CfnBudget(
        scope,
        construct_id,
        budget=budgets.CfnBudget.BudgetDataProperty(
            budget_name=name,
            budget_type="COST",
            time_unit="MONTHLY",
            budget_limit=budgets.CfnBudget.SpendProperty(amount=thresholds[-1], unit="USD"),
            cost_filters=cost_filters,
        ),
        notifications_with_subscribers=[
            budgets.CfnBudget.NotificationWithSubscribersProperty(
                notification=budgets.CfnBudget.NotificationProperty(
                    notification_type="ACTUAL",
                    comparison_operator="GREATER_THAN",
                    threshold=threshold,
                    threshold_type="ABSOLUTE_VALUE",
                ),
                subscribers=[
                    budgets.CfnBudget.SubscriberProperty(subscription_type="EMAIL", address=alert_email)
                ],
            )
            for threshold in thresholds
        ],
    )


class BudgetStack(Stack):
    """Two budgets with the same tiers.

    - account: account-wide, thresholds offset by the month-to-date baseline.
      It works from the moment it is deployed.
    - project: filtered on the project cost-allocation tag at the exact tiers.
      It sees spend only once the tag is active in billing.
    """

    def __init__(self, scope: Construct, construct_id: str, *, alert_email: str, baseline_usd: float, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        _budget(
            self,
            "AccountBudget",
            name=f"{PROJECT_TAG_VALUE}-account",
            thresholds=offset_thresholds(baseline_usd),
            alert_email=alert_email,
        )
        _budget(
            self,
            "ProjectBudget",
            name=f"{PROJECT_TAG_VALUE}-project",
            thresholds=list(TIERS_USD),
            alert_email=alert_email,
            cost_filters={"TagKeyValue": [f"user:{PROJECT_TAG_KEY}${PROJECT_TAG_VALUE}"]},
        )
