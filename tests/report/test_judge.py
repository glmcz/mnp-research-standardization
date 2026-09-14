"""LLM-as-judge, evaluated as an inter-rater reliability problem.

A judge that agrees with the ground truth 90% of the time sounds good until you notice the
labels are 85% one class — raw agreement is not evidence. Cohen's kappa corrects for chance
(Cohen 1960); the LLM-judge literature adds that a judge must be checked for position bias
and must be grounded in quoted evidence (Zheng et al. 2023; Liu et al. 2023, G-Eval).
"""

import pytest

from mnp.report import judge


# -- agreement metrics ---------------------------------------------------------------
def test_perfect_agreement_is_kappa_one():
    k = judge.cohen_kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"])
    assert k == pytest.approx(1.0)


def test_chance_agreement_is_kappa_zero():
    """Both raters call 'a' 50% of the time at random: raw agreement 0.5, kappa 0."""
    a = ["a", "a", "b", "b"]
    b = ["a", "b", "a", "b"]
    assert judge.raw_agreement(a, b) == pytest.approx(0.5)
    assert judge.cohen_kappa(a, b) == pytest.approx(0.0)


def test_high_raw_agreement_on_a_skewed_label_can_still_be_worthless():
    """The trap this metric exists for: 90% agreement, kappa ~0, because one label
    dominates and the judge simply always says it."""
    truth = ["yes"] * 9 + ["no"]
    always_yes = ["yes"] * 10
    assert judge.raw_agreement(truth, always_yes) == pytest.approx(0.9)
    assert judge.cohen_kappa(truth, always_yes) == pytest.approx(0.0)


def test_kappa_is_undefined_rather_than_one_when_both_raters_never_vary():
    assert judge.cohen_kappa(["a"] * 5, ["a"] * 5) is None


def test_bootstrap_gives_an_interval_that_contains_the_estimate():
    truth = ["a", "b"] * 20
    pred = ["a", "b"] * 18 + ["b", "a"] * 2
    lo, hi = judge.bootstrap_ci(truth, pred, n=200, seed=1)
    k = judge.cohen_kappa(truth, pred)
    assert lo <= k <= hi
    assert 0.0 <= lo < hi <= 1.0


# -- bias and grounding controls ----------------------------------------------------
def test_a_judge_that_flips_with_presentation_order_is_reported_as_biased():
    """Position bias (Zheng 2023): the same case, two orders, two answers."""
    forward = {"c1": "gold", "c2": "extraction"}
    reversed_ = {"c1": "extraction", "c2": "extraction"}
    r = judge.order_consistency(forward, reversed_)
    assert r["consistent"] == 1
    assert r["flipped"] == ["c1"]
    assert r["consistency"] == pytest.approx(0.5)


def test_a_verdict_whose_quote_is_not_in_the_article_is_ungrounded():
    article = "The zeta potential was -41.2 mV in 10 mM NaCl."
    assert judge.grounded("the zeta potential was -41.2 mV", article) is True
    assert judge.grounded("the zeta potential was -99 mV", article) is False
    assert judge.grounded("", article) is False


def test_ungrounded_verdicts_are_excluded_from_the_score_and_counted():
    verdicts = {
        "c1": {"verdict": "gold", "quote": "zeta was -41.2 mV"},
        "c2": {"verdict": "extraction", "quote": "invented sentence"},
    }
    articles = {"c1": "the zeta was -41.2 mV here", "c2": "nothing like it"}
    kept, dropped = judge.filter_grounded(verdicts, articles)
    assert list(kept) == ["c1"]
    assert dropped == ["c2"]


def test_abstention_is_kept_as_a_label_not_silently_dropped():
    """'The paper does not say' is a legitimate verdict and must survive to the metrics."""
    k = judge.cohen_kappa(["ambiguous", "gold"], ["ambiguous", "gold"])
    assert k == pytest.approx(1.0)


# -- the run ------------------------------------------------------------------------
def test_a_run_reports_kappa_consistency_and_grounding_together():
    cases = [
        {"case": "c1", "article": "zeta was -41.2 mV", "gold": "a", "extraction": "b"},
        {"case": "c2", "article": "zeta was -10.0 mV", "gold": "a", "extraction": "b"},
    ]

    def scripted(case, order):
        # agrees with the key, and does not flip with order
        return {"verdict": "gold correct", "quote": case["article"]}

    r = judge.run(cases, scripted, key={"c1": "gold correct", "c2": "gold correct"})
    assert r["n_scored"] == 2
    assert r["agreement"] == pytest.approx(1.0)
    assert r["order_consistency"] == pytest.approx(1.0)
    assert r["ungrounded"] == []


def test_a_run_refuses_to_report_a_score_with_no_key():
    cases = [{"case": "c1", "article": "x", "gold": "a", "extraction": "b"}]
    r = judge.run(cases, lambda c, o: {"verdict": "gold correct", "quote": "x"}, key=None)
    assert r["agreement"] is None
    assert r["kappa"] is None
    assert r["n_scored"] == 0
