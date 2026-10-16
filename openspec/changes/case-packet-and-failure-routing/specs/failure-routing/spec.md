# Spec Delta

## Purpose

Makes every failure end at a person. No failure may produce an approval or an adverse outcome. Each step has its own written rule for empty output, and every session ends in exactly one terminal outcome.

## ADDED Requirements

### Requirement: Each step follows its own empty-output rule
Each step SHALL follow its own row of the per-step table in `docs/empty-output-rules.md`. No step SHALL use a shared default, and each row SHALL have a test.

#### Scenario: Zero findings
- **WHEN** extraction returns valid output with no findings for a criterion
- **THEN** that criterion is "Not found" and the case continues

#### Scenario: Truncated extraction
- **WHEN** the extraction response stops at the token limit
- **THEN** the case routes to a reviewer labeled "extraction failed", with the stop reason

#### Scenario: Malformed extraction
- **WHEN** the extraction output does not parse against its schema
- **THEN** the case routes to a reviewer labeled "extraction failed"

#### Scenario: No text
- **WHEN** the model returns no text
- **THEN** the case routes to a reviewer labeled "extraction failed", with the stop reason

#### Scenario: No verified policy
- **WHEN** no compiled criteria exist for the payer and procedure
- **THEN** the case routes to a reviewer labeled "no verified policy"

#### Scenario: Summary missing
- **WHEN** the summary step returns nothing or fails
- **THEN** the packet remains valid, the summary is marked missing, and the decision is unchanged

#### Scenario: Eligibility unknown
- **WHEN** the eligibility lookup returns nothing or fails
- **THEN** the case routes to a reviewer labeled "eligibility unknown"

### Requirement: Denied model access alerts an operator
A denied model call SHALL end the session with an operator alert and emit the operator metric that drives the CloudWatch alarm `prior-auth-model-access-denied`. There is no SNS topic.

#### Scenario: Model access denied
- **WHEN** the model call is denied access
- **THEN** the session's outcome is `operator_alert` and the operator metric is emitted

### Requirement: Every session ends in exactly one terminal outcome
Every session SHALL end in exactly one of `approved`, `routed` or `operator_alert`. A session that ends without one SHALL become `needs_review` and be routed. A second terminal outcome SHALL be refused and logged.

#### Scenario: No outcome reached
- **WHEN** a session ends through an exception or an early return without a terminal outcome
- **THEN** its outcome is `needs_review` and the case is routed to a reviewer

#### Scenario: Second outcome attempted
- **WHEN** code tries to set a terminal outcome after one is already set
- **THEN** the attempt is refused, logged as an invariant violation, and the first outcome stands

### Requirement: A failure never pushes a case toward denial
No injected failure SHALL produce an approval or an adverse outcome. Every failure SHALL end as routed, needs review, or operator alert.

#### Scenario: Any injected failure
- **WHEN** any failure is injected at any step
- **THEN** the outcome is routed, needs review, or operator alert, and there is exactly one
