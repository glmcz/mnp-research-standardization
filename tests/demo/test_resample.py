"""FINDINGS E2e is unreproducible as committed - neither implementation survived. These tests
rebuild it from `mnp.demo.resample` and pin it against the published table, the groupby trap
that made the pandas attempt wrong, and one hand-computable synthetic case.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mnp import config
from mnp.demo.resample import METRICS, SEED, estimates, leave_one_out

PUBLISHED = {
    # metric: (per_row_pct, per_paper_pct, icc, n_eff)
    "medium_reported": (83.2, 72.1, 0.84, 560),
    "ionic_strength_reported": (14.2, 8.7, 0.83, 567),
    "pH_reported": (21.3, 16.8, 0.78, 588),
    "temperature_reported": (28.0, 20.9, 0.94, 517),
    "instrument_reported": (88.8, 81.0, 0.94, 517),
    "conditions_complete": (3.3, 2.3, 0.80, 577),
}


@pytest.fixture(scope="module")
def table() -> pd.DataFrame:
    return pd.read_csv(config.OUT_TABLES / "d1_zeta_table.csv")


@pytest.fixture(scope="module")
def results(table: pd.DataFrame):
    return {est.metric: est for est in estimates(table)}


def test_reproduces_published_e2e_table(results):
    for metric, (row_pct, paper_pct, icc, n_eff) in PUBLISHED.items():
        est = results[metric]
        assert est.per_row * 100 == pytest.approx(row_pct, abs=0.1), metric
        assert est.per_paper * 100 == pytest.approx(paper_pct, abs=0.1), metric
        assert est.icc == pytest.approx(icc, abs=0.01), metric
        assert est.n_eff == pytest.approx(n_eff, abs=2), metric


def test_deff_is_internally_consistent(results):
    """DEFF is derived, not independently fitted - n/DEFF must equal n_eff for every metric."""
    for est in results.values():
        assert est.n_eff == pytest.approx(est.n / est.deff, rel=1e-9)
        assert est.deff > 1.0


def test_groupby_trap_is_narrower_than_correct_bootstrap(table):
    """The pandas implementation FINDINGS caught: resample papers, concat rows, groupby pmcid,
    mean. A paper drawn twice collapses back into one group, so the replacement is silently
    cancelled and the interval comes out too narrow. Reproduced here for real, not simulated.
    """
    metric = "medium_reported"
    papers = np.sort(table["pmcid"].unique())
    k = len(papers)
    prop_by_paper = table.groupby("pmcid")[metric].mean().reindex(papers).to_numpy()

    rng = np.random.default_rng(SEED)
    trap_b = 2000
    draws = rng.integers(0, k, size=(trap_b, k))

    # correct: average the drawn papers' own proportions directly - a paper drawn twice counts
    # twice.
    correct_boot = prop_by_paper[draws].mean(axis=1)
    lo, hi = np.percentile(correct_boot, [2.5, 97.5])
    correct_hw = (hi - lo) / 2

    # trap: concat the drawn papers' rows into a frame, then groupby("pmcid").mean() - a
    # duplicate draw of the same paper lands in the same group and is averaged away.
    trap_boot = np.empty(trap_b)
    for i in range(trap_b):
        drawn = draws[i]
        frame = pd.DataFrame({"pmcid": papers[drawn], "v": prop_by_paper[drawn]})
        trap_boot[i] = frame.groupby("pmcid")["v"].mean().mean()
    lo_t, hi_t = np.percentile(trap_boot, [2.5, 97.5])
    trap_hw = (hi_t - lo_t) / 2

    assert trap_hw < correct_hw


def test_deterministic_across_runs(table):
    first = {est.metric: (est.row_ci, est.paper_ci) for est in estimates(table)}
    second = {est.metric: (est.row_ci, est.paper_ci) for est in estimates(table)}
    assert first == second


def test_cluster_interval_wider_than_naive_for_every_metric(results):
    for metric, est in results.items():
        assert est.row_half_width > est.naive_half_width, metric
        assert est.paper_half_width > est.naive_half_width, metric


def test_temperature_half_width_near_published(results):
    """FINDINGS: naive +-2.0 pp, cluster +-8.4 pp for temperature. This is the metric it names
    explicitly as the worst case for trusting the naive interval.
    """
    temp = results["temperature_reported"]
    assert temp.naive_half_width * 100 == pytest.approx(2.0, abs=0.3)
    assert temp.row_half_width * 100 == pytest.approx(8.4, abs=1.5)


def test_leave_one_out_moves_per_row_more_than_per_paper(table):
    """PMC8719689 is the corona case - one of the largest single papers in the corpus. Pulling
    it out should move the per-row headline (weighted by its row count) more than the
    per-paper headline (weighted 1/491 like everyone else).
    """
    pmcid = "PMC8719689"
    assert (table["pmcid"] == pmcid).sum() > 30  # a genuinely large paper, not a typical one

    results = {r.metric: r for r in leave_one_out(table, pmcid)}
    medium = results["medium_reported"]
    row_move = abs(medium.per_row_full - medium.per_row_without)
    paper_move = abs(medium.per_paper_full - medium.per_paper_without)
    assert row_move > paper_move


def test_leave_one_out_unknown_pmcid_raises(table):
    with pytest.raises(KeyError):
        leave_one_out(table, "PMC0000000")


def test_synthetic_table_hand_computable_icc():
    """3 papers, sizes 2/3/1, each paper internally unanimous (0 within-cluster variance) so
    ICC = 1 exactly and DEFF collapses to m0 - by hand: N=6, k=3, n_i=[2,3,1],
    m0 = (6 - (4+9+1)/6) / 2 = (6 - 14/6) / 2 = 11/6, DEFF = 11/6, n_eff = 6 / (11/6) = 36/11.
    """
    synthetic = pd.DataFrame(
        {
            "pmcid": ["A", "A", "B", "B", "B", "C"],
            "medium_reported": [True, True, False, False, False, True],
            "ionic_strength_reported": [True, True, False, False, False, True],
            "pH_reported": [True, True, False, False, False, True],
            "temperature_reported": [True, True, False, False, False, True],
            "instrument_reported": [True, True, False, False, False, True],
            "conditions_complete": [True, True, False, False, False, True],
        }
    )
    for est in estimates(synthetic):
        assert est.icc == pytest.approx(1.0)
        assert est.deff == pytest.approx(11 / 6)
        assert est.n_eff == pytest.approx(36 / 11)
        assert est.per_row == pytest.approx(3 / 6)
        assert est.per_paper == pytest.approx((1 + 0 + 1) / 3)


def test_estimates_covers_all_six_metrics(table):
    metrics_seen = {est.metric for est in estimates(table)}
    assert metrics_seen == set(METRICS)
    assert len(METRICS) == 6
