"""Minimal client for the deployed gateways: tokens and raw MCP calls.

Credentials come only from environment variables that `asm-exec` fills from
Secrets Manager references at run time, so secret values never pass through
the operator's tooling or logs:

    asm-exec -- env AGENT_CLIENT_SECRET='{{resolve:secretsmanager:prior-auth/agent-client:SecretString:client_secret}}' \
        SYN_CLINICIAN_1_PASSWORD='{{resolve:secretsmanager:prior-auth/users/syn-clinician-1:SecretString:password}}' \
        .venv/bin/python -m scripts.record_d1 smoke

Tokens are never printed or written to disk. Responses are returned raw so
evidence scripts can redact them before saving.
"""

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import boto3

OUTPUTS = Path(".local/d1-outputs.json")


def outputs(path: Path = OUTPUTS) -> dict:
    return json.loads(path.read_text())["PriorAuthGateways"]


def password_env(username: str) -> str:
    return username.upper().replace("-", "_") + "_PASSWORD"


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not set; run this through asm-exec with a Secrets Manager reference")
    return value


def agent_token(out: dict) -> str:
    secret = _required_env("AGENT_CLIENT_SECRET")
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

    srp = AWSSRP(username=username, password=_required_env(password_env(username)), pool_id=out["UserPoolId"],
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
