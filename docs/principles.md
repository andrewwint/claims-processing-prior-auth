# Principles

These principles govern every design and code decision in this repository. Each one is enforced by a test, a policy, or a gate, not by a reminder.

## Decisions

1. **The agent builds the case; a clinician decides.** The agent gathers evidence, checks it, and assembles a cited packet. It cannot issue an adverse determination. The agent's gateway has no tool for it. The tool exists only on a separate reviewer gateway, which admits clinicians only and where a policy forbids the action for the agent's identity.
2. **Approval is narrow and enforced outside the model.** The agent submits an approval by naming a stored packet and its hash. The approval service loads that packet, re-runs every check itself, and records the approval only if all criteria are met and all checks pass. The policy engine checks only that the call is well-formed. A prompt instruction is never the control, and neither is a value the agent asserts.
3. **Every failure goes to a person.** A failed, denied, empty, or truncated model call produces a typed "needs review" outcome with a reason. It never becomes a plausible default, an empty result, or a silent pass.

## Evidence

4. **Every statement in a packet cites its source.** Three checks run before a packet is shown: the packet matches its schema, each cited value matches its source, and every source belongs to the same patient.
5. **Evidence records are write-once.** Each decision writes a tamper-evident record whose hash is also carried in the trace, so the two can be checked against each other.
6. **Telemetry carries identifiers, timings, and hashes, not clinical text.** A scan of traces and logs is part of the test suite.

## Boundaries

7. **Controls run at the point of use.** Checks sit at the tool, query, and response boundary, not in callers or prompts. Tool inputs are typed, so the model fills slots instead of writing free-form commands.
8. **Every endpoint authenticates the caller and checks ownership.** Records are owned. Lookups use exact identifiers and never partial matches.
9. **Models come from an allow-list.** Access is confirmed with a real call before use. Lifecycle status is recorded with its source and date. Sampling settings follow the model, not the step.
10. **Region and routing are explicit.** Where data is processed is configuration, chosen on purpose and documented, and defaults to the deployment Region.
11. **Deployment outputs and account identifiers are never committed.**

## Evaluation

12. **Evaluation is pre-registered.** The questions, cases, metrics, and stopping rules are committed before any run. The primary metric is the false auto-approval rate on counterfactual cases. Every trial is reported, and N is stated next to every number.
13. **The harness must be able to fail.** Before a result is trusted, the harness is shown to catch injected defects, and every report is regenerated from raw trial data.
14. **Claims are limited to what the evidence supports.** A small sample supports a small claim. A claim that cannot be proven is changed, not stretched.

## Practice

15. **Read the contract before building.** Before the first build against an external service, its documented limits, auth model, and packaging rules are read and recorded.
16. **Structure beats care.** If a rule matters, a test, hook, or gate enforces it. Controls are calibrated so they stay quiet on normal input.
17. **Guardrails for cloud work.** All data is synthetic. A budget alert exists before the first deploy. Every deploy needs explicit approval. A teardown script removes everything that was deployed, and the teardown is verified.
