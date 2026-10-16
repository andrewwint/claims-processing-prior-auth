import pytest

from scripts.redact import find_unredacted, redact

ACCOUNT = "123456789012"
GATEWAY_ARN = f"arn:aws:bedrock-agentcore:us-east-1:{ACCOUNT}:gateway/reviewer-abc123"
AGENT_CLIENT = "4f1k2l3m4n5o6p7q8r9s0t1u2v"
ACTION = 'AgentCore::Action::"ReviewerTools___record_adverse_determination"'
NAMED = {AGENT_CLIENT: "<agent-client-id>", GATEWAY_ARN: "<reviewer-gateway-arn>"}

DEPLOYED = f"""forbid(
  principal == AgentCore::OAuthUser::"{AGENT_CLIENT}",
  action == {ACTION},
  resource == AgentCore::Gateway::"{GATEWAY_ARN}"
);"""

ARTICLE_SNIPPET = """forbid(
  principal == AgentCore::OAuthUser::"<agent-client-id>",
  action == AgentCore::Action::"ReviewerTools___record_adverse_determination",
  resource == AgentCore::Gateway::"<reviewer-gateway-arn>"
);"""


def test_redacted_policy_keeps_the_exact_action_string():
    out = redact(DEPLOYED, NAMED)
    assert ACTION in out
    assert out.count("___") == DEPLOYED.count("___") == 1


def test_redacted_policy_equals_the_article_form():
    assert redact(DEPLOYED, NAMED) == ARTICLE_SNIPPET


def test_generic_arn_and_account_id_are_replaced():
    text = f'{{"Arn": "arn:aws:iam::{ACCOUNT}:role/x", "Account": "{ACCOUNT}"}}'
    out = redact(text)
    assert out == '{"Arn": "<arn>", "Account": "<account-id>"}'
    assert find_unredacted(out) == []


def test_find_unredacted_reports_leftovers():
    assert find_unredacted(f"id {ACCOUNT}") == [ACCOUNT]
    assert find_unredacted(f"client {AGENT_CLIENT}", [AGENT_CLIENT]) == [AGENT_CLIENT]


def test_longer_numbers_are_not_account_ids():
    assert redact("1234567890123") == "1234567890123"


def test_unnamed_cognito_and_gateway_identifiers_are_replaced():
    text = ('{"pool": "us-east-1_AbCdEf123", "client": "4f1k2l3m4n5o6p7q8r9s0t1u2v", '
            '"url": "https://prior-auth-agent-x1y2z3.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp", '
            '"domain": "prior-auth-x9.auth.us-east-1.amazoncognito.com"}')
    out = redact(text)
    assert find_unredacted(out) == []
    for placeholder in ("<user-pool-id>", "<client-id>", "<gateway-host>", "<cognito-domain>"):
        assert placeholder in out


def test_generic_patterns_never_touch_action_names_or_hashes_of_other_length():
    assert redact(ACTION) == ACTION
    assert redact("AgentTools___record_approval") == "AgentTools___record_approval"
    sha = "a" * 64
    assert redact(sha) == sha


# X4 (second security review)
@pytest.mark.parametrize("secret,placeholder", [
    ("eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxMjMifQ.c2lnbmF0dXJl", "<jwt>"),
    ("9a8b7c6d-1234-4abc-8def-0123456789ab", "<uuid>"),
    ("someone@example.com", "<email>"),
    ("AKIAABCDEFGHIJKLMNOP", "<access-key>"),
    ("1q2w3e4r5t6y7u8i9o0p1q2w3e4r5t6y7u8i9o0p1q2w3e4r5t6", "<secret>"),
    ("prior-auth-agent-x1y2z3a4b5", "<gateway-id>"),
])
def test_more_identifier_shapes_are_replaced(secret, placeholder):
    out = redact(f'{{"v": "{secret}"}}')
    assert placeholder in out and secret not in out
    assert find_unredacted(out) == []


def test_sha256_hashes_survive_redaction():
    import hashlib
    h = hashlib.sha256(b"packet").hexdigest()
    assert redact(h) == h and find_unredacted(h) == []


def test_known_values_map_stack_outputs_to_named_placeholders():
    from scripts.redact import known_values
    named = known_values({"AgentClientId": AGENT_CLIENT, "ReviewerGatewayArn": GATEWAY_ARN, "Other": "x"})
    assert named == {AGENT_CLIENT: "<agent-client-id>", GATEWAY_ARN: "<reviewer-gateway-arn>"}



def test_committed_evidence_has_no_unredacted_identifiers():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "evidence"
    leaks = {str(p): find_unredacted(p.read_text()) for p in root.rglob("*") if p.is_file()}
    assert {k: v for k, v in leaks.items() if v} == {}
