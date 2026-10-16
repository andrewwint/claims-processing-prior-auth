# Proposal

## Why

Once the agent cannot deny, its only safety error is approving a case a clinician would not have approved. The article commits to measuring that, the false auto-approval rate, on counterfactual cases, and to publishing the number whatever it is. It is priority 5.

## What Changes

- **Pre-registration** (`harness/PREREGISTRATION.md`), committed before the first run. It covers the questions, the case set, the candidate models, trials per case, the metric definitions, the scoring rules and the stopping rules.
- **Counterfactual cases.** For each approvable synthetic case, one variant per removable piece of required evidence, with everything else fixed. Each case records its parent and the removed element. Labels are author-assigned and stated as such.
- **Model access check.** One real call to every candidate before the run, recording access, the parameters it accepts, and lifecycle status with source and date.
- **Runner.** Runs the real agent code in-process against the deployed gateways (policy enforced) and real model calls. Each case runs several times per model. Every trial is recorded with its sampling settings as sent.
- **Report.** Shows:
  - the false auto-approval rate and the auto-approval rate, with N next to every number
  - every trial
  - truncation counted as a failure
  - the cases labeled synthetic and author-labeled

  It is regenerated from raw trials and published unedited.

## Claims delivered

M1–M8.

## Capabilities

### New Capabilities

- `evaluation-harness`: how the false auto-approval rate is measured and reported.

### Modified Capabilities

None.

## Impact

- **New code:** `harness/` and tests.
- **AWS usage:** model calls only, under the budget.
- **Depends on** `case-packet-and-failure-routing` and `gateway-and-policy`.
