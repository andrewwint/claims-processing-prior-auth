# Proposal

## Why

An auditor asks about one case:
- What did the agent recommend, and on what evidence?
- Who decided, and when?

Answering that means keeping a full record without putting chart text in logs. The article's answer is two kinds of record with two jobs: a trace that holds identifiers, timings and hashes, and write-once evidence records whose hashes the trace carries. This change builds both, chains them by hash, and proves the trace is clean. It is priority 3.

## What Changes

- **Two records, chained by hash.**
  - **Recommendation record** (`recommendations/<case_id>.json`):
    - holds the packet, the recommendation, the citations and the policy version
    - is written at the end of the agent's session
    - its hash goes on the agent's final span
  - **Decision record** (`decisions/<case_id>.json`):
    - holds the reviewer identity, the decision, the reason, and `recommendation_record_hash`
    - is written by the reviewer service for clinician decisions, or by the approval service for auto-approvals
    - its hash goes on the reviewer call's span
  - **The chain:** decision → recommendation → trace.
- **Evidence store.** One S3 bucket with Object Lock in governance mode, versioning, and a default retention of 1 day. Records are encrypted under **one** customer-managed KMS key.
- **Prefix-scoped writes, enforced by the bucket policy:**
  - The agent runtime and tool roles may write only `recommendations/`.
  - Only the reviewer service, and the approval service for auto-approvals, may write `decisions/`.
  - No project role may overwrite or delete a record.
  - Only the teardown role may use `s3:BypassGovernanceRetention`. The bucket policy denies it to every other principal, including account administrators.
- **One canonical-JSON hash function.** The writer, the trace and the verifier all use it. The verifier recomputes the hash from the stored S3 object.
- **Server-generated timestamps.**
  - `received_at` is the time S3 assigns to the intake request record.
  - `decided_at` is set by the clock of the service that writes the decision record.
  - No timestamp is ever taken from the model or from the packet.
- **Decision records before the workbench exists.** `scripts/clinician_decide.py` signs in as a synthetic clinician, with the password from Secrets Manager. It then calls the reviewer gateway, so the reviewer service writes a real decision record through the real path.
- **Trace attributes.** Case ID, step, model ID, token counts, latency, stop reason, the SHA-256 of each content item, and the record hashes. No content.
- **Canary scan with a positive control.**
  - A canary planted in a span and in a log line is found by the scan.
  - Then the clean run scans empty.
  - Scope: the runtime logs, span records, gateway logs, both tool Lambda log groups, and error paths.
- **Memory.** No Memory resource. An explicit IAM deny on Memory actions, and evidence that none exists.

## Claims delivered

L1–L8, A5 (evidence for the article edit) and A6.

## Capabilities

### New Capabilities

- `evidence-record`: the two records, their hash chain, how they are protected, and the decision clock.
- `clean-telemetry`: what telemetry may contain, and how its cleanliness is proven.

### Modified Capabilities

None.

## Impact

- **New code:**
  - `infra/evidence_stack.py`
  - `evidence/records.py` (the record builders and writer)
  - `agent/telemetry.py`
  - `tools/reviewer_service.py`
  - `scripts/clinician_decide.py`, `scripts/canary_scan.py` and `scripts/verify_chain.py`
  - tests
- **AWS resources:**
  - one S3 bucket
  - **one** customer-managed KMS key. Its deletion is scheduled with the 7-day minimum, and the verifier accepts `PendingDeletion`.
  - a teardown role `prior-auth-teardown`
- **Depends on** `case-packet-and-failure-routing`.
- **Decided (Andrew, 2026-10-16):** auto-approval decision records are written by the approval service, which has its own Lambda and role (design D2).
