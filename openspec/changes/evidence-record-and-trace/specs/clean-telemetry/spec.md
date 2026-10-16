# Spec Delta

## Purpose

Lets telemetry answer "what happened" without holding any chart text, and proves it with a scan that is shown to work.

## ADDED Requirements

### Requirement: Telemetry holds identifiers, timings, and hashes only
Trace spans SHALL carry the case ID, step, model ID, token counts, latency, stop reason, content hashes and record hashes. They SHALL NOT carry chart text, prompts or completions.

#### Scenario: Span attributes
- **WHEN** a case's spans are exported
- **THEN** they contain the listed attributes and no content attributes

### Requirement: The canary scan is shown to find planted canaries
Before a clean result is trusted, the scan SHALL find a canary planted in a span and one planted in a log line.

#### Scenario: Positive control
- **WHEN** a canary is planted in one span and one log line and the scan runs
- **THEN** the scan reports both

### Requirement: Cleanliness is proven by a canary scan
Synthetic charts SHALL contain unique canary strings. A scan of the runtime logs, span records, gateway logs, both tool Lambda log groups, and the output of injected error paths SHALL find none of them.

#### Scenario: Scan after a run
- **WHEN** the canary scan runs after a set of cases with a failure injected at each step
- **THEN** it reports zero canary hits across every scanned source

### Requirement: Memory is not used for patient data
The system SHALL NOT create or call AgentCore Memory, and roles SHALL deny Memory actions.

#### Scenario: Memory evidence
- **WHEN** memories are listed and the agent code and roles are inspected
- **THEN** no memory exists, no memory client is used, and Memory actions are denied
