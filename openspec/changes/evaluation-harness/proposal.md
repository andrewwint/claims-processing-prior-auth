# Proposal

## Why

The article commits to measuring how often the system approves a case it should have routed, and to publishing that number whatever it is. This runs **after Monday's demo**, and the article is published only after these rows are green (PM, 2026-10-16).

## What Changes

- **Six synthetic cases**, each with its provenance: 2 clean, 2 one-note-removed counterfactuals, 1 wrong patient, 1 forged document.
- **Two models** (Nova Pro, the default; Sonnet 4.6, the opt-in) × 3 trials each = 36 trials. They run through the real agent code against the deployed gateways, with Policy enforced.
- **A one-page report**, per model:
  - false auto-approvals as "x of N" with the rule-of-three upper bound (about 3/N when x = 0)
  - the auto-approval rate
  - latency p50 and p95
  - cost per case
  - every trial listed
  - the cases labeled synthetic and author-labeled
- **Pre-registration** committed before the run.

**Deferred:** wrong-plan cases, larger N, and further change types.

## Claims delivered

M1–M8. The false-approval rate is measured on the "needs review" trials only: 4 cases × 3 trials = 12 per model. A zero result therefore bounds at about 25% (3/12), and the report says so in those words.

## Capabilities

### New Capabilities

- `evaluation-harness`: how the false auto-approval rate is measured and reported.

### Modified Capabilities

None.

## Impact

- **New code:** `evaluation/` and tests.
- **AWS usage:** model and gateway calls only.
- **Depends on** `case-packet-and-failure-routing`.
