"""JATS full text → the pieces an extraction model needs, plus a verbatim
`full_text` every quoted evidence string must be a substring of.

One normalisation, applied once to every paragraph and table cell, feeds both
the extraction text and `full_text`. That is what makes the evidence-substring
guard in `extract.zeta` sound: the model can only quote what it was shown, and
what it was shown is drawn from the same strings the guard searches.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from lxml import etree

KEYWORD_RE = re.compile(r"zeta|mobilit|zetasizer|ζ|electrophore", re.IGNORECASE)
METHODS_SECTYPE_RE = re.compile(r"method|materials", re.IGNORECASE)
METHODS_TITLE_RE = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*\.?\s*)?"
    r"(?:materials?\s*(?:and|&)\s*methods?|methods?|"
    r"experimental(?:\s+(?:section|procedures?|methods?|part))?)\s*$",
    re.IGNORECASE,
)
EXTRA_TITLE_RE = re.compile(
    r"zeta|electrophore|light scattering|\bDLS\b|characteri[sz]ation|\bcharge\b",
    re.IGNORECASE,
)
WINDOW = 2  # paragraphs either side of a keyword hit

_WS = re.compile(r"\s+")


# Publishers use at least eight different dash characters as a minus sign: U+2010 HYPHEN,
# U+2013 EN DASH and U+2212 MINUS SIGN all appear in this corpus in front of zeta values,
# and each one read as a positive number until normalised.
_DASHES = "\u2010\u2011\u2012\u2013\u2014\u2015\u2212\u02d7\ufe58\ufe63\uff0d"
# A dash right before a number, not preceded by one, is a sign rather than a range:
# "\u201313.4 \u00b1 0.8" is a zeta potential; "2\u20133%" is two to three percent. A tab
# separates table cells, not range endpoints, so only a real space blocks the sign.
_SIGN_DASH = re.compile(
    f"(?<!\\d)(?<!\\d[ \u00a0\u2009\u200a\u202f])[{_DASHES}][\u2009\u200a\u202f\u00a0 ]*(?=\\d)"
)


def normalise_minus(text: str) -> str:
    """Close up a dash that acts as a leading sign, and make a true minus an ASCII one.

    Only signs are rewritten. A dash between numbers is a range and keeps its character,
    so the article text stays faithful; `extract.coerce` normalises the rest when it
    parses. Quotes match because both sides pass through here.
    """
    text = _SIGN_DASH.sub("-", text)
    return text.replace("\u2212", "-").replace("\u00a0", " ")


def normalise(text: str) -> str:
    """Collapse whitespace, ASCII hyphen for the Unicode minus. Nothing else."""
    return _WS.sub(" ", normalise_minus(text)).strip()


def approx_tokens(text: str) -> int:
    return math.ceil(len(text) / 4)


@dataclass
class Section:
    title: str
    text: str


@dataclass
class Table:
    id: str
    caption: str
    tsv: str
    footnotes: list[str]

    @property
    def text(self) -> str:
        lines = [self.caption] if self.caption else []
        lines.append(self.tsv)
        lines.extend(self.footnotes)
        return "\n".join(line for line in lines if line)


@dataclass
class Article:
    pmcid: str | None
    doi: str | None
    title: str | None
    year: int | None
    journal: str | None
    license: str | None
    methods_text: str
    methods_source: str  # "sec-type" | "title" | "none"
    extra_sections: list[Section] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    keyword_windows: list[str] = field(default_factory=list)
    figure_captions: list[str] = field(default_factory=list)
    abstract: str = ""
    full_text: str = ""


# -- text helpers -------------------------------------------------------------


# Elements whose text is machinery, not prose: file names, alt text, ids.
_SKIP = frozenset(
    {"graphic", "media", "alt-text", "object-id", "supplementary-material", "inline-graphic"}
)


def _itertext(el: etree._Element, space_before: tuple[str, ...] = ()) -> str:
    """Document-order text of el. A child's tail comes after the child's own subtree."""
    parts: list[str] = []

    def walk(node: etree._Element) -> None:
        if not isinstance(node.tag, str) or node.tag in _SKIP:
            return
        if node.tag in space_before and (node.text or len(node)):
            parts.append(" ")
        if node.text:
            parts.append(node.text)
        for child in node:
            walk(child)
            if child.tail:
                parts.append(child.tail)

    walk(el)
    return "".join(parts)


def _para_text(p: etree._Element) -> str:
    return normalise(_itertext(p))


def _cell_text(cell: etree._Element) -> str:
    return normalise(_itertext(cell, space_before=("sup", "xref")))


def _sec_title(sec: etree._Element) -> str:
    t = sec.find("title")
    return normalise(_itertext(t)) if t is not None else ""


def _paragraphs(sec: etree._Element) -> list[etree._Element]:
    """Every <p> under sec (including nested secs), excluding those inside tables."""
    out = []
    for p in sec.iter("p"):
        if any(a.tag in ("table-wrap", "table-wrap-foot", "caption") for a in p.iterancestors()):
            continue
        out.append(p)
    return out


def _section_lines(sec: etree._Element) -> list[str]:
    lines = []
    for node in sec.iter():
        if node.tag == "title" and node.getparent() is not None and node.getparent().tag == "sec":
            t = normalise(_itertext(node))
            if t:
                lines.append(t)
        elif node.tag == "p" and not any(
            a.tag in ("table-wrap", "table-wrap-foot", "caption") for a in node.iterancestors()
        ):
            t = _para_text(node)
            if t:
                lines.append(t)
    return lines


# -- structure ----------------------------------------------------------------


def _find_methods(body: etree._Element) -> tuple[list[etree._Element], str]:
    by_type = [
        s
        for s in body.iter("sec")
        if s.get("sec-type") and METHODS_SECTYPE_RE.search(s.get("sec-type"))
    ]
    by_type = _drop_nested(by_type)
    if by_type:
        return by_type, "sec-type"
    by_title = [s for s in body.iter("sec") if METHODS_TITLE_RE.match(_sec_title(s))]
    by_title = _drop_nested(by_title)
    if by_title:
        return by_title, "title"
    return [], "none"


def _drop_nested(secs: list[etree._Element]) -> list[etree._Element]:
    chosen = set(secs)
    return [s for s in secs if not any(a in chosen for a in s.iterancestors())]


def _flatten_rows(tw: etree._Element) -> list[str]:
    """Table rows as TSV with colspan/rowspan expanded so columns line up.

    99% of the articles here use spanning cells; without expansion a group header
    ("Zeta potential (mV)" over Before/After) sits above the wrong column and the
    quantity is lost. Header text is repeated across the cells it covers, because it
    genuinely labels them; a spanning *data* cell is written once and the covered cells
    left empty, because repeating a number would invent a measurement that was never made.
    """
    grid: list[dict[int, str]] = []
    carry: dict[int, tuple[str, int]] = {}  # column -> (text, rows still to fill)
    for tr in tw.iter("tr"):
        row: dict[int, str] = {}
        for col, (text, left) in list(carry.items()):
            row[col] = text
            carry[col] = (text, left - 1)
            if left - 1 <= 0:
                del carry[col]
        col = 0
        for cell in tr:
            if cell.tag not in ("td", "th"):
                continue
            while col in row:
                col += 1
            text = _cell_text(cell)
            is_header = cell.tag == "th"
            span = max(1, int(cell.get("colspan") or 1))
            rowspan = max(1, int(cell.get("rowspan") or 1))
            for k in range(span):
                row[col + k] = text if (is_header or k == 0) else ""
            if rowspan > 1:
                for k in range(span):
                    row_text = text if (is_header or k == 0) else ""
                    carry[col + k] = ("" if not is_header else row_text, rowspan - 1)
            col += span
        if row:
            grid.append(row)
    out = []
    for row in grid:
        width = max(row) + 1 if row else 0
        cells = [row.get(i, "") for i in range(width)]
        if any(cells):
            out.append("\t".join(cells))
    return out


def _parse_table(tw: etree._Element) -> Table:
    label = tw.find("label")
    caption = tw.find("caption")
    cap_parts = []
    if label is not None:
        cap_parts.append(normalise(_itertext(label)).rstrip("."))
    if caption is not None:
        cap_parts.append(normalise(_itertext(caption)))
    cap = ". ".join(p for p in cap_parts if p)
    rows = _flatten_rows(tw)
    foots = []
    for fn in tw.iter("fn"):
        lab = fn.find("label")
        lab_t = normalise(_itertext(lab)) if lab is not None else ""
        body_t = normalise(" ".join(_itertext(p) for p in fn.iter("p")))
        foots.append(" ".join(x for x in (lab_t, body_t) if x))
    return Table(id=tw.get("id") or "", caption=cap, tsv="\n".join(rows), footnotes=foots)


def _keyword_windows(paras: list[etree._Element], texts: dict) -> list[list[etree._Element]]:
    hits = [i for i, p in enumerate(paras) if KEYWORD_RE.search(texts[p])]
    windows: list[list[int]] = []
    for i in hits:
        lo, hi = max(0, i - WINDOW), min(len(paras) - 1, i + WINDOW)
        if windows and lo <= windows[-1][1] + 1:
            windows[-1][1] = max(windows[-1][1], hi)
        else:
            windows.append([lo, hi])
    return [paras[lo : hi + 1] for lo, hi in windows]


def _meta(root: etree._Element) -> dict:
    am = root.find("front/article-meta")
    meta = {"pmcid": None, "doi": None, "title": None, "year": None, "journal": None}
    if am is None:
        return meta
    for aid in am.findall("article-id"):
        if aid.get("pub-id-type") == "pmcid":
            meta["pmcid"] = (aid.text or "").strip() or None
        elif aid.get("pub-id-type") == "doi":
            meta["doi"] = (aid.text or "").strip() or None
    t = am.find("title-group/article-title")
    if t is not None:
        meta["title"] = normalise(_itertext(t)) or None
    years = []
    for pd in am.findall("pub-date"):
        y = pd.findtext("year")
        if y and y.strip().isdigit():
            years.append((pd.get("pub-type") or pd.get("date-type") or "", int(y)))
    if years:
        preferred = [y for k, y in years if k in ("epub", "ppub", "collection", "pub")]
        meta["year"] = preferred[0] if preferred else years[0][1]
    jt = root.find("front/journal-meta/journal-title-group/journal-title")
    if jt is None:
        jt = root.find("front/journal-meta/journal-title")
    if jt is not None:
        meta["journal"] = normalise(_itertext(jt)) or None
    return meta


def parse(xml: bytes) -> Article:
    root = etree.fromstring(xml, parser=etree.XMLParser(recover=True, huge_tree=True))
    meta = _meta(root)
    abstract_el = next(
        (
            el
            for el in root.findall("front/article-meta/abstract")
            if not (el.get("abstract-type") or "").strip()
        ),
        None,
    )
    abstract = normalise(_itertext(abstract_el)) if abstract_el is not None else ""
    lic = root.find(".//license")
    license_text = normalise(_itertext(lic)) if lic is not None else None
    body = root.find("body")
    if body is None:
        body = etree.Element("body")

    methods_secs, source = _find_methods(body)
    methods_lines: list[str] = []
    for s in methods_secs:
        methods_lines.extend(_section_lines(s))
    covered = set()
    for s in methods_secs:
        covered.update(s.iter("p"))

    extra: list[Section] = []
    for s in body.iter("sec"):
        if s in methods_secs or any(a in methods_secs for a in s.iterancestors()):
            continue
        title = _sec_title(s)
        if title and EXTRA_TITLE_RE.search(title):
            extra.append(Section(title=title, text="\n".join(_section_lines(s))))
            covered.update(s.iter("p"))

    # Tables and figures are often parked in <floats-group>, outside <body> — 9% of this
    # corpus keeps every table there. Search the whole article, not just the body.
    tables = [_parse_table(tw) for tw in root.iter("table-wrap")]
    figure_captions = []
    for fig in root.iter("fig"):
        label = fig.find("label")
        caption = fig.find("caption")
        parts = []
        if label is not None:
            parts.append(normalise(_itertext(label)).rstrip("."))
        if caption is not None:
            parts.append(normalise(_itertext(caption)))
        text = ". ".join(p for p in parts if p)
        if text:
            figure_captions.append(text)

    paras = _paragraphs(body)
    texts = {p: _para_text(p) for p in paras}
    windows = _keyword_windows(paras, texts)
    window_texts = []
    for w in windows:
        fresh = [p for p in w if p not in covered and texts[p]]
        if any(KEYWORD_RE.search(texts[p]) for p in fresh):
            window_texts.append("\n".join(texts[p] for p in fresh))

    full_lines: list[str] = []
    for node in body.iter():
        if node.tag == "title" and node.getparent() is not None and node.getparent().tag == "sec":
            full_lines.append(normalise(_itertext(node)))
    full_lines.extend(texts[p] for p in paras)
    for t in tables:
        full_lines.append(t.caption)
        full_lines.extend(t.tsv.splitlines())
        full_lines.extend(t.footnotes)
    full_lines.extend(figure_captions)
    if abstract:
        full_lines.append(abstract)

    return Article(
        pmcid=meta["pmcid"],
        doi=meta["doi"],
        title=meta["title"],
        year=meta["year"],
        journal=meta["journal"],
        license=license_text,
        methods_text="\n".join(methods_lines),
        methods_source=source,
        extra_sections=extra,
        tables=tables,
        keyword_windows=window_texts,
        figure_captions=figure_captions,
        abstract=abstract,
        full_text="\n".join(line for line in full_lines if line),
    )


# -- what the model reads ------------------------------------------------------


def _pieces(a: Article) -> list[tuple[str, str, int]]:
    """(header, body, priority). Lower priority number = kept first when capped."""
    out = []
    for i, w in enumerate(a.keyword_windows, 1):
        out.append((f"== Context {i}", w, 0))
    for t in a.tables:
        out.append((f"== Table {t.id}", t.text, 1))
    for s in a.extra_sections:
        out.append((f"== {s.title}", s.text, 2))
    if a.figure_captions:
        out.append(("== Figure captions", "\n".join(a.figure_captions), 2))
    if a.abstract:
        out.append(("== Abstract", a.abstract, 2))
    if a.methods_text:
        out.append(("== Methods", a.methods_text, 3))
    return out


def extraction_text(a: Article, max_tokens: int | None = None) -> str:
    """Methods, tables, characterisation sections and keyword context, in reading
    order when uncapped; keyword context first when a budget forces choices."""
    pieces = _pieces(a)
    if max_tokens is None:
        ordered = sorted(pieces, key=lambda p: -p[2])
        return "\n\n".join(f"{h}\n{b}" for h, b, _ in ordered)

    budget = max_tokens
    kept: list[tuple[int, str]] = []
    for idx, (header, body, _) in enumerate(sorted(pieces, key=lambda p: p[2])):
        header_cost = approx_tokens(header) + 1
        if header_cost >= budget:
            break
        lines = []
        cost = header_cost
        for line in body.splitlines():
            c = approx_tokens(line) + 1
            if cost + c > budget:
                continue  # skip the oversized line, keep looking: the hit may be next
            lines.append(line)
            cost += c
        if not lines:
            continue
        kept.append((idx, f"{header}\n" + "\n".join(lines)))
        budget -= cost
    return "\n\n".join(text for _, text in kept)
