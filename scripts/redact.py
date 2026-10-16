"""Redact identifiers from evidence before it is committed.

Known identifiers (client IDs, gateway ARNs) are replaced with named
placeholders that match the article, for example `<agent-client-id>` and
`<reviewer-gateway-arn>`. Any remaining ARN, gateway host, Cognito domain,
user pool ID, 26-character client ID or 12-digit account ID is replaced
generically. Action names (`<target>___<tool>`) are never changed: B5 compares
the redacted policy text with the article character for character.
"""

import re

JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*")
UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
ACCESS_KEY = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")
# Cognito client secrets: long lowercase alphanumerics with at least one non-hex
# letter, so SHA-256 hashes (64 hex characters) stay intact.
CLIENT_SECRET = re.compile(r"(?<![A-Za-z0-9_])(?=[a-z0-9]*[g-z])[a-z0-9]{40,60}(?![A-Za-z0-9_])")
GATEWAY_ID = re.compile(r"\bprior-auth-(?:agent|reviewer)-[a-z0-9]{6,}\b")
COGNITO_POOL_ID = re.compile(r"\b[a-z]{2}-[a-z]+-\d_[A-Za-z0-9]{9}\b")
COGNITO_CLIENT_ID = re.compile(r"(?<![A-Za-z0-9_])[a-z0-9]{26}(?![A-Za-z0-9_])")
COGNITO_DOMAIN = re.compile(r"\b[a-z0-9-]+\.auth\.[a-z0-9-]+\.amazoncognito\.com\b")
GATEWAY_HOST = re.compile(r"\b[a-z0-9-]+\.gateway\.bedrock-agentcore\.[a-z0-9-]+\.amazonaws\.com\b")
ARN = re.compile(r"arn:aws[a-z-]*:[a-z0-9-]*:[a-z0-9-]*:\d{12}:[A-Za-z0-9_/:.+=@-]+")
ACCOUNT_ID = re.compile(r"(?<!\d)\d{12}(?!\d)")


def redact(text: str, named: dict[str, str] | None = None) -> str:
    for value, placeholder in sorted((named or {}).items(), key=lambda kv: -len(kv[0])):
        if value:
            text = text.replace(value, placeholder)
    text = JWT.sub("<jwt>", text)
    text = ARN.sub("<arn>", text)
    text = GATEWAY_HOST.sub("<gateway-host>", text)
    text = GATEWAY_ID.sub("<gateway-id>", text)
    text = EMAIL.sub("<email>", text)
    text = ACCESS_KEY.sub("<access-key>", text)
    text = UUID.sub("<uuid>", text)
    text = CLIENT_SECRET.sub("<secret>", text)
    text = COGNITO_DOMAIN.sub("<cognito-domain>", text)
    text = COGNITO_POOL_ID.sub("<user-pool-id>", text)
    text = COGNITO_CLIENT_ID.sub("<client-id>", text)
    return ACCOUNT_ID.sub("<account-id>", text)


def known_values(stack_outputs: dict[str, str]) -> dict[str, str]:
    """Named placeholders for this deployment's identifiers, from stack outputs.

    Every evidence writer passes these to redact() and find_unredacted().
    """
    names = {
        "AgentClientId": "<agent-client-id>",
        "ClinicianClientId": "<clinician-client-id>",
        "UserPoolId": "<user-pool-id>",
        "AgentGatewayArn": "<agent-gateway-arn>",
        "ReviewerGatewayArn": "<reviewer-gateway-arn>",
        "AgentGatewayId": "<agent-gateway-id>",
        "ReviewerGatewayId": "<reviewer-gateway-id>",
        "AgentGatewayUrl": "<agent-gateway-url>",
        "ReviewerGatewayUrl": "<reviewer-gateway-url>",
        "TokenDomain": "<token-domain>",
        "PolicyEngineId": "<policy-engine-id>",
    }
    return {stack_outputs[k]: v for k, v in names.items() if stack_outputs.get(k)}


def find_unredacted(text: str, known_values: list[str] = ()) -> list[str]:
    """Identifiers that should not appear in committed evidence."""
    patterns = (JWT, ARN, GATEWAY_HOST, GATEWAY_ID, EMAIL, ACCESS_KEY, UUID, CLIENT_SECRET,
                COGNITO_DOMAIN, COGNITO_POOL_ID, COGNITO_CLIENT_ID, ACCOUNT_ID)
    hits = [h for p in patterns for h in p.findall(text)]
    hits += [v for v in known_values if v and v in text]
    return list(dict.fromkeys(hits))
