"""E1 — the seven ways a paper can be handed to an agent, all built from one block set.

The published E1 table compared raw JATS, the plain text readers get today, and five
addressable serialisations. Its script lived in a scratchpad and is gone, so every ratio
quoted from it — including the whole of E1b — multiplied constants nobody could regenerate.
This module is that script, re-committed with the tokeniser declared.

**One block set.** `lines.build_lines` already yields the parser's own reading order —
methods, extra sections, figure captions, abstract, tables, keyword-context windows — one
entry per section title, paragraph, TSV row, caption or footnote. Every arm below is a
different way of writing *those* lines down. Nothing is re-segmented and nothing is dropped,
which is the only reason the token counts can be read as a fact about serialisation.

The first pass of E1 got this wrong and reported `md_anchored` at 0.72× — a decorated copy of
a document, cheaper than the document. It had omitted the keyword windows, 31.8 % of the
content. `tests/corpus/test_represent.py` fails that build.

**Where E1's prose was silent, this module chose. The choices, so a future reader can tell a
changed world from a changed interpretation:**

- `text_current` is `extraction_text` **uncapped**. `corpus parse` caps it at 12 000 approximate
  tokens, but E1 reports `text_current` and `md_plain` as equal to the token, which is only
  true with no cap. The cap almost never binds at ~5 k tokens a paper.
- **Anchors** are the `lines` section path, slugified, appended to the header as ` {#slug}`.
  The header keeps its `== ` marker: md_anchored must be md_plain plus anchors and nothing else.
- **A sentence** ends at `.`, `!` or `?` followed by whitespace and a capital, a digit or an
  opening bracket — unless either of the two preceding words is a label or abbreviation
  (`Table 1.`, `Fig 2.`, `et al.`, `e.g.`) or a single letter (`25 degrees C.`, initials).
  A line containing a tab is a TSV record, not prose, and is one span whole.
- **Span ids** are `[sNNNN]`, four digits, numbered over the whole document, printed before
  the sentence and separated by one space.
- **`ir_json`** is one JSON object: `doc_id`, `sections` (`id`, `title`), and `spans` (`id`,
  `type`, `section`, `text`) at sentence granularity — the same granularity `md_spanids`
  addresses, so the 1.12 → 1.45 gap is the JSON envelope and nothing else. It carries **no
  line number**: `md_linenum` is the arm that addresses by line, and an IR that paid for both
  would be measuring two designs at once. Section titles appear without the `== ` marker,
  which is markdown syntax rather than content. `ensure_ascii=False`, no indent: escaping
  every non-ASCII character is a property of a serialiser flag, not of the representation.
- **Tokens** are `cl100k_base` with `disallowed_special=()`, so `<|endoftext|>` inside a paper
  is counted as the text it is instead of raising.

Deterministic: no model, no network, no clock. `tiktoken` downloads the BPE table once into
its cache and never again; nothing here needs an API key.
"""

from __future__ import annotations

import functools
import json
import re

from mnp.corpus import jats, lines

# In the order the published table prints them.
ARMS: tuple[str, ...] = (
    "xml_raw",
    "text_current",
    "md_plain",
    "md_anchored",
    "md_linenum",
    "md_spanids",
    "ir_json",
)

# What a citation into each arm can name. This is the column E1's table is really about:
# the tokens only mean something next to what they buy.
ADDRESSABLE: dict[str, str] = {
    "xml_raw": "xpath",
    "text_current": "nothing",
    "md_plain": "nothing",
    "md_anchored": "section",
    "md_linenum": "line",
    "md_spanids": "sentence",
    "ir_json": "sentence",
}

ENCODING = "cl100k_base"

# The six kinds of block the parse yields, in `lines._pieces` order. `ir_json` types every
# span with one of these and the test suite holds it to the closed set.
BLOCK_KINDS: tuple[str, ...] = (
    "methods",
    "section",
    "figure_caption",
    "abstract",
    "table",
    "context",
)

_KIND_BY_PREFIX = (
    ("methods", "methods"),
    ("extra:", "section"),
    ("fig", "figure_caption"),
    ("abstract", "abstract"),
    ("table:", "table"),
    ("context:", "context"),
)

_SENTENCE_BREAK = re.compile(r"""(?<=[.!?])["')\]]?\s+(?=[("'\[A-Z0-9])""")
_TAIL_WORDS = re.compile(r"(\S+)\s+(\S+)\s*$|^\s*(\S+)\s*$")
# Words that end in a period without ending a sentence. Labels first, then the abbreviations
# that actually occur in this corpus.
_ABBREVIATIONS = frozenset(
    {
        "al", "approx", "ca", "cf", "chapter", "dr", "e.g", "eq", "eqn", "etc", "fig",
        "figs", "figure", "i.e", "min", "no", "nos", "p", "pp", "prof", "ref", "refs",
        "resp", "sec", "spp", "st", "supplementary", "table", "vol", "vs",
    }
)  # fmt: skip


@functools.lru_cache(maxsize=1)
def encoding():
    """`cl100k_base`, loaded once. First call may fetch the BPE table into tiktoken's cache."""
    import tiktoken

    return tiktoken.get_encoding(ENCODING)


def count_tokens(text: str) -> int:
    return len(encoding().encode(text, disallowed_special=()))


def block_kind(section_path: str) -> str:
    """One of `BLOCK_KINDS`, from the path `lines` gave the block."""
    for prefix, kind in _KIND_BY_PREFIX:
        if section_path.startswith(prefix):
            return kind
    raise ValueError(f"no block kind for section path {section_path!r}")


def sentences(line: str) -> list[str]:
    """The line split into sentences, per the rule in this module's docstring.

    Joining the result with a single space returns the line, so the arms that address
    sentences carry exactly the text the arms that do not carry.
    """
    if not line:
        return []
    if "\t" in line:  # a TSV record is one span, whole
        return [line]
    out: list[str] = []
    start = 0
    for m in _SENTENCE_BREAK.finditer(line):
        if _ends_a_sentence(line[start : m.start()]):
            out.append(line[start : m.start()])
            start = m.end()
    out.append(line[start:])
    return [s for s in out if s]


def _ends_a_sentence(chunk: str) -> bool:
    """False when the period belongs to a label, an abbreviation or an initial."""
    m = _TAIL_WORDS.search(chunk)
    if not m:
        return True
    for word in (g for g in m.groups() if g):
        bare = word.strip("\"')]").rstrip(".!?").lower()
        if bare in _ABBREVIATIONS or (len(bare) == 1 and bare.isalpha()):
            return False
    return True


# -- the seven arms ------------------------------------------------------------


def md_plain(doc: lines.LinedDoc) -> str:
    """`extraction_text` reassembled from the block set. Equal to it, character for character."""
    return "\n\n".join(f"{s.header}\n{_body(doc, s)}" for s in doc.sections)


def md_anchored(doc: lines.LinedDoc) -> str:
    """`md_plain` with a `{#slug}` anchor on each header — addressable to the section."""
    slugs = anchors(doc)
    return "\n\n".join(f"{s.header} {{#{slugs[s.path]}}}\n{_body(doc, s)}" for s in doc.sections)


def md_linenum(doc: lines.LinedDoc) -> str:
    """The committed converter, not a second copy of it."""
    return lines.render(doc)


def md_spanids(doc: lines.LinedDoc) -> str:
    """`md_plain` with `[sNNNN]` before every sentence — addressable to the sentence."""
    counter = _Counter()
    blocks = []
    for s in doc.sections:
        body = "\n".join(
            " ".join(f"{counter.next_id()} {t}" for t in sentences(x.text))
            for x in doc.lines[s.start : s.stop]
        )
        blocks.append(f"{s.header}\n{body}")
    return "\n\n".join(blocks)


def ir_json(doc: lines.LinedDoc) -> str:
    """Typed sentence spans as JSON — what the machine resolves, never read whole."""
    slugs = anchors(doc)
    sections = [{"id": slugs[s.path], "title": s.header.removeprefix("== ")} for s in doc.sections]
    counter = _Counter()
    spans = [
        {
            "id": counter.next_id()[1:-1],
            "type": block_kind(s.path),
            "section": slugs[s.path],
            "text": text,
        }
        for s in doc.sections
        for x in doc.lines[s.start : s.stop]
        for text in sentences(x.text)
    ]
    return json.dumps(
        {"doc_id": doc.pmcid or "", "sections": sections, "spans": spans}, ensure_ascii=False
    )


def representations(article: jats.Article, xml_text: str) -> dict[str, str]:
    """All seven arms of one paper, keyed by `ARMS`."""
    doc = lines.build_lines(article)
    return {
        "xml_raw": xml_text,
        "text_current": jats.extraction_text(article),
        "md_plain": md_plain(doc),
        "md_anchored": md_anchored(doc),
        "md_linenum": md_linenum(doc),
        "md_spanids": md_spanids(doc),
        "ir_json": ir_json(doc),
    }


def token_counts(article: jats.Article, xml_text: str) -> dict[str, int]:
    return {arm: count_tokens(text) for arm, text in representations(article, xml_text).items()}


def block_tokens(article: jats.Article) -> dict[str, int]:
    """`md_plain`'s cost split by block kind — the table behind E1's correction.

    Header and body together, as `md_plain` writes the block; the only thing left out is the
    blank line between blocks. Keyword windows were the third of this that went missing.
    """
    doc = lines.build_lines(article)
    out = dict.fromkeys(BLOCK_KINDS, 0)
    for s in doc.sections:
        out[block_kind(s.path)] += count_tokens(f"{s.header}\n{_body(doc, s)}")
    return out


# -- internals -----------------------------------------------------------------


class _Counter:
    def __init__(self) -> None:
        self.n = 0

    def next_id(self) -> str:
        self.n += 1
        return f"[s{self.n:04d}]"


def _body(doc: lines.LinedDoc, span: lines.SectionSpan) -> str:
    return "\n".join(x.text for x in doc.lines[span.start : span.stop])


def anchors(doc: lines.LinedDoc) -> dict[str, str]:
    """Section path → slug. Paths are already unique; slugification can still collide."""
    out: dict[str, str] = {}
    taken: dict[str, int] = {}
    for s in doc.sections:
        slug = re.sub(r"[^a-z0-9]+", "-", s.path.lower()).strip("-") or "section"
        taken[slug] = taken.get(slug, 0) + 1
        out[s.path] = slug if taken[slug] == 1 else f"{slug}-{taken[slug]}"
    return out
