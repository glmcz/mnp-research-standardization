"""Run the confirmatory tests P1–P4 exactly as docs/PREREG_2026-10.md states them.

Each verdict compares a statistic with the band committed in 050d5d1, before this script ran.
P5 and P6 need the validation system and run there.

    uv run --with openpyxl python tool/p2/prereg.py   # writes out/tables/p2_prereg_results.json
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu, spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold, KFold

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))
import extension as ext  # noqa: E402

from mnp.rescale.powerlaw import ALPHA_DEFAULT, cf_closed  # noqa: E402

PREREG_COMMIT = "050d5d1"
ALPHA_BAND = (1.3, 1.9)  # PREREG P3: 1.6 ± 0.3
SEED = 20261019
BOOT = 2000
ZETA = ROOT / "out/tables/p2_zeta_size.csv"
OUT = ROOT / "out/tables/p2_prereg_results.json"


def boot_ci(stat, groups: np.ndarray, rng: np.random.Generator) -> list[float]:
    """95 % percentile interval of `stat(idx)`, resampling whole groups with replacement."""
    keys = np.unique(groups)
    members = {k: np.flatnonzero(groups == k) for k in keys}
    vals = []
    for _ in range(BOOT):
        pick = rng.choice(keys, size=len(keys), replace=True)
        vals.append(stat(np.concatenate([members[k] for k in pick])))
    return [float(np.nanpercentile(vals, 2.5)), float(np.nanpercentile(vals, 97.5))]


def p1(soil: pd.DataFrame, rng) -> dict:
    """Soil, one point per study: finest lower limit against median positive concentration."""
    pos = soil[soil.conc > 0]
    per = (
        soil.groupby("study")
        .lower_um.min()
        .to_frame()
        .join(pos.groupby("study").conc.median().rename("median"))
        .dropna()
    )
    per = per[per.lower_um > 0]
    x, y = np.log10(per.lower_um.to_numpy()), np.log10(per["median"].to_numpy())
    rho = float(spearmanr(x, y).statistic)
    slope = float(np.polyfit(x, y, 1)[0])
    ci = boot_ci(
        lambda i: np.polyfit(x[i], y[i], 1)[0] if len(set(x[i])) > 1 else np.nan,
        np.arange(len(x)),
        rng,
    )
    band_hit = ci[0] <= -0.3 and ci[1] >= -1.2
    if rho >= 0 or not band_hit:
        verdict = "refuted"
    elif -0.40 <= rho <= -0.15 and -1.2 <= slope <= -0.3:
        verdict = "supported"
    else:
        verdict = "partly"
    return {
        "studies": len(per),
        "rho": round(rho, 3),
        "slope": round(slope, 3),
        "slope_ci95": [round(v, 3) for v in ci],
        "prediction": "rho in [-0.40, -0.15] and slope in [-1.2, -0.3]",
        "refuted_if": "rho >= 0, or the slope interval misses [-1.2, -0.3]",
        "verdict": verdict,
    }


def p2(soil: pd.DataFrame) -> dict:
    """Soil 0.1° cells holding 2+ studies: spread across studies, before vs after rescaling."""
    r = soil[(soil.conc > 0) & (soil.lower_um > 0) & (soil.upper_um > soil.lower_um)].copy()
    r["cf"] = [cf_closed(lo, hi) for lo, hi in zip(r.lower_um, r.upper_um, strict=True)]
    r["resc"] = r.conc * r.cf
    r["cell"] = list(zip(r.lat.round(1), r.lon.round(1), strict=True))
    per = (
        r.groupby(["cell", "study"])
        .agg(raw=("conc", "median"), resc=("resc", "median"))
        .reset_index()
    )
    reductions = []
    for _, g in per.groupby("cell"):
        if g.study.nunique() < 2:
            continue
        raw = np.log10(g.raw).max() - np.log10(g.raw).min()
        resc = np.log10(g.resc).max() - np.log10(g.resc).min()
        if raw > 0:
            reductions.append(1 - resc / raw)
    med = float(np.median(reductions))
    verdict = "supported" if med < 0.25 else "refuted" if med >= 0.50 else "partly"
    return {
        "cells": len(reductions),
        "median_reduction": round(med, 3),
        "share_cells_wider_after": round(float(np.mean(np.array(reductions) < 0)), 3),
        "prediction": "median reduction < 0.25",
        "refuted_if": "median reduction >= 0.50",
        "verdict": verdict,
    }


def p3(alphas: pd.DataFrame) -> dict:
    """MPsizeBase: one α per measured distribution."""
    a = alphas.alpha.to_numpy()
    within = float(np.mean((a >= ALPHA_BAND[0]) & (a <= ALPHA_BAND[1])))
    by = {t: g.alpha.to_numpy() for t, g in alphas.groupby("sample_type")}
    big = sorted(by, key=lambda t: -len(by[t]))[:2]
    mw = mannwhitneyu(by[big[0]], by[big[1]]).pvalue if len(big) == 2 else np.nan
    med = float(np.median(a))
    ok = 1.3 <= med <= 2.2 and (1 - within) >= 0.30 and mw < 0.05
    verdict = "refuted" if within >= 0.80 else "supported" if ok else "partly"
    pair = alphas.dropna(subset=["alpha_source"])
    return {
        "distributions": len(a),
        "median_alpha": round(med, 2),
        "alpha_p10_p90": [round(float(np.percentile(a, q)), 2) for q in (10, 90)],
        "share_within_1.6pm0.3": round(within, 3),
        "median_by_type": {t: round(float(np.median(by[t])), 2) for t in by},
        "n_by_type": {t: int(len(by[t])) for t in by},
        "mannwhitney_p_two_largest_types": float(f"{mw:.2g}"),
        "types_compared": big,
        "source_alpha_spearman": round(float(spearmanr(pair.alpha, pair.alpha_source).statistic), 2)
        if len(pair) > 2
        else None,
        "prediction": "median alpha in [1.3, 2.2]; >= 30 % outside 1.6 ± 0.3; type medians differ",
        "refuted_if": ">= 80 % within 1.6 ± 0.3",
        "verdict": verdict,
    }


FEATURES = {
    "size": ["log_size"],
    "polymer": ["material_group"],
    "surface": ["surface"],
    "liquid_pH": ["medium_class", "pH"],
    "all": ["log_size", "material_group", "surface", "medium_class", "pH"],
}
CATEGORICAL = {"material_group", "surface", "medium_class"}


def p4(rng) -> dict:
    """Zeta from descriptors: gradient-boosted trees, 5-fold CV grouped by paper."""
    t = pd.read_csv(ZETA)
    t["log_size"] = np.log10(t.size_nm)
    t["pH"] = pd.to_numeric(t.pH, errors="coerce")
    y = t.zeta_mV.to_numpy()
    groups = t.pmcid.to_numpy()
    folds = list(GroupKFold(n_splits=5).split(t, y, groups))
    out = {}
    for name, cols in FEATURES.items():
        X = t[cols].copy()
        cat = [c in CATEGORICAL for c in cols]
        for c in cols:
            if c in CATEGORICAL:
                X[c] = X[c].astype("category").cat.codes
        pred = np.empty_like(y, dtype=float)
        for train, test in folds:
            m = HistGradientBoostingRegressor(categorical_features=cat, random_state=SEED)
            m.fit(X.iloc[train], y[train])
            pred[test] = m.predict(X.iloc[test])

        def r2(i, pred=pred):
            return 1 - np.sum((y[i] - pred[i]) ** 2) / np.sum((y[i] - y[i].mean()) ** 2)

        out[name] = {
            "r2": round(float(r2(np.arange(len(y)))), 3),
            "r2_ci95": [round(v, 3) for v in boot_ci(r2, groups, rng)],
        }
    r = {k: v["r2"] for k, v in out.items()}
    refuted = r["all"] >= 0.69 or max(r["polymer"], r["size"]) > max(r["surface"], r["liquid_pH"])
    ok = (
        r["all"] < 0.5
        and r["size"] <= 0.05
        and r["surface"] > r["polymer"]
        and r["liquid_pH"] > r["polymer"]
    )
    return {
        "rows": len(t),
        "papers": int(t.pmcid.nunique()),
        "feature_sets": out,
        "zeta_table_sha256": hashlib.sha256(ZETA.read_bytes()).hexdigest(),
        "prediction": "R2(all) < 0.5; R2(size) <= 0.05; surface and liquid_pH each > polymer",
        "refuted_if": "R2(all) >= 0.69, or polymer or size out-predicts both surface and liquid_pH",
        "verdict": "refuted" if refuted else "supported" if ok else "partly",
    }


def secondary(soil: pd.DataFrame, bins: pd.DataFrame) -> dict:
    """Analyses chosen after seeing P1–P4. Reported, never used to change a verdict."""
    # P2: the median of 0 comes from cells where every study used the same window.
    r = soil[(soil.conc > 0) & (soil.lower_um > 0) & (soil.upper_um > soil.lower_um)].copy()
    r["resc"] = r.conc * [cf_closed(lo, hi) for lo, hi in zip(r.lower_um, r.upper_um, strict=True)]
    r["cell"] = list(zip(r.lat.round(1), r.lon.round(1), strict=True))
    per = (
        r.groupby(["cell", "study"])
        .agg(
            raw=("conc", "median"),
            resc=("resc", "median"),
            lo=("lower_um", "min"),
            hi=("upper_um", "max"),
        )
        .reset_index()
    )
    diff = []
    for _, g in per.groupby("cell"):
        raw = np.log10(g.raw).max() - np.log10(g.raw).min()
        if g.study.nunique() >= 2 and raw > 0 and g[["lo", "hi"]].drop_duplicates().shape[0] > 1:
            diff.append(1 - (np.log10(g.resc).max() - np.log10(g.resc).min()) / raw)
    diff = np.array(diff)
    # P3: MPsizeBase's own 'Low LOD size filter' drops bins near the detection limit.
    lod = ext.fit_alpha(
        bins.assign(
            Geom_mean_size=bins["filtered_geom_mean_size"],
            Normalized_concentration=bins["filtered_normalized_concentration"],
        )
    )
    a = lod.alpha.to_numpy()
    types = {t: g.alpha.to_numpy() for t, g in lod.groupby("sample_type")}
    # P4: the same model, rows shuffled across papers, so a paper's rows can train on each other.
    t = pd.read_csv(ZETA)
    t["log_size"] = np.log10(t.size_nm)
    t["pH"] = pd.to_numeric(t.pH, errors="coerce")
    cols = FEATURES["all"]
    X = t[cols].copy()
    for c in CATEGORICAL:
        X[c] = X[c].astype("category").cat.codes
    y = t.zeta_mV.to_numpy()
    pred = np.empty_like(y, dtype=float)
    for train, test in KFold(5, shuffle=True, random_state=SEED).split(X):
        m = HistGradientBoostingRegressor(
            categorical_features=[c in CATEGORICAL for c in cols], random_state=SEED
        ).fit(X.iloc[train], y[train])
        pred[test] = m.predict(X.iloc[test])
    by_paper = np.empty_like(y, dtype=float)
    for train, test in KFold(5, shuffle=True, random_state=SEED).split(X):
        means = t.iloc[train].groupby("pmcid").zeta_mV.mean()
        by_paper[test] = t.iloc[test].pmcid.map(means).fillna(y[train].mean()).to_numpy()
    return {
        "note": "chosen after seeing P1–P4; descriptive, not confirmatory",
        "P4_random_split_r2_paper_mean_only": round(
            float(1 - np.sum((y - by_paper) ** 2) / np.sum((y - y.mean()) ** 2)), 3
        ),
        "P2_cells_with_different_windows": {
            "cells": int(len(diff)),
            "median_reduction": round(float(np.median(diff)), 3),
            "share_wider_after": round(float(np.mean(diff < 0)), 3),
        },
        "P3_lod_filtered": {
            "distributions": int(len(a)),
            "median_alpha": round(float(np.median(a)), 2),
            "alpha_p10_p90": [round(float(np.percentile(a, q)), 2) for q in (10, 90)],
            "share_within_1.6pm0.3": round(
                float(np.mean((a >= ALPHA_BAND[0]) & (a <= ALPHA_BAND[1]))), 3
            ),
            "median_by_type": {k: round(float(np.median(v)), 2) for k, v in types.items()},
            "mannwhitney_p": float(f"{mannwhitneyu(*types.values()).pvalue:.2g}"),
        },
        "P4_random_split_r2_all": round(
            float(1 - np.sum((y - pred) ** 2) / np.sum((y - y.mean()) ** 2)), 3
        ),
        "P1_implied_alpha": None,  # filled in main from P1's slope: alpha = 1 - slope
    }


def main() -> None:
    ext.check_pins()
    rng = np.random.default_rng(SEED)
    soil = ext.soil()
    bins = ext.mpsb_bins()
    alphas = ext.fit_alpha(bins)
    results = {
        "prereg_commit": PREREG_COMMIT,
        "code_commit": subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
        ).stdout.strip(),
        "alpha_default": ALPHA_DEFAULT,
        "alpha_band": list(ALPHA_BAND),
        "seed": SEED,
        "bootstrap": BOOT,
        "inputs": {str(p.relative_to(ROOT)): s for p, s in ext.PINS.items()},
        "P1": p1(soil, rng),
        "P2": p2(soil),
        "P3": p3(alphas),
        "P4": p4(rng),
    }
    results["secondary"] = secondary(soil, bins)
    results["secondary"]["P1_implied_alpha"] = round(1 - results["P1"]["slope"], 2)
    OUT.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(results, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
