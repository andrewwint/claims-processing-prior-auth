"""AgentCore Runtime entry point: one case per invocation.

The gateway token comes from AgentCore Identity (M2M, client credentials) using
the workload access token Runtime supplies; the runtime holds no secret. The
model gathers through three tools; decide() acts. Telemetry content settings
come from the runtime's environment (prior_auth.agent.telemetry).
"""

import os

import boto3
from bedrock_agentcore.identity.auth import requires_access_token
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands.tools.mcp import MCPClient

from prior_auth.agent.pipeline import run_case
from prior_auth.agent.strands_agent import make_call, make_extract
from prior_auth.evidence_store import put_packet

app = BedrockAgentCoreApp()
REGION = os.environ.get("AWS_REGION", "us-east-1")


@requires_access_token(provider_name=os.environ.get("IDENTITY_PROVIDER_NAME", "prior-auth-agent-m2m"),
                       scopes=["prior-auth/tools"], auth_flow="M2M")
def _gateway_token(*, access_token: str) -> str:
    return access_token


def _public(outcome: dict) -> dict:
    """What the caller gets back: identifiers and the decision, never chart text."""
    keep = ("outcome", "reason", "gaps", "case_id", "disagreement")
    result = {k: outcome[k] for k in keep if k in outcome}
    if "packet" in outcome:
        result["packet_id"] = outcome["packet"]["packet_id"]
    return result


@app.entrypoint
def invoke(payload: dict) -> dict:
    case_id = payload.get("case_id")
    if not isinstance(case_id, str):
        return {"outcome": "rejected", "reason": "case_id is required"}
    s3 = boto3.client("s3", region_name=REGION)
    cloudwatch = boto3.client("cloudwatch", region_name=REGION)
    bucket = os.environ["EVIDENCE_BUCKET"]
    client = MCPClient(url=os.environ["AGENT_GATEWAY_URL"],
                       headers={"Authorization": f"Bearer {_gateway_token()}"})
    with client:
        outcome = run_case(case_id, make_call(client), make_extract(client, os.environ["MODEL_ID"], REGION),
                           lambda packet: put_packet(s3, bucket, packet),
                           cloudwatch=cloudwatch, model_id=os.environ["MODEL_ID"])
    return _public(outcome)


if __name__ == "__main__":
    app.run()
