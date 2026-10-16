# Spec Delta

## Purpose

Hosts the agent on AgentCore Runtime so each prior-authorization request runs in its own isolated, authenticated session.

## ADDED Requirements

### Requirement: One isolated session per case
Each prior-authorization request SHALL run in its own runtime session, identified by a session ID derived from the case.

#### Scenario: Two cases
- **WHEN** two cases are submitted
- **THEN** they run under different session IDs

### Requirement: Invocation is authenticated
The runtime SHALL accept only authenticated callers through a JWT authorizer.

#### Scenario: No token
- **WHEN** the runtime is invoked without a valid token
- **THEN** the request is rejected

### Requirement: Telemetry content is redacted from the first deploy
The agent SHALL run with prompt, completion, and system-instruction content redacted from telemetry from its first deployment.

#### Scenario: Redaction setting
- **WHEN** the runtime configuration is read
- **THEN** the redaction setting is present
