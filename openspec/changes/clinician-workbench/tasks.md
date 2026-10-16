# Tasks

- [ ] 1.1 Queue writer in `route_to_reviewer`: `queue/<tenant>/<case_id>.json`, with the tenant from the request record. Tests:
  - a model-supplied tenant is ignored
  - the case-tool role cannot write outside `queue/` and `recommendations/`
- [ ] 1.2 Reviewer tools `list_queue`, `get_case` and `record_clinician_approval` on `ReviewerTools`.
  - Cedar: a permit for the clinician group on each, and an explicit forbid on the agent principal for `record_clinician_approval`.
  - Tests for each tool.
  - Recorded: the agent identity is denied `record_clinician_approval`, and a clinician is allowed.
- [ ] 1.3 Denial reason enforced server-side. Done when tests pass for an empty, whitespace-only or missing reason, each refused by the Lambda, plus the schema marking it required.
- [ ] 1.4 Tenant isolation. Done when unit tests pass and the cross-tenant refusal is recorded: clinician A (tenant-a) calls `get_case` with an exact tenant-b case ID and is refused.
- [ ] 1.5 Workbench app.
  - Code + PKCE sign-in, with an SRP fallback.
  - Queue list and packet view through the reviewer gateway only.
  - Distinct labels for "Not found", "extraction failed" and "no verified policy".
  - The model summary marked as such.

  Done when rendering tests pass for each label and for the summary box.
- [ ] 1.6 Decisions through the reviewer gateway. Recorded: one clinician adverse determination and one clinician approval, each with its decision record showing the interceptor-supplied reviewer identity and decision time (B8, L3, L7).
- [ ] 1.7 A screenshot of the workbench on a synthetic case, for the article.

## Workflow follow-up

- Update the claims ledger for B8.
