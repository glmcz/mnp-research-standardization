"""D3: Koelmans 2019 Table S1 concentrations put on a common size range.

Writes `d3_rescaled.csv` (one row per study × target × α), `d3_spread.csv` (spread of
log10 concentration before and after rescaling, per target/α/unit) and
`d3_before_after.png` (measured vs the two targets at α = 1.6).
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

from mnp.rescale import koelmans2019
from mnp.rescale import powerlaw as pl

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

BEFORE = "measured"
SPREAD_COLUMNS = (
    "target",
    "alpha",
    "alpha_source",
    "unit",
    "n",
    "min",
    "max",
    "log10_range",
    "iqr_log10",
    "gcv",
)
# first three categorical slots of the validated default palette (all-pairs safe)
COLORS = {BEFORE: "#2a78d6", pl.target_label(pl.TARGET_DEFAULT): "#eb6834"}
COLORS[pl.target_label(pl.TARGET_NANO)] = "#1baf7a"
INK, INK_2, MUTED, GRID = "#0b0b0b", "#52514e", "#898781", "#e1e0d9"


def _stats(values, target: str, alpha: float, unit: str) -> dict:
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v) & (v > 0)]
    logs = np.log10(v)
    q75, q25 = np.percentile(logs, [75, 25])
    s_ln = np.log(v).std(ddof=1) if len(v) > 1 else np.nan
    return {
        "target": target,
        "alpha": alpha,
        "alpha_source": "" if np.isnan(alpha) else pl.alpha_source(alpha),
        "unit": unit,
        "n": int(len(v)),
        "min": v.min(),
        "max": v.max(),
        "log10_range": logs.max() - logs.min(),
        "iqr_log10": q75 - q25,
        "gcv": np.sqrt(np.exp(s_ln**2) - 1),
    }


def spread_table(rescaled: pd.DataFrame) -> pd.DataFrame:
    """Per unit: the measured spread once, then the rescaled spread per target and α."""
    ok = rescaled[rescaled["excluded_reason"].isna()]
    if ok.empty:
        return pd.DataFrame(columns=SPREAD_COLUMNS)
    first = ok[(ok["target"] == ok["target"].iloc[0]) & (ok["alpha"] == ok["alpha"].iloc[0])]
    rows = [
        _stats(grp["value_norm"], BEFORE, np.nan, unit)
        for unit, grp in first.groupby("unit_norm", sort=False)
    ]
    for (target, alpha, unit), grp in ok.groupby(["target", "alpha", "unit_norm"], sort=False):
        rows.append(_stats(grp["rescaled_value"], target, alpha, unit))
    return pd.DataFrame(rows, columns=SPREAD_COLUMNS)


def figure(rescaled: pd.DataFrame, path: Path, alpha: float = pl.ALPHA_DEFAULT) -> Path:
    ok = rescaled[rescaled["excluded_reason"].isna() & np.isclose(rescaled["alpha"], alpha)]
    units = list(dict.fromkeys(ok["unit_norm"])) or ["n/L"]
    fig, axes = plt.subplots(1, len(units), figsize=(4.4 * len(units) + 0.8, 4.8), squeeze=False)
    rng = np.random.default_rng(0)
    for ax, unit in zip(axes[0], units, strict=True):
        sub = ok[ok["unit_norm"] == unit]
        targets = list(dict.fromkeys(sub["target"]))
        groups = [(BEFORE, sub[sub["target"] == targets[0]]["value_norm"])] if targets else []
        groups += [(t, sub[sub["target"] == t]["rescaled_value"]) for t in targets]
        for i, (label, values) in enumerate(groups):
            logs = np.log10(np.asarray(values, dtype=float))
            logs = logs[np.isfinite(logs)]
            if len(logs) == 0:
                continue
            ax.boxplot(
                [logs],
                positions=[i],
                widths=0.5,
                showfliers=False,
                medianprops={"color": INK, "linewidth": 1.5},
                boxprops={"color": MUTED},
                whiskerprops={"color": MUTED},
                capprops={"color": MUTED},
            )
            jitter = rng.uniform(-0.16, 0.16, len(logs))
            ax.scatter(
                i + jitter,
                logs,
                s=24,
                color=COLORS.get(label, MUTED),
                edgecolors="white",
                linewidths=0.8,
                zorder=3,
            )
            ax.annotate(
                f"n = {len(logs)}\nmedian {10 ** np.median(logs):.3g}",
                (i, logs.max()),
                textcoords="offset points",
                xytext=(0, 8),
                ha="center",
                fontsize=8,
                color=INK_2,
            )
        ax.set_xticks(range(len(groups)))
        ax.set_xticklabels([g[0] for g in groups], fontsize=9)
        ax.set_xlim(-0.6, max(len(groups) - 0.4, 0.6))
        ax.set_ylabel(f"log10 concentration ({unit})", color=INK_2)
        ax.margins(y=0.18)
        ax.grid(axis="y", color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)
        ax.tick_params(colors=INK_2)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(MUTED)
    fig.suptitle(
        f"Koelmans 2019 Table S1: measured vs rescaled, pdf ∝ $x^{{-\\alpha}}$, α = {alpha:g}",
        fontsize=11,
        color=INK,
    )
    caption = (
        f"α = {alpha:g} from Kooi & Koelmans 2019 / Koelmans 2020 eq. 2. Studies reporting "
        "only a lower size bound are assumed to reach 5000 µm. The 0.1–5000 µm target "
        "extrapolates below every study's floor; it shifts every study by the same factor, "
        "so the spread is that of the 1–5000 µm target."
    )
    fig.text(0.01, 0.01, textwrap.fill(caption, 150), fontsize=7, color=MUTED, va="bottom")
    fig.tight_layout(rect=(0, 0.07, 1, 0.94))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def build(
    out_tables: Path,
    out_figures: Path,
    *,
    table: pd.DataFrame | None = None,
    processed: Path | None = None,
) -> list[Path]:
    if table is None:
        table = koelmans2019.load_table_s1()
    out_tables.mkdir(parents=True, exist_ok=True)
    out_figures.mkdir(parents=True, exist_ok=True)
    rescaled = pl.rescale_table(table)
    if processed is not None:
        processed.parent.mkdir(parents=True, exist_ok=True)
        rescaled.to_parquet(processed, index=False)
    rescaled_csv = out_tables / "d3_rescaled.csv"
    rescaled.to_csv(rescaled_csv, index=False)
    spread_csv = out_tables / "d3_spread.csv"
    spread_table(rescaled).to_csv(spread_csv, index=False)
    png = figure(rescaled, out_figures / "d3_before_after.png")
    return [rescaled_csv, spread_csv, png]
