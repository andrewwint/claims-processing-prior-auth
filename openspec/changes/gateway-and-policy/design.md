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
- **Packet store:** in this change it is a synthetic fixture bundled with the Lambda, with one passing packet and one failing packet. `case-packet-and-failure-routing` replaces the fixture with the real packet store and the real checks.
- **Why.** Policy checks the shape of a call, and only the server can check its truth (B7). Nothing the agent asserts can produce an approval.
- **Alternative considered.** A temporal policy that requires earlier passing check-tool responses in the same session. Deferred: it adds a session header to every call, extra IAM, and an unconfirmed detail about how tool output is matched.

### D3. Identities and principals

- **Agent.** A Cognito app client with the client-credentials grant and a resource-server scope. It has no user and no group.
  - Task 3.2 records the token's `sub` and `client_id` from a real token. The expectation is that `sub` equals the client ID for this grant, but this is confirmed, not assumed.
  - The explicit forbid uses that value as `AgentCore::OAuthUser::"<sub>"`.
- **Clinician.** A separate app client used by synthetic users in the `clinician` group.
  - The claim that carries group membership (`cognito:groups`) and how it maps to a principal tag are confirmed from a real token before policies are written.
  - Synthetic tenant users are in the `tenant-a` and `tenant-b` groups.
- **Explicit principals.** Every permit names its principal: the agent's `sub`, or the clinician group tag. There is no permit for all principals.

### D4. Infrastructure as code

- **Tools.** Python CDK. `aws-cdk-lib` stable constructs are used for Gateway and GatewayTarget. Policy uses the L1 `CfnPolicyEngine` and `CfnPolicy`.
- **Two stacks** (the deploy has two passes):
  1. Cognito, the Lambdas (each with an explicit log group), both gateways and their targets.
  2. The policy engine and policies, attached through the L1 `CfnGateway.policyEngineConfiguration` with `mode: ENFORCE` set explicitly.
- **Budgets** live in their own stack. It is deployed first and excluded from teardown.
- **Validation mode.** The default mode. An automated-reasoning finding is recorded, and work stops for a decision. The mode is never changed to get past a finding.
- **Gateway role.** It includes `bedrock-agentcore:AuthorizeAction`, `PartiallyAuthorizeActions` and `GetPolicyEngine`. These are missing from default roles, and without them every call is denied.
- **No secrets in the agent.** Both Lambda targets use `GATEWAY_IAM_ROLE` as their credential. The agent's client secret is stored in Secrets Manager for the caller that obtains tokens. It is never placed in tool configuration (A4).

### D5. Evidence is captured by scripts, not by hand

`scripts/capture_evidence.py` uses the pinned boto3 release, because the local AWS CLI is too old for the policy APIs. It writes to `evidence/<date>/`:
- target listings, tool schemas and target credential types
- the Cognito app clients (IDs and grant types, no secrets)
- paginated `tools/list` results per identity
- policy definitions, status and validation findings
- `get-gateway` (mode and allowed clients)
- raw responses for each allowed, rejected, denied and refused call
- matching span records and `DenyDecisions` and `AllowDecisions` datapoints

Account identifiers and ARNs are redacted before anything is committed.

## Risks / Trade-offs

- [Validation flags the overlapping forbids, the group-unless forbid and the agent-principal forbid, as redundant] → Record the finding and stop for a decision. The mode is not changed.
- [The client-credentials token lacks a claim the policy needs] → Task 3.2 records the token before any policy is written. If the agent cannot be named as a principal, stop for a decision.
- [The test configuration that admits the agent is left in place] → The revert is a scripted step. Evidence capture fails unless the final `get-gateway` shows the clinician client only.
- [Eventual consistency after policy or authorizer changes] → The evidence script waits for `ACTIVE` or `READY`, then retries the test call with backoff.
- [Enforcement silently set to LOG_ONLY] → Every evidence run captures `get-gateway` and fails if the mode isn't `ENFORCE`.
- [Leftover resources] → The teardown verifier lists Cognito pools, gateways, targets, policy engines, policies, Lambda functions, Lambda log groups, IAM roles and log deliveries.
