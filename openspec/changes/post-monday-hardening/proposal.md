# Proposal

## Why

Monday's demo is built backwards from five minutes, so several controls were designed but deliberately deferred. This change holds all of them in one place, so the README's "Known limitations" and the ledger's deferred rows point at one plan. None of it is needed for the demo. Each item closes a stated limitation.

## What Changes

- **Reviewer-identity interceptor.** A REQUEST interceptor on the reviewer gateway validates the clinician's token with Cognito `GetUser`. It then overwrites the reviewer's `sub`, username and tenant in the tool arguments. A recorded call with a spoofed name shows it working. The design work comes from the earlier `evidence-record-and-trace` revision, including the review gaps G1–G3: tenant isolation must fail closed, and decisions must be checked against the caller's tenant queue.
- **Tenants.** Two tenants. Clinicians each belong to one tenant group, and queue and record prefixes are scoped to the tenant. Workbench reads go through clinician-only gateway tools. A cross-tenant read and a cross-tenant decision write are each recorded as refused.
- **Evidence-rule redesign (E1–E3).** Rules become an allow-list: whole-line templates in allowed document sections, NFKC normalization, invisible characters stripped, and completion wording for therapy. Every probe from the third and targeted security reviews becomes a test.
- **Memory deny.** An explicit IAM deny on Memory actions for the runtime and tool roles, plus a recorded `list-memories` (A5).
- **Per-tenant keys.** One customer-managed key per tenant.
- **Redeploy test.** A fresh deploy from code after a verified teardown, both recorded.
- **Smaller deferrals:** the mutation run over the checks module and approval service; the decision-clock edge cases; harness change types beyond the demo set.

## Claims delivered

Closes the deferred parts of A5, G8, G11, L3 and L7, and the limitations listed in the README.

## Capabilities

### New Capabilities

- `hardening`: the deferred controls and their evidence.

### Modified Capabilities

None.

## Impact

- **Changes to:** the reviewer gateway (interceptor), the evidence bucket (tenant prefixes, keys), IAM (Memory deny), `src/prior_auth/checks/` (rule redesign), and the workbench (gateway-mediated reads).
- **Depends on** Monday's demo being complete.
