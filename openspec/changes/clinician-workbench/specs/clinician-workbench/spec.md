# Spec Delta

## Purpose

Gives the clinician a single place to review the case the agent built and to record the decision under their own identity.

## ADDED Requirements

### Requirement: Clinicians see only their tenant's routed cases
The workbench SHALL require clinician sign-in and SHALL list only routed cases owned by the clinician's tenant, looked up by exact identifiers.

#### Scenario: Other tenant's case
- **WHEN** a tenant-a clinician requests a tenant-b case by ID
- **THEN** the request is refused

### Requirement: The packet is shown with its sources and gaps
The workbench SHALL show every criterion with its evidence, source, and status, and any failure label or gap the agent recorded.

#### Scenario: Routed for missing evidence
- **WHEN** a case was routed with a criterion "Not found"
- **THEN** the gap is shown next to that criterion

### Requirement: Decisions are recorded under the clinician's identity
Approval and adverse-determination decisions SHALL be made through the reviewer gateway with the clinician's own token, an adverse determination SHALL require a reason, and the evidence record SHALL capture the reviewer identity and decision time.

#### Scenario: Adverse determination without a reason
- **WHEN** a clinician submits an adverse determination with no reason
- **THEN** the workbench refuses to submit it

#### Scenario: Decision recorded
- **WHEN** a clinician records a decision
- **THEN** the evidence record shows the clinician's identity and the decision timestamp
