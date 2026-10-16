# Design

## Decisions

### D1. Sign-in: authorization code with PKCE, SRP fallback

- **Flow.** The clinician app client allows only the authorization-code grant.
  - The callback is `http://localhost:8765/callback`; no other callback exists.
  - No implicit grant; no client secret (it's a public client).
  - Scopes are `openid` and `aws.cognito.signin.user.admin`.
- **PKCE.** The workbench always sends a code challenge. Cognito does not reject code requests that omit one, so the localhost-only callback is what limits who can receive a code.
- **Fallback.** The client's only password flow is `ALLOW_USER_SRP_AUTH`, so a password never crosses the wire. `USER_PASSWORD_AUTH` is not enabled.
- **Reconciled with the earlier security fix (E2, "OAuth off").** E2 turned OAuth off because CDK's defaults enabled:
  - the implicit grant
  - a third-party callback (`https://example.com`)
  - every scope

  The risk was tokens delivered in a URL fragment to someone else's origin. This configuration has none of those. OAuth is back on in its narrowest form (code only, localhost only, two scopes), because the workbench needs browser sign-in. Recorded in `gateway-and-policy`'s dispositions, and applied in the D1 stack before its first deploy.
- **The admin scope.** It lets a token holder read and update their own user, and the request interceptor needs it to validate the token with `GetUser`. The client has no write attributes, so a clinician cannot change their own attributes. Group membership is never self-editable.

### D2. One target name everywhere

Every reviewer tool is on the target `ReviewerTools`, so the actions are:
- `ReviewerTools___list_queue`
- `ReviewerTools___get_case`
- `ReviewerTools___record_adverse_determination`
- `ReviewerTools___record_clinician_approval`

The third matches the article and the deployed forbid.

### D3. Tenant isolation, from token claims only

- **Groups.** Every clinician is in exactly one tenant group (`tenant-a` or `tenant-b`), plus `clinician`.
- **Where the tenant comes from.** The interceptor reads the validated token's groups and writes `tenant` into the tool arguments, overwriting any caller value. If there is not exactly one tenant group, the interceptor rejects the call.
- **Reads.**
  - `list_queue` lists `queue/<tenant>/`.
  - `get_case(case_id)` reads `queue/<tenant>/<case_id>.json`, then the matching recommendation record, by exact key.
  - A case outside the clinician's tenant is "not found".
- **Writes.** `route_to_reviewer` writes `queue/<tenant>/<case_id>.json` with the tenant from the request record, which is written at intake. The model never supplies the tenant. The case-tool role may write only `queue/` and `recommendations/`.
- **Recorded.** Clinician A (tenant-a) calls `get_case` with a tenant-b case's exact ID and is refused.

### D4. Decisions

- **`record_adverse_determination(case_id, reason)`.**
  - `reason` is required in the schema.
  - The Lambda rejects empty or whitespace-only reasons.
  - It writes a decision record with the interceptor-supplied reviewer identity.
- **`record_clinician_approval(case_id)`.**
  - A separate tool, permitted only for the clinician group.
  - The agent is explicitly forbidden from it, as it is from the denial tool.
  - It writes a decision record.
- **Both decision records** carry `recommendation_record_hash`, linking them into the chain from `evidence-record-and-trace`.

### D5. The packet view

| What the packet says | What the workbench shows |
|---|---|
| criterion Met | "Met", with its evidence and source |
| criterion with no verified finding | "Not found" |
| extraction failed | "Extraction failed", with the stop reason |
| no compiled policy | "No verified policy" |
| summary | inside a box labeled "Model summary — not used for any decision" |

Each failure label is a distinct state with its own rendering test.

### D6. Scope

No styling work beyond a readable checklist table.

## Risks / Trade-offs

- [Hosted-UI setup takes time] → The fallback is SRP sign-in for the synthetic clinician, documented as demo-only.
- [Cognito does not enforce PKCE] → The localhost-only callback and a public client limit the exposure. This is stated in the README.
