# Spec Delta

## Purpose

Defines how payer criteria and chart evidence become a cited, checked case packet, how the approve-or-route decision is made in code, and how the approval service re-derives every verdict from trusted sources.

## ADDED Requirements

### Requirement: Payer policy compiles to one verified file per procedure
Each synthetic payer policy SHALL compile into one criteria file per (payer, procedure). Each criterion SHALL carry the policy version and its location in the source.

#### Scenario: Rebuild is reproducible
- **WHEN** the compiler runs on the committed source policies
- **THEN** it reproduces the committed criteria files exactly

### Requirement: One checks module serves the agent and the approval service
The schema, source-match and same-patient checks, and the recomputation of criterion status, SHALL live in one module. The runtime and the approval service SHALL both import it.

#### Scenario: Same module
- **WHEN** the decision function and the approval service are loaded
- **THEN** they reference the same checks module, and the deployed bundle holds a byte-identical copy

### Requirement: Source match is exact at the cited location
A finding's value SHALL match only if it occurs as an exact substring of the text at its cited document, page and line, after Unicode NFC normalization and nothing else. The value SHALL have at least four non-whitespace characters.

#### Scenario: Value not at its location
- **WHEN** a value appears in the document but not on the cited line
- **THEN** the source-match check fails

#### Scenario: Near miss
- **WHEN** the value differs from the cited text by one character or by case
- **THEN** the source-match check fails

#### Scenario: Trivial value
- **WHEN** the value is empty or has fewer than four non-whitespace characters
- **THEN** the source-match check fails

### Requirement: Same patient is derived from the chart index
The same-patient check SHALL take each cited document's patient from the chart index by `doc_id` and compare it with the request record's patient. It SHALL ignore any patient ID in the packet or supplied by the model.

#### Scenario: Another patient's document, relabeled
- **WHEN** a finding cites another patient's document and the packet labels it with this case's patient ID
- **THEN** the same-patient check fails

#### Scenario: Unknown document
- **WHEN** a finding cites a `doc_id` that is not in the chart index
- **THEN** the same-patient check fails

### Requirement: The decision is a code function the model cannot bypass
The approve-or-route decision SHALL be made by `decide(packet)` from the checks module's recomputation. The model SHALL receive no tools and SHALL NOT be able to call `record_approval` or `route_to_reviewer`.

#### Scenario: Approval path
- **WHEN** every compiled criterion has at least one finding and every finding verifies
- **THEN** `decide` returns approve and the wrapper calls `record_approval` with the packet ID and hash

#### Scenario: Routing path
- **WHEN** any criterion is not Met or any check fails
- **THEN** `decide` returns route with the gaps marked

#### Scenario: Model has no tools
- **WHEN** the model is invoked
- **THEN** the request carries no tool configuration

### Requirement: Model prose never affects a decision
The packet's prose SHALL be stored as a labeled model summary, and no decision SHALL depend on it.

#### Scenario: Summary changed
- **WHEN** the model summary is altered or removed
- **THEN** `decide` and the approval service return the same result

### Requirement: The approval service rebuilds the verdict from trusted sources
`record_approval` SHALL load the stored packet and verify its hash. It SHALL then rebuild the verdict:
- criteria from the compiled policy for the request record's (payer, CPT)
- every finding re-verified against the chart store
- the patient derived from the chart index

It SHALL ignore status labels and patient IDs in the packet. It SHALL record the approval only if every criterion is Met and nothing failed.

#### Scenario: Forged packet
- **WHEN** a stored packet is marked all Met, carries made-up findings, and is called with its valid hash
- **THEN** the approval service refuses it and records nothing

#### Scenario: Packet altered after hashing
- **WHEN** the stored packet changes after its hash was computed
- **THEN** the approval service refuses it

#### Scenario: Missing packet
- **WHEN** `packet_id` names no stored packet
- **THEN** the approval service refuses the call

#### Scenario: Well-formed call for a failing packet
- **WHEN** `record_approval` is called with a valid `packet_id` and matching `packet_hash`, but the rebuilt verdict has an unmet criterion
- **THEN** the call passes policy and the approval service refuses it
