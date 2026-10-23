"""PREREG P7: does NCEI's pooled rise in ocean-water counts survive inside one series?

Run once, after docs/PREREG_2026-10.md P7 was committed (08fe9a5). A series is one DOI, one
organisation and one sampling method, as P7 defines it; a DOI sampled with two methods
contributes its most-used method.

    uv run --with openpyxl python tool/survey/p7.py   # writes out/tables/survey_p7.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import table  # noqa: E402
import validators as v  # noqa: E402

OUT = ROOT / "out/tables/survey_p7.json"
LAW_2010 = "https://doi.org/10.1126/science.1192321"
#: The five series P7 names, chosen from metadata alone (>= 8 years, >= 200 records).
SERIES = {
    "Law et al. 2010": LAW_2010,
    "Law et al. 2014": "https://doi.org/10.1021/es4053076",
    "Oceaneye (unpublished)": "https://doi.org/10.25921/d1bs-3m40",
    "Russell and Webster 2021": "https://doi.org/10.1016/j.marpolbul.2021.112210",
    "Goldstein et al. 2013": "https://doi.org/10.1371/journal.pone.0080020",
}


def water(t):
    return t[(t.dataset == "ncei") & (t.setting == "Ocean water") & t.value.notna()]


def main() -> None:
    w = water(table.load())
    law = w[w.study == LAW_2010]
    rho, p = spearmanr(law.year, law.value)
    series = []
    for name, doi in SERIES.items():
        g = w[w.study == doi]
        method = g.method.value_counts().index[0]
        s = v.series_change(g[g.method == method].assign(series=name), key="series")
        row = s.iloc[0].to_dict()
        row |= {"doi": doi, "method": method, "methods_in_doi": int(g.method.nunique())}
        series.append(row)
    periods = v.pooled_periods(w)
    p7b_rises = sum(r["ratio_last_over_first"] >= 10 for r in series)
    first, last = periods.iloc[0], periods.iloc[-1]
    out = {
        "prereg_commit": "08fe9a5",
        "P7a": {
            "tows": len(law),
            "years": [int(law.year.min()), int(law.year.max())],
            "spearman_rho": round(float(rho), 4),
            "p": float(p),
            "prediction": "|rho| < 0.1",
            "refuted_if": "rho >= 0.2 and p < 0.001",
            "verdict": "supported"
            if abs(rho) < 0.1
            else ("refuted" if rho >= 0.2 and p < 0.001 else "not supported, not refuted"),
        },
        "P7b": {
            "series": series,
            "rises_x10_or_more": int(p7b_rises),
            "prediction": "every series < x10",
            "refuted_if": "two or more series rise x10 or more",
            "verdict": "supported"
            if p7b_rises == 0
            else ("refuted" if p7b_rises >= 2 else "partly"),
        },
        "P7c": {
            "periods": periods.round(6).to_dict(orient="records"),
            "pooled_ratio_last_over_2000s_per_record": None,
        },
    }
    p2000 = periods[periods.period == 2000]
    if len(p2000):
        out["P7c"]["pooled_ratio_last_over_2000s_per_record"] = round(
            float(last.median_per_record / p2000.median_per_record.iat[0]), 1
        )
        out["P7c"]["pooled_ratio_last_over_2000s_per_study"] = round(
            float(last.median_per_study / p2000.median_per_study.iat[0]), 1
        )
    out["P7c"]["first_period"] = int(first.period)
    # Secondary, chosen after P7b: Law et al. 2014 inside the accumulation zone its own abstract
    # defines (25-41 N, 130-180 W). The paper reports no robust trend and blames confounded
    # spatial and temporal variability; this asks how much of the series' x10 is the ship's track.
    g = w[w.study == SERIES["Law et al. 2014"]]
    box = g.lat.between(25, 41) & g.lon.between(-180, -130)
    years = np.sort(g.year.unique())
    k = int(np.ceil(len(years) / 3))
    out["P7_secondary_law2014_zone"] = {
        "chosen_after_results": True,
        "zone": "25-41 N, 130-180 W (Law et al. 2014 abstract)",
        "ratio_whole_series": round(series[1]["ratio_last_over_first"], 2),
        "ratio_inside_zone": round(
            float(v.series_change(g[box].assign(s=1), key="s").ratio_last_over_first.iat[0]), 2
        ),
        "share_in_zone_first_third": round(float(box[g.year.isin(years[:k])].mean()), 3),
        "share_in_zone_last_third": round(float(box[g.year.isin(years[-k:])].mean()), 3),
    }
    OUT.write_text(json.dumps(out, indent=1, default=float) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
