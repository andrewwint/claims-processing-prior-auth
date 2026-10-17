# Tasks (after Monday)

- [ ] 1.1 Evidence-rule redesign (E1–E3): an allow-list of whole-line templates in allowed sections, NFKC normalization and invisible characters stripped; every review probe becomes a refusal test (G11).
- [ ] 1.2 Mutation run over `src/prior_auth/checks/` and the approval service; report surviving mutants with dispositions (G8).
- [ ] 2.1 Reviewer-identity interceptor with fail-closed tenant fields. Record a spoofed-name call whose decision record shows the validated identity (L3).
- [ ] 2.2 Two tenants: tenant-scoped prefixes, gateway-mediated workbench reads, and a decision accepted only for the caller's tenant queue. Record a cross-tenant read and a cross-tenant write, each refused.
- [ ] 3.1 Memory deny on the runtime and tool roles, plus a recorded `list-memories` (A5).
- [ ] 3.2 Per-tenant customer-managed keys.
- [ ] 3.3 Decision-clock edge cases (L7).
- [ ] 3.4 Error-path canary scan (L2, A6): inject a failure at each step on the deployed runtime and scan the exception paths for chart text, with a positive control (PM, 2026-10-17).
- [ ] 4.1 Redeploy test: after a verified teardown, a fresh deploy from code, with the smoke checks re-recorded.

## From the AWS skills review (docs/reviews/2026-10-17-aws-skills.md)

- [ ] 5.1 (a1, option 2; unverified) Narrow who can read the AgentCore Identity vault secret so only Identity uses it; test whether a condition such as `aws:CalledVia` works before relying on it (A4).
- [ ] 5.2 (b1) Restrict `UpdateGateway`, `UpdatePolicy` and `DeletePolicy` to the deploy role, and alarm on `UpdateGateway` via CloudTrail.
- [ ] 5.3 (b2) Update the contract note and the `infra/cedar.py` comment on array claims (JSON text, matched with `like`).
- [ ] 5.4 (b5) Add a bucket-policy deny on any server-side encryption other than `aws:kms`.
- [ ] 5.5 (b6) Add a no-header row to the storage-controls simulation, matching how the writers actually send records.
- [ ] 5.6 (b7) Record review item R1 as closed: CopyObject into the record prefixes is refused under enforced conditional writes.
- [ ] 5.7 (b8, b9) Make `verify_chain` find the decision segment in `aws/spans` (which ingests every span), and plant a canary-scan control that lands in `aws/spans`.
- [ ] 5.8 (b10) Have the canary scan record the delivery configuration and the Bedrock invocation-logging setting, failing closed if it cannot read them.
- [ ] 5.9 (b11) Use the runtime's own log group name instead of a prefix match, and paginate `record_trace`'s log read.
- [ ] 5.10 (b12-b15) Teardown code: run the CDK app with the project's interpreter; check the bucket before assuming the teardown role; destroy by stack name; delete AgentCore workload identities by exact name; check the Identity vault secret; paginate the OAuth2 provider listing.

