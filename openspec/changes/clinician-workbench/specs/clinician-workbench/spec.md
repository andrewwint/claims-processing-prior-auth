# Spec Delta

## Purpose

Gives the clinician one local page to review the case the agent built and to record the decision, through the reviewer gateway under the clinician's own token.

## ADDED Requirements

### Requirement: Clinicians sign in through a standard OAuth library
The page SHALL sign the clinician in through the hosted UI with authorization code, PKCE and `state`, handled by a standard OAuth library. Its callback SHALL be bound to 127.0.0.1.

#### Scenario: State mismatch
- **WHEN** the callback's `state` does not match the one the page issued
- **THEN** sign-in is refused

### Requirement: The reviewer gateway holds both clinician decision tools
The reviewer gateway SHALL expose `record_adverse_determination` and `record_clinician_approval`, each permitted for clinicians only.

#### Scenario: Agent refused, clinician allowed
- **WHEN** the agent and then a clinician call `record_adverse_determination`
- **THEN** the agent is refused at the authorizer and by Cedar, and the clinician's call succeeds

### Requirement: A denial requires a reason, enforced server-side
`record_adverse_determination` SHALL mark `reason` required in its schema. Its Lambda SHALL refuse an empty or whitespace-only reason.

#### Scenario: Whitespace reason
- **WHEN** the tool is called with a reason of only spaces
- **THEN** the Lambda refuses it and records nothing

### Requirement: The packet view distinguishes failure states
The page SHALL label "Not found", "extraction failed", and "no verified policy" distinctly, and SHALL mark the model summary as a model summary.

#### Scenario: Extraction failed
- **WHEN** a case was routed because extraction failed
- **THEN** the view shows "Extraction failed" with the stop reason, not "Not found"

### Requirement: Decisions are chained records
Each clinician decision SHALL write a decision record that carries the recommendation record's hash. The record SHALL label the reviewer identity as the clinician app reports it.

#### Scenario: Decision recorded
- **WHEN** a clinician approves or denies
- **THEN** a decision record exists with the decision, the reason, the decision time, the identity label and the recommendation record's hash
