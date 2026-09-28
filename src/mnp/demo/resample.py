"""Rebuilds FINDINGS E2e: the six reporting-completeness metrics are computed per row, but rows
cluster by paper (median 2, up to 90 per paper), so 1 890 is not the sample size. Neither
implementation that produced the published table was committed - one of the two disagreed with
itself, because it resampled papers, concatenated their rows, and called `groupby("pmcid")`,
which silently merges a paper drawn twice back into one group and cancels the replacement. This
module resamples paper *indices* and never regroups by the cluster key afterward.

ICC comes from a one-way random-effects ANOVA with unbalanced cluster sizes; DEFF and n_eff
follow from it. The naive binomial interval and the cluster-bootstrap interval are computed for
every metric so the two can be compared directly, per row and per paper.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import norm

from mnp import config

METRICS: tuple[str, ...] = (
    "medium_reported",
    "ionic_strength_reported",
    "pH_reported",
    "temperature_reported",
    "instrument_reported",
    "conditions_complete",
)

B = 10_000
SEED = 20260921

_Z95 = norm.ppf(0.975)  # 95% CI critical value; the SE alone is half of FINDINGS' reported widths


@dataclass(frozen=True)
class MetricEstimate:
    """One metric's point estimates, clustering diagnostics, and both interval styles."""

    metric: str
    n: int
    k: int
    per_row: float
    per_paper: float
    icc: float
    deff: float
    n_eff: float
    naive_half_width: float
    row_ci: tuple[float, float]
    paper_ci: tuple[float, float]

    @property
    def row_half_width(self) -> float:
        lo, hi = self.row_ci
        return (hi - lo) / 2

    @property
    def paper_half_width(self) -> float:
        lo, hi = self.paper_ci
        return (hi - lo) / 2


@dataclass(frozen=True)
class LeaveOneOut:
    """One metric's per-row and per-paper value, with and without one paper's rows."""

    metric: str
    pmcid: str
    per_row_full: float
    per_row_without: float
    per_paper_full: float
    per_paper_without: float


def load_table() -> pd.DataFrame:
    """The D1 zeta table: 1 row per measurement, `pmcid` per paper."""
    return pd.read_csv(config.OUT_TABLES / "d1_zeta_table.csv")


def _cluster_arrays(table: pd.DataFrame, metric: str) -> tuple[np.ndarray, np.ndarray]:
    """(n_i, succ_i) per paper, sorted by pmcid so every caller sees the same ordering."""
    grouped = table.groupby("pmcid")[metric].agg(["size", "sum"]).sort_index()
    return grouped["size"].to_numpy(dtype=float), grouped["sum"].to_numpy(dtype=float)


@dataclass(frozen=True)
class Anova:
    """Every intermediate of the one-way random-effects ANOVA behind ICC, so the result can be
    recomputed by hand from the per-paper counts and checked term by term."""

    n: float
    k: int
    sum_n_squared: float
    grand_mean: float
    ss_between: float
    ss_within: float
    ms_between: float
    ms_within: float
    m0: float
    icc: float
    deff: float


def anova(n_i: np.ndarray, succ_i: np.ndarray) -> Anova:
    """One-way random-effects ANOVA: ICC, the unbalanced adjustment m0, and DEFF.

    Binary outcomes make the within-cluster sum of squares collapse to a closed form -
    `n_i * p_i * (1 - p_i)`, the Bernoulli variance identity - so no per-row pass is needed to
    get MS_within. DEFF = 1 + (m0 - 1) * ICC, and n_eff follows outside this function.
    """
    n = n_i.sum()
    k = len(n_i)
    p_i = succ_i / n_i
    grand_mean = succ_i.sum() / n
    ss_between = (n_i * (p_i - grand_mean) ** 2).sum()
    ss_within = (n_i * p_i * (1 - p_i)).sum()
    ms_between = ss_between / (k - 1)
    ms_within = ss_within / (n - k)
    sum_n_squared = (n_i**2).sum()
    m0 = (n - sum_n_squared / n) / (k - 1)
    denom = ms_between + (m0 - 1) * ms_within
    icc = 0.0 if denom == 0 else (ms_between - ms_within) / denom
    deff = 1 + (m0 - 1) * icc
    # numpy scalars, exactly as `estimates` has always received them: np.float64 is a float.
    return Anova(
        n=n,
        k=k,
        sum_n_squared=sum_n_squared,
        grand_mean=grand_mean,
        ss_between=ss_between,
        ss_within=ss_within,
        ms_between=ms_between,
        ms_within=ms_within,
        m0=m0,
        icc=icc,
        deff=deff,
    )


def anova_for(table: pd.DataFrame, metric: str) -> Anova:
    """`anova` on one metric of the table, clustered by paper in pmcid order."""
    n_i, succ_i = _cluster_arrays(table, metric)
    return anova(n_i, succ_i)


def _icc_and_deff(n_i: np.ndarray, succ_i: np.ndarray) -> tuple[float, float, float]:
    result = anova(n_i, succ_i)
    return result.icc, result.m0, result.deff


def _naive_half_width(p: float, n: int) -> float:
    """95% binomial half-width: z * sqrt(p(1-p)/n). FINDINGS' "sqrt(p(1-p)/N)" names the
    standard error; the number it actually reports (+-2.0 pp for temperature) is that SE times
    the z=1.96 critical value, so this multiplies by it rather than reporting the bare SE.
    """
    return _Z95 * math.sqrt(p * (1 - p) / n)


def _bootstrap_cis(
    n_i: np.ndarray, succ_i: np.ndarray, draws: np.ndarray
) -> tuple[tuple[float, float], tuple[float, float]]:
    """95% percentile intervals from B pre-drawn (B, k) paper-index resamples.

    Per row: sum of successes of the drawn papers / sum of their rows - a paper drawn twice
    contributes its rows twice. Per paper: the mean of the drawn papers' own proportions - same
    rule, a repeat draw counts twice in the average. Neither step regroups by pmcid.
    """
    drawn_n = n_i[draws]
    drawn_succ = succ_i[draws]
    per_row_boot = drawn_succ.sum(axis=1) / drawn_n.sum(axis=1)
    per_paper_boot = (drawn_succ / drawn_n).mean(axis=1)
    row_lo, row_hi = np.percentile(per_row_boot, [2.5, 97.5])
    paper_lo, paper_hi = np.percentile(per_paper_boot, [2.5, 97.5])
    return (float(row_lo), float(row_hi)), (float(paper_lo), float(paper_hi))


def estimates(table: pd.DataFrame) -> list[MetricEstimate]:
    """All six metrics: point estimates, ICC/DEFF/n_eff, and 95% intervals (naive + cluster).

    One shared set of B paper-index draws is generated once and reused for every metric, the
    way a single cluster bootstrap run would be in practice - paper i is the same draw for
    medium_reported as it is for conditions_complete.
    """
    n_i = table.groupby("pmcid").size().sort_index().to_numpy(dtype=float)
    n = int(n_i.sum())
    k = len(n_i)
    rng = np.random.default_rng(SEED)
    draws = rng.integers(0, k, size=(B, k))

    results = []
    for metric in METRICS:
        _, succ_i = _cluster_arrays(table, metric)
        per_row = float(table[metric].mean())
        per_paper = float((succ_i / n_i).mean())
        icc, _m0, deff = _icc_and_deff(n_i, succ_i)
        n_eff = n / deff
        naive_hw = _naive_half_width(per_row, n)
        row_ci, paper_ci = _bootstrap_cis(n_i, succ_i, draws)
        results.append(
            MetricEstimate(
                metric=metric,
                n=n,
                k=k,
                per_row=per_row,
                per_paper=per_paper,
                icc=icc,
                deff=deff,
                n_eff=n_eff,
                naive_half_width=naive_hw,
                row_ci=row_ci,
                paper_ci=paper_ci,
            )
        )
    return results


def leave_one_out(table: pd.DataFrame, pmcid: str) -> list[LeaveOneOut]:
    """Per metric, the per-row and per-paper value with and without one paper's rows.

    No resampling here, so the groupby trap doesn't apply - this groups the real table once
    each way, not a bootstrap replicate.
    """
    without = table[table["pmcid"] != pmcid]
    if len(without) == len(table):
        raise KeyError(f"{pmcid!r} has no rows in this table")

    results = []
    for metric in METRICS:
        results.append(
            LeaveOneOut(
                metric=metric,
                pmcid=pmcid,
                per_row_full=float(table[metric].mean()),
                per_row_without=float(without[metric].mean()),
                per_paper_full=float(table.groupby("pmcid")[metric].mean().mean()),
                per_paper_without=float(without.groupby("pmcid")[metric].mean().mean()),
            )
        )
    return results
