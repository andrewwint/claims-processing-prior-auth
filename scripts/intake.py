"""Submit one synthetic case to the runtime as the intake client (beats 2 and 3).

The intake client's secret is read from Cognito in memory (no Secrets Manager
reads). The session ID is derived from the case (33+ characters).

Usage: python -m scripts.intake <case_id> <runtime-arn>
"""

import base64
import json
import sys
import urllib.parse
import urllib.request

import boto3

from prior_auth.agent.pipeline import session_id_for
from scripts import gateway_client as gc


def intake_token(out: dict, session) -> str:
    secret = session.client("cognito-idp").describe_user_pool_client(
        UserPoolId=out["UserPoolId"], ClientId=out["IntakeClientId"])["UserPoolClient"]["ClientSecret"]
    basic = base64.b64encode(f"{out['IntakeClientId']}:{secret}".encode()).decode()
    req = urllib.request.Request(f"{out['TokenDomain']}/oauth2/token", method="POST",
                                 data=b"grant_type=client_credentials&scope=prior-auth%2Finvoke",
                                 headers={"Authorization": f"Basic {basic}",
                                          "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())["access_token"]


def invoke(case_id: str, runtime_arn: str, token: str) -> dict:
    url = (f"https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/"
           f"{urllib.parse.quote(runtime_arn, safe='')}/invocations?qualifier=DEFAULT")
    req = urllib.request.Request(url, method="POST", data=json.dumps({"case_id": case_id}).encode(),
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                                          "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id_for(case_id)})
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read())


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    session = boto3.Session(region_name="us-east-1")
    out = gc.outputs()
    print(json.dumps(invoke(sys.argv[1], sys.argv[2], intake_token(out, session))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
