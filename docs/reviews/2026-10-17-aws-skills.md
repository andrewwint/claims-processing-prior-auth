# AWS skills review, 2026-10-17

A read-only review of the deployed system and this repository against current AWS behavior, run during the pre-recording freeze. Four independent lanes, each loading one AWS skill: Amazon Bedrock and AgentCore, IAM, observability, and CDK (teardown path only). No AWS write calls, no deploys, and no repository changes except this report.

**Sources.** Every ranked finding cites current AWS documentation or a read-only API response from the live stack. The lanes had no AWS credentials, so the live responses below were taken separately, read-only, on 2026-10-17, and are reported as states and counts only. Findings based on skill knowledge alone are listed under "Unverified", not ranked.

**Ranks.** (a) breaks a demo beat or an article claim; (b) fix after Monday; (c) cosmetic. For each (a), both options are given; the PM decides.

## Summary

- **(a): one finding**, an article wording issue. No demo beat is affected.
- **(b): fifteen findings**, none affecting the demo or the recorded evidence.
- The observability lane's conditional (a), Bedrock model invocation logging as an unscanned sink, is **not a finding in this account**: invocation logging is off (live response below).

## Live read-only responses (2026-10-17)

| Call | Result |
|---|---|
| `bedrock:GetModelInvocationLoggingConfiguration` | No configuration: model invocation logging is off |
| `logs:DescribeLogGroups` on the runtime log-group prefix | Exactly one runtime log group for the project |
| `xray:GetTraceSegmentDestination` | CloudWatch Logs, ACTIVE (Transaction Search) |
| `xray:GetIndexingRules` | Default rule at 100% |
| `logs:DescribeDeliverySources` | Two sources for the project, both `TRACES` (the gateways); none for the runtime |
| `logs:DescribeResourcePolicies` | Only the account's Transaction Search policy; none created by AgentCore |
| `bedrock-agentcore-control:ListWorkloadIdentities` | Three for the project (two gateways, one runtime) |
| `secretsmanager:ListSecrets` (name filter, Identity vault) | One vault secret |

## (a) Breaks an article claim

### a1. "No secrets live in the agent": true, but for a different reason than the article gives

- **Article line:** "Clinicians and the agent sign in as separate identities. Tools authenticate with the gateway's role, so no secrets live in the agent" (AgentCore mapping table, Identity row).
- **What holds:** no secret appears in the agent's code, its environment or its templates (`evidence/2026-10-16/runtime-identity-and-memory.json`, `tests/test_runtime_identity.py`).
- **What the sentence gets wrong:**
  - The gateway's IAM role covers only the gateway-to-Lambda hop (`GATEWAY_IAM_ROLE` targets).
  - The agent reaches the gateway with an OAuth client-credentials token. AgentCore Identity mints it from a client secret held in its token vault (`requires_access_token(..., auth_flow="M2M")`).
  - The runtime role is granted Secrets Manager read on that one vault secret, as AWS documents for OAuth2 credential providers. So the runtime's IAM principal could read the value, even though the code never does.
- **Source:** https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/identity-authentication.html; https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/harness-security.html (the OAuth2 provider permission set).
- **Option 1, article wording:** "Clinicians and the agent sign in as separate identities. The agent gets its gateway token from AgentCore Identity, which holds the client secret in its vault, and the tools run under the gateway's IAM role. No secret is in the agent's code or configuration."
- **Option 2, code after the recording:** narrow who can read the vault secret so that only AgentCore Identity uses it. Whether a condition such as `aws:CalledVia` works with AgentCore Identity is unverified, so this needs a live test and may not be possible. Option 1 stands either way.

## (b) Fix after Monday

### Bedrock and AgentCore

- **b1. `UpdateGateway` alone can switch off both gateway layers.** Anyone holding it can set the policy engine to LOG_ONLY or remove it, and no condition key protects the mode. The runtime role does not hold it, so the article's claim holds today. Restrict `UpdateGateway`, `UpdatePolicy` and `DeletePolicy` to the deploy role (SCP or permissions boundary), and alarm on `UpdateGateway` via CloudTrail. Source: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-enforcement-modes.html
- **b2. The contract notes are out of date on array claims.** `docs/contract-notes.md` says the encoding of list claims is undocumented. AWS now documents that array claims become their JSON text and must be matched with `like`. The design, a scalar `pa_role` claim matched exactly, remains the stronger choice; update the note and the comment in `infra/cedar.py`. Source: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/example-policies-principal.html
- **b3. The reviewer identity in decision records comes from the caller.** This is already stated in the article ("as the clinician app reports it") and in the README. The fix is the request interceptor planned in `post-monday-hardening` 2.1.

### IAM

- **b4. The README overstates a record's protection.** "Nobody else can delete, hide or replace a record" holds only while the bucket policy stands. The account root can always replace or delete a bucket policy, and delete markers are not WORM-protected. Suggested wording: "...without first changing the bucket policy, which only account administrators can do." Compliance mode is the real fix. Sources: https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock-managing.html; https://docs.aws.amazon.com/cli/v1/reference/s3api/delete-bucket-policy.html
- **b5. The evidence-key deny does not explicitly refuse SSE-S3.** AWS's pattern pairs the key-ID deny with a deny on `s3:x-amz-server-side-encryption` other than `aws:kms`. No writer sends SSE-S3 today, and L5 rests on `head-object`, not on this deny. Add the second deny. Source: https://repost.aws/knowledge-center/s3-bucket-store-kms-encrypted-objects
- **b6. The storage-controls simulation models a header the writers never send.** The writers rely on bucket default encryption, so they send no KMS key-ID header, but the simulation always supplies one. The real no-header path is shown by the successful live writes. Add a no-header row, and read the simulated rows as policy logic over supplied context. Source: https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_testing-policies.html
- **b7. Copying into the record prefixes is impossible, not unverified.** This closes review item R1. With conditional writes enforced by the bucket policy, CopyObject into the prefix fails (403 without the header, 501 with it). Multipart uploads into the record prefixes are also denied; harmless, since records are single PUTs. Source: https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes-enforce.html

### Observability

- **b8. The decision-trace check relies on this account's 100% trace indexing.** With Transaction Search, the default indexing is 1% of spans, so in a default account `verify_chain`'s decision-trace check would usually fail. This account is at 100% (live response above). Document the requirement, or look the segment up in `aws/spans`, which ingests every span. Source: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Enable-TransactionSearch.html
- **b9. The scan's X-Ray sink only sees indexed traces.** With Transaction Search on, traces are not searchable in X-Ray unless indexed. At 100% this sink duplicates `aws/spans`, and the positive control scanned no `aws/spans` events, because spans first arrived there during the clean run. Treat `aws/spans` as the primary span sink and plant a control there. Source: https://docs.aws.amazon.com/xray/latest/api/API_BatchGetTraces.html
- **b10. The scan should record the sinks it did not need to scan.** The scan should record the delivery configuration (no `APPLICATION_LOGS` for the gateways or the runtime) and the invocation-logging setting (off), and fail closed if it cannot read them. Then "every span and log record the runs produced" is checked, not assumed. Today both are confirmed only by the live responses above. Source: https://docs.aws.amazon.com/bedrock/latest/userguide/model-invocation-logging.html
- **b11. The runtime log group is chosen by prefix and the first match** (`canary_scan`, `verify_chain`, `record_trace`). It is correct today, since there is exactly one group (live response above). Use the runtime's own log group name instead. `record_trace` also reads only the first `FilterLogEvents` page, which can legitimately be empty. Source: https://docs.aws.amazon.com/AmazonCloudWatchLogs/latest/APIReference/API_FilterLogEvents.html

### Teardown path (CDK lane; no changes before Monday)

- **b12. Teardown must run with the project's virtual environment active.** `cdk.json` runs `python3 -m infra.app`, and a shell without the virtual environment resolves a Python without `aws_cdk`. Teardown would then stop at its first step, safely, with nothing deleted. **On the day:** activate the virtual environment and run from the repository root. **Later:** point the app command at the project's interpreter. Source: https://docs.aws.amazon.com/cdk/v2/guide/hello-world.html
- **b13. A teardown rerun cannot pass step 2.** The bucket-emptying step assumes the teardown role before it checks whether the bucket still exists, and step 3 deletes that role. If a later step fails, finish the remaining steps and the verifier by hand; do not rerun the whole teardown. **Later:** check the bucket first with the caller's credentials. Source: https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html
- **b14. Teardown depends on local files.** The runtime and policy stacks exist in the CDK app only while `cdk.context.json` and `build/runtime` are present. Keep both until the teardown is verified. **Later:** destroy by CloudFormation stack name.
- **b15. Teardown must account for AgentCore-created resources.** The three workload identities and the Identity vault secret exist today (live responses above). The verifier flags workload identities, but no step deletes them. Confirm after `cdk destroy` whether they went with their parents, and delete any left by exact name. Add an exact-name check for the vault secret, which the verifier does not look for today. The OAuth2 provider listing is also unpaginated. Source: https://docs.aws.amazon.com/bedrock-agentcore-control/latest/APIReference/API_DeleteOauth2CredentialProvider.html

## (c) Cosmetic

- `docs/contract-notes.md` still describes the old session ID (16 hex, one session per case). The code and the article use one session per request.
- `docs/contract-notes.md` says the policy-engine mode "must be set explicitly"; the documented default is ENFORCE. Harmless, because the code sets it.
- The Cognito discovery URL Region is hardcoded in two places, while the runtime stack derives it.
- The gateway role is also granted `GetPolicyEngine` on the gateway ARN; the documented scope is the engine only.
- The vault secret's resource pattern uses `{name}*`; the documented pattern is `{name}-*`.
- The clinician app client requests the Cognito admin scope, which the gateway does not need.
- The F4 recorder does not record when it emitted the metric, so "within a minute" rests on the transition time alone.
- `inventory` omits a few transitional CloudFormation states and the alarm, which goes with its stack.
- The teardown output is printed, not saved. On the day, run it with `set -o pipefail` and `tee` it into the evidence directory.

## Unverified (skill knowledge only, or behavior not observed)

- Whether a condition such as `aws:CalledVia` can restrict the vault secret to AgentCore Identity (a1, option 2).
- Model-call errors after a tool use are wrapped by Strands, so a throttle or denial on a second model call may escape the access-denied mapping. This was read from the pinned package source, not an AWS document. Real IAM denials happen on the first call, so F4 holds in practice.
- The runtime build installs the top-level runtime pins, not the lockfile, so a transitive OpenTelemetry upgrade could change content-capture defaults.
- How long after `PutTraceSegments` a trace becomes searchable; wait a minute or two before running `verify_chain` after a live decision.
- Whether the CloudFormation bucket-policy resource deletes cleanly after the bucket is gone; if the evidence stack ends `DELETE_FAILED`, destroy it again.
- Whether deleting the OAuth2 provider removes its vault secret (b15).
- The Marketplace subscription needed by the opt-in third-party model on a fresh account.

## Verified correct (selected; full lists in the lane reports)

- Both gateways' JWT authorizers: allowed clients, the agent's required scope, and the reviewer's `pa_role` EQUALS check. Also the policy engine in ENFORCE with every policy ACTIVE, Cedar's principal and tag semantics, and the deployed forbid matching the article's snippet character for character. Sources: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/inbound-jwt-authorizer.html, https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-core-concepts.html
- Per-request runtime sessions, each its own microVM. Source: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-sessions.html
- The bucket policy's conditional-write keys and their `Null` logic; `aws:PrincipalArn` resolving to the role ARN for every session; the teardown role's version-by-version delete with the governance bypass; the profile-only Bedrock grant. Sources: https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes-enforce.html, https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_condition-keys.html
- The operator alarm fires on a single datapoint, and the dimensionless datapoint is the series it watches. The Lambda-sent X-Ray segment follows the documented pattern. The pinned ADOT and Strands settings redact content as the article describes. Sources: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/publishingMetrics.html, https://docs.aws.amazon.com/xray/latest/api/API_PutTraceSegments.html
- The teardown order works: the RETAIN bucket is emptied before its stack goes; there are no cross-stack exports; the KMS key goes through its deletion window; the Lambda log groups are deleted with their stack; and Transaction Search is restored to the recorded values. Source: https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-attribute-deletionpolicy.html
