"""Power-law rescaling of particle-number concentrations to a common size range.

Microplastic size distributions follow pdf ∝ x^−α (Kooi & Koelmans 2019, ES&T Lett
6:551). A concentration counted over the measured window [x1M, x2M] is moved onto the
default window [x1D, x2D] with

    CF = (x2D^(1−α) − x1D^(1−α)) / (x2M^(1−α) − x1M^(1−α))   for α ≠ 1
    CF = ln(x2D / x1D) / ln(x2M / x1M)                        at α = 1

    rescaled = measured × CF

(Koelmans et al. 2020, ES&T 54:12307, eq. 2). Default target 1–5000 µm, α = 1.6; the
second target 0.1–5000 µm makes the nano point. The α sensitivity set mixes published
fits (1.3, 1.6, 2.0) with values read from the abstract of Kooi et al. 2021 (Water Res
202:117429, paywalled) — every output row carries `alpha_source` so that is visible.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable

import numpy as np
import pandas as pd
from scipy.integrate import quad

ALPHA_DEFAULT = 1.6
TARGET_DEFAULT = (1.0, 5000.0)
TARGET_NANO = (0.1, 5000.0)
TARGETS = (TARGET_DEFAULT, TARGET_NANO)
ALPHA_SENSITIVITY = (1.3, 1.6, 2.0, 2.2, 2.6, 3.1)
UPPER_ASSUMED_UM = 5000.0

ALPHA_SOURCE_PUBLISHED = "Kooi & Koelmans 2019 ES&T Lett 6:551; Koelmans et al. 2020 ES&T 54:12307"
ALPHA_SOURCE_ABSTRACT = "Kooi et al. 2021 Water Res 202:117429 (abstract only, paywalled)"
_ABSTRACT_ONLY = (2.2, 2.6, 3.1)


def alpha_source(alpha: float) -> str:
    if any(math.isclose(alpha, a) for a in _ABSTRACT_ONLY):
        return ALPHA_SOURCE_ABSTRACT
    return ALPHA_SOURCE_PUBLISHED


def _check_range(x1: float, x2: float, name: str) -> None:
    if not (0 < x1 < x2):
        raise ValueError(f"{name} range must satisfy 0 < min < max, got ({x1}, {x2})")


def cf_closed(
    x1m: float,
    x2m: float,
    x1d: float = TARGET_DEFAULT[0],
    x2d: float = TARGET_DEFAULT[1],
    alpha: float = ALPHA_DEFAULT,
) -> float:
    """Closed-form correction factor; the α = 1 branch is the limit of the general one."""
    _check_range(x1m, x2m, "measured")
    _check_range(x1d, x2d, "target")
    if math.isclose(alpha, 1.0, abs_tol=1e-12):
        return math.log(x2d / x1d) / math.log(x2m / x1m)
    p = 1.0 - alpha
    return (x2d**p - x1d**p) / (x2m**p - x1m**p)


def cf_numeric(x1m: float, x2m: float, x1d: float, x2d: float, alpha: float) -> float:
    """Same ratio by numerical quadrature of x^−α; the oracle for `cf_closed`."""
    _check_range(x1m, x2m, "measured")
    _check_range(x1d, x2d, "target")
    num, _ = quad(lambda x: x**-alpha, x1d, x2d)
    den, _ = quad(lambda x: x**-alpha, x1m, x2m)
    return num / den


def rescale(
    value: float,
    x1m: float,
    x2m: float,
    target: tuple[float, float] = TARGET_DEFAULT,
    alpha: float = ALPHA_DEFAULT,
) -> float:
    return value * cf_closed(x1m, x2m, target[0], target[1], alpha)


_MASS = re.compile(r"^(?:µg|μg|ug|mg|g|kg)\b", re.I)
_NUMBER = re.compile(r"^(?:#|(?:n|p|mps?|sal|particles?|items?|pieces?|fibres?|fibers?)\b)", re.I)
_PER = re.compile(r"(?:/|\s+per\s+|\s+)\s*(l|litre|liter|m-?3|km-?2|m-?2|kg|g)\b(?:\s*-1)?", re.I)


def _split_unit(unit: str) -> tuple[str, str] | None:
    text = unit.strip().replace("−", "-")
    # "SAL L-1" style: numerator, space, denominator with a trailing -1
    match = _PER.search(text)
    if match is None:
        return None
    numerator = text[: match.start()].strip()
    denominator = match.group(1).lower().replace("-", "")
    return numerator, denominator


def classify_unit(unit: str | None) -> str:
    """'number' for particle counts (rescalable), 'mass' for µg/mg/g, else 'unknown'."""
    if not unit or not isinstance(unit, str):
        return "unknown"
    parts = _split_unit(unit)
    if parts is None:
        return "unknown"
    numerator, _ = parts
    if _MASS.match(numerator):
        return "mass"
    if _NUMBER.match(numerator):
        return "number"
    return "unknown"


_VOLUME_TO_L = {"l": 1.0, "litre": 1.0, "liter": 1.0, "m3": 1e-3}
_AREA_TO_KM2 = {"km2": 1.0, "m2": 1e6}


def normalise_unit(unit: str) -> tuple[str, float]:
    """Map a number unit to ('n/L' | 'n/km2', factor) so values can be compared."""
    parts = _split_unit(unit)
    if parts is None:
        raise ValueError(f"cannot normalise unit {unit!r}")
    _, denominator = parts
    if denominator in _VOLUME_TO_L:
        return "n/L", _VOLUME_TO_L[denominator]
    if denominator in _AREA_TO_KM2:
        return "n/km2", _AREA_TO_KM2[denominator]
    raise ValueError(f"unit {unit!r} is neither per volume nor per area")


def target_label(target: tuple[float, float]) -> str:
    lo, hi = target
    return f"{lo:g}-{hi:g} µm"


REQUIRED_COLUMNS = (
    "study",
    "size_min_um",
    "size_max_um",
    "concentration_value",
    "concentration_unit",
)


def _prepare(table: pd.DataFrame) -> pd.DataFrame:
    """One row per study: fill the assumed upper bound, decide exclusion, normalise units."""
    missing = [c for c in REQUIRED_COLUMNS if c not in table.columns]
    if missing:
        raise ValueError(f"table is missing columns {missing}")
    rows = table.copy().reset_index(drop=True)
    rows["size_min_um"] = pd.to_numeric(rows["size_min_um"], errors="coerce")
    rows["size_max_um"] = pd.to_numeric(rows["size_max_um"], errors="coerce")
    rows["concentration_value"] = pd.to_numeric(rows["concentration_value"], errors="coerce")

    rows["upper_assumed"] = rows["size_min_um"].notna() & rows["size_max_um"].isna()
    rows.loc[rows["upper_assumed"], "size_max_um"] = UPPER_ASSUMED_UM

    reasons: list[str | None] = []
    unit_norm: list[str | None] = []
    value_norm: list[float] = []
    for _, r in rows.iterrows():
        kind = classify_unit(r["concentration_unit"])
        reason = None
        norm, factor = None, math.nan
        if pd.isna(r["concentration_value"]):
            reason = "no_concentration"
        elif kind == "mass":
            reason = "mass_units"
        elif kind == "unknown":
            reason = "unknown_units"
        elif r["concentration_value"] <= 0:
            reason = "non_positive_value"
        elif pd.isna(r["size_min_um"]):
            reason = "no_size_range"
        elif not (0 < r["size_min_um"] < r["size_max_um"]):
            reason = "invalid_size_range"
        if kind == "number":
            try:
                norm, factor = normalise_unit(r["concentration_unit"])
            except ValueError:
                reason = reason or "unknown_units"
        reasons.append(reason)
        unit_norm.append(norm)
        value_norm.append(r["concentration_value"] * factor if norm else math.nan)
    rows["excluded_reason"] = pd.Series(reasons, dtype="object")
    rows["unit_norm"] = pd.Series(unit_norm, dtype="object")
    rows["value_norm"] = value_norm
    return rows


def rescale_table(
    table: pd.DataFrame,
    targets: Iterable[tuple[float, float]] = TARGETS,
    alphas: Iterable[float] = ALPHA_SENSITIVITY,
) -> pd.DataFrame:
    """Long table: one row per study × target × α, excluded rows kept with NaN factors."""
    base = _prepare(table)
    blocks = []
    for target in targets:
        for alpha in alphas:
            block = base.copy()
            block["target"] = target_label(target)
            block["target_min_um"] = target[0]
            block["target_max_um"] = target[1]
            block["alpha"] = alpha
            block["alpha_source"] = alpha_source(alpha)
            cf = np.full(len(block), np.nan)
            ok = block["excluded_reason"].isna().to_numpy()
            for i in np.flatnonzero(ok):
                cf[i] = cf_closed(
                    block.at[i, "size_min_um"], block.at[i, "size_max_um"], *target, alpha
                )
            block["cf"] = cf
            block["rescaled_value"] = block["value_norm"] * cf
            blocks.append(block)
    return pd.concat(blocks, ignore_index=True)
