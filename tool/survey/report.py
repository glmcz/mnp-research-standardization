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


def colocated_summary(t, km: float, days: int | None, same_method: bool, dup) -> dict:
    """Agreement between independent studies: study pairs that hold the same samples are out."""
    p = v.colocated(t, km=km, days=days, same_method=same_method)
    if p.empty:
        return {"pairs": 0}
    held_twice = {frozenset((a, b)) for a, b in zip(dup.study_a, dup.study_b, strict=True)}
    pair = [
        frozenset((a, b)) for a, b in zip(t.loc[p.i, "study"], t.loc[p.j, "study"], strict=True)
    ]
    keep = np.array([s not in held_twice for s in pair])
    p, pair = p[keep], [s for s, k in zip(pair, keep, strict=True) if k]
    studies = set(pair)
    q = np.quantile(p.log10_ratio, [0.5, 0.9])
    return {
        "km": km,
        "days": days,
        "same_method": same_method,
        "pairs": int(len(p)),
        "excluded_held_twice": int((~keep).sum()),
        "study_pairs": len(studies),
        "median_fold": round(float(10 ** q[0]), 2),
        "p90_fold": round(float(10 ** q[1]), 1),
    }


def main() -> None:
    t = table.load()
    dup = v.duplicates(t)
    dup.to_csv(TABLES / "survey_duplicates.csv", index=False)
    v.completeness(t).to_csv(TABLES / "survey_completeness.csv")
    water = t[t.setting == "Ocean water"]
    out = {
        "records": {k: int(n) for k, n in t.groupby("dataset").size().items()},
        "same_method_50km_365d": colocated_summary(water, 50, 365, True, dup),
        "any_method_50km_365d": colocated_summary(water, 50, 365, False, dup),
        "mediterranean_same_method_50km_365d": colocated_summary(
            water[water.region == "Mediterranean Sea"], 50, 365, True, dup
        ),
    }
    (TABLES / "survey_colocated.json").write_text(json.dumps(out, indent=1) + "\n")
    print(dup.to_string())
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
