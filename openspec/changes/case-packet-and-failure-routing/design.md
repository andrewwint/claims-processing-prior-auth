# Design

## Context

This change depends on the gateways, the policies and the allow-list from `gateway-and-policy`. Runtime constraints, including metadata service v2, telemetry redaction and JWT invocation, are in [docs/contract-notes.md](../../../docs/contract-notes.md).

## Decisions

### Deterministic steps vs model steps

Criteria lookup, the three checks and the approval rule are plain code. The model is used only for evidence extraction and for writing the packet's prose.

Why: every safety-relevant decision is testable without a model, and the model can't move a case toward approval on its own.

### Criteria compile

- **Sources.** Synthetic payer policies live as source documents in `policies/source/`.
- **Compiler.** `policies/compile.py` writes `policies/compiled/<payer>/<cpt>.json`.
- **Each criterion** carries `id`, `text`, `policy_version` and `source_location`.
- **Verification.** The compile step re-reads each criterion's text at its stated location and fails if it isn't there.

### Evidence extraction

- **Input.** One synthetic chart per case, with documents identified by `patient_id`, `doc_id` and page/line.
- **Output.** The model returns findings as structured output. Each finding carries `criterion_id`, `value`, `doc_id`, `location` and `patient_id`.
- **Check 2 (source match)** confirms each `value` is present at the cited location.
- **Check 3 (same patient)** compares each citation's `patient_id` with the case's.

### Approval handler

`record_approval(packet_id, packet_hash)` loads the stored packet, verifies the SHA-256 of its canonical JSON against `packet_hash`, and recomputes "all criteria Met and all checks passed" from the packet itself. The call carries no assertions. If the packet is missing, the hash does not match, or the recomputation fails, the service refuses, records nothing, and routes the case to a reviewer. This replaces the fixture-backed service from `gateway-and-policy`.

### Failure routing

- **One wrapper per step.** Each step runs inside a wrapper that converts any exception or empty output into a typed `Outcome(kind="needs_review" | "operator_alert", reason=...)`.
- **Access denied** raises `operator_alert`. This sets a CloudWatch alarm through a custom metric, and the alarm notifies an SNS topic.
- **No defaults.** No wrapper returns a default value.

### Runtime

- **Hosting.** Python CDK `Runtime` with a CodeZip ARM64 build, HTTP protocol, JWT authorizer, public network mode, and model IDs from the allow-list.
- **Metadata service v2.** `scripts/require_mmdsv2.py` runs after every deploy: it reads the runtime's configuration and calls `UpdateAgentRuntime` with `requireMMDSV2: true`.
- **Session IDs.** Derived from the case ID.
- **Telemetry.** Redaction is set through `OTEL_SEMCONV_STABILITY_OPT_IN`. `APPLICATION_LOGS` delivery is not enabled.

### Network

Public network mode with a JWT authorizer. VPC mode is an option within budget but is not used here: its network interfaces can remain for hours after deletion, which conflicts with same-day verified teardown.

## Risks / Trade-offs

- [The model invents a citation] → Checks 2 and 3 catch it, and the case routes to a reviewer.
- [Redaction misses error text] → `evidence-record-and-trace` adds the canary scan as a test.
- [Metadata service v2 step forgotten] → The deploy script runs it, and a test asserts the deploy script calls it.
