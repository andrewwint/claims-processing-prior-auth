"""M1, M3, M4, M6, M8: the harness report's arithmetic, wording, scoring and regeneration."""

import json

import pytest

from evaluation import report


def trial(case="SYN-CASE-CF-1", label="needs review", outcome="routed", model="amazon.nova-pro-v1:0", **kw):
    return {"model_id": model, "case_id": case, "label": label, "trial": 1, "outcome": outcome, "reason": None,
            "gaps": [], "stop_reason": "end_turn", "sampling": {"maxTokens": 2048, "temperature": 0},
            "usage": {"input_tokens": 10000, "output_tokens": 1000}, "seconds": 10.0} | kw


def test_rule_of_three_at_zero_and_clopper_pearson_above():
    assert report.upper_bound(0, 120) == pytest.approx(0.025)
    assert report.upper_bound(0, 12) == pytest.approx(0.25)
    # Exact one-sided 95% Clopper-Pearson upper limit for 1 of 12.
    assert report.upper_bound(1, 12) == pytest.approx(0.3387, abs=1e-3)
    assert report.binom_cdf(1, 12, report.upper_bound(1, 12)) == pytest.approx(0.05, abs=1e-6)


def test_false_auto_approval_counts_only_needs_review_cases():
    s = report.summarize([trial(outcome="approved"), trial(case="SYN-CASE-CLEAN-1", label="approve", outcome="approved"),
                          trial(), trial(outcome="operator_alert")])
    assert (s["false_auto"], s["n_review"], s["auto"], s["n"], s["excluded"]) == (1, 2, 2, 3, 1)


def test_truncation_is_a_counted_failure():
    s = report.summarize([trial(stop_reason="max_tokens", outcome="routed", reason="extraction failed: stop reason max_tokens")])
    assert s["n"] == 1 and s["truncated"] == 1 and s["false_auto"] == 0


def test_cost_uses_the_preregistered_prices():
    assert report.cost(trial()) == pytest.approx(10 * 0.0008 + 1 * 0.0032)
    assert report.cost(trial(model="us.anthropic.claude-sonnet-4-6")) == pytest.approx(10 * 0.0033 + 1 * 0.0165)


def test_report_states_rates_as_preregistered_and_lists_every_trial():
    trials = [trial(), trial(case="SYN-CASE-CLEAN-1", label="approve", outcome="approved")]
    text = report.render(trials)
    assert report.LABEL in text
    assert "0 of 1 (95% upper bound 100.0%)" in text
    assert "1 of 2 (50.0%)" in text
    assert text.count("| `amazon.nova-pro-v1:0` | SYN-CASE") == 2
    for banned in ("better", "best", "outperform", "safe"):
        assert banned not in text.lower()


def test_report_regenerates_byte_identically(tmp_path):
    trials = [trial(), trial(outcome="approved", seconds=3.0)]
    path = tmp_path / "trials.jsonl"
    path.write_text("".join(json.dumps(t) + "\n" for t in trials))
    assert report.render(report.load(path)) == report.render(report.load(path))


def test_committed_report_matches_the_committed_trials():
    if not report.TRIALS.exists():
        pytest.skip("no harness run recorded yet")
    assert report.REPORT.read_text() == report.render(report.load())
