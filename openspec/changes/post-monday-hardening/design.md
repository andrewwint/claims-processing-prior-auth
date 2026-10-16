# Design

## Context

Each item here was designed and reviewed before the scope cut. The detailed decisions remain in the earlier revisions of `evidence-record-and-trace` (D1: the interceptor), `clinician-workbench` (D3: tenant isolation) and the security reviews (E1–E3, G1–G3). This change carries them forward unchanged unless a review says otherwise.

## Decisions

- **Interceptor.**
  - It validates the token itself (`GetUser`), because the docs don't say whether the gateway validates the JWT before the interceptor runs.
  - It overwrites `reviewer_sub`, `reviewer_username` and `tenant`.
  - It rejects JSON-RPC batches and unknown methods.
  - It never logs headers.
  - The Lambda refuses any call that lacks the interceptor-written fields. That keeps tenant isolation fail-closed (G1).
- **Tenant writes.** A decision is accepted only if `queue/<tenant>/<case_id>.json` exists for the caller's tenant (G2).
- **Evidence rules.** The allow-list design in the README's "Known limitations" replaces the deny-list. A finding that doesn't match an allowed template routes to a reviewer.
- **Order.** Rule redesign, then the interceptor and tenants together, then the Memory deny, then per-tenant keys, then the redeploy test.

## Risks / Trade-offs

- [The interceptor's rewritten body may not reach a Lambda target] → A live test decides it. If it doesn't, the article keeps "as the clinician app reports it".
