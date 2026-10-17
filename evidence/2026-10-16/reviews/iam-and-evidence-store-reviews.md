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
| 5 | Low | The runtime role holds `logs:PutResourcePolicy` on `/aws/bedrock-agentcore/runtimes/*`; whether that scope applies is unverified. | Open; listed under "Reviewed limitations" below. |
| 6 | Low | The KMS key policy is the CDK default; key scoping is IAM-only, unlike design D4. | Open; listed under "Reviewed limitations" below. |
| 7 | Low | Reviewer identity is free text from the caller. | Already a known limitation (validating interceptor deferred to `post-monday-hardening`). |
| 8 | Low | The clean canary scan predated the decision trace segments and scanned no reviewer Lambda events. | Fixed: the clean scan now decides every routed case through the reviewer gateway and scans for the decision reasons too; rerun after the deploy. |

## Review 2 (pre-deploy): diff 2b05a82..24775b7

Verdict: **no blocking issue**. The condition keys `s3:if-none-match` / `s3:if-match` and their Null logic are correct; no writer is locked out; the `run_id` schema change does not interact with Cedar; both binding paths are tied to the exact recommendation reviewed or verified; no refusal writes a record; inbound access unchanged.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| E1 | Medium | A record could be hidden by a delete marker (plain `DeleteObject`), then a new conditional create succeeds. | Fixed: `RecordsAreNotDeleted` denies `s3:DeleteObject` on the record prefixes to all but the teardown role (delta reviewed: closes E1 for everyone but teardown, locks nothing out). |
| D1 | Medium | E1 remained possible for the teardown role. | Fixed: the teardown role no longer holds `s3:DeleteObject`; teardown empties the bucket by version ID with the governance bypass. |
| D2 | Low | An administrator could add a lifecycle expiration rule, which creates delete markers outside the bucket policy. | Open; same trust level as changing the bucket policy itself. No lifecycle rule is configured. |
| E2 | Low | Fixture approvals (`SYN-PKT-*`) report "recorded" but write no decision record. | Open; listed under "Reviewed limitations" below. Changing it would change the recorded boundary baseline. |
| R1 | Unverified | Whether CopyObject honors a destination `If-None-Match`. | Open; only the two decision Lambdas could attempt it, and no code does. |
| D1′ | Medium | The teardown role can still delete every version of a record (governance bypass) and let a new one be created. | Open by design of the demo: governance mode with one bypass role, so the stack can be torn down. Closed by compliance mode (README: production uses compliance mode) or by narrowing who may assume the teardown role (trusted by the account root). |

Delta review of the D1 change (teardown role without `s3:DeleteObject`; teardown empties by version ID): no blocking issue; teardown can still empty and delete the bucket (`DeleteObjects` with version IDs is authorized per key as `s3:DeleteObjectVersion`). To confirm on the first teardown run: `cdk destroy PriorAuthEvidence` after the bucket is already deleted (its bucket policy resource will see NoSuchBucket).

Deployed after these reviews: see `evidence/deploys.jsonl` for the SHAs that follow this file's commit.

## Review 3 (pre-deploy): the Sonnet 4.6 opt-in for the harness run (runtime role)

Diffs: the allow-list commit 0a8a669 and `cdk diff PriorAuthRuntime -c model_opt_in=us.anthropic.claude-sonnet-4-6`. Verdict: **contract satisfied, no blocking issue**, in both directions (the opt-in deploy and the revert). One allow-list feeds both the IAM grant and `MODEL_ALLOW_LIST`; exact ARNs; the opt-in comes only from deploy context and is not persisted; the caller's `model_id` must match the deployed list; who may invoke the runtime is unchanged; the revert replaces the whole policy document.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| N1 | Low (hardening) | The Sonnet foundation-model ARNs had no condition, so the role could call the model directly in the three Regions, not only through the profile. | Fixed: those ARNs are granted only with `bedrock:InferenceProfileArn` = the US profile ARN. Delta reviewed: closes N1; the default (no opt-in) policy is byte-identical to the deployed one. The first Sonnet trial is the live probe; a mismatch would fail closed (`operator_alert`). |
| N2 | Low (availability) | The three destination Regions are recorded, not re-read from the profile at deploy time; a new destination Region would be denied. | Open; fails closed. |
| N3 | Informational | While the opt-in is deployed, any holder of the intake client secret can choose Sonnet; the $10 cap is enforced by the runner, not the runtime. | Open, for the run window only; the intake client is operator-only. The opt-in is reverted after the run. |

## Reviewed limitations (open, not in the README)

The README keeps the governance-mode limitation (the qualifier on L4). These stay open and are recorded here:

- **The evidence key's policy is the CDK default** (account root `kms:*`). Key use is scoped by IAM, each role's grants conditioned on the key's alias, not by the key policy; design D4's "encrypt only for writers, decrypt only for the reviewer service and the verifier" is not enforced at the key, and the approval service also decrypts (it reads packets).
- **The runtime role may set log resource policies** on `/aws/bedrock-agentcore/runtimes/*` (`logs:PutResourcePolicy`), which AgentCore uses to deliver spans to the agent's log group. Whether CloudWatch Logs applies that resource scope or treats the action as account-wide is not verified.
- **Fixture approvals write no decision record.** The D1 fixture packets (`SYN-PKT-*`), kept so the boundary checks can be rerun, are approved or refused by the approval service but are not runs, so no recommendation or decision record exists for them. Live packets (`PKT-<case>`) always get one.
- **D2:** an administrator could add a lifecycle expiration rule, which creates delete markers outside the bucket policy. No lifecycle rule is configured.
- **R1:** whether CopyObject honors a destination `If-None-Match` is unverified; only the two decision Lambdas could attempt it, and no code does.
