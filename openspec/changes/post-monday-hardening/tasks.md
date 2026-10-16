# Tasks (after Monday)

- [ ] 1.1 Evidence-rule redesign (E1–E3): an allow-list of whole-line templates in allowed sections, NFKC normalization and invisible characters stripped; every review probe becomes a refusal test (G11).
- [ ] 1.2 Mutation run over `src/prior_auth/checks/` and the approval service; report surviving mutants with dispositions (G8).
- [ ] 2.1 Reviewer-identity interceptor with fail-closed tenant fields. Record a spoofed-name call whose decision record shows the validated identity (L3).
- [ ] 2.2 Two tenants: tenant-scoped prefixes, gateway-mediated workbench reads, and a decision accepted only for the caller's tenant queue. Record a cross-tenant read and a cross-tenant write, each refused.
- [ ] 3.1 Memory deny on the runtime and tool roles, plus a recorded `list-memories` (A5).
- [ ] 3.2 Per-tenant customer-managed keys.
- [ ] 3.3 Decision-clock edge cases (L7).
- [ ] 4.1 Redeploy test: after a verified teardown, a fresh deploy from code, with the smoke checks re-recorded.
