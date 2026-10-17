"""Run the pre-registered harness on the deployed runtime (evaluation/PREREGISTRATION.md).

Each trial is submitted by the intake client, in its own session, naming the model;
the runtime enforces its allow-list. Every trial is appended to trials.jsonl as it
finishes (no re-runs, no early stopping), with its outcome, stop reason, sampling as
sent, token usage and end-to-end seconds. Spend is tracked per trial against the cap.

Usage: python -m evaluation.run <model_id>
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3

from evaluation.report import PRICES, TRIALS, cost, load
from prior_auth import stores
from prior_auth.agent.pipeline import session_id_for
from scripts import gateway_client as gc
from scripts.intake import intake_token, invoke_payload

CAP_USD = 10.0
TRIALS_PER_CASE = 3
MARGIN = 1.5


def spent() -> float:
    return sum(cost(t) for t in load()) if TRIALS.exists() else 0.0


def estimate(model_id: str) -> float:
    """The planned trials' cost, from the recorded trials' mean token counts (x margin)."""
    done = load() if TRIALS.exists() else []
    if not done:
        return 0.0
    mean_in = sum((t.get("usage") or {}).get("input_tokens", 0) for t in done) / len(done)
    mean_out = sum((t.get("usage") or {}).get("output_tokens", 0) for t in done) / len(done)
    cin, cout = PRICES[model_id]
    return MARGIN * len(stores.cases()) * TRIALS_PER_CASE * (mean_in / 1000 * cin + mean_out / 1000 * cout)


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in PRICES:
        print(__doc__, file=sys.stderr)
        return 2
    model_id = sys.argv[1]
    if TRIALS.exists() and any(t["model_id"] == model_id for t in load()):
        print(f"refusing: {model_id} already has recorded trials (no re-runs)", file=sys.stderr)
        return 1
    projected = spent() + estimate(model_id)
    print(f"spent so far ${spent():.4f}; projected with {model_id} ${projected:.4f}; cap ${CAP_USD:.2f}")
    if projected > CAP_USD:
        print("refusing: the estimate exceeds the cap", file=sys.stderr)
        return 1
    session = boto3.Session(region_name="us-east-1")
    out = gc.outputs()
    runtime_arn = json.loads(Path(".local/runtime.json").read_text())["arn"]
    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    cases = stores.cases()
    for trial in range(1, TRIALS_PER_CASE + 1):
        for case_id, case in cases.items():
            if spent() >= CAP_USD:
                print("stopping: the spending cap is reached", file=sys.stderr)
                return 1
            token = intake_token(out, session)
            start = time.monotonic()
            try:
                result = invoke_payload({"case_id": case_id, "model_id": model_id}, runtime_arn, token,
                                        session_id_for(case_id))
            except Exception as e:  # a failed trial is a recorded trial
                result = {"outcome": "error", "reason": type(e).__name__}
            seconds = time.monotonic() - start
            extraction = result.get("extraction") or {}
            row = {"model_id": model_id, "case_id": case_id, "label": case["label"], "trial": trial,
                   "outcome": result.get("outcome"), "reason": result.get("reason"), "gaps": result.get("gaps"),
                   "disagreement": result.get("disagreement", False), "run_id": result.get("run_id"),
                   "stop_reason": extraction.get("stop_reason"), "sampling": extraction.get("sampling"),
                   "usage": extraction.get("usage"), "reported_model_id": extraction.get("model_id"),
                   "seconds": round(seconds, 2), "sha": sha,
                   "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            with TRIALS.open("a") as f:
                f.write(json.dumps(row, sort_keys=True) + "\n")
            print(f"{model_id} {case_id} trial {trial}: {row['outcome']} ({seconds:.1f}s, ${cost(row):.4f})")
    print(f"spent ${spent():.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
