"""Telemetry settings the runtime must carry (case-packet task 0.2, evidence/2026-10-16/telemetry-check.json).

Both are required. Measured with chart canaries, spans and log records captured:
- Strands puts prompts, tool results and completions in span events unless redacted.
- ADOT sets OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true by default (setdefault)
  when AGENT_OBSERVABILITY_ENABLED is on, and botocore's Bedrock extension then emits
  gen_ai.user.message, gen_ai.tool.message and gen_ai.choice log records with content.
Either setting alone still leaks; together, zero canaries in spans and logs.
"""

RUNTIME_TELEMETRY_ENV = {
    "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai_unredacted_attributes=",
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "false",
}
