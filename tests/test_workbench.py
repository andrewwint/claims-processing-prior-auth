"""Beat 5 workbench: the packet view's labels, the packet/run match, and tool results."""

from prior_auth import stores
from prior_auth.checks import canonical_hash
from scripts import workbench as wb

CRITERIA = stores.criteria("SYN-PAYER-LARKSPUR", "63030")
IDS = [c["id"] for c in CRITERIA]


def packet(run_id="R1"):
    findings = [{"criterion_id": i, "doc_id": "SYN-DOC", "page": 1, "line": n, "value": f"evidence {i}"}
                for n, i in enumerate(IDS, start=1)]
    return {"packet_id": "PKT-X", "case_id": "X", "run_id": run_id, "findings": findings}


def test_gap_is_not_found_and_others_met_with_source():
    rows = wb.criterion_rows(CRITERIA, {"reason": "criteria not met", "gaps": [IDS[-1]]}, packet())
    assert [r["status"] for r in rows] == ["Met"] * (len(IDS) - 1) + ["Not found"]
    assert rows[0]["source"] == "SYN-DOC, page 1, line 1"


def test_extraction_failed_is_labeled_with_stop_reason_not_not_found():
    rows = wb.criterion_rows(CRITERIA, {"reason": "extraction failed: stop reason max_tokens", "gaps": []}, None)
    assert {r["status"] for r in rows} == {"Extraction failed"}
    assert rows[0]["detail"] == "stop reason: max_tokens"


def test_no_verified_policy_is_labeled():
    rows = wb.criterion_rows(CRITERIA, {"reason": "no verified policy", "gaps": []}, None)
    assert {r["status"] for r in rows} == {"No verified policy"}


def test_packet_must_be_the_one_this_run_recommended():
    p = packet("R1")
    rec = {"packet_hash": canonical_hash(p)}
    assert wb.packet_matches(p, rec, "R1")
    assert not wb.packet_matches(p, rec, "R2")
    assert not wb.packet_matches(p | {"model_summary": "edited"}, rec, "R1")
    assert not wb.packet_matches(None, rec, "R1")


def test_tool_result_parses_success_and_refusals():
    ok = {"http_status": 200, "body": {"result": {"content": [{"type": "text", "text": '{"recorded": true}'}]}}}
    assert wb.tool_result(ok) == {"recorded": True}
    denied = {"http_status": 200, "body": {"error": {"code": -32002, "message": "Tool call denied"}}}
    assert wb.tool_result(denied) == {"recorded": False, "reasons": ["Tool call denied"]}
    assert wb.tool_result({"http_status": 403, "body": "forbidden"})["recorded"] is False


def test_bound_to_loopback_only():
    assert wb.HOST == "127.0.0.1"


def test_a_routed_run_shows_its_evidence_from_the_recommendation_record():
    """Routed runs store no packet; the checklist comes from the recommendation's citations,
    with values read from the trusted chart (the model's values are never used)."""
    from prior_auth.gold import gold_citations
    rec = {"citations": gold_citations("SYN-CASE-CF-1")}
    rebuilt = wb.findings_from_recommendation(rec, "SYN-CASE-CF-1")
    rows = wb.criterion_rows(CRITERIA, {"reason": "criteria not met", "gaps": ["C3"]}, rebuilt)
    assert [r["status"] for r in rows] == ["Met", "Met", "Not found"]
    assert rows[0]["source"].startswith("SYN-DOC-103-PT, page 1, line ") and "visits" in rows[0]["detail"]
    assert wb.findings_from_recommendation(None, "SYN-CASE-CF-1") is None
