"""Redact identifiers from evidence before it is committed.

Known identifiers (client IDs, gateway ARNs) are replaced with named
placeholders that match the article, for example `<agent-client-id>` and
`<reviewer-gateway-arn>`. Any remaining ARN, gateway host, Cognito domain,
user pool ID, 26-character client ID or 12-digit account ID is replaced
generically. Action names (`<target>___<tool>`) are never changed: B5 compares
the redacted policy text with the article character for character.
"""

import re

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
    text = ARN.sub("<arn>", text)
    text = GATEWAY_HOST.sub("<gateway-host>", text)
    text = COGNITO_DOMAIN.sub("<cognito-domain>", text)
    text = COGNITO_POOL_ID.sub("<user-pool-id>", text)
    text = COGNITO_CLIENT_ID.sub("<client-id>", text)
    return ACCOUNT_ID.sub("<account-id>", text)


def find_unredacted(text: str, known_values: list[str] = ()) -> list[str]:
    """Identifiers that should not appear in committed evidence."""
    patterns = (ARN, GATEWAY_HOST, COGNITO_DOMAIN, COGNITO_POOL_ID, COGNITO_CLIENT_ID, ACCOUNT_ID)
    hits = [h for p in patterns for h in p.findall(text)]
    hits += [v for v in known_values if v and v in text]
    return list(dict.fromkeys(hits))
