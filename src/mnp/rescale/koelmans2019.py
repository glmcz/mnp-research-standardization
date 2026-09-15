"""Koelmans et al. 2019, Water Res 155:410 (PMC6449537): SI `mmc1.docx` Table S1.

Table S1 ("Study Characteristics") is a 12-column prose table, not a tidy one: size
ranges live in "Size, shape" ("Size: 0.355-0.999, 1.00-4.759, ≥4.75 mm; Shape: ..."),
concentrations in "Value" ("Mean: 4.2 x 10-3 #/L; Median: ..."), and the mesh that
sets a study's floor in "Sampling method". This module fetches the SI from Europe PMC,
reads the table straight from the document XML (the file writes every "µ" as a
Symbol-font `w:sym` glyph that python-docx's `cell.text` drops, turning "333 µm" into
"333 m"), maps columns by header name, and extracts the numbers with regexes whose
behaviour is pinned by tests on cells copied from the real table.

Nothing is transcribed by hand; every derived number carries the cell it came from in
`notes` so it can be audited.
"""

from __future__ import annotations

import math
import re
import zipfile
from pathlib import Path

import httpx
import pandas as pd
from lxml import etree

from mnp import __version__, config

PMCID = "PMC6449537"
SI_URL = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{PMCID}/supplementaryFiles"
ZIP_NAME = "supplementaryFiles.zip"
DOCX_NAME = "mmc1.docx"


def raw_dir() -> Path:
    """Resolved on each call; a module-level constant freezes the data root at import time."""
    return config.DATA_RAW / "koelmans2019"


def csv_path() -> Path:
    return raw_dir() / "table_s1.csv"


USER_AGENT = f"NanoSolve-mnp-research/{__version__}"

CANONICAL = (
    "study",
    "matrix",
    "size_min_um",
    "size_max_um",
    "concentration_value",
    "concentration_unit",
    "method",
    "notes",
)
EXTRA = ("source_code", "size_source", "value_kind")


class HeaderMappingError(ValueError):
    """The header row could not be mapped onto the roles the parser needs."""


# --------------------------------------------------------------------------- fetch


def fetch_si(dest: Path | None = None, client: httpx.Client | None = None) -> Path:
    """Download the SI zip once, extract mmc1.docx, return its path. Cached on disk."""
    dest = Path(dest or raw_dir())
    dest.mkdir(parents=True, exist_ok=True)
    docx_path = dest / DOCX_NAME
    if docx_path.is_file() and docx_path.stat().st_size > 0:
        return docx_path
    zip_path = dest / ZIP_NAME
    if not (zip_path.is_file() and zip_path.stat().st_size > 0):
        own_client = client is None
        client = client or httpx.Client(timeout=60, follow_redirects=True)
        try:
            response = client.get(SI_URL, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
            zip_path.write_bytes(response.content)
        finally:
            if own_client:
                client.close()
    with zipfile.ZipFile(zip_path) as archive:
        docx_path.write_bytes(archive.read(DOCX_NAME))
    return docx_path


# --------------------------------------------------------------------------- docx

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _w(tag: str) -> str:
    return f"{{{_W}}}{tag}"


# Symbol-font code points seen in the wild; F06D is the µ this file uses 69 times.
SYMBOL_FONT = {"F06D": "µ", "F0B3": "≥", "F0A3": "≤", "F0B1": "±", "F0B0": "°", "F02D": "−"}


def cell_text(tc: etree._Element) -> str:
    """Cell text with paragraphs/breaks as newlines and `w:sym` glyphs resolved."""
    parts: list[str] = []
    for i, paragraph in enumerate(tc.iterfind(_w("p"))):
        if i:
            parts.append("\n")
        for node in paragraph.iter():
            tag = etree.QName(node).localname
            if tag == "t":
                parts.append(node.text or "")
            elif tag == "sym":
                parts.append(SYMBOL_FONT.get((node.get(_w("char")) or "").upper(), "?"))
            elif tag in ("br", "cr"):
                parts.append("\n")
            elif tag == "tab":
                parts.append("\t")
    return "".join(parts)


def read_tables(docx_path: Path) -> list[list[list[str]]]:
    """Every table in the document body as rows of cell strings."""
    with zipfile.ZipFile(docx_path) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    body = root.find(_w("body"))
    tables = []
    for tbl in body.iter(_w("tbl")):
        rows = []
        for tr in tbl.iterfind(_w("tr")):
            rows.append([cell_text(tc) for tc in tr.iterfind(_w("tc"))])
        tables.append(rows)
    return tables


# --------------------------------------------------------------------------- headers

HEADER_MAP = {
    "reference": "study",
    "study": "study",
    "citation": "study",
    "source": "source",
    "matrix": "source",
    "water type": "source",
    "size shape": "size",
    "size": "size",
    "size range": "size",
    "size class": "size",
    "size classes": "size",
    "value": "value",
    "concentration": "value",
    "concentrations": "value",
    "number concentration": "value",
    "sampling method": "sampling",
    "sampling": "sampling",
    "analysis method": "method",
    "analytical method": "method",
    "method": "method",
    "analysis": "method",
    "comments": "notes",
    "comment": "notes",
    "notes": "notes",
    "remarks": "notes",
}
REQUIRED_ROLES = ("study", "source", "size", "value")


def normalise_header(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def map_headers(headers: list[str]) -> dict[str, int]:
    """Role → column index, by normalised header name. Never by position."""
    roles: dict[str, int] = {}
    for index, header in enumerate(headers):
        role = HEADER_MAP.get(normalise_header(header))
        if role is not None and role not in roles:
            roles[role] = index
    missing = [role for role in REQUIRED_ROLES if role not in roles]
    if missing:
        raise HeaderMappingError(
            f"cannot map Table S1 header row: missing roles {missing}; headers seen: {headers!r}"
        )
    return roles


def find_table_s1(tables: list[list[list[str]]]) -> tuple[dict[str, int], list[list[str]]]:
    seen = []
    for rows in tables:
        if len(rows) < 2:
            continue
        try:
            return map_headers(rows[0]), rows[1:]
        except HeaderMappingError:
            seen.append([_squash(h) for h in rows[0]])
    raise HeaderMappingError(f"no table with a Table S1 header row; header rows seen: {seen!r}")


# --------------------------------------------------------------------------- text helpers


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def _clean(text: str) -> str:
    text = text.replace("\xa0", " ").replace("μ", "µ")
    text = re.sub(r"[–−—]", "-", text)
    return text.replace("×", "x").replace("”", "").replace("“", "")


_LEN_UNIT = r"(?:mm|µm|um)"
_NUM = r"\d+(?:\.\d+)?"


def _to_um(value: float, unit: str) -> float:
    return value * 1000.0 if unit == "mm" else value


# --------------------------------------------------------------------------- size


def _size_segment(text: str) -> str | None:
    text = _clean(text)
    lower = text.lower()
    start = lower.find("size")
    if start >= 0:
        segment = text[start + 4 :]
        segment = re.split(r"(?i)shape\s*:", segment, maxsplit=1)[0]
    elif re.search(rf"\d\s*-?\s*{_LEN_UNIT}\b", text):
        segment = text
    else:
        return None
    if re.search(r"±|\bmedian\b|\bmean\b", segment, re.I):
        return None
    segment = re.sub(r"(?i)\bup\s+to\b", "<", segment)
    return segment.replace("(", " ").replace(")", " ")


_SIZE_ITEM = re.compile(
    rf"(?P<lo>{_NUM})\s*(?P<u1>{_LEN_UNIT})?\s*(?:-|\bto\b)\s*(?P<hi>{_NUM})"
    rf"|(?P<op>[<>≥≤])\s*(?P<bound>{_NUM})"
    rf"|(?P<single>{_NUM})"
)
_UNIT_TOKEN = re.compile(rf"(?<![A-Za-z]){_LEN_UNIT}(?![A-Za-z])")


def parse_size(text: str) -> tuple[float | None, float | None]:
    """(min, max) in µm from a "Size, shape" cell; None where the cell leaves it open.

    Ranges and ">x" bounds give lower limits, "<x" bounds only upper ones, bare numbers
    are read as sieve cut-offs (lower limits, open at the top). The unit of a number is
    the first unit token after it (lists carry a trailing unit), else the last one before.
    """
    segment = _size_segment(text)
    if segment is None:
        return None, None
    units = [(m.start(), m.group(0)) for m in _UNIT_TOKEN.finditer(segment)]
    if not units:
        return None, None

    def unit_at(pos: int) -> str:
        after = [u for p, u in units if p >= pos]
        return after[0] if after else units[-1][1]

    lows: list[float] = []
    highs: list[float] = []
    open_lower = False
    open_upper: float | None = None
    for m in _SIZE_ITEM.finditer(segment):
        if m.group("lo") is not None:
            lo_unit = m.group("u1") or unit_at(m.end("lo"))
            lo = _to_um(float(m.group("lo")), lo_unit)
            hi = _to_um(float(m.group("hi")), unit_at(m.end("hi")))
            lows.append(min(lo, hi))
            highs.append(max(lo, hi))
        elif m.group("op") is not None:
            bound = _to_um(float(m.group("bound")), unit_at(m.end("bound")))
            if m.group("op") in "<≤":
                highs.append(bound)
                open_lower = True
            else:
                lows.append(bound)
                open_upper = max(open_upper or 0.0, bound)
        else:
            single = _to_um(float(m.group("single")), unit_at(m.end("single")))
            lows.append(single)
            open_upper = max(open_upper or 0.0, single)

    size_min = None if open_lower or not lows else min(lows)
    size_max = max(highs) if highs else None
    if open_upper is not None and (size_max is None or open_upper >= 0.98 * size_max):
        size_max = None
    return size_min, size_max


_MESH_CLAUSE = re.compile(
    r"(?i)\b(?:mesh|sieve|sieved|sieves|filter|filtered|net|screen|cartridge)"
)
_MESH_LIST = re.compile(
    rf"((?:{_NUM}\s*(?:,|and|&|-|to)\s*)*{_NUM})\s*-?\s*(?P<unit>{_LEN_UNIT})\b"
)


def mesh_floor(sampling_text: str) -> float | None:
    """Smallest mesh/sieve/filter size (µm) named in a sampling-method cell."""
    text = _clean(sampling_text)
    candidates: list[float] = []
    for clause in re.split(r"[;\n]|\.\s", text):
        if not _MESH_CLAUSE.search(clause):
            continue
        for m in _MESH_LIST.finditer(clause):
            unit = m.group("unit")
            for number in re.findall(_NUM, m.group(1)):
                candidates.append(_to_um(float(number), unit))
    return min(candidates) if candidates else None


# --------------------------------------------------------------------------- value

_VNUM = r"(?<![A-Za-z\d.])(?<!e-)(?:\d{1,3}(?:[ ,]\d{3})+|\d+)(?:\.\d+)?(?:e-?\d+)?(?!\d)"
_VUNIT = (
    r"(?<![A-Za-z])(?:#|particles?|items?|MPs?|SAL|n|p|mg|µg|ug|g|kg)"
    r"(?:/|\s+)(?:L|l|litre|liter|m3|m-3|km2|km-2|m2|kg|day|d)(?:\s*-1)?(?![A-Za-z])"
)
_LABELLED = re.compile(
    rf"(?P<label>\bmean\b|\baverage\b|\bmedian\b)[^\d]{{0,40}}?(?P<num>{_VNUM})"
    r"(?!\s*-\s*[A-Za-z\d])(?!\s*(?:µm|mm)\b)",
    re.I,
)
_RANGE = re.compile(rf"(?P<lo>{_VNUM})\s*-\s*(?P<hi>{_VNUM})\s*(?P<unit>{_VUNIT})")
_SINGLE = re.compile(rf"(?P<num>{_VNUM})\s*(?P<unit>{_VUNIT})")
_ANY_UNIT = re.compile(_VUNIT)
_KIND_RANK = {"mean": 0, "median": 1, "single": 2, "range_geomean": 3, "range_midpoint": 3}


def _prepare_value_text(text: str) -> str:
    text = _clean(text)
    text = re.sub(r"\s*/\s*", "/", text)
    text = text.replace("/Ll", "/L")
    text = re.sub(r"\(\s*±[^)]*\)", " ", text)
    text = re.sub(r"±\s*\d+(?:[.,]\d+)?", " ", text)
    text = re.sub(r"\(\s*[\d.,\s]+\)", " ", text)
    text = re.sub(r"(?i)\(\s*ranges?\b[^)]*\)", " ", text)
    text = re.sub(r"(?i)\(\s*s\.?\s?[de]\.?[^)]*\)", " ", text)
    text = re.sub(r"\(\s*(x?\s*10\s*-\s*\d)\s*\)", r" \1 ", text)
    # fold scale factors into e-notation: "4.2 x 10-3" → "4.2e-3", "0.55 E5" → "0.55e5"
    text = re.sub(r"x\s*10\^?\s*(-?\d)(?![\d.])", r" e\1", text)
    text = re.sub(r"(?<![\w.])10\^?\s*(-\d)(?![\d.])", r" e\1", text)
    text = re.sub(r"(\d)\s*E(\d+)\b", r"\1e\2", text)
    text = re.sub(r"(\d)\s+e(-?\d+)\b", r"\1e\2", text)
    return re.sub(r"\s+", " ", text).strip()


def _num(token: str) -> float:
    return float(token.replace(" ", "").replace(",", ""))


def _unit_family(unit: str) -> int:
    from mnp.rescale.powerlaw import classify_unit

    return {"number": 0, "mass": 1}.get(classify_unit(unit), 2)


def _unit_near(text: str, pos: int) -> str | None:
    after = _ANY_UNIT.search(text, pos)
    if after is not None:
        return after.group(0)
    before = list(_ANY_UNIT.finditer(text, 0, pos))
    return before[-1].group(0) if before else None


def parse_value(text: str) -> tuple[float | None, str | None, str]:
    """(value, unit, kind) from a "Value" cell.

    Preference: particle-number units over mass units, then mean > median > single
    number > range (geometric mean of the endpoints), then text order.
    """
    prepared = _prepare_value_text(text)
    candidates: list[tuple[tuple[int, int, int], float, str, str]] = []

    for m in _LABELLED.finditer(prepared):
        unit = _unit_near(prepared, m.end("num"))
        if unit is None:
            continue
        kind = "median" if m.group("label").lower() == "median" else "mean"
        value = _num(m.group("num"))
        candidates.append(((_unit_family(unit), _KIND_RANK[kind], m.start()), value, unit, kind))
    ranges = list(_RANGE.finditer(prepared))
    for m in _SINGLE.finditer(prepared):
        if any(r.start() <= m.start("num") < r.end() for r in ranges):
            continue
        unit = m.group("unit")
        candidates.append(
            ((_unit_family(unit), 2, m.start()), _num(m.group("num")), unit, "single")
        )
    for m in ranges:
        unit = m.group("unit")
        lo, hi = _num(m.group("lo")), _num(m.group("hi"))
        if "e" in m.group("hi") and "e" not in m.group("lo"):
            lo *= 10 ** int(m.group("hi").split("e")[1])
        lo, hi = min(lo, hi), max(lo, hi)
        if lo > 0:
            value, kind = math.sqrt(lo * hi), "range_geomean"
        else:
            value, kind = (lo + hi) / 2, "range_midpoint"
        candidates.append(((_unit_family(unit), 3, m.start()), value, unit, kind))

    if not candidates:
        return None, None, "none"
    _, value, unit, kind = min(candidates, key=lambda c: c[0])
    return value, _squash(unit), kind


# --------------------------------------------------------------------------- matrix

MATRIX_BY_SOURCE = {
    "LAK": "freshwater",
    "RIV": "freshwater",
    "CANAL": "freshwater",
    "BOT": "drinking water",
    "TAP": "drinking water",
    "DWTP": "drinking water",
    "GROUND": "groundwater",
    "GW": "groundwater",
    "WWTP": "wastewater",
}


def matrix_from_source(code: str) -> str:
    first = re.split(r"[,/;\s]+", _squash(code).upper())
    return MATRIX_BY_SOURCE.get(first[0] if first else "", "other")


# --------------------------------------------------------------------------- table


def parse_table_s1(docx_path: Path) -> pd.DataFrame:
    roles, rows = find_table_s1(read_tables(docx_path))

    def cell(cells: list[str], role: str) -> str:
        index = roles.get(role)
        return cells[index] if index is not None and index < len(cells) else ""

    records = []
    for cells in rows:
        study = _squash(cell(cells, "study"))
        if not study:
            continue
        size_text, value_text = cell(cells, "size"), cell(cells, "value")
        sampling, source = cell(cells, "sampling"), cell(cells, "source")
        size_min, size_max = parse_size(size_text)
        size_source = "size_text" if (size_min is not None or size_max is not None) else None
        if size_min is None:
            floor = mesh_floor(sampling)
            if floor is not None:
                size_min = floor
                size_source = "sampling_mesh" if size_source is None else "size_text+sampling_mesh"
        value, unit, kind = parse_value(value_text)
        notes = (
            f"size_source={size_source or 'none'}; value_kind={kind}; "
            f"size_text={_squash(size_text)!r}; value_text={_squash(value_text)!r}"
        )
        comments = _squash(cell(cells, "notes"))
        if comments:
            notes += f"; comments={comments!r}"
        records.append(
            {
                "study": study,
                "matrix": matrix_from_source(source),
                "size_min_um": math.nan if size_min is None else float(size_min),
                "size_max_um": math.nan if size_max is None else float(size_max),
                "concentration_value": math.nan if value is None else float(value),
                "concentration_unit": unit or "",
                "method": _squash(cell(cells, "method")),
                "notes": notes,
                "source_code": _squash(source),
                "size_source": size_source or "none",
                "value_kind": kind,
            }
        )
    return pd.DataFrame.from_records(records, columns=[*CANONICAL, *EXTRA])


NUMERIC = ("size_min_um", "size_max_um", "concentration_value")


def write_table_s1(df: pd.DataFrame, path: Path | None = None) -> Path:
    path = Path(path or csv_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path


def load_table_s1(path: Path | None = None) -> pd.DataFrame:
    path = Path(path or csv_path())
    if not path.is_file():
        raise FileNotFoundError(f"{path} missing; run `python -m mnp.rescale fetch-si parse` first")
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    for column in NUMERIC:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    return df
