"""Checks that decide whether two survey numbers may be compared. Code, not a model, decides.

Each check returns data, never prose: pairs with their distances and ratios, a factor interval,
a verdict with the reason it was reached. The hybrid agent's guard is built from these, and every
one is tested against a case whose answer is known from outside this file.

- duplicates: the same sample held under two studies (same day, a short distance apart)
- window_factor / window_verdict: what a count in one size window means in another
- unit_verdict: whether two units can be compared at all
- colocated: records from different studies near each other in space and time
- series_change, pooled_periods: whether a change over time survives inside one series
- completeness: how often each field is missing, per dataset
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[0] / "p2"))
import extension as ext  # noqa: E402

EARTH_KM = 6371.0088
#: The power-law slopes a window conversion is allowed to assume (PREREG P3's band, widened to
#: the median of the LOD-filtered MPsizeBase fits on one side and the Weser fit's lower half).
ALPHA_RANGE = (1.3, 2.2)
#: A conversion factor wider than this spread (hi / lo) carries no usable number.
MAX_FACTOR_SPREAD = 10.0


@dataclass(frozen=True)
class Verdict:
    decision: str  # allow | caveat | refuse
    reason: str
    detail: tuple = ()


def _xyz(lat, lon) -> np.ndarray:
    la, lo = np.radians(np.asarray(lat, float)), np.radians(np.asarray(lon, float))
    return np.column_stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])


def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * EARTH_KM * np.arcsin(np.sqrt(a))


def _pairs_within(t: pd.DataFrame, km: float) -> pd.DataFrame:
    """Index pairs (i < j) of records with coordinates closer than `km`, from different studies."""
    t = t[t.lat.notna() & t.lon.notna()]
    if len(t) < 2:
        return pd.DataFrame(columns=["i", "j", "km"])
    chord = 2 * np.sin(km / (2 * EARTH_KM)) * 1.0001
    p = cKDTree(_xyz(t.lat, t.lon)).query_pairs(chord, output_type="ndarray")
    if len(p) == 0:
        return pd.DataFrame(columns=["i", "j", "km"])
    i, j = t.index.to_numpy()[p[:, 0]], t.index.to_numpy()[p[:, 1]]
    keep = t.loc[i, "study"].to_numpy() != t.loc[j, "study"].to_numpy()
    i, j = i[keep], j[keep]
    d = haversine(t.loc[i, "lat"].to_numpy(), t.loc[i, "lon"].to_numpy(),
                  t.loc[j, "lat"].to_numpy(), t.loc[j, "lon"].to_numpy())  # fmt: skip
    return pd.DataFrame({"i": i, "j": j, "km": d})


def duplicates(t: pd.DataFrame, km: float = 2.0, min_shared: int = 10) -> pd.DataFrame:
    """Study pairs that share samples: records on the same day, within `km`, in one setting.

    One row per study pair with at least `min_shared` such records on each side, the median
    distance between them, and the median value ratio where both are positive. A pair of studies
    that hold the same tows is one survey counted twice, whatever the values say.
    """
    rows = []
    for setting, g in t[t.date.notna()].groupby("setting"):
        p = _pairs_within(g, km)
        if p.empty:
            continue
        same_day = g.loc[p.i, "date"].to_numpy() == g.loc[p.j, "date"].to_numpy()
        p = p[same_day]
        if p.empty:
            continue
        a, b = g.loc[p.i, "study"].to_numpy(), g.loc[p.j, "study"].to_numpy()
        swap = a > b
        p = p.assign(
            study_a=np.where(swap, b, a),
            study_b=np.where(swap, a, b),
            rec_a=np.where(swap, p.j, p.i),
            rec_b=np.where(swap, p.i, p.j),
        )
        for (sa, sb), q in p.groupby(["study_a", "study_b"]):
            n_a, n_b = q.rec_a.nunique(), q.rec_b.nunique()
            if min(n_a, n_b) < min_shared:
                continue
            va, vb = t.loc[q.rec_a, "value"].to_numpy(), t.loc[q.rec_b, "value"].to_numpy()
            both = (va > 0) & (vb > 0)
            rows.append(
                {
                    "setting": setting,
                    "study_a": sa,
                    "study_b": sb,
                    "records_a": int(n_a),
                    "records_b": int(n_b),
                    "median_km": float(np.median(q.km)),
                    "median_ratio_a_over_b": float(np.median(va[both] / vb[both]))
                    if both.any()
                    else np.nan,
                }
            )
    return pd.DataFrame(rows)


def window_factor(
    src: tuple[float, float], dst: tuple[float, float], alphas: tuple[float, float] = ALPHA_RANGE
) -> tuple[float, float]:
    """The factor that turns a count in size window `src` into one in `dst`, over the α range.

    For n(d) ∝ d^−α the count in a window is ∫ d^−α, so the factor is the ratio of the two
    integrals (`extension.window_ratio`). It is monotone in α, so the two ends bound it.
    """
    f = [ext.window_ratio(a, dst, src) for a in alphas]
    return (min(f), max(f))


def window_verdict(a: tuple[float, float] | None, b: tuple[float, float] | None) -> Verdict:
    if a is None or b is None or any(pd.isna(x) for x in (*(a or ()), *(b or ()))):
        return Verdict("refuse", "window_unreported")
    if tuple(map(float, a)) == tuple(map(float, b)):
        return Verdict("allow", "same_window")
    lo, hi = window_factor(a, b)
    if hi / lo > MAX_FACTOR_SPREAD:
        return Verdict("refuse", "window_factor_too_uncertain", (round(lo, 3), round(hi, 3)))
    return Verdict("caveat", "different_window", (round(lo, 3), round(hi, 3)))


def unit_verdict(a: str | None, b: str | None) -> Verdict:
    if not a or not b or pd.isna(a) or pd.isna(b):
        return Verdict("refuse", "unit_unreported")
    if a.strip() == b.strip():
        return Verdict("allow", "same_unit")
    return Verdict("refuse", "different_unit", (a, b))


def colocated(
    t: pd.DataFrame, km: float = 50.0, days: int | None = 365, same_method: bool = True
) -> pd.DataFrame:
    """Record pairs from different studies within `km` and `days`, one setting, both positive."""
    out = []
    for setting, g in t[t.lat.notna()].groupby("setting"):
        p = _pairs_within(g, km)
        if p.empty:
            continue
        if days is not None:
            da = pd.to_datetime(g.loc[p.i, "date"]).to_numpy()
            db = pd.to_datetime(g.loc[p.j, "date"]).to_numpy()
            p = p[np.abs((da - db) / np.timedelta64(1, "D")) <= days]
        if same_method:
            p = p[g.loc[p.i, "method"].to_numpy() == g.loc[p.j, "method"].to_numpy()]
        va, vb = g.loc[p.i, "value"].to_numpy(), g.loc[p.j, "value"].to_numpy()
        p = p[(va > 0) & (vb > 0)]
        out.append(
            p.assign(
                setting=setting,
                log10_ratio=np.abs(
                    np.log10(g.loc[p.i, "value"].to_numpy() / g.loc[p.j, "value"].to_numpy())
                ),
            )
        )
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def series_change(t: pd.DataFrame, key: str = "study") -> pd.DataFrame:
    """Per series: the mean over the last third of its sampled years over the first third.

    A third is taken over the distinct years the series sampled, rounded up, so a series of 8
    years compares its first 3 with its last 3. Zeros count: a tow that caught nothing is data.
    """
    rows = []
    for s, g in t[t.year.notna() & t.value.notna()].groupby(key):
        years = np.sort(g.year.unique())
        if len(years) < 2:
            continue
        k = int(np.ceil(len(years) / 3))
        first, last = g[g.year.isin(years[:k])], g[g.year.isin(years[-k:])]
        rows.append(
            {
                key: s,
                "years": len(years),
                "year_first": int(years[0]),
                "year_last": int(years[-1]),
                "records": len(g),
                "mean_first": float(first.value.mean()),
                "mean_last": float(last.value.mean()),
                "ratio_last_over_first": float(last.value.mean() / first.value.mean())
                if first.value.mean() > 0
                else np.nan,
            }
        )
    return pd.DataFrame(rows)


def pooled_periods(t: pd.DataFrame, width: int = 5) -> pd.DataFrame:
    """Period medians two ways: one value per record, and one value per study (its median)."""
    t = t[t.year.notna() & t.value.notna()].assign(period=lambda d: (d.year // width) * width)
    per_study = t.groupby(["period", "study"]).value.median().reset_index()
    a = t.groupby("period").agg(records=("value", "size"), studies=("study", "nunique"),
                                median_per_record=("value", "median"))  # fmt: skip
    b = per_study.groupby("period").value.median().rename("median_per_study")
    return a.join(b).reset_index()


def completeness(t: pd.DataFrame, fields=("lat", "date", "year", "size_min_um", "method", "study")):
    """Share of records missing each field, per dataset. Absence is a finding, not noise."""
    return t.groupby("dataset")[list(fields)].agg(lambda s: float(s.isna().mean())).round(4)
