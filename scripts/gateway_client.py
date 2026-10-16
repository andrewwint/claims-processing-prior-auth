"""Minimal client for the deployed gateways: tokens and raw MCP calls.

No Secrets Manager reads (Andrew's decision, 2026-10-16). Credentials are
obtained in this process only:
- the agent client secret is read from Cognito (DescribeUserPoolClient), as
  store_agent_secret already does;
- a synthetic user's password is replaced with a fresh random one, written to
  Secrets Manager write-only, and used for SRP sign-in.
If AGENT_CLIENT_SECRET or <USER>_PASSWORD is set (for example by asm-exec),
that value is used instead. Secrets and tokens are never printed or written
to disk. Responses are returned raw so evidence scripts can redact them.
"""

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import boto3

from infra.names import PROJECT_TAG, SECRET_PREFIX
from scripts.create_users import generate_password

OUTPUTS = Path(".local/d1-outputs.json")


def outputs(path: Path = OUTPUTS) -> dict:
    return json.loads(path.read_text())["PriorAuthGateways"]


def password_env(username: str) -> str:
    return username.upper().replace("-", "_") + "_PASSWORD"


def _agent_secret(out: dict, session: boto3.Session) -> str:
    if os.environ.get("AGENT_CLIENT_SECRET"):
        return os.environ["AGENT_CLIENT_SECRET"]
    client = session.client("cognito-idp").describe_user_pool_client(
        UserPoolId=out["UserPoolId"], ClientId=out["AgentClientId"])["UserPoolClient"]
    return client["ClientSecret"]


def _fresh_password(out: dict, session: boto3.Session, username: str) -> str:
    """Rotate the synthetic user's password in memory; Secrets Manager is written, never read."""
    password = generate_password()
    session.client("cognito-idp").admin_set_user_password(
        UserPoolId=out["UserPoolId"], Username=username, Password=password, Permanent=True)
    sm = session.client("secretsmanager")
    value = json.dumps({"username": username, "password": password})
    name = f"{SECRET_PREFIX}users/{username}"
    try:
        sm.put_secret_value(SecretId=name, SecretString=value)
    except sm.exceptions.ResourceNotFoundException:
        sm.create_secret(Name=name, SecretString=value, Tags=[{"Key": PROJECT_TAG[0], "Value": PROJECT_TAG[1]}])
    return password


def agent_token(out: dict, session: boto3.Session | None = None) -> str:
    secret = _agent_secret(out, session or boto3.Session(region_name="us-east-1"))
    body = "grant_type=client_credentials&scope=prior-auth%2Ftools".encode()
    basic = base64.b64encode(f"{out['AgentClientId']}:{secret}".encode()).decode()
    req = urllib.request.Request(f"{out['TokenDomain']}/oauth2/token", data=body, method="POST",
                                 headers={"Authorization": f"Basic {basic}",
                                          "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())["access_token"]


def user_token(out: dict, session: boto3.Session, username: str) -> str:
    """SRP sign-in for a synthetic user; the password stays in this process only."""
    from pycognito.aws_srp import AWSSRP

    password = os.environ.get(password_env(username)) or _fresh_password(out, session, username)
    srp = AWSSRP(username=username, password=password, pool_id=out["UserPoolId"],
                 client_id=out["ClinicianClientId"], client=session.client("cognito-idp"))
    return srp.authenticate_user()["AuthenticationResult"]["AccessToken"]


def claims(token: str) -> dict:
    """Decode a JWT payload for recording only (no trust is placed in it here)."""
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def mcp(url: str, token: str | None, method: str, params: dict | None = None, rpc_id: int = 1) -> dict:
    body = {"jsonrpc": "2.0", "id": rpc_id, "method": method}
    if params is not None:
        body["params"] = params
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return {"http_status": resp.status, "body": _parse(resp.read().decode())}
    except urllib.error.HTTPError as e:
        return {"http_status": e.code, "body": _parse(e.read().decode())}


def _parse(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Streamable HTTP may answer as server-sent events.
        data = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
        return json.loads(data[-1]) if data else text
