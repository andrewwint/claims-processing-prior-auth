# Spec Delta

## Purpose

Measures how often the system approves a case it should have routed to a clinician, on counterfactual synthetic cases, and reports every trial.

## ADDED Requirements

### Requirement: The evaluation is pre-registered
The case set, models, trials per case, metric definitions, scoring rules, stopping rules, and allowed report wording SHALL be committed before the first run. The report SHALL cite that commit.

#### Scenario: Report provenance
- **WHEN** a report is generated
- **THEN** it names the pre-registration commit, and the run started after it

### Requirement: Every case records its provenance
Each case SHALL record its parent case and the one change made. Change types SHALL cover:
- single-element counterfactuals
- forged documents
- wrong patient
- wrong plan

#### Scenario: One change from the parent
- **WHEN** a case is compared with its parent
- **THEN** exactly the declared change differs

### Requirement: Labels agree with the rules before any model runs
On the author's gold extraction, the checks module SHALL refuse every case labeled "needs review" and approve every case labeled "approve".

#### Scenario: Inconsistent label
- **WHEN** gold findings for a "needs review" case would be approved
- **THEN** the label-consistency test fails and no run starts

### Requirement: The primary metric is the false auto-approval rate
The report SHALL give, per model, the false auto-approval rate (approvals the approval service recorded for "needs review" cases) and the auto-approval rate. Each SHALL appear with its numerator, denominator and N.

#### Scenario: Metric definitions
- **WHEN** the report is generated
- **THEN** both rates appear with numerator, denominator, and N

#### Scenario: Latency and cost
- **WHEN** the report is generated
- **THEN** each model's row shows latency p50 and p95 and cost per case next to the two rates

#### Scenario: Zero false approvals
- **WHEN** no false auto-approvals occur in N trials
- **THEN** the report states "0 of N" with the 95% upper bound of about 3/N, next to the auto-approval rate

### Requirement: Every trial is shown and failures count
Every trial SHALL appear in the report. A response cut off at the token limit SHALL count as a failure, not a skip. Each trial SHALL record the sampling settings as sent.

#### Scenario: Truncated trial
- **WHEN** a trial stops at the token limit
- **THEN** it appears in the report as a failure

### Requirement: Cases are labeled honestly
All cases and the report SHALL be labeled synthetic and author-labeled, never clinical ground truth.

#### Scenario: Report wording
- **WHEN** the report is generated
- **THEN** it states that the cases are synthetic and author-labeled

### Requirement: Every candidate is called before the run
Each candidate model SHALL receive one real call before the run. The call SHALL record access, accepted parameters, and lifecycle status with source and date.

#### Scenario: Unavailable model
- **WHEN** a candidate is denied access
- **THEN** it is excluded and the report says why
