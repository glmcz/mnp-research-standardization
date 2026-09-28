"""The standardisation walk: one `Step` per condition, in a fixed order.

The rules are the ratified ones in `docs/2026-09-21-cile-a-otazky-pro-vedce.md` Part 1 (G1
walks one paper through them by hand): absence is never imputed, a condition derived from a
printed composition is a different claim from one the paper states directly, and an unreported
condition's reason must name the specific cause the row shows — conductivity printed instead
of ionic strength, a buffer named without its composition, a culture or biological medium,
pure/DI water, which is a reported medium and an unreported ionic strength, never zero, or a
printed 0 mM, which since 2026-09-28 is not a reported ionic strength either.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from mnp.corpus import lines as corpus_lines
from mnp.corpus.lines import LinedDoc
from mnp.extract.zeta import ZERO_IONIC_STRENGTH

CONDITIONS: tuple[str, ...] = ("medium", "ionic_strength", "pH", "temperature", "instrument")

#: A number is printed, just not the one the walk needs.
CONDUCTIVITY_RE = re.compile(r"µS|μS|mS\s*/\s*cm|conductiv", re.IGNORECASE)
#: A buffer named by its common name, with no printed composition to derive from.
BUFFER_RE = re.compile(r"\bPBS\b|\bHEPES\b|\bTris\b|\bMES\b|phosphate buffer", re.IGNORECASE)
#: Composition not printed, and a corona changes what "the particle" even means.
CULTURE_MEDIUM_CLASSES = frozenset({"culture_medium", "biofluid"})
#: Flags that sharpen the *derived* reason when the extraction recorded one.
_DERIVED_FLAGS = ("derived_from_composition", "ionic_strength_from_medium")


@dataclass(frozen=True)
class Step:
    """One condition's verdict for one row. `verdict` is one of the four the walk knows."""

    condition: str
    verdict: str  # reported | derived | nominal | unreported
    reason: str
    citations: tuple[str, ...] = ()


def _str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def _float(value: Any) -> float | None:
    text = _str(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def _citations(row: Mapping[str, Any], doc: LinedDoc) -> tuple[str, ...]:
    """`PMCID:Lnn` for every one of the row's `evidence_line_ids` that resolves in `doc`.

    The table carries one evidence set per row, not one per condition, so every `Step` of a
    row cites the same lines — the ones the extraction actually read to fill that row in.
    """
    pmcid = _str(row.get("pmcid"))
    resolved: list[tuple[int, str]] = []
    for line_id in _str(row.get("evidence_line_ids")).split(";"):
        line_id = line_id.strip()
        if not line_id:
            continue
        line = corpus_lines.resolve_id(doc, line_id)
        if line is not None:
            resolved.append((line.n, f"{pmcid}:L{line.n}"))
    resolved.sort()
    seen: set[str] = set()
    out: list[str] = []
    for _, cite in resolved:
        if cite not in seen:
            seen.add(cite)
            out.append(cite)
    return tuple(out)


def _medium_step(row: Mapping[str, Any], citations: tuple[str, ...]) -> Step:
    if _bool(row.get("medium_reported")):
        text = _str(row.get("medium_text"))
        return Step("medium", "reported", f'a liquid is named: "{text}"', citations)
    return Step("medium", "unreported", "no liquid is named anywhere in the row", citations)


def _ionic_strength_cause(row: Mapping[str, Any]) -> str:
    """Why this row's ionic strength is unreported — the specific cause, not a generic one."""
    medium_text = _str(row.get("medium_text"))
    medium_class = _str(row.get("medium_class"))
    if ZERO_IONIC_STRENGTH in _str(row.get("flags")).split(";"):
        return (
            f'0 mM is printed ("{medium_text}"), and 0 mM is not a reported ionic strength: '
            '"no added electrolyte" says nothing was added, not that the medium holds no ions '
            "(ratified 2026-09-28)"
        )
    if CONDUCTIVITY_RE.search(medium_text):
        return (
            f'conductivity is printed instead of ionic strength ("{medium_text}"); converting '
            "conductivity to ionic strength needs an assumed ionic composition, which is never "
            "assumed here"
        )
    if BUFFER_RE.search(medium_text):
        return (
            f'a buffer is named ("{medium_text}") without its printed composition; the nominal '
            "ionic strength of a named buffer is never looked up"
        )
    if medium_class in CULTURE_MEDIUM_CLASSES:
        return (
            f'the medium is a culture or biological medium ("{medium_text}"); its composition '
            "is not printed as a checkable ionic strength"
        )
    if medium_class == "DI_water":
        return (
            f'the medium is named as pure/DI water ("{medium_text}"); DI water does not mean '
            "ionic strength zero — absence is never imputed"
        )
    if not medium_text:
        return "nothing is printed for the medium at all, so there is nothing to derive from"
    return f'nothing printed gives an ionic strength for "{medium_text}"'


def _ionic_strength_step(row: Mapping[str, Any], citations: tuple[str, ...]) -> Step:
    source = _str(row.get("ionic_strength_source"))
    if source == "inferred_from_named_salt":
        value = _float(row.get("ionic_strength_mM"))
        value_text = f"{value:g} mM" if value is not None else "an ionic strength"
        flags = _str(row.get("flags"))
        note = f" (flagged: {flags})" if any(f in flags for f in _DERIVED_FLAGS) else ""
        return Step(
            "ionic_strength",
            "derived",
            f"{value_text} computed from the paper's printed salt composition, never a "
            f"looked-up nominal value{note}",
            citations,
        )
    if _bool(row.get("ionic_strength_reported")):
        value = _float(row.get("ionic_strength_mM"))
        value_text = f"{value:g} mM" if value is not None else "a value"
        return Step("ionic_strength", "reported", f"{value_text} stated directly", citations)
    return Step("ionic_strength", "unreported", _ionic_strength_cause(row), citations)


def _pH_step(row: Mapping[str, Any], citations: tuple[str, ...]) -> Step:
    if _bool(row.get("pH_reported")):
        ph = _float(row.get("pH"))
        if ph is not None:
            return Step("pH", "reported", f"pH {ph:g} stated directly", citations)
        text = _str(row.get("pH_text"))
        return Step("pH", "reported", f'a pH range is stated directly: "{text}"', citations)
    return Step("pH", "unreported", "no pH number or range is printed", citations)


def _temperature_step(row: Mapping[str, Any], citations: tuple[str, ...]) -> Step:
    qualifier = _str(row.get("temperature_qualifier"))
    if qualifier:
        return Step(
            "temperature",
            "nominal",
            f'temperature is given only as "{qualifier}", never as a number; it counts as '
            "reported, but is flagged nominal rather than treated as a measured value",
            citations,
        )
    temp = _float(row.get("temperature_C"))
    if temp is not None:
        return Step("temperature", "reported", f"{temp:g} °C stated directly", citations)
    return Step(
        "temperature",
        "unreported",
        "no measurement temperature is printed; an incubation, exposure or storage "
        "temperature never counts as the measurement temperature, even when it is the only "
        "one the paper gives",
        citations,
    )


def _instrument_step(row: Mapping[str, Any], citations: tuple[str, ...]) -> Step:
    if _bool(row.get("instrument_reported")):
        text = _str(row.get("instrument"))
        return Step("instrument", "reported", f'an instrument is named: "{text}"', citations)
    return Step("instrument", "unreported", "no instrument, brand or family is named", citations)


def walk_row(row: Mapping[str, Any], doc: LinedDoc) -> tuple[Step, ...]:
    """The five conditions of one row, each with a verdict, a reason and its citations.

    Order is fixed: medium, ionic_strength, pH, temperature, instrument — the order the demo
    page renders them in, and the order `CONDITIONS` names.
    """
    citations = _citations(row, doc)
    return (
        _medium_step(row, citations),
        _ionic_strength_step(row, citations),
        _pH_step(row, citations),
        _temperature_step(row, citations),
        _instrument_step(row, citations),
    )
