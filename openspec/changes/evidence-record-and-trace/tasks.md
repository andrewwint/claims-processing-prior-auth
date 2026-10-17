# Tasks (demo scope, PM 2026-10-16)

Delivers **beat 6**: a trace with no chart text (canary scan with a positive control).

It also provides the record chain that the clean-case, counterfactual and clinician beats rely on.

- [x] 1.1 (done 2026-10-16) One canonical hash function (`checks.canonical_hash`), shared by the writer, the trace and the verifier.
- [x] 1.2 (done 2026-10-16, deploys in `evidence/deploys.jsonl`) Evidence stack: one bucket with `recommendations/` and `decisions/`, Object Lock in governance mode (1-day default retention), one customer-managed key, and prefix-scoped writes. **Deploy with approval.**
- [x] 1.3 (done 2026-10-16; the recommendation hash is on the runtime's `POST /invocations` span) Writers:
  - the recommendation record at the end of the agent session, with its hash on the final span
  - the decision record from the reviewer Lambda, carrying `recommendation_record_hash`, with the reviewer identity labeled "as the clinician app reports it"
- [x] 1.4 (done 2026-10-16: `evidence/2026-10-16/chain-auto-approval-clean-1.json`, `evidence/2026-10-16/chain-clinician-denial-cf-1.json`) `scripts/verify_chain.py`: decision → recommendation → trace, with each hash recomputed from S3. Unit tests for a broken link. A recorded run (L6).
- [x] 1.5 (done 2026-10-16. **IAM: simulated**, accepted by the PM: `evidence/2026-10-16/storage-controls.json`. **Object Lock: live**: `evidence/2026-10-16/object-lock-live.json`. Write-once refused live. No trust change) Recorded: one failed overwrite by the agent role (L4), and one failed write to `decisions/` by the agent role (L8).
- [x] 1.6 (done 2026-10-16: runtime spans needed the ADOT entry point and `logs:PutResourcePolicy`; they land in the runtime log group's `spans` stream, and `aws/spans` began receiving spans during the clean run. The scan reads both, plus X-Ray `BatchGetTraces`) Trace path (design D10): a 1-hour diagnosis of `aws/spans`. If it's still empty, the scan reads X-Ray traces (`BatchGetTraces`), and the evidence records which path was used.
- [x] 1.7 (done 2026-10-16: `evidence/2026-10-16/canary-scan-control.json`, `evidence/2026-10-16/canary-scan-clean.json`; injected exception paths remain open, L2) Canary scan with positive control: a canary planted in a span and a log line is found, then the clean run scans empty. Scope: runtime logs, spans, and every tool Lambda log group. Both reports committed (L2).
- [x] 1.8 (done 2026-10-16: `tests/test_records.py`) Timestamps are server-generated. The L7 test covers the 7-day and 72-hour windows.

## Teardown

- [ ] 2.1 One full verified teardown, with its output saved. **Decided (2026-10-16): the stack stays up through the demo period; the verified teardown runs after it.** The teardown is extended (not run): it empties the evidence bucket as the teardown role by version ID before the evidence stack goes, and removes the Identity provider and the runtime's log group by exact name (`scripts/teardown.py`, `tests/test_guardrails.py`).
