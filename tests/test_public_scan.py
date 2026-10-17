"""The public-flip gate: its positive control, its own source, and its allowlist."""

import json

from scripts import public_scan as ps


def test_positive_control_catches_every_needle_kind():
    assert ps.positive_control(["prior-auth-fake-identifier-xyz"], ps.allowed()) == []


def test_positive_control_fails_without_deployment_identifiers():
    assert any("deployment identifier" in m for m in ps.positive_control([], ps.allowed()))


def test_hits_are_masked_never_printed_whole():
    account = "9876" + "54321098"  # built at run time, so this file never matches the scan itself
    hits = ps.scan_text(f"arn:aws:iam::{account}:role/x", [], set())
    assert hits and all(account not in value for _, value, _ in hits)


def test_the_scanner_does_not_match_its_own_source():
    source = (ps.ROOT / "scripts" / "public_scan.py").read_text()
    assert ps.scan_text(source, [], ps.allowed()) == []


def test_lowercase_secret_name_prefix_is_not_a_local_path():
    assert ps.scan_text("prior-auth/users/syn-clinician-1", [], set()) == []


def test_every_allowlist_entry_is_justified_and_never_a_restricted_word():
    entries = json.loads(ps.ALLOW.read_text())["allowed"]
    for e in entries:
        assert all(isinstance(e.get(k), str) and e[k].strip() for k in ("value", "where", "why")), e
        assert not any(w in e["value"].lower() for w in ps.RESTRICTED_WORDS), e


def test_the_control_plants_values_that_are_never_allowlisted():
    planted = "4040" + "30302020"
    assert planted not in ps.allowed()
