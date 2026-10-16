# Design (demo scope, PM 2026-10-16)

This change delivers **beat 5**: a clinician decides on the routed case from one local page. It is demoed right after beat 4, in which the agent is refused the same tool. The reviewer gateway's two clinician tools are part of beat 1 (`gateway-and-policy`).

## Decisions

### D1. Sign-in: hosted UI through a standard OAuth library

- **Flow.** The clinician client allows only the authorization-code grant, with the callback `http://localhost:8765/callback` (already deployed in D1).
- **The library.** The page uses a standard OAuth library that handles PKCE and `state`, and binds its server to 127.0.0.1.
- **Fallback.** SRP is the only password flow.
- **E2 reconciliation.** The earlier "OAuth off" fix was about the implicit grant delivering tokens to a third-party callback. Neither exists in this configuration (recorded in `gateway-and-policy`).

### D2. Decisions through the reviewer gateway

- **Tools.** `ReviewerTools___record_adverse_determination` (a reason is required in the schema and by the Lambda) and `ReviewerTools___record_clinician_approval`, both for clinicians only. They are called with the clinician's own access token.
- **Decision records.** The reviewer Lambda reads the case's recommendation record from the evidence bucket, computes its hash, and writes the decision record with `recommendation_record_hash`.
- **Reviewer identity.** The record names the reviewer **as the clinician app reports it**, and labels it that way.

### D3. Reading the queue

- **Single tenant.** The page lists `queue/` and reads recommendation records with the operator's local AWS credentials, read-only.
- **Demo only.** This is stated in the README's "Known limitations". Gateway-mediated reads and tenant scoping move to `post-monday-hardening`.

### D4. The packet view

| What the packet says | What the page shows |
|---|---|
| criterion Met | "Met", with its evidence and source |
| no verified finding | "Not found" |
| extraction failed | "Extraction failed", with the stop reason |
| no compiled policy | "No verified policy" |
| summary | inside a box labeled "Model summary — not used for any decision" |

## Risks / Trade-offs

- [Hosted-UI setup takes time] → At the Saturday 18:00 checkpoint, beat 5 can fall back to a scripted clinician call through the reviewer gateway, plus a screenshot.
- [Reads bypass the gateway] → Demo-only. Stated in "Known limitations".
