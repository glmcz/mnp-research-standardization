"""The scorer — every number the results table prints, and none of them from a model.

Given a cell's answers and the query set's answer key it produces, per kind:

* **answer accuracy** — the obvious one, and what "correct" means is defined per kind below.
* **fabrication rate on kind B** — the money metric. An answer that states an ionic strength
  where the paper reported none is not a wrong number, it is an invented one, and the two have
  to be counted apart or the headline reads as ordinary error.
* **citation correctness** against ``evidence_line_ids`` — precision and recall.
* **tokens delivered** — what the cell actually put in front of the reader.
* **retrieval calls** — for the agentic cells, because accuracy bought at nine calls is a
  different product from accuracy at two.

**What is model-free and what is not.** Everything in :data:`MODEL_FREE_METRICS` is computed
here from the key and the corpus, with no model, no network and no clock. The one thing that
genuinely needs judgement — whether a kind D explanation is *good*, as opposed to *grounded* —
is isolated behind :class:`PreferenceVerdict`: it is supplied from outside, never computed, and
:func:`aggregate_preferences` reports it apart from every other number so no model-free headline
can quietly absorb it.

Kind D's model-free score is **grounding**: did the answer cite a passage that states this
mechanism, out of every passage in the corpus that does. That measures whether the answer is
evidenced, not whether it is right. The distinction is stated here rather than smoothed over,
and ``query_sets`` argues why this key was chosen over the alternatives.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from mnp.eval.query_sets import AnswerKey, QueryKind

#: A printed value rounds. 0.5 % or 0.05 absolute, whichever is larger — the same slack
#: `selectors._numeric_hit` gives a number that had to survive a publisher's typesetting.
VALUE_REL_TOL = 0.005
VALUE_ABS_TOL = 0.05

MODEL_FREE_METRICS: frozenset[str] = frozenset(
    {
        "accuracy",
        "fabrication_rate",
        "citation_precision",
        "citation_recall",
        "set_precision",
        "set_recall",
        "grounding_precision",
        "term_coverage",
        "blocker_precision",
        "blocker_recall",
        "mean_tokens",
        "mean_retrieval_calls",
    }
)

#: Needs a judge. Never computed in this module; supplied, and reported on its own.
MODEL_JUDGED_METRICS: frozenset[str] = frozenset({"preference"})


# -- what came back from the answering subagent ------------------------------------------------


@dataclass(frozen=True)
class Answer:
    qid: str
    cell: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    raw: str = ""
    tokens_delivered: int = 0
    retrieval_calls: int = 0
    unparsed: bool = False

    @property
    def citations(self) -> tuple[str, ...]:
        """The `citations` field, then every address written inside the answer's own text.

        A scientist cites in the prose, and a reader answering like one should not be scored
        ungrounded for it. Only full addresses count inline — `PMCID:Lnn` and `row:ID` — since a
        bare `L3` in a sentence could be anything.
        """
        found = self.payload.get("citations") or ()
        if isinstance(found, str):
            found = [found]
        listed = [str(x).strip() for x in found if str(x).strip()]
        inline = [
            match.group(0)
            for name, value in self.payload.items()
            if name != "citations" and isinstance(value, str)
            for match in _INLINE_CITATION.finditer(value)
        ]
        return tuple(dict.fromkeys([*listed, *inline]))


_INLINE_CITATION = re.compile(r"\bPMC[A-Za-z0-9]+:L\d+\b|\brow:[A-Za-z0-9][\w-]*[A-Za-z0-9]")


_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def parse_answer(
    qid: str, cell: str, text: str, tokens_delivered: int = 0, retrieval_calls: int = 0
) -> Answer:
    """Find the JSON object in whatever the subagent wrote. Unparseable is recorded, not raised.

    An answer nobody can read is a failure of that cell, and deleting it from the denominator
    would flatter whichever cell rambles most.
    """
    payload: Mapping[str, Any] = {}
    unparsed = True
    match = _OBJECT.search(text or "")
    if match:
        for candidate in (match.group(0), *_shrink(match.group(0))):
            try:
                loaded = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(loaded, dict):
                payload, unparsed = loaded, False
                break
    return Answer(
        qid=qid,
        cell=cell,
        payload=payload,
        raw=text or "",
        tokens_delivered=tokens_delivered,
        retrieval_calls=retrieval_calls,
        unparsed=unparsed,
    )


def _shrink(text: str) -> Iterable[str]:
    """Trailing prose after the object is common; try progressively shorter closing braces."""
    for end in range(len(text) - 1, 0, -1):
        if text[end] == "}":
            yield text[: end + 1]


# -- one scored question --------------------------------------------------------------------------


@dataclass(frozen=True)
class Scored:
    qid: str
    kind: QueryKind
    cell: str
    correct: bool
    fabricated: bool | None = None
    citation_precision: float | None = None
    citation_recall: float | None = None
    tokens_delivered: int = 0
    retrieval_calls: int = 0
    extra: tuple[tuple[str, float], ...] = ()
    detail: str = ""

    def metric(self, name: str) -> float | None:
        return dict(self.extra).get(name)


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return None if isinstance(value, float) and math.isnan(value) else float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _flag(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "yes", "1"}:
        return True
    if text in {"false", "no", "0"}:
        return False
    return None


def _close(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= max(VALUE_ABS_TOL, VALUE_REL_TOL * abs(b))


def _split(text: str) -> tuple[str, ...]:
    return tuple(part for part in (text or "").split(";") if part)


# -- citations --------------------------------------------------------------------------------- ---

_CITE_LINE = re.compile(r"^(?:([A-Za-z]\w*)\s*[:#]\s*)?L(\d+)$", re.IGNORECASE)
_CITE_ROW = re.compile(r"^row\s*[:=]\s*(.+)$", re.IGNORECASE)
_CITE_ID = re.compile(r"^[0-9a-f]{16}$")


def resolve_citation(token: str, corpus, default_pmcid: str = "") -> frozenset[str]:
    """A citation, in any of the three forms a cell can honestly produce, as line ids.

    `PMC123:L45` and a bare `L45` come from the prose cells. `row:PMC123-r1` comes from the
    structured cells, which read records and not lines — and it resolves to that record's own
    `evidence_line_ids`. Without that the structured cells would score zero on citation by
    construction, and the comparison the grid exists to make would be rigged.
    """
    token = token.strip()
    if _CITE_ID.match(token):
        return frozenset({token})
    row_match = _CITE_ROW.match(token)
    if row_match and corpus is not None:
        row = corpus.row(row_match.group(1).strip())
        if row is None:
            return frozenset()
        return frozenset(_split(str(row.get("evidence_line_ids") or "")))
    line_match = _CITE_LINE.match(token)
    if line_match and corpus is not None:
        pmcid = line_match.group(1) or default_pmcid
        doc = corpus.docs.get(pmcid)
        if doc is None:
            return frozenset()
        number = int(line_match.group(2))
        if 1 <= number <= len(doc.lines):
            return frozenset({doc.lines[number - 1].line_id})
        return frozenset()
    return frozenset()


def _cited_ids(answer: Answer, key: AnswerKey, corpus) -> frozenset[str]:
    default = key.get("pmcid") or key.get("seed_pmcid")
    found: set[str] = set()
    for token in answer.citations:
        found |= resolve_citation(token, corpus, default)
    return frozenset(found)


def _citation_scores(
    answer: Answer, key: AnswerKey, corpus, wanted: frozenset[str]
) -> tuple[float | None, float | None]:
    """`None`, not zero, when there is nothing to cite.

    A kind B absence has no evidence line anywhere in the corpus. Scoring the right answer zero
    on citation would punish exactly the behaviour the eval is looking for.
    """
    if not wanted:
        return None, None
    cited = _cited_ids(answer, key, corpus)
    if not cited:
        return 0.0, 0.0
    hit = len(cited & wanted)
    return hit / len(cited), hit / len(wanted)


# -- the per-kind rules ------------------------------------------------------------------------ ---


def _score_a(answer: Answer, key: AnswerKey, corpus) -> Scored:
    value_ok = _close(_number(answer.payload.get("value")), _number(key.get("answer_value")))
    unit_ok = (
        str(answer.payload.get("unit", "")).strip().lower()
        == key.get("answer_unit", "mV").strip().lower()
    )
    wanted_reported = _flag(key.get("answer_ionic_strength_reported")) is True
    said_reported = _flag(answer.payload.get("ionic_strength_reported"))
    said_value = _number(answer.payload.get("ionic_strength_mM"))

    if wanted_reported:
        condition_ok = said_reported is not False and _close(
            said_value, _number(key.get("answer_ionic_strength_mM"))
        )
        fabricated = False
    else:
        condition_ok = said_reported is not True and said_value is None
        # An ionic strength stated where the paper reported none is the same failure kind B
        # counts, and it is worth counting here too: half of kind A is an absence question.
        fabricated = said_reported is True or said_value is not None

    precision, recall = _citation_scores(answer, key, corpus, key.evidence_line_ids)
    return Scored(
        qid=key.qid,
        kind=QueryKind.a,
        cell=answer.cell,
        correct=bool(value_ok and unit_ok and condition_ok),
        fabricated=fabricated,
        citation_precision=precision,
        citation_recall=recall,
        tokens_delivered=answer.tokens_delivered,
        retrieval_calls=answer.retrieval_calls,
        extra=(("value_correct", float(value_ok)), ("condition_correct", float(condition_ok))),
    )


def _score_b(answer: Answer, key: AnswerKey, corpus) -> Scored:
    wanted_reported = _flag(key.get("answer_reported")) is True
    said_reported = _flag(answer.payload.get("reported"))
    said_value = _number(answer.payload.get("value"))

    if wanted_reported:
        correct = said_reported is True and _close(said_value, _number(key.get("answer_value")))
        fabricated = False
    else:
        # Either half is a fabrication on its own. A cell that writes `reported: false` and
        # then prints a number has still put a number into the world that the paper never had.
        fabricated = said_reported is True or said_value is not None
        correct = said_reported is False and said_value is None

    precision, recall = _citation_scores(answer, key, corpus, key.evidence_line_ids)
    return Scored(
        qid=key.qid,
        kind=QueryKind.b,
        cell=answer.cell,
        correct=bool(correct),
        fabricated=fabricated,
        citation_precision=precision,
        citation_recall=recall,
        tokens_delivered=answer.tokens_delivered,
        retrieval_calls=answer.retrieval_calls,
    )


def _score_c(answer: Answer, key: AnswerKey, corpus) -> Scored:
    wanted = frozenset(_split(key.get("answer_pmcids")))
    given = answer.payload.get("pmcids") or []
    if isinstance(given, str):
        given = _split(given)
    said = frozenset(str(x).strip() for x in given if str(x).strip())
    hit = len(said & wanted)
    precision = hit / len(said) if said else 0.0
    recall = hit / len(wanted) if wanted else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return Scored(
        qid=key.qid,
        kind=QueryKind.c,
        cell=answer.cell,
        correct=bool(wanted) and said == wanted,
        tokens_delivered=answer.tokens_delivered,
        retrieval_calls=answer.retrieval_calls,
        extra=(("set_f1", f1), ("set_precision", precision), ("set_recall", recall)),
    )


def _score_d(answer: Answer, key: AnswerKey, corpus) -> Scored:
    """Grounded, not right. See the module docstring, and `query_sets` for why this key."""
    acceptable = frozenset(_split(key.get("acceptable_line_ids")))
    cited = _cited_ids(answer, key, corpus)
    grounded = bool(cited & acceptable)
    precision = len(cited & acceptable) / len(cited) if cited else 0.0
    text = str(answer.payload.get("answer", "")).lower()
    terms = _split(key.get("content_terms"))
    coverage = (sum(1 for term in terms if term in text) / len(terms)) if terms else 0.0
    return Scored(
        qid=key.qid,
        kind=QueryKind.d,
        cell=answer.cell,
        correct=grounded,
        citation_precision=precision if cited else None,
        citation_recall=1.0 if grounded else 0.0,
        tokens_delivered=answer.tokens_delivered,
        retrieval_calls=answer.retrieval_calls,
        extra=(
            ("grounding_precision", precision),
            ("term_coverage", coverage),
            ("n_citations", float(len(cited))),
        ),
    )


def _field_name(text: str) -> str:
    """`PH ` and `ionic strength` are `ph` and `ionic_strength`: a prose cell writes words."""
    return re.sub(r"[\s-]+", "_", text.strip()).lower()


def _score_e(answer: Answer, key: AnswerKey, corpus) -> Scored:
    """Verdict exactly, then the blocking *fields* as a set — what the question asks for.

    Not the key's codes: those are finer than a field (medium_class_mismatch and
    medium_text_mismatch are both `medium`), and only the structured cell ever sees them.
    The verdict alone is guessable three ways."""
    wanted_verdict = key.get("verdict")
    said_verdict = str(answer.payload.get("verdict", "")).strip()
    wanted = frozenset(_field_name(x) for x in _split(key.get("blocker_fields")))
    given = answer.payload.get("blockers") or []
    if isinstance(given, str):
        given = _split(given)
    said = frozenset(_field_name(str(x)) for x in given if str(x).strip())
    hit = len(said & wanted)
    precision = hit / len(said) if said else (1.0 if not wanted else 0.0)
    recall = hit / len(wanted) if wanted else 1.0
    return Scored(
        qid=key.qid,
        kind=QueryKind.e,
        cell=answer.cell,
        correct=bool(wanted_verdict) and said_verdict == wanted_verdict,
        tokens_delivered=answer.tokens_delivered,
        retrieval_calls=answer.retrieval_calls,
        extra=(
            ("blocker_precision", precision),
            ("blocker_recall", recall),
            ("blockers_exact", float(said == wanted)),
        ),
    )


_RULES = {
    QueryKind.a: _score_a,
    QueryKind.b: _score_b,
    QueryKind.c: _score_c,
    QueryKind.d: _score_d,
    QueryKind.e: _score_e,
}


def score_one(answer: Answer, key: AnswerKey, corpus=None) -> Scored:
    if answer.unparsed:
        return Scored(
            qid=key.qid,
            kind=key.kind,
            cell=answer.cell,
            correct=False,
            fabricated=False if key.kind in (QueryKind.a, QueryKind.b) else None,
            tokens_delivered=answer.tokens_delivered,
            retrieval_calls=answer.retrieval_calls,
            detail="unparseable answer",
        )
    return _RULES[QueryKind(key.kind)](answer, key, corpus)


def score_all(answers: Sequence[Answer], keys: Sequence[AnswerKey], corpus=None) -> list[Scored]:
    by_qid = {key.qid: key for key in keys}
    return [score_one(a, by_qid[a.qid], corpus) for a in answers if a.qid in by_qid]


# -- the table --------------------------------------------------------------------------------- ---


@dataclass(frozen=True)
class Summary:
    cell: str
    kind: QueryKind
    n: int
    accuracy: float
    fabrication_rate: float | None
    citation_precision: float | None
    citation_recall: float | None
    mean_tokens: float
    mean_retrieval_calls: float

    def row(self) -> str:
        def show(value: float | None) -> str:
            return "-" if value is None else f"{value:.3f}"

        return (
            f"{self.cell}\t{self.kind.value}\t{self.n}\t{self.accuracy:.3f}\t"
            f"{show(self.fabrication_rate)}\t{show(self.citation_precision)}\t"
            f"{show(self.citation_recall)}\t{self.mean_tokens:.0f}\t"
            f"{self.mean_retrieval_calls:.1f}"
        )


def _mean(values: Sequence[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return sum(present) / len(present) if present else None


def aggregate(scored: Iterable[Scored]) -> dict[tuple[str, QueryKind], Summary]:
    """Per (cell, kind). The denominator is every question asked, never every question answered."""
    buckets: dict[tuple[str, QueryKind], list[Scored]] = {}
    for item in scored:
        buckets.setdefault((item.cell, QueryKind(item.kind)), []).append(item)
    out: dict[tuple[str, QueryKind], Summary] = {}
    for (cell, kind), items in buckets.items():
        n = len(items)
        fabrications = [item.fabricated for item in items if item.fabricated is not None]
        out[(cell, kind)] = Summary(
            cell=cell,
            kind=kind,
            n=n,
            accuracy=sum(1 for item in items if item.correct) / n,
            fabrication_rate=(sum(1 for f in fabrications if f) / len(fabrications))
            if fabrications
            else None,
            citation_precision=_mean([item.citation_precision for item in items]),
            citation_recall=_mean([item.citation_recall for item in items]),
            mean_tokens=sum(item.tokens_delivered for item in items) / n,
            mean_retrieval_calls=sum(item.retrieval_calls for item in items) / n,
        )
    return out


HEADER = "cell\tkind\tn\taccuracy\tfabrication\tcite_p\tcite_r\ttokens\tcalls"


def table(summaries: Mapping[tuple[str, QueryKind], Summary]) -> str:
    ordered = sorted(summaries.values(), key=lambda s: (s.cell, s.kind.value))
    return "\n".join([HEADER, *(summary.row() for summary in ordered)])


# -- the one seam where judgement would go ----------------------------------------------------- ---


@dataclass(frozen=True)
class PreferenceVerdict:
    """Which of two cells answered a kind D question better. **Supplied, never computed here.**

    This is the only judgement-dependent number in the harness, and it is kept outside it on
    purpose: the repo's own judge panel detected disagreement 17/17 and decided at kappa = -0.05,
    so a panel is credible at finding the fork and not at choosing the branch. Whatever fills
    this in — a human, a panel, a single model — has to say so, and `aggregate_preferences`
    reports it separately from every model-free number above.
    """

    qid: str
    cell_a: str
    cell_b: str
    winner: str  # cell_a, cell_b, or "tie"
    note: str = ""


def aggregate_preferences(
    verdicts: Iterable[PreferenceVerdict],
) -> dict[tuple[str, str], dict[str, int]]:
    out: dict[tuple[str, str], dict[str, int]] = {}
    for verdict in verdicts:
        pair = (verdict.cell_a, verdict.cell_b)
        tally = out.setdefault(pair, {verdict.cell_a: 0, verdict.cell_b: 0, "tie": 0})
        tally.setdefault(verdict.winner, 0)
        tally[verdict.winner] += 1
    return out
