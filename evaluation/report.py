"""Build the one-page harness report from the raw trials (evaluation/PREREGISTRATION.md).

Deterministic: the same trials.jsonl always produces the same report.md, byte for byte.

Usage: python -m evaluation.report
"""

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TRIALS, REPORT, ANNOTATIONS = HERE / "trials.jsonl", HERE / "report.md", HERE / "annotations.json"
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
    for m in models:
        s = summarize([t for t in trials if t["model_id"] == m])
        lines += [
            f"**`{m}`.** False auto-approvals: {s['false_auto']} of {s['n_review']} trials on needs-review cases, "
            f"with a 95% upper bound of {pct(s['bound'])} "
            f"({'rule of three' if s['false_auto'] == 0 else 'exact Clopper-Pearson'}). "
            f"Auto-approvals: {s['auto_on_approve']} of {s['n_approve']} trials on approvable cases, and "
            f"{s['auto']} of {s['n']} ({pct(s['auto'] / s['n']) if s['n'] else 'n/a'}) overall; the overall figure "
            f"reflects the test mix, in which {len({t['case_id'] for t in trials if t['label'] == 'approve'})} of "
            f"{len({t['case_id'] for t in trials})} cases are approvable.", ""]
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
    notes = annotations()
    review = [t for t in trials if t["label"] == "needs review" and t["outcome"] == "routed" and t.get("run_id") in notes]
    if review:
        lines += ["", "## Did the designed check fire?", "",
                  "For every routed needs-review trial: the check each case was built to trigger, and whether it fired. "
                  "Reconstructed from each run's stored recommendation record, not re-run ([annotate.py](annotate.py)).", "",
                  "| Model | Case | Trial | Built to trigger | Fired | Other failures |", "|---|---|---|---|---|---|"]
        for t in review:
            note = notes[t["run_id"]]
            change = CASE_CHANGES.get(t["case_id"], {})
            fired = designed_check_fired(change, note)
            other = [f for f in plain_failures(note) if DESIGNED.get(change.get("type"), "\0") not in f]
            lines.append(f"| `{t['model_id']}` | {t['case_id']} | {t['trial']} | {describe(change)} | "
                         f"{'yes' if fired else 'no'} | {'; '.join(other) if other else 'none'} |")
    approvable = [t for t in trials if t["label"] == "approve" and t["outcome"] != "approved" and t.get("run_id") in notes]
    if approvable:
        lines += ["", "## Approvable trials that were routed", "",
                  "Not re-run. The cause is reconstructed from each run's stored recommendation record: its "
                  "citations are re-checked against the trusted chart ([annotate.py](annotate.py)).", ""]
        for t in approvable:
            note = notes[t["run_id"]]
            cites = "; ".join(
                f"{c['criterion_id']} cited {c['doc_id']} page {c['page']} line {c['line']}"
                + ("" if c.get("cited_line_exists", True) else f" (no such line: the document has "
                   f"{c.get('document_pages')} page{'s' if c.get('document_pages') != 1 else ''})")
                for c in note.get("citations", []))
            lines.append(f"- `{t['model_id']}` {t['case_id']} trial {t['trial']}: {cites}. "
                         f"Checks: {'; '.join(plain_failures(note))}. Routed to a clinician; nothing was approved.")
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


def annotations(path: Path = None) -> dict:
    path = path or ANNOTATIONS
    return json.loads(path.read_text()) if path.exists() else {}


# The check each needs-review case was built to trigger (data/cases/cases.json provenance).
DESIGNED = {"forge_unindexed_doc": "is not in the chart index", "other_patient_doc": "belongs to another patient"}


def _case_changes() -> dict:
    cases = json.loads((HERE.parent / "data" / "cases" / "cases.json").read_text())["cases"]
    return {cid: (c.get("provenance") or {}).get("change") or {} for cid, c in cases.items()}


CASE_CHANGES = _case_changes()


def describe(change: dict) -> str:
    if change.get("type") == "remove_evidence":
        return f"{change['criterion']} Not found (evidence removed)"
    if change.get("type") == "forge_unindexed_doc":
        return "same patient: forged document not in the chart index"
    if change.get("type") == "other_patient_doc":
        return "same patient: another patient's document"
    return "n/a"


def plain_failures(note: dict) -> list[str]:
    """The check failures, with citations to pages that do not exist stated as such (the source-match
    check reports them as values shorter than its minimum, because the filled value is empty)."""
    missing = [c["criterion_id"] for c in note.get("citations", []) if not c.get("cited_line_exists", True)]
    out = [f for f in note.get("check_failures", [])
           if not any(f == f"source match: value for {cid} is shorter than 4 characters" for cid in missing)]
    if missing:
        out.append(f"{', '.join(missing)} cited pages that do not exist, so source match refused them")
    return out


def designed_check_fired(change: dict, note: dict) -> bool:
    if change.get("type") == "remove_evidence":
        return change["criterion"] in (note.get("gaps") or [])
    return any(DESIGNED.get(change.get("type"), "\0") in f for f in note.get("check_failures", []))


def load(path: Path = TRIALS) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> int:
    REPORT.write_text(render(load()))
    print("->", REPORT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
