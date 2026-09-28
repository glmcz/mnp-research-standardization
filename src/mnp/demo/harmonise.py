"""Rebuilds FINDINGS E2b's conversion-model scan and turns a reported zeta or mobility into a
harmonised value.

Zeta is not measured. Electrophoretic mobility is measured, and zeta is a model-dependent
conversion of it: mu = (2*eps*zeta / 3*eta) * f(kappa*a), with f in [1, 1.5] between the
Huckel and Smoluchowski limits. A paper that reports zeta has already applied some f_m to get
there; if it never says which, the number it printed is underdetermined by a factor of up to
1.5 before any question of missing conditions arises. That is E2b's headline, corrected once
in FINDINGS.md ("the denominator was wrong"): of 485 papers reporting a zeta value, 33 name
the model; of 13 reporting a mobility, 6 do.

Nothing here imputes a missing parameter. A row missing ionic strength or size has no kappa*a
and gets an interval, never a point produced by guessing which end of [1, 1.5] applied. A
mobility row missing temperature gets no value at all, because eta and eps are temperature
dependent and there is no water-property default to fall back on that would not be a guess.

`models_named` records *mentions*, not the model actually applied - a paper can name
Smoluchowski in a background paragraph and use something else entirely. Every harmonised
value below is therefore conditional on "the named model is the one applied"; that is an
upper bound in the same sense the E2b scan itself is.
"""

from __future__ import annotations

import functools
import math
import re
from dataclasses import dataclass
from typing import Any

import pandas as pd

from mnp import config
from mnp.corpus import jats
from mnp.ek.constants import permittivity, viscosity
from mnp.eval.comparability import ZetaRow, henry_f
from mnp.schema.models import Quantity, Unit

# --- the conversion-model scan (FINDINGS E2b) ----------------------------------------------
#
# Smoluchowski and Huckel are counted on the bare surname: neither is a word that shows up by
# accident in a colloid-science paper. Henry is different - "Henry" alone collides with
# citations, co-author surnames and other uses in this corpus - so it is counted only when it
# names the function/equation/formula, which is the widened pattern FINDINGS E2b needed to
# move the zeta denominator from "all 851 readable papers" to "485 papers reporting a zeta
# value" and get 33/452 instead of the wrong 48/803 read against the wrong denominator.

_SMOLUCHOWSKI_RE = re.compile(r"smoluchowski", re.IGNORECASE)
_HUCKEL_RE = re.compile(r"h(?:u|ü)ckel", re.IGNORECASE)
_OHSHIMA_RE = re.compile(r"ohshima", re.IGNORECASE)
_HENRY_RE = re.compile(r"henry(?:'s)?\s+(?:function|equation|formula)", re.IGNORECASE)

_MODEL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("smoluchowski", _SMOLUCHOWSKI_RE),
    ("huckel", _HUCKEL_RE),
    ("ohshima", _OHSHIMA_RE),
    ("henry", _HENRY_RE),
)

#: Naming Henry's function/equation, or Ohshima's approximation to it, means the paper did not
#: assume a single fixed f_m, so there is no f_m to have gotten wrong. See `_zeta_case` for how
#: that is used.
#:
#: Naming *both* textbook limits together (Smoluchowski and Huckel, neither Henry nor Ohshima)
#: is deliberately NOT in this set, correcting the design doc's original rule (Martin,
#: 2026-09-28): that usually means "we used Smoluchowski rather than Huckel", i.e. a specific,
#: single f_m - and a mention scan cannot tell which one was applied. It is treated as an
#: unknown f_m, exactly like no model named at all; see `_zeta_case`.
_HENRY_CONSISTENT_TRIGGER = frozenset({"henry", "ohshima"})

#: f_m each single named textbook limit assumes. Smoluchowski = the thin-double-layer limit
#: (kappa*a >> 1), Huckel = the thick-double-layer limit (kappa*a << 1).
_MODEL_FM: dict[str, float] = {"smoluchowski": 1.5, "huckel": 1.0}

#: The only mobility unit this corpus prints. 1 um*cm/(V*s) = 1e-8 m^2/(V*s).
_MOBILITY_UNIT_TO_SI: dict[str, float] = {Unit.um_cm_per_Vs.value: 1e-8}


@functools.cache
def models_named(pmcid: str) -> frozenset[str]:
    """Conversion models named in `pmcid`'s vendored full text: a subset of {smoluchowski,
    huckel, henry, ohshima}. Cached, since `scan` calls it once per paper in the table but a
    render pass may ask again for the same pmcid.

    Case-insensitive. A missing XML (should not happen for a vendored pmcid, but the corpus is
    not the ground truth of the filesystem) yields no models rather than raising.
    """
    path = config.EPMC_XML_DIR / f"{pmcid}.xml"
    if not path.is_file():
        return frozenset()
    article = jats.parse(path.read_bytes())
    text = article.full_text
    return frozenset(name for name, pattern in _MODEL_PATTERNS if pattern.search(text))


@dataclass(frozen=True)
class ScanResult:
    """Denominators are *papers with a row of that quantity*, value null or not: a paper that
    printed the row at all made the claim, whether or not the number survived extraction. That
    is what reproduces FINDINGS E2b's 485/33/452 and 13/6 - counting only rows with a non-null
    value undercounts the denominator (348 and 9, not 485 and 13) and does not match.
    """

    zeta_papers: int
    zeta_named: int
    mobility_papers: int
    mobility_named: int

    @property
    def zeta_not_named(self) -> int:
        return self.zeta_papers - self.zeta_named

    @property
    def mobility_not_named(self) -> int:
        return self.mobility_papers - self.mobility_named


def scan(table: pd.DataFrame) -> ScanResult:
    """The E2b census on the current `d1_zeta_table.csv`. See `ScanResult` for the denominator
    rule; see the module docstring for the published numbers this must reproduce.
    """
    zeta_pmcids = table.loc[table["quantity"] == Quantity.zeta_potential.value, "pmcid"].unique()
    mobility_pmcids = table.loc[
        table["quantity"] == Quantity.electrophoretic_mobility.value, "pmcid"
    ].unique()
    zeta_named = sum(1 for pmcid in zeta_pmcids if models_named(str(pmcid)))
    mobility_named = sum(1 for pmcid in mobility_pmcids if models_named(str(pmcid)))
    return ScanResult(
        zeta_papers=len(zeta_pmcids),
        zeta_named=zeta_named,
        mobility_papers=len(mobility_pmcids),
        mobility_named=mobility_named,
    )


# --- harmonisation ---------------------------------------------------------------------------


def _clean(value: Any) -> Any:
    """Mirrors `comparability._clean`: NaN and blank strings are absence, not zero."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _as_float(value: Any) -> float | None:
    value = _clean(value)
    return None if value is None else float(value)


def _as_str(value: Any) -> str | None:
    value = _clean(value)
    return None if value is None else str(value)


@dataclass(frozen=True)
class Harmonised:
    """One row's harmonised zeta. `point` is set only when the correction is fully determined;
    otherwise `low`/`high` bound it and `point` stays `None`. `low <= high` always, whatever the
    sign of `reported_value`. `why` is a one-line, human-readable reason a reviewer can check
    against the row without opening this module.
    """

    row_id: str
    quantity: Quantity
    reported_value: float | None
    unit: str | None
    model: str | None
    kappa_a: float | None
    f: float | None
    low: float | None
    high: float | None
    point: float | None
    why: str


def _sorted_bounds(a: float, b: float) -> tuple[float, float]:
    return (a, b) if a <= b else (b, a)


#: model, kappa_a, f, low, high, point, why - the seven pieces `Harmonised` needs beyond the
#: reported value and unit, shared by both branches below so `harmonise` can stay a plain
#: dispatch with no unpacking gymnastics.
_Case = tuple[
    str | None,
    float | None,
    float | None,
    float | None,
    float | None,
    float | None,
    str,
]


def _zeta_case(value: float, kappa_a: float | None, models: frozenset[str]) -> _Case:
    """The four cases in the design doc, plus the Henry-consistent one, plus one correction to
    the design doc.

    Deviation 1, stated plainly: the design says a Henry/Ohshima-named paper gets "(point if
    kappa*a known)". Henry's function has no assumed f_m to have gotten wrong at *any*
    kappa*a - that is the entire content of it being the general function the two named limits
    approximate - so the correction ratio f_m/f(kappa*a) is 1 by construction and does not
    depend on whether kappa*a is known. The rule implemented here is: the point is always the
    reported value in this branch; kappa_a and f are reported alongside it only when they are
    independently computable, purely for the reviewer's context, never gating the value.

    Deviation 2, a correction made in the parent session's review of this module's first pass
    on 2026-09-28 (recorded in docs/DESIGN_2026-09-28_demo.md): naming *both*
    Smoluchowski and Huckel (with neither Henry nor Ohshima named) is NOT Henry-consistent.
    That combination usually means "we used Smoluchowski rather than Huckel" - a specific,
    single f_m - and a mention scan cannot tell which one was applied ("used Smoluchowski
    rather than Huckel" reads identically to the reverse in the text). It is treated exactly
    like no model named: f_m is unknown, in {1, 1.5}.
    """
    f = henry_f(kappa_a) if kappa_a is not None else None

    if models & _HENRY_CONSISTENT_TRIGGER:
        if kappa_a is not None:
            why = (
                "paper names Henry's function/Ohshima's approximation, so no fixed f_m was "
                f"assumed; kappa*a is known ({kappa_a:.3g}, f={f:.4f}) and shown for context; "
                "the reported value is taken as-is"
            )
        else:
            why = (
                "paper names Henry's function/Ohshima's approximation, so no fixed f_m was "
                "assumed; kappa*a is unreported, but nothing here needed correcting, so the "
                "reported value is taken as-is"
            )
        return "henry", kappa_a, f, None, None, value, why

    named = models & {"smoluchowski", "huckel"}
    if len(named) == 1:
        model = next(iter(named))
        f_m = _MODEL_FM[model]
        if kappa_a is not None:
            point = value * f_m / f
            why = (
                f"{model} named (f_m={f_m}); kappa*a known ({kappa_a:.3g}, f={f:.4f}): "
                f"zeta_true = zeta_rep * f_m / f(kappa*a)"
            )
            return model, kappa_a, f, None, None, point, why
        b1 = value * f_m * (1.0 / 1.5)
        b2 = value * f_m * (1.0 / 1.0)
        low, high = _sorted_bounds(b1, b2)
        why = (
            f"{model} named (f_m={f_m}); kappa*a unreported (ionic strength or size missing): "
            "interval over the true f(kappa*a) in [1, 1.5]"
        )
        return model, None, None, low, high, None, why

    # f_m is unknown here, either because no textbook limit was named, or because both were
    # named and a mention scan cannot tell which was actually applied (deviation 2 above).
    if named:
        source = "both Smoluchowski and Huckel are named, so which f_m was applied is undetermined"
    else:
        source = "no model named"

    if kappa_a is not None:
        p1 = value * 1.0 / f
        p2 = value * 1.5 / f
        low, high = _sorted_bounds(p1, p2)
        why = (
            f"{source}; kappa*a known ({kappa_a:.3g}, f={f:.4f}): interval over the unknown "
            "f_m in {1 (Huckel), 1.5 (Smoluchowski)}"
        )
        return None, kappa_a, f, low, high, None, why

    b1 = value * (1.0 / 1.5)
    b2 = value * 1.5
    low, high = _sorted_bounds(b1, b2)
    why = (
        f"{source} and kappa*a unreported: interval over the combined range of "
        "f_m / f(kappa*a), [1/1.5, 1.5]"
    )
    return None, None, None, low, high, None, why


def _mobility_case(row: ZetaRow, value: float, unit: str | None) -> _Case:
    """zeta = 3*eta*mu / (2*eps*f(kappa*a)). `models_named` plays no part: a mobility row is the
    raw observable, not a value some f_m has already been baked into, so the model field here
    is always `None`.
    """
    temperature_C = row.conditions.temperature_C
    if temperature_C is None:
        return None, row.kappa_a, None, None, None, None, "needs the measurement temperature"

    factor = _MOBILITY_UNIT_TO_SI.get(unit or "")
    if factor is None:
        why = f"unrecognised mobility unit {unit!r}"
        return None, row.kappa_a, None, None, None, None, why

    mu_si = value * factor
    eta = float(viscosity(temperature_C))
    eps = float(permittivity(temperature_C))
    kappa_a = row.kappa_a

    if kappa_a is not None:
        f = henry_f(kappa_a)
        point = (3.0 * eta * mu_si / (2.0 * eps * f)) * 1000.0  # V -> mV
        why = (
            f"electrophoretic mobility converted at T={temperature_C:g} degC; kappa*a known "
            f"({kappa_a:.3g}, f={f:.4f}): zeta = 3*eta*mu / (2*eps*f(kappa*a))"
        )
        return None, kappa_a, f, None, None, point, why

    z_at_f1 = (3.0 * eta * mu_si / (2.0 * eps * 1.0)) * 1000.0
    z_at_f15 = (3.0 * eta * mu_si / (2.0 * eps * 1.5)) * 1000.0
    low, high = _sorted_bounds(z_at_f1, z_at_f15)
    why = (
        f"electrophoretic mobility converted at T={temperature_C:g} degC; kappa*a unreported "
        "(ionic strength or size missing): interval over f(kappa*a) in [1, 1.5]"
    )
    return None, None, None, low, high, None, why


def harmonise(row_mapping: dict[str, Any], models: frozenset[str]) -> Harmonised:
    """Harmonise one row. `row_mapping` is a record from `d1_zeta_table.csv` (or an equivalent
    dict); `models` is `models_named(row_mapping["pmcid"])` - passed in rather than looked up
    here so a caller harmonising many rows of one paper computes it once.
    """
    row = ZetaRow.from_mapping(row_mapping)
    value = _as_float(row_mapping.get("value"))
    unit = _as_str(row_mapping.get("unit"))

    if value is None:
        return Harmonised(
            row_id=row.row_id,
            quantity=row.quantity,
            reported_value=None,
            unit=unit,
            model=None,
            kappa_a=row.kappa_a,
            f=None,
            low=None,
            high=None,
            point=None,
            why="no reported value to harmonise",
        )

    if row.quantity is Quantity.zeta_potential:
        model, kappa_a, f, low, high, point, why = _zeta_case(value, row.kappa_a, models)
    elif row.quantity is Quantity.electrophoretic_mobility:
        model, kappa_a, f, low, high, point, why = _mobility_case(row, value, unit)
    else:
        raise ValueError(f"unknown quantity {row.quantity!r}")

    return Harmonised(
        row_id=row.row_id,
        quantity=row.quantity,
        reported_value=value,
        unit=unit,
        model=model,
        kappa_a=kappa_a,
        f=f,
        low=low,
        high=high,
        point=point,
        why=why,
    )


def harmonise_paper(pmcid: str, table: pd.DataFrame) -> list[Harmonised]:
    """Every row of `pmcid` in `table`, harmonised. Convenience for the render pass, which
    needs this per case rather than per row.
    """
    models = models_named(pmcid)
    rows = table.loc[table["pmcid"] == pmcid].to_dict(orient="records")
    return [harmonise(row, models) for row in rows]
