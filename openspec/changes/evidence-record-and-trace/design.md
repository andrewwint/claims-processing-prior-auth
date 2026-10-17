# Design

## Decisions

### D1. Two records, chained by hash

| Record | Key | Holds | Written by | When | Its hash goes on |
|---|---|---|---|---|---|
| Recommendation | `recommendations/<case_id>.json` | packet, recommendation (approve or route, with gaps), citations, policy version, `received_at`, `recommended_at` | agent runtime role | end of the agent's session | the agent's final span (`pa.recommendation_record_sha256`) |
| Decision | `decisions/<case_id>.json` | reviewer identity, decision, reason, `recommendation_record_hash`, `decided_at` | reviewer service role | when the reviewer service records a decision | the reviewer call's span (`pa.decision_record_sha256`) |

- **The chain.** `scripts/verify_chain.py` and its test check three links:
  1. The decision record's `recommendation_record_hash` equals the hash recomputed from the stored recommendation object.
  2. That hash equals the agent's final span attribute.
  3. The decision record's recomputed hash equals the reviewer span attribute.
- **Coverage.** L3 covers both records' fields. L6 covers every link.
- **Reviewer identity** is recorded **as the clinician app reports it**, and labeled `reviewer_identity_source: "clinician-app"`. The request interceptor that would validate it is deferred to `post-monday-hardening`; the design work is kept there.

### D2. Who writes the decision record for an auto-approved case (decided: Andrew, 2026-10-16)

The PM's rule is that the agent and tool roles may write only `recommendations/`, and only the reviewer service may write `decisions/`. Today `record_approval` runs inside the agent's tools Lambda, under a tool role. That leaves an auto-approved case without a permitted writer for its decision record.

- **Proposal.** Split `record_approval` into its own target and Lambda, the "approval service", with its own role.
  - That role may write `decisions/` for auto-approvals, with `reviewer_identity: "approval-service"`.
  - The agent runtime and the case-tool Lambda keep writing only `recommendations/`.
  - This changes the agent gateway to two targets. The action name becomes `ApprovalService___record_approval`.
  - It must land before D1, or as a D1 update.
- **Alternative.** Auto-approvals write no decision record: the approval service's result is folded into the recommendation record. The decision chain then exists only for clinician decisions.

**Decision: split.** `record_approval` is its own target (`ApprovalService`), with its own Lambda (`prior-auth-approval-service`) and role. This was applied in `gateway-and-policy` before D1.
- The approval service role writes `decisions/` for auto-approvals, with `reviewer_identity: "approval-service"`.
- The reviewer service role writes `decisions/` for clinician decisions.
- The agent runtime and the case-tool Lambda write only `recommendations/`.

### D3. Write-once storage and prefix-scoped writes

- **Object Lock.**
  - Governance mode, versioning on, and a default retention of **1 day**. The value is recorded from `get-object-lock-configuration`.
  - One day lets the stack be torn down the next day, or the same day through the teardown role's governance bypass.
- **Bucket policy** (explicit denies, which apply to every principal in the account):
  - Deny `s3:PutObject` on `decisions/*` unless the principal is the reviewer service role or the approval service role.
  - Deny `s3:PutObject` on `recommendations/*` unless the principal is the agent runtime role.
  - Deny `s3:PutObject` on `queue/*` unless the principal is the case-tool role (`route_to_reviewer`). One tenant: entries are `queue/<case_id>.json`. Tenant-scoped prefixes move to `post-monday-hardening`.
  - The case-tool role stays denied on `decisions/` (L8).
  - Deny `s3:BypassGovernanceRetention`, `s3:PutObjectRetention` and `s3:DeleteObjectVersion` unless the principal is `prior-auth-teardown`.
  - Deny any `PutObject` that names a KMS key other than the project key.
- **Overwrites.** Writers use `If-None-Match: *`, so a second write of the same key is refused.
- **How it's proven (L4, L8).** Recorded attempts, each refused:
  - an overwrite by the agent role
  - a delete by the agent role
  - a write to `decisions/` by the agent role (L8)
  - a governance bypass by a non-teardown principal

  Also recorded: `get-object-lock-configuration` showing governance mode and the 1-day retention, and the bucket policy.
- **Production note.** A production deployment would use compliance mode with the retention its records policy requires. The README says so; the demo does not claim it.

### D4. One customer-managed key

- **Key.** One KMS key for the evidence store. The bucket's default encryption is SSE-KMS with that key and a bucket key, and the bucket policy pins it.
- **Access.** The key policy allows encrypt only for the writer roles, and decrypt only for the reviewer service and the verifier.
- **Not claimed.** Per-tenant keys. The article no longer makes that claim.
- **Teardown.** The key is scheduled for deletion with the 7-day minimum, and the verifier accepts `PendingDeletion`.
- **Reconciled.** The earlier text said "two keys" in one place. There is one key.

### D5. One canonical-JSON hash function

- **The function.** `checks.canonical_hash` (today's `packet_hash`, renamed): SHA-256 over JSON with sorted keys, no whitespace and UTF-8. Packets, both records, the trace attributes and the verifier all use it.
- **What is stored.** The writer stores exactly the canonical bytes, so hashing the stored S3 object's bytes equals the record's hash.
- **The test.** It recomputes the hash from the downloaded object, not from the in-memory record.

### D6. Server-generated timestamps

- **`received_at`:** the `LastModified` that S3 assigns to `requests/<case_id>.json` when the intake script writes it.
- **`recommended_at`:** the runtime's clock when it writes the recommendation record.
- **`decided_at`:** the reviewer service's clock (or the approval service's clock).
- **Never from the model or packet.** The record builders ignore any timestamp field in a packet or in model output, and a test proves it.
- **L7 test.** Elapsed time is computed against the 7-day standard and 72-hour expedited windows, including boundary cases (exactly at the window, one second over).

### D7. Decision records before the workbench

`scripts/clinician_decide.py <case_id> <decision> <reason>` works like this:
1. It reads a synthetic clinician's password from Secrets Manager.
2. It signs in through the clinician app client, using SRP.
3. It calls `ReviewerTools___record_adverse_determination` on the reviewer gateway.
4. The reviewer service, `src/prior_auth/handlers/reviewer_tools.py` extended, writes the decision record and returns its hash.

So decision records are produced through the real gateway, authorizer and Cedar path. The workbench later reuses the same tool.

### D8. Telemetry and the canary scan

- **Redaction.** Strands telemetry redaction is set, so content attributes become `[REDACTED]`. `APPLICATION_LOGS` delivery stays off.
- **Custom attributes.** Only non-content values: identifiers, timings, hashes.
- **Scan scope.**
  - the runtime log groups
  - `aws/spans`
  - the gateway's vended logs
  - both tool Lambda log groups: `/aws/lambda/prior-auth-agent-tools` and `/aws/lambda/prior-auth-reviewer-tools`
  - error paths, through an injected failure in each step, so exception messages are scanned too
- **Positive control** before the clean run:
  1. Plant a unique canary in one span attribute and one log line, through a test-only path. (Recorded 2026-10-16; the path was then removed, because the intake client could reach it.)
  2. The scan must find both.
  3. Then the clean run must find zero.

  Both reports are committed.

### D9. Memory

Not used. The Memory IAM deny and its evidence are deferred to `post-monday-hardening`.

### D10. Trace path (PM, 2026-10-16)

`aws/spans` had received no spans since July, though Transaction Search was ACTIVE (it began receiving spans during the 2026-10-16 clean run; the runtime's own spans needed the ADOT entry point and `logs:PutResourcePolicy`). The diagnosis is time-boxed to one hour. If spans still don't arrive, the canary scan reads X-Ray traces (`BatchGetTraces`) as its span source, and the evidence records which path was used.

## Risks / Trade-offs

- [Redaction misses error text or another event path] → The canary scan, with injected failures and a positive control, finds it. The fix is to stop emitting that path.
- [Governance mode is weaker than compliance mode] → The bypass is limited to the teardown role by the bucket policy, and the README states production uses compliance mode.
- [The bucket policy locks out an administrator] → The teardown role is assumable by account administrators. Teardown assumes it explicitly.
