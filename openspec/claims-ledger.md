# Claims ledger

Source: the article "Build the Case, Let the Clinician Decide" (draft, 2026-10-16).

Each row is one checkable claim the article makes about this design, and the evidence that proves it. The work is done when every row has evidence.

- **Evidence types:**
  - **test:** an automated test in this repository.
  - **deployed:** a resource that exists in the AWS account, shown by a recorded listing.
  - **recorded:** a captured call and its response.
  - **report:** a generated report committed with its raw data.
  - **citation:** an external primary source.
- **Status values:** `open`, `proven`, or `flag: article edit`.
- **The rule:** if a row can't be proven, the article changes. The evidence never stretches to fit.
- **Change:** the OpenSpec change in `openspec/changes/` that delivers the evidence.

## Cut line: Sunday 2026-10-18, 18:00

Rows committed to proven by the cut line, in priority order. Rows below the line stay `open`, and the article is not published claiming them until they have evidence.

1. **Gateway and policy:** B1, B2, B3, B4 (both layers), B5, B6, B8 (agent-side denial), A2, A3, A4, M9.
2. **Cited packet and failure routing:** B7, G1–G7, F1–F6, A1.
3. **Evidence record and clean trace:** L1, L2, L3, L6, A5, A6.
4. **Citations (no deploy needed):** R1 (with the article edit applied), R2, R3, R4.

**Below the line:**
- L4, L5 and L7 (write-once storage proof, per-tenant keys, the decision clock)
- B8 (clinician-side workbench call)
- M1–M8 (harness)

Each of these stays open, with its status unchanged.

**Dependency.** Every deploy in priority 1–3 waits for Andrew's approval. If approval for priority 1 lands after Saturday noon, priority 3 moves below the line.

## Boundary: the agent cannot deny

| # | Claim | Evidence that proves it | Type | Change | Status |
|---|---|---|---|---|---|
| B1 | The agent's gateway exposes exactly five tools: `check_eligibility`, `fetch_policy_criteria`, `extract_clinical_evidence`, `record_approval`, `route_to_reviewer`. | `tools/list` from the deployed agent gateway, plus a test asserting the exact tool set. | deployed, recorded, test | `gateway-and-policy` | open |
| B2 | The agent's gateway does not expose `record_adverse_determination`. | The same recorded `tools/list`, plus a test that fails if the tool appears. | recorded, test | `gateway-and-policy` | open |
| B3 | A Cedar `forbid` on the adverse-determination action is deployed and evaluated on every tool call: one forbid unless the principal is in the clinician group, and one explicit forbid on the agent identity. Every permit names its principal. | The policy listing from the deployed policy engine, validated in the default mode with any findings recorded, plus the policy text in the repository. | deployed | `gateway-and-policy` | open |
| B4 | The agent cannot reach the denial tool, and a policy forbids it even if it does. | Two layers, both recorded. (1) The reviewer gateway's inbound authorizer admits clinician clients only, so an agent-token call is rejected at the door. (2) In a temporary test configuration the agent client is admitted, the Cedar forbid denies the call, the denied call is recorded, and the configuration is reverted; the revert is recorded too. | recorded | `gateway-and-policy` | open (article edited per D1, 2026-10-16) |
| B5 | The Cedar snippet in the article matches the deployed policy. | The article snippet is copied from the deployed policy text, never typed. The action name's underscore count is confirmed from the deployed `tools/list` names. A test compares the committed snippet with the deployed policy text. | deployed, test | `gateway-and-policy` | open (article edited per D1; the snippet is replaced from the deployed text once it exists) |
| B6 | `record_approval` takes `packet_id` and `packet_hash`, not agent-asserted booleans. Cedar permits it only for the agent identity when both fields are present. The approval service loads the stored packet, verifies the hash, re-runs the checks, and refuses otherwise. | Two recorded well-formed calls: one refused server-side (its stored packet fails its checks) and one approved. A test for the server-side refusal. The policy text. | recorded, deployed, test | `gateway-and-policy` (fixture packet), `case-packet-and-failure-routing` (real packet store) | open |
| B7 | Policy checks the shape of a call, not whether its inputs are true. Grounding covers truth. | Test: a call with well-formed but false inputs passes Policy and is caught by the grounding checks (G4–G6). | test | `case-packet-and-failure-routing` | open |
| B8 | Only the reviewer app holds `record_adverse_determination`, and it runs under the clinician's own identity. | The deployed reviewer path, kept separate from the agent gateway. A recorded call is made under a clinician identity, and an agent-identity call to the same action is denied. | deployed, recorded | `clinician-workbench` | open |

## Grounding: every recommendation cites its source

| # | Claim | Evidence that proves it | Type | Change | Status |
|---|---|---|---|---|---|
| G1 | Each payer policy compiles into one verified file per procedure. | Compiled synthetic policy files, plus a test that rebuilds them from source. | test | `case-packet-and-failure-routing` | open |
| G2 | Each criterion carries its policy version and its location in the source. | Schema test on the compiled files. | test | `case-packet-and-failure-routing` | open |
| G3 | The packet is a checklist: criterion, evidence, source, status (Met / Not found). | An example packet produced from a synthetic case, plus a schema test. | test, report | `case-packet-and-failure-routing` | open |
| G4 | Check 1: output must match its schema. | Test: malformed output goes to the reviewer. | test | `case-packet-and-failure-routing` | open |
| G5 | Check 2: every extracted value must appear in the source it cites. | Test: a value missing from its cited source goes to the reviewer. | test | `case-packet-and-failure-routing` | open |
| G6 | Check 3: every citation must come from this patient's record. | Test: a citation from another synthetic patient goes to the reviewer. | test | `case-packet-and-failure-routing` | open |
| G7 | The agent calls `record_approval` only when all criteria are met and all checks pass. Anything else goes to a clinician with the gaps marked. The approval service enforces the same rule on the stored packet. | Tests covering both paths, plus the recorded calls in B6. | test, recorded | `case-packet-and-failure-routing` | open |

## Failure routing: every failure goes to a person

| # | Claim | Evidence that proves it | Type | Change | Status |
|---|---|---|---|---|---|
| F1 | Evidence extraction fails → route to reviewer, labeled "extraction failed". | Test with an injected extraction failure. | test | `case-packet-and-failure-routing` | open |
| F2 | Model returns no text → route to reviewer, with the stop reason. | Test with an empty response and a `max_tokens` response. | test | `case-packet-and-failure-routing` | open |
| F3 | Policy criteria not found → route to reviewer, labeled "no verified policy". | Test with an unknown CPT/payer pair. | test | `case-packet-and-failure-routing` | open |
| F4 | Model access denied → fail loudly and alert the operator. | Test with an injected AccessDenied, plus a deployed alarm and a recorded alarm state change. | test, deployed, recorded | `case-packet-and-failure-routing` | open |
| F5 | Each step has its own written, tested empty-output rule. | One test per step's empty-output rule, plus the rules documented in the spec. | test | `case-packet-and-failure-routing` | open |
| F6 | A failure may slow a case down. It may never push a case toward denial. | Property test: no injected failure produces an approval or an adverse outcome; every failure ends in "routed to reviewer" or "operator alert". | test | `case-packet-and-failure-routing` | open |

## Lineage: prove the gate held

| # | Claim | Evidence that proves it | Type | Change | Status |
|---|---|---|---|---|---|
| L1 | The trace holds case ID, step, model ID, token counts, latency, stop reason and content hashes. | An exported OpenTelemetry trace from a deployed run, plus a schema test of the span attributes. | deployed, recorded, test | `evidence-record-and-trace` | open |
| L2 | The trace holds no chart text. | A scan of exported traces and the Runtime logs for every synthetic chart string, returning zero hits, committed as a report. The scan is also a test. | report, test | `evidence-record-and-trace` | open |
| L3 | The evidence record holds the packet, recommendation, citations, policy version, reviewer identity, decision and timestamps. | A recorded evidence record from a deployed run, plus a schema test. | recorded, test | `evidence-record-and-trace` | open |
| L4 | The evidence record lives in encrypted, write-once storage the agent cannot rewrite. | The deployed storage configuration (encryption, write-once setting), plus a recorded failed overwrite or delete attempt by the agent role. | deployed, recorded | `evidence-record-and-trace` | open: governance-mode Object Lock, so the demo can be torn down the same day; the article or README notes that production uses compliance mode |
| L5 | Evidence records use per-tenant keys. | A deployed key per synthetic tenant, with records encrypted under the matching key (recorded). | deployed, recorded | `evidence-record-and-trace` | open (scope check: two synthetic tenants) |
| L6 | The hash in the trace matches the evidence record. | Test plus a recorded check: recompute the record's hash and compare it with the trace attribute. | test, recorded | `evidence-record-and-trace` | open |
| L7 | The timestamps answer the decision clock (received → decided). | The evidence record fields, plus a test computing elapsed time against the standard and expedited windows. | test | `evidence-record-and-trace` | open |

## Models and evaluation

| # | Claim | Evidence that proves it | Type | Change | Status |
|---|---|---|---|---|---|
| M1 | Metrics: false auto-approval rate and auto-approval rate, as defined in the article. | Pre-registration document committed before the first run, and a report with both metrics. | report | `evaluation-harness` | open |
| M2 | Cases are synthetic and counterfactual: a case that meets criteria, with one piece of evidence removed. | Case files with parent and removed-element provenance, plus a generator test. | test | `evaluation-harness` | open |
| M3 | Each case runs several times, and every trial is shown. | The report's per-trial table, regenerated from raw trials. | report | `evaluation-harness` | open |
| M4 | A response cut off at the token limit counts as a failure. | Scoring test. | test | `evaluation-harness` | open |
| M5 | Each model's sampling settings are recorded, as actually sent. | Manifest field, plus a test that it matches the request sent. | test, report | `evaluation-harness` | open |
| M6 | Cases are labeled synthetic and author-labeled, never clinical ground truth. | Report text, plus a test on the report wording. | test | `evaluation-harness` | open |
| M7 | One real call to every candidate before building. | A recorded access check per candidate model, with date and lifecycle status. | recorded | `evaluation-harness` | open |
| M8 | The harness rate is published whatever it is. | The committed report, unedited. | report | `evaluation-harness` | open |
| M9 | One allow-list names the models, enforced in code and in IAM, with Regions pinned. Cross-Region routing is opt-in. | Code test (unlisted model rejected), plus the deployed IAM policy listing exactly the allow-listed model ARNs in the pinned Region. | test, deployed | `gateway-and-policy` (platform) | open |

## AgentCore mapping (one deployed resource per row)

| # | Concern | Service | Evidence | Type | Change | Status |
|---|---|---|---|---|---|---|
| A1 | Run the agent, one case at a time: an isolated session per request. | Runtime | The deployed runtime and endpoint, plus recorded invocations with a distinct session ID per case. | deployed, recorded | `gateway-and-policy` (platform) | open |
| A2 | Expose only safe tools behind one MCP endpoint per role: the agent's gateway, and a separate reviewer gateway. | Gateway | Same evidence as B1, B2 and B4 (layer 1). | deployed, recorded | `gateway-and-policy` | open (article Gateway row edited, 2026-10-16) |
| A3 | Make denial impossible for the agent. | Policy | Same evidence as B3, B4 and B6. | deployed, recorded | `gateway-and-policy` | open |
| A4 | Clinicians and the agent sign in as separate identities; tools authenticate with the gateway's role, so no secrets live in the agent. | Identity | Recorded listings: separate Cognito app clients for agent and clinician, each gateway's `allowedClients`, every gateway target's credential type (`GATEWAY_IAM_ROLE`), and the runtime environment showing no secret values. A test fails on any secret-like value in the runtime configuration. | deployed, recorded, test | `gateway-and-policy` | open (article edited per D3, 2026-10-16) |
| A5 | Memory is not used for patient data. | Memory | The runtime configuration with no memory resource attached (recorded listing), plus an explicit IAM deny on Memory data-plane actions for the runtime role. | deployed | `evidence-record-and-trace` | open (article edited, 2026-10-16) |
| A6 | Prove what happened: OpenTelemetry traces with IDs, timings and hashes, never chart text. | Observability | Same evidence as L1 and L2. | deployed, report | `evidence-record-and-trace` | open |

## Regulatory and external claims (citations, not code)

| # | Claim | Evidence | Type | Status |
|---|---|---|---|---|
| R1 | State laws (2026 to 2027) bar AI from being the sole basis to deny care; a licensed clinician must review the denial. | Washington E2SSB 5395, Ch. 157, Laws of 2026, amending RCW 48.43.830(3): "Artificial intelligence shall not be the sole means used to deny, delay, or modify health care services"; effective June 11, 2026 (lawfilesext.leg.wa.gov session law). Colorado HB26-1139, Session Laws 2026 Ch. 325, adding C.R.S. 10-16-112.7(5)(b): medical-necessity denials may not issue solely on AI output without approval by a licensed clinician; effective January 1, 2027 (leg.colorado.gov). Illinois SB 3114 (P.A. 104-0568) was cut: it regulates claim downcoding, not utilization review. | citation | **flag: article edit**: "2026 to 2028" becomes "2026 to 2027"; name WA and CO; "delay or modify" is Washington only; drop Illinois (verified 2026-10-16 from primary legislature sources) |
| R2 | CMS-0057-F: standard decisions in 7 calendar days, expedited in 72 hours, a specific reason on every denial (January 2026). | The CMS final rule text. | citation | open |
| R3 | CMS-0057-F: payers expose a FHIR Prior Authorization API (January 2027). | The CMS final rule text. | citation | open |
| R4 | Prior authorization sits pre-service, on the X12 278 request and response. | X12 / CMS source. | citation | open |

## Not tracked here

Author experience, earlier articles and personal context are the author's own statements, not claims about this implementation.
