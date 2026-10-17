# Harness report

**Synthetic, author-labeled cases; not clinical ground truth.**

Six synthetic cases, three trials each per model, run end to end on the deployed system (runtime, gateways, approval service). Definitions, prices and wording: [PREREGISTRATION.md](PREREGISTRATION.md). No ranking claims are made at this N.

**`amazon.nova-pro-v1:0`.** False auto-approvals: 0 of 12 trials on needs-review cases, with a 95% upper bound of 25.0% (rule of three). Auto-approvals: 5 of 6 trials on approvable cases, and 5 of 18 (27.8%) overall; the overall figure reflects the test mix, in which 2 of 6 cases are approvable.

**`us.anthropic.claude-sonnet-4-6`.** False auto-approvals: 0 of 12 trials on needs-review cases, with a 95% upper bound of 25.0% (rule of three). Auto-approvals: 6 of 6 trials on approvable cases, and 6 of 18 (33.3%) overall; the overall figure reflects the test mix, in which 2 of 6 cases are approvable.

| Model | False auto-approvals | Auto-approval rate | Auto-approvals on approve-labeled cases | Disagreements | Truncated | Latency p50 / p95 | Cost per trial |
|---|---|---|---|---|---|---|---|
| `amazon.nova-pro-v1:0` | 0 of 12 (95% upper bound 25.0%) | 5 of 18 (27.8%) | 5 of 6 | 0 | 0 | 13.0 s / 16.1 s | $0.0042 |
| `us.anthropic.claude-sonnet-4-6` | 0 of 12 (95% upper bound 25.0%) | 6 of 18 (33.3%) | 6 of 6 | 0 | 0 | 14.3 s / 18.0 s | $0.0207 |

## Approvable trials that were routed

Not re-run. The cause is reconstructed from each run's stored recommendation record: its citations are re-checked against the trusted chart ([annotate.py](annotate.py)).

- `amazon.nova-pro-v1:0` SYN-CASE-CLEAN-2 trial 1: C1 cited SYN-DOC-102-PT page 3 line 3 (no such line: the document has 1 page); C2 cited SYN-DOC-102-MRI page 3 line 3 (no such line: the document has 1 page); C3 cited SYN-DOC-102-FUNC page 3 line 3 (no such line: the document has 1 page). Checks: source match: value for C1 is shorter than 4 characters; source match: value for C2 is shorter than 4 characters; source match: value for C3 is shorter than 4 characters. Routed to a clinician; nothing was approved.

Operator-alert trials excluded from the rates: 0.
Total model cost of the run: $0.4489.

## Every trial

| # | Model | Case | Label | Trial | Outcome | Reason | Gaps | Stop reason | Sampling sent | Tokens in / out | Seconds |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `amazon.nova-pro-v1:0` | SYN-CASE-CF-1 | needs review | 1 | routed | criteria not met | C3 | tool_use | {"maxTokens": 2048, "temperature": 0} | 2639 / 573 | 14.6 |
| 2 | `amazon.nova-pro-v1:0` | SYN-CASE-CF-2 | needs review | 1 | routed | criteria not met | C2 | tool_use | {"maxTokens": 2048, "temperature": 0} | 2633 / 464 | 13.8 |
| 3 | `amazon.nova-pro-v1:0` | SYN-CASE-CLEAN-1 | approve | 1 | approved |  |  | tool_use | {"maxTokens": 2048, "temperature": 0} | 2740 / 524 | 16.1 |
| 4 | `amazon.nova-pro-v1:0` | SYN-CASE-CLEAN-2 | approve | 1 | routed | checks failed | C1, C2, C3 | tool_use | {"maxTokens": 2048, "temperature": 0} | 4251 / 487 | 15.2 |
| 5 | `amazon.nova-pro-v1:0` | SYN-CASE-FORGED | needs review | 1 | routed | checks failed | C1, C2, C3 | tool_use | {"maxTokens": 2048, "temperature": 0} | 4262 / 495 | 12.2 |
| 6 | `amazon.nova-pro-v1:0` | SYN-CASE-WRONG-PATIENT | needs review | 1 | routed | checks failed | C3 | tool_use | {"maxTokens": 2048, "temperature": 0} | 2744 / 564 | 14.1 |
| 7 | `amazon.nova-pro-v1:0` | SYN-CASE-CF-1 | needs review | 2 | routed | criteria not met | C3 | tool_use | {"maxTokens": 2048, "temperature": 0} | 2639 / 554 | 12.6 |
| 8 | `amazon.nova-pro-v1:0` | SYN-CASE-CF-2 | needs review | 2 | routed | criteria not met | C2 | tool_use | {"maxTokens": 2048, "temperature": 0} | 4142 / 449 | 12.2 |
| 9 | `amazon.nova-pro-v1:0` | SYN-CASE-CLEAN-1 | approve | 2 | approved |  |  | tool_use | {"maxTokens": 2048, "temperature": 0} | 2740 / 474 | 12.7 |
| 10 | `amazon.nova-pro-v1:0` | SYN-CASE-CLEAN-2 | approve | 2 | approved |  |  | tool_use | {"maxTokens": 2048, "temperature": 0} | 4250 / 490 | 14.7 |
| 11 | `amazon.nova-pro-v1:0` | SYN-CASE-FORGED | needs review | 2 | routed | checks failed | C1, C2, C3 | tool_use | {"maxTokens": 2048, "temperature": 0} | 4262 / 495 | 14.5 |
| 12 | `amazon.nova-pro-v1:0` | SYN-CASE-WRONG-PATIENT | needs review | 2 | routed | checks failed | C3 | tool_use | {"maxTokens": 2048, "temperature": 0} | 2744 / 479 | 13.5 |
| 13 | `amazon.nova-pro-v1:0` | SYN-CASE-CF-1 | needs review | 3 | routed | criteria not met | C3 | tool_use | {"maxTokens": 2048, "temperature": 0} | 2639 / 554 | 11.8 |
| 14 | `amazon.nova-pro-v1:0` | SYN-CASE-CF-2 | needs review | 3 | routed | criteria not met | C2 | tool_use | {"maxTokens": 2048, "temperature": 0} | 4120 / 428 | 11.7 |
| 15 | `amazon.nova-pro-v1:0` | SYN-CASE-CLEAN-1 | approve | 3 | approved |  |  | tool_use | {"maxTokens": 2048, "temperature": 0} | 2740 / 474 | 13.5 |
| 16 | `amazon.nova-pro-v1:0` | SYN-CASE-CLEAN-2 | approve | 3 | approved |  |  | tool_use | {"maxTokens": 2048, "temperature": 0} | 2761 / 511 | 12.8 |
| 17 | `amazon.nova-pro-v1:0` | SYN-CASE-FORGED | needs review | 3 | routed | checks failed | C1, C2, C3 | tool_use | {"maxTokens": 2048, "temperature": 0} | 4262 / 495 | 12.4 |
| 18 | `amazon.nova-pro-v1:0` | SYN-CASE-WRONG-PATIENT | needs review | 3 | routed | checks failed | C3 | tool_use | {"maxTokens": 2048, "temperature": 0} | 2744 / 479 | 13.0 |
| 19 | `us.anthropic.claude-sonnet-4-6` | SYN-CASE-CF-1 | needs review | 1 | routed | criteria not met | C3 | tool_use | {"maxTokens": 2048, "temperature": 0} | 3213 / 604 | 16.1 |
| 20 | `us.anthropic.claude-sonnet-4-6` | SYN-CASE-CF-2 | needs review | 1 | routed | criteria not met | C2 | tool_use | {"maxTokens": 2048, "temperature": 0} | 3208 / 544 | 14.0 |
| 21 | `us.anthropic.claude-sonnet-4-6` | SYN-CASE-CLEAN-1 | approve | 1 | approved |  |  | tool_use | {"maxTokens": 2048, "temperature": 0} | 3325 / 597 | 18.0 |
| 22 | `us.anthropic.claude-sonnet-4-6` | SYN-CASE-CLEAN-2 | approve | 1 | approved |  |  | tool_use | {"maxTokens": 2048, "temperature": 0} | 3320 / 593 | 14.8 |
| 23 | `us.anthropic.claude-sonnet-4-6` | SYN-CASE-FORGED | needs review | 1 | routed | checks failed | C3 | tool_use | {"maxTokens": 2048, "temperature": 0} | 3324 / 594 | 13.0 |
| 24 | `us.anthropic.claude-sonnet-4-6` | SYN-CASE-WRONG-PATIENT | needs review | 1 | routed | checks failed | C3 | tool_use | {"maxTokens": 2048, "temperature": 0} | 3324 / 661 | 14.9 |
| 25 | `us.anthropic.claude-sonnet-4-6` | SYN-CASE-CF-1 | needs review | 2 | routed | criteria not met | C3 | tool_use | {"maxTokens": 2048, "temperature": 0} | 3213 / 644 | 14.5 |
| 26 | `us.anthropic.claude-sonnet-4-6` | SYN-CASE-CF-2 | needs review | 2 | routed | criteria not met | C2 | tool_use | {"maxTokens": 2048, "temperature": 0} | 3208 / 544 | 12.2 |
| 27 | `us.anthropic.claude-sonnet-4-6` | SYN-CASE-CLEAN-1 | approve | 2 | approved |  |  | tool_use | {"maxTokens": 2048, "temperature": 0} | 3325 / 588 | 12.7 |
| 28 | `us.anthropic.claude-sonnet-4-6` | SYN-CASE-CLEAN-2 | approve | 2 | approved |  |  | tool_use | {"maxTokens": 2048, "temperature": 0} | 3320 / 578 | 15.2 |
| 29 | `us.anthropic.claude-sonnet-4-6` | SYN-CASE-FORGED | needs review | 2 | routed | checks failed | C3 | tool_use | {"maxTokens": 2048, "temperature": 0} | 3324 / 581 | 12.4 |
| 30 | `us.anthropic.claude-sonnet-4-6` | SYN-CASE-WRONG-PATIENT | needs review | 2 | routed | checks failed | C3 | tool_use | {"maxTokens": 2048, "temperature": 0} | 3324 / 656 | 13.6 |
| 31 | `us.anthropic.claude-sonnet-4-6` | SYN-CASE-CF-1 | needs review | 3 | routed | criteria not met | C3 | tool_use | {"maxTokens": 2048, "temperature": 0} | 3213 / 643 | 14.8 |
| 32 | `us.anthropic.claude-sonnet-4-6` | SYN-CASE-CF-2 | needs review | 3 | routed | criteria not met | C2 | tool_use | {"maxTokens": 2048, "temperature": 0} | 3208 / 564 | 12.7 |
| 33 | `us.anthropic.claude-sonnet-4-6` | SYN-CASE-CLEAN-1 | approve | 3 | approved |  |  | tool_use | {"maxTokens": 2048, "temperature": 0} | 3325 / 591 | 14.6 |
| 34 | `us.anthropic.claude-sonnet-4-6` | SYN-CASE-CLEAN-2 | approve | 3 | approved |  |  | tool_use | {"maxTokens": 2048, "temperature": 0} | 3320 / 578 | 16.5 |
| 35 | `us.anthropic.claude-sonnet-4-6` | SYN-CASE-FORGED | needs review | 3 | routed | checks failed | C3 | tool_use | {"maxTokens": 2048, "temperature": 0} | 3324 / 595 | 14.3 |
| 36 | `us.anthropic.claude-sonnet-4-6` | SYN-CASE-WRONG-PATIENT | needs review | 3 | routed | checks failed | C3 | tool_use | {"maxTokens": 2048, "temperature": 0} | 3324 / 601 | 12.3 |
