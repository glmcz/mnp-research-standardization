"""Extension datasets for P2: soil, measured size distributions, the Weser fractions.

Decided 2026-10-18: new data is an extension layer. The frozen corpus and every number the deck
prints are untouched. Inputs are third-party downloads (gitignored), each pinned by sha256; their
sources and licences are in tool/datasets/README.md. Excel needs openpyxl, passed per command:

    uv run --with openpyxl python tool/p2/prereg.py
"""

from __future__ import annotations

import hashlib
import io
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CONC = ROOT / "data/raw/datasets_recon/conc"
SOIL = CONC / "soil_wu/soil_mp_2005_2026.xlsx"  # Wu et al., Zenodo 20806151, CC BY 4.0
MPSB = CONC / "mpsizebase/MPsizeBase_v19-5-2026.xlsx"  # CNRS, Zenodo 20832480, CC BY 4.0
WESER_S = CONC / "pangaea/p_937685.tab"  # PANGAEA 937685, CC BY 4.0
WESER_L = CONC / "pangaea/p_938143.tab"  # PANGAEA 938143, CC BY 4.0
PINS = {
    SOIL: "8dba8a1e8a36aca6f5ce6f1b9dcc1091da7d5567b08ec802c742b4c0804ea06e",
    MPSB: "2bf00714d8131c5fc16b355b67d9a80407070753c28578c432974aec8519d25d",
    WESER_S: "9f1dbdadac462f5768c3732757e3093bb63cb9134be1144ba0c621e4b5192b6b",
    WESER_L: "ecccbfcabd6efd4e6e4da14db1c53df6837dbc9ec92ef477a63c6991d5ea957f",
}


def check_pins() -> None:
    for path, want in PINS.items():
        got = hashlib.sha256(path.read_bytes()).hexdigest()
        if got != want:
            raise SystemExit(f"{path}: sha256 {got} != pinned {want}")


def _year(v) -> float:
    """'2024', 2021.9 or '2019.05-2019.08' → the first four-digit year; anything else → NaN."""
    m = re.search(r"(19|20)\d\d", str(v))
    return float(m.group(0)) if m else np.nan


def soil() -> pd.DataFrame:
    """One row per soil record. A study is a paper title: the dataset has no DOI column."""
    s = pd.read_excel(SOIL, sheet_name="information")
    s = s[s["ID"].notna()]
    return pd.DataFrame(
        {
            "study": s["Title"].astype(str).str.strip(),
            "lat": pd.to_numeric(s["Latitude"], errors="coerce"),
            "lon": pd.to_numeric(s["Longitude"], errors="coerce"),
            "year": s["Sampling date"].map(_year),
            "lower_um": pd.to_numeric(s["Size min(μm)"], errors="coerce"),
            "upper_um": pd.to_numeric(s["Size max(μm)"], errors="coerce"),
            "conc": pd.to_numeric(s["abundance_numeric"], errors="coerce"),
            "cf_source": pd.to_numeric(s["CF"], errors="coerce"),
            "land_use": s["Land use"].astype(str),
        }
    ).reset_index(drop=True)


def mpsb_bins() -> pd.DataFrame:
    """MPsizeBase 'Literature PSD data': one row per size bin of a measured size distribution."""
    p = pd.read_excel(MPSB, sheet_name="Literature PSD data", header=2)
    p = p.loc[:, [c for c in p.columns if not str(c).startswith("Unnamed")]]
    return p[p["PSD_ID"].notna()].reset_index(drop=True)


def fit_alpha(bins: pd.DataFrame, min_bins: int = 4) -> pd.DataFrame:
    """Per distribution: α from log10(normalised concentration) on log10(bin geometric mean size).

    n(d) ∝ d^−α, so the slope is −α. Least squares in log space over the bins with a positive
    concentration; distributions with fewer than `min_bins` such bins are dropped (PREREG P3).
    """
    rows = []
    for psd, g in bins.groupby("PSD_ID"):
        x = pd.to_numeric(g["Geom_mean_size"], errors="coerce")
        y = pd.to_numeric(g["Normalized_concentration"], errors="coerce")
        ok = (x > 0) & (y > 0)
        if ok.sum() < min_bins:
            continue
        slope = np.polyfit(np.log10(x[ok]), np.log10(y[ok]), 1)[0]
        source_alpha = pd.to_numeric(g["cumsum_powerlaw_alpha"], errors="coerce").dropna()
        rows.append(
            {
                "psd_id": psd,
                "sample_type": str(g["Sample_type"].iat[0]),
                "study": str(g["Study"].iat[0]),
                "bins": int(ok.sum()),
                "alpha": float(-slope),
                "alpha_source": float(source_alpha.iat[0]) if len(source_alpha) else np.nan,
                "lat": pd.to_numeric(g["Lat"], errors="coerce").iat[0],
                "lon": pd.to_numeric(g["Lon"], errors="coerce").iat[0],
            }
        )
    return pd.DataFrame(rows)


def _pangaea(path: Path) -> tuple[pd.DataFrame, tuple[float, float]]:
    """A PANGAEA .tab file and the size window its own citation names, e.g. '(S-MP, 11-500 µm)'."""
    text = path.read_text(encoding="utf-8")
    head, body = text.split("*/\n", 1)
    m = re.search(r"\((?:S|L)-MP, (\d+)-(\d+) µm\)", head)
    if not m:
        raise ValueError(f"{path}: no size window in the citation")
    return pd.read_csv(io.StringIO(body), sep="\t"), (float(m.group(1)), float(m.group(2)))


def weser() -> tuple[pd.DataFrame, dict]:
    """The two Weser fractions at the same stations: one study, two complementary size windows."""
    s, win_s = _pangaea(WESER_S)
    lg, win_l = _pangaea(WESER_L)
    for t in (s, lg):
        t["station"] = t["Event"].str.split("_").str[-1]
    m = s.merge(lg, on="station", suffixes=("_s", "_l"))
    col = "Microplastic [#/m**3]"
    out = pd.DataFrame(
        {
            "station": m["station"],
            "location": m["Location_s"],
            "date": m["Date/Time_s"].astype(str).str[:10],
            "small": m[f"{col}_s"],
            "large": m[f"{col}_l"],
        }
    )
    # A station with no large particles has no ratio. Dividing would give inf, which pandas keeps
    # inside a median without a word (it moved the median from 5 237 to 5 340 before this guard).
    out["ratio"] = np.where(out.large > 0, out.small / out.large.where(out.large > 0), np.nan)
    return out, {"small_um": list(win_s), "large_um": list(win_l)}


def window_ratio(alpha: float, small: tuple[float, float], large: tuple[float, float]) -> float:
    """Power-law count in `small` over the count in `large`, for n(d) ∝ d^−α (α ≠ 1)."""
    return (small[0] ** (1 - alpha) - small[1] ** (1 - alpha)) / (
        large[0] ** (1 - alpha) - large[1] ** (1 - alpha)
    )


def implied_alpha(ratio: float, small: tuple[float, float], large: tuple[float, float]) -> float:
    """The power-law α at which counts in `small` outnumber those in `large` by `ratio`."""
    lo, hi = 1.01, 6.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if window_ratio(mid, small, large) < ratio:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2
