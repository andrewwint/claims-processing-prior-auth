# Spec Delta

## Purpose

Lets telemetry answer "what happened" without holding chart text, and proves it with a scan that is shown to work.

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
Synthetic charts SHALL contain unique canary strings. A scan of the runtime logs, span records, and every tool Lambda log group SHALL find none of them.

#### Scenario: Scan after the demo cases
- **WHEN** the canary scan runs after the demo cases
- **THEN** it reports zero canary hits across every scanned source
