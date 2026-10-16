"""Reviewed exceptions to the secret-safety control.

The same pattern the secret-safety hook uses is applied to every tracked file.
Any occurrence that is not a reviewed exception fails, and so does any exception
that no longer matches anything. The control is never routed around; where its
purpose does not apply, the reason is recorded in security/control-exceptions.json.
"""

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCEPTIONS_FILE = ROOT / "security" / "control-exceptions.json"
# The hook's own pattern: GetSecretValue / get_secret_value / get-secret-value, with or without batch.
SECRET_FETCH = re.compile(r"(batch[-_]?)?get[-_]?secret[-_]?value", re.I)
REQUIRED = ("control", "match", "file", "kind", "justification", "reviewed_by", "approved_by")


def exceptions() -> list[dict]:
    return json.loads(EXCEPTIONS_FILE.read_text())["exceptions"]


def occurrences() -> list[tuple[str, str]]:
    files = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT,
                           capture_output=True, text=True, check=True).stdout.split()
    hits = []
    for name in files:
        if name in ("security/control-exceptions.json", "uv.lock"):
            continue
        try:
            text = (ROOT / name).read_text()
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        for line in text.splitlines():
            if SECRET_FETCH.search(line):
                hits.append((name, line.strip()))
    return hits


def test_every_exception_is_fully_reviewed():
    for e in exceptions():
        assert all(isinstance(e.get(k), str) and e[k].strip() for k in REQUIRED), e


def test_every_occurrence_is_a_reviewed_exception():
    allowed = {(e["file"], e["match"]) for e in exceptions()}
    unreviewed = [(f, line) for f, line in occurrences()
                  if f != "tests/test_control_exceptions.py"
                  and not any(f == af and am in line for af, am in allowed)]
    assert unreviewed == []


def test_no_exception_is_stale():
    found = occurrences()
    for e in exceptions():
        assert any(f == e["file"] and e["match"] in line for f, line in found), e
