# Proposal

## Why

The article's design ends at a person: the clinician sees the case the agent built and makes the decision, and only the clinician's app holds the denial tool. A minimal workbench makes that real and lets the ledger prove the clinician-side half of the boundary. It is priority 4.

## What Changes

- **Review queue.** `route_to_reviewer` writes a queue entry (case ID, tenant, reason, gaps) next to the evidence record.
- **The workbench.** A minimal local web app that signs the clinician in through Cognito and lists queued cases for the clinician's tenant. It shows the packet checklist with sources, failure labels and gaps. It records one of two decisions:
  - approve
  - adverse determination, with a required reason

  Both go through the reviewer gateway under the clinician's own token.
- **Reviewer identity and decision time** are written to the evidence record.
- **No public endpoint.** The workbench runs locally against the deployed gateways.

## Claims delivered

B8, completing the clinician-side half. It also supports L3 (reviewer identity) and L7 (decision timestamp).

## Capabilities

### New Capabilities

- `clinician-workbench`: how a clinician reviews a routed case and records a decision.

### Modified Capabilities

None.

## Impact

- **New code:** `workbench/` (Python web app) and tests.
- **AWS resources:** none new beyond the queue storage.
- **Depends on** `evidence-record-and-trace`.
