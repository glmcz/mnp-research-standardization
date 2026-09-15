"""Each stage of the pipeline is measured on its own, against its own ground truth.

Until now only two stages were scored: the model's reading (against the gold set) and the
aggregate (against the published tables). A parser or coercion defect could only show up as a
worse end-to-end number, with nothing to say which stage caused it — and a stage nobody
measures is a stage nobody knows is broken.

The rule that matters more than any threshold: a stage with no ground truth scores
**not measured**. Never 0.00, never 1.00 — both are claims, and neither is supported.
"""

import pytest

from mnp.eval import stages


def test_every_stage_declares_where_its_truth_comes_from():
    for stage in stages.STAGES:
        assert stage.name
        assert stage.ground_truth, f"{stage.name} claims no ground truth"
        assert stage.metric, f"{stage.name} has no metric"


def test_the_stages_are_the_pipeline_in_order():
    assert [s.name for s in stages.STAGES] == [
        "parse",
        "scan",
        "read",
        "coerce",
        "verify",
        "aggregate",
    ]


def test_a_stage_with_no_ground_truth_is_not_measured_rather_than_perfect():
    result = stages.Result(stage="scan", metric="recall", value=None, n=0, threshold=0.9)
    assert result.status == "not measured"
    assert "not measured" in result.line()


def test_a_measured_stage_is_judged_against_its_threshold():
    assert stages.Result("scan", "recall", 0.95, 20, 0.90).status == "pass"
    assert stages.Result("scan", "recall", 0.80, 20, 0.90).status == "fail"


def test_a_measured_stage_with_no_threshold_reports_rather_than_judges():
    """Some numbers are worth knowing before anyone knows what good looks like."""
    assert stages.Result("read", "row P", 0.73, 108, None).status == "reported"


def test_zero_out_of_zero_is_not_a_score():
    assert stages.Result("coerce", "accuracy", 0.0, 0, 1.0).status == "not measured"


def test_verify_must_catch_every_adversarial_row():
    """Each case is a defect that reached production once; the gate is all of them, not most."""
    result = stages.measure_verify()
    assert result.n >= 5, "too few adversarial cases to mean anything"
    assert result.threshold == 1.0
    assert result.value == 1.0, f"verifier missed: {result.detail}"


def test_coerce_covers_every_ratified_rule():
    result = stages.measure_coerce()
    rules = {case["rule"] for case in stages.coerce_cases()}
    assert {"composition_is_ionic_strength", "incubation_is_not_measurement"} <= rules
    assert result.value == 1.0, result.detail


def test_scan_recall_is_measured_against_the_gold_printed_values():
    result = stages.measure_scan()
    if result.value is None:
        pytest.skip("no corpus parsed here")
    assert 0.0 <= result.value <= 1.0
    assert result.n > 0


def test_the_summary_names_every_stage_and_its_status():
    text = stages.summary(stages.run_all(fast=True))
    for stage in stages.STAGES:
        assert stage.name in text
    assert "not measured" in text or "pass" in text
