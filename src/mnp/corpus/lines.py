"""The line-addressed document — S1 of `docs/DESIGN_2026-09-17_tool-value-grid.md` §2.

A line is one unit the parse already yields: a section title, a paragraph, a table
caption, one TSV row, a table footnote, a figure caption. Nothing is re-segmented, so
`render()` with the numbers stripped back off is `jats.extraction_text()` character for
character. That is the point — the model reads the same document the evidence guard
searches, and gains only a number to point at.

The model cites the number; ingest stores the `line_id`. The id hashes
(section_path, ordinal within that section, text) and never the global line number, so a
parser fix that shifts every number below it leaves stored citations intact.

Deterministic: no model, no network, no clock.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from mnp.corpus import jats

# The separator `extract.zeta.verify_row` already splits multi-passage evidence on.
EVIDENCE_SEP = "||"

# 16 hex chars = 64 bits. Collisions need ~4e9 lines; the corpus has ~4e4.
ID_LENGTH = 16

_UNIT = "\x1f"  # ASCII unit separator: cannot occur in normalised text
_WS = re.compile(r"\s+")
# `extract.zeta` reaches for the same private table; a publisher dash is a parse detail.
_DASH_TO_ASCII = str.maketrans({d: "-" for d in jats._DASHES})


@dataclass(frozen=True, slots=True)
class Line:
    n: int  # 1-based, global, and the only thing the model ever sees
    text: str
    section_path: str
    ordinal: int  # 0-based index within section_path
    line_id: str


@dataclass(frozen=True, slots=True)
class SectionSpan:
    """One `extraction_text` header and the half-open range of lines under it."""

    path: str
    header: str
    start: int
    stop: int


@dataclass(frozen=True, slots=True)
class LinedDoc:
    pmcid: str | None
    lines: tuple[Line, ...]
    sections: tuple[SectionSpan, ...]


def fold(text: str) -> str:
    """The comparison `extract.zeta.verify_row` already makes, kept identical to it.

    Every publisher dash flattened to ASCII, every run of whitespace to one space. A
    stored quote was verified against an article folded this way, so a line-addressed
    `locate` that insisted on exact text would reject 132 of the 1 890 rows the guard
    itself accepted — mostly table rows, whose TSV tabs the fold turns into spaces.
    """
    flat = jats.normalise_minus(text).translate(_DASH_TO_ASCII)
    return _WS.sub(" ", flat).strip()


def line_id(section_path: str, ordinal: int, text: str) -> str:
    """The durable address of a line. Deliberately blind to the line number."""
    key = f"{section_path}{_UNIT}{ordinal}{_UNIT}{text}".encode()
    return hashlib.sha256(key).hexdigest()[:ID_LENGTH]


def build_lines(article: jats.Article) -> LinedDoc:
    rows: list[Line] = []
    spans: list[SectionSpan] = []
    taken: dict[str, int] = {}
    for base, header, body in _pieces(article):
        path = _unique(base, taken)
        start = len(rows)
        for ordinal, text in enumerate(t for t in body.split("\n") if t):
            rows.append(Line(len(rows) + 1, text, path, ordinal, line_id(path, ordinal, text)))
        spans.append(SectionSpan(path, header, start, len(rows)))
    return LinedDoc(pmcid=article.pmcid, lines=tuple(rows), sections=tuple(spans))


def render(doc: LinedDoc) -> str:
    """`md_linenum` — what the agent reads. `extraction_text` plus a number per line."""
    blocks = []
    for s in doc.sections:
        body = "\n".join(f"{x.n}\t{x.text}" for x in doc.lines[s.start : s.stop])
        blocks.append(f"{s.header}\n{body}")
    return "\n\n".join(blocks)


def resolve(doc: LinedDoc, n: int) -> Line | None:
    return doc.lines[n - 1] if 1 <= n <= len(doc.lines) else None


def resolve_id(doc: LinedDoc, ident: str) -> Line | None:
    """The inverse of what ingest stores: a citation written before a parser fix."""
    return next((x for x in doc.lines if x.line_id == ident), None)


def locate_parts(doc: LinedDoc, quote: str) -> list[list[int]]:
    """Line numbers per `||`-separated passage — empty for a passage that is not here.

    Retrofit needs the shape, not just the numbers: a quote whose third passage fails to
    locate is a different problem from one that matched nothing at all.
    """
    return [_match(doc, part) for part in _passages(quote)]


def locate(doc: LinedDoc, quote: str) -> list[int]:
    """Line numbers containing the quote, in passage order, each listed once."""
    seen: set[int] = set()
    out: list[int] = []
    for part in locate_parts(doc, quote):
        for n in part:
            if n not in seen:
                seen.add(n)
                out.append(n)
    return out


# -- internals ----------------------------------------------------------------


def _pieces(a: jats.Article) -> list[tuple[str, str, str]]:
    """(path, header, body) in `jats.extraction_text`'s uncapped reading order.

    This mirrors `jats._pieces` sorted by descending priority rather than calling it,
    because the path needs the table id and section title that the header has already
    flattened into a string. The coverage test compares the rendered result against
    `extraction_text` line for line, so any drift between the two fails loudly.
    """
    out: list[tuple[str, str, str]] = []
    if a.methods_text:
        out.append(("methods", "== Methods", a.methods_text))
    for s in a.extra_sections:
        out.append((f"extra:{s.title}", f"== {s.title}", s.text))
    if a.figure_captions:
        out.append(("fig", "== Figure captions", "\n".join(a.figure_captions)))
    if a.abstract:
        out.append(("abstract", "== Abstract", a.abstract))
    for i, t in enumerate(a.tables, 1):
        out.append((f"table:{t.id}" if t.id else f"table:#{i}", f"== Table {t.id}", t.text))
    for i, w in enumerate(a.keyword_windows, 1):
        out.append((f"context:{i}", f"== Context {i}", w))
    return out


def _unique(path: str, taken: dict[str, int]) -> str:
    """Two tables may carry the same id, two sections the same title. Ids built on a
    shared path would then collide between sections with identical text."""
    taken[path] = taken.get(path, 0) + 1
    return path if taken[path] == 1 else f"{path}#{taken[path]}"


def _passages(quote: str) -> list[str]:
    """The split `extract.zeta.verify_row` already applies to stored evidence."""
    return [p.strip() for p in quote.split(EVIDENCE_SEP) if p.strip()]


def _match(doc: LinedDoc, part: str) -> list[int]:
    """Exact first, folded second. A passage that itself spans lines answers with each.

    Splitting the passage on newlines is not a liberty: the guard folded those newlines
    into spaces before verifying, so a quote covering a caption and three table rows is
    genuine evidence there and simply addresses four lines here.
    """
    hits = [x.n for x in doc.lines if part in x.text]
    if hits:
        return hits
    out: list[int] = []
    for fragment in part.split("\n"):
        needle = fold(fragment)
        if not needle:
            continue
        found = [x.n for x in doc.lines if needle in fold(x.text)]
        if not found:
            return []
        out.extend(n for n in found if n not in out)
    return out
