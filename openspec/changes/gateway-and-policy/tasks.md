# Tasks

## 1. Guardrails (before any deploy)

- [ ] 1.1 Python project skeleton:
  - `pyproject.toml` with pinned `aws-cdk-lib`, `aws-cdk.aws-bedrock-agentcore-alpha`, `boto3` and `pytest`
  - a test for the synthetic-data label

  Done when `pytest` passes locally.
- [ ] 1.2 `infra/budget_stack.py`: AWS Budgets alerts at USD 20, USD 50 and USD 100, plus a USD 500 alarm. It is excluded from teardown.
  - Deploy it first, **with Andrew's approval**.
  - Done when a recorded `describe-budgets` listing shows all four.
- [ ] 1.3 `scripts/teardown.py` and `scripts/verify_teardown.py`. The verifier lists every resource type this change creates, including Lambda log groups, and fails on leftovers. It also confirms that the budgets still exist.
  - Done when a unit test with stubbed listings shows the verifier fails on a leftover resource and on a leftover log group.
- [ ] 1.4 The deploy script refuses to run if any budget alert is missing. Verified by a unit test.

## 2. Identity and tools (no deploy yet)

- [ ] 2.1 Cognito stack:
  - a user pool
  - an agent app client (client-credentials grant, resource-server scope)
  - a separate clinician app client
  - the groups `clinician`, `tenant-a` and `tenant-b`
  - synthetic clinician and tenant users

  Done when unit tests with CDK assertions pass.
- [ ] 2.2 `tools/agent_tools.py`: one Lambda handler that dispatches the five tools by name. Four of them return synthetic stub results. Done when unit tests pass for each tool.
- [ ] 2.3 Approval service in `tools/agent_tools.py`:
  - `record_approval(packet_id, packet_hash)` loads the packet from a bundled synthetic fixture (one passing packet, one failing packet)
  - it verifies the SHA-256 of the canonical JSON and re-runs the checks
  - it refuses with a reason on any failure

  Tests:
  - a well-formed call whose stored packet fails its checks is refused and records nothing (B6)
  - a hash mismatch is refused
  - an unknown `packet_id` is refused
  - a passing packet is recorded
- [ ] 2.4 `tools/reviewer_tools.py`: the `record_adverse_determination` stub. Done when its unit test passes.
- [ ] 2.5 Tool schemas in code. `record_approval` declares `packet_id` and `packet_hash` as required strings and has no boolean inputs. Tests assert:
  - the exact five-tool set, with no denial tool present (B1, B2)
  - that schema

## 3. Gateways and policy (deploy, with approval)

- [ ] 3.1 Gateway stack:
  - The agent gateway: MCP, `CUSTOM_JWT`, `allowedClients` set to the agent client.
  - The reviewer gateway: MCP, `CUSTOM_JWT`, `allowedClients` set to the clinician client only.
  - Lambda targets with `GATEWAY_IAM_ROLE`, and explicit log groups.
  - A gateway role with the policy-authorization permissions.

  A CDK assertions test checks it. **Deploy with approval**, then wait for `READY`.
- [ ] 3.2 Get one real token for each client.
  - Record the agent token's `sub` and `client_id` format, and the clinician token's group claim.
  - Write the principal values used by the policies from these records.
  - Stop for a decision if the agent cannot be named as a principal.
- [ ] 3.3 Policy stack: one engine attached to both gateways in `ENFORCE` mode, plus the five policies in proposal.md. Every permit names its principal.
  - Validation runs in the default mode. Any automated-reasoning finding is saved to `evidence/`, and work stops for a decision. The mode is never changed to get past it.
  - **Deploy with approval**, then wait for `ACTIVE`.
- [ ] 3.4 Enable Transaction Search and gateway tracing, so policy decisions appear as spans.

## 4. Evidence

- [ ] 4.1 `scripts/capture_evidence.py` writes:
  - target listings and credential types
  - the app clients (no secrets)
  - `tools/list` per identity
  - policy text, status and findings
  - `get-gateway`, failing unless the mode is `ENFORCE` and the reviewer gateway allows the clinician client only

  Done when the evidence directory exists (B1, B2, B3, A2, A3, A4).
- [ ] 4.2 Recorded calls:
  - **B4, layer 1:** the agent calls `record_adverse_determination` on the reviewer gateway with its own token and is rejected by the inbound authorizer.
  - **B4, layer 2:** add the agent client to the reviewer gateway's `allowedClients` in a test configuration, repeat the call, and record the policy denial. Then revert. Capture `get-gateway` before, during and after. Done only when the final state allows the clinician client only.
  - **B6:**
    - a well-formed `record_approval` call for the failing fixture packet, refused by the approval service
    - a well-formed call for the passing packet, approved
    - a call missing `packet_hash`, denied by policy
  - **B8, first half:** a clinician calls `record_adverse_determination` and is allowed.

  Done when each response, span and metric datapoint is saved.
- [ ] 4.3 B5: copy the deployed forbid text for the agent principal into the article snippet, with no retyping. Confirm the underscore count in the action name from the deployed `tools/list` names. Done when a test that compares the committed snippet with the deployed policy text passes.
- [ ] 4.4 A4: record listings showing separate agent and clinician app clients, every target using `GATEWAY_IAM_ROLE`, and no secret values in tool or target configuration. Done when a test that fails on any secret-like value in the captured configuration passes.
- [ ] 4.5 Model allow-list (M9). Done when:
  - a code test shows an unlisted model is rejected
  - the IAM policy lists exactly the allow-listed model ARNs in us-east-1
- [ ] 4.6 Redact account identifiers and ARNs from the evidence before committing. Done when a test fails on any 12-digit account ID or ARN in `evidence/`.

## 5. Teardown

- [ ] 5.1 Run the teardown, then the verifier. The verifier covers the Lambda log groups and confirms that the budgets remain. Done when verification passes the same day and its output is saved to the evidence directory.

## Workflow follow-up

- Update `openspec/claims-ledger.md` with the evidence paths and statuses for B1–B6, B8 (partial), A2, A3, A4 and M9.
