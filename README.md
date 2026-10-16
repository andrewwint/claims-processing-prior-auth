# prior-auth-agentcore

Reference implementation for the article **"Build the Case, Let the Clinician Decide."**

An agent on Amazon Bedrock AgentCore assembles a prior-authorization case: it gathers the evidence, checks it, and cites every statement. A clinician makes the decision.

The agent's gateway has no tool for an adverse determination. That tool lives on a separate reviewer gateway, which admits clinicians only and where a Cedar policy forbids the action for the agent's identity. The agent may submit an approval, but the approval service records it only after re-running every check on the stored packet itself.

## Start here

If you have ten minutes, read in this order:

1. **The article:** [docs/article-draft.md](docs/article-draft.md). It makes the claims; this repository backs them.
2. **The demo:** six beats, run with `python -m scripts.demo <beat>`.

   | Beat | What it shows | Status |
   |---|---|---|
   | 1 | Both gateways side by side: the agent's five case-building tools and no denial tool; the reviewer gateway's clinician-only tools | **Proven** |
   | 2 | The Strands agent (three gathering tools, Nova Pro) builds a cited packet; `decide()` approves | **Proven** |
   | 3 | One note removed: routed to the reviewer, gap marked | **Proven** |
   | 4 | The agent refused at the reviewer gateway, first by the authorizer, then by Cedar | **Proven** |
   | 5 | A clinician succeeds with the same tool; the decision record chains to the recommendation | In progress |
   | 6 | A trace with no chart text (canary scan with a positive control) | In progress |

   After Monday: the harness report (six cases × Nova Pro and Sonnet 4.6 × three trials).

3. **The claims ledger:** [openspec/claims-ledger.md](openspec/claims-ledger.md). One row per article claim, with the evidence that proves it and its status.
4. **The evidence:** [evidence/](evidence/). Redacted records from deployed runs: gateway configuration, policy text, live allowed and denied calls, and validation findings.

**Status:** beats 1–4 are deployed and proven: the gateways, Cedar policies, and the Strands agent on AgentCore Runtime. Beats 5 and 6 are being built. The article is published only after every ledger row is green.

## What this repository demonstrates

- **Two gateways.** The agent's gateway has no denial tool. The reviewer gateway rejects the agent's token at sign-in, and a Cedar `forbid` stands behind that. Both layers are shown with recorded denied calls.
- **Server-verified auto-approval:** `record_approval` takes a packet reference, and the approval service re-runs the checks on the stored packet before recording anything.
- **A cited case packet**, with four checks run before anyone sees it: schema, source match, the criterion's evidence rule, and same patient.
- **Failure routing:** every failure mode goes to a human reviewer, never to a default.
- **Clean telemetry:** traces hold identifiers, timings, and hashes, and a scan shows they contain no chart text.
- **A write-once evidence record** whose hash matches the trace.
- **A pre-registered evaluation** that reports the false auto-approval rate on counterfactual cases, with every trial shown.

## Repository map

| Folder | What it holds | Demo beat / ledger rows |
|---|---|---|
| `infra/` | CDK app (`infra/app.py`): budgets, gateways, Cognito, policy engine, Cedar policies (`cedar.py`) | Beats 1, 4, 5 · B1–B6, A2–A4, M9 |
| `src/prior_auth/checks/` | The four checks and `recompute()`, shared by `decide()` and the approval service | Beats 2, 3 · G4–G8, G11 |
| `src/prior_auth/handlers/` | Lambda handlers: case tools, the approval service, reviewer tools, pre-token trigger | Beats 1, 2, 5 · B6, B8 |
| `src/prior_auth/agent/` | The Strands agent and its session wrapper (in progress) | Beats 2, 3 · G10, F1–F7, A1 |
| `workbench/` | The clinician's local page (in progress) | Beat 5 · B8, L3 |
| `data/` | Synthetic policies, charts and cases; `SYNTHETIC.md` | Beats 2, 3, 6 · G1–G3 |
| `evaluation/` | The harness and its one-page report (in progress) | Beat 6 · M1–M8 |
| `scripts/` | Deploy guard, teardown and verifier, evidence recorders, `demo.py` | All beats · guardrails |
| `evidence/` | Redacted, committed evidence from deployed runs | All proven ledger rows |
| `docs/` | Principles, AgentCore contract notes, the article draft | B5, R1–R6 |
| `openspec/` | The claims ledger and the OpenSpec changes | Definition of done |
| `tests/` | The test suite, including the real-payer-name and evidence-redaction scans | All rows typed `test` |

## Principles

See [docs/principles.md](docs/principles.md).

## Why there is no Knowledge Base

A decision gate needs a verified criterion, not a retrieved one. Payer criteria are compiled and verified upstream, once. Each criterion carries its policy version, its source location and an evidence rule. At decision time the agent looks them up by exact match on (payer, CPT). Retrieval over a vector store is the right tool for open-ended questions; here it would add a step that can return the wrong criterion.

## Production notes

This repository is a reference implementation that can be torn down the same day. A production deployment would differ in at least two ways:

- **The runtime runs in VPC mode.** The demo uses public mode behind a JWT authorizer.
- **The evidence store uses Object Lock in compliance mode,** with the retention its records policy requires. The demo uses governance mode so it can be torn down the same day.

## Threat model

**Inside the trust boundary.** AWS account administrators. They can change any control here, including the Cedar policies. The controls are aimed at the agent and at callers outside the account.

**The boundary the article describes.** It holds at three points:
- **The agent's gateway** has no denial tool.
- **The reviewer gateway** admits only the clinician app client, and only tokens in the clinician group.
- **The Cedar policies** forbid the denial action for every non-clinician, and explicitly for the agent.

**Residual risks, stated plainly:**
- **Direct Lambda invocation.** A principal in the account allowed to call `lambda:InvokeFunction` can invoke the tool Lambdas directly and skip both gateway layers. Gateway does not pass the caller's identity to Lambda targets, so the denial Lambda cannot verify the clinician itself. This does not let anyone forge an approval: `record_approval` rebuilds every verdict from trusted sources, whatever the call path.
- **Reviewer identity.** A request interceptor on the reviewer gateway validates the clinician's token and overwrites the reviewer identity and tenant in each call, so a client cannot claim to be someone else. That holds only for calls through the gateway; the direct-invocation risk above still applies.
- **Governance mode.** The evidence store uses Object Lock in governance mode, and only the teardown role may bypass it. Production would use compliance mode.

## Known limitations

This repository is built backwards from a five-minute demo. These are deliberately out of scope, and each one is planned in [`openspec/changes/post-monday-hardening`](openspec/changes/post-monday-hardening/proposal.md).

- **Reviewer identity is reported, not verified.** Decision records name the reviewer as the clinician app reports it. A gateway request interceptor that validates the clinician's token and overwrites the identity is designed but not built.
- **One tenant.** There are no tenant groups in use, no cross-tenant tests, and no per-tenant keys. The workbench page reads the review queue with the operator's local AWS credentials. Only decisions go through the reviewer gateway under the clinician's token.
- **Evidence rules are narrow.** They cover the demo cases. Adversarial review found further gaps that would let a negated or hedged line count as support:
  - negators outside the list ("w/o", "neg.", "cannot confirm", typographic apostrophes, fullwidth or zero-width characters)
  - negation in a section header above the line
  - planned or ordered therapy counted as completed

  The fix is an allow-list design: whole-line templates in allowed sections, NFKC normalization and invisible-character removal.
- **Operator alerting is a metric only.** There is no deployed alarm or SNS topic.
- **Memory is not used,** and no Memory evidence is recorded. **No Knowledge Base:** policy lookup is an exact match on (payer, CPT).
- **The decision clock** is tested against the 7-day and 72-hour windows only, not edge cases.
- **No redeploy-from-scratch test.** One verified teardown is recorded.
- **No mutation testing** of the checks module.
- **Direct Lambda invocation** by account administrators bypasses both gateway layers (see the threat model above).

## Data

This repository uses synthetic data only. It contains no real patient data, and it must never be used with any.
