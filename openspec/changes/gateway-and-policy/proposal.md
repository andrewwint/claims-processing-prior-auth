# Proposal

## Why

The article's central claim is that the agent cannot deny care, and that this is enforced outside the prompt, in layers:

- The agent's gateway has no denial tool.
- The reviewer gateway, which holds that tool, admits clinician clients only.
- A Cedar policy forbids the adverse-determination action for the agent's identity.

The agent may submit an approval, but only by naming a stored packet. The approval service re-runs the checks on that packet itself before it records anything. This change deploys these boundaries and records the evidence. It is priority 1.

## What Changes

- **Guardrails, before any deploy:**
  - AWS Budgets alerts at USD 20, USD 50 and USD 100, plus a USD 500 alarm. The budgets persist across teardowns until the project ends.
  - A teardown script with a verification step. It lists every resource type, including the Lambda log groups, and fails if anything remains.
  - Every deploy is gated on Andrew's explicit approval.
- **Identity** (one Cognito user pool, synthetic data; self-signup disabled, so only an administrator can create users; synthetic users' passwords live in Secrets Manager, never in the repository):
  - **Agent:** a Cognito app client that uses the client-credentials grant. It is not a user. The format of its token's `sub` and `client_id` is recorded from a real token and used as the forbid principal.
  - **Clinician:** a separate app client used by synthetic clinician users in the `clinician` group.
  - **Tenants:** synthetic users in the groups `tenant-a` and `tenant-b`.
- **Agent gateway** (MCP, `CUSTOM_JWT`; allowed clients: the agent app client):
  - One Lambda target exposing exactly five tools: `check_eligibility`, `fetch_policy_criteria`, `extract_clinical_evidence`, `record_approval` and `route_to_reviewer`.
  - `record_approval` takes `packet_id` and `packet_hash`, both required strings. It takes no booleans.
  - The approval Lambda:
    - loads the stored packet (a synthetic fixture in this change)
    - verifies the hash
    - re-runs the checks
    - refuses the call if any step fails
  - The other four tools are stubs backed by synthetic data. Their real logic arrives in `case-packet-and-failure-routing`.
- **Reviewer gateway** (MCP, `CUSTOM_JWT`; allowed clients: the clinician app client only): one Lambda target exposing `record_adverse_determination`.
- **Policy engine:** one engine attached to both gateways in `ENFORCE` mode. Policies are validated in the default mode, and any automated-reasoning finding is recorded rather than bypassed. Every permit names its principal explicitly.
  - `permit`: the agent principal may call the four non-approval tools on the agent gateway.
  - `permit`: the agent principal may call `record_approval` on the agent gateway when `packet_id` and `packet_hash` are both present.
  - `permit`: the clinician group may call `record_adverse_determination` on the reviewer gateway.
  - `forbid`: `record_adverse_determination` on the reviewer gateway, unless the principal is in the clinician group.
  - `forbid`: `record_adverse_determination` on the reviewer gateway when the principal is the agent identity. This is the article's snippet, and B5 must match it by copy.
- **Evidence capture scripts** record:
  - target listings and `tools/list`
  - policy listings and their validation findings
  - `get-gateway`, showing `ENFORCE` and each gateway's allowed clients
  - allowed, denied and refused calls, with their spans, metrics and log lines
- **Transaction Search** is an account-wide setting. Its current state and indexing percentage are recorded before it is enabled, and teardown restores them.
- **Evidence redaction** replaces ARNs, account IDs and client IDs with placeholders. It never changes action names.
- **Model allow-list:** one list in code and the matching IAM policy, with the Region pinned to us-east-1.
- **Out of scope:** the agent runtime, real tool logic (apart from the approval service's checks against a fixture), the evidence store, the workbench and the harness.

## Claims delivered

- B1, B2, B3, B4 (both layers), B5, B6, A2, A3, A4 and M9.
- B8 in part: the agent-side denial. The clinician-side workbench call is completed in `clinician-workbench`.

## Capabilities

### New Capabilities

- `tool-boundary`: which identity can reach which gateway and tool, the policies on approval and adverse determination, and server-side approval verification.
- `deployment-guardrails`: budget alerts, the approval gate, and verified teardown.

### Modified Capabilities

None.

## Impact

- **New code:** `infra/` (Python CDK), `tools/` (Lambda handlers and a synthetic packet fixture), `scripts/` (evidence capture and teardown), and `tests/`.
- **AWS resources:**
  - Cognito: a user pool and two app clients.
  - Two AgentCore Gateways, plus a policy engine and its policies.
  - Two Lambda functions and their log groups.
  - IAM roles.
- **Teardown:** removes every resource above. The Budgets alerts stay in place until the project ends.
