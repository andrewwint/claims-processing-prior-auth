# Teardown checks, 2026-10-25

`scripts/teardown.py --yes` exited 0 and the verifier reported `VERIFY: PASS` ([teardown.txt](teardown.txt), redacted; CDK deprecation warnings removed). The runbook's manual checks, read afterwards:

| Check | Result |
|---|---|
| Project stacks | Only `PriorAuthBudgets` remains |
| Agent runtime, both gateways | None remain |
| Workload identities (three before: two gateways, one runtime) | None remain |
| OAuth2 credential provider | None remains |
| Identity vault secret | Gone, including from planned deletion |
| Project secrets (agent client, four test users) | Gone, including from planned deletion |
| Project log groups | None remain; other projects' runtime log groups were not touched |
| Evidence bucket | `HeadBucket` returns 404 (172 object versions deleted first) |
| KMS key | `PendingDeletion`, deletion date 2026-11-01 |
| Budgets | Both remain |
| Transaction Search | Matches the value recorded before the first deploy (CloudWatch Logs, 100% indexing) |
