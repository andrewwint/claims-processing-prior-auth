# Empty-output and failure rules, per step

Each step has its own rule for empty output or failure. No step falls back to a shared default. A failure may slow a case down; it may never push a case toward denial. Every row has a test (case-packet-and-failure-routing, task 4.2). This page is copied from that change's design D6, which is the source of truth.

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
