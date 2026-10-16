# Design

## Decisions

### Write-once storage: Object Lock in governance mode

- **Configuration.** S3 Object Lock in governance mode, with a short default retention, so the stack can be torn down the same day.
- **Who can do what.** The agent and tool roles have `s3:PutObject` with `s3:if-none-match` conditions, and no `s3:BypassGovernanceRetention`, `DeleteObject` or `PutObjectRetention`.
- **Why not compliance mode.** It would block teardown until retention expires.
- **How it's proven.** A recorded overwrite or delete attempt by the agent role (L4).
- **Production note.** A production deployment would use compliance mode with the retention its records policy requires. The docs say this; the demo does not claim it.

### Per-tenant keys

- **Keys.** One customer-managed KMS key per synthetic tenant (`tenant-a`, `tenant-b`). Records are written with `SSEKMSKeyId` set to the tenant's key.
- **Access.** Key policies allow encrypt only for the writer roles, and decrypt only for the reviewer roles of that tenant.
- **Teardown.** Keys are scheduled for deletion with the 7-day minimum, and the verifier accepts `PendingDeletion`.

### Hashes

- **What is hashed.** SHA-256 over canonical JSON (sorted keys, no whitespace) of the record.
- **Content hashes.** Each content item (chart document, packet) also gets a hash attribute.
- **Linking.** The record ID and the record hash go on the final span.

### Telemetry

- **Redaction.** Strands telemetry redaction is set, so content attributes become `[REDACTED]`.
- **Custom attributes.** Added with `Agent(trace_attributes=…)`, and only non-content values.
- **Request payloads.** `APPLICATION_LOGS` delivery stays off, because it includes request payloads.
- **Canary scan.** `scripts/canary_scan.py` queries the runtime log groups, span records and gateway vended logs for every canary through CloudWatch Logs Insights, and writes a report.

### Memory

No Memory resource. The runtime and tool roles include an explicit `Deny` on `bedrock-agentcore:CreateMemory`, `CreateEvent` and `RetrieveMemoryRecords`. Evidence is the `list-memories` output, a code search, and the role policies.

## Risks / Trade-offs

- [Redaction misses error text or another event path] → The canary scan finds it. The fix is to stop emitting that path, not to scrub after the fact.
- [Governance mode is weaker than compliance mode] → Stated in the README and the article's evidence notes.
