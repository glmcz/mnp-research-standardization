"""Three demo questions per case, in the exact shapes `mnp.eval.query_sets` already defines.

Building them this way means nothing downstream has to know the demo exists: `cells.build_d`
routes them the same way it routes the real query sets, and `scoring.score_one` scores them
unchanged. Kind A mirrors `query_sets.build_kind_a`'s record shape; kind B mirrors
`build_kind_b`'s, restricted to the fields `ABSENCE_FIELDS` actually supports (ionic_strength,
pH, temperature — not medium or instrument, which `build_kind_b` never built questions for and
whose values are not numbers `scoring._score_b` can compare); kind E mirrors
`comparability.PairSpec`.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from mnp.demo.cases import Case
from mnp.eval import comparability as comp
from mnp.eval.query_sets import (
    ABSENCE_FIELDS,
    AnswerKey,
    QueryKind,
    Question,
    answer_from_record,
    question_from_record,
)

_QUANTITY_WORDS: dict[str, str] = {
    "zeta_potential": "zeta potential",
    "electrophoretic_mobility": "electrophoretic mobility",
}

_VERDICT_RANK: dict[str, int] = {
    "comparable": 0,
    "conditionally_comparable": 1,
    "not_comparable": 2,
}


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


def _rows(table: pd.DataFrame, pmcid: str) -> list[dict[str, Any]]:
    return table[table["pmcid"] == pmcid].to_dict(orient="records")


def _particle_phrase(row: dict[str, Any]) -> str:
    material = _str(row.get("material"))
    functionalisation = _str(row.get("functionalisation"))
    return f"{material}, {functionalisation}" if functionalisation else material


def _lookup_key(row: dict[str, Any]) -> tuple[str, ...]:
    return (
        _str(row.get("material")),
        _str(row.get("functionalisation")),
        _str(row.get("medium_text")),
        _str(row.get("particle_name")),
        _str(row.get("quantity")),
    )


def _row_number(row: dict[str, Any]) -> int:
    try:
        return int(_str(row.get("row_id")).rsplit("-r", 1)[-1])
    except ValueError:
        return 0


# -- kind A: a lookup unique in its paper, always naming the particle -----------------------


def _kind_a(case: Case, rows: list[dict[str, Any]]) -> tuple[Question, AnswerKey] | None:
    counts: dict[tuple[str, ...], int] = {}
    for row in rows:
        key = _lookup_key(row)
        counts[key] = counts.get(key, 0) + 1
    candidates = [
        row
        for row in rows
        if counts[_lookup_key(row)] == 1
        and _str(row.get("particle_name"))
        and _str(row.get("material"))
        and _str(row.get("medium_text"))
        and _float(row.get("value")) is not None
    ]
    if not candidates:
        return None
    # zeta_potential first (what kind A means everywhere else in this repo), then by row number.
    row = sorted(
        candidates,
        key=lambda r: (0 if _str(r.get("quantity")) == "zeta_potential" else 1, _row_number(r)),
    )[0]
    quantity = _str(row.get("quantity"))
    quantity_word = _QUANTITY_WORDS.get(quantity, quantity)
    particle_name = _str(row.get("particle_name"))
    medium_text = _str(row.get("medium_text"))
    reported = bool(row.get("ionic_strength_reported"))
    text = (
        f"In {case.pmcid}, what {quantity_word} was reported for {_particle_phrase(row)} "
        f'particles described as "{particle_name}" in {medium_text}, and at what ionic '
        "strength was that measurement made?"
    )
    record = {
        "qid": f"X{case.nn}-A",
        "kind": "A",
        "pmcid": case.pmcid,
        "question": text,
        "material": _str(row.get("material")),
        "functionalisation": _str(row.get("functionalisation")),
        "medium_text": medium_text,
        "quantity": quantity,
        "particle_name": particle_name,
        "gold_row_id": _str(row.get("row_id")),
        "answer_value": f"{_float(row.get('value'))}",
        "answer_unit": _str(row.get("unit")) or "mV",
        "answer_ionic_strength_reported": str(reported),
        "answer_ionic_strength_mM": f"{_float(row.get('ionic_strength_mM'))}" if reported else "",
        "evidence_line_ids": _str(row.get("evidence_line_ids")),
        "source": f"d1_zeta_table.csv:{row.get('row_id')}",
    }
    return question_from_record(record), answer_from_record(record)


# -- kind B: a condition every row of the paper agrees on --------------------------------------


def _kind_b(case: Case, rows: list[dict[str, Any]]) -> tuple[Question, AnswerKey] | None:
    for name in ("ionic_strength", "pH", "temperature"):
        field = ABSENCE_FIELDS[name]
        reported_column = f"{field.name}_reported"
        flags = {bool(row.get(reported_column)) for row in rows}
        if flags == {False}:
            reported, value = False, None
        elif flags == {True}:
            values = {_float(row.get(field.column)) for row in rows}
            if len(values) != 1 or None in values:
                continue
            reported, value = True, values.pop()
        else:
            continue

        evidence = (
            ";".join(
                sorted(
                    {
                        part
                        for row in rows
                        for part in _str(row.get("evidence_line_ids")).split(";")
                        if part
                    }
                )
            )
            if reported
            else ""
        )
        record = {
            "qid": f"X{case.nn}-B",
            "kind": "B",
            "pmcid": case.pmcid,
            "question": (
                f"What {field.asked_as} was used for the zeta-potential and "
                f"electrophoretic-mobility measurements reported in {case.pmcid}?"
            ),
            "field": field.name,
            "answer_reported": str(reported),
            "answer_value": f"{value}" if reported else "",
            "n_rows": str(len(rows)),
            "row_ids": ";".join(sorted(_str(row.get("row_id")) for row in rows)),
            "evidence_line_ids": evidence,
            "gold_cross_check": "not_in_gold",
            "source": f"d1_zeta_table.csv:{case.pmcid}:{reported_column}",
        }
        return question_from_record(record), answer_from_record(record)
    return None


# -- kind E: one within-paper pair, keyed exactly as comparability.PairSpec -------------------


def _pairs(rows: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    ordered = sorted(rows, key=lambda r: _str(r.get("row_id")))
    return [
        (ordered[i], ordered[j]) for i in range(len(ordered)) for j in range(i + 1, len(ordered))
    ]


def _best_pair(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """The most instructive pair: prefer comparable, then conditionally comparable, then any."""
    best: tuple[int, str, str, dict[str, Any], dict[str, Any]] | None = None
    for a, b in _pairs(rows):
        verdict = comp.comparable(comp.ZetaRow.from_mapping(a), comp.ZetaRow.from_mapping(b))
        rank = _VERDICT_RANK[verdict.verdict.value]
        candidate = (rank, _str(a.get("row_id")), _str(b.get("row_id")), a, b)
        if best is None or candidate[:3] < best[:3]:
            best = candidate
    return (best[3], best[4]) if best else None


def _widest_spread_pair(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Case 02's pair: the one that shows medium alone moving zeta the furthest."""
    best: tuple[float, str, dict[str, Any], dict[str, Any]] | None = None
    for a, b in _pairs(rows):
        value_a, value_b = _float(a.get("value")), _float(b.get("value"))
        if value_a is None or value_b is None:
            continue
        candidate = (abs(value_a - value_b), _str(a.get("row_id")), a, b)
        if best is None or (-candidate[0], candidate[1]) < (-best[0], best[1]):
            best = candidate
    return (best[2], best[3]) if best else None


#: Case 02's pair is picked for spread (the 54 mV medium swing), not verdict rank.
_PAIR_PICKERS = {"02": _widest_spread_pair}


def _kind_e(case: Case, rows: list[dict[str, Any]]) -> tuple[Question, AnswerKey] | None:
    picker = _PAIR_PICKERS.get(case.nn, _best_pair)
    pair = picker(rows)
    if pair is None:
        return None
    row_a = comp.ZetaRow.from_mapping(pair[0])
    row_b = comp.ZetaRow.from_mapping(pair[1])
    first, second = sorted((row_a, row_b), key=lambda r: r.row_id)
    verdict = comp.comparable(first, second)
    spec = comp.PairSpec(stratum="within_case", a=first, b=second, verdict=verdict)
    qid = f"X{case.nn}-E"
    question = Question(
        qid=qid,
        kind=QueryKind.e,
        text=spec.question,
        scope=tuple(sorted({first.pmcid, second.pmcid})),
        target=(("row_id_a", first.row_id), ("row_id_b", second.row_id)),
    )
    record = spec.as_record()
    key = AnswerKey(
        qid=qid,
        kind=QueryKind.e,
        fields=tuple((name, str(value)) for name, value in record.items()),
    )
    return question, key


def questions_for(case: Case, table: pd.DataFrame) -> list[tuple[Question, AnswerKey]]:
    """This case's demo questions: kind A, then B, then E, skipping any kind with no honest row.

    Case 04 (PMC12312160) and case 13 (PMC12598813) come back with two, not three: neither
    paper has a condition every one of its rows agrees on being present or absent (ionic
    strength, pH and temperature are each a mix of reported/derived/unreported across their
    rows), so `_kind_b` has nothing to build without forcing a question the data does not
    support.
    """
    rows = _rows(table, case.pmcid)
    out: list[tuple[Question, AnswerKey]] = []
    for builder in (_kind_a, _kind_b, _kind_e):
        built = builder(case, rows)
        if built is not None:
            out.append(built)
    return out
