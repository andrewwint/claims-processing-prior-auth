# Tasks (demo scope, PM 2026-10-16)

Delivers demo **beats 2 and 3**: a clean case approved by `decide()`, and a one-note-removed counterfactual routed to the reviewer with its gap marked. Deferred items are listed in the README's "Known limitations".

## 0. Before any invocation

- [x] 0.1 Model access recorded: Nova Pro (runtime default, us-east-1) and Sonnet 4.6 (opt-in). `evidence/2026-10-16/model-access-extraction.json`.
- [ ] 0.2 Telemetry check. Run the agent locally with the runtime's ADOT configuration, botocore instrumentation and Strands telemetry against a fake model and gateway. Record which attributes carry content, disable each one, and re-run until a planted canary appears nowhere. Record the settings in the contract notes.

## 1. Synthetic data, generated here

- [ ] 1.1 One fictional payer (Larkspur Health Plan) and one procedure (lumbar discectomy, CPT number only, with our own description), plus a short synthetic policy whose criteria carry evidence rules. `policies/compile.py` produces the criteria with source locations. A test reproduces the committed output.
- [ ] 1.2 Charts for about 6 synthetic patients in a single tenant: page- and line-addressable documents, each with a `kind`; a chart index; canaries in every chart. The harness cases are drawn from these.

## 2. Checks and decision (most already built in `checks/`)

- [ ] 2.1 Move the fixture rules into compiled criteria. Done when the existing checks tests pass on the compiled policy.
- [ ] 2.2 `decide(packet)`: the only caller of `record_approval` and `route_to_reviewer`. Tests:
  - approve
  - route with gaps
  - the model summary never changes the decision
  - no other code path calls the ending tools (G7, G9, G10)

## 3. Real tools and the approval service

- [ ] 3.1 Real `check_eligibility`, `fetch_policy_criteria` (exact (payer, CPT) match, no Knowledge Base) and `extract_clinical_evidence` (returns chart lines with document, page and line).
- [ ] 3.2 Approval service against the real stores: request record, compiled criteria, chart index, packet store. The existing refusal tests run against them.
- [ ] 3.3 `route_to_reviewer` writes `queue/<case_id>.json` and the recommendation record (single tenant).

## 4. Strands agent on Runtime (deploy, with approval)

- [ ] 4.1 The Strands agent: MCP client to the agent gateway, filtered to exactly the three gathering tools; Nova Pro; redaction on. Done when tests confirm the tool list is exactly three (G10).
- [ ] 4.2 Session wrapper: exactly one terminal outcome per session, with `needs_review` on any gap (F7). Unit tests per failure-table row (F1–F3, F5, F6).
- [ ] 4.3 Runtime stack (CodeZip ARM64, JWT, intake client only), deploy script with `require_mmdsv2`. **Deploy with approval.**
- [ ] 4.4 Record beat 2 (clean case approved) and beat 3 (counterfactual routed, gap marked), each with a distinct session ID (A1, G3).

## Workflow follow-up

- Update the claims ledger.
