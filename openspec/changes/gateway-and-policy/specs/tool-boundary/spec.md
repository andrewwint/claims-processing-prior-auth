# Spec Delta

## Purpose

Defines which identity can reach which gateway and tool, the policies on approval and adverse determination, and the server-side checks that stand behind approval. Every rule here is enforced at the gateway, the policy engine, or the tool service, never in the prompt.

## ADDED Requirements

### Requirement: The agent's gateway has no denial tool
The agent's gateway SHALL register exactly five tools: `check_eligibility`, `fetch_policy_criteria`, `extract_clinical_evidence`, `record_approval`, `route_to_reviewer`. It SHALL NOT register `record_adverse_determination` or any other tool that denies, delays, or modifies care.

#### Scenario: Registered tool set
- **WHEN** the agent gateway's targets and tool schemas are listed
- **THEN** exactly the five tools are registered and no denial tool appears

### Requirement: The agent is a separate machine identity
The agent SHALL authenticate as a Cognito app client using the client-credentials grant. That client SHALL be separate from the clinician app client. The forbid principal SHALL be written from the `sub` and `client_id` format recorded from a real agent token.

#### Scenario: Token format recorded
- **WHEN** a real agent token is issued
- **THEN** its `sub` and `client_id` values and format are recorded before any policy is written

### Requirement: The reviewer gateway admits clinician clients only
The reviewer gateway's inbound authorizer SHALL list only the clinician app client as an allowed client.

#### Scenario: Agent token rejected at the door
- **WHEN** the agent calls the reviewer gateway with its own token
- **THEN** the gateway rejects the request before any policy is evaluated

### Requirement: Only clinicians can record an adverse determination
The policy engine SHALL forbid `record_adverse_determination` unless the principal is in the clinician group. It SHALL also explicitly forbid that action when the principal is the agent identity. A permit SHALL allow clinicians to call it. Every permit SHALL name its principal explicitly.

#### Scenario: Agent identity is denied by policy
- **WHEN** the agent client is temporarily admitted to the reviewer gateway in a test configuration and calls `record_adverse_determination`
- **THEN** the call is denied by policy, the decision names the forbid policy, and the test configuration is then reverted

#### Scenario: Clinician is allowed
- **WHEN** a clinician identity calls `record_adverse_determination` with a reason
- **THEN** the call is allowed

### Requirement: Approval names a stored packet and is verified server-side
`record_approval` SHALL take `packet_id` and `packet_hash` as required strings and no boolean inputs. Policy SHALL permit it only for the agent principal when both fields are present. The approval service SHALL:
1. load the stored packet
2. verify that its hash matches `packet_hash`
3. re-run the checks

It SHALL refuse the call if any step fails.

#### Scenario: Malformed call
- **WHEN** the agent calls `record_approval` without `packet_id` or `packet_hash`
- **THEN** the call is denied by policy

#### Scenario: Well-formed call for a failing packet
- **WHEN** the agent makes a well-formed call whose stored packet fails its checks
- **THEN** the approval service refuses it, records nothing, and returns a reason

#### Scenario: Hash mismatch
- **WHEN** `packet_hash` does not match the stored packet
- **THEN** the approval service refuses the call

#### Scenario: Passing packet
- **WHEN** the agent makes a well-formed call for a stored packet whose hash matches and whose checks pass
- **THEN** the approval is recorded

### Requirement: Enforcement is on
The policy engine SHALL be attached to both gateways in enforce mode. Evidence SHALL record the mode at the time each test call is made.

#### Scenario: Mode evidence
- **WHEN** evidence is captured
- **THEN** it includes the gateway configuration showing enforce mode for the attached engine

### Requirement: Policy validation is not bypassed
Policies SHALL be validated in the default mode. Any automated-reasoning finding SHALL be recorded, and the validation mode SHALL NOT be changed to get past it.

#### Scenario: Finding raised
- **WHEN** validation reports a finding on a policy
- **THEN** the finding is saved to the evidence directory, and work stops for a decision

### Requirement: Models come from one allow-list in a pinned Region
Model invocation SHALL be limited to an allow-listed set of model identifiers in us-east-1. The limit SHALL be enforced both in code and by the IAM policy of every role that invokes models.

#### Scenario: Unlisted model
- **WHEN** code requests a model that is not on the allow-list
- **THEN** the request is rejected before any call is made
