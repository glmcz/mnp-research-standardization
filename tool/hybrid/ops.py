"""The hybrid agent's tools: a registry of operations, the code that runs them, and the guard.

A model never computes a number here. It names an operation and its arguments (a `Plan`); code
checks the plan against the registry, runs it over the source data and returns the value with
its provenance and the diagnostics the guard needs. The guard turns diagnostics into a verdict:
allow, caveat (with a reason from a fixed list) or refuse.
"""

from __future__ import annotations

import functools
import inspect
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, get_args, get_origin, get_type_hints

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "tool" / "survey"))
sys.path.insert(0, str(ROOT / "tool" / "p2"))
import extension as ext  # noqa: E402
import table  # noqa: E402
import validators as v  # noqa: E402

from mnp.eval.comparability import ZetaRow, comparable  # noqa: E402
from mnp.eval.query_sets import zeta_table  # noqa: E402

P2_ZETA = ROOT / "out/tables/p2_zeta_size.csv"
D1 = ROOT / "out/tables/d1_zeta_table.csv"

CAVEATS = (
    "composition_shift",  # different studies, places or methods on the two sides of a change
    "sampling_area_shift",  # one series, but it sampled elsewhere later
    "method_mix",  # different sampling methods compared
    "held_twice",  # the same samples counted under two studies
    "different_window",  # different size windows; a factor is needed
    "window_unreported",
    "different_unit",
    "liquid_dependent",  # a zeta sign or value that depends on the liquid it was measured in
    "single_paper",  # one paper supplies most of the values
    "not_comparable",  # comparability rules block the comparison
)
#: A series' first and last thirds whose tow centroids lie further apart than this sampled
#: different water.
AREA_SHIFT_KM = 300.0


@dataclass(frozen=True)
class Plan:
    op: str
    args: dict = field(default_factory=dict)

    def validate(self) -> list[str]:
        """Problems with the plan, empty if it may run. No model output is trusted unchecked."""
        if self.op not in OPS:
            return [f"unknown op {self.op!r}"]
        params = inspect.signature(OPS[self.op]).parameters
        extra = sorted(set(self.args) - set(params))
        missing = sorted(
            n for n, p in params.items() if p.default is inspect._empty and n not in self.args
        )
        hints = get_type_hints(OPS[self.op])
        bad = [
            f"{name}={value!r} is not one of {list(allowed)}"
            for name, value in self.args.items()
            if (allowed := _choices(hints.get(name))) and value not in allowed
        ]
        return [f"unknown arg {a!r}" for a in extra] + [f"missing arg {m!r}" for m in missing] + bad


def _choices(hint) -> tuple:
    """The values a Literal argument allows (inside Optional too); empty for any other type."""
    if get_origin(hint) is Literal:
        return get_args(hint)
    for inner in get_args(hint):
        if get_origin(inner) is Literal:
            return get_args(inner) + (None,)
    return ()


Dataset = Literal["ncei", "mpsed", "soil", "pangaea_weser"]
Field = Literal["lat", "date", "year", "size_min_um", "method", "study"]
Polymer = Literal["PS", "PE", "PET", "PMMA", "PP", "PVC", "PLA", "PBAT", "nylon", "other"]
Surface = Literal["amine", "carboxyl", "plain", "sulfate", "unreported"]
Condition = Literal["ionic_strength", "pH", "temperature", "medium", "instrument"]


@dataclass
class Result:
    value: Any
    n: int = 0
    provenance: list[str] = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)

    def numbers(self) -> list[float]:
        """Every number the result states, for the composer's grounding check."""
        out: list[float] = []

        def walk(x):
            if isinstance(x, bool):
                return
            if isinstance(x, int | float | np.floating | np.integer) and np.isfinite(x):
                out.append(float(x))
            elif isinstance(x, dict):
                for y in x.values():
                    walk(y)
            elif isinstance(x, list | tuple):
                for y in x:
                    walk(y)

        walk(self.value)
        walk(self.diagnostics)
        out.append(float(self.n))
        return out


# -- data --------------------------------------------------------------------------------------


@functools.cache
def survey() -> pd.DataFrame:
    return table.load()


@functools.cache
def zeta() -> pd.DataFrame:
    return pd.read_csv(P2_ZETA)


@functools.cache
def d1() -> pd.DataFrame:
    return pd.read_csv(D1, dtype=str, keep_default_na=False)


def _water() -> pd.DataFrame:
    s = survey()
    return s[(s.dataset == "ncei") & (s.setting == "Ocean water") & s.value.notna()]


def _study(t: pd.DataFrame, study: str) -> pd.DataFrame:
    """A study by DOI, or by a fragment of it (an agent may write '10.1021/es4053076')."""
    g = t[t.study == study]
    return g if len(g) else t[t.study.astype(str).str.contains(study, regex=False)]


# -- operations ---------------------------------------------------------------------------------


def period_change(
    period_from: int, period_to: int, per: Literal["record", "study"] = "record"
) -> Result:
    """NCEI ocean water: the median in five-year period `period_to` over `period_from`."""
    w = _water().assign(period=lambda d: (d.year // 5) * 5)
    a, b = w[w.period == period_from], w[w.period == period_to]
    if per == "study":
        ma, mb = (
            a.groupby("study").value.median().median(),
            b.groupby("study").value.median().median(),
        )
    else:
        ma, mb = a.value.median(), b.value.median()
    sa, sb = set(a.study), set(b.study)
    return Result(
        value=round(float(mb / ma), 1),
        n=len(a) + len(b),
        provenance=sorted(sa | sb),
        diagnostics={
            "median_from": float(ma),
            "median_to": float(mb),
            "studies_from": len(sa),
            "studies_to": len(sb),
            "studies_in_both": len(sa & sb),
        },
    )


def study_count(period: int) -> Result:
    """NCEI ocean water: how many studies sampled in the five-year period starting `period`."""
    w = _water()
    g = w[(w.year // 5) * 5 == period]
    return Result(value=int(g.study.nunique()), n=len(g), provenance=sorted(set(g.study)))


def _centroid_km(a: pd.DataFrame, b: pd.DataFrame) -> float:
    def c(g):
        xyz = v._xyz(g.lat, g.lon).mean(axis=0)
        return np.degrees(np.arctan2(xyz[2], np.hypot(xyz[0], xyz[1]))), np.degrees(
            np.arctan2(xyz[1], xyz[0])
        )

    (la1, lo1), (la2, lo2) = c(a), c(b)
    return float(v.haversine(la1, lo1, la2, lo2))


def series_trend(study: str, statistic: Literal["ratio", "spearman"] = "ratio") -> Result:
    """One NCEI series: last third of years over first (ratio) or Spearman ρ of year (spearman)."""
    g = _study(_water(), study)
    g = g[g.method == g.method.value_counts().index[0]]
    rho, p = spearmanr(g.year, g.value)
    s = v.series_change(g.assign(s=1), key="s").iloc[0]
    years = np.sort(g.year.unique())
    k = int(np.ceil(len(years) / 3))
    first, last = g[g.year.isin(years[:k])], g[g.year.isin(years[-k:])]
    return Result(
        value=round(float(rho), 3)
        if statistic == "spearman"
        else round(float(s.ratio_last_over_first), 2),
        n=len(g),
        provenance=sorted(set(g.study)),
        diagnostics={
            "ratio_last_over_first": round(float(s.ratio_last_over_first), 2),
            "spearman_rho": round(float(rho), 3),
            "p": float(p),
            "year_first": int(years[0]),
            "year_last": int(years[-1]),
            "centroid_shift_km": round(_centroid_km(first, last), 0),
        },
    )


def colocated_agreement(
    km: float = 50, days: int = 365, same_method: bool = True, region: str | None = None
) -> Result:
    """Independent NCEI ocean-water studies near each other: how far apart are their values?"""
    w = _water()
    if region:  # "Mediterranean" finds "Mediterranean Sea"
        w = w[w.region.astype(str).str.contains(region, case=False, regex=False)]
    p = v.colocated(w, km=km, days=days, same_method=same_method)
    dup = v.duplicates(survey())
    twice = {frozenset((a, b)) for a, b in zip(dup.study_a, dup.study_b, strict=True)}
    pair = [
        frozenset((a, b)) for a, b in zip(w.loc[p.i, "study"], w.loc[p.j, "study"], strict=True)
    ]
    keep = np.array([s not in twice for s in pair], dtype=bool)
    p = p[keep]
    q = np.quantile(p.log10_ratio, [0.5, 0.9])
    return Result(
        value=round(float(10 ** q[0]), 2),
        n=len(p),
        provenance=sorted({s for s, k in zip(pair, keep, strict=True) if k for s in s}),
        diagnostics={
            "p90_fold": round(float(10 ** q[1]), 1),
            "same_method": same_method,
            "excluded_held_twice": int((~keep).sum()),
        },
    )


def duplicate_pairs(setting: str | None = None) -> Result:
    """How many study pairs hold same-day samples within 2 km (at least 10 records each)."""
    d = v.duplicates(survey())
    if setting:
        d = d[d.setting == setting]
    return Result(
        value=len(d),
        n=int(d.records_a.sum() + d.records_b.sum()),
        provenance=sorted(set(d.study_a) | set(d.study_b)),
        diagnostics={"pairs": d.round(3).to_dict(orient="records")},
    )


def duplicate_check(study_a: str, study_b: str) -> Result:
    """Do two studies hold the same samples? The median value ratio a/b of shared records."""
    d = v.duplicates(survey())
    a = _study(survey(), study_a).study.iat[0]
    b = _study(survey(), study_b).study.iat[0]
    row = d[((d.study_a == a) & (d.study_b == b)) | ((d.study_a == b) & (d.study_b == a))]
    if row.empty:
        return Result(value=None, n=0, provenance=[a, b], diagnostics={"shared": 0})
    r = row.iloc[0]
    ratio = r.median_ratio_a_over_b if r.study_a == a else 1 / r.median_ratio_a_over_b
    return Result(
        value=round(float(ratio), 2),
        n=int(r.records_a + r.records_b),
        provenance=[a, b],
        diagnostics={
            "shared": int(min(r.records_a, r.records_b)),
            "median_ratio": round(float(ratio), 2),
            "median_km": round(float(r.median_km), 2),
        },
    )


def compare_windows(window_a: list[float], window_b: list[float]) -> Result:
    """May a count in size window a be compared with one in b? The factor from a to b."""
    a = tuple(window_a) if window_a else None
    b = tuple(window_b) if window_b else None
    verdict = v.window_verdict(a, b)
    return Result(
        value=list(verdict.detail) if verdict.detail else None,
        diagnostics={"verdict": verdict.decision, "reason": verdict.reason},
    )


def compare_units(unit_a: str, unit_b: str) -> Result:
    """May a value in unit a be compared with one in unit b?"""
    verdict = v.unit_verdict(unit_a, unit_b)
    return Result(value=None, diagnostics={"verdict": verdict.decision, "reason": verdict.reason})


def weser_window_ratio() -> Result:
    """The Weser stations: small-fraction count over large-fraction count, and the slope needed."""
    w, win = ext.weser()
    ratio = float(w.ratio.median())
    small, large = tuple(win["small_um"]), tuple(win["large_um"])
    return Result(
        value=round(ratio, 0),
        n=int(w.ratio.notna().sum()),
        provenance=["PANGAEA 937685", "PANGAEA 938143"],
        diagnostics={
            "predicted_at_alpha_1_6": round(ext.window_ratio(1.6, small, large), 1),
            "implied_alpha": round(ext.implied_alpha(ratio, small, large), 2),
            "window_small_um": list(small),
            "window_large_um": list(large),
        },
    )


def completeness(dataset: Dataset, field: Field) -> Result:
    """The share of a dataset's records that do not give `field`."""
    c = v.completeness(survey())
    return Result(
        value=round(float(c.loc[dataset, field]), 4), n=int((survey().dataset == dataset).sum())
    )


def zeta_sign_share(
    surface: Surface, sign: Literal["negative", "positive"], polymer: Polymer | None = None
) -> Result:
    """Of the zeta values for a surface group (optionally one polymer), how many have a sign."""
    z = zeta()
    g = z[(z.surface == surface) & ((z.material_group == polymer) if polymer else True)]
    hit = g.zeta_mV < 0 if sign == "negative" else g.zeta_mV > 0
    by_liquid = g.assign(hit=hit).groupby("medium_class").hit.mean().round(2).to_dict()
    return Result(
        value=int(hit.sum()),
        n=len(g),
        provenance=sorted(set(g.pmcid)),
        diagnostics={"of": len(g), "share_by_liquid": by_liquid, "papers": int(g.pmcid.nunique())},
    )


def zeta_size_correlation() -> Result:
    """Spearman ρ of log particle size against zeta over the literature values with a size."""
    z = zeta()
    rho, p = spearmanr(np.log10(z.size_nm), z.zeta_mV)
    return Result(
        value=round(float(rho), 2),
        n=len(z),
        diagnostics={"p": float(p), "papers": int(z.pmcid.nunique())},
    )


def polymer_median(polymer: Polymer) -> Result:
    """The median zeta of one polymer group, and how many of its values one paper supplies."""
    z = zeta()
    g = z[z.material_group == polymer]
    top = g.pmcid.value_counts()
    return Result(
        value=round(float(g.zeta_mV.median()), 1),
        n=len(g),
        provenance=sorted(set(g.pmcid)),
        diagnostics={"papers": int(top.size), "top_paper_values": int(top.iat[0])},
    )


def reported_share(condition: Condition) -> Result:
    """The share of papers with at least one zeta row that states `condition`."""
    t = d1()
    col = f"{condition}_reported"
    by = t.groupby("pmcid")[col].agg(lambda s: (s == "True").any())
    return Result(
        value=round(float(by.mean()), 3),
        n=int(by.size),
        diagnostics={"papers_reporting": int(by.sum())},
    )


def compare_rows(row_a: str, row_b: str) -> Result:
    """May two zeta rows (by row id) be compared under the comparability rules?"""
    rows = {r["row_id"]: r for r in zeta_table()}
    verdict = comparable(ZetaRow.from_mapping(rows[row_a]), ZetaRow.from_mapping(rows[row_b]))
    a, b = float(rows[row_a]["value"]), float(rows[row_b]["value"])
    return Result(
        value=round(abs(a - b), 1),
        provenance=[row_a, row_b],
        diagnostics={
            "verdict": verdict.verdict.value,
            "value_a": a,
            "value_b": b,
            "blockers": [x.code for x in verdict.blockers],
        },
    )


OPS: dict[str, Callable[..., Result]] = {
    f.__name__: f
    for f in (
        period_change,
        study_count,
        series_trend,
        colocated_agreement,
        duplicate_pairs,
        duplicate_check,
        compare_windows,
        compare_units,
        weser_window_ratio,
        completeness,
        zeta_sign_share,
        zeta_size_correlation,
        polymer_median,
        reported_share,
        compare_rows,
    )
}


def registry_text() -> str:
    """What the planner is shown: each operation's signature and docstring, nothing computed."""
    lines = []
    for name, f in OPS.items():
        hints = get_type_hints(f)
        params = []
        for pname, p in inspect.signature(f).parameters.items():
            allowed = _choices(hints.get(pname))
            kind = (
                " | ".join(json.dumps(x) for x in allowed) if allowed else _type_name(hints[pname])
            )
            default = "" if p.default is inspect._empty else f" = {json.dumps(p.default)}"
            params.append(f"{pname}: {kind}{default}")
        lines.append(f"- {name}({', '.join(params)})\n    {inspect.getdoc(f).splitlines()[0]}")
    return "\n".join(lines)


def _type_name(hint) -> str:
    return getattr(hint, "__name__", str(hint)).replace("typing.", "")


def execute(plan: Plan) -> Result:
    problems = plan.validate()
    if problems:
        raise ValueError("; ".join(problems))
    return OPS[plan.op](**plan.args)


# -- the guard ---------------------------------------------------------------------------------


def guard(plan: Plan, result: Result) -> tuple[str, list[str]]:
    """Diagnostics → (allow | caveat | refuse, reasons). Rules, not judgement."""
    d = result.diagnostics
    if plan.op == "period_change":
        changed = d["studies_in_both"] < 0.5 * min(d["studies_from"], d["studies_to"]) or (
            max(d["studies_from"], d["studies_to"]) > 2 * min(d["studies_from"], d["studies_to"])
        )
        return ("caveat", ["composition_shift"]) if changed else ("allow", [])
    if plan.op == "series_trend":
        moved = d["centroid_shift_km"] > AREA_SHIFT_KM
        return ("caveat", ["sampling_area_shift"]) if moved else ("allow", [])
    if plan.op == "colocated_agreement":
        return ("allow", []) if d["same_method"] else ("caveat", ["method_mix"])
    if plan.op == "duplicate_check":
        return ("refuse", ["held_twice"]) if d["shared"] >= 10 else ("allow", [])
    if plan.op == "compare_windows":
        return d["verdict"], (
            []
            if d["verdict"] == "allow"
            else [d["reason"].replace("window_factor_too_uncertain", "different_window")]
        )
    if plan.op == "compare_units":
        return d["verdict"], ([] if d["verdict"] == "allow" else ["different_unit"])
    if plan.op == "weser_window_ratio":
        return "caveat", ["different_window"]
    if plan.op == "zeta_sign_share":
        shares = list(d["share_by_liquid"].values())
        spread = max(shares) - min(shares) if shares else 0
        return ("caveat", ["liquid_dependent"]) if spread > 0.3 else ("allow", [])
    if plan.op == "polymer_median":
        return (
            ("caveat", ["single_paper"])
            if d["top_paper_values"] > 0.5 * result.n
            else ("allow", [])
        )
    if plan.op == "compare_rows":
        return ("allow", []) if d["verdict"] == "comparable" else ("refuse", ["not_comparable"])
    return "allow", []


def to_json(result: Result) -> str:
    return json.dumps(
        {
            "value": result.value,
            "n": result.n,
            "diagnostics": result.diagnostics,
            "provenance": result.provenance[:12],
        },
        default=float,
    )
