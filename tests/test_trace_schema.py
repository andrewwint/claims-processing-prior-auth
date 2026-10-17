"""L1: the recorded trace of a deployed run holds the case ID, the steps, the model ID, token
counts, latency, the stop reason and the content hash; and no chart text."""

import json
from pathlib import Path

from scripts.canary_scan import needles

TRACE = Path(__file__).resolve().parent.parent / "evidence/2026-10-16/trace-20261017T001220Z-7da8444a.json"


def spans():
    return json.loads(TRACE.read_text())["spans"]


def test_the_root_span_carries_the_case_run_and_recommendation_hash():
    root = next(s for s in spans() if s["name"] == "POST /invocations")
    assert root["values"]["pa.case_id"] == "SYN-CASE-CF-1" and root["values"]["pa.run_id"]
    assert len(root["values"]["pa.recommendation_record_sha256"]) == 64 and root["seconds"] > 0


def test_model_calls_carry_model_tokens_stop_reason_and_latency():
    chats = [s for s in spans() if "gen_ai.request.model" in s["values"] and s["name"].startswith("chat")]
    assert chats
    for s in chats:
        v = s["values"]
        assert v["gen_ai.request.model"] == "amazon.nova-pro-v1:0"
        assert v.get("gen_ai.usage.input_tokens", 0) > 0
        assert v.get("gen_ai.usage.completion_tokens", v.get("gen_ai.usage.output_tokens", 0)) > 0
        assert s["seconds"] > 0  # latency: every span's duration
    assert any("gen_ai.server.request.duration" in s["values"] for s in chats)
    assert any("gen_ai.response.finish_reasons" in s["values"] for s in spans())


def test_each_step_is_its_own_span():
    names = {s["name"] for s in spans()}
    for step in ("AgentTools___check_eligibility", "AgentTools___fetch_policy_criteria",
                 "AgentTools___extract_clinical_evidence", "AgentTools___route_to_reviewer"):
        assert any(step[:20] in n for n in names), step
    assert "S3.PutObject" in names


def test_the_recorded_trace_holds_no_chart_text():
    text = TRACE.read_text()
    assert [origin for needle, origin in needles().items() if needle in text] == []
