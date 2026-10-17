"""Build the one-page harness report from the raw trials (evaluation/PREREGISTRATION.md).

Deterministic: the same trials.jsonl always produces the same report.md, byte for byte.

Usage: python -m evaluation.report
"""

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TRIALS, REPORT = HERE / "trials.jsonl", HERE / "report.md"
LABEL = "Synthetic, author-labeled cases; not clinical ground truth."
# Per 1K tokens (input, output), from the pre-registration.
PRICES = {"amazon.nova-pro-v1:0": (0.0008, 0.0032), "us.anthropic.claude-sonnet-4-6": (0.0033, 0.0165)}


def binom_cdf(x: int, n: int, p: float) -> float:
    return sum(math.comb(n, k) * p ** k * (1 - p) ** (n - k) for k in range(x + 1))


def upper_bound(x: int, n: int) -> float:
    """One-sided 95% upper bound: rule of three at x = 0, else exact Clopper-Pearson."""
    if n == 0:
        return 1.0
    if x == 0:
        return min(1.0, 3 / n)
    if x == n:
        return 1.0
    lo, hi = x / n, 1.0
    for _ in range(100):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if binom_cdf(x, n, mid) > 0.05 else (lo, mid)
    return hi


def cost(trial: dict) -> float:
    usage = trial.get("usage") or {}
    cin, cout = PRICES[trial["model_id"]]
    return usage.get("input_tokens", 0) / 1000 * cin + usage.get("output_tokens", 0) / 1000 * cout


def percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)] if ordered else float("nan")


def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def summarize(trials: list[dict]) -> dict:
    counted = [t for t in trials if t["outcome"] != "operator_alert"]
    review = [t for t in counted if t["label"] == "needs review"]
    approve = [t for t in counted if t["label"] == "approve"]
    false_auto = sum(t["outcome"] == "approved" for t in review)
    return {
        "n": len(counted), "excluded": len(trials) - len(counted),
        "false_auto": false_auto, "n_review": len(review), "bound": upper_bound(false_auto, len(review)),
        "auto": sum(t["outcome"] == "approved" for t in counted),
        "auto_on_approve": sum(t["outcome"] == "approved" for t in approve), "n_approve": len(approve),
        "disagreements": sum(bool(t.get("disagreement")) for t in counted),
        "truncated": sum(t.get("stop_reason") == "max_tokens" for t in counted),
        "p50": percentile([t["seconds"] for t in counted], 0.5), "p95": percentile([t["seconds"] for t in counted], 0.95),
        "cost_per_trial": sum(cost(t) for t in counted) / len(counted) if counted else 0.0,
        "cost_total": sum(cost(t) for t in trials),
    }


def render(trials: list[dict]) -> str:
    lines = ["# Harness report", "", f"**{LABEL}**", "",
             "Six synthetic cases, three trials each per model, run end to end on the deployed system "
             "(runtime, gateways, approval service). Definitions, prices and wording: "
             "[PREREGISTRATION.md](PREREGISTRATION.md). No ranking claims are made at this N.", ""]
    models = list(dict.fromkeys(t["model_id"] for t in trials))
    lines += ["| Model | False auto-approvals | Auto-approval rate | Auto-approvals on approve-labeled cases | "
              "Disagreements | Truncated | Latency p50 / p95 | Cost per trial |",
              "|---|---|---|---|---|---|---|---|"]
    for m in models:
        s = summarize([t for t in trials if t["model_id"] == m])
        lines.append(
            f"| `{m}` | {s['false_auto']} of {s['n_review']} (95% upper bound {pct(s['bound'])}) | "
            f"{s['auto']} of {s['n']} ({pct(s['auto'] / s['n']) if s['n'] else 'n/a'}) | "
            f"{s['auto_on_approve']} of {s['n_approve']} | {s['disagreements']} | {s['truncated']} | "
            f"{s['p50']:.1f} s / {s['p95']:.1f} s | ${s['cost_per_trial']:.4f} |")
    excluded = [t for t in trials if t["outcome"] == "operator_alert"]
    lines += ["", f"Operator-alert trials excluded from the rates: {len(excluded)}.",
              f"Total model cost of the run: ${sum(cost(t) for t in trials):.4f}.", "",
              "## Every trial", "",
              "| # | Model | Case | Label | Trial | Outcome | Reason | Gaps | Stop reason | Sampling sent | "
              "Tokens in / out | Seconds |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, t in enumerate(trials, start=1):
        usage = t.get("usage") or {}
        lines.append(
            f"| {i} | `{t['model_id']}` | {t['case_id']} | {t['label']} | {t['trial']} | {t['outcome']} | "
            f"{t.get('reason') or ''} | {', '.join(t.get('gaps') or [])} | {t.get('stop_reason') or ''} | "
            f"{json.dumps(t.get('sampling') or {}, sort_keys=True)} | "
            f"{usage.get('input_tokens', '')} / {usage.get('output_tokens', '')} | {t['seconds']:.1f} |")
    return "\n".join(lines) + "\n"


def load(path: Path = TRIALS) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> int:
    REPORT.write_text(render(load()))
    print("->", REPORT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
