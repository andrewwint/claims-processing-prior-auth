# Proposal

## Why

An auditor follows one case from the decision back to the recommendation and on to the trace, without finding chart text anywhere in the telemetry. This change delivers that chain and **beat 6**'s clean-trace proof (PM scope cut, 2026-10-16).

## What Changes

- **One evidence bucket.**
  - `recommendations/` is written only by the agent runtime.
  - `decisions/` is written only by the reviewer and approval services.
  - Object Lock in governance mode, and one customer-managed key.
- **The hash chain.**
  - The recommendation record's hash is on the agent's final span.
  - The decision record carries `recommendation_record_hash`.
  - `verify_chain.py` recomputes every link from S3.
- **Recorded refusals:**
  - an overwrite by the agent role (L4)
  - a write to `decisions/` by the agent role (L8)
- **Clean trace.** A canary scan with a positive control. It runs after the account's trace path is diagnosed.
- **Server-generated timestamps**, and a test of the decision clock.

**Deferred (README "Known limitations"):**
- the reviewer-identity interceptor. Decision records label the identity "as asserted by the clinician app".
- tenants and per-tenant scoping
- per-tenant keys
- Memory evidence
- the extra clock edge cases
- the redeploy test

## Claims delivered

L1–L4, L6–L8, A6. L5 stays (one customer-managed key). A5 is deferred.

## Capabilities

### New Capabilities

- `evidence-record`: the two records, their chain, and how they are protected.
- `clean-telemetry`: what telemetry may contain, and how that is proven.

### Modified Capabilities

None.

## Impact

- **New code:** `infra/evidence_stack.py`, the record writers, `scripts/verify_chain.py`, `scripts/canary_scan.py`, and tests.
- **AWS resources:** one bucket, one KMS key (deletion scheduled at teardown), and a teardown role.
- **Depends on** `case-packet-and-failure-routing`.
