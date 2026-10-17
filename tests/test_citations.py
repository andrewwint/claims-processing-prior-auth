"""Every citation row in the ledger (R*) has a recorded official source: URLs, a retrieval date,
the quotes relied on, and a verdict on how far it supports the article's wording."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = json.loads((ROOT / "evidence/citations/sources.json").read_text())["sources"]
OFFICIAL = ("federalregister.gov", "ecfr.gov", "cms.gov", "leg.wa.gov", "leg.colorado.gov", "hl7.org")


def ledger_r_rows() -> list[str]:
    text = (ROOT / "openspec/claims-ledger.md").read_text()
    return re.findall(r"^\| (R\d+) \|", text, flags=re.M)


def test_every_r_row_has_a_recorded_source():
    recorded = {s["row"] for s in SOURCES}
    assert set(ledger_r_rows()) <= recorded


def test_every_source_is_official_dated_and_quoted():
    for s in SOURCES:
        assert s["urls"] and all(any(o in u for o in OFFICIAL) for u in s["urls"]), s["row"]
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", s["retrieved"]), s["row"]
        assert s["quotes"] and all(q.strip() for q in s["quotes"]), s["row"]
        assert s["verdict"].startswith(("supported", "partly", "not supported")), s["row"]


def test_every_r_row_points_at_the_sources_file():
    text = (ROOT / "openspec/claims-ledger.md").read_text()
    for row in ledger_r_rows():
        line = next(l for l in text.splitlines() if l.startswith(f"| {row} |"))
        assert "evidence/citations/sources.json" in line, row
