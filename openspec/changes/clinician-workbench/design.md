# Design

## Decisions

- **App and hosting.** A small Python web app run locally. Sign-in uses the Cognito user pool through the hosted UI (authorization code with PKCE). The app keeps the clinician's tokens in server-side session memory only. Running locally keeps the demo from standing up a new public endpoint.
- **Queue storage.** `route_to_reviewer` writes `queue/<tenant>/<case_id>.json` in the evidence bucket under the evidence store's customer-managed key. Queue entries are not write-once. Decisions are, because they go to the evidence record.
- **Tenant isolation.** The app derives the tenant from the clinician's token claims, never from a request parameter. Lookups use the exact case ID within the tenant's prefix.
- **Decisions.**
  - Adverse determinations call `reviewer___record_adverse_determination` on the reviewer gateway with the clinician's access token, so the Cedar permit for the clinician group applies.
  - Clinician approvals call the same reviewer gateway's approval tool. That tool is added to the reviewer target, permitted for clinicians.
- **Scope.** No styling work beyond a readable checklist table.

## Risks / Trade-offs

- [Hosted-UI redirect setup takes time] → Fallback: a username and password sign-in for the synthetic clinician user, documented as demo-only.
