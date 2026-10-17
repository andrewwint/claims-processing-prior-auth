# Design

## Context

This change depends on the gateways, the policies and the allow-list from `gateway-and-policy`. Runtime constraints are in [docs/contract-notes.md](../../../docs/contract-notes.md): metadata service v2, telemetry redaction, and JWT invocation.

The rule underneath every decision here: **an approval is derived only from trusted sources.** The packet is a claim to be checked, never an input to be believed.

## Decisions

### D1. Trusted sources and the stores (as built, PM 2026-10-16)

**Read-only, bundled at build time.** `scripts/stage_bundle.py` copies the committed synthetic data into the Lambda and Runtime packages (`prior_auth/trusted/`). The stores are immutable at run time: no role, model or tool can write them. They are read through `prior_auth.stores`.

| Source | Holds | Built from | Read by |
|---|---|---|---|
| Compiled criteria, `trusted/policies/<payer>/<cpt>.json` | criterion ID, text, policy version, source location, evidence rule | `data/policies/compile.py` from `data/policies/source/` | case tools, runtime, approval service |
| Chart documents, `trusted/charts/<doc_id>.json` | the pages and lines of one synthetic document, and its kind | `data/cases/generate.py` | case tools, runtime, approval service |
| Chart index, `trusted/charts/index.json` | `doc_id` → owning patient ID | `data/cases/generate.py` | runtime, approval service |
| Request records, `trusted/cases/cases.json` | case ID, member, payer, CPT, patient, tenant, the case's documents | `data/cases/generate.py` | case tools, runtime, approval service |
| Eligibility, `trusted/cases/eligibility.json` | member → payer, plan, coverage dates, covered CPT codes | `data/cases/generate.py` | `check_eligibility` |

**Written at run time, in the evidence bucket** (`evidence-record-and-trace`):

| Prefix | Holds | Written by | Read by |
|---|---|---|---|
| `packets/<packet_id>.json` | the packet (untrusted claims); `packet_id` is `PKT-<case_id>`, so a packet cannot choose its case | the runtime role | the approval service role |
| `queue/<case_id>.json` | routed cases for the reviewer | the case-tool role (`route_to_reviewer`) | the workbench (operator credentials, demo only) |
| `recommendations/<case_id>.json` | the recommendation record | the runtime role | the reviewer service, the verifier |
| `decisions/<case_id>.json` | the decision record | the reviewer and approval service roles | the verifier |

- **IAM.**
  - Each role can write only its own prefixes, and the bucket policy denies everything else (`evidence-record-and-trace` D3).
  - No role has write access to the bundled stores, because they are not stored anywhere writable.
  - The runtime role has no permission for `record_approval` outside the gateway.
- **Changing the data** means a commit, a rebuild and a deploy. Each deploy is recorded with its SHA in `evidence/deploys.jsonl`.

### D2. One checks module

`src/prior_auth/checks/` is a single package. The runtime's `decide()` and the approval service both import it, and a test asserts they reference the same module object. Another test asserts that the deployed Lambda bundle contains a byte-identical copy.

- **Check 1, schema.** The packet has a `case_id` and a list of findings. Each finding has `criterion_id`, `doc_id`, `page`, `line` and `value`. Any finding for a criterion ID outside the compiled policy fails the check.
- **Values come from the chart, not the model (PM, 2026-10-16).**
  - The model returns citations only: `(criterion_id, doc_id, page, line)`.
  - `checks.findings_from_citations()` fills each finding's `value` with the cited line from the trusted chart store. Any value the model supplied is dropped, and a citation to a missing line gets an empty value.
- **Check 2, source match.** The `value` must equal the text at (`doc_id`, `page`, `line`) exactly, after Unicode NFC normalization and nothing else. For an honest packet this always holds. It still catches a stored packet whose values were edited after the fact. A value shorter than 4 non-whitespace characters fails.
- **Check 3, evidence rule.** The cited line, read from the trusted chart, must satisfy the criterion's compiled evidence rule (design D9).
- **Check 4, same patient.** The owning patient is looked up as `index[doc_id]` and compared with the request record's patient ID.
  - The packet's `patient_id`, and any patient ID the model supplied, are ignored.
  - A `doc_id` missing from the index fails the check.
- **`recompute(packet, request, criteria, chart)`** rebuilds the verdict:
  1. Run check 1.
  2. Take the criteria from the compiled policy for the request's (payer, CPT), never from the packet.
  3. Check every finding with checks 2, 3 and 4.
  4. A criterion is Met only if it has at least one finding and every finding for it verifies.
  5. Return each criterion's status, all failures and the gaps.

  Status labels in the packet are ignored.

### D3. A Strands agent gathers the case; the decision is code (PM, 2026-10-16)

- **The agent is a Strands agent** on AgentCore Runtime. It connects to the agent gateway over MCP with the agent's client-credentials token, and is given **exactly three tools**:
  - `check_eligibility`
  - `fetch_policy_criteria`
  - `extract_clinical_evidence`

  It uses them to assemble the case: real tool use, with every call evaluated by Cedar as the agent identity.
- **Extraction schema.** The agent's final output is structured:

  ```
  {"citations": [{"criterion_id": str, "doc_id": str, "page": int, "line": int}], "summary": str}
  ```

  It returns citations only, never quoted values. Code builds the findings from the chart store (D2) and stores the summary as the labeled model summary.
- **The tool filter.** The MCP client lists the gateway's tools and keeps only those three by exact name, before the agent is built. A test asserts that the Strands agent's tool list is exactly those three. `record_approval` and `route_to_reviewer` are never given to the agent.
- **`decide(packet)` (`src/prior_auth/decide.py`) runs as code after the agent finishes.** It returns `Approve(packet_id, packet_hash)` or `Route(reason, gaps)`, computed by `checks.recompute()`. It is the **only** caller of `record_approval` and `route_to_reviewer`, under the same agent identity. No other code path calls either tool, and a test asserts that.
- **Same identity, different code paths.** Cedar permits the agent identity to call all five tools. The model can choose among the three gathering tools only, because the other two are not in its tool list. The approval service's server-side rebuild is unchanged: even a forged approval call is refused.
- **No Knowledge Base.** Policy lookup is an exact match on (payer, CPT) against the compiled criteria. There is no retrieval and no similarity search (PM, 2026-10-16).
- **The model summary** is stored under `model_summary` with `label: "Model summary. Not used for any decision."` Neither `decide()` nor `recompute()` reads it, and a test changes it and shows the decision does not change.

### D4. The approval service never trusts the packet

`record_approval(packet_id, packet_hash)`:
1. loads the stored packet (unknown → refuse)
2. verifies the SHA-256 of its canonical JSON (mismatch → refuse; this proves integrity, not truth)
3. derives the case from the packet ID (`PKT-<case_id>`) and loads its request record from the bundled stores (missing → refuse)
4. loads the compiled criteria for the request's (payer, CPT) (missing → refuse, "no verified policy")
5. runs `checks.recompute()` against the bundled chart documents and index
6. records the approval only if every criterion is Met and nothing failed

It writes nothing on refusal and returns the failures. This replaces the fixture-backed service from `gateway-and-policy`, which uses the same algorithm against fixture copies of the trusted sources.

### D5. Session invariant

- **Recorder.** `src/prior_auth/agent/session.py` holds a single-assignment outcome recorder.
- **Terminal outcomes:** `approved`, `routed`, `operator_alert`.
- **Ending without one.** If the session ends without a terminal outcome (an exception, a timeout, or a path that returns early), the wrapper's `finally` block records `needs_review` and routes the case with the reason "session ended without an outcome".
- **Second attempt.** A second attempt to set a terminal outcome is refused and logged as an invariant violation, with a metric. The first outcome stands.

### D6. Per-step empty-output table

This replaces any global "empty output" rule.

| Step | Condition | Outcome |
|---|---|---|
| Eligibility | lookup empty or failed | routed, "eligibility unknown" |
| Criteria lookup | no compiled file, or the file has no criteria | routed, "no verified policy" (F3) |
| Extraction | valid output with zero findings for a criterion | that criterion is "Not found"; the case continues and ends routed, with the gap |
| Extraction | no text, malformed output, or truncated (`stopReason: max_tokens`) | routed, "extraction failed", with the stop reason (F1, F2) |
| Extraction | throttled or timed out after retries | routed, "extraction failed", with the error class |
| Extraction | access denied | `operator_alert`: metric and CloudWatch alarm (F4) |
| Model summary | empty or failed | the packet stays valid, the summary is marked "missing", and the decision is unaffected |
| Any step | unexpected exception | routed, "needs review" ("session ended without an outcome"); the exception class is logged |
| `record_approval` | refused by the approval service, denied by Cedar, or errored | routed to the reviewer with the reason; counted as a decide-vs-service disagreement |
| `route_to_reviewer` | fails | `operator_alert`: the case cannot reach a person, so an operator must act |

The eligibility row and the last two extraction-adjacent rows (throttling and unexpected exceptions) go beyond the PM's four rows. They exist so that no step is left without a rule.

### D7. Runtime and intake

- **Hosting.** A Python CDK `Runtime`:
  - CodeZip ARM64 build, HTTP protocol, public network mode
  - a JWT authorizer whose allowed client is the `prior-auth-intake` app client only (client credentials)
  - models from the allow-list
- **Intake.** `scripts/intake.py` names a case from the bundled request records, then invokes the runtime with a token from the intake client and a session ID that names the case and is unique per request. (Finding, 2026-10-17: a session ID derived from the case alone was reused on resubmission, and the reused session ran the pre-deploy code. The new approval service refused its packet, which had no run ID, so the case was routed; nothing was approved.)
- **Session IDs.** `runtimeSessionId` must be 33–256 characters, and it doubles as an idempotency token (contract notes). The ID is `prior-auth-case-<case_id>-<first 16 hex of sha256(case_id)>`: deterministic per case, and always at least 33 characters. A test checks the length for the shortest possible case ID.
- **Agent token without a secret (PM, 2026-10-16; contract-read in the notes).**
  - An AgentCore Identity OAuth2 credential provider (vendor `CognitoOauth2`, client credentials) holds the agent client's secret in the token vault.
  - The runtime obtains the gateway token with `@requires_access_token(provider_name=..., scopes=["prior-auth/tools"], auth_flow="M2M")`, using the workload access token Runtime supplies.
  - The provider is created by a post-deploy script that reads the client secret from Cognito in memory, so the secret never appears in a CloudFormation template.
  - The runtime's environment holds no secret, so the article's Identity row stands.
- **Metadata service v2.** `scripts/require_mmdsv2.py` runs after every deploy.
- **Telemetry (PM, 2026-10-16).**
  - **Strands:** content redaction is on from the first invocation (`OTEL_SEMCONV_STABILITY_OPT_IN`, Strands ≥ 1.47). It covers prompts, completions and system instructions. Tool inputs and outputs are checked separately, because chart text arrives as tool results.
  - **ADOT and botocore** (measured by task 0.2): ADOT defaults botocore's Bedrock content capture to on, which emits content as log records. The runtime sets `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=false`. Both settings live in `prior_auth.agent.telemetry.RUNTIME_TELEMETRY_ENV`, and the runtime stack must use that constant.
  - **Runtime `APPLICATION_LOGS`** are not enabled; they include the request payload.
  - **The proof** stays the canary scan with its positive control (`evidence-record-and-trace`).
- **Network.** Public network mode behind the JWT authorizer. VPC mode is not used: its network interfaces can remain for hours after deletion, which conflicts with same-day verified teardown. The README notes production uses VPC mode.

### D8. Extraction model and Regions (PM, 2026-10-16)

- **Runtime default: Amazon Nova Pro** (`amazon.nova-pro-v1:0`).
  - It runs on demand in us-east-1 only, so "Regions pinned" holds by default.
  - It is sent temperature 0.
- **Opt-in: Claude Sonnet 4.6** (`anthropic.claude-sonnet-4-6`), through `us.anthropic.claude-sonnet-4-6`.
  - It routes across us-east-1, us-east-2 and us-west-2, as a documented, recorded opt-in exercised in the harness.
  - It is sent temperature 0 only, since it rejects `temperature` with `topP`.
- **Allow-list and IAM.** Both name exactly Nova Pro in us-east-1, plus the Sonnet 4.6 profile and its three foundation-model ARNs. The opt-in is off unless configured.
- **Refused for this account** (each probed, each `AccessDeniedException`, recorded):
  - `us.anthropic.claude-opus-4-8`
  - `us.anthropic.claude-sonnet-5`
  - `us.anthropic.claude-sonnet-5-5`
  - `us.anthropic.claude-opus-5-5`
  - `us.anthropic.claude-haiku-5-5`

  No other model was probed.

### D9. Compiled evidence rules bind findings to criteria (second security review, X1)

Citation accuracy is not support. A line can be cited exactly and still say nothing about the criterion, or say the opposite. So each compiled criterion carries an `evidence_rule`, written in the source policy and verified by the compile step. It is applied to the **whole cited line** from the trusted chart, as `checks/core.py` does:
- **`doc_kinds`:** the document kinds that may support it. The kind comes from the trusted chart store, never the packet.
- **`pattern`:** searched for in the cited line (patterns carry their own word boundaries). Every named numeric group must have a `minimums` entry, and number words up to twenty are read as numbers.
- **Disqualifying terms:** **anywhere on the cited line**, any negating, hedging or planning term ("no", "not", "n't", "without", "denies", "rule out", "plan", "goal", "history of", "excluded", "prior", and the rest of `DISQUALIFYING_TERMS`) disqualifies the line.

A finding counts only if it passes source match, same patient and its criterion's rule. One cited line may support only one criterion. A criterion with no compiled rule is never Met. The rules are deliberately narrow: a true finding phrased differently routes to a reviewer, which costs time, not safety. The allow-list redesign (E1–E3) is in `post-monday-hardening`.

### D10. Operator alert

- **Path.** Access denied emits `PriorAuth/Operator` `ModelAccessDenied` (`src/prior_auth/agent/operator.py`). The CloudWatch alarm `prior-auth-model-access-denied`, already deployed, goes into ALARM. There is no SNS topic (PM, 2026-10-16); the recorded alarm state change is the evidence.

### D11. Mutation testing

Deferred to `post-monday-hardening`.

## Risks / Trade-offs

- [The model invents a citation] → Checks 2 and 4 fail it, and the criterion is not Met.
- [A real quote proves nothing about the criterion] → Check 3 fails it.
- [A forged or tampered packet reaches the approval service] → The hash catches tampering after storage. `recompute()` catches forged content, because it never reads statuses or patient IDs from the packet.
- [Strict matching rejects true findings that the model paraphrased] → They route to a reviewer. That costs time, not safety. The extraction prompt asks for verbatim quotes.
- [Cross-Region routing] → It is limited to three named US Regions by an explicit opt-in. Nova Pro is the single-Region fallback.
- [Redaction misses error text] → `evidence-record-and-trace` adds the canary scan as a test.
- [Metadata service v2 step forgotten] → The deploy script runs it, and a test asserts that.
