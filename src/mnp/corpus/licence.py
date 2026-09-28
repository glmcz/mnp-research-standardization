"""What a source article says about re-use, read from its own JATS: pmcid → one licence code.

The release ships a paper's verbatim quotes only when that paper is CC BY or CC0 (Martin's
decision of 2026-09-28), so this is the function that decides which quotes leave the
repository. It reads the vendored XML and nothing else. The earlier count came from
`data/interim/articles.parquet`, which is gitignored: a fresh clone could not rebuild the
decision it was publishing.

Publishers state a licence in four shapes, and this corpus has all of them: a machine-readable
`xlink:href` on `<license>`, an `<ali:license_ref>`, a creativecommons.org URL inside the
prose (as an `ext-link` href or as bare text), and prose that names the licence with no URL at
all. A URL is preferred over wording, but where the URL and the words disagree, or two licence
URLs name different licences, the statement is not certain of either and is `other-named`.
So is anything that names no Creative Commons licence — a publisher's own terms, "public
domain unless otherwise noted". Withholding a quote costs a reader one command; shipping one
we had no right to ship cannot be taken back.

Only the article's own licence counts: `front/article-meta/permissions`. Sub-articles (peer
review reports, decision letters) carry licences of their own, and a figure credited under
CC BY does not make the article CC BY.

Deterministic: no network, no model, no clock.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from mnp import config
from mnp.corpus import jats
from mnp.schema.models import SourceLicence

CODES = tuple(c.value for c in SourceLicence)
QUOTE_ALLOWED = frozenset({SourceLicence.cc_by.value, SourceLicence.cc0.value})

_XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
_CC_URL = re.compile(r"creativecommons\.org/(licenses|publicdomain)/([a-z-]+)", re.IGNORECASE)
# The URL path's terms, in any order CC has used ("by-nd-nc" is the 1.0 spelling).
_URL_TERMS = frozenset({"by", "nc", "nd", "sa"})


@dataclass(frozen=True, slots=True)
class Licence:
    code: str
    basis: str  # "url" | "wording" | "conflict" | "unclassified" | "no statement"
    statement: str
    url: str | None = None

    @property
    def quote_allowed(self) -> bool:
        return self.code in QUOTE_ALLOWED


def classify(xml: bytes) -> Licence:
    root = etree.fromstring(xml, parser=etree.XMLParser(recover=True, huge_tree=True))
    elements = _article_licences(root) if root is not None else []
    statement = " ".join(t for t in (_statement(el) for el in elements) if t)
    machine, inline = _urls(elements)
    if not elements or not (statement or machine or inline):
        return Licence("none", "no statement", statement)

    by_url, url = _from_urls(machine or inline)
    by_words = _from_words(statement)
    if by_url is None:
        if by_words is None:
            return Licence("other-named", "unclassified", statement)
        return Licence(by_words, "wording", statement)
    if by_url == "other-named" or (by_words is not None and by_words != by_url):
        return Licence("other-named", "conflict", statement, url)
    return Licence(by_url, "url", statement, url)


def read(pmcid: str, xml_dir: Path | None = None) -> Licence:
    """The licence of one vendored paper. A missing XML is an error, never `none`."""
    path = Path(xml_dir if xml_dir is not None else config.EPMC_XML_DIR) / f"{pmcid}.xml"
    return classify(path.read_bytes())


# -- internals ----------------------------------------------------------------


def _local(el: etree._Element) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def _article_licences(root: etree._Element) -> list[etree._Element]:
    meta = next((c for c in root if _local(c) == "front"), None)
    meta = (
        next((c for c in meta if _local(c) == "article-meta"), None) if meta is not None else None
    )
    if meta is None:
        return []
    return [
        lic
        for perm in meta
        if _local(perm) == "permissions"
        for lic in perm
        if _local(lic) == "license"
    ]


def _statement(el: etree._Element) -> str:
    """The prose of the licence, without the `ali:license_ref` URL glued onto its front."""
    parts = [jats.normalise("".join(p.itertext())) for p in el.iter() if _local(p) == "license-p"]
    if not parts:  # a bare <license> with text directly inside it
        parts = [jats.normalise("".join(el.itertext()))]
    return " ".join(p for p in parts if p)


def _urls(elements: list[etree._Element]) -> tuple[list[str], list[str]]:
    """(machine-readable, inline) creativecommons.org URLs, each in document order."""
    machine: list[str] = []
    inline: list[str] = []

    def found(text: str | None) -> list[str]:
        return [m.group(0) for m in _CC_URL.finditer(text or "")]

    for lic in elements:
        if lic.get(_XLINK_HREF):
            machine.append(lic.get(_XLINK_HREF))
        inline += found(lic.text)
        for el in lic.iterdescendants():
            if not isinstance(el.tag, str):
                continue
            if _local(el) == "license_ref":
                machine.append((el.text or "").strip())
            else:
                inline += [el.get(_XLINK_HREF)] if el.get(_XLINK_HREF) else []
                inline += found(el.text)
            inline += found(el.tail)
    return [u for u in machine if _CC_URL.search(u)], [u for u in inline if _CC_URL.search(u)]


def _url_code(url: str) -> str:
    m = _CC_URL.search(url)
    kind, path = m.group(1).lower(), m.group(2).lower()
    if kind == "publicdomain":
        return "CC0" if path == "zero" else "other-named"
    terms = path.split("-")
    if terms[0] != "by" or any(t not in _URL_TERMS for t in terms) or len(set(terms)) != len(terms):
        return "other-named"
    return _compose(nc="nc" in terms, nd="nd" in terms, sa="sa" in terms)


def _from_urls(urls: list[str]) -> tuple[str | None, str | None]:
    """One code from every URL the statement gives, or `other-named` when they disagree.

    A CC0 URL next to a CC BY one is the BMC/Springer pattern: the waiver covers the data,
    the licence covers the article. The licence wins; two different licences are a conflict.
    """
    if not urls:
        return None, None
    codes = [(_url_code(u), u) for u in urls]
    licences = {c for c, _ in codes if c != "CC0"}
    if len(licences) > 1:
        return "other-named", codes[0][1]
    if licences:
        code = licences.pop()
        return code, next(u for c, u in codes if c == code)
    return "CC0", codes[0][1]


_URL = re.compile(r"https?://\S+|(?:www\.)?creativecommons\.org/\S*", re.IGNORECASE)
_NAMES_CC = re.compile(r"creative\s*commons|\bcc[\s-]*by\b|\bcc0\b", re.IGNORECASE)
_ATTRIBUTION = re.compile(r"\battribution\b|\bcc[\s-]*by\b", re.IGNORECASE)
_CC0_WORDS = re.compile(r"\bcc0\b|public\s+domain\s+dedication", re.IGNORECASE)
_NC = re.compile(r"non[\s-]*commercial|\bcc[\s-]*by(?:[\s-]+(?:nd|sa))*[\s-]+nc\b", re.IGNORECASE)
_ND = re.compile(r"no[\s-]*deriv|\bcc[\s-]*by(?:[\s-]+(?:nc|sa))*[\s-]+nd\b", re.IGNORECASE)
_SA = re.compile(r"share[\s-]*alike|\bcc[\s-]*by(?:[\s-]+(?:nc|nd))*[\s-]+sa\b", re.IGNORECASE)


def _from_words(statement: str) -> str | None:
    """The licence the prose names, or None when it names no particular one.

    URLs are cut out first: a bare `creativecommons.org/licenses/by-nd/4.0/` in the prose is
    the URL's evidence, not the wording's. "A Creative Commons licence" with no terms is None
    too — it neither contradicts a URL nor classifies a statement that has none. Every
    restriction found anywhere in the prose counts, so the reading can only err towards the
    more restrictive licence.
    """
    words = _URL.sub(" ", statement)
    if not _NAMES_CC.search(words):
        return None
    if _ATTRIBUTION.search(words):
        return _compose(
            nc=bool(_NC.search(words)), nd=bool(_ND.search(words)), sa=bool(_SA.search(words))
        )
    return "CC0" if _CC0_WORDS.search(words) else None


def _compose(*, nc: bool, nd: bool, sa: bool) -> str:
    if nd and sa:
        return "other-named"  # no such licence
    return "CC-BY" + ("-NC" if nc else "") + ("-ND" if nd else "") + ("-SA" if sa else "")
