"""Read the printed unit out of the article, rather than trusting a transcription.

A unit is a property of the paper. When it is retyped — by a worker or a model — it can
arrive as `m²/Vs` where the paper printed `cm²/Vs`, and the conversion is then wrong by
10⁴ with nothing to catch it: that is exactly how 25 mobility rows were stored as 400
instead of 4.00. This module finds the unit where it was printed (a table header, a
caption, or the sentence carrying the number) so the claim can be checked against it.

Run it on any paper to see what the article actually prints:

    python -m mnp.extract units --pmcid PMC11117817
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from mnp.corpus import jats
from mnp.extract import coerce
from mnp.schema.models import Quantity, Unit

# A printed unit is either parenthesised, comma-separated, or trailing: "(mV)",
# ", mV", "in mV". Take the longest plausible run of unit characters.
_UNIT_CHARS = r"[A-Za-zµμ0-9⁻⁰¹²³⁴⁵⁶⁷⁸⁹·×x/^\-\s\.]"
_PARENS = re.compile(rf"\(({_UNIT_CHARS}{{1,40}}?)\)")
_AFTER_COMMA = re.compile(rf",\s*({_UNIT_CHARS}{{1,40}})$")

_OUTSIDE_EXPONENT = re.compile(r"(?:10|1e)\s*-\s*\d+")
_SUPERSCRIPTS = str.maketrans(
    {
        "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7",
        "⁸": "8", "⁹": "9", "⁻": "-", "⁺": "+",
    }
)  # fmt: skip


def _ascii(text: str) -> str:
    """Dashes and superscripts flattened, so one pattern matches every typesetting."""
    flattened = jats.normalise_minus(text).translate(str.maketrans({d: "-" for d in jats._DASHES}))
    return flattened.translate(_SUPERSCRIPTS)


_ZETA_KW = re.compile(r"zeta|ζ|z-?potential", re.IGNORECASE)
_MOB_KW = re.compile(r"mobilit|\bE\.?\s?M\.?\b|\bEPM\b", re.IGNORECASE)
# In prose the unit follows the number directly.
# Matched against _ascii(line): a number, then the unit that follows it.
_PROSE_UNIT = re.compile(
    r"[-+]?\d+(?:[.,]\d+)?\s*(?:±\s*\d+(?:[.,]\d+)?\s*)?"
    r"((?:mV\b|[\sA-Za-zµμ0-9/·×x^.-]{2,40}?"
    r"(?:V\s*-\s*1\s*s\s*-\s*1|/\s*V\s*s|V\s*-\s*1\s*s)))",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class UnitMention:
    """A unit as the article prints it, with what it means numerically."""

    text: str
    unit: Unit
    factor: float
    quantity: Quantity | None = None
    location: str = ""
    header: str = ""
    source: str = ""  # header | caption | prose

    @property
    def is_mobility(self) -> bool:
        return self.unit is Unit.um_cm_per_Vs


def _quantity_of(text: str) -> Quantity | None:
    if _MOB_KW.search(text):
        return Quantity.electrophoretic_mobility
    if _ZETA_KW.search(text):
        return Quantity.zeta_potential
    return None


def unit_in(text: str) -> UnitMention | None:
    """The unit printed in this header or caption fragment, if any.

    Candidates are tried longest-first so "10-8 m2 V-1 s-1" wins over "m2".
    """
    if not text:
        return None
    # Priority: what is written as a unit beats the whole fragment, so the reported
    # text is "cm 2/Vs" rather than "E. M. (cm 2/Vs)". Within a tier, longest wins, so
    # "10-8 m2 V-1 s-1" beats "m2".
    parens = [m.group(1).strip() for m in _PARENS.finditer(text)]
    after = _AFTER_COMMA.search(text.strip())
    tiers = [parens, [after.group(1).strip()] if after else [], [text.strip()]]
    # "linear mobility × 10 –4 (cm 2 V -1 s -1)" keeps its exponent OUTSIDE the
    # brackets; reading the bracket alone drops a factor of 1e-4.
    outside = _PARENS.sub("", text)
    if _OUTSIDE_EXPONENT.search(_ascii(outside)):
        tiers.insert(0, [text.strip()])
    quantity = _quantity_of(text)
    for tier in tiers:
        best: UnitMention | None = None
        for cand in sorted({c for c in tier if c}, key=len, reverse=True):
            unit, factor = coerce.normalise_unit(cand)
            if unit is None:
                continue
            # A bare size column must not masquerade as a measurement.
            if unit is Unit.mV and not _ZETA_KW.search(text) and "mv" not in cand.lower():
                continue
            best = UnitMention(text=cand, unit=unit, factor=factor, quantity=quantity)
            break
        if best is not None:
            return best
    return None


def _table_units(table_id: str, caption: str, rows: list[str]) -> list[UnitMention]:
    location = f"Table {table_id}"
    out: list[UnitMention] = []
    # A table is column-oriented (units in the header row) or row-oriented (units in
    # each row's leading label). Both appear in this corpus, so read both.
    labels: list[str] = list(rows[0].split("\t")) if rows else []
    labels += [r.split("\t")[0] for r in rows[1:] if r.split("\t")[0]]
    seen: set[str] = set()
    for cell in labels:
        if cell in seen:
            continue
        seen.add(cell)
        m = unit_in(cell)
        if m is None or m.quantity is None:
            continue
        out.append(UnitMention(m.text, m.unit, m.factor, m.quantity, location, cell, "header"))
    if not out:
        m = unit_in(caption)
        if m is not None and m.quantity is not None:
            out.append(
                UnitMention(m.text, m.unit, m.factor, m.quantity, location, caption, "caption")
            )
    return out


def find_units(text: str) -> list[UnitMention]:
    """Every printed unit in an extraction text, with where it was printed."""
    out: list[UnitMention] = []
    location = "text"
    table_id: str | None = None
    caption = ""
    rows: list[str] = []

    def flush():
        nonlocal rows, caption
        if table_id is not None and rows:
            out.extend(_table_units(table_id, caption, rows))
        rows, caption = [], ""

    for line in text.splitlines():
        header = re.match(r"^== (?:Table (\S+)|(.+))$", line.strip())
        if header:
            flush()
            table_id = header.group(1)
            location = f"Table {table_id}" if table_id else (header.group(2) or "text")
            continue
        if not line.strip():
            continue
        if table_id is not None:
            if "\t" in line:
                rows.append(line)
            elif not rows:
                caption = f"{caption} {line}".strip()
            continue
        quantity = _quantity_of(line)
        if quantity is None:
            continue
        for m in _PROSE_UNIT.finditer(_ascii(line)):
            mention = unit_in(f"({m.group(1)})")
            if mention is None:
                continue
            out.append(
                UnitMention(
                    mention.text, mention.unit, mention.factor, quantity, location, line, "prose"
                )
            )
            break
    flush()
    return out


def report(text: str) -> list[dict]:
    """find_units as plain rows, one per printed unit."""
    return [
        {
            "location": u.location,
            "source": u.source,
            "quantity": u.quantity.value if u.quantity else None,
            "unit": u.text,
            "canonical": u.unit.value,
            "factor": u.factor,
            "header": u.header[:80],
        }
        for u in find_units(text)
    ]


def disagrees(claimed: str | None, printed: UnitMention | None) -> bool:
    """Would the claimed unit convert differently from the one the article prints?

    Only a difference in the numeric factor matters: "cm2/Vs" and "cm² V⁻¹ s⁻¹" agree,
    while "m2/Vs" against a printed "cm2/Vs" is a factor of 10⁴ and must be caught.
    """
    if printed is None or not claimed:
        return False
    unit, factor = coerce.normalise_unit(claimed)
    if unit is None or unit is not printed.unit:
        return False
    return abs(factor - printed.factor) > 1e-9 * max(factor, printed.factor)
