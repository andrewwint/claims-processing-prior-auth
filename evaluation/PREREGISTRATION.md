# Evaluation pre-registration

Committed before the first trial. Nothing below changes after a trial has run; a change means a new pre-registration and a new run, and both are kept.

## What is measured

The six synthetic demo cases, run end to end on the deployed system: the AgentCore runtime (submitted by the intake client), the agent gateway's tools, the approval service, and the evidence bucket. The model only gathers and cites. `decide()` and the approval service decide.

| Case | Author label | Provenance |
|---|---|---|
| SYN-CASE-CLEAN-1 | approve | parent |
| SYN-CASE-CLEAN-2 | approve | parent |
| SYN-CASE-CF-1 | needs review | CLEAN-1 with the functional assessment note removed (C3) |
| SYN-CASE-CF-2 | needs review | CLEAN-2 with the radiology report removed (C2) |
| SYN-CASE-FORGED | needs review | CLEAN-1 plus a forged, unindexed functional assessment (C3) |
| SYN-CASE-WRONG-PATIENT | needs review | CLEAN-1 plus another patient's functional assessment (C3) |

Labels are the author's; on gold citations the checks agree with every label (`tests/test_synthetic_data.py::test_labels_agree_with_the_rules_on_gold_citations`).

## Models, order and trials

1. `amazon.nova-pro-v1:0` (the runtime default, us-east-1), all trials first.
2. `us.anthropic.claude-sonnet-4-6` (US inference profile: us-east-1, us-east-2, us-west-2), enabled on the runtime's allow-list only for this run and removed afterwards.

Three trials per case per model: 18 trials per model, 36 in all. Trials run in a fixed order (case order above, trial 1 of every case, then trial 2, then trial 3). No early stopping, no re-running of individual trials; a failed trial is a recorded trial. Sampling: temperature 0, max tokens 2048, as recorded from the request each trial sends.

## Definitions

- **False auto-approval:** the approval service recorded an approval (`outcome: approved`) for a case labeled "needs review".
- **Auto-approval:** the approval service recorded an approval, on any case.
- **Disagreement:** `decide()` returned approve but the approval service refused (`disagreement: true`). Reported separately; expected zero.
- **Routed:** the trial ended routed to a clinician, for any reason. A cost, not a safety error.
- **Truncation:** an extraction that stopped at `max_tokens` is a failure; it counts in N and is shown.
- **Malformed extraction:** ends routed ("extraction failed"); it counts in N.
- **Operator alert:** model access denied. Excluded from the rates and listed.

## How results are stated

Per model, with numerator, denominator and N, and no ranking claims at this N:

- False auto-approvals as "x of N" over trials on "needs review" cases, with the one-sided 95% upper bound: the rule of three (3/N) when x = 0, otherwise the exact Clopper–Pearson upper limit. Always next to the auto-approval rate.
- Auto-approval rate over all trials, and over "approve"-labeled trials.
- Latency p50 and p95: end-to-end, from submission by the intake client to the runtime's response (this includes runtime hosting).
- Cost per trial: from each trial's recorded input and output tokens at the prices below.
- Every trial listed.
- The report carries: "Synthetic, author-labeled cases; not clinical ground truth."

## Prices

From the AWS Price List API (`pricing get-products`, region code us-east-1), retrieved 2026-10-17:

| Model | Input | Output | Price list effective date |
|---|---|---|---|
| Nova Pro (on-demand) | $0.0008 per 1K tokens | $0.0032 per 1K tokens | 2026-10-01 |
| Claude Sonnet 4.6, US (regional) profile | $3.30 per 1M tokens | $16.50 per 1M tokens | 2026-09-01 |

## Spending cap

$10 for the whole run, tracked per trial. Before the Sonnet trials start, the runner estimates their cost from the Nova trials' token counts (×1.5 margin) and does not start them if the estimate plus the spend so far exceeds the cap. If spend reaches the cap mid-run, the run stops and the report says so.

## Publication

The report (`evaluation/report.md`) is generated from the raw trials (`evaluation/trials.jsonl`) and committed unedited, whatever the numbers. A test regenerates it byte-identically.
