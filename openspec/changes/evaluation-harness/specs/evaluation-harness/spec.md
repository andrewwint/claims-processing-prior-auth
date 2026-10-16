# Spec Delta

## Purpose

Measures how often the agent approves a case it should have routed to a clinician, on counterfactual synthetic cases, and reports every trial.

## ADDED Requirements

### Requirement: The evaluation is pre-registered
The case set, models, trials per case, metric definitions, scoring rules, and stopping rules SHALL be committed before the first run, and the report SHALL cite that commit.

#### Scenario: Report provenance
- **WHEN** a report is generated
- **THEN** it names the pre-registration commit, and the run started after it

### Requirement: Cases are counterfactual and labeled honestly
Each counterfactual case SHALL differ from an approvable parent by exactly one removed piece of required evidence and SHALL record the parent and the removed element. All cases SHALL be labeled synthetic and author-labeled, never clinical ground truth.

#### Scenario: One change from the parent
- **WHEN** a counterfactual case is compared with its parent
- **THEN** exactly the declared element differs

### Requirement: The primary metric is the false auto-approval rate
The report SHALL give the false auto-approval rate (agent approvals of cases whose author label is "needs review") and the auto-approval rate, each with its N, per model.

#### Scenario: Metric definitions
- **WHEN** the report is generated
- **THEN** both rates appear with numerator, denominator, and N

### Requirement: Every trial is shown and failures count
Every trial SHALL appear in the report; a response cut off at the token limit SHALL count as a failure, not a skip; and each trial SHALL record the model's sampling settings as sent.

#### Scenario: Truncated trial
- **WHEN** a trial stops at the token limit
- **THEN** it appears in the report as a failure

### Requirement: Every candidate is called before the run
Each candidate model SHALL receive one real call before the run, recording access, accepted parameters, and lifecycle status with its source and date.

#### Scenario: Unavailable model
- **WHEN** a candidate is denied access
- **THEN** it is excluded and the report says why
