"""A withheld quote as an address into its source, and the way back.

The release withholds the verbatim evidence of every paper not licensed CC BY or CC0. The row
keeps enough to put the quote back on a machine that has the article: the lines it lies in,
character offsets within them, and the sha256 of the original so the result can be checked.

`address` and `restore` are an encoder and its decoder, kept in one file because they must
agree. An address is a list of pieces whose concatenation is the quote, exactly:

    [line_id, start, end]   line_id's text (as `lines.build_lines` makes it) sliced [start:end]
    "…"                     glue — only whitespace, `|` and dash characters, never a letter
                            or a digit, so the address itself carries none of the text

Glue exists because a stored quote is not always a clean slice. Passages are joined by
` || ` (and, in a handful of rows, by `||` or `\\t || `); a passage over a caption and the
table rows under it keeps its newlines; and a quote written before the parser normalised
signs has an en dash, or spaces, where the line now has a hyphen, or tabs. The evidence guard
accepted all of these after folding, so all of them have to be restorable byte for byte.

Deterministic: no model, no clock. `rehydrate` touches the network only through a `fetch`
the caller passes in.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from mnp.corpus import jats, lines

# What glue may contain. Whitespace the parser collapses, the passage separator, and every
# dash `jats.normalise_minus` rewrites. Nothing a reader could read.
GLUE_ALPHABET = frozenset(" \t\n\r    |-" + jats._DASHES)

_SEPARATOR = re.compile(r"(\s*\|\|\s*)")

Piece = list | str


def address(doc: lines.LinedDoc, quote: str, prefer: Sequence[str] = ()) -> list[Piece] | None:
    """Pieces that concatenate to `quote`, or None when some part of it is in no line.

    `prefer` are the line ids the row already cites; they are tried first, so an address
    points where the citation points when the same text occurs twice in a paper.
    """
    by_id = {x.line_id: x for x in doc.lines}
    order = [by_id[i] for i in dict.fromkeys(prefer) if i in by_id] + list(doc.lines)
    pieces: list[Piece] = []
    for k, token in enumerate(_SEPARATOR.split(quote)):
        if k % 2:
            pieces.append(token)
            continue
        for j, fragment in enumerate(token.split("\n")):
            if j:
                pieces.append("\n")
            if not fragment:
                continue
            found = _fragment(order, fragment)
            if found is None:
                return None
            pieces.extend(found)
    return _merged(pieces)


def restore(doc: lines.LinedDoc, pieces: Sequence[Piece]) -> str:
    """The quote an address describes. KeyError when a cited line is not in `doc`."""
    text = {x.line_id: x.text for x in doc.lines}
    out = []
    for piece in pieces:
        if isinstance(piece, str):
            out.append(piece)
        else:
            line_id, start, end = piece
            out.append(text[line_id][start:end])
    return "".join(out)


def glue_is_clean(pieces: Sequence[Piece]) -> bool:
    return all(set(p) <= GLUE_ALPHABET for p in pieces if isinstance(p, str))


def dumps(pieces: Sequence[Piece]) -> str:
    """The column's serialisation: compact, key-free JSON, byte-stable across runs."""
    return json.dumps(list(pieces), ensure_ascii=False, separators=(",", ":"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# -- rehydrate ------------------------------------------------------------------


@dataclass
class Rehydrated:
    withheld: int = 0
    restored: int = 0
    failed: list[str] = field(default_factory=list)  # row ids whose restore did not match
    missing_xml: list[str] = field(default_factory=list)  # pmcids with no source to read
    written: list[Path] = field(default_factory=list)


def rehydrate(
    release_dir: Path,
    out_dir: Path,
    *,
    xml_dir: Path,
    fetch: Callable[[str], bytes | None] | None = None,
) -> Rehydrated:
    """A local copy of the release with every withheld quote put back and hash-checked.

    A quote whose restore does not reproduce its sha256 — the source was re-typeset, or the
    parser changed — stays null and is named. It is never replaced by the nearest text.
    """
    from mnp.report import release

    table = pd.read_parquet(Path(release_dir) / "dataset.parquet")
    result = Rehydrated()
    withheld = table.index[table["quote_withheld"].astype(bool)]
    result.withheld = len(withheld)
    docs: dict[str, lines.LinedDoc | None] = {}
    for i in withheld:
        pmcid = table.at[i, "pmcid"]
        if pmcid not in docs:
            docs[pmcid] = _document(pmcid, Path(xml_dir), fetch)
            if docs[pmcid] is None:
                result.missing_xml.append(pmcid)
        doc = docs[pmcid]
        if doc is None:
            continue
        try:
            quote = restore(doc, json.loads(table.at[i, "evidence_quote_spans"]))
        except (KeyError, TypeError, ValueError):
            quote = None
        if quote is not None and sha256_text(quote) == table.at[i, "evidence_quote_sha256"]:
            table.at[i, "evidence_quote"] = quote
            result.restored += 1
        else:
            result.failed.append(str(table.at[i, "row_id"]))

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    parquet, jsonl = out_dir / "dataset.parquet", out_dir / "dataset.jsonl"
    table.to_parquet(parquet, index=False)
    with jsonl.open("w", encoding="utf-8") as fh:
        for row in release.records(table):
            fh.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    result.written = [parquet, jsonl]
    return result


def _document(
    pmcid: str, xml_dir: Path, fetch: Callable[[str], bytes | None] | None
) -> lines.LinedDoc | None:
    path = xml_dir / f"{pmcid}.xml"
    xml = path.read_bytes() if path.is_file() else (fetch(pmcid) if fetch else None)
    return lines.build_lines(jats.parse(xml)) if xml else None


# -- internals ------------------------------------------------------------------


def _fragment(order: Sequence[lines.Line], fragment: str) -> list[Piece] | None:
    """One newline-free passage: an exact slice if there is one, an aligned one if not."""
    for x in order:
        k = x.text.find(fragment)
        if k >= 0:
            return [[x.line_id, k, k + len(fragment)]]
    needle = lines.fold(fragment)
    if not needle:
        return [fragment] if set(fragment) <= GLUE_ALPHABET else None
    for x in order:
        if needle in lines.fold(x.text):
            aligned = _align(x, fragment)
            if aligned is not None:
                return aligned
    return None


def _align(x: lines.Line, fragment: str) -> list[Piece] | None:
    """Slices of the line for what matches, glue for the rest — if the rest is only glue.

    Called only for a line whose folded text contains the folded fragment, so the two differ
    in whitespace and dashes alone. The matched slices must also sit together in the line: a
    fragment rebuilt from characters scattered across a paragraph would restore exactly and
    point nowhere.
    """
    matcher = difflib.SequenceMatcher(None, fragment, x.text, autojunk=False)
    pieces: list[Piece] = []
    pos = 0
    first = last = None
    for a, b, size in matcher.get_matching_blocks():
        if a > pos:
            pieces.append(fragment[pos:a])
        if size:
            pieces.append([x.line_id, b, b + size])
            first = b if first is None else first
            last = b + size
        pos = a + size
    if pos < len(fragment):
        pieces.append(fragment[pos:])
    if first is None or not glue_is_clean(pieces):
        return None
    if lines.fold(x.text[first:last]) not in lines.fold(fragment):
        return None
    return pieces


def _merged(pieces: list[Piece]) -> list[Piece]:
    """Adjacent glue joined, adjacent slices of one line joined, so the address is minimal."""
    out: list[Piece] = []
    for p in pieces:
        if out and isinstance(p, str) and isinstance(out[-1], str):
            out[-1] += p
        elif (
            out
            and not isinstance(p, str)
            and not isinstance(out[-1], str)
            and out[-1][0] == p[0]
            and out[-1][2] == p[1]
        ):
            out[-1] = [p[0], out[-1][1], p[2]]
        else:
            out.append(p)
    return out
