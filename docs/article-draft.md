# Build the Case, Let the Clinician Decide

Oct 16, 2026 · @Andrew Wint

Most agentic prior authorization designs start with a model. Pick one, prompt it with the payer policy, let it read the chart, ask it for a decision.

That is the wrong place to start. The hard part is not what the agent can decide. It is the one thing it may not decide.

An agent can check eligibility. It can assemble the packet, read the clinical notes, match them to policy criteria, and recommend. It cannot deny care on its own. That line is now written into state law, starting with Washington and Colorado.

This article designs a prior authorization agent on Amazon Bedrock AgentCore from that line outward. The agent builds the case. The clinician decides.

## Start with the gate

Prior authorization is the approval a payer gives before a service happens. On the claims lifecycle it sits pre-service, on the X12 278 request and response. Decisions made here shape everything downstream.

Requests arrive two ways: as X12 278 transactions, or as FHIR bundles following the Da Vinci Prior Authorization Support guide. Translating between them is integration work. It belongs in front of the agent, not inside it.

Two sets of rules now frame those decisions.

| Rule | What it requires | What it means for an agent |
| --- | --- | --- |
| State AI laws, 2026 to 2027 (Washington E2SSB 5395, Colorado HB26-1139) | AI may assist review but cannot be the sole basis to deny care. Washington's law also covers delaying or modifying it | The agent recommends. A licensed clinician owns every adverse decision |
| CMS-0057-F, decision timeframes (Jan 2026) | Standard decisions in 7 calendar days, expedited in 72 hours, a specific reason on every denial | Speed matters, and every denial needs a reason a person can read |
| CMS-0057-F, Prior Authorization API (Jan 2027) | Payers expose prior authorization through a FHIR API | Requests arrive as structured data, ready for an agent to work |

The rules are asymmetric. They do not ban automated processing. They ban automated adverse decisions: denying care, and in Washington, delaying or modifying it too. Approving a clearly covered request is allowed, and the CMS clocks reward it. That asymmetry is why the agent can hold an approval tool and never a denial tool.

Read together, they describe the job. Approve what is clearly covered, fast. Build the case for everything else. Put the case in front of a clinician before the clock runs out.

The design question is not whether an agent can judge medical necessity. It is where the human gate sits, what the agent hands the reviewer, and how you prove the gate held.

## Draw the decision flow

The agent works the whole pre-service path. It stops at one place.

&#91;embedded content: prior authorization decision flow · agent and clinician lanes\]

The agent approves only when every criterion is met and every check passes. A miss or any failure goes to a clinician with the case already built. Only the clinician can deny.

Here it is running on AgentCore, with synthetic data: \[DEMO VIDEO LINK\]

## Enforce the boundary outside the prompt

You can write "never deny a request" in a system prompt. The model will usually listen. Usually is not a compliance posture.

I learned this the hard way with text-to-SQL. In [Why Your AI Agent Should Never Write SQL](https://medium.com/@andrewwint/why-your-ai-agent-should-never-write-sql-a42949099a79), three rounds of adversarial review broke the guard. The last break had no patch. The fix was to take the capability away and give the agent allow-listed tools instead.

The same move works here. The agent never gets a tool that can deny.

| Tool | What it does | Agent may call |
| --- | --- | --- |
| `check_eligibility` | Coverage and benefits for the member and service | Yes |
| `fetch_policy_criteria` | Verified criteria for the CPT code and payer | Yes |
| `extract_clinical_evidence` | Pulls findings from the record, each with its source | Yes |
| `record_approval` | Approves a request whose criteria are all met | Yes, under policy |
| `route_to_reviewer` | Sends the case packet to a clinician queue | Yes |
| `record_adverse_determination` | Denies, delays, or modifies care | No. Only the reviewer app holds it |

AgentCore Gateway fronts every tool, and Policy in AgentCore evaluates each call against Cedar rules before the tool runs. So the boundary is written twice. The agent's gateway does not expose the denial tool at all. That tool lives on a separate reviewer gateway that only clinicians can sign in to. A Cedar `forbid` stands behind it, naming the agent's identity and anyone without the clinician role, so the call fails even if the agent reaches the tool.

```
forbid(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"ReviewerTools___record_adverse_determination",
  resource == AgentCore::Gateway::"<reviewer-gateway-arn>"
) when { principal == AgentCore::OAuthUser::"<agent-client-id>" || !(principal.hasTag("pa_role") && principal.getTag("pa_role") == "clinician") };
```

Policy checks the shape of a call. It cannot check whether the agent's inputs are true. That job belongs to grounding.

## Ground every recommendation

A reviewer under a 72-hour clock should not search the chart. The agent should hand over a packet where every claim points at its source.

Payer medical policies are long PDFs that change. Chunking them into a vector store and hoping retrieval finds the right criterion is the weak link. In Beyond the Vector DB: Grounded, Auditable Agents with Amazon Bedrock AgentCore and OKF, I argued for a compile step instead. Verify the source once, upstream, and ship focused concept files the agent can cite. [Orchestrating the Upstream OKF Compiler](https://medium.com/towards-aws/orchestrating-the-upstream-okf-compiler-scaling-context-verification-with-aws-mwaa-and-sagemaker-5ba25b348e2b) showed how to run that compile at scale.

For prior authorization, each payer policy compiles into one verified file per procedure. Each criterion carries its policy version, its location in the source, and a rule for what evidence can satisfy it.

The packet then reads like a checklist.

| Criterion | Evidence in the record | Source | Status |
| --- | --- | --- | --- |
| Six weeks of conservative therapy | PT notes, eight visits over seven weeks | Therapy note, page and line cited | Met |
| Imaging confirms the diagnosis | MRI report names the finding | Radiology report, line cited | Met |
| Functional limitation documented | No measure found | None | Not found |

Four checks run before the packet moves. Output must match its schema. Every extracted value must appear in the source it cites. The cited text must satisfy the criterion's evidence rule, because a real quote on the right line can still prove nothing. Every citation must come from this patient's record.

All criteria met, every citation verified, and every check passed means the agent may call `record_approval`. Anything else goes to a clinician, with the gaps marked.

Inside the agent, that decision is code. The model reads the chart and writes the summary. It never chooses which tool ends the case.

## Fail toward a human

Model calls fail. They time out, get throttled, hit a token limit, or return nothing. What the system does next is a clinical decision, whether you meant it to be or not.

The common pattern is a broad `except` that falls back to a default and keeps going. In most software that is resilience. Here it is an adverse determination by omission. An evidence step that fails quietly returns an empty list. Empty evidence looks like unmet criteria. Unmet criteria look like a denial.

So every failure has one destination.

| What goes wrong | Wrong default | Right default |
| --- | --- | --- |
| Evidence extraction fails | Empty evidence, keep going | Route to reviewer, labeled "extraction failed" |
| Model returns no text | Treat as no criteria | Route to reviewer, with the stop reason |
| Policy criteria not found | Generic placeholder criteria | Route to reviewer, labeled "no verified policy" |
| Model access denied | Fall back to string matching | Fail loudly, alert the operator |

There is a subtler trap. Empty output does not mean the same thing at every step. No criteria for a code might be a missing policy. No evidence might be a thin chart. Each step needs its own empty-output rule, written and tested on purpose.

The rule underneath all of it: a failure may slow a case down. It may never push a case toward denial.

## Prove the gate held

An auditor will not ask whether your agent is accurate. They will ask about one case. What did the agent recommend? On what evidence? Who decided, and when?

That is a lineage problem, and it has a built-in tension. To prove what a model recommended, you have to keep it. Keeping it puts protected health information somewhere. Logs are the worst place for it.

The answer is two records with two jobs.

| Record | Holds | Lives in |
| --- | --- | --- |
| Trace | Case ID, step, model ID, token counts, latency, stop reason, content hashes | AgentCore Observability, exported over OpenTelemetry |
| Evidence record | The packet, the recommendation, citations, policy version, the reviewer's identity as the clinician app reports it, decision, timestamps | Encrypted, write-once storage under customer-managed keys |

The trace answers "what happened" without holding a word of the chart. The hash in the trace proves the evidence record was not changed after the fact. The timestamps answer the CMS clock.

Defaults work against you here. In this build, two separate settings each sent chart text to telemetry, one into spans and one into log records. Turning off either one alone still leaked. Only a planted canary, searched for in every span and log record the runs produced, proved both were closed.

I did this kind of work at Crisis Text Line: PII redaction, data contracts, and audit hardening on a platform holding some of the most sensitive conversations there are. The lesson carries over. Decide what may never appear in a log before you write the first logging line.

## Choose models with evidence

Once the agent cannot deny, it can only make two mistakes. It can approve a case that needed a clinician. Or it can send a clinician a case it could have approved. The first is a safety error. The second is a cost.

That gives the bake-off two numbers to watch.

| Metric | Defined as | Direction |
| --- | --- | --- |
| False auto-approval rate | Cases the agent approved that should have gone to a clinician. In a test harness, the case author's label stands in for that clinician | As close to zero as you can get |
| Auto-approval rate | Share of requests that clear without a human touch | Higher, once the first number holds |

The cases are synthetic, because real charts do not belong in a test harness. The useful ones are counterfactual. Take a case that clearly meets criteria. Remove one piece of evidence. Keep everything else fixed. The agent should stop approving and route to a reviewer.

I used the same one-change method in [The Reader Who Never Asks](https://medium.com/@andrewwint/the-reader-who-never-asks-46534ee4c702), where one word split how models read a sentence. In prior authorization, the change is one missing note.

A few rules keep the comparison honest. Run each case several times and show every trial. Count a response cut off at the token limit as a failure, not a skip. Record the sampling settings each model was given, because model families accept different ones. Here, one candidate rejected temperature and top-p set together. Label the cases as synthetic and author-labeled, never as clinical ground truth.

On six synthetic cases, three trials each, Nova Pro and Sonnet 4.6 each made zero false approvals in twelve trials that needed review. That's a small sample: the 95% upper bound is still 25%. Sonnet cleared one more approvable case, at about five times the cost.

Make one real call to every candidate before you build. Model families disagree about which sampling parameters they accept. You want that surprise on day one.

## Map it to AgentCore

Each concern above lands on a specific AgentCore service. None of them depends on which model you pick.

| Concern | AgentCore service | How it is used |
| --- | --- | --- |
| Run the agent, one case at a time | Runtime | An isolated session per prior authorization request |
| Expose only safe tools | Gateway | Two gateways. The agent's holds the five case-building tools. The reviewer's holds the denial tool, for clinicians only |
| Make denial impossible for the agent | Policy | Cedar rules evaluated on every tool call, with a `forbid` on adverse determinations |
| Reach payer systems without shared secrets | Identity | Clinicians and the agent sign in as separate identities. The agent's gateway token comes from AgentCore Identity, which keeps the client secret in its vault, and tools run under the gateway's role. No secret is in the agent's code or configuration |
| Keep context inside the case | Memory | Not used for patient data. Context lives only in the case's Runtime session |
| Prove what happened | Observability | OpenTelemetry traces with IDs, timings, and hashes, never chart text |

Two things are kept apart on purpose. The evidence record lives in encrypted, write-once storage the agent cannot rewrite. And the denial tool is reachable only through the reviewer gateway, under the clinician's own identity.

Model choice becomes configuration. One allow-list names the models the agent may use, enforced in code and in IAM, with Regions pinned. Cross-Region routing is something you opt into, not something you discover.

## Build the case

An agent can shorten the wait for a decision. It can clear the obvious approvals in minutes and hand a clinician a finished case for the rest. It should never be the one who says no.

The design follows from that one rule. Take the denial tool away and enforce it outside the prompt. Ground every claim in a cited source. Send every failure to a person. Keep a record an auditor can follow, with no chart text in the logs. Choose models by how rarely they approve what they should not.

The reference implementation is on GitHub at [andrewwint/claims-processing-prior-auth](https://github.com/andrewwint/claims-processing-prior-auth). Every claim about how the system behaves maps to a test or a recorded artifact there, and every regulatory claim cites its source.
