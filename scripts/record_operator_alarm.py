"""Record F4's alarm state change: publish the operator metric exactly as the runtime does on a
model access-denied (prior_auth.agent.operator), then record the alarm going to ALARM and back.
This exercises the metric path; the access-denied branch itself is covered by a test.

Usage: python -m scripts.record_operator_alarm
"""

import json
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import boto3

from infra.names import EXTRACTION_MODEL_ID
from prior_auth.agent import operator

ALARM = "prior-auth-model-access-denied"


def state(cw) -> str:
    return cw.describe_alarms(AlarmNames=[ALARM])["MetricAlarms"][0]["StateValue"]


def wait_for(cw, wanted: str, seconds: int) -> str:
    deadline = time.time() + seconds
    while (now := state(cw)) != wanted and time.time() < deadline:
        time.sleep(20)
    return now


def main() -> int:
    cw = boto3.client("cloudwatch", region_name="us-east-1")
    start = datetime.now(timezone.utc)
    before = state(cw)
    operator.emit_model_access_denied(cw, EXTRACTION_MODEL_ID)
    fired = wait_for(cw, "ALARM", 300)
    cleared = wait_for(cw, "OK", 600) if fired == "ALARM" else state(cw)
    history = [{"at": h["Timestamp"].isoformat(), "summary": h["HistorySummary"]}
               for h in cw.describe_alarm_history(AlarmName=ALARM, HistoryItemType="StateUpdate",
                                                  StartDate=start)["AlarmHistoryItems"]]
    record = {"date": date.today().isoformat(),
              "sha": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
              "alarm": ALARM, "method": "operator.emit_model_access_denied, as the runtime calls it",
              "state_before": before, "state_after_emit": fired, "state_after_quiet": cleared,
              "history": sorted(history, key=lambda h: h["at"]),
              "passed": before == "OK" and fired == "ALARM" and cleared == "OK"}
    path = Path(f"evidence/{record['date']}/operator-alarm-state-change.json")
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps(record, indent=2))
    return 0 if record["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
