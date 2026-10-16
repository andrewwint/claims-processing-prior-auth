# Spec Delta

## Purpose

Makes every failure end at a person: no failure may produce an approval or an adverse outcome, and each step has a written rule for empty output.

## ADDED Requirements

### Requirement: Each failure mode has one destination
Evidence-extraction failure, a model response with no text, missing verified policy criteria, and denied model access SHALL each produce the outcome named in the article's failure table: route to reviewer labeled "extraction failed"; route to reviewer with the stop reason; route to reviewer labeled "no verified policy"; fail loudly and alert the operator.

#### Scenario: Extraction fails
- **WHEN** evidence extraction raises an error
- **THEN** the case routes to a reviewer labeled "extraction failed"

#### Scenario: No text from the model
- **WHEN** the model returns no text or stops at the token limit before producing text
- **THEN** the case routes to a reviewer with the stop reason

#### Scenario: No verified policy
- **WHEN** no compiled criteria exist for the payer and procedure
- **THEN** the case routes to a reviewer labeled "no verified policy"

#### Scenario: Model access denied
- **WHEN** the model call is denied access
- **THEN** the run fails loudly and the operator alarm fires

### Requirement: Each step has its own empty-output rule
Every step that can return empty output SHALL have a written rule for what empty means at that step, and a test for it.

#### Scenario: Empty criteria versus empty evidence
- **WHEN** criteria lookup returns nothing, or evidence extraction returns nothing
- **THEN** each follows its own documented rule

### Requirement: A failure never pushes a case toward denial
No injected failure SHALL produce an approval or an adverse outcome; every failure SHALL end as "routed to reviewer" or "operator alert".

#### Scenario: Any injected failure
- **WHEN** any failure is injected at any step
- **THEN** the outcome is routed-to-reviewer or operator-alert
