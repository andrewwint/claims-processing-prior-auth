"""Prepare the history to publish (PM, 2026-10-17): mask the values the public scan finds in
history, in a fresh clone, and record the SHA remap. Nothing is pushed and no repository is
created or renamed here; those steps need Andrew's go-ahead and are printed at the end.

1. Find the values to mask: every hit of the public scan's generic patterns in history that is
   not allowlisted (today: one SSO role suffix). The values are never written into the repository.
2. Clone this repository (all branches) into a scratch directory and run `git filter-repo
   --replace-text` there, replacing each value with a masked placeholder.
3. In the rewritten clone, write evidence/sha-remap.jsonl (old SHA -> new SHA, from filter-repo's
   commit map) and add `published_sha` beside every entry in evidence/deploys.jsonl, keeping the
   original `sha` (what was deployed). Commit that.
4. Run the public scan against the rewritten clone; it must pass.

Usage: python -m scripts.rewrite_history <scratch-dir>
"""

import json
import subprocess
import sys
from pathlib import Path

from scripts import public_scan as ps

ROOT = ps.ROOT
MASK = "<masked-sso-role-suffix>"


def values_to_mask() -> list[str]:
    allow = ps.allowed()
    found = set()
    for _, _, text in ps.history():
        for kind, pattern in ps.GENERIC.items():
            for m in pattern.findall(text):
                value = m if isinstance(m, str) else m[0]
                if value not in allow:
                    found.add(value)
    return sorted(found)


def git(*args, cwd) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    scratch = Path(sys.argv[1]).resolve()
    if ROOT in scratch.parents or scratch == ROOT:
        print("refusing: the scratch directory must be outside the repository", file=sys.stderr)
        return 2
    values = values_to_mask()
    print(f"{len(values)} value(s) to mask: {[ps.mask(v) for v in values]}")
    clone = scratch / "rewritten"
    if clone.exists():
        print(f"refusing: {clone} exists", file=sys.stderr)
        return 2
    scratch.mkdir(parents=True, exist_ok=True)
    git("clone", "--no-local", str(ROOT), str(clone), cwd=scratch)
    # The clone does not inherit this repository's local config; the remap commit must carry the
    # same no-reply identity as every other commit, never the machine's global one.
    for key in ("user.name", "user.email"):
        value = git("config", "--local", key, cwd=ROOT).strip()
        if key == "user.email" and not value.endswith("@users.noreply.github.com"):
            print(f"refusing: this repository's user.email is not a GitHub no-reply address", file=sys.stderr)
            return 2
        git("config", "--local", key, value, cwd=clone)
    replacements = scratch / "replacements.txt"  # outside the repository; deleted below
    replacements.write_text("".join(f"{v}==>{MASK}\n" for v in values))
    try:
        subprocess.run(["git", "filter-repo", "--replace-text", str(replacements), "--force"], cwd=clone, check=True)
    finally:
        replacements.unlink()
    pairs = [line.split() for line in (clone / ".git/filter-repo/commit-map").read_text().splitlines()[1:]]
    remap = {old: new for old, new in pairs if old != new}
    (clone / "evidence/sha-remap.jsonl").write_text(
        "".join(json.dumps({"old": old, "new": new}) + "\n" for old, new in sorted(pairs) if old != new))
    deploys = clone / "evidence/deploys.jsonl"
    entries = [json.loads(line) for line in deploys.read_text().splitlines() if line.strip()]
    def published(sha: str) -> str:
        """The published SHA for a full or abbreviated original SHA (unchanged commits keep theirs)."""
        full = next((old for old, _ in pairs if old.startswith(sha)), None)
        return remap.get(full, full or sha)[:len(sha)] if len(sha) < 40 else remap.get(full, sha)
    for e in entries:
        if "sha" in e:
            e["published_sha"] = published(e["sha"])
        if "content_committed_in" in e:  # backfilled dirty-tree deploys record where the content landed
            e["published_content_committed_in"] = published(e["content_committed_in"])
    deploys.write_text("".join(json.dumps(e, sort_keys=True) + "\n" for e in entries))
    git("add", "evidence/sha-remap.jsonl", "evidence/deploys.jsonl", cwd=clone)
    git("commit", "-q", "-m", "Record the SHA remap for the published history\n\n"
        "The history was rewritten to mask one SSO role suffix (scripts/rewrite_history.py). "
        "evidence/sha-remap.jsonl maps each original commit to its published one; each deploys.jsonl "
        "entry keeps the deployed sha and adds published_sha.\n\n"
        "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>", cwd=clone)
    changed = sum(e.get("published_sha", e.get("sha")) != e.get("sha") for e in entries)
    print(f"rewritten: {len(remap)} commits remapped; {changed} deploy entries carry a new published_sha")
    rc = ps.main(["--repo", str(clone)])
    print("\nNext, only with Andrew's go-ahead (PM 2026-10-17, Sunday, last step before the flip):\n"
          "  1. keep the original repository private and archived\n"
          "  2. push the rewritten clone to the new, private repository (claims-processing-prior-auth)\n"
          "  3. run make scan against it again, then make it public")
    return rc


if __name__ == "__main__":
    sys.exit(main())
