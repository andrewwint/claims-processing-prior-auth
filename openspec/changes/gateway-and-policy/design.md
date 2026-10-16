# Design

## Context

The service constraints this design relies on are in [docs/contract-notes.md](../../../docs/contract-notes.md). Three of them shape it:

1. A Cedar policy can only name an action that is registered on a gateway attached to the policy engine.
2. Policy checks the arguments a caller sends, not whether they are true.
3. Lambda targets can only use the gateway's IAM role as their outbound credential.

## Decisions

### D1. Two gateways, one policy engine, two layers (PM-approved)

- **What.**
  - The agent's gateway does not register the denial tool.
  - A separate reviewer gateway registers `record_adverse_determination`, and one engine governs both.
  - **Layer 1, inbound:** the reviewer gateway's `CUSTOM_JWT` authorizer lists only the clinician app client in `allowedClients`. An agent token is rejected before policy is evaluated.
  - **Layer 2, policy:** a `forbid` unless the principal is in the clinician group, and an explicit `forbid` when the principal is the agent identity.
- **Why.**
  - The agent's gateway can truthfully have no denial tool (B1, B2).
  - The forbid names a registered action, so it passes validation and can be exercised (B3).
  - Each layer is proven separately (B4).
- **How layer 2 is proven.** Layer 1 would otherwise hide it, so a test configuration temporarily adds the agent client to the reviewer gateway's `allowedClients`. The agent then calls the tool, and the denied call is recorded. The configuration is reverted, and `get-gateway` is captured before, during and after.
- **Alternative considered.** Register the denial tool on the agent's gateway and forbid it unconditionally. Rejected: the target listing would show the tool as registered, which contradicts B2.

### D2. `record_approval` names a stored packet and is verified server-side (PM-approved)

- **Input:** `packet_id` and `packet_hash` are required strings, and there are no booleans. The hash is SHA-256 over the packet's canonical JSON.
- **Policy:** the permit names the agent principal and requires both fields to be present. That is all Cedar checks.
- **Approval Lambda:** it loads the stored packet and verifies the hash. It then re-runs the checks: every criterion Met, and the schema, source-match and same-patient checks passing. If any step fails, it refuses and returns a reason, and it records nothing.
- **Never trust the packet (PM, 2026-10-16).** The verdict is rebuilt by the shared `checks/` module from trusted sources:
  - the request record (payer, CPT, patient)
  - the compiled criteria for that (payer, CPT)
  - the chart store and its index

  Status labels and patient IDs in the packet are ignored. In this change all of these, and the packet store, are synthetic fixtures bundled with the Lambda: a passing packet, a failing packet, and a forged packet marked all Met. `case-packet-and-failure-routing` replaces the fixtures with the real stores.
- **Why.** Policy checks the shape of a call, and only the server can check its truth (B7). Nothing the agent asserts can produce an approval.
- **Alternative considered.** A temporal policy that requires earlier passing check-tool responses in the same session. Deferred: it adds a session header to every call, extra IAM, and an unconfirmed detail about how tool output is matched.

### D3. Identities and principals

- **Agent.** A Cognito app client with the client-credentials grant and a resource-server scope. It has no user and no group.
  - Task 3.2 records the token's `sub` and `client_id` from a real token. The expectation is that `sub` equals the client ID for this grant, but this is confirmed, not assumed.
  - The explicit forbid uses that value as `AgentCore::OAuthUser::"<sub>"`.
- **Clinician.** A separate app client used by synthetic users in the `clinician` group.
  - The claim that carries group membership (`cognito:groups`) and how it maps to a principal tag are confirmed from a real token before policies are written.
  - Synthetic tenant users are in the `tenant-a` and `tenant-b` groups.
- **User pool.** `AllowAdminCreateUserOnly` is true, so there is no self-signup. Synthetic users are created by an administrator script, and their passwords are generated into Secrets Manager. No password is ever written to the repository or to evidence.
- **Hardening from the security review (2026-10-16):**
  - The clinician client has OAuth disabled: no hosted-UI, implicit or code flow.
  - The agent client's sign-in flows are pinned to `ALLOW_REFRESH_TOKEN_AUTH`, so it cannot mint a user-subject token.
  - Both clients prevent user-existence errors.
  - The agent gateway requires the `prior-auth/tools` scope.
  - The reviewer gateway's layer 1 checks the clinician client **and** `cognito:groups` containing `clinician`.
  - The Cognito domain prefix is a private deploy-time value.
  - After D1, the agent client secret is copied into Secrets Manager (`prior-auth/agent-client`).
- **Explicit principals.** Every permit names its principal: the agent's `sub`, or the clinician group tag. There is no permit for all principals.

### D4. Infrastructure as code

- **Tools.** Python CDK. `aws-cdk-lib` stable constructs are used for Gateway and GatewayTarget. Policy uses the L1 `CfnPolicyEngine` and `CfnPolicy`.
- **Two stacks** (the deploy has two passes):
  1. Cognito, the Lambdas (each with an explicit log group), **the policy engine**, and both gateways with their targets. Each gateway attaches the engine through `policyEngineConfiguration` with `mode: ENFORCE` from its first deploy. An engine with no policies denies every call, so between D1 and D2 the gateways fail closed: there is no window without Cedar.
  2. The five policies (`CfnPolicy`), each with `enforcementMode: ACTIVE` set explicitly. A policy in `LOG_ONLY` enforces nothing, just as an engine attached in `LOG_ONLY` doesn't.
- **Gateway role trust** is bound by `aws:SourceArn` to the gateway's own name prefix, and the policy-evaluation permissions are scoped to the one engine.
- **Budgets** live in their own stack. It is deployed first and excluded from teardown. The account already had spend this month, so an account-wide budget's thresholds are offset by the month-to-date baseline. A second budget, filtered on the project tag, carries the exact tiers once the tag is active (task 1.2).
- **Validation mode.** The default mode. An automated-reasoning finding is recorded, and work stops for a decision. The mode is never changed to get past a finding.
- **Gateway role.** It includes `bedrock-agentcore:AuthorizeAction`, `PartiallyAuthorizeActions` and `GetPolicyEngine`. These are missing from default roles, and without them every call is denied.
- **No secrets in the agent.** Both Lambda targets use `GATEWAY_IAM_ROLE` as their credential. The agent's client secret is stored in Secrets Manager for the caller that obtains tokens. It is never placed in tool configuration (A4).

### D6. Transaction Search is account-wide

Transaction Search and its span indexing percentage apply to the whole account, not just this project.

- **Before enabling (task 3.4):** the script records the current state and the indexing percentage to `evidence/`.
- **Teardown:** restores both values.
- **Verifier:** reports the restored values next to the recorded ones, and fails if they differ.

### D5. Evidence is captured by scripts, not by hand

`scripts/capture_evidence.py` uses the pinned boto3 release, because the local AWS CLI is too old for the policy APIs. It writes to `evidence/<date>/`:
- target listings, tool schemas and target credential types
- the Cognito app clients (IDs and grant types, no secrets)
- paginated `tools/list` results per identity
- policy definitions, status and validation findings
- `get-gateway` (mode and allowed clients)
- raw responses for each allowed, rejected, denied and refused call
- matching span records and `DenyDecisions` and `AllowDecisions` datapoints

Before anything is committed, redaction replaces ARNs, account IDs and Cognito client IDs with stable placeholders such as `<ACCOUNT_ID>`, `<GATEWAY_ARN:reviewer>` and `<CLIENT_ID:agent>`. Redaction never touches action names (`<target>___<tool>`). B5 compares the policy text character for character, so a test asserts that the redacted policy text keeps the exact action string.

## Security review dispositions (independent lane, 2026-10-16)

| Finding | Status |
|---|---|
| E1. Reviewer gateway admits every pool user | Fixed: a group claim check on the authorizer, plus the engine in ENFORCE from D1 |
| E2. Clinician client OAuth defaults (implicit and code flows) | Fixed: OAuth disabled |
| E3. Agent client falls back to Cognito's default sign-in flows | Fixed: refresh-token flow only |
| E4. Gateway role trust has no `aws:SourceArn` | Fixed: bound to the gateway name prefix (ARN format confirmed live at D1; a wrong pattern fails closed) |
| E5. Teardown deletes by name pattern | Fixed: exact log group names; secrets need the prefix and the project tag; teardown stops if `cdk destroy` fails |
| E6. Agent client secret only in Cognito | Fixed: copied to Secrets Manager after D1. Reading it from Cognito by account administrators remains possible (residual) |
| E7. Predictable Cognito domain prefix | Fixed: private deploy-time value |
| E8. Account principals with `lambda:InvokeFunction` can call the tool Lambdas directly, bypassing both gateway layers | **Accepted as a documented residual (PM, 2026-10-16).** Account admins are inside the trust boundary, and could also edit the Cedar policies. `record_approval`'s server-side rebuild refuses forged approvals whatever the call path. Contract-read: Gateway does not pass the caller's JWT or identity to Lambda targets (the context carries only gateway, target, tool and message IDs; a request interceptor can inject an `Authorization` header, but the docs describe header delivery only for targets with header allowlists). So the denial Lambda cannot verify the clinician itself. Documented in the README's threat model. |
| E9. Redaction misses Cognito and gateway identifiers | Fixed: generic patterns, with tests that action names and hashes are untouched |

### Second independent review (2026-10-16)

| Finding | Status |
|---|---|
| X1. Approval matched quotes, not meaning: any 4-character quote on the right patient's line counted for any criterion | Fixed in `checks/`: compiled evidence rules (document kind, pattern, numeric minimums, negation), one line per criterion, no rule means never Met. Tests reproduce the reviewer's probes. Carried into `case-packet-and-failure-routing` design D11. |
| X2. E8 (direct Lambda invoke) | Accepted residual (above) |
| X3. The Cedar clinician check was free text; the clinician permit's principal was unscoped | Fixed: the check is built in code from a recorded tag shape (`set` or `string`, exact membership, no `like`); the permit is scoped to `principal is AgentCore::OAuthUser`; `agent_sub` is validated against injection; one statement per policy |
| X4. Redaction gaps: JWTs, UUIDs, emails, access keys, client secrets, gateway IDs | Fixed: generic patterns (SHA-256 hashes untouched), named placeholders from stack outputs, and a test that scans all committed evidence |
| X5. Transaction Search restore used the author's committed values | Fixed: a local, git-ignored record keyed by account. Restore and verify fail when this account has no record. |
| X6. The domain prefix fell back to a public default | Fixed: synth and deploy refuse a missing or empty prefix |
| X7. Secrets were deleted by search | Fixed: exact names only |
| X8. The trust-policy wildcard on the gateway name | Fixed: a second pass after D1 binds each role to its exact gateway ID (task 3.1d) |

## Risks / Trade-offs

- [The representation of the `cognito:groups` claim as a principal tag is not documented] → Task 3.2 records it from a real token and a test call. The clinician test expression is passed to D2 as context, never guessed.
- [The service stores the policy text reformatted] → B5 compares the redacted deployed text. If it differs, the article copies the deployed text.
- [Validation flags the overlapping forbids, the group-unless forbid and the agent-principal forbid, as redundant] → Record the finding and stop for a decision. The mode is not changed.
- [The client-credentials token lacks a claim the policy needs] → Task 3.2 records the token before any policy is written. If the agent cannot be named as a principal, stop for a decision.
- [The test configuration that admits the agent is left in place] → The revert is a scripted step. Evidence capture fails unless the final `get-gateway` shows the clinician client only.
- [Eventual consistency after policy or authorizer changes] → The evidence script waits for `ACTIVE` or `READY`, then retries the test call with backoff.
- [Enforcement silently set to LOG_ONLY, at the engine or on a single policy] → Every evidence run captures `get-gateway` and fails if the mode isn't `ENFORCE`.
- [Transaction Search left changed for the whole account] → The previous values are recorded before enabling. Teardown restores them, and the verifier compares the two.
- [Leftover resources] → The teardown verifier lists Cognito pools, gateways, targets, policy engines, policies, Lambda functions, Lambda log groups, IAM roles and log deliveries.
