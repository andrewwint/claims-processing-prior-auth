# prior-auth-agentcore

Reference implementation for the article **"Build the Case, Let the Clinician Decide."**

An agent on Amazon Bedrock AgentCore assembles a prior-authorization case: it gathers the evidence, checks it, and cites every statement. A clinician makes the decision.

The agent's gateway has no tool for an adverse determination. That tool lives on a separate reviewer gateway, which admits clinicians only and where a Cedar policy forbids the action for the agent's identity. The agent may submit an approval, but the approval service records it only after re-running every check on the stored packet itself.

> **Status: planning.** The work is planned as OpenSpec changes in `openspec/changes/`. Every claim the article makes is tracked in `openspec/claims-ledger.md`, together with the evidence that proves it.

## What this repository demonstrates

- **Two gateways.** The agent's gateway has no denial tool. The reviewer gateway rejects the agent's token at sign-in, and a Cedar `forbid` stands behind that. Both layers are shown with recorded denied calls.
- **Server-verified auto-approval:** `record_approval` takes a packet reference, and the approval service re-runs the checks on the stored packet before recording anything.
- **A cited case packet**, with three checks run before anyone sees it: schema, source match, and same patient.
- **Failure routing:** every failure mode goes to a human reviewer, never to a default.
- **Clean telemetry:** traces hold identifiers, timings, and hashes, and a scan shows they contain no chart text.
- **A write-once evidence record** whose hash matches the trace.
- **A pre-registered evaluation** that reports the false auto-approval rate on counterfactual cases, with every trial shown.

## Principles

See [docs/principles.md](docs/principles.md).

## Production notes

This repository is a reference implementation that can be torn down the same day. A production deployment would differ in at least two ways:

- **The runtime runs in VPC mode.** The demo uses public mode behind a JWT authorizer.
- **The evidence store uses Object Lock in compliance mode,** with the retention its records policy requires. The demo uses governance mode so it can be torn down the same day.

## Data

This repository uses synthetic data only. It contains no real patient data, and it must never be used with any.
