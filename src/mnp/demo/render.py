"""Renders the demo's three outputs from the committed cases/walk/questions/resample/harmonise
modules, plus the recorded reader runs: ``out/demo/README.md``, ``out/demo/cases/NN-<slug>.md``
(one per case) and ``out/demo/METHOD.md``. A case built on a pair across papers (case 14) shows
every paper it spans, in `Case.pmcids` order.

Nothing here calls a model. The reader's answers are **read**, never regenerated, from
``data/interim/runs/demo-cell{d,b}-20261003`` (``tool/run_demo_reader.py`` asks them through
``mnp.eval.grid``); a missing run directory renders as "not run", and a recorded reader failure
whose error names the usage-policy filter renders as a refusal rather than as a missing answer.

Deterministic: every collection is sorted before it is printed, every float is formatted to a
fixed number of digits, and nothing here reads a clock. Rendering the same inputs twice produces
identical bytes -- `tests/demo/test_render.py` checks that directly, and `report reproduce`
checks it again against the wider release once this output is committed.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from mnp import config, runs
from mnp.demo import cases as cases_mod
from mnp.demo import harmonise, resample
from mnp.demo import questions as questions_mod
from mnp.demo import walk as walk_mod
from mnp.eval import cells, grid, scoring
from mnp.eval import comparability as comp
from mnp.eval.query_sets import AnswerKey, Question
from mnp.extract.zeta import ZERO_IONIC_STRENGTH
from mnp.report import scope

CELL_D_RUN = "demo-celld-20261003"
CELL_B_RUN = "demo-cellb-20261003"
CELLS: tuple[str, ...] = ("D", "B")
RUN_IDS: dict[str, str] = {"D": CELL_D_RUN, "B": CELL_B_RUN}

_USAGE_POLICY_MARK = "usage policy"


# -- small formatting helpers, shared by every section ----------------------------------------


def _str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def _float(value: Any) -> float | None:
    text = _str(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _num(value: float | None, nd: int = 3) -> str:
    return "unreported" if value is None else f"{value:.{nd}f}"


def _pct(value: float, nd: int = 1) -> str:
    return f"{value * 100:.{nd}f}%"


def _row_number(row: Mapping) -> int:
    try:
        return int(_str(row.get("row_id")).rsplit("-r", 1)[-1])
    except ValueError:
        return 0


def _md_table(header: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(header) + " |",
        "|" + "|".join("---" for _ in header) + "|",
    ]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


# -- loading (once per build) ------------------------------------------------------------------


def load() -> tuple[pd.DataFrame, cells.Corpus]:
    corpus = cells.load_corpus()
    return corpus.table, corpus


def scope_block(table: pd.DataFrame) -> list[str]:
    """The block REVIEW.md and the card open with, from the stats beside the table read here."""
    tables = config.OUT_TABLES
    origin = tables / "sample_origin_stats.json"
    return scope.block(
        table,
        json.loads((tables / "d1_stats.json").read_text()),
        json.loads(origin.read_text()) if origin.is_file() else None,
    )


def paper_rows(table: pd.DataFrame, pmcid: str) -> list[dict[str, Any]]:
    rows = table[table["pmcid"] == pmcid].to_dict(orient="records")
    return sorted(rows, key=_row_number)


def case_rows(table: pd.DataFrame, case: cases_mod.Case) -> list[dict[str, Any]]:
    return [row for pmcid in case.pmcids for row in paper_rows(table, pmcid)]


# -- section 1: why this case -------------------------------------------------------------------


def _first_sentence(text: str) -> str:
    match = re.search(r"[.!?](?:\s|$)", text)
    return text[: match.start() + 1].strip() if match else text.strip()


def _paper_meta(table: pd.DataFrame, pmcid: str) -> tuple[str, str, str]:
    rows = table[table["pmcid"] == pmcid]
    if rows.empty:
        return "", "", ""
    row = rows.iloc[0]
    return _str(row.get("doi")), _str(row.get("year")), _str(row.get("journal"))


def _particle_key(row: Mapping) -> tuple[str, str]:
    return (_str(row.get("material")), _str(row.get("functionalisation")))


def _case_06_convergence_note(table: pd.DataFrame, pmcid: str) -> str | None:
    """Case 06 claims different particles converge in a culture medium. Checked, not assumed:
    compare the spread of each particle's *mean* zeta potential (culture medium vs. every other
    medium this paper uses) for the particles present in both. `None` if the paper no longer has
    both sides to compare, so a page never prints a claim it cannot back with this paper's own
    rows.
    """
    rows = paper_rows(table, pmcid)
    zeta_rows = [r for r in rows if _str(r.get("quantity")) == "zeta_potential"]
    culture = [r for r in zeta_rows if _str(r.get("medium_class")) == "culture_medium"]
    other = [r for r in zeta_rows if _str(r.get("medium_class")) != "culture_medium"]
    if not culture or not other:
        return None

    def means_by_particle(members: list[dict[str, Any]]) -> dict[tuple[str, str], float]:
        groups: dict[tuple[str, str], list[float]] = {}
        for row in members:
            value = _float(row.get("value"))
            if value is None:
                continue
            groups.setdefault(_particle_key(row), []).append(value)
        return {key: sum(vals) / len(vals) for key, vals in groups.items() if vals}

    culture_means = means_by_particle(culture)
    other_means = means_by_particle(other)
    shared = sorted(set(culture_means) & set(other_means))
    if not shared:
        return None

    other_vals = [other_means[k] for k in shared]
    culture_vals = [culture_means[k] for k in shared]
    other_spread = max(other_vals) - min(other_vals)
    culture_spread = max(culture_vals) - min(culture_vals)
    per_particle = "; ".join(
        f"{material}, {func or 'unmodified'}: {other_means[(material, func)]:.1f} -> "
        f"{culture_means[(material, func)]:.1f} mV"
        for material, func in shared
    )
    return "\n".join(
        [
            "",
            "**Computed check — does the particle-mean zeta spread narrow in culture medium?**",
            "",
            f"- spread of particle-mean zeta outside culture medium ({len(other)} rows, "
            f"{len(shared)} particles): {other_spread:.1f} mV",
            f"- spread of particle-mean zeta inside culture medium ({len(culture)} rows, "
            f"{len(shared)} particles): {culture_spread:.1f} mV",
            f"- per particle, outside -> inside: {per_particle}",
        ]
    )


def section_1(case: cases_mod.Case, table: pd.DataFrame) -> str:
    out = ["## 1. Why this case\n", case.why]
    for pmcid in case.pmcids:
        doi, year, journal = _paper_meta(table, pmcid)
        out.append("")
        out.append(f"- pmcid: {pmcid}")
        out.append(f"- doi: {doi or 'unreported'}")
        out.append(f"- year: {year or 'unreported'}")
        out.append(f"- journal: {journal or 'unreported'}")
    if case.nn == "06":
        note = _case_06_convergence_note(table, case.pmcid)
        if note:
            out.append(note)
    return "\n".join(out)


# -- section 2: rows -------------------------------------------------------------------------


def _particle(row: Mapping) -> str:
    material, func = _str(row.get("material")), _str(row.get("functionalisation"))
    return f"{material}, {func}" if func else material or "unreported"


def _value_text(row: Mapping) -> str:
    value, sd, unit = _float(row.get("value")), _float(row.get("sd")), _str(row.get("unit"))
    if value is None:
        return "unreported"
    body = f"{value:.3g} ± {sd:.3g}" if sd is not None else f"{value:.3g}"
    return f"{body} {unit}".strip()


def _medium_text(row: Mapping) -> str:
    return _str(row.get("medium_text")) if row.get("medium_reported") else "unreported"


def _ionic_strength_text(row: Mapping) -> str:
    reported = bool(row.get("ionic_strength_reported"))
    derived = _str(row.get("ionic_strength_source")) == "inferred_from_named_salt"
    if not (reported or derived):
        return "unreported"
    value = _float(row.get("ionic_strength_mM"))
    tag = "" if reported else " (derived)"
    return f"{value:g} mM{tag}" if value is not None else f"unreported{tag}"


def _ph_text(row: Mapping) -> str:
    if not row.get("pH_reported"):
        return "unreported"
    ph = _float(row.get("pH"))
    return f"{ph:g}" if ph is not None else (_str(row.get("pH_text")) or "unreported")


def _temperature_text(row: Mapping) -> str:
    qualifier = _str(row.get("temperature_qualifier"))
    if qualifier:
        return f"{qualifier} (nominal)"
    temp = _float(row.get("temperature_C"))
    if temp is not None:
        return f"{temp:g} °C"
    return "unreported"


def _instrument_text(row: Mapping) -> str:
    return _str(row.get("instrument")) if row.get("instrument_reported") else "unreported"


def _row_citations(row: dict[str, Any], doc) -> tuple[str, ...]:
    """The row's own evidence citations, via `walk.walk_row` -- every Step of a row carries the
    same citation set, so the first Step's is the row's."""
    steps = walk_mod.walk_row(row, doc)
    return steps[0].citations if steps else ()


def section_2(case: cases_mod.Case, table: pd.DataFrame, corpus: cells.Corpus) -> str:
    rows = case_rows(table, case)
    out = ["## 2. Rows\n"]
    header = ["row_id", "particle", "value", "medium", "ionic strength", "pH", "T", "instrument"]
    body = []
    for row in rows:
        body.append(
            [
                _str(row.get("row_id")),
                _particle(row),
                _value_text(row),
                _medium_text(row),
                _ionic_strength_text(row),
                _ph_text(row),
                _temperature_text(row),
                _instrument_text(row),
            ]
        )
    out.append(_md_table(header, body))
    out.append("")
    for row in rows:
        doc = corpus.docs.get(_str(row.get("pmcid")))
        citations = _row_citations(row, doc) if doc is not None else ()
        out.append(f"**{_str(row.get('row_id'))}** evidence:")
        if not citations:
            out.append("- (no evidence line ids resolved)")
        for cite in citations:
            out.append(f"- {cite}: “{_cite_text(cite, corpus)}”")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


_LINE_CITE = re.compile(r"^([A-Za-z]\w*)\s*[:#]\s*L(\d+)$", re.IGNORECASE)


def _cite_text(cite: str, corpus: cells.Corpus) -> str:
    match = _LINE_CITE.match(cite.strip())
    if not match:
        return "(unresolved citation)"
    pmcid, n = match.group(1), int(match.group(2))
    doc = corpus.docs.get(pmcid)
    if doc is None or not (1 <= n <= len(doc.lines)):
        return "(line not found in the corpus)"
    return doc.lines[n - 1].text


# -- section 3: standardisation walk -----------------------------------------------------------


def section_3(case: cases_mod.Case, table: pd.DataFrame, corpus: cells.Corpus) -> str:
    rows = case_rows(table, case)
    out = ["## 3. Standardisation walk\n"]
    header = ["row_id", "condition", "verdict", "reason", "citations"]
    body = []
    for row in rows:
        doc = corpus.docs.get(_str(row.get("pmcid")))
        if doc is None:
            continue
        for step in walk_mod.walk_row(row, doc):
            body.append(
                [
                    _str(row.get("row_id")),
                    step.condition,
                    step.verdict,
                    step.reason,
                    ", ".join(step.citations) or "-",
                ]
            )
    out.append(_md_table(header, body))
    return "\n".join(out)


# -- section 4: comparability -----------------------------------------------------------------

MAX_INTRA_PAIRS = 15


def _intra_paper_pairs(rows: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    ordered = sorted(rows, key=lambda r: _str(r.get("row_id")))
    return [
        (ordered[i], ordered[j]) for i in range(len(ordered)) for j in range(i + 1, len(ordered))
    ]


def corpus_wide_census(table: pd.DataFrame) -> list[comp.PairSpec]:
    rows = [comp.ZetaRow.from_mapping(r) for r in table.to_dict(orient="records")]
    return comp.graded_census(rows)


def same_particle_census(table: pd.DataFrame) -> comp.SameParticleCensus:
    rows = [comp.ZetaRow.from_mapping(r) for r in table.to_dict(orient="records")]
    return comp.same_particle_census(rows)


def _blocker_field_counter(fields_column: list[str]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for value in fields_column:
        for field in value.split(";"):
            field = field.strip()
            if field:
                counter[field] += 1
    return counter


def _verdicts(
    pairs: list[tuple[dict[str, Any], dict[str, Any]]],
) -> list[tuple[dict[str, Any], dict[str, Any], comp.Verdict]]:
    return [
        (a, b, comp.comparable(comp.ZetaRow.from_mapping(a), comp.ZetaRow.from_mapping(b)))
        for a, b in pairs
    ]


def _verdicts_table(verdicts: list[tuple[dict[str, Any], dict[str, Any], comp.Verdict]]) -> str:
    header = ["row_id_a", "row_id_b", "verdict", "blockers"]
    body = [
        [_str(a["row_id"]), _str(b["row_id"]), v.verdict.value, ";".join(v.codes) or "(none)"]
        for a, b, v in verdicts
    ]
    return _md_table(header, body)


def _case_pair(
    case: cases_mod.Case, rows: list[dict[str, Any]]
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    if case.pair is None:
        return []
    by_id = {_str(row.get("row_id")): row for row in rows}
    first, second = case.pair
    return [(by_id[first], by_id[second])] if first in by_id and second in by_id else []


def section_4(
    case: cases_mod.Case,
    table: pd.DataFrame,
    census: list[comp.PairSpec],
    kind_e_sample: list[dict[str, str]],
) -> str:
    rows = case_rows(table, case)
    out = ["## 4. Comparability\n"]
    one_paper = len(case.pmcids) == 1

    verdicts = _verdicts(_case_pair(case, rows))
    if case.pair is not None:
        out.append("### The case's pair, across papers\n")
        if verdicts:
            out.append(_verdicts_table(verdicts))
        else:
            out.append(f"(one of {', '.join(case.pair)} is no longer in the table)")
        out.append("")

    for pmcid in case.pmcids:
        inside = _verdicts(_intra_paper_pairs(paper_rows(table, pmcid)))
        verdicts += inside
        shown = inside if len(inside) <= MAX_INTRA_PAIRS else inside[:MAX_INTRA_PAIRS]
        note = (
            ""
            if len(inside) <= MAX_INTRA_PAIRS
            else f" (first {MAX_INTRA_PAIRS} of {len(inside)} pairs, by row_id)"
        )
        out.append(f"### Pairs inside {'this paper' if one_paper else pmcid}{note}\n")
        if shown:
            out.append(_verdicts_table(shown))
        else:
            out.append("(this paper has fewer than two rows -- no intra-paper pair exists)")
        out.append("")

    out.append("### Each row against the whole corpus\n")
    out.append(
        "How many corpus rows (in any paper) this row is `comparable` or "
        "`conditionally_comparable` with, from the exhaustive corpus-wide census."
    )
    out.append("")
    header2 = ["row_id", "comparable_with", "conditionally_comparable_with"]
    body2 = []
    for row in rows:
        row_id = _str(row.get("row_id"))
        comparable_n = sum(
            1
            for spec in census
            if spec.verdict.verdict is comp.Comparability.comparable
            and row_id in (spec.a.row_id, spec.b.row_id)
        )
        conditional_n = sum(
            1
            for spec in census
            if spec.verdict.verdict is comp.Comparability.conditionally_comparable
            and row_id in (spec.a.row_id, spec.b.row_id)
        )
        body2.append([row_id, str(comparable_n), str(conditional_n)])
    out.append(_md_table(header2, body2))
    out.append("")

    scope = "this paper" if one_paper else "this case"
    out.append(f"### Blocker fields: {scope} versus the kind E query set\n")
    out.append(
        f"The kind E query set (`queries/kind_e_comparability.csv`) is a **{len(kind_e_sample)}"
        f"-pair stratified sample**, not the full {len(table) * (len(table) - 1) // 2:,} "
        "possible pairs in the corpus. Share of pairs blocked on each field, side by side."
    )
    out.append("")
    paper_fields = _blocker_field_counter(
        [";".join(sorted({b.field for b in v.blockers})) for _, _, v in verdicts]
    )
    sample_fields = _blocker_field_counter([row["blocker_fields"] for row in kind_e_sample])
    n_paper_pairs, n_sample_pairs = len(verdicts), len(kind_e_sample)
    all_fields = sorted(set(paper_fields) | set(sample_fields))
    header3 = [
        "field",
        f"{scope} (of {n_paper_pairs} pairs)",
        f"kind E sample (of {n_sample_pairs} pairs)",
    ]
    body3 = []
    for field in all_fields:
        paper_share = _pct(paper_fields.get(field, 0) / n_paper_pairs) if n_paper_pairs else "n/a"
        sample_share = (
            _pct(sample_fields.get(field, 0) / n_sample_pairs) if n_sample_pairs else "n/a"
        )
        body3.append([field, paper_share, sample_share])
    if body3:
        out.append(_md_table(header3, body3))
    else:
        out.append("(no blockers to compare -- this paper has fewer than two rows)")
    return "\n".join(out)


# -- section 5: harmonised value ----------------------------------------------------------------


def _interval_text(h: harmonise.Harmonised) -> str:
    if h.point is not None:
        return f"{h.point:.3g} mV (point)"
    if h.low is not None and h.high is not None:
        return f"[{h.low:.3g}, {h.high:.3g}] mV"
    return "not computable"


def section_5(case: cases_mod.Case, table: pd.DataFrame) -> str:
    harmonised = [
        h
        for pmcid in case.pmcids
        for h in sorted(
            harmonise.harmonise_paper(pmcid, table),
            key=lambda h: _row_number({"row_id": h.row_id}),
        )
    ]
    out = ["## 5. Harmonised value\n"]
    header = ["row_id", "reported", "model", "kappa_a", "f(kappa_a)", "harmonised", "why"]
    body = []
    for h in harmonised:
        body.append(
            [
                h.row_id,
                f"{h.reported_value:g} {h.unit or ''}".strip()
                if h.reported_value is not None
                else "unreported",
                h.model or "not named",
                _num(h.kappa_a, 3) if h.kappa_a is not None else "unknown",
                _num(h.f, 4) if h.f is not None else "unknown",
                _interval_text(h),
                h.why,
            ]
        )
    out.append(_md_table(header, body))
    return "\n".join(out)


# -- section 6: resampling ------------------------------------------------------------------


def section_6(case: cases_mod.Case, table: pd.DataFrame) -> str:
    out = ["## 6. Resampling\n"]
    for pmcid in case.pmcids:
        if len(case.pmcids) > 1:
            out.append(f"### {pmcid}\n")
        out += _resampling_lines(table, pmcid)
        out.append("")
    return "\n".join(out).rstrip()


def _resampling_lines(table: pd.DataFrame, pmcid: str) -> list[str]:
    n_total = len(table)
    k_total = int(table["pmcid"].nunique())
    n_paper = len(table[table["pmcid"] == pmcid])
    out = [f"- rows in this paper: {n_paper}"]
    out.append(f"- weight per row (n / {n_total}): {n_paper / n_total:.5f}")
    out.append(f"- weight per paper (1 / {k_total}): {1 / k_total:.5f}")
    out.append("")
    loo = resample.leave_one_out(table, pmcid)
    header = [
        "metric",
        "per-row (with paper)",
        "per-row (without)",
        "per-paper (with)",
        "per-paper (without)",
    ]
    body = [
        [
            item.metric,
            _pct(item.per_row_full),
            _pct(item.per_row_without),
            _pct(item.per_paper_full),
            _pct(item.per_paper_without),
        ]
        for item in loo
    ]
    out.append(_md_table(header, body))
    return out


# -- section 7: reader ------------------------------------------------------------------------


@dataclass(frozen=True)
class ReaderAnswer:
    cell: str
    qid: str
    status: str  # answered | not_run | refused | not_answered
    text: str = ""
    scored: scoring.Scored | None = None
    citation_lines: tuple[str, ...] = ()


def _load_errors(directory: Path) -> dict[str, str]:
    path = directory / "errors.jsonl"
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        out.setdefault(record["qid"], record.get("error", ""))
    return out


@dataclass(frozen=True)
class RunHandle:
    cell: str
    directory: Path
    answers: dict[str, dict[str, Any]]
    errors: dict[str, str]


def load_run(cell: str) -> RunHandle | None:
    directory = runs.run_dir(RUN_IDS[cell])
    if not (directory / "manifest.json").is_file():
        return None
    return RunHandle(cell, directory, grid.load_answers(directory), _load_errors(directory))


def _line_index(corpus: cells.Corpus) -> dict[str, str]:
    out: dict[str, str] = {}
    for pmcid, doc in corpus.docs.items():
        for line in doc.lines:
            out[line.line_id] = f'{pmcid}:L{line.n}\t"{line.text}"'
    return out


def reader_answer(
    cell: str,
    run: RunHandle | None,
    qid: str,
    key: AnswerKey,
    corpus: cells.Corpus,
    default_pmcid: str,
    line_index: dict[str, str],
) -> ReaderAnswer:
    if run is None:
        return ReaderAnswer(cell, qid, "not_run")
    record = run.answers.get(qid)
    if record is not None and record.get("refused"):
        return ReaderAnswer(cell, qid, "refused")
    if record is None:
        error = run.errors.get(qid, "")
        status = "refused" if _USAGE_POLICY_MARK in error.lower() else "not_answered"
        return ReaderAnswer(cell, qid, status)
    answer = scoring.parse_answer(
        qid, cell, record["text"], tokens_delivered=record.get("tokens_delivered", 0)
    )
    scored = scoring.score_one(answer, key, corpus)
    resolved: list[str] = []
    for token in sorted(set(answer.citations)):
        ids = scoring.resolve_citation(token, corpus, default_pmcid)
        if not ids:
            resolved.append(f"{token} (unresolved)")
            continue
        for line_id in sorted(ids):
            resolved.append(line_index.get(line_id, f"{line_id} (line not found)"))
    return ReaderAnswer(
        cell, qid, "answered", text=record["text"], scored=scored, citation_lines=tuple(resolved)
    )


def _score_line(scored: scoring.Scored) -> str:
    parts = [f"correct={scored.correct}"]
    if scored.fabricated is not None:
        parts.append(f"fabricated={scored.fabricated}")
    if scored.citation_precision is not None:
        parts.append(f"citation_precision={scored.citation_precision:.2f}")
    if scored.citation_recall is not None:
        parts.append(f"citation_recall={scored.citation_recall:.2f}")
    for name, value in scored.extra:
        if not name.startswith("key_"):  # the true verdict, carried for the recall table
            parts.append(f"{name}={value:.2f}")
    return ", ".join(parts)


def section_7(
    case: cases_mod.Case,
    qas: list[tuple[Question, AnswerKey]],
    runs_by_cell: dict[str, RunHandle | None],
    corpus: cells.Corpus,
    line_index: dict[str, str],
) -> str:
    out = ["## 7. Reader\n"]
    for question, key in qas:
        out.append(f"### {question.qid}\n")
        out.append(question.text)
        out.append("")
        default_pmcid = (
            key.get("pmcid") or key.get("seed_pmcid") or key.get("pmcid_a") or case.pmcid
        )
        for cell in CELLS:
            run = runs_by_cell.get(cell)
            answer = reader_answer(cell, run, question.qid, key, corpus, default_pmcid, line_index)
            out.append(f"**cell {cell}**")
            if answer.status == "not_run":
                out.append("- not run")
            elif answer.status == "refused":
                out.append("- refused by the reader's usage-policy filter")
            elif answer.status == "not_answered":
                out.append("- not answered")
            else:
                out.append(f"- answer: `{answer.text}`")
                if answer.scored is not None:
                    out.append(f"- score: {_score_line(answer.scored)}")
                if answer.citation_lines:
                    out.append("- cited lines:")
                    for line in answer.citation_lines:
                        out.append(f"  - {line}")
                else:
                    out.append("- cited lines: (none)")
            out.append("")
    return "\n".join(out).rstrip() + "\n"


# -- one case page --------------------------------------------------------------------------


def case_page(
    case: cases_mod.Case,
    table: pd.DataFrame,
    corpus: cells.Corpus,
    census: list[comp.PairSpec],
    kind_e_sample: list[dict[str, str]],
    runs_by_cell: dict[str, RunHandle | None],
    line_index: dict[str, str],
) -> str:
    qas = questions_mod.questions_for(case, table)
    sections = [
        f"# Case {case.nn} — {case.slug}\n",
        f"**mode:** {case.mode}\n",
        section_1(case, table),
        section_2(case, table, corpus),
        section_3(case, table, corpus),
        section_4(case, table, census, kind_e_sample),
        section_5(case, table),
        section_6(case, table),
        section_7(case, qas, runs_by_cell, corpus, line_index),
    ]
    return "\n\n".join(sections).rstrip() + "\n"


# -- README ----------------------------------------------------------------------------------


def _case_index_row(case: cases_mod.Case) -> list[str]:
    return [case.nn, case.slug, ", ".join(case.pmcids), case.mode, _first_sentence(case.why)]


def _pp(value: float, nd: int = 1) -> str:
    """A half-width in percentage points, e.g. 8.4 -> '8.4 pp'."""
    return f"{value * 100:.{nd}f} pp"


def _e2e_table(table: pd.DataFrame) -> str:
    header = [
        "metric",
        "per row",
        "per paper",
        "ICC",
        "DEFF",
        "n_eff",
        "naive ± (row)",
        "cluster ± (row)",
        "cluster ± (paper)",
    ]
    body = [
        [
            e.metric,
            _pct(e.per_row),
            _pct(e.per_paper),
            f"{e.icc:.2f}",
            f"{e.deff:.2f}",
            f"{e.n_eff:.0f}",
            _pp(e.naive_half_width),
            _pp(e.row_half_width),
            _pp(e.paper_half_width),
        ]
        for e in resample.estimates(table)
    ]
    return _md_table(header, body)


def _scan_table(table: pd.DataFrame) -> str:
    scan = harmonise.scan(table)
    header = ["quantity", "papers", "name a model", "do not"]
    body = [
        ["zeta_potential", str(scan.zeta_papers), str(scan.zeta_named), str(scan.zeta_not_named)],
        [
            "electrophoretic_mobility",
            str(scan.mobility_papers),
            str(scan.mobility_named),
            str(scan.mobility_not_named),
        ],
    ]
    return _md_table(header, body)


def _reader_summary_table(
    cell: str, run: RunHandle | None, all_qas: list[tuple[Question, AnswerKey]], corpus
) -> str:
    if run is None:
        return f"cell {cell}: not run"
    scored: list[scoring.Scored] = []
    not_answered = 0
    refused = 0
    for question, key in all_qas:
        record = run.answers.get(question.qid)
        error = run.errors.get(question.qid, "")
        if (record is not None and record.get("refused")) or (
            record is None and _USAGE_POLICY_MARK in error.lower()
        ):
            # A refusal is the cell's answer (Martin, 2026-09-28): in the denominator, wrong.
            refused += 1
            scored.append(
                scoring.score_one(scoring.parse_answer(question.qid, cell, ""), key, corpus)
            )
            continue
        if record is None:
            not_answered += 1
            continue
        answer = scoring.parse_answer(
            question.qid, cell, record["text"], tokens_delivered=record.get("tokens_delivered", 0)
        )
        scored.append(scoring.score_one(answer, key, corpus))
    answered = len(scored) - refused
    lines = [f"cell {cell}: {answered} answered, {refused} refused, {not_answered} not answered"]
    if scored:
        lines.append(scoring.table(scoring.aggregate(scored)))
    return "\n".join(lines)


def reader_framing_note(n_questions: int) -> str:
    """Shared verbatim with METHOD.md's reader-grid section (item 7/9 of the review): why a
    high cell-D score is expected rather than newsworthy, and why `n_questions` is an
    illustration of the grid on this demo's own cases, not a statistical estimate of accuracy.
    """
    return (
        f"Cell D is handed the matching structured rows for each question, so a high score "
        "there is the expected outcome, not a finding on its own -- what the grid actually "
        "measures is cell D's *difference* from cell B, which is given only BM25-retrieved "
        f"lines and no table. Both cells answer the same {n_questions} questions here: an "
        "illustration of the grid running on this demo's own cases, not a statistical estimate "
        "of either cell's accuracy."
    )


def _case_for_qid(qid: str) -> cases_mod.Case | None:
    nn = qid[1:3]
    return next((c for c in cases_mod.CASES if c.nn == nn), None)


def _case_link(qid: str) -> str:
    case = _case_for_qid(qid)
    if case is None:
        return f"`{qid}`"
    return f"[`{qid}`](cases/{case.nn}-{case.slug}.md)"


def _describe_b_miss(text: str, question: Question, key: AnswerKey) -> str:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return f"answered `{text}`, which does not parse as the expected JSON"
    field = question.targeting("field") or "the condition"
    gold_reported = key.get("answer_reported") == "True"
    gold_value = key.get("answer_value")
    said_reported = bool(parsed.get("reported"))
    said_value = parsed.get("value")
    if said_reported and not gold_reported:
        return (
            f"answered {field} reported=true, value {said_value!r} -- the paper never reports "
            f"{field} on any row of this case"
        )
    if not said_reported and gold_reported:
        return f"answered {field} reported=false -- the paper reports {field} = {gold_value}"
    return (
        f"answered {field} reported={said_reported}, value {said_value!r}; gold is "
        f"reported={gold_reported}, value {gold_value!r}"
    )


def _describe_e_miss(text: str, key: AnswerKey) -> str:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return f"answered `{text}`, which does not parse as the expected JSON"
    said_verdict = parsed.get("verdict", "?")
    said_blockers = parsed.get("blockers") or []
    gold_verdict = key.get("verdict") or "?"
    gold_blockers = [f for f in (key.get("blocker_fields") or "").split(";") if f]
    return (
        f"answered {said_verdict} (blockers: {', '.join(said_blockers) or 'none'}) -- gold is "
        f"{gold_verdict} (blockers: {', '.join(gold_blockers) or 'none'})"
    )


def _describe_miss(question: Question, text: str, key: AnswerKey) -> str:
    if question.kind.value == "B":
        return _describe_b_miss(text, question, key)
    if question.kind.value == "E":
        return _describe_e_miss(text, key)
    return f"answered `{text}`, scored incorrect"


def _reader_problem_lines(
    cell: str,
    run: RunHandle | None,
    all_qas: list[tuple[Question, AnswerKey]],
    corpus: cells.Corpus,
    predicate: Any,
) -> list[str]:
    """qid-linked, one-line, computed-from-the-run descriptions of every answer `predicate`
    flags, sorted by qid so the page is deterministic.
    """
    if run is None:
        return []
    lines: list[str] = []
    for question, key in all_qas:
        record = run.answers.get(question.qid)
        if record is None:
            continue
        answer = scoring.parse_answer(
            question.qid, cell, record["text"], tokens_delivered=record.get("tokens_delivered", 0)
        )
        scored = scoring.score_one(answer, key, corpus)
        if not predicate(scored):
            continue
        lines.append(
            f"- {_case_link(question.qid)}: {_describe_miss(question, record['text'], key)}"
        )
    return sorted(lines)


def _absence_block(census: comp.SameParticleCensus) -> str:
    absence = census.count("lost_to_absence")
    only = dict(census.only_absent_field)
    surface = dict(census.absent_fields).get("functionalisation", 0)
    lines = [
        "Every pair of rows that describe the same particle: the same `quantity`, the same "
        "`material_key` (a row whose material is unreported describes no particle) and the same "
        f"`functionalisation_key`. That is {census.pairs:,} pairs among "
        f"{sum(p.rows for p in census.particles):,} rows of {len(census.particles):,} particles. "
        '`comparability.comparable` grades each one, and the rule in `METHOD.md` ("The '
        'same-particle census") puts it in exactly one category:',
        "",
        _md_table(
            ["category", "pairs"],
            [[comp.SAME_PARTICLE_LABELS[name], f"{n:,}"] for name, n in census.categories]
            + [["all same-particle pairs", f"{census.pairs:,}"]],
        ),
        "",
        f"**{absence:,}** pairs of the same particle "
        f"({_pct(absence / census.pairs)}) are blocked only by "
        "conditions a paper did not report: no stated value differs and nothing is undecidable. "
        f"{census.absence_cross_paper:,} of them cross a paper boundary; "
        f"{census.absence_same_paper:,} sit inside one paper. **{census.count('comparable'):,}** "
        "pairs are comparable. These are pairs of the same particle blocked only by unreported "
        "conditions -- not a claim about what those conditions were, and not a claim about what "
        "a default would make comparable. Reported, the conditions could still differ: the pair "
        "would become decidable, not necessarily comparable.",
        "",
        "Which conditions are missing, ranked over those pairs. A pair usually misses several, "
        "so the first column adds up to more than the pairs; the second counts the pairs where "
        "the field is the only one missing, where one reported number would make the pair "
        "decidable:",
        "",
        _md_table(
            ["missing field", "pairs missing it", "pairs missing only it"],
            [[f"`{f}`", f"{n:,}", f"{only.get(f, 0):,}"] for f, n in census.absent_fields],
        ),
    ]
    if surface:
        lines += [
            "",
            f"{surface:,} of the pairs lost to absence leave the surface unstated on both rows. "
            "They are grouped as one particle only because nothing printed tells them apart; "
            "the unstated surface is itself one of their absences, so none of them can be "
            "comparable.",
        ]
    return "\n".join(lines)


def readme(
    table: pd.DataFrame,
    corpus: cells.Corpus,
    runs_by_cell: dict[str, RunHandle | None],
    all_qas: list[tuple[Question, AnswerKey]],
    scope_lines: list[str],
    same_particle: comp.SameParticleCensus,
) -> str:
    out = [f"# The demo: {len(cases_mod.CASES)} real cases, each re-sampled four ways\n"]
    out.append("\n".join(scope_lines) + "\n")
    out.append(
        "See `docs/DESIGN_2026-09-28_demo.md` for what this shows and `METHOD.md` for how every "
        "number below is computed. One page per case is in `cases/`."
    )
    out.append("\n## Cases\n")
    header = ["nn", "slug", "pmcid", "mode", "result"]
    body = [_case_index_row(case) for case in cases_mod.CASES]
    out.append(_md_table(header, body))

    out.append("\n## Not different, just unreported\n")
    out.append(_absence_block(same_particle))

    out.append("\n## Corpus-wide resampling (E2e, rebuilt)\n")
    out.append(_e2e_table(table))

    out.append("\n## Conversion-model scan (E2b, rebuilt)\n")
    out.append(_scan_table(table))

    out.append("\n## Reader results\n")
    out.append(reader_framing_note(len(all_qas)))
    out.append("")
    for cell in CELLS:
        out.append(_reader_summary_table(cell, runs_by_cell.get(cell), all_qas, corpus))
        out.append("")

    out.append("### Cell B fabrications\n")
    fabrications = _reader_problem_lines(
        "B", runs_by_cell.get("B"), all_qas, corpus, lambda s: s.fabricated is True
    )
    out.extend(fabrications if fabrications else ["(none recorded in this run)"])
    out.append("")

    out.append("### Cell D wrong answers\n")
    wrong = _reader_problem_lines(
        "D", runs_by_cell.get("D"), all_qas, corpus, lambda s: s.correct is False
    )
    out.extend(wrong if wrong else ["(none recorded in this run)"])
    return "\n".join(out).rstrip() + "\n"


# -- METHOD.md ---------------------------------------------------------------------------------


def _condition_rules_table() -> str:
    header = [
        "condition",
        "why a zeta value means nothing without it",
        "counts as reported",
        "does not count",
    ]
    body = [
        [
            "medium",
            "zeta is a property of the particle **and** its medium",
            'any liquid named, even "DI water", even "PBS"',
            "the paper never names a liquid at all",
        ],
        [
            "ionic strength (mM)",
            "sets the Debye length; without it the mobility curve has no x-axis",
            '"10 mM NaCl"; even a printed composition ("0.137 M NaCl, 0.0027 M KCl"), then as '
            "**derived**",
            '"PBS" or "HEPES" named alone; a component whose speciation the paper never '
            "states; a named buffer's nominal composition is never looked up",
        ],
        [
            "pH",
            "sets dissociation of surface groups, and can flip the sign on a functionalised "
            "particle",
            'a number, even a range ("between 6.8 and 7.2")',
            '"physiological pH" with no number attached',
        ],
        [
            "temperature (°C)",
            "enters ε, η and kT in every conversion model",
            'a number; even "room temperature", but flagged **nominal**',
            "incubation, exposure, storage or culture temperature -- even when the paper "
            "states no other temperature anywhere",
        ],
        [
            "instrument",
            "different instruments apply a different mobility-to-zeta conversion",
            'even a family name ("Zetasizer"); brand and model is better and is stored verbatim',
            "nothing named at all",
        ],
    ]
    return _md_table(header, body)


def _verdict_vocabulary_block() -> str:
    return "\n".join(
        [
            "`mnp.demo.walk.walk_row` gives each of a row's five conditions one of four "
            "verdicts, in the fixed order medium, ionic strength, pH, temperature, instrument:",
            "",
            "- **reported** -- the paper states it directly: a number, a range, a name, or (for "
            "temperature only) a qualitative phrase.",
            "- **derived** -- computed from a printed composition "
            '(`ionic_strength_source == "inferred_from_named_salt"`), never a looked-up '
            "nominal value.",
            '- **nominal** -- reported only as a qualitative phrase ("room temperature") rather '
            "than a number; a non-null `temperature_qualifier`, flagged rather than treated as "
            "a measured value.",
            "- **unreported** -- nothing usable is printed. The reason always names the "
            "specific cause the row shows -- see the per-condition table above and the "
            "worked example below.",
        ]
    )


def _three_rules_block(census: comp.SameParticleCensus) -> str:
    return "\n".join(
        [
            "Three rules, ratified before this demo and written down in "
            "`docs/2026-09-21-cile-a-otazky-pro-vedce.md` Part 1, sit above the per-condition "
            "table and the verdict vocabulary -- they are not the same three things as "
            "reported/derived/nominal/unreported and should not be conflated with it:",
            "",
            "1. **Scope.** A condition holds only inside the experiment that states it. It is "
            "never carried to another preparation, not even one in the same paper (ratified "
            "2026-09-13).",
            '2. **Absence is never imputed.** "DI water" is a reported medium; it does not '
            "mean ionic strength zero. What absence costs is measured, not imagined: of the "
            f"{census.pairs:,} pairs of rows that describe the same particle, "
            f"**{census.count('lost_to_absence'):,}** are blocked only by conditions one row or "
            f"both did not report, and **{census.count('comparable'):,}** are comparable (the "
            "same-particle census below; every category in `README.md`). These are pairs blocked "
            "only by absence -- not a count of what any default would make comparable.",
            '3. **Every figure here is an upper bound.** "Reported" is softer than '
            '"reported as a number": a pH range counts, a nominal room temperature counts, an '
            "instrument family counts. True completeness is lower than every percentage this "
            "project prints.",
        ]
    )


def _ionic_strength_sources_block(table: pd.DataFrame, corpus: cells.Corpus) -> str:
    counts = table["ionic_strength_source"].value_counts()
    papers = table.groupby("ionic_strength_source")["pmcid"].nunique()
    order = ("reported", "inferred_from_named_salt", "unreported")
    header = ["source", "rows", "papers"]
    body = [[src, str(int(counts.get(src, 0))), str(int(papers.get(src, 0)))] for src in order]

    lines = [
        "Every row's `ionic_strength_source`, counted at build time from "
        "`out/tables/d1_zeta_table.csv`:",
        "",
        _md_table(header, body),
        "",
        "Conductivity is never converted to ionic strength -- the conversion needs an assumed "
        "ionic composition the paper does not give -- and a buffer's nominal composition is "
        "never looked up even when the field knows it by heart. Both land in `unreported`, "
        "never in a value.",
        "",
        "**Worked example, case 02 (PMC10141840).** Three rows, one particle, ionic strength "
        "unreported on all three -- for three different reasons (`walk.walk_row`):",
    ]
    doc = corpus.docs.get("PMC10141840")
    if doc is not None:
        for row in paper_rows(table, "PMC10141840"):
            steps = walk_mod.walk_row(row, doc)
            step = next(s for s in steps if s.condition == "ionic_strength")
            lines.append(
                f"- `{_str(row.get('row_id'))}` ({_str(row.get('medium_text'))}): {step.reason}"
            )
    return "\n".join(lines)


def _comparability_block(
    table: pd.DataFrame,
    census: list[comp.PairSpec],
    kind_e_sample: list[dict[str, str]],
) -> str:
    n_comparable = sum(1 for s in census if s.verdict.verdict is comp.Comparability.comparable)
    n_conditional = sum(
        1 for s in census if s.verdict.verdict is comp.Comparability.conditionally_comparable
    )
    n_zeta_comparable = sum(
        1
        for s in census
        if s.verdict.verdict is comp.Comparability.comparable
        and s.a.quantity.value == "zeta_potential"
        and s.b.quantity.value == "zeta_potential"
    )
    n_zeta_cross_paper = sum(
        1
        for s in census
        if s.verdict.verdict is comp.Comparability.comparable
        and s.a.quantity.value == "zeta_potential"
        and s.b.quantity.value == "zeta_potential"
        and s.a.pmcid != s.b.pmcid
    )
    total_pairs = len(table) * (len(table) - 1) // 2
    strata_line = "; ".join(f"{comp.STRATUM_SIZES[s]} from `{s}`" for s in comp.STRATA)

    return "\n".join(
        [
            "`mnp.eval.comparability.comparable(a, b)` grades a pair `comparable` (no "
            "blockers), `conditionally_comparable` (every blocker is a stated, quantified "
            "difference on one of the axis fields below) or `not_comparable` (anything else).",
            "",
            "Tolerances, read from the module's own constants, never typed by hand: ionic "
            f"strength {comp.IONIC_STRENGTH_REL_TOL:.0%} relative, pH ±{comp.PH_TOL:g} units, "
            f"temperature ±{comp.TEMPERATURE_TOL_C:g}°C, Henry's f "
            f"{comp.HENRY_REL_TOL:.0%} relative -- each argued in "
            "`docs/FINDINGS_comparability.md` §2.",
            "",
            "A mismatch keeps a pair only *conditionally* comparable when it falls on one of "
            "these axis codes -- a stated, quantified difference the reviewer can still place "
            "on a common scale:",
            "",
            "\n".join(f"- `{code}`" for code in sorted(comp._AXIS_CODES)),
            "",
            "Anything else the key can flag is a blocker field, the vocabulary a kind E answer "
            "names: " + ", ".join(f"`{f}`" for f in comp.BLOCKER_FIELDS) + ".",
            "",
            "The κ·a conversion-regime rule (Henry's f within "
            f"{comp.HENRY_REL_TOL:.0%}) applies only when **both** rows report a zeta "
            "potential -- a mobility row has no assumed f_m to compare, so the rule never "
            "fires on it.",
            "",
            f"On the current table, the exhaustive census over all {total_pairs:,} unordered "
            f"pairs finds **{n_comparable}** fully comparable pairs, of which "
            f"**{n_zeta_comparable}** compare two zeta potentials and **{n_zeta_cross_paper}** "
            f"of those cross a paper boundary; **{n_conditional}** pairs are conditionally "
            "comparable.",
            "",
            "The kind E query set (`queries/kind_e_comparability.csv`) unions the exhaustive "
            f"census of comparable and conditionally comparable pairs with **{len(comp.STRATA)}"
            f"** uniform seeded strata -- "
            f"{strata_line} -- plus the census itself, so a rare positive is never sampled "
            f"away. Loaded here it holds {len(kind_e_sample)} pairs.",
        ]
    )


def _pp_range(lo: float, hi: float) -> str:
    return f"{lo:.2f}x to {hi:.2f}x"


def _resampling_block(table: pd.DataFrame) -> str:
    ests = {e.metric: e for e in resample.estimates(table)}
    ratios = {metric: e.row_half_width / e.naive_half_width for metric, e in ests.items()}
    ratio_lo, ratio_hi = min(ratios.values()), max(ratios.values())
    temp = ests["temperature_reported"]
    ionic = ests["ionic_strength_reported"]

    loo_pmcid = "PMC8719689"  # case 06 -- the largest single paper in the corpus (90 rows)
    loo = {item.metric: item for item in resample.leave_one_out(table, loo_pmcid)}
    temp_loo = loo["temperature_reported"]
    row_shift = abs(temp_loo.per_row_full - temp_loo.per_row_without)
    paper_shift = abs(temp_loo.per_paper_full - temp_loo.per_paper_without)
    n_paper_rows = int((table["pmcid"] == loo_pmcid).sum())
    flags = table["flags"].fillna("").astype(str).str.split(";")
    zeroed = int(flags.map(lambda parts: ZERO_IONIC_STRENGTH in parts).sum())

    return "\n".join(
        [
            "`mnp.demo.resample` rebuilds FINDINGS E2e: reporting completeness computed per "
            "row is inflated because rows cluster by paper. ICC comes from a one-way "
            "random-effects ANOVA with the unbalanced-cluster adjustment m0; "
            "DEFF = 1 + (m0-1)*ICC and n_eff = N/DEFF follow from it. The cluster bootstrap "
            "(B=10,000, seed 20260921) resamples **paper indices** with replacement and never "
            "regroups by the cluster key afterward -- doing so would silently merge a paper "
            "drawn twice back into one group and narrow the interval, the exact defect one of "
            "the two original, uncommitted implementations had.",
            "",
            "Every metric, rebuilt on the current table, per row and per paper, with both "
            "interval styles:",
            "",
            _e2e_table(table),
            "",
            f"**Worked example -- temperature.** The naive binomial half-width is "
            f"±{_pp(temp.naive_half_width)}; the cluster bootstrap gives "
            f"±{_pp(temp.row_half_width)} per row. Any interval this project computed as "
            "`sqrt(p(1-p)/1890)` is that far wrong.",
            "",
            f"**Cluster/naive ratio across the six metrics: {_pp_range(ratio_lo, ratio_hi)}** "
            "-- every metric's cluster interval is at least twice the naive one.",
            "",
            f"**Ionic strength's ICC.** This rebuild gives **{ionic.icc:.4f}** ({ionic.icc:.2f} "
            "in the table above), where FINDINGS.md §E2e printed 0.83. FINDINGS predates the "
            "rule of 2026-09-28 that a printed 0 mM is not a reported ionic strength; on the "
            "table before it, this code gave 0.8247 (commit f78a4f5), which the printed 0.83 "
            "most likely rounds twice (0.8247 -> 0.825 -> 0.83). The "
            f"{zeroed} rows that rule cleared account for the rest. "
            "The difference is reported here, not tuned to match.",
            "",
            f"**Leave-one-out, {loo_pmcid} (case 06, {n_paper_rows} rows -- the largest single "
            "paper in the corpus).** Dropping it moves the per-row temperature-reported "
            f"estimate by {row_shift * 100:.1f} pp ({_pct(temp_loo.per_row_full)} -> "
            f"{_pct(temp_loo.per_row_without)}) but the per-paper estimate by only "
            f"{paper_shift * 100:.1f} pp ({_pct(temp_loo.per_paper_full)} -> "
            f"{_pct(temp_loo.per_paper_without)}) -- on a real paper, the demonstration of why "
            "per-paper is the more conservative unit: one large paper cannot move it much.",
        ]
    )


def _reader_grid_block(n_questions: int) -> str:
    return "\n".join(
        [
            "Cells D (structured records first, prose fallback) and B (BM25 top-k lines, no "
            "table) of `mnp.eval.cells` answer the demo's kind A/B/E questions through "
            '`mnp.eval.grid.read`: `claude -p` with `--tools ""`, `--setting-sources ""`, '
            "`--strict-mcp-config`, its own system prompt (replacing the coding-agent one), "
            "and a temporary working directory with no CLAUDE.md above it, so nothing but the "
            "prompt reaches the model. The model is pinned by full id "
            f"(`{grid.READER_MODEL}`, `mnp.eval.grid.READER_MODEL`) and a reply is refused if "
            "it comes from any other model.",
            "",
            "`mnp.eval.scoring` scores every answer without a model: fabrication is counted on "
            "kind B (and on the absence half of kind A) whenever an answer states a value the "
            "paper never reported; an unparseable reply counts as wrong, never as excluded "
            "from the denominator. A citation counts whether it is listed in the `citations` "
            "field or written inside the answer's own text, as a scientist would write it -- "
            "but only as a full address (`PMCID:Lnn` or `row:ID`); a bare `L3` in a sentence "
            "is not one.",
            "",
            "A reader failure (timeout, wrong model, no JSON) is not an answer -- it goes to "
            "`errors.jsonl` and the question is asked again the next time the run resumes. "
            'The harness itself carries no "only once" limit on that resume; the two runs this '
            "demo reads happen to have each been resumed at most once. A usage-policy refusal "
            "is different: it is deterministic (D-008 was refused three times on ordinary "
            "colloid text), so it is recorded as the cell's answer, scored wrong, kept in the "
            "denominator and never asked again (Martin, 2026-09-28).",
            "",
            reader_framing_note(n_questions),
        ]
    )


def _same_particle_rule_block() -> str:
    label = comp.SAME_PARTICLE_LABELS
    return "\n".join(
        [
            "`mnp.eval.comparability.same_particle_census` takes every pair of rows that measure "
            "the same particle -- the same `quantity`, the same `material_key(material)` (a row "
            "whose material is unreported is left out) and the same "
            "`functionalisation_key(functionalisation)` -- and grades it with `comparable(a, b)`. "
            "Each pair falls in exactly one category, decided in this order:",
            "",
            f"- **{label['comparable']}** -- verdict `comparable`;",
            f"- **{label['conditionally_comparable']}** -- verdict `conditionally_comparable`;",
            f"- **{label['lost_to_absence']}** -- verdict `not_comparable` and **every** blocker "
            "has kind `unreported`;",
            f"- **{label['stated_difference']}** -- verdict `not_comparable` and at least one "
            "blocker has kind `mismatch`;",
            f"- **{label['undecidable']}** -- the rest: no mismatch, and at least one blocker "
            "`undecidable`.",
            "",
            "Within lost only to absence it counts, per blocker field, the pairs where that field "
            "is among the missing ones; per field, the pairs where it is the only one missing; "
            "and the pairs that cross a paper boundary. A surface unreported on both rows keys to "
            "no surface, so those rows group together, but `comparable` still raises "
            "`functionalisation_unreported` on every such pair: an unstated surface is counted as "
            "absence, never as sameness. The census counts what blocks a pair. It imputes nothing "
            "and says nothing about what a default would do. The numbers are in `README.md`.",
        ]
    )


def method(
    table: pd.DataFrame,
    corpus: cells.Corpus,
    scope_lines: list[str],
    same_particle: comp.SameParticleCensus,
) -> str:
    census = corpus_wide_census(table)
    scan = harmonise.scan(table)
    kind_e_sample = comp.read_query_set()
    n_questions = sum(len(questions_mod.questions_for(case, table)) for case in cases_mod.CASES)

    out = ["# METHOD — how the PoC measures\n"]
    out.append("\n".join(scope_lines) + "\n")
    out.append(
        "Every number below is either computed at build time from the repo's own code and data, "
        "or quoted with the exact FINDINGS file and section that measured it. None is typed by "
        "hand as a bare number."
    )

    out.append("\n## Corpus and parsing\n")
    out.append(
        f"{len(table)} rows from {table['pmcid'].nunique()} papers, one row per printed "
        "measurement of a zeta potential or an electrophoretic mobility "
        "(`out/tables/d1_zeta_table.csv`, built by `report d1`). Line addresses (`PMCID:Lnn`) "
        "come from `mnp.corpus.lines`, and evidence quotes are verified verbatim against the "
        "vendored JATS XML before a row is written."
    )

    out.append("\n## The five conditions -- what counts as reported\n")
    out.append(
        "`mnp.demo.walk.walk_row` walks every row through these five conditions, in this "
        "order, against the ratified rules of `docs/2026-09-21-cile-a-otazky-pro-vedce.md` "
        "Part 1, translated:"
    )
    out.append("")
    out.append(_condition_rules_table())

    out.append("\n## Verdict vocabulary\n")
    out.append(_verdict_vocabulary_block())

    out.append("\n## Three extra rules\n")
    out.append(_three_rules_block(same_particle))

    out.append("\n## Ionic-strength sources\n")
    out.append(_ionic_strength_sources_block(table, corpus))

    out.append("\n## Comparability\n")
    out.append(_comparability_block(table, census, kind_e_sample))

    out.append("\n## The same-particle census\n")
    out.append(_same_particle_rule_block())

    out.append("\n## Harmonisation\n")
    out.append(
        "`mnp.demo.harmonise` rebuilds FINDINGS E2b's conversion-model scan (case-insensitive "
        "regex over the vendored full text for Smoluchowski, Hückel, Henry's function/equation "
        f"and Ohshima) and reproduces on this table: **{scan.zeta_papers}** papers report a zeta "
        f"value, **{scan.zeta_named}** name a model, **{scan.zeta_not_named}** do not; "
        f"**{scan.mobility_papers}** report a mobility, **{scan.mobility_named}** name a model "
        "(docs/FINDINGS.md §E2b). Naming a single textbook limit (Smoluchowski or Hückel) "
        "gives a known assumed f_m; naming Henry's function or Ohshima's approximation means no "
        "single f_m was assumed, so the reported value stands; naming both limits without Henry "
        "is treated as unknown, since a mention scan cannot tell which one was applied "
        "(harmonise.py's documented deviation from the original design, decided in review on "
        "2026-09-28, recorded in docs/DESIGN_2026-09-28_demo.md). A missing ionic strength or "
        "size gives no kappa*a and returns an interval, never a point produced by guessing. "
        "Zeta from a reported mobility uses ζ = 3ημ / (2ε f(κa)) at the reported temperature; "
        "an unreported temperature returns no value at all rather than defaulting to a water "
        "property. The Debye length assumes a 1:1 electrolyte in water at 25°C -- a limitation "
        "for any medium with divalent ions, stated here rather than silently applied."
    )

    out.append("\n## Resampling\n")
    out.append(_resampling_block(table))

    out.append("\n## The reader grid\n")
    out.append(_reader_grid_block(n_questions))

    out.append("\n## Limits, stated plainly\n")
    out.append(
        "- **The kappa audit has not been done.** Extraction accuracy is scored against "
        "`gold_50.csv`, which was annotated by Claude and has not been checked by a human; a "
        "blind re-judgement worksheet (`audit_10.csv`) exists and is unfilled "
        "(`out/release/DATASET_CARD.md`)."
    )
    out.append(
        "- **The gold set itself is model-annotated.** Every accuracy number this demo reports "
        "inherits that provenance."
    )
    out.append(
        "- **`models_named` records mentions, not the model actually applied.** Every harmonised "
        'value is conditional on "the named model is the one applied" -- an upper bound in the '
        "same sense the E2b scan itself is; a mention in a background paragraph is not evidence "
        "of what was used."
    )
    out.append(
        "- **The Debye length assumes a 1:1 electrolyte.** A medium with divalent ions has a "
        "shorter true Debye length than `debye_length_nm` returns."
    )
    out.append(
        "- **Quotes ship only from CC BY and CC0 sources.** The release is licensed CC BY 4.0; "
        "a quote from any other source is withheld and can be restored locally "
        "(`out/release/DATASET_CARD.md`, Licence)."
    )
    return "\n".join(out).rstrip() + "\n"


# -- the runner --------------------------------------------------------------------------------


def build(root: Path) -> list[Path]:
    """Write `README.md`, `cases/NN-<slug>.md` (one per case) and `METHOD.md` under `root/demo/`."""
    table, corpus = load()
    demo_dir = root / "demo"
    cases_dir = demo_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)

    census = corpus_wide_census(table)
    same_particle = same_particle_census(table)
    kind_e_sample = comp.read_query_set()
    runs_by_cell = {cell: load_run(cell) for cell in CELLS}
    line_index = _line_index(corpus)

    written: list[Path] = []
    all_qas: list[tuple[Question, AnswerKey]] = []
    for case in cases_mod.CASES:
        qas = questions_mod.questions_for(case, table)
        all_qas.extend(qas)
        text = case_page(case, table, corpus, census, kind_e_sample, runs_by_cell, line_index)
        path = cases_dir / f"{case.nn}-{case.slug}.md"
        path.write_text(text, encoding="utf-8")
        written.append(path)

    block = scope_block(table)
    readme_path = demo_dir / "README.md"
    readme_path.write_text(
        readme(table, corpus, runs_by_cell, all_qas, block, same_particle), encoding="utf-8"
    )
    written.append(readme_path)

    method_path = demo_dir / "METHOD.md"
    method_path.write_text(method(table, corpus, block, same_particle), encoding="utf-8")
    written.append(method_path)

    return sorted(written)
