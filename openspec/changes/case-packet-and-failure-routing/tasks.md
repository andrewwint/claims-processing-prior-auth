# Tasks

## 0. Before any model invocation

- [x] 0.1 Real access calls, with lifecycle status, accepted sampling parameters and Regions recorded (M7, D8). Done 2026-10-16. Evidence: `evidence/2026-10-16/model-access-extraction.json`.
  - Runtime default Nova Pro: ACTIVE, us-east-1, accepts all three sampling probes.
  - Opt-in Sonnet 4.6 (via `us.anthropic.claude-sonnet-4-6`): ACTIVE, rejects `temperature` with `topP`.
  - Refused: the five model IDs listed in design D8.

## 1. Criteria and synthetic data

- [ ] 1.0 Synthetic data rules (PM, 2026-10-16):
  - **Self-generated.** All data is generated here. Nothing is reused from any other repository: no files, names or attribution.
  - **Payers.** Two fictional payers, **Larkspur Health Plan** and **Tidewell Mutual**. A test fails if any real payer name appears anywhere in the repository (`tests/test_no_real_payers.py`, added 2026-10-16).
  - **Codes.** ICD-10-CM codes as they are. CPT code numbers only, each with our own short description, never the AMA descriptor text.
- [ ] 1.1 Short synthetic payer policies in `policies/source/`, labeled synthetic, covering 2–3 procedures across the two payers: outpatient physical therapy, knee arthroscopy and lumbar discectomy. Each criterion has its evidence rule (design D11). `policies/compile.py` produces criteria with source locations and evidence rules, with source verification. Tests:
  - the compile reproduces the committed output
  - a criterion moved away from its stated location fails the compile (G1, G2)
- [ ] 1.2 About 8 synthetic patients across `tenant-a` and `tenant-b`, in `cases/`, labeled synthetic.
  - Documents are page- and line-addressable, each with a `kind`.
  - `index.json` maps `doc_id` to patient.
  - Every chart embeds unique canary strings for the telemetry scan.
  - Request records carry the tenant.

  Cases:
  - approvable
  - missing evidence
  - wrong patient
  - near-miss value
  - another patient's document labeled with this case's patient ID

  `scripts/seed_charts.py` uploads them. Done when the schema test passes.

## 2. Checks module and decision

- [ ] 2.1 `checks/`: check 1 (schema), check 2 (exact NFC substring at the cited line, at least 4 non-whitespace characters), check 3 (the compiled evidence rule), check 4 (patient from `index[doc_id]`), and `recompute()`. The four checks match the article. Negative tests, one per case:
  - malformed output (G4)
  - value not at its location (G5)
  - near miss: one changed character, a change of case, the adjacent line (G5)
  - trivial or empty value (G5)
  - another patient's document (G6)
  - another patient's document labeled with this case's patient ID (G6)
  - unknown `doc_id` (G6)
  - a finding for a criterion that isn't in the compiled policy (G4)
  - one quote cited for every criterion, a quote that doesn't state the criterion, a wrong document kind, a numeric minimum not met, a negated finding, one line cited for two criteria, a criterion with no rule (G11)
- [ ] 2.2 Packet schema and builder, with `model_summary` labeled. Done when a test shows the example packet reproduces the article's three checklist rows (G3).
- [ ] 2.3 `decide(packet)` returns approve or route. Tests:
  - the approval path
  - the routing path, with gaps marked (G7)
  - changing or removing `model_summary` never changes the decision (G9)
- [ ] 2.4 A test that `agent.decision` and the approval service import the same `checks` module object, and that the Lambda bundle holds a byte-identical copy.

## 3. Approval service

- [ ] 3.1 The real approval service, as in design D4. Negative tests:
  - hash mismatch
  - missing packet
  - packet altered after hashing
  - missing request record
  - no compiled policy
  - a well-formed call whose stored packet fails its checks is refused (B6, B7, G7)
  - **a forged packet marked all Met, with made-up findings and a valid hash, is refused (G8)**
  - a forged packet whose `patient_id` matches the request but cites another patient's document is refused (G6, G8)
  - status labels in the packet are ignored
- [ ] 3.2 IAM: the runtime can write only `packets/`; the approval service is read-only. Done when CDK assertions pass.

## 4. Failure routing and session invariant

- [ ] 4.1 The per-step empty-output table (design D6) in `docs/empty-output-rules.md`. Done when there is one test per row (F1, F2, F3, F5).
- [ ] 4.2 The access-denied path emits the operator metric. Done when its test passes (F4).
- [ ] 4.3 Session recorder (design D5). Tests:
  - every path ends in exactly one terminal outcome
  - a session ending without one becomes `needs_review` and is routed
  - a second terminal attempt is refused and logged (F7)
- [ ] 4.4 Property test: inject failures at every step. No outcome is an approval or an adverse outcome, and every session has exactly one terminal outcome (F6, F7).
- [ ] 4.5 Mutation run with `mutmut` over `checks/`, the approval service, `agent/session.py` and the pipeline wrapper. Done when the report lists every surviving mutant and its disposition, and is committed.

## 5. Agent runtime (deploy, with approval)

- [ ] 5.1 The pipeline with the allow-listed model, temperature 0 only, and the redaction setting. The model gets no tool list. Done when unit tests with a fake gateway and a fake model pass, including one asserting the model is never given tools.
- [ ] 5.2 Runtime stack:
  - CodeZip ARM64, HTTP protocol, JWT authorizer admitting only `prior-auth-intake`
  - the case and chart buckets
  - the intake app client
  - the operator alarm and SNS topic
  - a deploy script that runs `require_mmdsv2.py`

  Done when the CDK assertions test passes. **Deploy with approval.**
- [ ] 5.3 Subscribe the operator email to the topic. Wait for Andrew to confirm it, then record `ListSubscriptionsByTopic` showing a confirmed subscription.
- [ ] 5.4 Seed the charts, then submit two cases through `scripts/intake.py`. Record the distinct session IDs and each outcome (A1). Record the operator alarm's state change from an injected access-denied (F4).
- [ ] 5.5 Extend the teardown verifier to cover the runtime and its log groups, both buckets, the intake client, the alarm, the topic and its subscriptions. Run the teardown the same day and save the output.

## Workflow follow-up

- Update the claims ledger for B7, G1–G9, F1–F7 and A1.
