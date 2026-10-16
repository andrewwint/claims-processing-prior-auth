# Proposal

## Why

An auditor asks about one case: what the agent recommended, on what evidence, and who decided, and when. Answering that means keeping a full record without putting chart text in logs. The article's answer is two records with two jobs: a trace that holds identifiers, timings and hashes, and a write-once evidence record whose hash the trace carries. This change builds both and proves the trace is clean. It is priority 3.

## What Changes

- **Evidence store.** One S3 bucket with Object Lock in governance mode and versioning. Each record is encrypted under one customer-managed KMS key.
  - The agent and tool roles can write new objects but cannot overwrite, delete or bypass retention.
  - Only the teardown role can bypass governance retention.
- **Evidence record.** Packet, recommendation, citations, policy version, reviewer identity, decision, and timestamps (received, recommended, decided).
- **Trace attributes.** Case ID, step, model ID, token counts, latency, stop reason, and the SHA-256 of each content item and of the evidence record. No content.
- **Canary scan.** Synthetic charts carry unique canary strings. A scan of the runtime logs, span records and gateway logs must find zero canaries. The scan runs as a test and as a committed report.
- **Memory.** No Memory resource. An explicit IAM deny on Memory actions, and evidence that none exists.

## Claims delivered

L1–L7, A5 (evidence for the article edit) and A6.

## Capabilities

### New Capabilities

- `evidence-record`: what the write-once record holds, how it is protected, and how it links to the trace.
- `clean-telemetry`: what telemetry may contain, and how its cleanliness is proven.

### Modified Capabilities

None.

## Impact

- **New code:** `infra/evidence_stack.py`, `agent/telemetry.py`, `scripts/canary_scan.py` and tests.
- **AWS resources:** the S3 bucket and two KMS keys (key deletion is scheduled with a 7-day minimum; the verifier accepts `PendingDeletion`).
- **Depends on** `case-packet-and-failure-routing`.
