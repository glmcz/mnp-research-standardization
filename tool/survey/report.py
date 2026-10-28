"""The validators' findings over the whole survey table, written as small committed tables.

uv run --with openpyxl python tool/survey/report.py
# out/tables/survey_duplicates.csv, survey_completeness.csv, survey_studies.csv,
# survey_colocated.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import table  # noqa: E402
import validators as v  # noqa: E402

TABLES = ROOT / "out/tables"


def _paper(study: pd.Series) -> pd.Series:
    """The DOI link a study id ends in, whichever database holds it ("aomi:https://doi.org/..."
    and "https://doi.org/..." are one paper); missing for an id that names no DOI."""
    return study.str.extract(r"(https://doi\.org/\S+)$", expand=False)


def _independent(t, p, dup):
    """Drop record pairs whose two studies are one paper held by two databases, or hold the same
    samples (the duplicates table, found by date and place)."""
    held_twice = (
        {frozenset(x) for x in zip(dup.study_a, dup.study_b, strict=True)} if len(dup) else set()
    )
    pair = [
        frozenset((a, b)) for a, b in zip(t.loc[p.i, "study"], t.loc[p.j, "study"], strict=True)
    ]
    pa, pb = _paper(t.loc[p.i, "study"]).to_numpy(), _paper(t.loc[p.j, "study"]).to_numpy()
    same = pd.notna(pa) & (pa == pb)
    twice = np.array([s in held_twice for s in pair], dtype=bool) & ~same
    keep = ~(same | twice)
    excluded = {"excluded_held_twice": int(twice.sum()), "excluded_same_paper": int(same.sum())}
    return p[keep], [s for s, k in zip(pair, keep, strict=True) if k], excluded


def _folds(log10_ratio) -> dict:
    q = np.quantile(log10_ratio, [0.5, 0.9])
    return {"median_fold": round(float(10 ** q[0]), 2), "p90_fold": round(float(10 ** q[1]), 1)}


def colocated_summary(t, km: float, days: int | None, same_method: bool, dup) -> dict:
    """Agreement between independent studies: study pairs that hold the same samples are out."""
    p = v.colocated(t, km=km, days=days, same_method=same_method)
    if p.empty:
        return {"pairs": 0}
    p, pair, excluded = _independent(t, p, dup)
    return {
        "km": km,
        "days": days,
        "same_method": same_method,
        "pairs": int(len(p)),
        **excluded,
        "study_pairs": len(set(pair)),
        **_folds(p.log10_ratio),
    }


def within_study_summary(t, km: float, days: int | None) -> dict:
    """The same check inside one study: two of its own records this close, same method. It is the
    patchiness and replicate spread that a disagreement between studies has to exceed."""
    p = v.colocated(t, km=km, days=days, same_method=True, same_study=True)
    if p.empty:
        return {"pairs": 0}
    return {
        "km": km,
        "days": days,
        "pairs": int(len(p)),
        "studies": int(t.loc[p.i, "study"].nunique()),
        **_folds(p.log10_ratio),
    }


def _residual(va: float, vb: float, verdict) -> float:
    """log10 of how far b/a lies outside the window factor's interval; 0 when it is inside."""
    lo, hi = verdict.detail if verdict.decision == "caveat" else (1.0, 1.0)
    r = np.log10(vb / va)
    return float(max(0.0, r - np.log10(hi), np.log10(lo) - r))


def across_datasets(t, km: float, days: int | None, dup) -> dict:
    """Records from two datasets near each other, judged by the window guard before any ratio.

    A pair the guard refuses is counted and shown with its fold, but never enters the summary
    fold: two windows no slope can convert between say nothing about each other's numbers.
    A caveated pair also reports its residual: the fold left after the most generous window
    conversion, which is the disagreement the size window cannot explain.
    """
    p = v.colocated(t, km=km, days=days, same_method=False)
    if not p.empty:
        p = p[t.loc[p.i, "dataset"].to_numpy() != t.loc[p.j, "dataset"].to_numpy()]
    if p.empty:
        return {"km": km, "days": days, "pairs": 0}
    p, _, excluded = _independent(t, p, dup)
    if p.empty:
        return {"km": km, "days": days, "pairs": 0, **excluded}
    a, b = t.loc[p.i], t.loc[p.j]
    verdicts = [
        v.window_verdict((a0, a1), (b0, b1))
        for a0, a1, b0, b1 in zip(a.size_min_um, a.size_max_um, b.size_min_um, b.size_max_um,
                                  strict=True)
    ]  # fmt: skip
    p = p.assign(
        datasets=[" vs ".join(sorted(x)) for x in zip(a.dataset, b.dataset, strict=True)],
        decision=[x.decision for x in verdicts],
        reason=[x.reason for x in verdicts],
        years_apart=np.abs(a.year.to_numpy() - b.year.to_numpy()),
        residual=[_residual(va, vb, x) for va, vb, x in zip(a.value, b.value, verdicts,
                                                              strict=True)],
    )  # fmt: skip
    groups = [
        {"datasets": d, "decision": dec, "reason": r, "pairs": int(len(g)),
         "median_years_apart": float(np.nanmedian(g.years_apart)), **_folds(g.log10_ratio),
         **({} if dec == "refuse" else
            {"median_residual_fold": round(float(10 ** np.median(g.residual)), 2)})}
        for (d, dec, r), g in p.groupby(["datasets", "decision", "reason"])
    ]  # fmt: skip
    compared = p[p.decision != "refuse"]
    return {
        "km": km,
        "days": days,
        "pairs": int(len(p)),
        **excluded,
        "compared": int(len(compared)),
        "refused": int(len(p) - len(compared)),
        **(_folds(compared.log10_ratio) if len(compared) else {}),
        "unguarded": _folds(p.log10_ratio),  # what pooling every pair would have reported
        "by_dataset_pair": groups,
    }


def studies(t: pd.DataFrame) -> pd.DataFrame:
    """One row per study and setting: its stated window and the span of its positive values.

    This is the reviewer's benchmark plot as a table (review call, 2026-10-10, item 12): x is the
    size window a study counted, y the concentrations it reports.
    """
    keys = ["dataset", "study", "setting", "unit"]
    t = t.assign(study=t.study.fillna("(no study id)"))
    g = t.groupby(keys, dropna=False)
    pos = t[t.value > 0].groupby(keys, dropna=False).value
    out = pd.DataFrame(
        {
            "n": g.size(),
            "n_pos": pos.size(),
            "p10": pos.quantile(0.1),
            "p50": pos.median(),
            "p90": pos.quantile(0.9),
            "size_min_um": g.size_min_um.median(),
            "size_max_um": g.size_max_um.median(),
            "lat": g.lat.median(),
            "lon": g.lon.median(),
            "year_first": g.year.min(),
            "year_last": g.year.max(),
        }
    ).reset_index()
    return out.fillna({"n_pos": 0}).astype({"n_pos": int})


def main() -> None:
    t = table.load()
    dup = v.duplicates(t)
    dup.to_csv(TABLES / "survey_duplicates.csv", index=False)
    v.completeness(t).to_csv(TABLES / "survey_completeness.csv")
    studies(t).round(6).to_csv(TABLES / "survey_studies.csv", index=False)
    water = t[t.setting == "Ocean water"]
    # studies against studies inside one database (the questions ask about NCEI); databases
    # against each other are across_datasets, judged by the window guard
    ncei = water[water.dataset == "ncei"]
    out = {
        "records": {k: int(n) for k, n in t.groupby("dataset").size().items()},
        "same_method_50km_365d": colocated_summary(ncei, 50, 365, True, dup),
        "within_study_50km_365d": within_study_summary(ncei, 50, 365),
        "any_method_50km_365d": colocated_summary(ncei, 50, 365, False, dup),
        "mediterranean_same_method_50km_365d": colocated_summary(
            ncei[ncei.region == "Mediterranean Sea"], 50, 365, True, dup
        ),
        "across_datasets": across_datasets(water, 50, 365, dup),
        # the same area in another dataset, in any year: descriptive, place held, time not
        "across_datasets_100km_any_year": across_datasets(water, 100, None, dup),
        "net_depth_from_paper": [
            {
                "study": doi,
                "method": method,
                "paper_m": paper,
                "implied_m": implied,
                "records": t[t["flags"].str.contains(f"depth_from_paper_{paper}m", na=False)]
                .groupby("dataset")
                .size()
                .astype(int)
                .to_dict(),
            }
            for (doi, method), (paper, implied) in table.NET_DEPTH.items()
        ],
    }
    (TABLES / "survey_colocated.json").write_text(json.dumps(out, indent=1) + "\n")
    print(dup.to_string())
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
