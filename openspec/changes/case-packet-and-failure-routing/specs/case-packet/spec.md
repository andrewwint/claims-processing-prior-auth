# Spec Delta

## Purpose

Defines how payer criteria and chart evidence become a cited, checked case packet, and the only condition under which the agent may record an approval.

## ADDED Requirements

### Requirement: Payer policy compiles to one verified file per procedure
Each synthetic payer policy SHALL compile into one criteria file per (payer, procedure), and each criterion SHALL carry the policy version and its location in the source.

#### Scenario: Rebuild is reproducible
- **WHEN** the compiler runs on the committed source policies
- **THEN** it reproduces the committed criteria files exactly

### Requirement: Every finding cites its source
Each extracted finding SHALL cite the source document, the page or line, and the patient ID of the record it came from.

#### Scenario: Missing citation
- **WHEN** a finding has no source
- **THEN** the packet marks the criterion "Not found" rather than "Met"

### Requirement: Three checks run before the packet moves
The packet SHALL pass three checks before any decision: it matches its schema; every extracted value appears in the source it cites; every citation comes from the same patient's record. A failed check SHALL route the case to a reviewer with the failed check named.

#### Scenario: Value not in its source
- **WHEN** an extracted value does not appear in its cited source
- **THEN** the source-match check fails and the case routes to a reviewer

#### Scenario: Citation from another patient
- **WHEN** a citation points at a different patient's record
- **THEN** the same-patient check fails and the case routes to a reviewer

#### Scenario: Malformed output
- **WHEN** the packet does not match its schema
- **THEN** the schema check fails and the case routes to a reviewer

### Requirement: Approval only when all criteria are met and all checks pass
The agent SHALL call `record_approval` only when every criterion is Met and all three checks passed; otherwise it SHALL call `route_to_reviewer` with the gaps marked. The call SHALL carry only `packet_id` and `packet_hash`. The approval service SHALL load the stored packet, verify its hash, re-run the checks, and refuse to record an approval that does not satisfy the condition.

#### Scenario: Well-formed call for a failing packet
- **WHEN** `record_approval` is called with a valid `packet_id` and matching `packet_hash`, but the stored packet has an unmet criterion
- **THEN** the call passes policy and the handler refuses it and routes to a reviewer
