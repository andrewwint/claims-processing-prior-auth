# Proposal

## Why

The agent has to hand a reviewer a case where every claim points at its source, and a failure must slow a case down without ever pushing it toward denial. This change turns the tool stubs into a working agent that builds a cited packet, runs the three checks, decides between approval and routing, and sends every failure to a person. It is priority 2.

## What Changes

- **Compiled policy criteria.** Synthetic payer policies compile into one verified file per (payer, procedure). Each criterion carries its policy version and source location.
- **Evidence extraction.** Each finding cites its source document, page or line, and patient ID.
- **The case packet.** A checklist of criterion, evidence, source and status (Met / Not found).
- **Three checks** run before the packet moves: schema, source match, and same patient.
- **The decision.**
  - All criteria met and all checks passed: the agent stores the packet and calls `record_approval` with `packet_id` and `packet_hash`.
  - Anything else: `route_to_reviewer`, with the gaps marked.
  - The approval service replaces the fixture from `gateway-and-policy` with the real packet store: it loads the stored packet, verifies the hash, and re-runs the checks before writing.
- **Failure routing.** Each row of the article's failure table, plus a written empty-output rule for each step:
  - extraction failed → reviewer
  - no text → reviewer, with the stop reason
  - no verified policy → reviewer
  - model access denied → fail loudly and alert the operator
- **Agent runtime.**
  - A Strands agent on AgentCore Runtime: HTTP protocol, JWT inbound authentication, one session per case.
  - A post-deploy step requires metadata service v2.
  - Models come from the allow-list.
  - Telemetry content redaction is on from the first deploy.

## Claims delivered

B7, G1–G7, F1–F6, A1.

## Capabilities

### New Capabilities

- `case-packet`: how criteria and evidence become a cited, checked packet, and when approval is allowed.
- `failure-routing`: where every failure mode goes.
- `agent-runtime`: how the agent is hosted, invoked and isolated per case.

### Modified Capabilities

None.

## Impact

- **New code:** `policies/` (synthetic source policies and compiled criteria files), `cases/` (synthetic charts), `agent/` (Strands agent), real logic in `tools/`, `infra/runtime_stack.py`, `scripts/require_mmdsv2.py`, and tests.
- **AWS resources:** an AgentCore Runtime, plus an operator alarm and SNS topic.
- **Depends on** `gateway-and-policy`.
