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
- **Reviewer identity comes from a request interceptor** on the reviewer gateway (PM, 2026-10-16; contract-read in `docs/contract-notes.md`). Gateway does not pass the caller's identity to Lambda targets, but a REQUEST interceptor receives the bearer token (`passRequestHeaders: true`) and can rewrite the `tools/call` arguments.
  - **Validation.** `tools/reviewer_interceptor.py` validates the token itself with Cognito `GetUser`, a server-side check, so it relies neither on the authorizer having run first nor on a crypto library in the Lambda. It also requires the token's `client_id` to be the clinician client, and its groups to include `clinician` and exactly one tenant group.
  - **Overwrite.** It writes `reviewer_sub`, `reviewer_username` and `tenant` into the arguments, overwriting any caller-supplied values. It then returns the transformed request.
  - **On failure** it returns a `transformedGatewayResponse` error (a short-circuit), so the target is never called.
  - **No logging of credentials.** It never logs headers or the token.
  - **In the record.** The decision record's reviewer identity is the interceptor's value, labeled `reviewer_identity_source: "validated-token"`.
  - **Tests.** A unit test shows that a spoofed `reviewer_username` is overwritten. A recorded live call sends a spoofed name, and the decision record shows the real one.
  - **Live check.** Whether a transformed body reaches a *Lambda* target is not stated in the docs. It is confirmed by that recorded call before the article's row is marked proven. If it does not, the article's evidence-record row is flagged for "reviewer identity as asserted by the clinician app".

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
  - Deny `s3:PutObject` on `queue/*` unless the principal is the case-tool role (`route_to_reviewer`). Queue entries also fall under the default retention; they are never overwritten, only superseded by the decision record.
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
4. The reviewer service, `tools/reviewer_tools.py` extended, writes the decision record and returns its hash.

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
  1. Plant a unique canary in one span attribute and one log line, through a test-only path.
  2. The scan must find both.
  3. Then the clean run must find zero.

  Both reports are committed.

### D9. Memory

No Memory resource. The runtime and tool roles include an explicit `Deny` on `bedrock-agentcore:CreateMemory`, `CreateEvent` and `RetrieveMemoryRecords`. The evidence is the `list-memories` output, a code search, and the role policies.

## Risks / Trade-offs

- [Redaction misses error text or another event path] → The canary scan, with injected failures and a positive control, finds it. The fix is to stop emitting that path.
- [Governance mode is weaker than compliance mode] → The bypass is limited to the teardown role by the bucket policy, and the README states production uses compliance mode.
- [The interceptor's body rewrite might not reach a Lambda target] → A recorded live test with a spoofed name decides it before the claim is marked proven. The fallback is the article edit named above.
- [The bucket policy locks out an administrator] → The teardown role is assumable by account administrators. Teardown assumes it explicitly.
