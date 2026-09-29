"""Three demo questions per case, in the exact shapes `query_sets`/`comparability` define.

The point of building them this way is that nothing downstream has to know the demo exists:
`cells.build_d` must route every one of them "structured", and `scoring.score_one` must score
them the same way it scores the real query sets. Both are asserted here, not assumed.
"""

from __future__ import annotations

import pandas as pd
import pytest

from mnp import config
from mnp.demo import cases, questions
from mnp.eval import cells, scoring
from mnp.eval.query_sets import QueryKind


@pytest.fixture(scope="module")
def table() -> pd.DataFrame:
    return pd.read_csv(config.OUT_TABLES / "d1_zeta_table.csv")


@pytest.fixture(scope="module")
def corpus() -> cells.Corpus:
    return cells.load_corpus([case.pmcid for case in cases.CASES])


def _answer(qid: str, payload: dict) -> scoring.Answer:
    return scoring.Answer(qid=qid, cell="test", payload=payload)


@pytest.mark.parametrize("case", cases.CASES, ids=lambda c: f"{c.nn}-{c.slug}")
def test_between_one_and_three_questions_per_case(case, table):
    pairs = questions.questions_for(case, table)
    assert 1 <= len(pairs) <= 3


@pytest.mark.parametrize("case", cases.CASES, ids=lambda c: f"{c.nn}-{c.slug}")
def test_qids_are_xnn_kind_and_question_matches_key(case, table):
    for question, key in questions.questions_for(case, table):
        assert question.qid == key.qid
        assert question.qid == f"X{case.nn}-{key.kind.value}"


def test_cases_04_and_13_have_no_kind_b_question(table):
    """Neither paper has a condition every one of its rows agrees on being present or absent."""
    for nn in ("04", "13"):
        case = next(c for c in cases.CASES if c.nn == nn)
        kinds = {key.kind for _, key in questions.questions_for(case, table)}
        assert QueryKind.b not in kinds, nn


@pytest.mark.parametrize("case", cases.CASES, ids=lambda c: f"{c.nn}-{c.slug}")
def test_every_question_routes_structured_through_cell_d(case, table, corpus):
    for question, _ in questions.questions_for(case, table):
        delivered = cells.build_d(question, corpus)
        assert delivered.route == "structured", (question.qid, delivered.route, delivered.prompt)


@pytest.mark.parametrize("case", cases.CASES, ids=lambda c: f"{c.nn}-{c.slug}")
def test_the_answer_never_appears_in_the_question_text(case, table):
    for question, key in questions.questions_for(case, table):
        if key.kind is QueryKind.a:
            assert key.get("answer_value") not in question.text
        elif key.kind is QueryKind.b and key.get("answer_reported") == "True":
            assert key.get("answer_value") not in question.text
        elif key.kind is QueryKind.e:
            assert key.get("verdict") not in question.text.lower()


@pytest.mark.parametrize("case", cases.CASES, ids=lambda c: f"{c.nn}-{c.slug}")
def test_kind_a_question_always_names_the_particle(case, table):
    for question, key in questions.questions_for(case, table):
        if key.kind is QueryKind.a:
            particle_name = question.targeting("particle_name")
            assert particle_name, key.qid
            assert particle_name in question.text


def test_scoring_kind_a_correct_and_wrong(table):
    case = next(c for c in cases.CASES if c.nn == "02")
    _, key = next((q, k) for q, k in questions.questions_for(case, table) if k.kind is QueryKind.a)
    reported = key.get("answer_ionic_strength_reported") == "True"
    correct_payload = {
        "value": float(key.get("answer_value")),
        "unit": key.get("answer_unit"),
        "ionic_strength_reported": reported,
        "ionic_strength_mM": float(key.get("answer_ionic_strength_mM")) if reported else None,
    }
    correct = scoring.score_one(_answer(key.qid, correct_payload), key)
    assert correct.correct is True

    wrong_payload = dict(correct_payload, value=correct_payload["value"] + 100.0)
    wrong = scoring.score_one(_answer(key.qid, wrong_payload), key)
    assert wrong.correct is False


def test_scoring_kind_b_correct_and_wrong(table):
    case = next(c for c in cases.CASES if c.nn == "01")
    _, key = next((q, k) for q, k in questions.questions_for(case, table) if k.kind is QueryKind.b)
    reported = key.get("answer_reported") == "True"
    if reported:
        correct_payload = {"reported": True, "value": float(key.get("answer_value"))}
        wrong_payload = {"reported": True, "value": float(key.get("answer_value")) + 5.0}
    else:
        correct_payload = {"reported": False, "value": None}
        wrong_payload = {"reported": True, "value": 1.0}
    correct = scoring.score_one(_answer(key.qid, correct_payload), key)
    wrong = scoring.score_one(_answer(key.qid, wrong_payload), key)
    assert correct.correct is True
    assert wrong.correct is False


def test_scoring_kind_e_correct_and_wrong(table):
    case = next(c for c in cases.CASES if c.nn == "01")
    _, key = next((q, k) for q, k in questions.questions_for(case, table) if k.kind is QueryKind.e)
    verdict = key.get("verdict")
    blockers = key.get("blocker_fields")
    correct_payload = {"verdict": verdict, "blockers": blockers.split(";") if blockers else []}
    other = sorted({"comparable", "conditionally_comparable", "not_comparable"} - {verdict})[0]
    wrong_payload = {"verdict": other, "blockers": []}
    correct = scoring.score_one(_answer(key.qid, correct_payload), key)
    wrong = scoring.score_one(_answer(key.qid, wrong_payload), key)
    assert correct.correct is True
    assert wrong.correct is False


@pytest.mark.parametrize("case", cases.CASES, ids=lambda c: c.slug)
def test_no_lookup_is_built_on_a_value_a_rule_cleared(case, table):
    """X12-A once asked about a row whose medium reads "no background electrolyte (ionic
    strength 0 mM)": rule R1 clears that 0, but the question carried the paper's words, the
    reader repeated them, and the answer was scored a fabrication. A reader cannot know a
    project rule, so a lookup must not rest on a value one of them cleared."""
    rule_flags = (
        "ionic_strength_zero_not_reported",
        "temperature_step_not_measurement",
        "temperature_from_other_step",
    )
    by_id = table.set_index("row_id")
    for question, key in questions.questions_for(case, table):
        if question.kind is not QueryKind.a:
            continue
        flags = str(by_id.loc[key.get("gold_row_id"), "flags"] or "")
        assert not any(f in flags for f in rule_flags), (question.qid, flags)
