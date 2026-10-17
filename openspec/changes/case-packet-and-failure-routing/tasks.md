# Tasks (demo scope, PM 2026-10-16)

Delivers demo **beats 2 and 3**: a clean case approved by `decide()`, and a one-note-removed counterfactual routed to the reviewer with its gap marked. Deferred items are listed in the README's "Known limitations".

## 0. Before any invocation

- [x] 0.1 Model access recorded: Nova Pro (runtime default, us-east-1) and Sonnet 4.6 (opt-in). `evidence/2026-10-16/model-access-extraction.json`.
- [x] 0.2 Telemetry check (done 2026-10-16: `scripts/telemetry_check.py`, `evidence/2026-10-16/telemetry-check.json`; positive control 18 canary hits, runtime settings zero, in spans and logs). Run the agent locally with the runtime's ADOT configuration, botocore instrumentation and Strands telemetry against a fake model and gateway. Record which attributes carry content, disable each one, and re-run until a planted canary appears nowhere. Record the settings in the contract notes.

## 1. Synthetic data, generated here

- [x] 1.1 One fictional payer (Larkspur Health Plan) and one procedure (lumbar discectomy, CPT number only, with our own description), plus a short synthetic policy whose criteria carry evidence rules. `data/policies/compile.py` produces the criteria with source locations. A test reproduces the committed output.
- [x] 1.2 Charts for about 6 synthetic patients in a single tenant: page- and line-addressable documents, each with a `kind`; a chart index; canaries in every chart. The harness cases are drawn from these.

## 2. Checks and decision (most already built in `src/prior_auth/checks/`)

- [x] 2.1 Move the fixture rules into compiled criteria. Done when the existing checks tests pass on the compiled policy.
- [x] 2.2 `decide(packet)`: the only caller of `record_approval` and `route_to_reviewer`. Tests:
  - approve
  - route with gaps
  - the model summary never changes the decision
  - no other code path calls the ending tools (G7, G9, G10)

## 3. Real tools and the approval service

- [x] 3.1 Real `check_eligibility`, `fetch_policy_criteria` (exact (payer, CPT) match, no Knowledge Base) and `extract_clinical_evidence` (returns chart lines with document, page and line).
- [x] 3.2 Approval service against the real stores: request record, compiled criteria, chart index, packet store. The existing refusal tests run against them.
- [x] 3.3 (done 2026-10-16: `src/prior_auth/handlers/agent_tools.py` writes the queue entry with the run ID; the runtime writes the write-once recommendation record before acting, `tests/test_evidence_chain.py`) `route_to_reviewer` writes `queue/<case_id>.json` and the recommendation record (single tenant).

## 4. Strands agent on Runtime (deploy, with approval)

- [x] 4.1 The Strands agent: MCP client to the agent gateway, filtered to exactly the three gathering tools; Nova Pro; redaction on; structured output of citations only (design D3), turned into findings by `checks.findings_from_citations()`. The gateway token comes from an AgentCore Identity OAuth2 provider (M2M), and the runtime holds no secret. Done when tests confirm the tool list is exactly three (G10) and that the model's values are ignored.
- [x] 4.2 Session wrapper: exactly one terminal outcome per session, with `needs_review` on any gap (F7). Unit tests per failure-table row (F1–F3, F5, F6), including the two new rows:
  - `record_approval` refused, denied or errored → routed with the reason, and counted as a disagreement
  - `route_to_reviewer` failing → `operator_alert`

  The F6 property test injects failures at both. Session IDs are 33 characters or more. Access denied emits the operator metric, and the recorded alarm state change closes F4.
- [x] 4.3 Runtime stack (CodeZip ARM64, JWT, intake client only), deploy script with `require_mmdsv2`. **Deploy with approval.**
- [x] 4.4 (done 2026-10-16: `evidence/2026-10-16/beats-2-and-3.json`, deployed at the SHAs in `evidence/deploys.jsonl`) Record beat 2 (clean case approved) and beat 3 (counterfactual routed, gap marked), each with a distinct session ID (A1, G3).

## Workflow follow-up

- Update the claims ledger.
