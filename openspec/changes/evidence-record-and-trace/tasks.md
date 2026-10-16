# Tasks (demo scope, PM 2026-10-16)

Delivers **beat 6**: a trace with no chart text (canary scan with a positive control).

It also provides the record chain that the clean-case, counterfactual and clinician beats rely on.

- [ ] 1.1 One canonical hash function (`checks.canonical_hash`), shared by the writer, the trace and the verifier.
- [ ] 1.2 Evidence stack: one bucket with `recommendations/` and `decisions/`, Object Lock in governance mode (1-day default retention), one customer-managed key, and prefix-scoped writes. **Deploy with approval.**
- [ ] 1.3 Writers:
  - the recommendation record at the end of the agent session, with its hash on the final span
  - the decision record from the reviewer Lambda, carrying `recommendation_record_hash`, with the reviewer identity labeled "as the clinician app reports it"
- [ ] 1.4 `scripts/verify_chain.py`: decision → recommendation → trace, with each hash recomputed from S3. Unit tests for a broken link. A recorded run (L6).
- [ ] 1.5 Recorded: one failed overwrite by the agent role (L4), and one failed write to `decisions/` by the agent role (L8).
- [ ] 1.6 Trace path (design D10): a 1-hour diagnosis of `aws/spans`. If it's still empty, the scan reads X-Ray traces (`BatchGetTraces`), and the evidence records which path was used.
- [ ] 1.7 Canary scan with positive control: a canary planted in a span and a log line is found, then the clean run scans empty. Scope: runtime logs, spans, and every tool Lambda log group. Both reports committed (L2).
- [ ] 1.8 Timestamps are server-generated. The L7 test covers the 7-day and 72-hour windows.

## Teardown

- [ ] 2.1 Sunday, after the final evidence run: one full verified teardown, with its output saved. Ask Andrew whether to keep the stack up for Monday.
