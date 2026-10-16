# Spec Delta

## Purpose

Keeps a complete, tamper-evident record of each decision outside the agent's control, linked to the trace by hash.

## ADDED Requirements

### Requirement: Each decision writes one evidence record
Each case SHALL write one evidence record holding the packet, the recommendation, citations, policy version, reviewer identity (when a clinician decides), the decision, and the received, recommended, and decided timestamps.

#### Scenario: Record fields
- **WHEN** a case completes
- **THEN** its evidence record contains every listed field

### Requirement: The agent cannot rewrite evidence
Evidence records SHALL be stored write-once under retention that the agent and tool roles cannot overwrite, delete, or bypass.

#### Scenario: Overwrite attempt
- **WHEN** the agent role attempts to overwrite or delete an existing record
- **THEN** the request is refused

### Requirement: Records use per-tenant keys
Each record SHALL be encrypted with the key of the tenant that owns the case.

#### Scenario: Two tenants
- **WHEN** cases from two tenants complete
- **THEN** each record is encrypted under its own tenant's key

### Requirement: The trace carries the record's hash
The trace SHALL carry the SHA-256 of the evidence record, and recomputing the hash from the stored record SHALL match it.

#### Scenario: Hash check
- **WHEN** the stored record is hashed and compared with the trace attribute
- **THEN** they match

### Requirement: Timestamps answer the decision clock
The record SHALL allow elapsed time from receipt to decision to be computed and compared with the standard and expedited windows.

#### Scenario: Elapsed time
- **WHEN** a decided case is checked
- **THEN** elapsed time and the applicable window are reported
