"""The synthetic data: compiled policy, charts, index and demo cases (G1, G2, beats 2 and 3)."""

import copy
import json
import re
from pathlib import Path

import pytest

from data.cases import generate
from data.policies import compile as policy_compile
from prior_auth import checks

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SOURCE = DATA / "policies/source/larkspur-lumbar-discectomy.md"
COMPILED = DATA / "policies/compiled/SYN-PAYER-LARKSPUR/63030.json"


def load(path):
    return json.loads(Path(path).read_text())


# G1, G2: the compile step
def test_compile_reproduces_the_committed_output():
    assert policy_compile.compile_policy(SOURCE) == load(COMPILED)


def test_each_criterion_carries_version_location_and_rule():
    for c in load(COMPILED)["criteria"]:
        assert c["policy_version"] and c["source_location"]["line"] and c["evidence_rule"]["doc_kinds"]


def test_a_criterion_moved_from_its_location_fails_the_compile():
    compiled = policy_compile.compile_policy(SOURCE)
    lines = SOURCE.read_text().splitlines()
    moved = copy.deepcopy(compiled["criteria"])
    moved[0]["source_location"]["line"] -= 1
    with pytest.raises(policy_compile.CompileError):
        policy_compile.verify_locations(moved, lines)
    policy_compile.verify_locations(compiled["criteria"], lines)


def test_a_rule_with_an_unbounded_number_fails_the_compile(tmp_path):
    bad = SOURCE.read_text().replace('"minimums": {"odi": 40}', '"minimums": {}')
    path = tmp_path / "bad.md"
    path.write_text(bad)
    with pytest.raises(policy_compile.CompileError):
        policy_compile.compile_policy(path)


# Charts and cases
def test_generator_is_deterministic():
    docs, index, cases, eligibility = generate.build()
    assert load(DATA / "charts/index.json")["index"] == index
    assert load(DATA / "cases/cases.json")["cases"] == cases
    assert load(DATA / "cases/eligibility.json")["members"] == eligibility
    for doc_id, d in docs.items():
        stored = load(DATA / f"charts/{doc_id}.json")
        assert {k: v for k, v in stored.items() if k != "_label"} == d


def test_every_document_has_a_unique_canary_on_its_header():
    docs, *_ = generate.build()
    canaries = [re.search(r"CANARY-[0-9A-F]{12}", d["pages"][0][0]).group(0) for d in docs.values()]
    assert len(set(canaries)) == len(docs)


def test_the_forged_document_is_not_in_the_index():
    docs, index, cases, _ = generate.build()
    forged = cases["SYN-CASE-FORGED"]["documents"][-1]
    assert forged in docs and forged not in index


def test_every_case_records_its_provenance():
    _, _, cases, _ = generate.build()
    for c in cases.values():
        if c["label"] == "needs review":
            assert c["provenance"]["parent"] and c["provenance"]["change"]["type"]


# Label consistency: honest citations approve the clean cases and refuse every other case
def gold_citations(case, docs, criteria):
    cites = []
    for crit in criteria:
        rule = crit["evidence_rule"]
        for doc_id in case["documents"]:
            d = docs[doc_id]
            if d["kind"] not in rule["doc_kinds"]:
                continue
            for n, line in enumerate(d["pages"][0], start=1):
                if re.search(rule["pattern"], line):
                    cites.append({"criterion_id": crit["id"], "doc_id": doc_id, "page": 1, "line": n})
                    break
    return cites


@pytest.mark.parametrize("case_id", ["SYN-CASE-CLEAN-1", "SYN-CASE-CLEAN-2", "SYN-CASE-CF-1", "SYN-CASE-CF-2",
                                     "SYN-CASE-WRONG-PATIENT", "SYN-CASE-FORGED"])
def test_labels_agree_with_the_rules_on_gold_citations(case_id):
    docs, index, cases, _ = generate.build()
    case = cases[case_id]
    criteria = load(COMPILED)["criteria"]
    chart = {"docs": docs, "index": index}
    packet = {"packet_id": "P", "case_id": case_id,
              "findings": checks.findings_from_citations(gold_citations(case, docs, criteria), docs)}
    request = {"case_id": case_id, "patient_id": case["patient_id"], "payer_id": case["payer_id"],
               "cpt_code": case["cpt_code"]}
    verdict = checks.recompute(packet, request, criteria, chart)
    assert verdict.approvable == (case["label"] == "approve"), verdict.failures or verdict.gaps
