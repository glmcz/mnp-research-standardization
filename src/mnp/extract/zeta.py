"""Extract one paper: prompt → coerce → verify against the article → record.

Three independent checks stand between the model and the statistics:
- `coerce` parses every number deterministically (tested in test_coerce.py);
- `verify_row` checks the value against the *line* the row cites and every reported
  condition against the *quote*, and the two scopes differ on purpose: the worker writes
  the quote and can trim it until its own number passes, whereas a line is the paper's;
  but a line is a whole paragraph, so a condition supported only elsewhere in that
  paragraph was carried across experiments, which is an inference, not a reading
  (Martin's scope rule, 2026-09-13). A condition must also appear in the article;
- `find_candidates` locates every printed zeta/mobility number by regex, so
  recall can be estimated per paper without a gold set.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

from mnp.corpus import jats, lines
from mnp.extract import coerce, prompts, units
from mnp.extract.llm import LLMClient, LLMError, ParseError
from mnp.schema import models
from mnp.schema.models import Quantity, SurfaceMeasurement

Measurement = SurfaceMeasurement  # the extraction target IS the schema row

MAX_TOKENS = 12_000
_ZETA_KW = re.compile(r"zeta|ζ|\bZP\b(?=[^A-Za-z0-9-])|surface potential|charg", re.IGNORECASE)
_MOB_KW = re.compile(r"mobilit", re.IGNORECASE)
_D = r"-?\d+(?:[.,]\d+)?"  # a decimal point or a decimal comma
_SD = r"-?\d+(?:[.,]\d+)?"  # a printed SD occasionally carries a stray minus
# The deviation can sit on either side of the unit: "-13.7 ± 2.1 mV" and
# "-13.7 mV ± 2.1" are both printed in this corpus.
# The unit may be spelled out, and a closing bracket may sit between the number and it:
# "(-17.90 ± 0.42) mV" and "-30 millivolts" are both printed in this corpus.
_MV = r"(?:mV|m\.?\s?volts?|millivolts?)\b"
_MV_NUM = re.compile(
    rf"({_D})\s*(?:±\s*({_SD})\s*)?[)\]]?\s*{_MV}(?:\s*±\s*({_SD}))?", re.IGNORECASE
)
_MOB_NUM = re.compile(
    rf"({_D})\s*(?:±\s*({_SD})\s*)?"
    r"(?:[×x·]\s*10\s*\^?\s*-\s*8|(?:µ|μ|u)m\s*·?\s*cm|10\s*-\s*8)"
    rf"(?:\s*±\s*({_SD}))?",
    re.IGNORECASE,
)


def _f(raw: str | None) -> float | None:
    """A matched number, decimal comma included."""
    return None if raw is None else float(raw.replace(",", "."))


def _sd(*raws: str | None) -> float | None:
    """A standard deviation is a magnitude, printed before or after the unit."""
    for raw in raws:
        v = _f(raw)
        if v is not None:
            return abs(v)
    return None


def _nearest(pattern: re.Pattern, line: str, start: int) -> int | None:
    """Distance from `start` to the closest match of `pattern`, or None."""
    best = None
    for m in pattern.finditer(line):
        d = (
            0
            if m.start() <= start <= m.end()
            else min(abs(m.start() - start), abs(m.end() - start))
        )
        best = d if best is None else min(best, d)
    return best


def _other_quantity_near(line: str, start: int) -> bool:
    """Is this number some other millivolt quantity rather than a zeta potential?

    Whichever quantity name is *closer* owns the number. A paragraph arrives here as a
    single line, so asking only "does this line mention an electron microscope" once threw
    away two real zeta values because a microscope was named later in the same paragraph.
    """
    other = _nearest(_NOT_ZETA, line, start)
    if other is None:
        return False
    mine = _nearest(_ZETA_KW, line, start)
    return mine is None or other < mine


_INEQUALITY_BEFORE = re.compile(r"[<>≤≥]\s*$")


def _is_bound(line: str, start: int) -> bool:
    """Is this number an inequality bound? "<0 mV" means negative, not zero."""
    return bool(_INEQUALITY_BEFORE.search(line[max(0, start - 4) : start]))


def _in_citation(line: str, start: int) -> bool:
    """Is this number inside a bracketed citation list, as in "[4,5]"?"""
    open_bracket = line.rfind("[", 0, start)
    if open_bracket < 0:
        return False
    close = line.find("]", open_bracket)
    return close == -1 or close > start


_HEADER = re.compile(r"^== (Table (\S+)|.+)$")


@dataclass
class Candidate:
    value: float
    quantity: Quantity
    context: str
    location: str
    sd: float | None = None
    # "the zeta potentials were ± 45 and ± 20": the paper names a magnitude, not a sign.
    sign_unknown: bool = False

    def as_dict(self) -> dict:
        d = asdict(self)
        d["quantity"] = self.quantity.value
        return d


# Some papers print a zeta potential with no unit at all: "a zeta potential of -32.0",
# "the zeta potentials of PS and PVC MPs were ± 45 and ± 20". The quantity is named, so
# the number is a measurement; a number carrying some OTHER unit is not.
_OTHER_UNIT = re.compile(
    r"\s*(?:nm|µm|μm|um|mm|%|°|K\b|h\b|hr|min|mg|µg|ug|mL|ml|mM|kDa|ppm|rpm|cm|Hz)",
    re.IGNORECASE,
)
# "...zeta potential was measured at pH = 7": the number belongs to pH, not to zeta.
_FOREIGN_QUANTITY = re.compile(
    r"\b(?:pH|temperature|temp|size|diameter|concentration|dose|time|n|N|radius|"
    r"volume|mass|ratio|pKa|IEP)\b[^A-Za-z0-9]{0,4}$",
    re.IGNORECASE,
)
_UNITLESS_ZETA = re.compile(
    r"(?:zeta|ζ)[\s-]?potentials?[^.\n]{0,60}?"
    r"(?:\bof\b|\bwas\b|\bwere\b|\bis\b|\bare\b|[:=])\s*"
    r"(±\s*)?(-?\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
# Other things are measured in millivolts. A line about an applied voltage, a membrane
# potential or an electrode is not reporting a particle's zeta potential.
_NOT_ZETA = re.compile(
    r"applied voltage|applied potential|membrane potential|electrode|Ag/AgCl|"
    r"redox potential|potential difference|action potential|field strength|"
    # "3.5 MV single stage electrostatic accelerator": megavolts, not millivolts. The
    # unit match is case-insensitive because one paper prints a zeta as "6.63 MV".
    r"accelerating|accelerator|\bbeam\b|kV\b|electron microscop",
    re.IGNORECASE,
)
_MV_UNIT = re.compile(r"\bmv\b|\(\s*mv\s*\)", re.IGNORECASE)
_MOB_UNIT = re.compile(r"10\s*-?\s*8|(?:µ|μ|u)m\s*·?\s*cm|m2\s*v", re.IGNORECASE)


def _table_header_quantity(cell: str, caption_quantity: Quantity | None = None) -> Quantity | None:
    """The quantity a header cell denotes.

    A cell naming the quantity speaks for itself. A cell carrying only a unit
    ("Before Treatment (mV)") is claimed by the caption's quantity if it has one —
    that is how a table captioned "Zeta potential of the effluents" is read. A unit
    that disagrees with the caption (nm, PDI) is never claimed.
    """
    low = cell.lower()
    # "mobility" alone is not electrophoretic mobility: "High mobility group box
    # transcription factor 1" is a gene, and it once produced 42 phantom candidates from
    # one gene-expression table. Demand electrophoresis or a mobility unit.
    named = _MOB_KW.search(low) and ("electrophor" in low or _MOB_UNIT.search(low))
    if named or re.search(r"\bepm\b", low):
        return Quantity.electrophoretic_mobility
    if _NOT_ZETA.search(low):
        return None  # a membrane, applied or redox potential is not a zeta potential
    if _ZETA_KW.search(low) and ("mv" in low or "potential" in low):
        return Quantity.zeta_potential
    # One paper heads its columns "MPS-zate(mv)" — a typo, and no "potential" either,
    # which hid 42 values. A column measured in millivolts that is neither some other
    # potential (excluded above) nor a size is the quantity, whatever it calls itself.
    if _MV_UNIT.search(low) and not _SIZE_KW.search(low):
        return Quantity.zeta_potential
    if caption_quantity is Quantity.zeta_potential and _MV_UNIT.search(low):
        return caption_quantity
    if caption_quantity is Quantity.electrophoretic_mobility and _MOB_UNIT.search(low):
        return caption_quantity
    return None


_WORD = re.compile(r"[A-Za-z]{3,}")
# Words that may legitimately sit in a numeric cell.
_CELL_WORDS = {"mv", "nm", "um", "mm", "and", "to", "cm", "vs"}


_SIZE_KW = re.compile(r"\bsize\b|diameter|\bnm\b|\bhydrodynamic\b", re.IGNORECASE)


def _cell_value(cell: str, quantity: Quantity):
    """(value, sd) for a cell, preferring the part that carries the quantity's own unit.

    A column can hold two quantities at once — "Size (ζ-potential)" over cells reading
    "95 nm (-13.7 mV ± 2.1)". Taking the first number there yields a particle size
    reported as a zeta potential, so when a unit is present it decides.
    """
    pattern = _MV_NUM if quantity is Quantity.zeta_potential else _MOB_NUM
    m = pattern.search(jats.normalise_minus(cell))
    if m:
        return _f(m.group(1)), _sd(m.group(2), m.group(3))
    if _SIZE_KW.search(cell):
        return None, None  # a sized cell with no unit of ours is not our measurement
    v, sd, flags = coerce.parse_number(cell)
    return (None, None) if v is None or "range" in flags else (v, sd)


def _looks_like_data(cell: str) -> bool:
    """A data cell is a number, not prose.

    Colspan expansion repeats a header across the columns it covers, so a header such as
    "Zeta Potential (mV) ± Stdev (n = 3)" can arrive where a value is expected and parse
    as 3.0. Prose cells ("not determined", "see Figure 2") are equally not measurements.
    """
    return not any(w.group(0).lower() not in _CELL_WORDS for w in _WORD.finditer(cell))


def _table_candidates(table_id: str, rows: list[str], caption: str = "") -> list[Candidate]:
    out: list[Candidate] = []
    grid = [r.split("\t") for r in rows]
    location = f"Table {table_id}"
    caption_q = _table_header_quantity(caption) if caption else None
    column_q: dict[int, str] = {}
    for r_idx, cells in enumerate(grid):
        q = _table_header_quantity(cells[0], caption_q) if cells else None
        if q is not None:
            for cell in cells[1:]:
                if not _looks_like_data(cell):
                    continue
                v, sd = _cell_value(cell, q)
                if v is not None:
                    out.append(Candidate(v, q, cells[0], location, sd))
            continue
        if r_idx == 0 or not column_q:
            for c_idx, cell in enumerate(cells):
                if _table_header_quantity(cell, caption_q) is not None:
                    column_q[c_idx] = cell
        if r_idx > 0 and column_q:
            for c_idx, header in column_q.items():
                if c_idx < len(cells) and _looks_like_data(cells[c_idx]):
                    q = _table_header_quantity(header, caption_q)
                    v, sd = _cell_value(cells[c_idx], q)
                    if v is not None:
                        out.append(Candidate(v, q, header, location, sd))
    return out


def find_candidates(text: str) -> list[Candidate]:
    """Every printed zeta/mobility number in extraction text, by regex alone."""
    text = jats.normalise_minus(text)
    out: list[Candidate] = []
    table_id: str | None = None
    table_rows: list[str] = []
    table_caption = ""
    location = "text"

    # extraction_text can print one sentence twice (a keyword window and its own
    # section). Scanning a line we have already scanned would double-count every number
    # in it; two identical cells inside one table row are still two measurements.
    seen: set[tuple] = set()

    def flush():
        nonlocal table_rows, table_caption
        if table_id is not None and table_rows:
            key = (table_id, tuple(table_rows))
            if key not in seen:
                seen.add(key)
                out.extend(_table_candidates(table_id, table_rows, table_caption))
        table_rows = []
        table_caption = ""

    for line in text.split("\n"):
        h = _HEADER.match(line)
        if h:
            flush()
            table_id = h.group(2)
            location = h.group(1)
            continue
        if table_id is not None:
            if not line.strip():  # pieces are separated by a blank line
                flush()
                table_id = None
                continue
            if "\t" in line:
                table_rows.append(line)
                continue
            if not table_rows:  # lines before the first row are the caption
                table_caption = f"{table_caption} {line}".strip()
            # caption or footnote: also falls through to the prose regexes below
        line_key = ("line", _norm(line))
        if line_key in seen:
            continue
        seen.add(line_key)
        if _ZETA_KW.search(line):
            claimed: list[tuple[int, int]] = []
            for m in _MV_NUM.finditer(line):
                if (
                    _in_citation(line, m.start())
                    or _other_quantity_near(line, m.start())
                    or _is_bound(line, m.start())
                ):
                    continue
                claimed.append(m.span(1))
                out.append(
                    Candidate(
                        _f(m.group(1)),
                        Quantity.zeta_potential,
                        line,
                        location,
                        _sd(m.group(2), m.group(3)),
                    )
                )
            for m in _UNITLESS_ZETA.finditer(line):
                span = m.span(2)
                if _other_quantity_near(line, span[0]):
                    continue
                if any(a <= span[0] < b for a, b in claimed):
                    continue  # already captured with its unit
                if _in_citation(line, span[0]) or _OTHER_UNIT.match(line[span[1] : span[1] + 6]):
                    continue  # the number belongs to some other quantity
                if _FOREIGN_QUANTITY.search(line[m.start() : span[0]]):
                    continue  # ...and nor does a number introduced by pH, size, n, ...
                out.append(
                    Candidate(
                        _f(m.group(2)),
                        Quantity.zeta_potential,
                        line,
                        location,
                        None,
                        bool(m.group(1)),
                    )
                )
        if _MOB_KW.search(line):
            for m in _MOB_NUM.finditer(line):
                if (
                    _in_citation(line, m.start())
                    or _other_quantity_near(line, m.start())
                    or _is_bound(line, m.start())
                ):
                    continue
                out.append(
                    Candidate(
                        _f(m.group(1)),
                        Quantity.electrophoretic_mobility,
                        line,
                        location,
                        _sd(m.group(2), m.group(3)),
                    )
                )
    flush()
    # An abstract restates the body. A value it repeats is one measurement printed twice,
    # not two; a value only it prints is still a printed value.
    elsewhere = {(c.quantity, round(c.value, 2)) for c in out if c.location != "Abstract"}
    return [
        c
        for c in out
        if c.location != "Abstract" or (c.quantity, round(c.value, 2)) not in elsewhere
    ]


def check_units(m, claimed_units: set[str], article_text: str) -> list[str]:
    """Compare a row's claimed unit against the unit the article prints.

    The unit is the one field a transcription can get wrong without leaving a trace in
    the value: "cm2/Vs" retyped as "m2/Vs" converts 1e4 times too large and still looks
    like a number. So the article's own printed unit is the authority.
    """
    printed = [
        u for u in units.find_units(article_text) if u.quantity is m.quantity and u.unit is m.unit
    ]
    if not printed:
        return []
    for claimed in claimed_units:
        if any(units.disagrees(claimed, p) for p in printed):
            return ["unit_disagrees_with_article"]
    return []


# -- verification ------------------------------------------------------------------

STEP_TEMPERATURE = "temperature_step_not_measurement"
OTHER_STEP_TEMPERATURE = "temperature_from_other_step"
ZERO_IONIC_STRENGTH = "ionic_strength_zero_not_reported"
BUFFER_IONIC_STRENGTH = "buffer_concentration_not_ionic_strength"


def _norm(s: str) -> str:
    """Whitespace- and dash-insensitive form, for comparing a quote with the article.

    `coerce` flattens every dash while parsing a value, so a range it stored as "-2--3"
    must be compared against a quote that still prints "\u22122\u2013\u22123" — normalise both the
    same way or the comparison fails on the punctuation alone.
    """
    flattened = jats.normalise_minus(s).translate(str.maketrans({d: "-" for d in jats._DASHES}))
    return re.sub(r"\s+", " ", flattened).strip()


def _number_in(value: float, text: str) -> bool:
    """Is this number printed in text?

    Sign-agnostic and digit-bounded, and the decimal separator may be a point or a
    comma: papers written in several European languages print "-35,2 mV", and matching
    only the point form flagged correctly-extracted rows as unsupported.
    """
    mag = abs(value)
    for form in {f"{mag:g}", f"{mag:.1f}", f"{mag:.2f}"}:
        pattern = r"(?<![\d.,])" + re.escape(form).replace(r"\.", r"[.,]") + r"(?:0+)?(?![\d])"
        if re.search(pattern, text):
            return True
    return False


_KELVIN = re.compile(r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(?:±\s*\d+(?:[.,]\d+)?\s*)?K\b")


def _temperature_in(celsius: float, text: str) -> bool:
    """Is this temperature printed in text, in °C or in kelvin? "298 ± 0.1K" is stored as
    24.85 °C, and looking only for "24.85" flagged it as absent (PMC9687657)."""
    if _number_in(celsius, text):
        return True
    return any(
        abs(float(m.group(1).replace(",", ".")) - 273.15 - celsius) < 0.06
        for m in _KELVIN.finditer(text)
    )


def _ionic_number_in(mM: float, text: str) -> bool:
    """Is this ionic strength printed in text: as its mM number, or in another unit as a salt's
    concentration or a stated ionic strength (`coerce.ionic_concentration_in`)?"""
    return _number_in(mM, text) or coerce.ionic_concentration_in(text, mM)


def _cited_runs(doc: lines.LinedDoc, ev: models.Evidence) -> list[str]:
    """The lines this row cites, folded, one string per run of *consecutive* lines.

    Contiguity is what keeps the guard a guard. `lines._match` answers a passage with every
    line each of its newline-separated fragments hits, which is right for a locator and
    would be wrong here: case 4 of `verify_adversarial.json` glues a table header to a
    distant row and lands on lines 1 and 3. Cutting the citation at every gap in the
    numbering means a passage has to sit inside one uninterrupted stretch of the paper.

    Measured before it was written, so that the rule separates the fabrication from the
    legitimate case rather than merely excluding both: all 16 stored rows whose quote
    carries a literal newline — a caption plus the table rows beneath it — span consecutive
    lines, and the fabricated one does not.

    A row with no stored citation is located from its quote. That is the state every row is
    in at extraction time, before `extract retrofit` writes the address down.
    """
    cited = {ln.n for ident in ev.line_ids or () if (ln := lines.resolve_id(doc, ident))}
    runs: list[list[int]] = []
    for n in sorted(cited) if cited else sorted(set(lines.locate(doc, ev.quote))):
        if runs and n == runs[-1][-1] + 1:
            runs[-1].append(n)
        else:
            runs.append([n])
    return [" ".join(_norm(doc.lines[n - 1].text) for n in run) for run in runs]


def verify_row(
    m: SurfaceMeasurement, full_text: str, doc: lines.LinedDoc | None = None
) -> list[str]:
    """Flags for anything the article does not support. Mutates m.evidence.verified.

    The halves of this check read different haystacks, and the difference is deliberate:

    - **the value, and whether the evidence exists at all, are checked against the lines
      the row cites.** The worker writes the quote and is then judged on it, so trimming it
      until the guard passes works, and five sweep workers did exactly that. A line belongs
      to the paper, not to the worker, and holds nothing to trim.
    - **every condition is checked against the quote** — Martin's scope rule of 2026-09-13,
      unchanged. A line is a paragraph and routinely covers several experiments: 16 lines in
      the committed table are cited by rows at more than one ionic strength, 69 rows in all,
      the widest line spanning 0.1 to 100 mM. The sentence stays the unit within which a
      condition is established, or a condition read from the experiment next door reads as
      this row's own.

    `doc` is optional because a caller may have only a string: the adversarial fixture in
    `eval.stages` is text, not an article. Without it the value and the quote are checked
    as they were before line citation existed.
    """
    flags: list[str] = []
    text = _norm(full_text)
    if m.evidence is None or not m.evidence.quote:
        flags.append("evidence_missing")
        quote = ""
    else:
        quote = _norm(m.evidence.quote)
        parts = [p.strip() for p in quote.split("||") if p.strip()]
        if doc is None or not doc.lines:
            m.evidence.verified = bool(parts) and all(p in text for p in parts)
            cited = quote
        else:
            runs = _cited_runs(doc, m.evidence)
            m.evidence.verified = bool(parts) and all(any(p in r for r in runs) for p in parts)
            cited = " ".join(runs)
        if not m.evidence.verified:
            flags.append("evidence_unverified")
        if m.value is not None:
            if not _number_in(m.value, cited):
                flags.append("value_not_in_quote")
        elif m.value_text and m.value_text != "not printed" and _norm(m.value_text) not in cited:
            flags.append("value_text_not_in_quote")
    c = m.conditions
    if c.pH is not None and not _number_in(c.pH, text):
        flags.append("pH_not_in_text")
    if c.pH_text:
        nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", c.pH_text)]
        if nums and not all(_number_in(x, text) for x in nums):
            flags.append("pH_not_in_text")
    if c.temperature_C is not None and not _temperature_in(c.temperature_C, text):
        flags.append("temperature_not_in_text")
    if c.ionic_strength_mM is not None:
        ok = _ionic_number_in(c.ionic_strength_mM, text)
        if not ok and c.medium_text:
            ok = _norm(c.medium_text) in text
        if not ok and c.ionic_strength_source is models.ValueSource.inferred_from_named_salt:
            ok = True  # computed from a named salt; the salt string was checked above
        if not ok:
            flags.append("ionic_strength_not_in_text")
    flags += _scope_flags(c, quote)
    return flags


def _sentence_with(celsius: float, quote: str) -> str:
    """The sentence of a `" || "`-joined quote that carries this temperature, or the whole quote.

    A passage is often several sentences. "...Zetasizer Ultra at 25 °C. Suspensions were ...
    sonicated for 30 min before measurement." put the sonication's "before measurement" in the
    measurement temperature's piece, and R2 cleared a temperature the paper ties to the
    instrument (PMC12929567, PMC12886875).
    """
    for piece in quote.split("||"):
        for sentence in _SENTENCE_END.split(piece):
            if _temperature_in(celsius, sentence):
                return sentence
    return quote


def _scope_flags(c, quote: str) -> list[str]:
    """A condition is only established where the paper states it.

    Martin's rule, 2026-09-13: a condition applies within the experiment that states it and
    does not propagate to other preparations unless the paper says it does. What that makes
    checkable is the row's own evidence — quote the sentence that establishes the condition
    (join separate sentences with " || "). A condition found in the article but not in this
    row's quote was carried from somewhere else, which is the reading the rule forbids.

    "Own evidence" here means the **quote**, never the line the row cites, and `verify_row`
    deliberately hands this function the one and not the other. The line is a paragraph:
    69 rows in the committed table cite a line covering more than one ionic strength, the
    widest spanning 0.1 to 100 mM, so reading a condition off the paragraph would make the
    neighbouring experiment's number look like this row's.
    """
    flags: list[str] = []
    if not quote:
        return flags
    if c.pH is not None and not _number_in(c.pH, quote):
        flags.append("pH_not_in_evidence")
    elif c.pH_text and (nums := [float(x) for x in re.findall(r"\d+(?:\.\d+)?", c.pH_text)]):
        if not all(_number_in(x, quote) for x in nums):
            flags.append("pH_not_in_evidence")
    if c.temperature_C is not None:
        if not _temperature_in(c.temperature_C, quote):
            flags.append("temperature_not_in_evidence")
        elif coerce.OTHER_STEP_RE.search(_sentence_with(c.temperature_C, quote)):
            # the number is attached to incubation or exposure *in its own sentence* of the
            # quote. Testing the whole join flagged correct rows whenever any other piece
            # mentioned a culture or an exposure, so workers trimmed their evidence to clear
            # it — the guard was punishing the more complete quote.
            flags.append(STEP_TEMPERATURE)
    if c.ionic_strength_mM is not None and not _ionic_in(c, quote):
        flags.append("ionic_strength_not_in_evidence")
    return flags


def _ionic_in(c, quote: str) -> bool:
    """Is the ionic strength supported by this quote — as a number, a medium, or a salt?"""
    if _ionic_number_in(c.ionic_strength_mM, quote):
        return True
    if c.medium_text and _norm(c.medium_text) in quote:
        return True
    if c.ionic_strength_source is models.ValueSource.inferred_from_named_salt:
        return bool(coerce.SALT_RE.search(quote))
    return False


# -- record --------------------------------------------------------------------------


# A temperature as a paper prints one: a number, perhaps "± x", then a degree sign. The ring
# (˚) and the ordinal (º) stand in for the degree sign often enough to matter.
_DEGREES = re.compile(r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(?:±\s*\d+(?:[.,]\d+)?\s*)?[°˚º℃]")
_SENTENCE_END = re.compile(r"(?<=[.;!?])\s+(?=[A-Z(])")


def step_only(text: str) -> dict[float, bool]:
    """Every temperature `text` prints → whether each sentence printing it is about another step.

    A step sentence is one `coerce.OTHER_STEP_RE` matches: storage, incubation, exposure,
    culture, digestion. One sentence outside a step is enough to say False, because the paper
    may be stating the measurement there.
    """
    only: dict[float, bool] = {}
    for line in text.splitlines():
        for sentence in _SENTENCE_END.split(line):
            step = bool(coerce.OTHER_STEP_RE.search(sentence))
            for m in _DEGREES.finditer(sentence):
                value = float(m.group(1).replace(",", "."))
                only[value] = only.get(value, True) and step
    return only


def _other_step_temperature(
    c: models.MeasurementConditions, quote: str, paper: dict[float, bool] | None
) -> bool:
    """R2b: is this temperature another step's, read from outside the row's own quote?

    The row's source for a temperature its quote does not state is its medium label, when the
    label prints it, and otherwise the paper. It is another step's when that source prints it
    only in a step phrase.
    """
    t = c.temperature_C
    if t is None or _temperature_in(t, quote):
        return False
    if c.medium_text and t in (label := step_only(c.medium_text)):
        return label[t]
    return bool(paper and paper.get(t))


def row_conditions(
    c: models.MeasurementConditions,
    flags: list[str],
    quote: str = "",
    paper: dict[float, bool] | None = None,
) -> tuple[models.MeasurementConditions, list[str]]:
    """The conditions a table row carries, after the rules Martin ratified on 2026-09-28 and 29.

    All keep the row and clear the value. R1: an ionic strength of exactly 0 mM is not a
    reported one: "no added electrolyte" says nothing was added, not that the medium holds no
    ions, and absence is never imputed. R2: a temperature the verifier tied to an incubation or
    exposure step is not the measurement temperature, even when the paper gives no other.
    R2b: nor is a temperature the row's quote does not state, when its source prints it only
    for storage, incubation, exposure or culture — the medium label "RPMI (stored at 37 ˚C for
    24 h)" (PMC8719689), or a paper whose only 37 °C is an incubation in gastric fluid.
    R3 (2026-10-03): a buffer's concentration taken as a reported ionic strength is not one.
    "10 mM phosphate buffer pH 7.0" holds about 18 mM of ions, and the brief already says a
    component whose speciation the paper does not print contributes nothing. A paper that
    calls its number an ionic strength keeps it.

    `paper` is `step_only` of the article; without it R2b reads the row alone.

    Applied here and not in the record, which stays what the model read: that is provenance,
    and the rule can be revisited without re-reading a paper. The `*_reported` properties are
    computed from the fields, so the copy re-derives them.
    """
    update: dict = {}
    flags = list(flags)
    if c.ionic_strength_mM == 0:
        update["ionic_strength_mM"] = None
        update["ionic_strength_source"] = models.ValueSource.unreported
        if ZERO_IONIC_STRENGTH not in flags:
            flags.append(ZERO_IONIC_STRENGTH)
    if (
        c.ionic_strength_source == models.ValueSource.reported
        and c.ionic_strength_mM
        and coerce.buffer_concentration(f"{c.medium_text or ''} || {quote}", c.ionic_strength_mM)
    ):
        update["ionic_strength_mM"] = None
        update["ionic_strength_source"] = models.ValueSource.unreported
        if BUFFER_IONIC_STRENGTH not in flags:
            flags.append(BUFFER_IONIC_STRENGTH)
    if STEP_TEMPERATURE in flags or _other_step_temperature(c, quote, paper):
        update["temperature_C"] = None
        update["temperature_qualifier"] = None
        if STEP_TEMPERATURE not in flags and OTHER_STEP_TEMPERATURE not in flags:
            flags.append(OTHER_STEP_TEMPERATURE)
    return (c.model_copy(update=update) if update else c), flags


def _quote_of(m: SurfaceMeasurement) -> str:
    return _norm(m.evidence.quote) if m.evidence and m.evidence.quote else ""


def needs_paper(m: SurfaceMeasurement) -> bool:
    """Does R2b have to read the paper for this row: a temperature neither its quote nor its
    medium label prints?"""
    t = m.conditions.temperature_C
    if t is None:
        return False
    label = step_only(m.conditions.medium_text or "")
    return not _temperature_in(t, _quote_of(m)) and t not in label


@dataclass
class ExtractionRecord:
    pmcid: str
    doi: str | None
    model: str | None
    prompt_sha256: str
    # Which brief the judgement was made under. None means the record predates brief
    # tracking and cannot be traced to its instructions — see extract.provenance.
    brief_path: str | None = None
    brief_sha256: str | None = None
    measurements: list[SurfaceMeasurement] = field(default_factory=list)
    row_flags: list[list[str]] = field(default_factory=list)
    dropped: list[dict] = field(default_factory=list)
    n_candidates: int = 0
    n_candidates_matched: int = 0
    unmatched_candidates: list[dict] = field(default_factory=list)
    error: str | None = None
    cached: bool = False
    extraction_tokens: int = 0
    # provider-reported usage of the call behind this record; extraction_tokens is len/4
    model_prompt_tokens: int | None = None
    model_completion_tokens: int | None = None
    methods_source: str | None = None
    year: int | None = None
    journal: str | None = None

    @property
    def coverage(self) -> float | None:
        return self.n_candidates_matched / self.n_candidates if self.n_candidates else None

    def to_json(self) -> str:
        d = asdict(self)
        d["measurements"] = [m.model_dump(mode="json") for m in self.measurements]
        return json.dumps(d, ensure_ascii=False)

    @classmethod
    def from_json(cls, line: str) -> ExtractionRecord:
        d = json.loads(line)
        d["measurements"] = [SurfaceMeasurement.model_validate(m) for m in d["measurements"]]
        return cls(**d)

    def to_rows(self, paper: str | None = None) -> list[dict]:
        """One dict per measurement. `paper` is the article's full text, which R2b needs only
        for a row where `needs_paper` holds."""
        steps = step_only(paper) if paper else None
        rows = []
        for m, stored_flags in zip(self.measurements, self.row_flags, strict=True):
            c, flags = row_conditions(m.conditions, stored_flags, _quote_of(m), steps)
            rows.append(
                {
                    "pmcid": self.pmcid,
                    "doi": self.doi,
                    "year": self.year,
                    "journal": self.journal,
                    "row_id": m.row_id,
                    "particle_name": m.particle_name,
                    "material": m.material,
                    "functionalisation": m.functionalisation,
                    "supplier": m.supplier,
                    "size_nominal_nm": m.size_nominal_nm,
                    "size_measured_nm": m.size_measured_nm,
                    "quantity": m.quantity.value,
                    "value": m.value,
                    "value_text": m.value_text,
                    "unit": m.unit.value,
                    "sd": m.sd,
                    "n": m.n,
                    "medium_text": c.medium_text,
                    "medium_class": c.medium_class.value,
                    "ionic_strength_mM": c.ionic_strength_mM,
                    "ionic_strength_source": c.ionic_strength_source.value,
                    "pH": c.pH,
                    "pH_text": c.pH_text,
                    "temperature_C": c.temperature_C,
                    "temperature_qualifier": c.temperature_qualifier,
                    "instrument": c.instrument,
                    "medium_reported": c.medium_reported,
                    "ionic_strength_reported": c.ionic_strength_reported,
                    "pH_reported": c.pH_reported,
                    "temperature_reported": c.temperature_reported,
                    "instrument_reported": c.instrument_reported,
                    "conditions_complete": c.conditions_complete,
                    "medium_matches_exposure": m.medium_matches_exposure,
                    "evidence_quote": m.evidence.quote if m.evidence else None,
                    "evidence_location": m.evidence.location if m.evidence else None,
                    "evidence_verified": bool(m.evidence and m.evidence.verified),
                    "evidence_line_ids": (
                        ";".join(m.evidence.line_ids)
                        if m.evidence and m.evidence.line_ids
                        else None
                    ),
                    "flags": ";".join(flags),
                    "model": self.model,
                    "prompt_sha256": self.prompt_sha256,
                }
            )
        return rows


def _rows_from(data: dict) -> list:
    for key in ("measurements", "rows", "results", "data"):
        if key in data:
            v = data[key]
            return v if isinstance(v, list) else [v]
    for v in data.values():
        if isinstance(v, list):
            return v
    return [data] if "value" in data else []


def _match(cands: list[Candidate], ms: list[SurfaceMeasurement]) -> tuple[int, list[dict]]:
    """One-to-one: an extracted row claims at most one printed number, so a table
    that prints the same value for two particles needs two rows to be covered."""
    claimed: set[int] = set()
    for m in ms:
        if m.value is None:
            continue
        # Closest fit, not first fit: two particles in one table can print values inside
        # each other's tolerance window (-31.09 beside -31.13), and first-fit hands a row
        # its neighbour's number while reporting its own as missing.
        best: tuple[float, int] | None = None
        for i, c in enumerate(cands):
            if i in claimed or m.quantity is not c.quantity:
                continue
            gap = abs(abs(m.value) - abs(c.value)) if c.sign_unknown else abs(m.value - c.value)
            if gap <= 0.05 + 0.01 * abs(c.value) and (best is None or gap < best[0]):
                best = (gap, i)
        if best is None:
            continue
        hit = best[1]
        claimed.add(hit)
        # The same number printed in a table and restated in the text is one
        # measurement, so this row claims those too. Two identical cells inside the
        # same table are two measurements and still need a row each.
        here = cands[hit]
        for i, c in enumerate(cands):
            if i in claimed or c.location == here.location:
                continue
            if c.quantity is here.quantity and abs(c.value - here.value) <= 1e-9:
                claimed.add(i)
    unmatched = [c.as_dict() for i, c in enumerate(cands) if i not in claimed]
    return len(claimed), unmatched


def _new_record(article: jats.Article, text: str) -> ExtractionRecord:
    return ExtractionRecord(
        pmcid=article.pmcid or "unknown",
        doi=article.doi,
        model=None,
        prompt_sha256=prompts.prompt_sha256(),
        extraction_tokens=jats.approx_tokens(text),
        methods_source=article.methods_source,
        year=article.year,
        journal=article.journal,
    )


#: Every flag `verify_row` can raise. `reverify` replaces exactly these on a stored row and keeps
#: the rest, which the coercer and the unit check raised from the raw reply.
VERIFY_FLAGS = frozenset(
    {
        "evidence_missing",
        "evidence_unverified",
        "value_not_in_quote",
        "value_text_not_in_quote",
        "pH_not_in_text",
        "pH_not_in_evidence",
        "temperature_not_in_text",
        "temperature_not_in_evidence",
        STEP_TEMPERATURE,
        "ionic_strength_not_in_text",
        "ionic_strength_not_in_evidence",
    }
)


def reverify(rec: ExtractionRecord, article: jats.Article) -> list[list[str]]:
    """The row flags `rec` would carry under today's verifier. A verifier fix makes every stored
    flag stale at once, and re-reading a paper to refresh them would cost a model call."""
    doc = lines.build_lines(article)
    return [
        [f for f in old if f not in VERIFY_FLAGS] + verify_row(m, article.full_text, doc)
        for m, old in zip(rec.measurements, rec.row_flags, strict=True)
    ]


def extract_from_payload(article: jats.Article, data: dict, model: str) -> ExtractionRecord:
    """Coerce, verify and score a parsed model reply — whoever produced it."""
    text = jats.extraction_text(article, max_tokens=MAX_TOKENS)
    # Uncapped, unlike `text`: the guard may look at a line the token budget kept the model
    # from seeing, but never the other way round.
    doc = lines.build_lines(article)
    record = _new_record(article, text)
    record.model = model
    candidates = find_candidates(text)
    record.n_candidates = len(candidates)
    for i, raw in enumerate(_rows_from(data)):
        if not isinstance(raw, dict):
            record.dropped.append({"index": i, "flags": ["not_an_object"]})
            continue
        m, flags = coerce.coerce_measurement(raw)
        if m is None:
            record.dropped.append({"index": i, "flags": flags})
            continue
        flags = flags + verify_row(m, article.full_text, doc)
        claimed = {str(raw.get("unit"))} if raw.get("unit") else set()
        flags = flags + check_units(m, claimed, text)
        m.row_id = f"{record.pmcid}-r{len(record.measurements) + 1}"
        record.measurements.append(m)
        record.row_flags.append(flags)
    record.n_candidates_matched, record.unmatched_candidates = _match(
        candidates, record.measurements
    )
    return record


def extract_paper(article: jats.Article, client: LLMClient) -> ExtractionRecord:
    text = jats.extraction_text(article, max_tokens=MAX_TOKENS)
    pmcid = article.pmcid or "unknown"
    try:
        data, completion = client.complete_json(
            prompts.system_prompt(), prompts.user_prompt(pmcid, text)
        )
    except (LLMError, ParseError) as e:
        record = _new_record(article, text)
        record.error = str(e)
        candidates = find_candidates(text)
        record.n_candidates = len(candidates)
        record.unmatched_candidates = [c.as_dict() for c in candidates]
        return record
    record = extract_from_payload(article, data, completion.model)
    record.cached = completion.cached
    record.model_prompt_tokens = completion.prompt_tokens
    record.model_completion_tokens = completion.completion_tokens
    return record
