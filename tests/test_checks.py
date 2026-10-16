"""Negative tests for each check, against the fixture copies of the trusted sources."""

import copy

import pytest

import checks
from tools.approval import load_fixtures

TRUSTED, PACKETS = load_fixtures()
REQUEST = TRUSTED["requests"]["SYN-CASE-PASS"]
CRITERIA = TRUSTED["criteria"]["SYN-PAYER-A"]["63030"]
CHART = TRUSTED["chart"]


def verdict(mutate=None, chart=CHART):
    packet = copy.deepcopy(PACKETS["SYN-PKT-PASS"])
    if mutate:
        mutate(packet)
    return checks.recompute(packet, REQUEST, CRITERIA, chart)


def finding(packet, cid):
    return next(f for f in packet["findings"] if f["criterion_id"] == cid)


def test_the_passing_packet_is_approvable():
    v = verdict()
    assert v.approvable and v.statuses == {"C1": "Met", "C2": "Met", "C3": "Met"}


# Check 1: schema
@pytest.mark.parametrize("mutate", [
    lambda p: p.pop("findings"),
    lambda p: p.update(findings="C1 met"),
    lambda p: p.pop("case_id"),
    lambda p: finding(p, "C1").pop("line"),
    lambda p: finding(p, "C1").update(line="3"),
    lambda p: finding(p, "C1").update(page=True),
    lambda p: p["findings"].append({"criterion_id": "C9", "doc_id": "SYN-DOC-PT-001", "page": 1, "line": 3, "value": "Eight visits"}),
    lambda p: p["findings"].append("C3 met"),
])
def test_malformed_packet_fails_schema(mutate):
    v = verdict(mutate)
    assert not v.approvable and any(f.startswith("schema:") for f in v.failures)


def test_packet_for_another_case_fails():
    v = verdict(lambda p: p.update(case_id="SYN-CASE-FAIL"))
    assert "schema: packet case_id does not match the request" in v.failures


def test_not_an_object_fails_schema():
    assert checks.recompute(["x"], REQUEST, CRITERIA, CHART).failures == ["schema: packet is not an object"]


# Check 2: source match, exact at the cited line
@pytest.mark.parametrize("mutate,why", [
    (lambda p: finding(p, "C2").update(line=2), "adjacent line"),
    (lambda p: finding(p, "C2").update(value="L4-L5 disc herniation with nerve root compresion"), "one character"),
    (lambda p: finding(p, "C2").update(value="l4-l5 disc herniation with nerve root compression"), "case"),
    (lambda p: finding(p, "C2").update(value="L4-L5  disc herniation"), "whitespace"),
    (lambda p: finding(p, "C2").update(value="Impression: L4-L5 disc herniation with nerve root compression and stenosis"), "longer than the line"),
    (lambda p: finding(p, "C2").update(page=2), "page out of range"),
    (lambda p: finding(p, "C2").update(line=0), "line zero"),
    (lambda p: finding(p, "C2").update(line=-1), "negative line wraps in Python"),
    (lambda p: finding(p, "C1").update(value="Twelve visits over eight weeks"), "made up"),
])
def test_value_not_at_its_location_fails(mutate, why):
    v = verdict(mutate)
    assert not v.approvable, why
    assert any(f.startswith("source match:") for f in v.failures), why


@pytest.mark.parametrize("value", ["", "   ", "L4-", " a b "])
def test_trivial_values_never_match(value):
    v = verdict(lambda p: finding(p, "C2").update(value=value))
    assert any("shorter than 4 characters" in f for f in v.failures)


def test_nfc_equivalent_text_matches():
    chart = copy.deepcopy(CHART)
    chart["docs"]["SYN-DOC-MRI-001"]["pages"][0][2] = "Impression: L4-L5 café note."
    f = {"criterion_id": "C2", "doc_id": "SYN-DOC-MRI-001", "page": 1, "line": 3, "value": "cafe\u0301 note"}
    assert checks.source_match(f, chart["docs"]) is None


# Check 3: same patient, from the chart index
def test_another_patients_document_fails():
    v = verdict(lambda p: finding(p, "C3").update(doc_id="SYN-DOC-FUNC-002", value="Oswestry Disability Index 52 percent"))
    assert "same patient: SYN-DOC-FUNC-002 belongs to another patient" in v.failures


def test_another_patients_document_labeled_with_this_patient_fails():
    def relabel(p):
        p["patient_id"] = "SYN-PAT-0001"
        finding(p, "C3").update(doc_id="SYN-DOC-FUNC-002", value="Oswestry Disability Index 52 percent", patient_id="SYN-PAT-0001")
    v = verdict(relabel)
    assert "same patient: SYN-DOC-FUNC-002 belongs to another patient" in v.failures


def test_unknown_document_fails():
    v = verdict(lambda p: finding(p, "C3").update(doc_id="SYN-DOC-NOPE"))
    assert "same patient: SYN-DOC-NOPE is not in the chart index" in v.failures


# Recompute: criteria come from the compiled policy, never the packet
def test_missing_finding_is_not_found():
    v = verdict(lambda p: p["findings"].pop())
    assert v.statuses["C3"] == "Not found" and v.gaps == ["C3"] and not v.failures


def test_one_bad_finding_spoils_its_criterion():
    v = verdict(lambda p: p["findings"].append(
        {"criterion_id": "C3", "doc_id": "SYN-DOC-FUNC-002", "page": 1, "line": 2, "value": "Oswestry Disability Index 52 percent"}))
    assert v.statuses["C3"] == "Not found" and not v.approvable


def test_no_criteria_means_no_verified_policy():
    assert checks.recompute(PACKETS["SYN-PKT-PASS"], REQUEST, [], CHART).failures == ["no verified policy"]


def test_packet_cannot_add_or_drop_criteria():
    fewer = CRITERIA[:2]
    v = checks.recompute(PACKETS["SYN-PKT-PASS"], REQUEST, fewer, CHART)
    assert any("C3 not in the compiled policy" in f for f in v.failures)


def test_hash_is_canonical_and_sensitive():
    p = PACKETS["SYN-PKT-PASS"]
    assert checks.packet_hash(dict(reversed(list(p.items())))) == checks.packet_hash(p)
    q = copy.deepcopy(p)
    q["findings"][0]["line"] = 2
    assert checks.packet_hash(q) != checks.packet_hash(p)


# X1 (second security review): a finding must satisfy its criterion's compiled evidence rule
def _all_cite(packet, doc_id, page, line, value):
    packet["findings"] = [{"criterion_id": c, "doc_id": doc_id, "page": page, "line": line, "value": value}
                          for c in ("C1", "C2", "C3")]


@pytest.mark.parametrize("doc_id,line,value", [
    ("SYN-DOC-PT-001", 1, "SYNTHETIC"),
    ("SYN-DOC-MRI-001", 3, "nerve"),
    ("SYN-DOC-MRI-001", 3, "L4-L5 disc herniation with nerve root compression"),
])
def test_one_quote_for_every_criterion_is_refused(doc_id, line, value):
    v = verdict(lambda p: _all_cite(p, doc_id, 1, line, value))
    assert not v.approvable


def test_quote_must_state_what_the_criterion_requires():
    v = verdict(lambda p: finding(p, "C1").update(value="conservative therapy completed"))
    assert any("does not state what the criterion requires" in f for f in v.failures)


def test_wrong_kind_of_document_is_refused():
    v = verdict(lambda p: finding(p, "C2").update(doc_id="SYN-DOC-PT-001", line=2, value="Lumbar radiculopathy"))
    assert any("cannot be supported by a physical therapy notes document" in f for f in v.failures)


def test_numeric_minimum_is_enforced():
    chart = copy.deepcopy(CHART)
    chart["docs"]["SYN-DOC-PT-001"]["pages"][0][2] = "Four visits over three weeks; conservative therapy completed."
    v = verdict(lambda p: finding(p, "C1").update(value="Four visits over three weeks"), chart=chart)
    assert any("below the required weeks of 6" in f for f in v.failures)


def test_negated_finding_is_refused():
    chart = copy.deepcopy(CHART)
    chart["docs"]["SYN-DOC-MRI-001"]["pages"][0][2] = "Impression: no disc herniation with nerve root compression."
    v = verdict(lambda p: finding(p, "C2").update(value="disc herniation with nerve root compression"), chart=chart)
    assert any("negated on its line" in f for f in v.failures)


def test_same_line_cannot_support_two_criteria():
    def reuse(p):
        p["findings"].append({"criterion_id": "C1", "doc_id": "SYN-DOC-MRI-001", "page": 1, "line": 3,
                              "value": "L4-L5 disc herniation with nerve root compression"})
    v = verdict(reuse)
    assert any("cited for more than one criterion" in f for f in v.failures)


def test_criterion_without_a_rule_is_never_met():
    criteria = copy.deepcopy(CRITERIA)
    del criteria[2]["evidence_rule"]
    v = checks.recompute(PACKETS["SYN-PKT-PASS"], REQUEST, criteria, CHART)
    assert "evidence rule: C3 has no compiled evidence rule" in v.failures
