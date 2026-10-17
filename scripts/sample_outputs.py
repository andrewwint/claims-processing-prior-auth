"""Build SAMPLE_OUTPUTS.md: a reviewer's view of real runs, one section per demo beat.

Every sample is read from a committed, redacted evidence file (named next to it);
nothing is typed by hand, and chart values come from the synthetic chart store.
Deterministic: a test regenerates the page and compares it byte for byte.

Usage: python -m scripts.sample_outputs
"""

import json
import re
import sys
from pathlib import Path

from prior_auth import stores
from scripts.redact import find_unredacted, redact

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "SAMPLE_OUTPUTS.md"
E = "evidence/2026-10-16"
SOURCES = {
    "tools": f"{E}/boundary-smoke-2028d6b66d71.json",
    "beats23": f"{E}/beats-2-and-3.json",
    "layer1": f"{E}/d1/calls.json",
    "layer2": f"{E}/d1/b4-layer2-agent-call.json",
    "beat5": f"{E}/beat5-clinician-decision.json",
    "chain": f"{E}/chain-clinician-denial-cf-1.json",
    "control": f"{E}/canary-scan-control.json",
    "clean": f"{E}/canary-scan-clean.json",
    "report": "evaluation/report.md",
}
POLICY_SUFFIX = re.compile(r"(prior_auth_[a-z_]+)-[a-z0-9]{10}\b")


def _load(key: str):
    return json.loads((ROOT / SOURCES[key]).read_text())


def _src(key: str) -> str:
    return f"<sub>Source: [`{SOURCES[key]}`]({SOURCES[key]})</sub>"


def _line(doc_id: str, page: int, line: int) -> str:
    return stores.document(doc_id)["pages"][page - 1][line - 1]


def _block(text: str, lang: str = "") -> list[str]:
    return [f"```{lang}", text, "```"]


def beat1() -> list[str]:
    checks = _load("tools")["checks"]
    agent = checks["agent_tools_list"]["live"]["tools"]
    reviewer = checks["reviewer_tools_list_clinician"]["live"]["tools"]
    return ["## 1. Two gateways, side by side", "",
            "`python -m scripts.demo --redact 1`: each gateway's `tools/list`, under the agent's and a clinician's token.", "",
            *_block("Agent gateway (agent identity):\n" + "\n".join(f"   {t}" for t in agent)
                    + "\nReviewer gateway (clinician identity):\n" + "\n".join(f"   {t}" for t in reviewer)),
            "", "The agent's gateway has no denial tool. " + _src("tools"), ""]


def beat2() -> list[str]:
    beat = _load("beats23")["beats"]["beat2"]
    rows = [f"| {c} | `{d}` p{p} l{n} | {_line(d, p, n)} |" for c, d, p, n in beat["stored_packet"]["citations"]]
    return ["## 2. Clean case: a cited packet, approved", "",
            f"`{beat['case_id']}` → **{beat['response']['outcome']}**. The model returned citations only; the values "
            "are filled by code from the trusted chart, then the approval service re-ran every check on the stored "
            "packet before recording the approval.", "",
            "| Criterion | Citation | Value (from the chart store) |", "|---|---|---|", *rows, "",
            f"Stored packet: SSE `{beat['stored_packet']['sse']}`, Object Lock `{beat['stored_packet']['object_lock_mode']}`, "
            f"sha256 `{beat['stored_packet']['sha256'][:16]}…`. " + _src("beats23"), ""]


def beat3() -> list[str]:
    r = _load("beats23")["beats"]["beat3"]["response"]
    return ["## 3. One note removed: routed, gap marked", "",
            *_block(json.dumps({k: r[k] for k in ("outcome", "reason", "gaps")}, indent=2), "json"), "",
            "`SYN-CASE-CF-1` is `SYN-CASE-CLEAN-1` with the functional assessment removed. Nothing is denied; "
            "the case goes to a clinician with C3 marked. " + _src("beats23"), ""]


def beat4() -> list[str]:
    layer1 = _load("layer1")["B4_layer1_agent_token_on_reviewer"]
    layer2 = _load("layer2")
    msg2 = POLICY_SUFFIX.sub(r"\1", layer2["body"]["error"]["message"])
    return ["## 4. The agent refused at the reviewer gateway", "",
            "Layer 1, the gateway's authorizer (the agent's token is not a clinician client):", "",
            *_block(f"HTTP {layer1['http_status']}  {layer1['body']['error']['message']}"), "",
            "Layer 2, Cedar (recorded under a temporary test configuration that let the agent's token past layer 1, "
            "then reverted):", "",
            *_block(f"HTTP {layer2['http_status']}  JSON-RPC {layer2['body']['error']['code']}  {msg2}"), "",
            _src("layer1") + " · " + _src("layer2"), ""]


def beat5() -> list[str]:
    rec = _load("beat5")
    calls = rec["calls"]
    order = ["whitespace_reason_refused_by_lambda", "agent_token_refused_at_authorizer",
             "decision_on_another_run_refused", "clinician_denial_recorded", "second_decision_refused_write_once"]
    rows = []
    for k in order:
        r = calls[k]["result"]
        what = "recorded" if r.get("recorded") else "refused: " + "; ".join(r.get("reasons", []))
        rows.append(f"| {k.replace('_', ' ')} | {calls[k]['http_status']} | {what} |")
    chain = _load("chain")
    checks = "\n".join(f"  {'ok ' if v else 'FAIL'} {k}" for k, v in chain["checks"].items())
    return ["## 5. A clinician decides; the record chains", "",
            "The same denial tool, through the reviewer gateway, under a clinician's token (scripted sign-in; the "
            "workbench page calls the same tool after a hosted-UI sign-in):", "",
            "| Call | HTTP | Result |", "|---|---|---|", *rows, "",
            "`python -m scripts.verify_chain <case> <run>`: every hash recomputed from the stored bytes.", "",
            *_block(f"decision {chain['decision']} -> recommendation -> runtime span, decision -> trace segment\n"
                    f"{checks}\nverified: {chain['verified']}"), "",
            _src("beat5") + " · " + _src("chain"), ""]


def beat6() -> list[str]:
    control, clean = _load("control"), _load("clean")
    planted = sorted(control["scan"]["hits"])
    n = clean["needles"]
    events = sum(clean["scan"]["events_scanned"].values())
    return ["## 6. A trace with no chart text", "",
            "Positive control first: a control token was planted through the runtime (one span attribute, one log "
            "line, through a test-only path since removed) and written as a line into each Lambda log group. The "
            f"scan found it in every place it was planted: {', '.join(f'`{s}`' for s in planted)}.", "",
            f"Clean run: all six cases, each routed case decided by a clinician, then a scan of {events:,} events "
            f"for {n['canaries']} chart canaries, {n['chart_lines']} chart lines and {n['decision_reasons']} decision "
            f"reasons: **{len(clean['scan']['hits'])} hits**.", "",
            "| Sink | Events scanned |", "|---|---|",
            *[f"| `{k}` | {v} |" for k, v in clean["scan"]["events_scanned"].items()], "",
            _src("control") + " · " + _src("clean"), ""]


def harness() -> list[str]:
    report = (ROOT / SOURCES["report"]).read_text().splitlines()
    headline = [l for l in report if l.startswith("**`")]
    return ["## 7. The harness", "",
            "Pre-registered ([evaluation/PREREGISTRATION.md](evaluation/PREREGISTRATION.md)); six synthetic cases, "
            "three trials per model, on the deployed system.", "", *headline, "",
            "Every trial, and the cause of each approvable trial that was routed: "
            "[evaluation/report.md](evaluation/report.md).", ""]


def render() -> str:
    lines = ["# Sample outputs", "",
             "Real runs on the deployed system, with synthetic data only. Each sample is generated from a committed, "
             "redacted evidence file named beside it (`python -m scripts.sample_outputs`); account IDs, ARNs, "
             "gateway URLs, client IDs and tokens are masked.", "",
             "> **Reproducibility.** The boundary results (tool lists, refusals, Cedar denials, write-once, the "
             "chain checks) are deterministic. The model's citations are not, even at temperature 0: in the harness, "
             "one of six Nova Pro trials on an approvable case cited lines that do not exist and was routed to a "
             "clinician instead of approved. A different run can cite differently; it cannot approve without "
             "passing every check.", "",
             "1. [Two gateways, side by side](#1-two-gateways-side-by-side)",
             "2. [Clean case: a cited packet, approved](#2-clean-case-a-cited-packet-approved)",
             "3. [One note removed: routed, gap marked](#3-one-note-removed-routed-gap-marked)",
             "4. [The agent refused at the reviewer gateway](#4-the-agent-refused-at-the-reviewer-gateway)",
             "5. [A clinician decides; the record chains](#5-a-clinician-decides-the-record-chains)",
             "6. [A trace with no chart text](#6-a-trace-with-no-chart-text)",
             "7. [The harness](#7-the-harness)", ""]
    for section in (beat1, beat2, beat3, beat4, beat5, beat6, harness):
        lines += section()
    return redact("\n".join(lines).rstrip() + "\n")


def main() -> int:
    text = render()
    leaks = find_unredacted(text)
    if leaks:
        print(f"refusing: unredacted identifiers {leaks}", file=sys.stderr)
        return 1
    OUT.write_text(text)
    print("->", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
