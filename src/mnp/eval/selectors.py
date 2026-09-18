"""Does knowing the question help you pick the lines that answer it?

`jats.extraction_text` chooses what an extraction model reads **query-blind**: it sorts the
pieces of a paper by a hand-tuned priority and fills a 12 000-token budget from the top. This
module scores that incumbent against three rivals and a floor, on ground truth that already
exists and cost no model tokens: every row of `out/tables/d1_zeta_table.csv` carries the
`line_id` of each line its evidence was actually read from.

A selector here is `(LinedDoc, Query) -> tuple[int, ...]` — a **total ranking** of the
document's line numbers, best first. Total, not a top-k list, so recall at every k is defined
for every selector and nobody is scored on a shorter list than anybody else.

Nothing in here calls a model, a network or a clock. The only randomness is seeded.

Read `docs/FINDINGS_selector_bakeoff.md` for what the numbers came out as.
"""

from __future__ import annotations

import math
import random
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from functools import cache
from pathlib import Path

import pandas as pd

from mnp import config
from mnp.corpus import jats, lines
from mnp.corpus.lines import LinedDoc

# A term is a word or a signed decimal. Numbers are terms because half the evidence in this
# corpus *is* a number, and a tokeniser that drops "-34.2" throws the strongest signal away.
_TERM = re.compile(r"-?\d+(?:\.\d+)?|[a-z]+")

# Dropped from queries and from the leakage count. Present in almost every line, so they
# measure nothing; BM25 already discounts them by idf but the leakage number would not.
STOPWORDS = frozenset(
    "a an and the of in for with was were by to from at on as is are this that it its"
    " between using used".split()
)

# Swept on this corpus (k1 in 0.9..6.0, b in 0.0..1.0) and set to the best cell — see the
# findings doc, which also says plainly that tuning on the rows it is scored on flatters it.
# b = 1.0: full length normalisation, because a "document" here is one paragraph and the long
# ones are table dumps that would otherwise win on term count alone.
BM25_K1 = 2.0
BM25_B = 1.0

RANDOM_SEED = 20260918

# k = "the whole document". Larger than any paper here (the longest is 218 lines).
ALL_LINES = 1_000_000
DEFAULT_KS: tuple[int, ...] = (1, 3, 5, 10, 20, 40, ALL_LINES)

# `extract.zeta.MAX_TOKENS`, repeated rather than imported: `eval` importing `extract` to read
# one integer would put a constant of the reading path on the import graph of the scorer.
INCUMBENT_BUDGET = 12_000


def tokenise(text: str) -> tuple[str, ...]:
    """Lower-cased terms, with publisher dashes folded the way the evidence guard folds them.

    `lines.fold` first: a zeta printed with U+2212 must yield the same term as the same number
    typed into a query with an ASCII hyphen, or every numeric match is a coin flip on which
    minus sign the publisher used.
    """
    return tuple(_TERM.findall(lines.fold(text).lower()))


def content_terms(text: str) -> tuple[str, ...]:
    return tuple(t for t in tokenise(text) if t not in STOPWORDS)


@cache
def doc_terms(doc: LinedDoc) -> tuple[tuple[str, ...], ...]:
    """Every line of a paper tokenised once. A pure function of a frozen document, so the
    memo cannot go stale; without it the bake-off retokenises the corpus once per selector
    per k, which is most of its runtime and none of its meaning."""
    return tuple(tokenise(line.text) for line in doc.lines)


# -- queries -------------------------------------------------------------------


class Kind(StrEnum):
    """How a query field is matched against a line. The point of `structured`: a field is not
    a bag of words, it is a typed thing with its own notion of what counts as a hit."""

    lexical = "lexical"
    numeric = "numeric"
    cue = "cue"


@dataclass(frozen=True)
class QueryField:
    name: str
    text: str
    kind: Kind
    weight: float


@dataclass(frozen=True)
class Query:
    """`text` is what a lexical selector sees; `fields` is what a structured one sees.

    Both are built from the same information, so the difference between `bm25` and
    `structured` is the use made of the record's shape, not extra knowledge.
    """

    text: str
    fields: tuple[QueryField, ...] = ()

    @property
    def terms(self) -> tuple[str, ...]:
        return content_terms(self.text)


# (kind, weight) per column of `d1_zeta_table.csv`. The value outweighs everything else
# because it is the one field that is unique to the line it was read from; a material name
# appears in every paragraph of the paper.
FIELD_SPECS: dict[str, tuple[Kind, float]] = {
    "material": (Kind.lexical, 1.0),
    "functionalisation": (Kind.lexical, 1.0),
    "particle_name": (Kind.lexical, 0.5),
    "supplier": (Kind.lexical, 0.25),
    "quantity": (Kind.cue, 1.0),
    "value": (Kind.numeric, 3.0),
    "medium_text": (Kind.lexical, 1.0),
    "medium_class": (Kind.lexical, 0.5),
    "instrument": (Kind.lexical, 1.0),
    "ionic_strength_mM": (Kind.numeric, 0.5),
    "pH": (Kind.numeric, 0.5),
    "temperature_C": (Kind.numeric, 0.5),
    "size_measured_nm": (Kind.numeric, 0.5),
    "size_nominal_nm": (Kind.numeric, 0.5),
}

# What the quantity is called on the page, including the unit it is printed in.
QUANTITY_CUES: dict[str, str] = {
    "zeta_potential": "zeta potential mV surface charge",
    "electrophoretic_mobility": "electrophoretic mobility",
}

# `checklist_label` from `mnp.schema.models`, which is where these words are defined. The
# low-leakage query is built from these and from nothing the model read out of the paper.
CHECKLIST_LABELS: tuple[tuple[str, str], ...] = (
    ("material", "polymer or material"),
    ("functionalisation", "surface functionalisation"),
    ("size_measured_nm", "measured hydrodynamic size in nm"),
    ("medium_text", "dispersion medium as composed"),
    ("ionic_strength_mM", "ionic strength in mM"),
    ("pH", "pH"),
    ("temperature_C", "temperature in degrees C"),
    ("instrument", "instrument and model"),
)


def _present(row: Mapping[str, object], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    return text or None


def value_query(row: Mapping[str, object]) -> Query:
    """The question as the record itself states it — every field the row actually carries.

    This is the high-leakage form on purpose. The values in it were read *out of* the evidence
    line, so its terms are expected to appear there verbatim; `leakage` measures how much.
    """
    fields: list[QueryField] = []
    for name, (kind, weight) in FIELD_SPECS.items():
        text = _present(row, name)
        if text is None:
            continue
        if kind is Kind.cue:
            text = QUANTITY_CUES.get(text, text)
        elif name == "medium_class":
            text = text.replace("_", " ")
        fields.append(QueryField(name, text, kind, weight))
    return Query(text=" ".join(f.text for f in fields), fields=tuple(fields))


def label_query(row: Mapping[str, object]) -> Query:
    """The same question asked in words the paper never supplied: the schema's field *labels*.

    The one thing taken from the row is which quantity is being asked about, because that is
    the question rather than the answer. Everything else is a label, so a lexical selector
    gets no free hit on a number it was quietly handed.
    """
    quantity = _present(row, "quantity") or "zeta_potential"
    asked = "zeta potential" if quantity == "zeta_potential" else "electrophoretic mobility"
    fields = [QueryField("quantity", asked, Kind.cue, 1.0)]
    fields += [QueryField(name, text, Kind.lexical, 1.0) for name, text in CHECKLIST_LABELS]
    text = (
        f"What {asked} was measured, on what "
        + ", ".join(label for _, label in CHECKLIST_LABELS)
        + "?"
    )
    return Query(text=text, fields=tuple(fields))


# -- the incumbent -------------------------------------------------------------


def _priority(path: str) -> int:
    """`jats._pieces`'s priority, recovered from the section path `lines` records.

    Lower is kept first under a budget. Pinned by
    `test_incumbent_reproduces_extraction_text_verbatim_under_its_real_budget`, which compares
    the result against the real function rather than trusting this table.
    """
    if path.startswith("context:"):
        return 0
    if path.startswith("table:"):
        return 1
    if path == "methods":
        return 3
    return 2


def incumbent_kept(
    doc: LinedDoc, max_tokens: int | None
) -> tuple[tuple[str, tuple[int, ...]], ...]:
    """`(header, line numbers)` per kept piece, under `extraction_text`'s own budget loop.

    The loop is reproduced rather than called because the caller needs line *identity*, which
    the string the real function returns has already thrown away. The test compares the two
    character for character at seven budgets, so a drift in either fails loudly.
    """
    ordered = sorted(doc.sections, key=lambda s: _priority(s.path))
    if max_tokens is None:
        ordered = sorted(doc.sections, key=lambda s: -_priority(s.path))
        return tuple((s.header, tuple(x.n for x in doc.lines[s.start : s.stop])) for s in ordered)

    budget = max_tokens
    kept: list[tuple[str, tuple[int, ...]]] = []
    for span in ordered:
        header_cost = jats.approx_tokens(span.header) + 1
        if header_cost >= budget:
            break
        cost = header_cost
        taken: list[int] = []
        for line in doc.lines[span.start : span.stop]:
            c = jats.approx_tokens(line.text) + 1
            if cost + c > budget:
                continue  # the incumbent skips the oversized line and keeps looking
            taken.append(line.n)
            cost += c
        if not taken:
            continue
        kept.append((span.header, tuple(taken)))
        budget -= cost
    return tuple(kept)


def incumbent_text(doc: LinedDoc, max_tokens: int | None) -> str:
    by_n = {line.n: line.text for line in doc.lines}
    blocks = [
        header + "\n" + "\n".join(by_n[n] for n in numbers)
        for header, numbers in incumbent_kept(doc, max_tokens)
    ]
    return "\n\n".join(blocks)


# -- selectors -----------------------------------------------------------------

Selector = Callable[[LinedDoc, Query], tuple[int, ...]]


def select_whole(doc: LinedDoc, query: Query) -> tuple[int, ...]:
    """The ceiling and the honest reference: the document, in the order it is written."""
    return tuple(line.n for line in doc.lines)


def select_incumbent(doc: LinedDoc, query: Query) -> tuple[int, ...]:
    """What `extraction_text` reads first — priority order, and blind to the query."""
    order: list[int] = []
    for span in sorted(doc.sections, key=lambda s: _priority(s.path)):
        order.extend(x.n for x in doc.lines[span.start : span.stop])
    return tuple(order)


def _rank(doc: LinedDoc, scores: Sequence[float]) -> tuple[int, ...]:
    """Ties break on document order, so a selector that scores nothing degrades to `whole`."""
    return tuple(line.n for line in sorted(doc.lines, key=lambda x: (-scores[x.n - 1], x.n)))


def bm25_scores(doc: LinedDoc, query: Query, k1: float = BM25_K1, b: float = BM25_B) -> list[float]:
    """Okapi BM25 over the lines of one paper, each line a document.

    Query term frequency is ignored — only the distinct terms count — because a query built
    from a record repeats its material name three times over three fields, and weighting by
    that would score the record's redundancy rather than the paper's content.
    """
    docs = doc_terms(doc)
    n = len(docs)
    if n == 0:
        return []
    avgdl = sum(len(d) for d in docs) / n or 1.0
    terms = sorted(set(query.terms))
    counts = [{t: d.count(t) for t in terms} for d in docs]
    idf = {}
    for t in terms:
        df = sum(1 for c in counts if c[t])
        idf[t] = math.log(1 + (n - df + 0.5) / (df + 0.5))
    out = []
    for d, c in zip(docs, counts, strict=True):
        norm = k1 * (1 - b + b * len(d) / avgdl)
        out.append(sum(idf[t] * c[t] * (k1 + 1) / (c[t] + norm) for t in terms if c[t]))
    return out


def select_bm25(
    doc: LinedDoc, query: Query, k1: float = BM25_K1, b: float = BM25_B
) -> tuple[int, ...]:
    return _rank(doc, bm25_scores(doc, query, k1, b))


def _numbers(terms: Iterable[str]) -> list[float]:
    out = []
    for t in terms:
        try:
            out.append(float(t))
        except ValueError:
            pass
    return out


def _numeric_hit(wanted: float, found: Sequence[float]) -> bool:
    """A printed number rounds; 0.5 % or 0.05, whichever is larger, is the slack for that."""
    tol = max(0.05, 0.005 * abs(wanted))
    return any(abs(x - wanted) <= tol for x in found)


def structured_scores(doc: LinedDoc, query: Query) -> list[float]:
    """Retrieval over the record's fields as typed edges, not over its words as a bag.

    Each field asks its own question of the line: a lexical field asks what fraction of its
    words are here, a numeric field asks whether its number is printed here, a cue field asks
    whether the quantity is named here. The weights are in `FIELD_SPECS`.
    """
    per_line_terms = [set(t) for t in doc_terms(doc)]
    per_line_numbers = [_numbers(t) for t in per_line_terms]
    scores = [0.0] * len(doc.lines)
    for f in query.fields:
        if f.kind is Kind.numeric:
            wanted = _numbers(tokenise(f.text))
            if not wanted:
                continue
            for i, found in enumerate(per_line_numbers):
                if _numeric_hit(wanted[0], found):
                    scores[i] += f.weight
            continue
        wanted_terms = set(content_terms(f.text))
        if not wanted_terms:
            continue
        for i, present in enumerate(per_line_terms):
            hit = len(wanted_terms & present)
            if hit:
                scores[i] += f.weight * hit / len(wanted_terms)
    return scores


def select_structured(doc: LinedDoc, query: Query) -> tuple[int, ...]:
    return _rank(doc, structured_scores(doc, query))


def select_random(doc: LinedDoc, query: Query, seed: int = RANDOM_SEED) -> tuple[int, ...]:
    """The floor. Seeded per paper, so the number is reproducible and not one lucky draw."""
    order = [line.n for line in doc.lines]
    random.Random(f"{seed}:{doc.pmcid}").shuffle(order)
    return tuple(order)


SELECTORS: dict[str, Selector] = {
    "whole": select_whole,
    "incumbent": select_incumbent,
    "bm25": select_bm25,
    "structured": select_structured,
    "random": select_random,
}


# -- scoring -------------------------------------------------------------------


@dataclass(frozen=True)
class Case:
    """One row of the published table: a question, the paper, and the lines that answer it."""

    pmcid: str
    row_id: str
    doc: LinedDoc
    evidence: frozenset[str]
    query: Query


@dataclass(frozen=True)
class Score:
    selector: str
    k: int
    rows: int
    recall: float
    partial: float
    tokens: float

    @property
    def recall_per_1k_tokens(self) -> float:
        return self.recall / (self.tokens / 1000) if self.tokens else 0.0


def _top_ids(doc: LinedDoc, ranked: Sequence[int], k: int) -> set[str]:
    return {doc.lines[n - 1].line_id for n in ranked[:k]}


def recall_at_k(doc: LinedDoc, ranked: Sequence[int], evidence: frozenset[str], k: int) -> float:
    """1.0 only when **every** evidence line is in the top k.

    A row whose value line is retrieved and whose ionic-strength line is not cannot be
    answered, so partial credit here would be credit for an answer nobody could give.
    """
    return 1.0 if evidence and evidence <= _top_ids(doc, ranked, k) else 0.0


def partial_recall_at_k(
    doc: LinedDoc, ranked: Sequence[int], evidence: frozenset[str], k: int
) -> float:
    if not evidence:
        return 0.0
    return len(evidence & _top_ids(doc, ranked, k)) / len(evidence)


def tokens_at_k(doc: LinedDoc, ranked: Sequence[int], k: int) -> int:
    """`len/4` plus one separator per line — `jats.approx_tokens`, the budget loop's own
    measure. Approximate: `tiktoken` is not a dependency here and is not being added."""
    return sum(jats.approx_tokens(doc.lines[n - 1].text) + 1 for n in ranked[:k])


def score(
    cases: Sequence[Case], name: str, selector: Selector, ks: Sequence[int] = DEFAULT_KS
) -> tuple[Score, ...]:
    ranked = [selector(c.doc, c.query) for c in cases]
    out = []
    for k in ks:
        n = len(cases) or 1
        out.append(
            Score(
                selector=name,
                k=k,
                rows=len(cases),
                recall=sum(
                    recall_at_k(c.doc, r, c.evidence, k) for c, r in zip(cases, ranked, strict=True)
                )
                / n,
                partial=sum(
                    partial_recall_at_k(c.doc, r, c.evidence, k)
                    for c, r in zip(cases, ranked, strict=True)
                )
                / n,
                tokens=sum(tokens_at_k(c.doc, r, k) for c, r in zip(cases, ranked, strict=True))
                / n,
            )
        )
    return tuple(out)


def score_incumbent_at_budget(cases: Sequence[Case], budget: int = INCUMBENT_BUDGET) -> Score:
    """The incumbent at its **real** operating point: the set it actually hands the model.

    Not a top-k prefix — the budget loop's own selection, per paper, at the budget production
    runs it at. This is the number the rivals have to beat to change anything.
    """
    recall = partial = tokens = 0.0
    for c in cases:
        kept = [n for _, numbers in incumbent_kept(c.doc, budget) for n in numbers]
        ids = {c.doc.lines[n - 1].line_id for n in kept}
        recall += 1.0 if c.evidence and c.evidence <= ids else 0.0
        partial += len(c.evidence & ids) / len(c.evidence) if c.evidence else 0.0
        tokens += tokens_at_k(c.doc, kept, len(kept))
    n = len(cases) or 1
    return Score("incumbent@budget", budget, len(cases), recall / n, partial / n, tokens / n)


# -- the confound --------------------------------------------------------------


def leakage(case: Case, seed: int = RANDOM_SEED) -> tuple[float, float] | None:
    """Fraction of query terms printed verbatim in the evidence lines, versus in a random
    other line of the same paper.

    A query built from a record's own fields is built from words that were read out of the
    evidence line, so a lexical selector may be finding its own answer. The gap between these
    two numbers is how much it is being flattered. `None` when the paper has no other line to
    compare against — a one-line document measures nothing.
    """
    terms = set(case.query.terms)
    if not terms:
        return None
    target = [x for x in case.doc.lines if x.line_id in case.evidence]
    other = [x for x in case.doc.lines if x.line_id not in case.evidence]
    if not target or not other:
        return None
    here = set().union(*(set(tokenise(x.text)) for x in target))
    picked = random.Random(f"{seed}:{case.row_id}").choice(other)
    there = set(tokenise(picked.text))
    return len(terms & here) / len(terms), len(terms & there) / len(terms)


# -- loading the corpus --------------------------------------------------------


@dataclass
class Corpus:
    table: pd.DataFrame
    docs: dict[str, LinedDoc] = field(default_factory=dict)


def load_corpus(table_path: Path | None = None) -> Corpus:
    path = table_path or (config.OUT_TABLES / "d1_zeta_table.csv")
    table = pd.read_csv(path)
    table = table[table["evidence_line_ids"].notna()].copy()
    docs: dict[str, LinedDoc] = {}
    for pmcid in sorted(table["pmcid"].unique()):
        xml = config.EPMC_XML_DIR / f"{pmcid}.xml"
        if not xml.is_file():
            continue
        article = jats.parse(xml.read_bytes())
        article.pmcid = pmcid
        docs[pmcid] = lines.build_lines(article)
    return Corpus(table=table, docs=docs)


def build_cases(
    corpus: Corpus, query_builder: Callable[[Mapping[str, object]], Query] = value_query
) -> tuple[Case, ...]:
    """One case per published row whose evidence ids all resolve in its own line document."""
    out: list[Case] = []
    for row in corpus.table.to_dict("records"):
        doc = corpus.docs.get(row["pmcid"])
        if doc is None:
            continue
        evidence = frozenset(str(row["evidence_line_ids"]).split(";"))
        known = {x.line_id for x in doc.lines}
        if not evidence or not evidence <= known:
            continue
        out.append(
            Case(
                pmcid=row["pmcid"],
                row_id=row["row_id"],
                doc=doc,
                evidence=evidence,
                query=query_builder(row),
            )
        )
    return tuple(out)
