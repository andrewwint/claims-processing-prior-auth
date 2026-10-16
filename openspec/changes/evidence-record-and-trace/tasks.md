# Tasks

## 1. Records and hash chain

- [ ] 1.1 Rename `checks.packet_hash` to `checks.canonical_hash` and use it everywhere. Test: the writer, the telemetry module and the verifier all reference the same function object.
- [ ] 1.2 Record builders in `evidence/records.py` for the recommendation and decision records (design D1). Tests:
  - field presence for both (L3)
  - a one-byte change alters the hash
  - timestamps are never taken from a packet or model output (D6)
- [ ] 1.3 Clock calculation. Done when tests pass against the 7-day and 72-hour windows, including boundary cases (L7).
- [ ] 1.4 `scripts/verify_chain.py`: decision → recommendation → trace, recomputing hashes from the stored S3 objects. Unit tests with stubbed S3 objects and spans, including a broken link at each step (L6).

## 2. Evidence stack (deploy, with approval)

- [ ] 2.1 `infra/evidence_stack.py`:
  - an Object Lock bucket in governance mode, versioning on, 1-day default retention
  - one customer-managed KMS key
  - the bucket policy from design D3: prefix-scoped writes, a governance bypass for the teardown role only, the key pinned
  - the `prior-auth-teardown` role
  - Memory denies on the runtime and tool roles

  Done when the CDK assertions test passes. **Deploy with approval.**
- [ ] 2.2 Record `get-object-lock-configuration` (mode and default retention), the bucket policy, and an IAM policy simulation showing only the teardown role is allowed `s3:BypassGovernanceRetention`.
- [ ] 2.3 Writers:
  - the runtime writes the recommendation record and puts its hash on the final span
  - the reviewer service writes the decision record and puts its hash on the reviewer span

  Done when the unit tests pass.
- [ ] 2.4 `tools/reviewer_interceptor.py` on the reviewer gateway (REQUEST, `passRequestHeaders: true`).
  - It validates the token with `GetUser`, checks the client ID and groups, and overwrites `reviewer_sub`, `reviewer_username` and `tenant`.
  - Unit tests: a spoofed name is overwritten; an invalid token is short-circuited; there is no logging of headers.
- [ ] 2.5 `scripts/clinician_decide.py` (design D7), signing in with SRP. Record one clinician decision through the reviewer gateway with a spoofed `reviewer_username` in the arguments. The decision record must show the validated username. If the transformed body does not reach the Lambda, record that, and flag the article's evidence-record row.

## 3. Recorded proofs

- [ ] 3.1 Each of these is recorded and refused:
  - an overwrite of a recommendation by the agent role
  - a delete by the agent role (L4)
  - **a write to `decisions/` by the agent role, and by the case-tool role after the `queue/<tenant>/` scoping lands (L8)**
  - a write by the case-tool role to `queue/` outside a tenant prefix
  - a governance bypass attempted by a non-teardown principal
  - a write under another KMS key (L5)

  Also record `head-object` showing the customer-managed key (L5).
- [ ] 3.2 Run `verify_chain.py` on one routed-then-decided case. Save the output: every hash recomputed from S3 matches its span (L6, A6).

## 4. Clean telemetry proof

- [ ] 4.1 Canaries in every synthetic chart. `scripts/canary_scan.py` covers the full scope in design D8, including both tool Lambda log groups. Done when a unit test with a fake log source finds a planted canary.
- [ ] 4.2 Positive control: plant a canary in one span and one log line. The scan finds both. Commit the report.
- [ ] 4.3 Clean run: run the cases, with an injected failure at each step, then the scan. Commit the zero-hit report and the list of sources scanned (L2).
- [ ] 4.4 Memory evidence: the `list-memories` output, a code search for memory clients, and the deny statements (A5).

## 5. Teardown

- [ ] 5.1 Extend the teardown and verifier:
  - the teardown assumes `prior-auth-teardown` to bypass governance and empty the bucket
  - the key is accepted in `PendingDeletion`

  Run them the same day and save the output.

## Workflow follow-up

- Update the claims ledger for L1–L8, A5 and A6.
