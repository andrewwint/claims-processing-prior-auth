# Independent reviews: evidence-store IAM and decision binding (2026-10-16/17)

Each review was an independent lane that received the spec (OpenSpec change specs and designs, ledger rows) and the diff only. Reviews are summarized here; the findings are stated as the reviewers gave them, with what was done about each.

## Process note

The PM's rule ("any change to IAM policies, Cedar policies or gateway allowed clients gets an independent review lane before it deploys") arrived after the 2b05a82 gateway deploy had finished. That deploy changed IAM (active tracing adds X-Ray write permissions to the approval and reviewer Lambda roles), and the earlier ec49468 deploy scoped each Lambda's evidence-bucket access. Both were reviewed **retroactively** (review 1). The boundary smoke checks were rerun after 2b05a82 and matched the recorded evidence (`evidence/2026-10-16/boundary-smoke-15a490fd49ef.json`).

## Review 1 (retroactive): diff 53b83c2..2b05a82, gateway IAM and evidence writers

Cleared: per-Lambda S3 prefix scoping (template-verified), prefix-conditioned ListBucket, KMS grants conditioned on the evidence key alias, the X-Ray grant, trace annotations (identifiers and hashes only), logs without reason text, refusal paths, unchanged inbound access.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | Medium, **blocking** | Write-once was only the writer's `If-None-Match` header; the bucket did not enforce it, so a writer role could replace the current version of a record. | Fixed in 24775b7: bucket policy denies `PutObject` to `recommendations/` and `decisions/` without `If-None-Match` and with `If-Match`. |
| 2 | Medium | A clinician decision bound to whatever run the queue named at call time, not the run reviewed. | Fixed in 24775b7: reviewer tools require `run_id`, refuse a mismatch with the queue, and require the run's recommendation to be a route. The workbench sends the run it showed. |
| 3 | Low-medium | An auto-approval could chain to another run's recommendation (packet re-read after verification; recommendation not checked). | Fixed in 24775b7: binds to the verified packet object (read once) and requires its recommendation to approve that exact packet hash. |
| 4 | Low | A missing record might return 403, not 404, under the prefix-conditioned ListBucket. | Probed live: a decision on an unqueued case returns the structured refusal "case is not in the review queue". Not reproduced. |
| 5 | Low | The runtime role holds `logs:PutResourcePolicy` on `/aws/bedrock-agentcore/runtimes/*`; whether that scope applies is unverified. | Open, stated in README "Known limitations". |
| 6 | Low | The KMS key policy is the CDK default; key scoping is IAM-only, unlike design D4. | Open, stated in README "Known limitations". |
| 7 | Low | Reviewer identity is free text from the caller. | Already a known limitation (validating interceptor deferred to `post-monday-hardening`). |
| 8 | Low | The clean canary scan predated the decision trace segments and scanned no reviewer Lambda events. | Fixed: the clean scan now decides every routed case through the reviewer gateway and scans for the decision reasons too; rerun after the deploy. |

## Review 2 (pre-deploy): diff 2b05a82..24775b7

Verdict: **no blocking issue**. The condition keys `s3:if-none-match` / `s3:if-match` and their Null logic are correct; no writer is locked out; the `run_id` schema change does not interact with Cedar; both binding paths are tied to the exact recommendation reviewed or verified; no refusal writes a record; inbound access unchanged.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| E1 | Medium | A record could be hidden by a delete marker (plain `DeleteObject`), then a new conditional create succeeds. | Fixed: `RecordsAreNotDeleted` denies `s3:DeleteObject` on the record prefixes to all but the teardown role (delta reviewed: closes E1 for everyone but teardown, locks nothing out). |
| D1 | Medium | E1 remained possible for the teardown role. | Fixed: the teardown role no longer holds `s3:DeleteObject`; teardown empties the bucket by version ID with the governance bypass. |
| D2 | Low | An administrator could add a lifecycle expiration rule, which creates delete markers outside the bucket policy. | Open; same trust level as changing the bucket policy itself. No lifecycle rule is configured. |
| E2 | Low | Fixture approvals (`SYN-PKT-*`) report "recorded" but write no decision record. | Open, stated in README "Known limitations"; changing it would change the recorded boundary baseline. |
| R1 | Unverified | Whether CopyObject honors a destination `If-None-Match`. | Open; only the two decision Lambdas could attempt it, and no code does. |
| D1′ | Medium | The teardown role can still delete every version of a record (governance bypass) and let a new one be created. | Open by design of the demo: governance mode with one bypass role, so the stack can be torn down. Closed by compliance mode (README: production uses compliance mode) or by narrowing who may assume the teardown role (trusted by the account root). |

Delta review of the D1 change (teardown role without `s3:DeleteObject`; teardown empties by version ID): no blocking issue; teardown can still empty and delete the bucket (`DeleteObjects` with version IDs is authorized per key as `s3:DeleteObjectVersion`). To confirm on the first teardown run: `cdk destroy PriorAuthEvidence` after the bucket is already deleted (its bucket policy resource will see NoSuchBucket).

Deployed after these reviews: see `evidence/deploys.jsonl` for the SHAs that follow this file's commit.
