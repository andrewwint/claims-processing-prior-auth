"""The gate before the repository goes public: scan the working tree and the full git history
(every commit's diff and its author and committer metadata) for identifiers that must not be
published.

Two kinds of needle:
- exact: this deployment's identifiers, read from the git-ignored local files (`.local/`,
  `cdk.context.json`): account ID, pool and client IDs, gateway IDs, the policy engine ID, the
  Cognito domain prefix, the runtime ID; plus the restricted words in RESTRICTED_WORDS;
- generic: anything shaped like an account ID, an ARN with an account, an email address, a JWT,
  an access key or an SSO role name. Reviewed fake values (test fixtures, the no-reply addresses)
  are listed with their justification in security/public-scan-allow.json.

A positive control runs first: one planted value of each kind must be caught, or the scan fails.
Hits are reported as commit, file and line with the value masked, so the scan never re-leaks
what it finds. Exit status 1 on any hit or a failed control.

Usage: python -m scripts.public_scan
"""

import codecs
import json
import re
import subprocess
import sys
from pathlib import Path

from scripts.redact import ACCESS_KEY, ACCOUNT_ID, ARN, EMAIL, JWT

ROOT = Path(__file__).resolve().parent.parent
ALLOW = ROOT / "security" / "public-scan-allow.json"
# Stored rot13, so this file does not match itself. Matched case-insensitively, except paths.
RESTRICTED_WORDS = tuple(codecs.decode(w, "rot13") for w in ("unpxrebar", "rzoneteb", "fnzcyr-cevbe-nhgubevmngvba",
                                                                "jvag.naqerj"))
RESTRICTED_PATHS = (codecs.decode("/Hfref/", "rot13"),)  # case-sensitive: "prior-auth/users/" is a secret name
SSO_ROLE = re.compile(r"AWSReservedSSO_[A-Za-z0-9_]+_[0-9a-f]{16}")
GENERIC = {"account id": ACCOUNT_ID, "arn": ARN, "email": EMAIL, "jwt": JWT, "access key": ACCESS_KEY,
           "sso role": SSO_ROLE}


def known_identifiers() -> list[str]:
    """This deployment's identifiers, from the git-ignored local files only."""
    values = set()
    outputs = ROOT / ".local" / "d1-outputs.json"
    if outputs.exists():
        for k, v in json.loads(outputs.read_text()).get("PriorAuthGateways", {}).items():
            if k.endswith(("Id", "Url", "Arn", "Domain")) and isinstance(v, str):
                values.add(v)
    context = ROOT / "cdk.context.json"
    if context.exists():
        for k in ("cognito_domain_prefix", "agent_sub", "policy_engine_id", "intake_client_id", "user_pool_id",
                  "agent_gateway_url", "agent_gateway_id", "reviewer_gateway_id"):
            if v := json.loads(context.read_text()).get(k):
                values.add(str(v))
    runtime = ROOT / ".local" / "runtime.json"
    if runtime.exists():
        r = json.loads(runtime.read_text())
        values |= {r["id"], r["arn"]}
        if m := re.search(r":(\d{12}):", r["arn"]):
            values.add(m.group(1))
    return sorted(v for v in values if len(v) >= 6)


def allowed() -> set[str]:
    return {e["value"] for e in json.loads(ALLOW.read_text())["allowed"]} if ALLOW.exists() else set()


def mask(value: str) -> str:
    return value[:3] + "…" + f"({len(value)} chars)"


def scan_text(text: str, exact: list[str], allow: set[str]) -> list[tuple[str, str, int]]:
    """(kind, masked value, line number) for every hit."""
    hits = []
    for n, line in enumerate(text.splitlines(), start=1):
        for v in exact:
            if v in line:
                hits.append(("deployment identifier", mask(v), n))
        lower = line.lower()
        for w in RESTRICTED_WORDS:
            if w in lower:
                hits.append(("restricted word", w, n))
        for w in RESTRICTED_PATHS:
            if w in line:
                hits.append(("restricted word", w, n))
        for kind, pattern in GENERIC.items():
            for m in pattern.findall(line):
                value = m if isinstance(m, str) else m[0]
                if value not in allow:
                    hits.append((kind, mask(value), n))
    return hits


def positive_control(exact: list[str], allow: set[str]) -> list[str]:
    """Every needle kind must catch a planted value; returns the kinds that did not."""
    # Built at run time, so this file's own text never matches.
    acct = "4040" + "30302020"  # never allowlisted
    planted = {
        "deployment identifier": exact[0] if exact else None,
        "restricted word": "see the " + RESTRICTED_WORDS[0] + " report",
        "account id": f"account {acct} here",
        "arn": "arn:" + f"aws:iam::{acct}:role/x",
        "email": "someone.planted" + "@corp.example",
        "jwt": "eyJ" + "hbGciOiJIUzI1NiJ9.eyJzdWIiOiJwbGFudGVkIn0.c2lnbmF0dXJl",
        "access key": "AKIA" + "PLANTEDCONTROL12",
        "sso role": "AWSReservedSSO_" + "Planted_0123456789abcdef",
    }
    missed = []
    for kind, text in planted.items():
        if text is None:
            missed.append(f"{kind} (no local identifiers found: run from a deployed checkout)")
        elif not any(h[0] == kind for h in scan_text(text, exact, allow - {text})):
            missed.append(kind)
    return missed


def tree_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    return [f for f in out.splitlines() if f != "security/public-scan-allow.json"]


def history() -> list[tuple[str, str, str]]:
    """(commit, file, added text) for every commit's diff, plus each commit's metadata."""
    out = subprocess.run(["git", "log", "--all", "-p", "--no-color", "--format=COMMIT %H%n%an <%ae>%n%cn <%ce>%n%B"],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    chunks, commit, path, buf = [], "", "<metadata>", []
    for line in out.splitlines():
        if line.startswith("COMMIT "):
            if buf:
                chunks.append((commit, path, "\n".join(buf)))
            commit, path, buf = line[7:19], "<metadata>", []
        elif line.startswith("+++ b/"):
            if buf:
                chunks.append((commit, path, "\n".join(buf)))
            path, buf = line[6:], []
        elif path == "<metadata>" or (line.startswith(("+", "-")) and not line.startswith(("+++", "---"))):
            buf.append(line)
    if buf:
        chunks.append((commit, path, "\n".join(buf)))
    return [c for c in chunks if c[1] != "security/public-scan-allow.json"]


def main() -> int:
    exact, allow = known_identifiers(), allowed()
    missed = positive_control(exact, allow)
    if missed:
        print(f"FAIL: positive control missed {missed}")
        return 1
    print(f"positive control: every needle kind caught its planted value ({len(exact)} deployment identifiers)")
    hits = []
    for f in tree_files():
        try:
            text = (ROOT / f).read_text()
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        hits += [("tree", f, n, kind, value) for kind, value, n in scan_text(text, exact, allow)]
    for commit, f, text in history():
        hits += [(commit, f, n, kind, value) for kind, value, n in scan_text(text, exact, allow)]
    seen = set()
    for h in hits:
        if h not in seen:
            seen.add(h)
            print(f"HIT {h[0]} {h[1]}:{h[2]} {h[3]}: {h[4]}")
    print(f"{len(seen)} hits" if seen else "PASS: no hits in the working tree or history")
    return 1 if seen else 0


if __name__ == "__main__":
    sys.exit(main())
