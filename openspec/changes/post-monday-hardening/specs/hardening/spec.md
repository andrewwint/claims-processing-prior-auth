# Spec Delta

## Purpose

Closes the controls deferred from Monday's demo, each tied to a README limitation.

## ADDED Requirements

### Requirement: Reviewer identity is validated, not asserted
A request interceptor on the reviewer gateway SHALL validate the caller's token and overwrite the reviewer identity and tenant in every tool call. The reviewer Lambda SHALL refuse calls that lack the interceptor's fields.

#### Scenario: Spoofed reviewer name
- **WHEN** a clinician's call carries a reviewer name that is not theirs
- **THEN** the decision record shows the validated identity

### Requirement: Tenants are isolated
Each clinician SHALL see and decide only cases in their own tenant.

#### Scenario: Cross-tenant read
- **WHEN** a tenant-a clinician requests a tenant-b case by its exact ID
- **THEN** the request is refused

#### Scenario: Cross-tenant decision
- **WHEN** a tenant-a clinician records a decision on a tenant-b case
- **THEN** the write is refused

### Requirement: Evidence rules are an allow-list
A finding SHALL count toward a criterion only if its cited line matches an allowed template in an allowed section, after NFKC normalization and with invisible characters removed.

#### Scenario: Review probes
- **WHEN** any probe line from the security reviews is cited
- **THEN** the finding does not count

### Requirement: Memory is denied
The runtime and tool roles SHALL carry an explicit deny on Memory actions.

#### Scenario: Memory evidence
- **WHEN** memories are listed and the role policies are read
- **THEN** no memory exists and Memory actions are denied

### Requirement: The stack redeploys from code
After a verified teardown, a fresh deploy from code SHALL pass the same smoke checks.

#### Scenario: Redeploy
- **WHEN** the stack is redeployed after teardown
- **THEN** the recorded smoke checks match the previous run
