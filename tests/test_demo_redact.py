"""V1: demo.py --redact leaves no identifier on screen."""

import io
import sys

from scripts import demo
from scripts.redact import find_unredacted

OUT = {"AgentClientId": "a" * 25 + "1", "ClinicianClientId": "b" * 25 + "2", "IntakeClientId": "c" * 25 + "3",
       "UserPoolId": "us-east-1_AbCdEfGhI", "AgentGatewayUrl": "https://prior-auth-agent-abc123def.gateway"
       ".bedrock-agentcore.us-east-1.amazonaws.com/mcp", "TokenDomain": "https://demo-x.auth.us-east-1.amazoncognito.com"}
SCREEN = (f"agent {OUT['AgentClientId']} clinician {OUT['ClinicianClientId']} intake {OUT['IntakeClientId']}\n"
          f"pool {OUT['UserPoolId']} url {OUT['AgentGatewayUrl']} domain {OUT['TokenDomain']}\n"
          "role arn:aws:iam::123456789012:role/prior-auth-runtime-role account 123456789012\n"
          "token eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ4In0.c2ln operator AWSReservedSSO_AdministratorAccess_0123abcd4567ef89\n"
          "kept: ReviewerTools___record_adverse_determination SYN-CASE-CF-1 run 20261017T003416Z-8dd3a8dc\n")


def test_redact_masks_every_identifier():
    buf = io.StringIO()
    demo.RedactingStream(buf, demo.demo_named(OUT)).write(SCREEN)
    shown = buf.getvalue()
    assert find_unredacted(shown, list(OUT.values())) == []
    for leaked in ("123456789012", "0123abcd4567ef89", "eyJ", "us-east-1_AbCdEfGhI"):
        assert leaked not in shown
    assert "<intake-client-id>" in shown and "<operator-role>" in shown
    # What the audience needs to see stays.
    assert "ReviewerTools___record_adverse_determination" in shown and "SYN-CASE-CF-1" in shown
    assert "20261017T003416Z-8dd3a8dc" in shown


def test_redact_flag_is_parsed_anywhere(monkeypatch):
    seen = {}
    monkeypatch.setattr(sys, "stdout", sys.stdout)  # restored after the test
    monkeypatch.setattr(sys, "stderr", sys.stderr)
    monkeypatch.setattr(demo.gc, "outputs", lambda: OUT)
    monkeypatch.setitem(demo.BEATS, "1", lambda session, out: seen.setdefault("stdout", type(sys.stdout)))
    assert demo.main(["--redact", "1"]) == 0
    assert seen["stdout"] is demo.RedactingStream
    assert demo.main(["1", "--redact", "2"]) == 2
