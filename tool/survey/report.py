"""The validators' findings over the whole survey table, written as small committed tables.

uv run --with openpyxl python tool/survey/report.py
# out/tables/survey_duplicates.csv, survey_completeness.csv, survey_colocated.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import table  # noqa: E402
import validators as v  # noqa: E402

TABLES = ROOT / "out/tables"


def _independent(t, p, dup):
    """Drop record pairs whose two studies hold the same samples (the duplicates table)."""
    held_twice = {frozenset((a, b)) for a, b in zip(dup.study_a, dup.study_b, strict=True)}
    pair = [
        frozenset((a, b)) for a, b in zip(t.loc[p.i, "study"], t.loc[p.j, "study"], strict=True)
    ]
    keep = np.array([s not in held_twice for s in pair], dtype=bool)
    return p[keep], [s for s, k in zip(pair, keep, strict=True) if k], int((~keep).sum())


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
        "excluded_held_twice": excluded,
        "study_pairs": len(set(pair)),
        **_folds(p.log10_ratio),
    }


def across_datasets(t, km: float, days: int | None, dup) -> dict:
    """Records from two datasets near each other, judged by the window guard before any ratio.

    A pair the guard refuses is counted and shown with its fold, but never enters the summary
    fold: two windows no slope can convert between say nothing about each other's numbers.
    """
    p = v.colocated(t, km=km, days=days, same_method=False)
    if not p.empty:
        p = p[t.loc[p.i, "dataset"].to_numpy() != t.loc[p.j, "dataset"].to_numpy()]
    if p.empty:
        return {"km": km, "days": days, "pairs": 0}
    p, _, excluded = _independent(t, p, dup)
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
    )
    groups = [
        {"datasets": d, "decision": dec, "reason": r, "pairs": int(len(g)),
         "median_years_apart": float(np.nanmedian(g.years_apart)), **_folds(g.log10_ratio)}
        for (d, dec, r), g in p.groupby(["datasets", "decision", "reason"])
    ]  # fmt: skip
    compared = p[p.decision != "refuse"]
    return {
        "km": km,
        "days": days,
        "pairs": int(len(p)),
        "excluded_held_twice": excluded,
        "compared": int(len(compared)),
        "refused": int(len(p) - len(compared)),
        **(_folds(compared.log10_ratio) if len(compared) else {}),
        "by_dataset_pair": groups,
    }


def main() -> None:
    t = table.load()
    dup = v.duplicates(t)
    dup.to_csv(TABLES / "survey_duplicates.csv", index=False)
    v.completeness(t).to_csv(TABLES / "survey_completeness.csv")
    water = t[t.setting == "Ocean water"]
    # studies against studies inside one database (the questions ask about NCEI); databases
    # against each other are across_datasets, judged by the window guard
    ncei = water[water.dataset == "ncei"]
    out = {
        "records": {k: int(n) for k, n in t.groupby("dataset").size().items()},
        "same_method_50km_365d": colocated_summary(ncei, 50, 365, True, dup),
        "any_method_50km_365d": colocated_summary(ncei, 50, 365, False, dup),
        "mediterranean_same_method_50km_365d": colocated_summary(
            ncei[ncei.region == "Mediterranean Sea"], 50, 365, True, dup
        ),
        "across_datasets": across_datasets(water, 50, 365, dup),
        # the same area in another dataset, in any year: descriptive, place held, time not
        "across_datasets_100km_any_year": across_datasets(water, 100, None, dup),
    }
    (TABLES / "survey_colocated.json").write_text(json.dumps(out, indent=1) + "\n")
    print(dup.to_string())
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
