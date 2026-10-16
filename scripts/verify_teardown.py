"""Fail if any project resource remains, if a budget is gone, or if
account-wide settings differ from what was recorded before the project."""

import sys

import boto3
from botocore.exceptions import ClientError

from infra.names import BUDGET_NAMES
from scripts import inventory, transaction_search


def problems(found: dict[str, list[str]], budgets: list[str], ts_matches: bool) -> list[str]:
    out = [f"leftover {kind}: {name}" for kind, names in sorted(found.items()) for name in names]
    out += [f"missing budget: {b}" for b in BUDGET_NAMES if b not in budgets]
    if not ts_matches:
        out.append("transaction search differs from the recorded pre-project values")
    return out


def main() -> int:
    session = boto3.Session(region_name="us-east-1")
    try:
        found = inventory.inventory(session)
        budgets = inventory.present_budgets(session)
        recorded, now, matches = transaction_search.compare(session.client("xray"))
    except ClientError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    print(f"transaction search recorded: {recorded}")
    print(f"transaction search now:      {now}")
    print(f"budgets present: {budgets}")
    found_problems = problems(found, budgets, matches)
    for p in found_problems:
        print(p)
    print("VERIFY: FAIL" if found_problems else "VERIFY: PASS")
    return 1 if found_problems else 0


if __name__ == "__main__":
    sys.exit(main())
