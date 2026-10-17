# Teardown runbook

The verified teardown runs once, after the demo period, with Andrew's go-ahead. `scripts/teardown.py` does the work; this page is what to do around it. The notes come from the AWS skills review (`docs/reviews/2026-10-17-aws-skills.md`, b12–b15). The teardown code is not changed before then.

## Before you start

1. **Activate the project's virtual environment, and work from the repository root.**
   ```
   source .venv/bin/activate
   ```
   The CDK app runs `python3 -m infra.app`. A shell without the virtual environment finds a Python without `aws_cdk`, and the teardown stops at its first step, with nothing deleted.
2. **Keep `cdk.context.json` and `build/runtime` until the teardown is verified.** The runtime and policy stacks exist in the CDK app only while both are present. Without them, `cdk destroy` cannot find those stacks.
3. **Set `AWS_PROFILE`** to the account's administrator profile in this shell. No file names it.
4. **Record what exists now (read-only)**, so the end state can be compared:
   ```
   aws bedrock-agentcore-control list-agent-runtimes
   aws bedrock-agentcore-control list-workload-identities          # expect three for the project: two gateways, one runtime
   aws bedrock-agentcore-control list-oauth2-credential-providers  # expect the project's one provider
   aws secretsmanager list-secrets --filters Key=name,Values=bedrock-agentcore-identity   # expect the provider's one vault secret
   aws logs describe-log-groups --log-group-name-prefix /aws/bedrock-agentcore/runtimes/
   aws logs describe-resource-policies
   ```

## Run

```
set -o pipefail
python -m scripts.teardown --yes | tee evidence/<date>/teardown.txt
```

`pipefail` keeps the teardown's exit status, which the `tee` would otherwise hide. The steps, in order:
1. Destroy the runtime, policy and gateway stacks.
2. Empty the evidence bucket as the teardown role (by version, with the governance bypass), then delete the bucket.
3. Destroy the evidence stack. Its KMS key enters its 7-day deletion window.
4. Delete the Identity provider, the runtime log group, the Lambda log groups and the project's secrets, each by exact name.
5. Restore Transaction Search to the recorded values.
6. Run the verifier.

## If a step fails

**Do not rerun the whole teardown.** After step 3 the teardown role no longer exists, so a rerun stops at step 2. Instead:
- **Step 1, 2 or 3 fails:** read the error. It is safe to fix the cause and rerun, because the role still exists. If the evidence stack ends `DELETE_FAILED` on its bucket-policy resource (the bucket is already gone), destroy it again.
- **Step 4, 5 or 6 fails:** finish the remaining steps by hand, then run `python -m scripts.verify_teardown`.

## After the run: checklist

- [ ] `verify_teardown` reports `VERIFY: PASS`, and its output is saved in the evidence directory.
- [ ] **Workload identities:** the three the project had are gone. They were created by AgentCore for the runtime and the gateways, and no teardown step deletes them directly. If any remain, delete each by exact name (`aws bedrock-agentcore-control delete-workload-identity --name <name>`) and rerun the verifier.
- [ ] **The Identity vault secret is gone.** Deleting the OAuth2 credential provider is expected to remove it. The verifier does not check this secret, so check by hand with the `list-secrets` call above.
- [ ] The evidence bucket no longer exists; the KMS key shows `PendingDeletion`.
- [ ] The budgets remain (the verifier checks).
- [ ] Transaction Search matches the recorded values (the verifier checks).
- [ ] Only then: delete the archived original repository, and remove the deployment IDs from `cdk.context.json` (keep the Cognito domain prefix) so a later redeploy does not bind to deleted resources.
