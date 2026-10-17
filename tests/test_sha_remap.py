"""The published history was rewritten once, to mask one SSO role suffix. evidence/sha-remap.jsonl
maps every original commit to its published commit; every deploy keeps the SHA that was
deployed, and that SHA resolves through the remap to the published SHA recorded beside it."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REMAP = {e["old"]: e["new"] for e in map(json.loads, (ROOT / "evidence/sha-remap.jsonl").read_text().splitlines())}
DEPLOYS = [json.loads(line) for line in (ROOT / "evidence/deploys.jsonl").read_text().splitlines() if line.strip()]


def resolve(sha: str) -> str:
    matches = [old for old in REMAP if old.startswith(sha)]
    assert len(matches) == 1, f"{sha} does not resolve to exactly one original commit"
    return REMAP[matches[0]][:len(sha)]


def test_the_remap_is_one_to_one():
    assert len(set(REMAP.values())) == len(REMAP) and all(len(k) == len(v) == 40 for k, v in REMAP.items())


def test_every_deploy_sha_resolves_through_the_remap():
    for e in DEPLOYS:
        if "sha" in e:
            assert e["sha_in_published_history"] == resolve(e["sha"]), e
        if "content_committed_in" in e:
            assert e["content_committed_in_published_history"] == resolve(e["content_committed_in"]), e
        assert "sha" in e or "content_committed_in" in e, e


def test_every_deploy_carries_its_published_sha():
    deployed = [e for e in DEPLOYS if "sha" in e]
    assert deployed and all("sha_in_published_history" in e for e in deployed)
