# Tasks

## 1. Evidence record

- [ ] 1.1 Record schema, canonical JSON and hash function. Tests: field presence (L3), hash stability, and that a one-byte change alters the hash.
- [ ] 1.2 Evidence stack: Object Lock bucket in governance mode, one customer-managed KMS key with a bucket policy pinning it, role policies as in design.md. CDK assertions test. **Deploy with approval.**
- [ ] 1.3 Writer in the approval and routing paths. Recorded: a record's `head-object` showing the customer-managed key (L5), a refused write under another key, plus a refused overwrite and a refused delete by the agent role (L4).
- [ ] 1.4 Clock calculation against the standard and expedited windows. Test (L7).

## 2. Trace

- [ ] 2.1 Telemetry module: trace attributes, content hashes, record hash on the final span, redaction setting. Unit tests on the attribute set (L1).
- [ ] 2.2 Recorded: an exported trace for one case, and a recomputed record hash that matches the trace attribute (L6, A6).

## 3. Clean telemetry proof

- [ ] 3.1 Canaries in every synthetic chart, and `scripts/canary_scan.py`. Test with a fake log source that the scanner finds a planted canary.
- [ ] 3.2 Run the cases, then the scan. Commit the zero-hit report and the list of sources scanned (L2).
- [ ] 3.3 Memory evidence: `list-memories` output, a code search for memory clients, and the deny statements in the role policies (A5).

## 4. Teardown

- [ ] 4.1 Extend the teardown and verifier for the bucket (governance bypass by the teardown role) and the keys (`PendingDeletion` accepted). Run them the same day and save the output.

## Workflow follow-up

- Update the claims ledger for L1–L7, A5 and A6.
