# Proposal

## Why

The agent has to hand a reviewer a case where every claim points at its source. A failure must slow a case down without ever pushing it toward denial, and an approval must not depend on anything the agent or the model says about the case. This change:

- turns the tool stubs into a working pipeline that builds a cited packet
- moves the approve-or-route decision into code that the model cannot reach
- makes the approval service rebuild its verdict from trusted sources only

It is priority 2.

## What Changes

- **Trusted sources.** Three sources are written only by trusted parties, and they are the only inputs to a decision:
  - **Request records** in the case store, written by the intake client: case, payer, CPT and patient.
  - **Compiled policy criteria**, bundled with the code.
  - **The chart store and its index**: documents, plus the patient that owns each `doc_id`. Seeded by the operator.
- **One checks module, `checks/`.** It is imported by both the runtime and the approval service, and it holds:
  - check 1: schema
  - check 2: exact source match, at the cited line
  - check 3: the cited text satisfies the criterion's compiled evidence rule
  - check 4: the same patient, derived from the chart index
  - `recompute()`, which rebuilds every criterion's status from trusted sources
- **The decision is a code function.** `decide(packet)` returns approve or route. It calls `checks.recompute()`, and the runtime wrapper acts on its result.
  - The model has no tools: it cannot call `record_approval` or `route_to_reviewer`.
  - The model's prose is labeled a model summary, and no decision reads it.
- **The approval service never trusts the packet.**
  - It loads the stored packet and verifies the hash. The hash proves integrity, not truth.
  - It then rebuilds the verdict: criteria come from the compiled policy for the request's (payer, CPT); each finding is re-verified against the chart, value at its cited location; the patient is derived from the chart index.
  - Status labels and the `patient_id` in the packet are ignored.
  - A forged packet marked all Met, with made-up findings and a valid hash, is refused.
- **Session invariant.** Every session ends in exactly one terminal outcome: `approved`, `routed` or `operator_alert`. A session that ends without one becomes `needs_review` and is routed.
- **Per-step empty-output table.** This replaces a global wrapper rule. Each row gets one test.
- **Failure routing.** Each row of the article's failure table, with access-denied alerting an operator through an SNS topic. The topic's email subscription is confirmed before the alarm test.
- **Agent runtime.**
  - A Strands agent on AgentCore Runtime: HTTP protocol, a JWT authorizer that admits only the intake client, and one session per case.
  - A post-deploy step requires metadata service v2.
  - Telemetry content redaction is on from the first deploy.
- **Extraction model (PM, 2026-10-16):**
  - **Runtime default:** Amazon Nova Pro (`amazon.nova-pro-v1:0`), on demand in us-east-1 only. "Regions pinned" holds by default.
  - **Opt-in:** Claude Sonnet 4.6 (`anthropic.claude-sonnet-4-6`), through `us.anthropic.claude-sonnet-4-6` (us-east-1, us-east-2, us-west-2). It is a documented, recorded opt-in, exercised in the harness. It is sent temperature only, since it rejects `temperature` together with `topP`.
  - Both access calls were recorded before any build (evidence `2026-10-16/model-access-extraction.json`).
- **Compiled evidence rules (second security review, X1).** Each compiled criterion carries a deterministic evidence rule: allowed document kinds, a required pattern with numeric minimums, and a negation check. A finding counts toward a criterion only if it satisfies that rule, and one cited line may support only one criterion. Citation accuracy alone never makes a criterion Met.
- **Mutation testing** over the checks module, the approval service and the runtime wrapper, with surviving mutants reported.

## Claims delivered

B7, G1–G9, F1–F7, A1. M7 is advanced by the recorded access check for the extraction model.

## Capabilities

### New Capabilities

- `case-packet`: how criteria and evidence become a cited, checked packet; the decision function; and how approval is re-derived from trusted sources.
- `failure-routing`: the per-step empty-output table, the failure destinations, and the session invariant.
- `agent-runtime`: how the agent is hosted, invoked by the intake client, and isolated per case.

### Modified Capabilities

None.

## Impact

- **New code:**
  - `checks/` (the single checks module)
  - `policies/` (synthetic source policies and compiled criteria)
  - `cases/` (synthetic charts and the chart index)
  - `agent/` (pipeline, decision and runtime wrapper)
  - the real approval service in `tools/`
  - `scripts/intake.py`, `scripts/seed_charts.py` and `scripts/require_mmdsv2.py`
  - `infra/runtime_stack.py`
  - tests and the mutation-testing configuration
- **AWS resources:**
  - S3 buckets `prior-auth-cases` (request records and the packet store) and `prior-auth-charts` (chart documents and index)
  - a Cognito app client `prior-auth-intake`
  - an AgentCore Runtime
  - an operator alarm and an SNS topic with a confirmed email subscription

  All of them are removed by teardown.
- **Depends on** `gateway-and-policy`.
