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
