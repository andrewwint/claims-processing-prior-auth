"""Record the month-to-date baseline and the deployed budgets as evidence."""

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from scripts.redact import find_unredacted, redact

BUDGET_PREFIX = "prior-auth-agentcore-"


def month_to_date_usd(ce, today: date) -> float:
    start = today.replace(day=1)
    end = today + timedelta(days=1)
    resp = ce.get_cost_and_usage(
        TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
    )
    return round(sum(float(r["Total"]["UnblendedCost"]["Amount"]) for r in resp["ResultsByTime"]), 2)


def project_budgets(client, account_id: str) -> list[dict]:
    found = []
    for page in client.get_paginator("describe_budgets").paginate(AccountId=account_id):
        found += [b for b in page.get("Budgets", []) if b["BudgetName"].startswith(BUDGET_PREFIX)]
    for b in found:
        b["Notifications"] = client.describe_notifications_for_budget(
            AccountId=account_id, BudgetName=b["BudgetName"]
        )["Notifications"]
    return found


def write(path: Path, payload) -> None:
    text = redact(json.dumps(payload, indent=2, sort_keys=True, default=str))
    leftovers = find_unredacted(text)
    if leftovers:
        raise RuntimeError(f"unredacted identifiers in {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("what", choices=["baseline", "budgets"])
    parser.add_argument("--out", default=f"evidence/{date.today().isoformat()}")
    args = parser.parse_args()
    session = boto3.Session(region_name="us-east-1")
    out = Path(args.out)
    try:
        if args.what == "baseline":
            usd = month_to_date_usd(session.client("ce"), date.today())
            write(out / "budget-baseline.json", {"as_of": date.today().isoformat(), "month_to_date_usd": usd})
            print(usd)
        else:
            account_id = session.client("sts").get_caller_identity()["Account"]
            budgets = project_budgets(session.client("budgets"), account_id)
            write(out / "describe-budgets.json", budgets)
            print(f"{len(budgets)} project budgets recorded")
        return 0
    except ClientError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
