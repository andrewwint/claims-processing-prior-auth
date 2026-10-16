# Spec Delta

## Purpose

Gives the clinician a single place to review the case the agent built and to record the decision under their own identity, with identity and tenant taken only from their validated token.

## ADDED Requirements

### Requirement: Clinicians sign in with authorization code and PKCE
The clinician client SHALL allow only the authorization-code grant with a localhost callback. Its only password flow SHALL be SRP.

#### Scenario: Client configuration
- **WHEN** the clinician app client is synthesized
- **THEN** its OAuth flows are code only, its callback is localhost only, and `USER_PASSWORD_AUTH` is not enabled

### Requirement: Clinicians see only their tenant's routed cases
The tenant SHALL come only from the clinician's validated token claims. Every read SHALL use the exact case ID within that tenant's queue.

#### Scenario: Other tenant's case
- **WHEN** a tenant-a clinician requests a tenant-b case by its exact ID
- **THEN** the request is refused

### Requirement: The queue tenant comes from the request record
`route_to_reviewer` SHALL write only under `queue/`, using the tenant from the request record and never a value from the model.

#### Scenario: Model-supplied tenant
- **WHEN** a route call carries a tenant value
- **THEN** it is ignored and the request record's tenant is used

### Requirement: The packet view distinguishes failure states
The workbench SHALL label "Not found", "extraction failed", and "no verified policy" distinctly, and SHALL mark the model summary as a model summary.

#### Scenario: Extraction failed
- **WHEN** a case was routed because extraction failed
- **THEN** the view shows "Extraction failed" with the stop reason, not "Not found"

#### Scenario: Model summary
- **WHEN** a packet has a summary
- **THEN** it appears inside a box labeled as a model summary not used for any decision

### Requirement: A denial requires a reason, enforced server-side
`record_adverse_determination` SHALL mark `reason` required in its schema. Its Lambda SHALL refuse an empty or whitespace-only reason.

#### Scenario: Whitespace reason
- **WHEN** the tool is called with a reason of only spaces
- **THEN** the Lambda refuses it and records nothing

### Requirement: Clinician approval is a separate, clinician-only tool
Clinician approval SHALL be a separate reviewer-gateway tool. It SHALL be permitted only for the clinician group, and it SHALL write a decision record.

#### Scenario: Agent attempts clinician approval
- **WHEN** the agent identity calls `record_clinician_approval`
- **THEN** the call is denied

#### Scenario: Clinician approves
- **WHEN** a clinician records an approval
- **THEN** a decision record exists with the clinician's identity, the decision time and the recommendation record's hash
