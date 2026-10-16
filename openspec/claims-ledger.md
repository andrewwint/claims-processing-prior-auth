# Claims ledger

Source: the article "Build the Case, Let the Clinician Decide", in [docs/article-draft.md](../docs/article-draft.md) (export of 2026-10-16). Every row below was re-checked against that export on 2026-10-16.

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
2. **Cited packet and failure routing:** B7, G1–G9, F1–F7, A1.
3. **Evidence record and clean trace:** L1, L2, L3, L4, L6, L7, A5, A6. L5 follows if the evidence stack is deployed in time, since it is the same stack.
4. **Citations (no deploy needed):** R1–R6.

**Below the line:**
- L5 (customer-managed key), if the evidence stack slips
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
| B5 | The Cedar snippet in the article matches the deployed policy. The article currently shows `principal == AgentCore::OAuthUser::"<agent-client-id>"` and `AgentCore::Action::"ReviewerTools___record_adverse_determination"`. | The reviewer gateway's target is named `ReviewerTools`. The article snippet is replaced by a copy of the deployed policy text, never typed, with only identifiers redacted. The underscore count is confirmed from the deployed `tools/list` names. A test compares the committed snippet with the redacted deployed policy text. | deployed, test | `gateway-and-policy` | open (article edited per D1) |
| B6 | `record_approval` takes `packet_id` and `packet_hash`, not agent-asserted booleans. Cedar permits it only for the agent identity when both fields are present. The approval service loads the stored packet, verifies the hash, re-runs the checks, and refuses otherwise. | Two recorded well-formed calls: one refused server-side (its stored packet fails its checks) and one approved. A test for the server-side refusal. The policy text. | recorded, deployed, test | `gateway-and-policy` (fixture packet), `case-packet-and-failure-routing` (real packet store) | open |
| B7 | Policy checks the shape of a call, not whether its inputs are true. Grounding covers truth. | Test: a call with well-formed but false inputs passes Policy and is caught by the grounding checks (G4–G6). | test | `case-packet-and-failure-routing` | open |
| B8 | Only the reviewer app holds `record_adverse_determination`, and it runs under the clinician's own identity. | The deployed reviewer path, kept separate from the agent gateway. A recorded call is made under a clinician identity, and an agent-identity call to the same action is denied. | deployed, recorded | `clinician-workbench` | open |

## Grounding: every recommendation cites its source

| # | Claim | Evidence that proves it | Type | Change | Status |
|---|---|---|---|---|---|
| G1 | Each payer policy compiles into one verified file per procedure. | Compiled synthetic policy files, plus a test that rebuilds them from source. | test | `case-packet-and-failure-routing` | open |
| G2 | Each criterion carries its policy version and its location in the source. | Schema test on the compiled files. | test | `case-packet-and-failure-routing` | open |
| G3 | The packet is a checklist: criterion, evidence, source, status (Met / Not found). | An example packet produced from a synthetic case that reproduces the article's three rows (six weeks of conservative therapy: Met; imaging confirms the diagnosis: Met; functional limitation documented: Not found), plus a schema test. | test, report | `case-packet-and-failure-routing` | open |
| G4 | Check 1: output must match its schema. | Test: malformed output goes to the reviewer. | test | `case-packet-and-failure-routing` | open |
| G5 | Check 2: every extracted value must appear in the source it cites. | Rule: exact substring of the cited line after Unicode NFC normalization only, at least 4 non-whitespace characters. Tests: value not at its location, near misses (one character, case, adjacent line), trivial value. Each goes to the reviewer. | test | `case-packet-and-failure-routing` | open |
| G6 | Check 3: every citation must come from this patient's record. | The patient is derived from the chart index by `doc_id`; the packet's or model's patient ID is ignored. Tests: another patient's document; another patient's document labeled with this case's patient ID; unknown `doc_id`. | test | `case-packet-and-failure-routing` | open |
| G7 | The agent approves only when all criteria are met and all checks pass. Anything else goes to a clinician with the gaps marked. | `decide(packet)` is code built on the shared checks module, and the model has no tools. Tests: both paths, the model is never given tools, and the agent and the approval service use the same checks module. Plus the recorded calls in B6. | test, recorded | `case-packet-and-failure-routing` | open |
| G8 | The approval service refuses forged packets. It rebuilds the verdict from trusted sources: criteria from the compiled policy for the request's (payer, CPT), each finding re-verified against the chart, the patient taken from the chart index. The hash proves integrity, not truth. | Tests: a forged packet marked all Met, with made-up findings and a valid hash, is refused; a relabeled other-patient citation is refused; status labels are ignored; the packet altered after hashing, a missing packet and a missing request record are each refused. Plus a mutation run with surviving mutants reported. | test, report | `case-packet-and-failure-routing` | open |
| G9 | The model's prose is a labeled summary and never affects a decision. | Test: changing or removing `model_summary` leaves `decide` and the approval service unchanged. | test | `case-packet-and-failure-routing` | open |

## Failure routing: every failure goes to a person

| # | Claim | Evidence that proves it | Type | Change | Status |
|---|---|---|---|---|---|
| F1 | Evidence extraction fails → route to reviewer, labeled "extraction failed". | Test with an injected extraction failure. | test | `case-packet-and-failure-routing` | open |
| F2 | Model returns no text → route to reviewer, with the stop reason. | Test with an empty response and a `max_tokens` response. | test | `case-packet-and-failure-routing` | open |
| F3 | Policy criteria not found → route to reviewer, labeled "no verified policy". | Test with an unknown CPT/payer pair. | test | `case-packet-and-failure-routing` | open |
| F4 | Model access denied → fail loudly and alert the operator. | Test with an injected AccessDenied, plus a deployed alarm and a recorded alarm state change. | test, deployed, recorded | `case-packet-and-failure-routing` | open |
| F5 | Each step has its own written, tested empty-output rule. | The per-step table in `docs/empty-output-rules.md`, with one test per row: zero findings → criterion Not found; no text, malformed or truncated → extraction failed with the stop reason; empty criteria → no verified policy; empty or failed summary → packet valid, summary marked missing; eligibility empty → eligibility unknown. | test | `case-packet-and-failure-routing` | open |
| F6 | A failure may slow a case down. It may never push a case toward denial. | Property test: no injected failure produces an approval or an adverse outcome; every failure ends in "routed to reviewer" or "operator alert". | test | `case-packet-and-failure-routing` | open |
| F7 | Every session ends in exactly one terminal outcome (approved, routed, operator alert). A session that ends without one becomes "needs review" and is routed. | Tests: an exception or early return ends as needs review; a second terminal outcome is refused and logged. A property test over injected failures. | test | `case-packet-and-failure-routing` | open |

## Lineage: prove the gate held

| # | Claim | Evidence that proves it | Type | Change | Status |
|---|---|---|---|---|---|
| L1 | The trace holds case ID, step, model ID, token counts, latency, stop reason and content hashes. | An exported OpenTelemetry trace from a deployed run, plus a schema test of the span attributes. | deployed, recorded, test | `evidence-record-and-trace` | open |
| L2 | The trace holds no chart text. | A scan of exported traces and the Runtime logs for every synthetic chart string, returning zero hits, committed as a report. The scan is also a test. | report, test | `evidence-record-and-trace` | open |
| L3 | The evidence record holds the packet, recommendation, citations, policy version, reviewer identity, decision and timestamps. | A recorded evidence record from a deployed run, plus a schema test. | recorded, test | `evidence-record-and-trace` | open |
| L4 | The evidence record lives in encrypted, write-once storage the agent cannot rewrite. | The deployed storage configuration (encryption, write-once setting), plus a recorded failed overwrite or delete attempt by the agent role. | deployed, recorded | `evidence-record-and-trace` | open: governance-mode Object Lock, so the demo can be torn down the same day; the article or README notes that production uses compliance mode |
| L5 | The evidence record lives in encrypted storage under a customer-managed key. | The deployed bucket encryption (SSE-KMS with the customer-managed key), a recorded `head-object` naming that key, and a recorded refusal of a write under any other key. | deployed, recorded | `evidence-record-and-trace` | open (article edited: "customer-managed keys", no per-tenant claim, PM 2026-10-16) |
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
| M7 | One real call to every candidate before building. Model families disagree about which parameters they accept, and some return a reasoning block before the answer. | A recorded access check per candidate model, with date and lifecycle status, the sampling parameters each model accepted or rejected, and whether a reasoning block came before the answer. | recorded | `evaluation-harness` | open. Extraction model done 2026-10-16: Claude Sonnet 4.6 ACTIVE; rejects `temperature` with `topP`; Claude 4.8 and 5.x refused for this account (`evidence/2026-10-16/model-access-extraction.json`). |
| M8 | The harness rate is published whatever it is. | The committed report, unedited. | report | `evaluation-harness` | open |
| M9 | One allow-list names the models, enforced in code and in IAM, with Regions pinned. Cross-Region routing is opt-in. | Code test (an unlisted model is rejected), plus the deployed IAM policy listing exactly the allow-listed ARNs. The extraction model is reachable only through the US inference profile (us-east-1, us-east-2, us-west-2), so the pinned set is those three Regions by explicit, recorded opt-in. Nova Pro is the single-Region alternative. | test, deployed | `gateway-and-policy` (platform) | open: the article's "Regions pinned" holds only as "three US Regions, by explicit opt-in". PM to confirm the wording or require Nova Pro. |

## AgentCore mapping (one deployed resource per row)

| # | Concern | Service | Evidence | Type | Change | Status |
|---|---|---|---|---|---|---|
| A1 | Run the agent, one case at a time: an isolated session per request. | Runtime | The deployed runtime, whose JWT authorizer admits only the `prior-auth-intake` client, plus two recorded invocations by `scripts/intake.py` with distinct, case-derived session IDs. | deployed, recorded | `case-packet-and-failure-routing` | open |
| A2 | Expose only safe tools behind one MCP endpoint per role: the agent's gateway, and a separate reviewer gateway. | Gateway | Same evidence as B1, B2 and B4 (layer 1). | deployed, recorded | `gateway-and-policy` | open (article Gateway row edited, 2026-10-16) |
| A3 | Make denial impossible for the agent. | Policy | Same evidence as B3, B4 and B6. | deployed, recorded | `gateway-and-policy` | open |
| A4 | Clinicians and the agent sign in as separate identities; tools authenticate with the gateway's role, so no secrets live in the agent. | Identity | Recorded listings: separate Cognito app clients for agent and clinician, each gateway's `allowedClients`, every gateway target's credential type (`GATEWAY_IAM_ROLE`), and the runtime environment showing no secret values. A test fails on any secret-like value in the runtime configuration. | deployed, recorded, test | `gateway-and-policy` | open (article edited per D3, 2026-10-16) |
| A5 | Memory is not used for patient data. Context lives only in the case's Runtime session. | Memory | The runtime configuration with no memory resource attached (recorded listing), an explicit IAM deny on Memory data-plane actions for the runtime role, and the per-case session evidence from A1. | deployed | `evidence-record-and-trace` | open (article edited) |
| A6 | Prove what happened: OpenTelemetry traces with IDs, timings and hashes, never chart text. | Observability | Same evidence as L1 and L2. | deployed, report | `evidence-record-and-trace` | open |

## Regulatory and external claims (citations, not code)

| # | Claim | Evidence | Type | Status |
|---|---|---|---|---|
| R1 | State law, starting with Washington and Colorado (2026 to 2027): AI cannot be the sole basis to deny care; Washington also covers delaying or modifying it. | Washington E2SSB 5395, Ch. 157, Laws of 2026, amending RCW 48.43.830(3): "Artificial intelligence shall not be the sole means used to deny, delay, or modify health care services"; effective June 11, 2026. Colorado HB26-1139, Session Laws 2026 Ch. 325, C.R.S. 10-16-112.7(5)(b): medical-necessity denials may not issue solely on AI output without approval by a licensed clinician; effective January 1, 2027. Illinois is not cited. | citation | proven (primary sources, 2026-10-16). Article edited: "among others" removed; the opening reads "now written into state law, starting with Washington and Colorado" (PM, 2026-10-16). |
| R2 | CMS-0057-F: standard decisions in 7 calendar days, expedited in 72 hours, a specific reason on every denial (January 2026). | The CMS final rule text. | citation | open |
| R3 | CMS-0057-F: payers expose a FHIR Prior Authorization API (January 2027). | The CMS final rule text. | citation | open |
| R4 | Prior authorization sits pre-service, on the X12 278 request and response. | X12 / CMS source. | citation | open |
| R5 | The rules ban automated adverse decisions, not automated processing; approving a clearly covered request is allowed. | Washington RCW 48.43.830(3)(a) as amended: "Algorithms may be used to process and approve prior authorization requests". Colorado C.R.S. 10-16-112.7(5)(a): AI "may be used to assist with utilization review, including expedited approvals". | citation | proven (primary sources, 2026-10-16) |
| R6 | Requests arrive as X12 278 transactions or as FHIR bundles following the Da Vinci Prior Authorization Support implementation guide. | The HL7 Da Vinci PAS implementation guide, and the CMS-0057-F text on the Prior Authorization API. | citation | open |

## Not tracked here

Author experience, earlier articles (the text-to-SQL, OKF and one-change articles) and personal context (the clinic, the earlier platform work) are the author's own statements, not claims about this implementation. Design opinions (for example, that translation belongs in front of the agent) are not tracked either.

One publishing rule follows from the cut line: the article states L5 (customer-managed keys). If that row is still open at publication, the sentence waits or is softened.
