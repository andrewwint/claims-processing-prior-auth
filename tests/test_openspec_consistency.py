"""The plan stays consistent: ledger rows name real changes, every demo beat is
delivered by exactly one change, deferred rows point at the hardening change,
and no open task describes scope that was cut or reversed."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGES = ROOT / "openspec" / "changes"
LEDGER = (ROOT / "openspec" / "claims-ledger.md").read_text()
EXISTING = {p.name for p in CHANGES.iterdir() if p.is_dir() and p.name != "archive"}


def ledger_rows():
    for line in LEDGER.splitlines():
        m = re.match(r"\| ([A-Z]\d+) \|", line)
        if m:
            yield m.group(1), [c.strip() for c in line.strip().strip("|").split("|")]


def test_every_ledger_row_names_an_existing_change():
    for row_id, cells in ledger_rows():
        if row_id.startswith("R"):
            continue  # citation rows have no change column
        named = set(re.findall(r"`([a-z0-9-]+)`", cells[-2]))
        assert named, f"{row_id} names no change"
        assert named <= EXISTING, f"{row_id} names unknown change(s) {named - EXISTING}"


def test_deferred_rows_point_at_post_monday_hardening():
    for row_id, cells in ledger_rows():
        if "deferred: known limitation" in cells[-1] and not row_id.startswith("M"):
            assert "post-monday-hardening" in cells[-2], row_id


def _delivered_beats(tasks: str) -> set[int]:
    beats = set()
    for line in tasks.splitlines():
        if "Delivers" in line:
            for phrase in re.findall(r"beats? \*?\*?([0-9][0-9 ,and]*)", line):
                beats |= {int(n) for n in re.findall(r"\d", phrase)}
    return beats


def test_every_demo_beat_is_delivered_by_exactly_one_change():
    owners = {b: [] for b in range(1, 7)}
    for change in EXISTING:
        tasks = CHANGES / change / "tasks.md"
        if tasks.exists():
            for b in _delivered_beats(tasks.read_text()):
                owners[b].append(change)
    assert all(len(v) == 1 for v in owners.values()), owners


STALE = ["SNS", "mutmut", "list_queue", "get_case", "no tool list", "model has no tools", "wrong-plan",
         "Tidewell", "interceptor", "tenant-a", "tenant-b", "per-tenant"]


def test_no_open_task_describes_cut_or_reversed_scope():
    for change in EXISTING - {"post-monday-hardening"}:
        tasks = CHANGES / change / "tasks.md"
        if not tasks.exists():
            continue
        for line in tasks.read_text().splitlines():
            if line.lstrip().startswith("- [ ]"):
                hits = [w for w in STALE if w.lower() in line.lower()]
                assert not hits, f"{change}: {line.strip()[:80]} -> {hits}"


DOC_REF = re.compile(r"(?<![\w/])(docs/[\w./-]+\.md)")


def test_no_dangling_doc_references():
    sources = [ROOT / "README.md", ROOT / "openspec" / "claims-ledger.md", *CHANGES.rglob("*.md"),
               *(ROOT / "docs").glob("*.md")]
    missing = {}
    for src in sources:
        for ref in DOC_REF.findall(src.read_text()):
            if not (ROOT / ref).exists():
                missing.setdefault(ref, []).append(str(src.relative_to(ROOT)))
    assert missing == {}


def test_empty_output_rules_doc_matches_the_design_table():
    design = (CHANGES / "case-packet-and-failure-routing" / "design.md").read_text()
    table = design[design.index("### D6."):design.index("### D7.")].split("\n", 1)[1].strip()
    assert table in (ROOT / "docs" / "empty-output-rules.md").read_text()
