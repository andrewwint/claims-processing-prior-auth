# Spec Delta

## Purpose

Lets telemetry answer "what happened" without holding any chart text.

## ADDED Requirements

### Requirement: Telemetry holds identifiers, timings, and hashes only
Trace spans SHALL carry case ID, step, model ID, token counts, latency, stop reason, and content hashes, and SHALL NOT carry chart text, prompts, or completions.

#### Scenario: Span attributes
- **WHEN** a case's spans are exported
- **THEN** they contain the listed attributes and no content attributes

### Requirement: Cleanliness is proven by a canary scan
Synthetic charts SHALL contain unique canary strings, and a scan of every log group and span record the system writes SHALL find none of them.

#### Scenario: Scan after a run
- **WHEN** the canary scan runs after a set of cases
- **THEN** it reports zero canary hits across all scanned sources

### Requirement: Memory is not used for patient data
The system SHALL NOT create or call AgentCore Memory, and roles SHALL deny Memory actions.

#### Scenario: Memory evidence
- **WHEN** memories are listed and the agent code and roles are inspected
- **THEN** no memory exists, no memory client is used, and Memory actions are denied
