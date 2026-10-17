"""SAMPLE_OUTPUTS.md is generated from committed evidence, unedited and redacted."""

from scripts import sample_outputs
from scripts.redact import find_unredacted


def test_sample_outputs_regenerate_byte_identically():
    assert sample_outputs.OUT.read_text() == sample_outputs.render()


def test_sample_outputs_carry_no_identifiers():
    assert find_unredacted(sample_outputs.render()) == []


def test_every_source_is_committed_evidence_or_the_report():
    for path in sample_outputs.SOURCES.values():
        assert (sample_outputs.ROOT / path).is_file() and path.startswith(("evidence/", "evaluation/report.md"))
