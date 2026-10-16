# Spec Delta

## Purpose

Hosts the agent on AgentCore Runtime, so that each prior-authorization request runs in its own isolated, authenticated session started by a separate intake client.

## ADDED Requirements

### Requirement: One isolated session per case
Each prior-authorization request SHALL run in its own runtime session, identified by a session ID derived from the case.

#### Scenario: Two cases
- **WHEN** two cases are submitted
- **THEN** they run under different session IDs

### Requirement: Only the intake client can invoke the runtime
The runtime SHALL accept callers only through a JWT authorizer. Its only allowed client SHALL be the `prior-auth-intake` app client, using client credentials. That client SHALL be separate from the agent and clinician clients.

#### Scenario: No token
- **WHEN** the runtime is invoked without a valid token
- **THEN** the request is rejected

#### Scenario: Another client's token
- **WHEN** the runtime is invoked with an agent or clinician token
- **THEN** the request is rejected

### Requirement: The extraction model is named, allow-listed and access-checked
The runtime's default extraction model SHALL be Amazon Nova Pro in us-east-1. Claude Sonnet 4.6, through the US inference profile, SHALL be available only as an explicit, recorded opt-in. Each SHALL be sent only the sampling parameters it accepts. A real access call with lifecycle status SHALL be recorded for each before its first invocation.

#### Scenario: Access record exists
- **WHEN** the runtime is first deployed
- **THEN** a dated access-check record for the model exists in the evidence directory

### Requirement: Telemetry content is redacted from the first deploy
The Strands agent SHALL run with prompt, completion and system-instruction content redacted from its first invocation. No ADOT or botocore instrumentation SHALL attach request, response, tool-argument or tool-result content.

#### Scenario: Redaction setting
- **WHEN** the runtime configuration is read
- **THEN** the redaction setting is present, and the content-capture settings found in the telemetry check are disabled

#### Scenario: Planted canary
- **WHEN** a canary is planted in a tool result during the telemetry check
- **THEN** it appears in no span attribute and no log line
