# Proposal

## Why

The article's design ends at a person: the clinician sees the case the agent built and makes the decision, and only the clinician's side holds the denial tool. A minimal workbench makes that real and lets the ledger prove the clinician-side half of the boundary. It is priority 4.

## What Changes

- **Sign-in.** Authorization code with PKCE, through the Cognito hosted UI, with a localhost callback only. The only password fallback is SRP, never `USER_PASSWORD_AUTH`.
- **Identity and tenant come only from the validated token.**
  - The reviewer gateway's request interceptor (from `evidence-record-and-trace`) validates the clinician's token.
  - It overwrites the reviewer `sub`, username and tenant in every tool call's arguments.
  - The tenant comes from the clinician's tenant group claim, never from a request parameter or the model.
- **Reviewer-gateway tools.** All are on the `ReviewerTools` target, and each is permitted by Cedar for the clinician group only:
  - `ReviewerTools___list_queue`: the clinician's tenant queue.
  - `ReviewerTools___get_case`: one case, looked up by exact ID within the clinician's tenant. Another tenant's case is refused.
  - `ReviewerTools___record_adverse_determination`: requires a reason, enforced by the schema and by the Lambda. Writes a decision record.
  - `ReviewerTools___record_clinician_approval`: a separate tool. Writes a decision record.
- **Review queue.**
  - `route_to_reviewer` writes only under `queue/<tenant>/<case_id>.json`.
  - The tenant is taken from the request record, never from the model.
- **The workbench** is a minimal local web app.
  - **Queue:** shows the clinician's tenant queue.
  - **Packet:** shows the packet checklist with sources.
  - **Labels:** "Not found", "extraction failed" and "no verified policy" are labeled distinctly.
  - **Summary:** the model summary is marked as a model summary.
  - **Data access:** every read and write goes through the reviewer gateway under the clinician's own token. The app holds no AWS credentials.
- **No public endpoint.** The workbench runs locally against the deployed gateways.

## Claims delivered

B8, completing the clinician-side half. It also supports L3 (reviewer identity) and L7 (decision timestamp).

## Capabilities

### New Capabilities

- `clinician-workbench`: how a clinician reviews a routed case and records a decision.

### Modified Capabilities

None.

## Impact

- **New code:**
  - `workbench/` (Python web app)
  - the reviewer tools `list_queue`, `get_case` and `record_clinician_approval`
  - the queue writer in `route_to_reviewer`
  - tests
- **AWS changes:**
  - the reviewer gateway target gains three tools
  - three Cedar permits for the clinician group
  - no new resources beyond the queue prefix in the evidence bucket
- **Depends on** `evidence-record-and-trace` (the request interceptor and decision records).
