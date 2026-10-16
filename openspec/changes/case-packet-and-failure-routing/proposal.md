# Proposal

## Why

The article's demo needs two moments. A Strands agent builds a cited case and code approves it. Then the same case with one note removed is routed to a clinician with the gap marked. This change delivers **beats 2 and 3** of the five-minute demo and nothing more (PM scope cut, 2026-10-16).

## What Changes

- **Synthetic data, generated here.** One fictional payer (Larkspur Health Plan), one procedure, and about 6 patients in one tenant. Documents are line-addressable, and every chart carries canaries.
- **The Strands agent** on AgentCore Runtime uses Nova Pro.
  - It connects to the agent gateway over MCP and is given exactly three gathering tools: `check_eligibility`, `fetch_policy_criteria` and `extract_clinical_evidence`.
  - Every call goes through Cedar as the agent identity.
  - Redaction is on from the first invocation.
- **`decide(packet)`** runs as code after the agent finishes, using the shared four checks. It is the only caller of `record_approval` and `route_to_reviewer`.
- **The approval service** rebuilds the verdict from trusted stores. The existing tests carry over.
- **Routing** writes a queue entry and the recommendation record with the gaps marked.
- **No Knowledge Base.** Policy lookup is an exact match on (payer, CPT).

## Claims delivered

B7, G1–G3, G4–G7, G9–G11, F1–F7, A1.

**Deferred (README "Known limitations"):**
- an SNS topic. F4 is the deployed alarm on the operator metric.
- the mutation run (`post-monday-hardening`)
- the evidence-rule redesign, E1–E3 (`post-monday-hardening`)
- the second payer and further procedures

## Capabilities

### New Capabilities

- `case-packet`: criteria, cited findings, the four checks and the decision.
- `failure-routing`: where every failure goes, and exactly one outcome per session.
- `agent-runtime`: the Strands agent on Runtime, invoked by the intake client.

### Modified Capabilities

None.

## Impact

- **New code:** `data/policies/`, `data/cases/`, `src/prior_auth/agent/`, the real tools, `infra/runtime_stack.py`, `scripts/intake.py`, and tests.
- **AWS resources:** an AgentCore Runtime and the intake app client. Trusted stores are bundled into the packages; packets go to the evidence bucket. All of them are removed by teardown.
- **Depends on** `gateway-and-policy`.
