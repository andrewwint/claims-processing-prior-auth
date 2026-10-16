# Tasks

## 1. Criteria and synthetic data

- [ ] 1.1 Two synthetic payer policies (two procedures each) in `policies/source/`, labeled synthetic, plus `policies/compile.py` with source verification. Test: the compile reproduces the committed output, and a criterion moved away from its stated location fails the compile (G1, G2).
- [ ] 1.2 Synthetic charts for at least three cases (approvable, missing evidence, wrong patient), labeled synthetic. Schema test.

## 2. Packet and checks

- [ ] 2.1 Packet schema and builder. Test: the example packet matches the article's checklist shape (G3).
- [ ] 2.2 Check 1 (schema), check 2 (source match) and check 3 (same patient), each with a failing-case test (G4, G5, G6).
- [ ] 2.3 Decision rule and approval handler with re-validation. Tests:
  - the approval path
  - the routing path, with gaps marked
  - a well-formed call (`packet_id`, `packet_hash`) whose stored packet fails its checks passes policy and is refused by the approval service (G7, B7)
  - a call whose `packet_hash` does not match the stored packet is refused

## 3. Failure routing

- [ ] 3.1 Step wrappers and `Outcome` types. One test per failure-table row (F1, F2, F3, F4: the test asserts the operator-alert metric is emitted).
- [ ] 3.2 A written empty-output rule per step in `docs/empty-output-rules.md`, each with a test (F5).
- [ ] 3.3 Property test: inject failures at every step; no outcome is an approval or adverse (F6).

## 4. Agent runtime (deploy, with approval)

- [ ] 4.1 Strands agent with the gateway MCP client, allow-listed model and redaction setting. Unit tests with a fake gateway and fake model.
- [ ] 4.2 Runtime stack (CodeZip ARM64, JWT, HTTP), deploy script that runs `require_mmdsv2.py`, operator alarm and SNS topic. CDK assertions test. **Deploy with approval.**
- [ ] 4.3 Record two invocations for different cases showing distinct session IDs and the outcome of each (A1). Record the operator alarm's state change from an injected access-denied (F4).
- [ ] 4.4 Extend the teardown verifier to cover the runtime, its log groups, the alarm and the topic. Run the teardown the same day and save the output.

## Workflow follow-up

- Update the claims ledger for B7, G1–G7, F1–F6 and A1.
