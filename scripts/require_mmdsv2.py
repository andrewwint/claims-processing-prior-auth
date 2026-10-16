"""Post-deploy (every runtime deploy): require metadata service v2 on the runtime.

UpdateAgentRuntime replaces the configuration, so every field is copied from the
current runtime and only metadataConfiguration changes. Not settable in CloudFormation.

Usage: python -m scripts.require_mmdsv2 <agent-runtime-id>
"""

import sys

import boto3

COPY = ("agentRuntimeArtifact", "roleArn", "networkConfiguration", "description", "authorizerConfiguration",
        "requestHeaderConfiguration", "protocolConfiguration", "lifecycleConfiguration", "environmentVariables")


def update_request(current: dict) -> dict:
    req = {k: current[k] for k in COPY if current.get(k) is not None}
    req["agentRuntimeId"] = current["agentRuntimeId"]
    req["metadataConfiguration"] = {"requireMMDSV2": True}
    return req


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    control = boto3.Session(region_name="us-east-1").client("bedrock-agentcore-control")
    current = control.get_agent_runtime(agentRuntimeId=sys.argv[1])
    if current.get("metadataConfiguration", {}).get("requireMMDSV2"):
        print("already requires MMDSv2")
        return 0
    control.update_agent_runtime(**update_request(current))
    print("requireMMDSV2 set")
    return 0


if __name__ == "__main__":
    sys.exit(main())
