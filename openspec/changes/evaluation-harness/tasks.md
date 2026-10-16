# Tasks

- [ ] 1.1 Case generator with provenance (parent, one declared change, label). Tests:
  - exactly one declared difference from the parent (M2)
  - every change type is generated
  - every case is labeled synthetic and author-labeled (M6)
- [ ] 1.2 Gold extraction for every parent, and the label-consistency check: the checks module refuses every "needs review" case on gold findings and approves every "approve" parent. This is a test.
- [ ] 1.3 Write `harness/PREREGISTRATION.md` and commit it before any run (M1). It covers the questions, the case set (generated, with provenance), the models, trials per case, the metric and scoring definitions from design D1 and D4, the stopping rules and the allowed report wording.
- [ ] 1.4 Model access check per candidate: access, accepted parameters, lifecycle status, source and date (M7). Nova Pro and Sonnet 4.6 are already recorded on 2026-10-16; re-run on the day of the run.
- [ ] 1.5 Runner and trial records, with the sampling settings as sent (M5) and the stop reason, decision, approval-service verdict and policy denials. Scoring tests:
  - truncation counts as a failure (M4)
  - false auto-approval, auto-approval and disagreement definitions (M1)
- [ ] 1.6 Report generator: every trial (M3), the required wording (M6), and a byte-identical regeneration test.
- [ ] 1.7 Run per the pre-registration, against the deployed gateways. Commit the raw trials and the report unedited, whatever the rate (M8).

## Workflow follow-up

- Update the claims ledger for M1–M8.
