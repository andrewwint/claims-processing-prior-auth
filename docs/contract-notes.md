# AgentCore contract notes

These notes record the documented constraints this design builds on. They were read before any build, on 2026-10-16, from the AWS developer guide, the CloudFormation reference, and the botocore 1.43.114 service models for `bedrock-agentcore-control` and `bedrock-agentcore`.

If a newer document disagrees with these notes, the newer document wins. Update these notes when that happens.

## Gateway

- **Creation.** Gateways are created with `CreateGateway` (asynchronous). Status values are `CREATING`, `READY`, `FAILED`, and others. Inbound authorizer types are `CUSTOM_JWT`, `AWS_IAM`, `AUTHENTICATE_ONLY`, and `NONE`.
- **Targets.** A target exposes exactly the tools in its schema. An inline Lambda `toolSchema` is the most explicit option.
- **Tool names.** Tools are named `<target>___<tool>`, with three underscores. (Docs: gateway tool naming.)
- **Lambda target invocation.** The event is the map of tool arguments from the `inputSchema`. The tool name arrives in `context.client_context.custom["bedrockAgentCoreToolName"]` as `<target>___<tool>`, and the handler strips the prefix itself. Gateway, target and message IDs are in the same map. The function must return valid JSON. The docs' prose renders the delimiter as one underscore, but their code uses three, so the deployed `tools/list` is the authority. (Docs: Lambda function targets, read 2026-10-16.)
- **Request interceptors.** At most one REQUEST and one RESPONSE interceptor per gateway, Lambda only. The REQUEST interceptor receives the parsed MCP request (`mcp.gatewayRequest.body`, including `tools/call` arguments), plus the headers and bearer token only when `passRequestHeaders` is true (default false). It returns `transformedGatewayRequest.body` to rewrite the request, or `transformedGatewayResponse` to answer immediately without calling the target. The gateway may retry an interceptor, so it must be idempotent. The docs do not state whether the inbound JWT is validated before the interceptor runs, or whether Policy sees the original or the transformed arguments, so the interceptor validates the token itself. Whether a transformed body reaches a Lambda target is confirmed live. (Docs: interceptors, types, configuration, read 2026-10-16.)
- **Outbound credentials.** Each target takes exactly one credential provider. Lambda targets support only the gateway IAM role. Per-target API key or OAuth providers need OpenAPI or MCP targets. (Docs: gateway outbound auth.)
- **Evidence of the exposed tools.** `ListGatewayTargets` and `GetGatewayTarget` show the full registered tool set. With a policy engine attached, `tools/list` is filtered by policy, so it is not proof on its own.

## Policy (Cedar)

- **Availability.** Generally available, and supported in us-east-1.
- **Structure.** A policy engine holds the policies, and the gateway enforces them on every `tools/call`. Each gateway has at most one engine; one engine can serve many gateways.
- **Decision rules.** Calls are denied by default, and an explicit `forbid` always wins.
- **Enforcement mode.** Attaching an engine in `LOG_ONLY` mode enforces nothing. The mode must be set to `ENFORCE` explicitly, and evidence is captured with `GetGateway` at the time of the test.
- **Request shape:**
  - principal: `AgentCore::OAuthUser::"<sub>"`, with JWT claims as tags, or `AgentCore::IamEntity`
  - action: `AgentCore::Action::"<target>___<tool>"`
  - resource: `AgentCore::Gateway::"<gateway ARN>"`
  - context: only `context.input`, the tool arguments, typed from the tool's input schema
- **Policies can only name registered actions.** A policy naming an action that no attached gateway has registered fails validation. A policy that names an action must also name a specific gateway ARN.
- **Policy checks the shape of a call, not its truth.** `context.input` is whatever the caller sends.
- **What a denied call returns** (observed live, 2026-10-16): a JSON-RPC **error** with code `-32002` and "Tool Execution Denied: Tool call not allowed due to policy enforcement [No policy applies to the request (denied by default).]". `tools/list` is filtered by policy: with no permits, it returns an empty list. A token rejected by the inbound authorizer gets HTTP 401 (missing) or 403 (`insufficient_scope`) before policy runs.
- **Where decisions are recorded.** `DenyDecisions` and `AllowDecisions` metrics in `AWS/Bedrock-AgentCore`, plus spans carrying the decision, the determining policy IDs, and the effects (requires Transaction Search and gateway tracing).
- **Principal tags.** JWT claims become tags on `AgentCore::OAuthUser`, read with `principal.hasTag("x")`, `principal.getTag("x") == "v"` and `like "*v*"`. The principal ID is the token's `sub`. Observed live (2026-10-16): **an array claim such as `cognito:groups` becomes a String tag, not a Set.** Policy validation rejects `getTag("cognito:groups").contains(...)` with "expected Set… but saw String". How the list is encoded inside that string is not documented. For a client-credentials token, `sub` equals `client_id`. (Docs: policy conditions, read 2026-10-16.)
- **Per-policy enforcement.** Each policy has its own `enforcementMode` (`ACTIVE` or `LOG_ONLY`), separate from the gateway's engine mode. Both must be enforcing.
- **Names.** Policy engine and policy names match `[A-Za-z][A-Za-z0-9_]*`, at most 48 characters. Gateway names are letters, digits and single hyphens.
- **Validation.** The default validation mode rejects policies with automated-reasoning findings, such as "overly restrictive" or "overly permissive".
- **Deploy order.** Two passes: the gateway and its targets must be `READY` before the policies that reference them.

## Runtime

- **Deployment artifacts.** CodeZip (S3, ARM64 wheels) or an ARM64 container. Limits:
  - code: 250 MB compressed
  - container image: 2 GB
  - synchronous request: 15 min
  - idle session timeout: 15 min by default
  - maximum session lifetime: 8 h
- **Protocol.** HTTP: `POST /invocations` and `GET /ping` on port 8080. Each request carries a session ID, which gives one isolated session per case.
- **Inbound authentication.** SigV4 or a JWT authorizer, never both. JWT runtimes are invoked over HTTPS with a bearer token.
- **Network mode.** `PUBLIC` or `VPC`. VPC mode requires subnets in specific us-east-1 Availability Zone IDs, and its network interfaces can remain for hours after deletion.
- **Metadata service v2.** Runtimes must require IMDS/MMDS v2 or invocations fail. The setting is applied with `UpdateAgentRuntime` after creation; it is not available on create or in CloudFormation.
- **Logs.** Container output goes to a per-runtime log group that is created on the first invocation. The opt-in `APPLICATION_LOGS` delivery includes the request payload.

## Observability

- **Default content capture.** With the AWS Distro for OpenTelemetry (ADOT), Strands agent spans include prompts, completions, and tool inputs and outputs by default.
- **Redaction.** Strands 1.47 and later can redact `gen_ai.input.messages`, `gen_ai.output.messages`, and `gen_ai.system_instructions` with `OTEL_SEMCONV_STABILITY_OPT_IN="gen_ai_unredacted_attributes="`.
- **Custom attributes.** Can be added with `Agent(trace_attributes=…)` or on spans you create yourself.

## Identity

- **Workload identities.** Runtime creates a workload identity automatically.
- **Token exchange.** `GetWorkloadAccessTokenForJWT` exchanges an inbound user token. Credential providers (API key, OAuth2) are stored in the token vault.
- **No native per-tenant dimension.** Per-tenant credentials need either per-user OAuth flows or one target per tenant, each with its own provider, gated by a policy on the caller's identity.

## Memory

- **Opt-in.** Memory is a separate resource. A runtime has no memory configuration unless the agent code creates and calls one.
