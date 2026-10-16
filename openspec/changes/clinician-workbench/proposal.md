# Proposal

## Why

The article's design ends at a person: the clinician reviews the case and decides, with the denial tool only on the clinician's side. This change delivers **beat 5**, demoed right after **beat 4** shows the agent refused the same tool (PM scope cut, 2026-10-16).

## What Changes

- **Reviewer gateway tools:** `record_adverse_determination` (reason required) and `record_clinician_approval`, both for clinicians only.
- **A single local page:**
  - hosted-UI sign-in through a standard OAuth library (PKCE and `state`)
  - the queue
  - a packet view with distinct failure labels and a marked model summary
  - approve, or deny with a required reason
- **Decision records** chained to the recommendation record. The reviewer identity is labeled "as asserted by the clinician app".

**Deferred (README "Known limitations"):**
- the request interceptor that would validate the reviewer identity
- tenants and cross-tenant tests (one tenant)
- reads through the gateway (the demo page reads the queue with the operator's credentials)

## Claims delivered

B8 (clinician half). It also supports L3 and L7.

## Capabilities

### New Capabilities

- `clinician-workbench`: how a clinician reviews a routed case and records a decision.

### Modified Capabilities

None.

## Impact

- **New code:** `workbench/`, the reviewer tool additions, and tests.
- **AWS changes:** one more reviewer tool and one more Cedar permit.
- **Depends on** `evidence-record-and-trace`.
