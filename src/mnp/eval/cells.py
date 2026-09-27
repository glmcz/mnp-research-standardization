"""The per-cell context builders — the exact text an answering subagent is handed.

Four cells of ``docs/DESIGN_2026-09-17_tool-value-grid.md`` §1, one axis moved at a time:

=======  =======================  ==================================================
cell     substrate x control      what it is given
=======  =======================  ==================================================
**B**    S1 x C2                  the tuned BM25's top k lines, one shot, no tools
**D**    S2 x C3                  a static route: the table first, prose as fallback
**C**    S1 x C4                  prose tools and an initial state; the KB withheld
**E**    S2 x C4                  the same tools, plus the KB tools
=======  =======================  ==================================================

B and D are **fully precomputed here**: their prompt is a pure function of the question and the
corpus, so a run can be inspected, re-run and diffed without a model. C and E cannot be — the
agent decides what to fetch next — so what is built for them is the tool *contract* plus a
deterministic implementation of every tool, which the parent session drives one call at a time.

Nothing in this module calls a model, a network or a clock.

Three decisions that shape what the numbers will mean, stated here rather than discovered later:

* **The retrieval is the one E6 already tuned.** :class:`LineIndex` is an inverted-index
  accelerator over ``selectors.bm25_scores``, not a second ranker: a line carrying no query term
  scores exactly zero and ties break on document order, so restricting scoring to the posting
  lists returns the identical ranking. A test pins that against ``selectors.select_bm25`` line
  for line, because "we tuned a different BM25 for the baseline" would be a fair objection.
* **Cell B is scoped to the paper when the question names one.** That is what building it to win
  means, and it is also the honest reading of the question. It has a consequence worth naming:
  a paper averages 44 lines, so :data:`PAPER_K` = 30 hands over most of a short paper. On
  paper-scoped kinds cell B is nearly a long-context cell at paper scale, and any structure
  advantage measured against it is therefore *not* an artefact of retrieval missing the line.
* **Cell D falls back to prose.** C3 is a static *route*, not a table-only cell. Without the
  fallback, kind D would be losable by construction and the grid would prove nothing; with it,
  cell D is handed exactly what cell B is handed whenever the table has no field for the
  question, and any difference between them on kind D is the model's, not the harness's.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from mnp import config
from mnp.corpus import jats, lines
from mnp.corpus.lines import LinedDoc
from mnp.eval import selectors
from mnp.eval.comparability import (
    BLOCKER_FIELDS,
    ZetaRow,
    comparable,
    functionalisation_key,
    material_key,
)
from mnp.eval.query_sets import FilterSpec, QueryKind, Question, apply_filter

#: Top k for a question that names one paper. See the module note: a paper is ~44 lines.
PAPER_K = 30
#: Top k for a corpus-wide question. Ten papers' worth of lines, before the agent asks for more.
CORPUS_K = 40
#: What a single `read_paper` call returns before the agent has to ask for the next window.
PAGE = 40

approx_tokens = jats.approx_tokens


def _str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


# -- the corpus --------------------------------------------------------------------------------


@dataclass
class Corpus:
    """Both substrates at once: S1 (line-addressed prose) and S2 (the published records).

    A cell is given one of them. Holding both in one object is what lets the same question,
    the same seed and the same tokeniser serve every cell in the grid.
    """

    docs: dict[str, LinedDoc] = field(default_factory=dict)
    table: pd.DataFrame | None = None

    @property
    def rows(self) -> tuple[Mapping[str, Any], ...]:
        if self.table is None:
            return ()
        return tuple(self.table.to_dict(orient="records"))

    def row(self, row_id: str) -> Mapping[str, Any] | None:
        return next((r for r in self.rows if _str(r.get("row_id")) == row_id), None)


def load_corpus(pmcids: Iterable[str] | None = None) -> Corpus:
    """Parse the vendored XML into line documents. ~4 s for 491 papers, zero model tokens."""
    table = pd.read_csv(config.OUT_TABLES / "d1_zeta_table.csv")
    wanted = sorted(set(pmcids)) if pmcids is not None else sorted(table["pmcid"].unique())
    docs: dict[str, LinedDoc] = {}
    for pmcid in wanted:
        path = config.EPMC_XML_DIR / f"{pmcid}.xml"
        if not path.is_file():
            continue
        article = jats.parse(path.read_bytes())
        article.pmcid = pmcid
        docs[pmcid] = lines.build_lines(article)
    return Corpus(docs=docs, table=table)


def flatten(corpus: Corpus) -> tuple[LinedDoc, tuple[tuple[str, int], ...]]:
    """The whole corpus as one `LinedDoc`, plus the (pmcid, n) each flat line came from.

    This exists so `selectors.select_bm25` — the tuned one — can be run corpus-wide unchanged
    in the equivalence test. The real search path uses `LineIndex`, which returns the same
    ranking without scoring 21 700 lines per query.
    """
    rows: list[lines.Line] = []
    spans: list[lines.SectionSpan] = []
    addresses: list[tuple[str, int]] = []
    for pmcid in sorted(corpus.docs):
        doc = corpus.docs[pmcid]
        start = len(rows)
        for line in doc.lines:
            rows.append(
                lines.Line(len(rows) + 1, line.text, line.section_path, line.ordinal, line.line_id)
            )
            addresses.append((pmcid, line.n))
        spans.append(lines.SectionSpan(pmcid, f"== {pmcid}", start, len(rows)))
    return LinedDoc(pmcid=None, lines=tuple(rows), sections=tuple(spans)), tuple(addresses)


@dataclass(frozen=True)
class Hit:
    pmcid: str
    n: int
    line_id: str
    text: str
    score: float

    @property
    def cite(self) -> str:
        return f"{self.pmcid}:L{self.n}"


class LineIndex:
    """Okapi BM25 over every line of the corpus, with `selectors`' constants and tokeniser.

    Not a second ranker. `selectors.bm25_scores` gives a line with no query term a score of
    exactly zero and `selectors._rank` breaks ties on document order, so scoring only the lines
    on a query term's posting list and appending the rest in order is the same ranking. The
    inverted index is what makes that affordable at 21 700 lines and nine tool calls a question.
    """

    def __init__(self, corpus: Corpus, k1: float = selectors.BM25_K1, b: float = selectors.BM25_B):
        self.k1, self.b = k1, b
        self._lines: list[Hit] = []
        self._terms: list[tuple[str, ...]] = []
        for pmcid in sorted(corpus.docs):
            for line in corpus.docs[pmcid].lines:
                self._lines.append(Hit(pmcid, line.n, line.line_id, line.text, 0.0))
                self._terms.append(selectors.tokenise(line.text))
        self._lengths = [len(terms) for terms in self._terms]
        self._n = len(self._lines)
        self._avgdl = (sum(self._lengths) / self._n) if self._n else 1.0
        self._postings: dict[str, list[tuple[int, int]]] = {}
        for i, terms in enumerate(self._terms):
            counts: dict[str, int] = {}
            for term in terms:
                counts[term] = counts.get(term, 0) + 1
            for term, count in counts.items():
                self._postings.setdefault(term, []).append((i, count))

    def _scores(self, query: str) -> dict[int, float]:
        terms = sorted(set(selectors.Query(text=query).terms))
        scores: dict[int, float] = {}
        for term in terms:
            posting = self._postings.get(term)
            if not posting:
                continue
            df = len(posting)
            idf = math.log(1 + (self._n - df + 0.5) / (df + 0.5))
            for i, count in posting:
                norm = self.k1 * (1 - self.b + self.b * self._lengths[i] / self._avgdl)
                scores[i] = scores.get(i, 0.0) + idf * count * (self.k1 + 1) / (count + norm)
        return scores

    def _order(self, query: str, pmcid: str | None = None) -> list[int]:
        scores = self._scores(query)
        allowed = range(self._n)
        if pmcid is not None:
            allowed = [i for i in range(self._n) if self._lines[i].pmcid == pmcid]
        return sorted(allowed, key=lambda i: (-scores.get(i, 0.0), i))

    def ranking(self, query: str, pmcid: str | None = None) -> list[tuple[str, int]]:
        return [(self._lines[i].pmcid, self._lines[i].n) for i in self._order(query, pmcid)]

    def search(self, query: str, k: int = 10, pmcid: str | None = None) -> tuple[Hit, ...]:
        scores = self._scores(query)
        order = self._order(query, pmcid)[: max(0, int(k))]
        found = []
        for i in order:
            hit = self._lines[i]
            found.append(Hit(hit.pmcid, hit.n, hit.line_id, hit.text, scores.get(i, 0.0)))
        return tuple(found)

    def papers(self, query: str, k: int = 10) -> tuple[tuple[str, float], ...]:
        """Papers ranked by their best-scoring line. The cheapest honest corpus-wide sweep."""
        scores = self._scores(query)
        best: dict[str, float] = {}
        for i, score in scores.items():
            pmcid = self._lines[i].pmcid
            if score > best.get(pmcid, 0.0):
                best[pmcid] = score
        ordered = sorted(best.items(), key=lambda pair: (-pair[1], pair[0]))
        return tuple(ordered[: max(0, int(k))])


_INDEX_CACHE: dict[int, LineIndex] = {}


def index(corpus: Corpus) -> LineIndex:
    """One index per corpus object. Building it is ~2 s; a question must not pay that twice."""
    key = id(corpus)
    found = _INDEX_CACHE.get(key)
    if found is None:
        found = LineIndex(corpus)
        _INDEX_CACHE[key] = found
    return found


# -- the instructions, identical in every cell ---------------------------------------------------
#
# If the rules or the output contract differed between cells, every delta in the results table
# would be confounded by prompt wording. A test asserts all four carry the same two blocks.

_RULES_COMMON = """RULES
- Answer only from the evidence you were given or fetched. Do not use background knowledge.
- A condition that is not stated in the evidence is NOT REPORTED. Never default it, never
  estimate it, and never carry it over from another paper or another measurement.
- "not reported" is a correct and expected answer. Prefer it to a guess.
- Cite the evidence for every claim. A line citation is written PMCID:Lnn (for example
  PMC1234567:L212). A record citation is written row:ROW_ID.
- Do not restate the question or explain your reasoning outside the JSON object."""

_CONTRACTS: dict[QueryKind, str] = {
    QueryKind.a: """OUTPUT
Return exactly one JSON object and nothing else:
{"value": <number>, "unit": "<string>", "ionic_strength_reported": <true|false>,
 "ionic_strength_mM": <number or null>, "citations": ["<citation>", ...]}""",
    QueryKind.b: """OUTPUT
Return exactly one JSON object and nothing else:
{"reported": <true|false>, "value": <number or null>, "citations": ["<citation>", ...]}
If the papers did not report it, "reported" is false and "value" MUST be null.""",
    QueryKind.c: """OUTPUT
Return exactly one JSON object and nothing else:
{"pmcids": ["<PMCID>", ...], "citations": ["<citation>", ...]}""",
    QueryKind.e: """OUTPUT
Return exactly one JSON object and nothing else:
{"verdict": "comparable" | "conditionally_comparable" | "not_comparable",
 "blockers": ["<field that blocks the comparison>", ...], "citations": ["<citation>", ...]}
Each blocker is one of these field names: """
    + ", ".join(BLOCKER_FIELDS)
    + ".",
    QueryKind.d: """OUTPUT
Return exactly one JSON object and nothing else:
{"answer": "<two to four sentences>", "citations": ["<citation>", ...]}""",
}


def rules_block(kind: QueryKind) -> str:
    return _RULES_COMMON


def answer_contract(kind: QueryKind) -> str:
    return _CONTRACTS[QueryKind(kind)]


# -- what a cell delivered ------------------------------------------------------------------------


@dataclass(frozen=True)
class Delivered:
    """The exact prompt, and an account of what was in it. Diffable, re-runnable, model-free."""

    cell: str
    qid: str
    prompt: str
    line_ids: tuple[str, ...] = ()
    row_ids: tuple[str, ...] = ()
    route: str = ""

    @property
    def tokens(self) -> int:
        return approx_tokens(self.prompt)


_EVIDENCE_MARK = "EVIDENCE"


def _evidence_of(prompt: str) -> str:
    """The body of an assembled prompt's EVIDENCE block, so one cell can reuse another's."""
    block = prompt.split(f"\n\n{_EVIDENCE_MARK}", 1)[1]
    return block.split("\n", 1)[1].split("\n\nRULES", 1)[0]


def _assemble(question: Question, body_header: str, body: str) -> str:
    return "\n\n".join(
        [
            "You are answering one question about a corpus of micro- and nanoplastic papers.",
            f"QUESTION\n{question.text}",
            f"{body_header}\n{body}",
            rules_block(question.kind),
            answer_contract(question.kind),
        ]
    )


# -- cell B: S1 x C2, one shot ----------------------------------------------------------------- ---


def _scope(question: Question) -> str | None:
    """The one paper a question is about, or `None` when it is about more than one or none."""
    return question.scope[0] if len(question.scope) == 1 else None


def build_b(question: Question, corpus: Corpus, k: int | None = None) -> Delivered:
    """The tuned BM25's top k lines and nothing else. No table, no tools, one shot."""
    scope = question.scope
    budget = k if k is not None else (PAPER_K if scope else CORPUS_K)
    if len(scope) > 1:
        # A kind E pair names two papers. Splitting the budget between them is the only way the
        # cell can see both sides of the comparison; taking a global top k would let the
        # better-matching paper eat the whole budget and leave the question unanswerable.
        hits = tuple(
            hit
            for pmcid in scope
            for hit in index(corpus).search(question.text, k=budget, pmcid=pmcid)
        )
    else:
        hits = index(corpus).search(question.text, k=budget, pmcid=_scope(question))
    body = "\n".join(f"{hit.cite}\t{hit.text}" for hit in hits) or "(nothing retrieved)"
    return Delivered(
        cell="B",
        qid=question.qid,
        prompt=_assemble(question, "EVIDENCE — retrieved lines", body),
        line_ids=tuple(hit.line_id for hit in hits),
        route="bm25",
    )


# -- cell D: S2 x C3, the static route --------------------------------------------------------- ---

_RECORD_COLUMNS = (
    "row_id",
    "pmcid",
    "quantity",
    "material",
    "functionalisation",
    "particle_name",
    "size_measured_nm",
    "value",
    "unit",
    "sd",
    "n",
    "medium_text",
    "medium_class",
    "ionic_strength_mM",
    "ionic_strength_source",
    "pH",
    "pH_text",
    "temperature_C",
    "temperature_qualifier",
    "instrument",
    "medium_reported",
    "ionic_strength_reported",
    "pH_reported",
    "temperature_reported",
    "instrument_reported",
    "conditions_complete",
)


def render_row(row: Mapping[str, Any], columns: Sequence[str] = _RECORD_COLUMNS) -> str:
    """One record, every field named — including the fields that are False.

    An unreported condition is printed as `ionic_strength_reported=False`, not omitted. That
    difference is the entire argument for the structured substrate: a blank is something a
    reader has to interpret, a False is something a paper said nothing about.
    """
    parts = []
    for column in columns:
        value = row.get(column)
        parts.append(f"{column}={_str(value) if _str(value) else 'null'}")
    return " | ".join(parts)


def _route_note(question: Question) -> str:
    """What the static router conditioned on, printed with the records it returned.

    A router that will not say what it filtered on is not inspectable, and this line is also
    the tripwire: it puts `Question.target` in front of the reader, so a targeting field that
    quietly grew an answer column shows up in `test_no_cell_leaks_the_answer_key_into_its_prompt`
    rather than in the results table.
    """
    if not question.target:
        return "(routed on: the paper alone)"
    stated = ", ".join(f"{name}={value}" for name, value in question.target)
    return f"(routed on: {stated})"


def _rows_for_lookup(question: Question, corpus: Corpus) -> list[Mapping[str, Any]]:
    """The static router's filter for kind A: the paper, then the conditions the question states.

    Deliberately **not** the gold row id. The question states a material, a functionalisation
    and a medium; those are what a router could condition on if a user asked this. Filtering by
    the row the answer came from would hand cell D the answer and make its accuracy meaningless.
    """
    pmcid = _scope(question)
    rows = [r for r in corpus.rows if not pmcid or _str(r.get("pmcid")) == pmcid]
    material = question.targeting("material")
    if material:
        key = material_key(material)
        narrowed = [r for r in rows if material_key(_str(r.get("material")) or None) == key]
        rows = narrowed or rows
    functionalisation = question.targeting("functionalisation")
    if functionalisation:
        key = functionalisation_key(functionalisation)
        narrowed = [
            r
            for r in rows
            if functionalisation_key(_str(r.get("functionalisation")) or None) == key
        ]
        rows = narrowed or rows
    quantity = question.targeting("quantity")
    if quantity:
        rows = [r for r in rows if _str(r.get("quantity")) == quantity] or rows
    return rows


def _rows_for_filter(question: Question, corpus: Corpus) -> list[Mapping[str, Any]]:
    payload = question.targeting("filter_json")
    if not payload:
        return []
    return list(apply_filter(corpus.rows, FilterSpec(**json.loads(payload))))


def build_d(question: Question, corpus: Corpus) -> Delivered:
    """Structured filter first; prose retrieval when the table has no field for the question."""
    kind = QueryKind(question.kind)
    if kind is QueryKind.e:
        return build_d_comparability(
            question, corpus, question.targeting("row_id_a"), question.targeting("row_id_b")
        )
    rows: list[Mapping[str, Any]] = []
    if question.targeting("structured_field") != "none":
        if kind is QueryKind.c:
            rows = _rows_for_filter(question, corpus)
        elif kind in (QueryKind.a, QueryKind.b):
            rows = _rows_for_lookup(question, corpus)

    if not rows:
        fallback = build_b(question, corpus)
        return Delivered(
            cell="D",
            qid=question.qid,
            prompt=_assemble(
                question,
                "EVIDENCE — the structured records hold no field that answers this question, "
                "so retrieved lines are given instead",
                _evidence_of(fallback.prompt),
            ),
            line_ids=fallback.line_ids,
            route="prose_fallback",
        )

    body = f"{_route_note(question)}\n" + "\n".join(render_row(row) for row in rows)
    return Delivered(
        cell="D",
        qid=question.qid,
        prompt=_assemble(question, "EVIDENCE — structured records", body),
        row_ids=tuple(_str(row.get("row_id")) for row in rows),
        route="structured",
    )


def build_d_comparability(
    question: Question, corpus: Corpus, row_id_a: str, row_id_b: str
) -> Delivered:
    """Kind E through the static route: the pair, the verdict, and the fields that block it.

    Kind E's key already exists in `comparability.py`; this only renders it as context, so cell
    D answers the same question the other cells are asked rather than a reformulation of it.
    """
    left, right = corpus.row(row_id_a), corpus.row(row_id_b)
    if left is None or right is None:
        return build_b(question, corpus)
    verdict = comparable(ZetaRow.from_mapping(dict(left)), ZetaRow.from_mapping(dict(right)))
    blockers = (
        "\n".join(
            f"  {b.code}\tfield={b.field}\tkind={b.kind.value}\t{b.detail}"
            for b in verdict.blockers
        )
        or "  (none)"
    )
    body = (
        f"{render_row(left)}\n{render_row(right)}\n\n"
        f"comparability_verdict={verdict.verdict.value}\nblockers:\n{blockers}"
    )
    return Delivered(
        cell="D",
        qid=question.qid,
        prompt=_assemble(question, "EVIDENCE — structured records", body),
        row_ids=(row_id_a, row_id_b),
        route="structured",
    )


# -- cells C and E: the tool contract -------------------------------------------------------------


@dataclass(frozen=True)
class ToolSpec:
    name: str
    signature: str
    returns: str
    description: str = ""

    def render(self) -> str:
        return f"- {self.signature}\n    {self.description}\n    returns: {self.returns}"


TOOLS_PROSE: tuple[ToolSpec, ...] = (
    ToolSpec(
        "search_lines",
        "search_lines(query: str, k: int = 10, pmcid: str | null = null)",
        "one line per hit, as PMCID:Lnn<TAB>text, best first",
        "BM25 over every line of every paper. Scope it to one paper with pmcid.",
    ),
    ToolSpec(
        "read_paper",
        "read_paper(pmcid: str, start: int = 1, count: int = 40)",
        "consecutive lines of that paper, as PMCID:Lnn<TAB>text",
        "Read a window of one paper in written order. Use it after search_lines locates a line.",
    ),
    ToolSpec(
        "list_papers",
        "list_papers(query: str, k: int = 10)",
        "one PMCID per line with its best line score",
        "Which papers contain anything matching the query, ranked by their best line.",
    ),
)

TOOLS_KB: tuple[ToolSpec, ...] = (
    ToolSpec(
        "query_rows",
        (
            "query_rows(quantity: str | null = null, material: str | null = null, "
            "functionalisation: str | null = null, medium_class: str | null = null, "
            "pmcid: str | null = null, ionic_strength_min: number | null = null, "
            "ionic_strength_max: number | null = null, pH_min: number | null = null, "
            "pH_max: number | null = null, size_min: number | null = null, "
            "size_max: number | null = null, limit: int = 50)"
        ),
        "one extracted record per line, every field named, including the *_reported booleans",
        "Filter the extracted records. A record whose value is unreported never matches a range.",
    ),
    ToolSpec(
        "get_row",
        "get_row(row_id: str)",
        "one record, every field named, plus the line ids its evidence was read from",
        "Fetch one record by id.",
    ),
    ToolSpec(
        "paper_conditions",
        "paper_conditions(pmcid: str)",
        "per condition: whether that paper reported it, and the value if it did",
        "What a paper did and did not report. False means the paper never stated it.",
    ),
    ToolSpec(
        "compare_rows",
        "compare_rows(row_id_a: str, row_id_b: str)",
        "a verdict of comparable | conditionally_comparable | not_comparable, and the blockers",
        "May these two measurements be compared, and which fields block the comparison.",
    ),
)


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: Mapping[str, Any] = field(default_factory=dict)

    def key(self) -> str:
        return f"{self.name}({json.dumps(dict(self.args), sort_keys=True, default=str)})"


@dataclass(frozen=True)
class ToolResult:
    text: str
    tokens: int = 0
    line_ids: tuple[str, ...] = ()
    row_ids: tuple[str, ...] = ()
    error: bool = False


@dataclass(frozen=True)
class Session:
    """The initial state of an agentic cell, and the tools it is allowed to call."""

    cell: str
    qid: str
    kind: QueryKind
    question: str
    prompt: str
    tools: tuple[ToolSpec, ...]
    scope: tuple[str, ...] = ()

    @property
    def tool_names(self) -> frozenset[str]:
        return frozenset(tool.name for tool in self.tools)

    @property
    def tokens(self) -> int:
        return approx_tokens(self.prompt)


_LOOP = """HOW TO WORK
- You may call the tools above as many times as you need, one at a time, and you decide when
  you have enough. Every call is counted and reported, so do not call a tool you do not need.
- Write a call as a single line: CALL <name> <json object of arguments>
- You will be given that call's result, and then you may call again or answer.
- When you are ready, stop calling tools and emit the JSON object described under OUTPUT."""


def _session(question: Question, cell: str, tools: tuple[ToolSpec, ...]) -> Session:
    scoped = (
        f"\n\nThe question is about {', '.join(question.scope)}."
        if question.scope
        else "\n\nThe question is about the whole corpus; no paper is named for you."
    )
    prompt = "\n\n".join(
        [
            "You are answering one question about a corpus of micro- and nanoplastic papers.",
            f"QUESTION\n{question.text}{scoped}",
            "TOOLS\n" + "\n".join(tool.render() for tool in tools),
            _LOOP,
            rules_block(question.kind),
            answer_contract(question.kind),
        ]
    )
    return Session(
        cell=cell,
        qid=question.qid,
        kind=QueryKind(question.kind),
        question=question.text,
        prompt=prompt,
        tools=tools,
        scope=question.scope,
    )


def session_c(question: Question) -> Session:
    """S1 x C4 — the dangerous rival. Prose tools, an agent loop, and no knowledge base."""
    return _session(question, "C", TOOLS_PROSE)


def session_e(question: Question) -> Session:
    """S2 x C4 — the same loop with the knowledge base added. The C->E delta is the finding."""
    return _session(question, "E", TOOLS_PROSE + TOOLS_KB)


# -- the deterministic implementation of every tool -------------------------------------------- ---


def _err(message: str) -> ToolResult:
    return ToolResult(text=message, tokens=approx_tokens(message), error=True)


def _lines_result(hits: Sequence[Hit]) -> ToolResult:
    text = "\n".join(f"{hit.cite}\t{hit.text}" for hit in hits) or "(no matching lines)"
    return ToolResult(
        text=text, tokens=approx_tokens(text), line_ids=tuple(hit.line_id for hit in hits)
    )


def _rows_result(rows: Sequence[Mapping[str, Any]], columns=_RECORD_COLUMNS) -> ToolResult:
    text = "\n".join(render_row(row, columns) for row in rows) or "(no matching records)"
    return ToolResult(
        text=text,
        tokens=approx_tokens(text),
        row_ids=tuple(_str(row.get("row_id")) for row in rows),
    )


_CONDITION_FIELDS = (
    ("medium", "medium_text"),
    ("ionic_strength", "ionic_strength_mM"),
    ("pH", "pH"),
    ("temperature", "temperature_C"),
    ("instrument", "instrument"),
)


def dispatch(session: Session, corpus: Corpus, call: ToolCall) -> ToolResult:
    """Run one tool call. Deterministic, offline, and gated by the cell's own tool list."""
    if call.name not in session.tool_names:
        known = ", ".join(sorted(session.tool_names))
        return _err(f"no such tool in this cell: {call.name}. Available: {known}")
    handler = _HANDLERS.get(call.name)
    if handler is None:  # pragma: no cover - a spec without a handler is a bug, not a call
        return _err(f"no such tool: {call.name}")
    try:
        return handler(corpus, dict(call.args))
    except (KeyError, TypeError, ValueError) as exc:
        return _err(f"{call.name} failed: {exc}")


def _t_search_lines(corpus: Corpus, args: Mapping[str, Any]) -> ToolResult:
    query = str(args["query"])
    k = int(args.get("k", 10))
    pmcid = args.get("pmcid") or None
    return _lines_result(index(corpus).search(query, k=k, pmcid=pmcid))


def _t_read_paper(corpus: Corpus, args: Mapping[str, Any]) -> ToolResult:
    pmcid = str(args["pmcid"])
    doc = corpus.docs.get(pmcid)
    if doc is None:
        return _err(f"no such paper: {pmcid}")
    start = max(1, int(args.get("start", 1)))
    count = max(1, min(int(args.get("count", PAGE)), PAGE))
    window = doc.lines[start - 1 : start - 1 + count]
    hits = [Hit(pmcid, line.n, line.line_id, line.text, 0.0) for line in window]
    result = _lines_result(hits)
    tail = f"\n({len(doc.lines)} lines in this paper)"
    return ToolResult(
        text=result.text + tail,
        tokens=approx_tokens(result.text + tail),
        line_ids=result.line_ids,
    )


def _t_list_papers(corpus: Corpus, args: Mapping[str, Any]) -> ToolResult:
    query = str(args["query"])
    k = int(args.get("k", 10))
    found = index(corpus).papers(query, k=k)
    text = "\n".join(f"{pmcid}\t{score:.3f}" for pmcid, score in found) or "(no matching papers)"
    return ToolResult(text=text, tokens=approx_tokens(text))


_FILTER_KEYS = {
    "quantity",
    "material",
    "functionalisation",
    "medium_class",
    "ionic_strength_min",
    "ionic_strength_max",
    "pH_min",
    "pH_max",
    "size_min",
    "size_max",
}


def _t_query_rows(corpus: Corpus, args: Mapping[str, Any]) -> ToolResult:
    spec_args = {
        name: value for name, value in args.items() if name in _FILTER_KEYS and value is not None
    }
    if "material" in spec_args:
        spec_args["material"] = material_key(str(spec_args["material"]))
    if "functionalisation" in spec_args:
        spec_args["functionalisation"] = functionalisation_key(str(spec_args["functionalisation"]))
    rows = apply_filter(corpus.rows, FilterSpec(**spec_args))
    pmcid = args.get("pmcid")
    if pmcid:
        rows = [row for row in rows if _str(row.get("pmcid")) == str(pmcid)]
    limit = max(1, int(args.get("limit", 50)))
    return _rows_result(rows[:limit])


def _t_get_row(corpus: Corpus, args: Mapping[str, Any]) -> ToolResult:
    row = corpus.row(str(args["row_id"]))
    if row is None:
        return _err(f"no such record: {args['row_id']}")
    return _rows_result([row], (*_RECORD_COLUMNS, "evidence_line_ids"))


def _t_paper_conditions(corpus: Corpus, args: Mapping[str, Any]) -> ToolResult:
    pmcid = str(args["pmcid"])
    rows = [row for row in corpus.rows if _str(row.get("pmcid")) == pmcid]
    if not rows:
        return _err(f"no records for paper: {pmcid}")
    out = [f"pmcid={pmcid} records={len(rows)}"]
    for name, column in _CONDITION_FIELDS:
        reported = sorted({bool(row.get(f"{name}_reported")) for row in rows})
        values = sorted({_str(row.get(column)) for row in rows} - {""})
        state = "True" if reported == [True] else ("False" if reported == [False] else "mixed")
        out.append(f"{name}_reported={state}\t{name}_values={';'.join(values) or 'null'}")
    text = "\n".join(out)
    return ToolResult(
        text=text, tokens=approx_tokens(text), row_ids=tuple(_str(r.get("row_id")) for r in rows)
    )


def _t_compare_rows(corpus: Corpus, args: Mapping[str, Any]) -> ToolResult:
    left, right = corpus.row(str(args["row_id_a"])), corpus.row(str(args["row_id_b"]))
    if left is None or right is None:
        return _err("no such record")
    verdict = comparable(ZetaRow.from_mapping(dict(left)), ZetaRow.from_mapping(dict(right)))
    blockers = (
        "\n".join(
            f"{b.code}\tfield={b.field}\tkind={b.kind.value}\t{b.detail}" for b in verdict.blockers
        )
        or "(none)"
    )
    text = f"verdict={verdict.verdict.value}\nblockers:\n{blockers}"
    return ToolResult(
        text=text,
        tokens=approx_tokens(text),
        row_ids=(str(args["row_id_a"]), str(args["row_id_b"])),
    )


_HANDLERS = {
    "search_lines": _t_search_lines,
    "read_paper": _t_read_paper,
    "list_papers": _t_list_papers,
    "query_rows": _t_query_rows,
    "get_row": _t_get_row,
    "paper_conditions": _t_paper_conditions,
    "compare_rows": _t_compare_rows,
}


# -- driving an agentic cell ------------------------------------------------------------------- ---

_CALL = re.compile(r"^\s*CALL\s+(\w+)\s*(\{.*\})?\s*$", re.MULTILINE)


def parse_calls(text: str) -> tuple[ToolCall, ...]:
    """Pull `CALL name {json}` lines out of whatever the agent wrote. Deterministic."""
    out: list[ToolCall] = []
    for name, payload in _CALL.findall(text):
        try:
            args = json.loads(payload) if payload else {}
        except json.JSONDecodeError:
            continue
        if isinstance(args, dict):
            out.append(ToolCall(name, args))
    return tuple(out)


@dataclass
class Transcript:
    """What an agentic cell actually did, so its cost can be counted without a model."""

    cell: str
    qid: str
    initial_tokens: int
    calls: list[ToolCall] = field(default_factory=list)
    results: list[ToolResult] = field(default_factory=list)

    def record(self, call: ToolCall, result: ToolResult) -> ToolResult:
        self.calls.append(call)
        self.results.append(result)
        return result

    @property
    def retrieval_calls(self) -> int:
        return len(self.calls)

    @property
    def tokens_delivered(self) -> int:
        return self.initial_tokens + sum(result.tokens for result in self.results)

    @property
    def line_ids(self) -> tuple[str, ...]:
        return tuple(x for result in self.results for x in result.line_ids)

    @property
    def row_ids(self) -> tuple[str, ...]:
        return tuple(x for result in self.results for x in result.row_ids)


def start(session: Session) -> Transcript:
    return Transcript(cell=session.cell, qid=session.qid, initial_tokens=session.tokens)
