# Spec Delta

## Purpose

Keeps cloud work bounded and reversible: spend alerts exist before anything is deployed, every deploy is approved, and teardown is verified.

## ADDED Requirements

### Requirement: Budget alerts exist before the first deploy
Budget alerts SHALL exist at USD 20, USD 50 and USD 100 of monthly spend, plus a USD 500 alarm, before any other resource is deployed. The budgets SHALL persist across teardowns until the project ends.

#### Scenario: Deploy without budget
- **WHEN** the deploy script runs and any of the budget alerts is missing
- **THEN** the deploy stops before creating resources

#### Scenario: Teardown keeps budgets
- **WHEN** the teardown runs
- **THEN** the budget alerts still exist afterward

### Requirement: Teardown is verified
A teardown script SHALL remove every resource this project deploys, including Lambda log groups. It SHALL then verify, by listing each resource type, that none remain.

#### Scenario: Leftover resource
- **WHEN** any project resource still exists after teardown
- **THEN** verification fails and names the resource

#### Scenario: Leftover log group
- **WHEN** a Lambda log group for a project function still exists after teardown
- **THEN** verification fails and names the log group

### Requirement: Data is synthetic
Every document, member, and case used by this project SHALL be synthetic and labeled as synthetic.

#### Scenario: Case files
- **WHEN** case or chart files are added
- **THEN** each carries a synthetic-data label checked by a test
