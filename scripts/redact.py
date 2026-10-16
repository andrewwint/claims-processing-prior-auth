"""Redact identifiers from evidence before it is committed.

Known identifiers (client IDs, gateway ARNs) are replaced with named
placeholders that match the article, for example `<agent-client-id>` and
`<reviewer-gateway-arn>`. Any remaining ARN or 12-digit account ID is replaced
generically. Action names (`<target>___<tool>`) are never changed: B5 compares
the redacted policy text with the article character for character.
"""

import re

ARN = re.compile(r"arn:aws[a-z-]*:[a-z0-9-]*:[a-z0-9-]*:\d{12}:[A-Za-z0-9_/:.+=@-]+")
ACCOUNT_ID = re.compile(r"(?<!\d)\d{12}(?!\d)")


def redact(text: str, named: dict[str, str] | None = None) -> str:
    for value, placeholder in sorted((named or {}).items(), key=lambda kv: -len(kv[0])):
        if value:
            text = text.replace(value, placeholder)
    text = ARN.sub("<arn>", text)
    return ACCOUNT_ID.sub("<account-id>", text)


def find_unredacted(text: str, known_values: list[str] = ()) -> list[str]:
    """Identifiers that should not appear in committed evidence."""
    hits = ARN.findall(text) + ACCOUNT_ID.findall(text)
    return hits + [v for v in known_values if v and v in text]
