"""The scorer — every number in the results table, and none of them from a model.

The one that decides the talk is the fabrication rate on kind B: an answer that states an
ionic strength where the paper reported none. That is not a wrong number, it is an invented
one, and the two failures have to be counted apart.

The only judgement-dependent number in here is the kind D preference, and it is isolated
behind `PreferenceVerdict` — supplied from outside, never computed, and reported separately
so no model-free headline can quietly absorb it.
"""

import pytest

from mnp.eval import query_sets as qs
from mnp.eval import scoring
from mnp.eval.query_sets import QueryKind as K


def _key(kind, **fields):
    record = {column: "" for column in qs.FIELDNAMES[kind]}
    record["qid"] = f"{kind.value}-1"
    record.update({name: str(value) for name, value in fields.items()})
    return qs.answer_from_record(record)


def _answer(kind, cell="B", tokens=100, calls=0, **payload):
    return scoring.Answer(
        qid=f"{kind.value}-1",
        cell=cell,
        payload=payload,
        raw="",
        tokens_delivered=tokens,
        retrieval_calls=calls,
    )


# -- parsing whatever the subagent actually returned ------------------------------------------


def test_the_answer_json_is_found_even_when_it_is_wrapped_in_prose_and_a_fence():
    text = 'Here is my answer.\n```json\n{"reported": false, "value": null}\n```\nDone.'
    answer = scoring.parse_answer("B-1", "B", text)
    assert answer.payload == {"reported": False, "value": None}


def test_an_unparseable_answer_is_recorded_rather_than_raising():
    answer = scoring.parse_answer("B-1", "B", "I could not determine this.")
    assert answer.payload == {}
    assert answer.unparsed


def test_an_unparseable_answer_is_never_scored_correct():
    answer = scoring.parse_answer("B-1", "B", "no idea")
    scored = scoring.score_one(answer, _key(K.b, answer_reported="False"), corpus=None)
    assert scored.correct is False


# -- kind B, the money metric -----------------------------------------------------------------


def test_saying_not_reported_when_nothing_was_reported_is_correct_and_not_a_fabrication():
    scored = scoring.score_one(
        _answer(K.b, reported=False, value=None), _key(K.b, answer_reported="False"), corpus=None
    )
    assert scored.correct is True
    assert scored.fabricated is False


def test_stating_a_value_where_none_was_reported_is_a_fabrication():
    scored = scoring.score_one(
        _answer(K.b, reported=True, value=10.0), _key(K.b, answer_reported="False"), corpus=None
    )
    assert scored.correct is False
    assert scored.fabricated is True


def test_an_answer_that_says_not_reported_and_then_states_a_value_anyway_is_still_a_fabrication():
    """The failure this metric exists for is a number appearing where the literature has
    none. A hedge in the neighbouring field does not undo it."""
    scored = scoring.score_one(
        _answer(K.b, reported=False, value=10.0), _key(K.b, answer_reported="False"), corpus=None
    )
    assert scored.fabricated is True
    assert scored.correct is False


def test_a_reported_value_recalled_correctly_is_correct_and_not_a_fabrication():
    key = _key(K.b, answer_reported="True", answer_value="10.0")
    scored = scoring.score_one(_answer(K.b, reported=True, value=10.0), key, corpus=None)
    assert scored.correct is True
    assert scored.fabricated is False


def test_a_reported_value_recalled_wrongly_is_wrong_but_is_not_a_fabrication():
    key = _key(K.b, answer_reported="True", answer_value="10.0")
    scored = scoring.score_one(_answer(K.b, reported=True, value=137.0), key, corpus=None)
    assert scored.correct is False
    assert scored.fabricated is False


def test_missing_a_value_that_was_reported_is_wrong_but_is_not_a_fabrication():
    key = _key(K.b, answer_reported="True", answer_value="10.0")
    scored = scoring.score_one(_answer(K.b, reported=False, value=None), key, corpus=None)
    assert scored.correct is False
    assert scored.fabricated is False


# -- kind A, a value and a condition together --------------------------------------------------


def test_kind_a_needs_both_halves_of_the_question():
    key = _key(K.a, answer_value="-34.2", answer_unit="mV", answer_ionic_strength_reported="False")
    right = _answer(K.a, value=-34.2, unit="mV", ionic_strength_reported=False)
    assert scoring.score_one(right, key, corpus=None).correct is True
    half = _answer(
        K.a, value=-34.2, unit="mV", ionic_strength_reported=True, ionic_strength_mM=35.0
    )
    assert scoring.score_one(half, key, corpus=None).correct is False


def test_kind_a_invents_an_ionic_strength_and_that_counts_as_a_fabrication_too():
    key = _key(K.a, answer_value="-34.2", answer_unit="mV", answer_ionic_strength_reported="False")
    answer = _answer(K.a, value=-34.2, unit="mV", ionic_strength_mM=600.0)
    assert scoring.score_one(answer, key, corpus=None).fabricated is True


def test_a_printed_value_is_allowed_to_round():
    key = _key(K.a, answer_value="-34.25", answer_unit="mV", answer_ionic_strength_reported="False")
    answer = _answer(K.a, value=-34.2, unit="mV", ionic_strength_reported=False)
    assert scoring.score_one(answer, key, corpus=None).correct is True


def test_the_wrong_unit_is_the_wrong_answer():
    key = _key(K.a, answer_value="-34.2", answer_unit="mV", answer_ionic_strength_reported="False")
    answer = _answer(K.a, value=-34.2, unit="mV/cm", ionic_strength_reported=False)
    assert scoring.score_one(answer, key, corpus=None).correct is False


# -- kind C, a set ------------------------------------------------------------------------------


def test_kind_c_is_scored_as_a_set_with_precision_and_recall():
    key = _key(K.c, answer_pmcids="PMC1;PMC2;PMC3")
    scored = scoring.score_one(_answer(K.c, pmcids=["PMC1", "PMC2", "PMC9"]), key, corpus=None)
    assert scored.correct is False
    assert scored.metric("set_precision") == pytest.approx(2 / 3)
    assert scored.metric("set_recall") == pytest.approx(2 / 3)


def test_kind_c_is_correct_only_on_the_exact_set():
    key = _key(K.c, answer_pmcids="PMC1;PMC2")
    assert scoring.score_one(_answer(K.c, pmcids=["PMC2", "PMC1"]), key, corpus=None).correct
    assert not scoring.score_one(
        _answer(K.c, pmcids=["PMC1", "PMC2", "PMC3"]), key, corpus=None
    ).correct


def test_naming_every_paper_in_the_corpus_does_not_win_kind_c():
    key = _key(K.c, answer_pmcids="PMC1")
    scored = scoring.score_one(
        _answer(K.c, pmcids=[f"PMC{i}" for i in range(1, 50)]), key, corpus=None
    )
    assert scored.correct is False
    assert scored.metric("set_precision") < 0.05


# -- kind D, grounding, and the seam where judgement would go ------------------------------------


def test_kind_d_is_grounded_when_it_cites_a_passage_stating_the_mechanism(corpus, doc_a, doc_b):
    acceptable = ";".join([doc_a.lines[2].line_id, doc_b.lines[1].line_id])
    key = _key(K.d, acceptable_line_ids=acceptable, content_terms="double layer;screened")
    answer = _answer(K.d, answer="The double layer was screened.", citations=["PMCAAA:L3"])
    scored = scoring.score_one(answer, key, corpus=corpus)
    assert scored.correct is True
    assert scored.metric("term_coverage") == pytest.approx(1.0)


def test_kind_d_grounded_on_a_different_paper_that_states_the_same_mechanism(corpus, doc_a, doc_b):
    """The known weakness of judging against a source passage. The acceptable set is
    corpus-wide precisely so a correct answer grounded elsewhere is not marked wrong."""
    acceptable = ";".join([doc_a.lines[2].line_id, doc_b.lines[1].line_id])
    key = _key(K.d, acceptable_line_ids=acceptable, content_terms="double layer")
    answer = _answer(K.d, answer="see the other paper", citations=["PMCBBB:L2"])
    assert scoring.score_one(answer, key, corpus=corpus).correct is True


def test_an_uncited_kind_d_answer_is_not_grounded_however_fluent_it_is(corpus, doc_a):
    key = _key(
        K.d, acceptable_line_ids=doc_a.lines[2].line_id, content_terms="double layer;screened"
    )
    answer = _answer(K.d, answer="The double layer is screened by counterions.", citations=[])
    scored = scoring.score_one(answer, key, corpus=corpus)
    assert scored.correct is False
    assert scored.metric("term_coverage") == pytest.approx(1.0)


def test_padding_kind_d_with_citations_costs_precision(corpus, doc_a):
    key = _key(K.d, acceptable_line_ids=doc_a.lines[2].line_id, content_terms="double layer")
    answer = _answer(
        K.d, answer="x", citations=["PMCAAA:L1", "PMCAAA:L2", "PMCAAA:L3", "PMCBBB:L1"]
    )
    scored = scoring.score_one(answer, key, corpus=corpus)
    assert scored.correct is True
    assert scored.metric("grounding_precision") == pytest.approx(0.25)


def test_the_preference_verdict_is_supplied_never_computed():
    """If this module ever learns to decide which of two explanations is better, it has
    started calling a model and the 'model-free' claim is gone."""
    with open(scoring.__file__, encoding="utf-8") as handle:
        text = handle.read()
    for forbidden in ("openai", "httpx", "Anthropic", "subprocess"):
        assert forbidden not in text
    assert "preference" in scoring.MODEL_JUDGED_METRICS


def test_preferences_aggregate_separately_from_the_model_free_numbers():
    verdicts = [
        scoring.PreferenceVerdict("D-1", "C", "D", "C", "judge-note"),
        scoring.PreferenceVerdict("D-2", "C", "D", "tie", ""),
    ]
    tally = scoring.aggregate_preferences(verdicts)
    assert tally[("C", "D")] == {"C": 1, "D": 0, "tie": 1}


# -- citations ------------------------------------------------------------------------------------


def test_a_line_citation_is_checked_against_the_lines_the_row_was_actually_read_from(corpus, doc_a):
    key = _key(
        K.a,
        answer_value="-34.2",
        answer_unit="mV",
        answer_ionic_strength_reported="False",
        pmcid="PMCAAA",
        evidence_line_ids=doc_a.lines[1].line_id,
    )
    good = _answer(
        K.a, value=-34.2, unit="mV", ionic_strength_reported=False, citations=["PMCAAA:L2"]
    )
    scored = scoring.score_one(good, key, corpus=corpus)
    assert scored.citation_recall == pytest.approx(1.0)
    assert scored.citation_precision == pytest.approx(1.0)


def test_a_citation_to_the_wrong_line_is_not_a_citation(corpus, doc_a):
    key = _key(
        K.a,
        answer_value="-34.2",
        answer_unit="mV",
        answer_ionic_strength_reported="False",
        pmcid="PMCAAA",
        evidence_line_ids=doc_a.lines[1].line_id,
    )
    answer = _answer(
        K.a, value=-34.2, unit="mV", ionic_strength_reported=False, citations=["PMCAAA:L1"]
    )
    scored = scoring.score_one(answer, key, corpus=corpus)
    assert scored.citation_recall == pytest.approx(0.0)


def test_a_structured_cell_may_cite_a_row_and_it_resolves_to_its_evidence_lines(corpus, doc_a):
    """Cell D reads records, not lines. If a row citation did not resolve, the structured
    cells would score zero on citation by construction and the comparison would be rigged."""
    key = _key(
        K.a,
        answer_value="-34.2",
        answer_unit="mV",
        answer_ionic_strength_reported="False",
        pmcid="PMCAAA",
        evidence_line_ids=doc_a.lines[1].line_id,
    )
    answer = _answer(
        K.a, value=-34.2, unit="mV", ionic_strength_reported=False, citations=["row:PMCAAA-r1"]
    )
    scored = scoring.score_one(answer, key, corpus=corpus)
    assert scored.citation_recall == pytest.approx(1.0)


def test_a_bare_line_number_resolves_against_the_paper_the_question_named(corpus, doc_a):
    key = _key(
        K.b, answer_reported="False", pmcid="PMCAAA", evidence_line_ids=doc_a.lines[1].line_id
    )
    answer = _answer(K.b, reported=False, value=None, citations=["L2"])
    assert scoring.score_one(answer, key, corpus=corpus).citation_recall == pytest.approx(1.0)


def test_citation_scoring_is_skipped_rather_than_zeroed_when_there_is_nothing_to_cite():
    """A kind B absence has no evidence line. Scoring it zero would punish the right answer."""
    key = _key(K.b, answer_reported="False", pmcid="PMCAAA", evidence_line_ids="")
    scored = scoring.score_one(_answer(K.b, reported=False, value=None), key, corpus=None)
    assert scored.citation_recall is None


# -- the table the talk prints ------------------------------------------------------------------


def test_aggregate_reports_accuracy_fabrication_tokens_and_calls_per_cell_and_kind():
    keys = [
        _key(K.b, answer_reported="False"),
        qs.answer_from_record(
            {**{c: "" for c in qs.FIELDNAMES[K.b]}, "qid": "B-2", "answer_reported": "False"}
        ),
    ]
    answers = [
        _answer(K.b, cell="B", tokens=100, calls=0, reported=False, value=None),
        scoring.Answer("B-2", "B", {"reported": True, "value": 5.0}, "", 300, 4),
    ]
    scored = scoring.score_all(answers, keys, corpus=None)
    summary = scoring.aggregate(scored)[("B", K.b)]
    assert summary.n == 2
    assert summary.accuracy == pytest.approx(0.5)
    assert summary.fabrication_rate == pytest.approx(0.5)
    assert summary.mean_tokens == pytest.approx(200.0)
    assert summary.mean_retrieval_calls == pytest.approx(2.0)


def test_the_summary_says_which_of_its_numbers_needed_a_model():
    assert scoring.MODEL_FREE_METRICS & scoring.MODEL_JUDGED_METRICS == frozenset()
    assert "fabrication_rate" in scoring.MODEL_FREE_METRICS
    assert "accuracy" in scoring.MODEL_FREE_METRICS


# -- kind E --------------------------------------------------------------------------------


def _kind_e_key(verdict="not_comparable", blockers="pH_unreported;medium_class_mismatch"):
    return qs.answer_from_record(
        {
            "row_id_a": "PMCAAA-r1",
            "row_id_b": "PMCBBB-r1",
            "pmcid_a": "PMCAAA",
            "pmcid_b": "PMCBBB",
            "verdict": verdict,
            "blockers": blockers,
            "question": "?",
        }
    )


def test_kind_e_is_correct_only_on_the_verdict_the_key_derived():
    key = _kind_e_key()
    right = scoring.Answer(key.qid, "E", {"verdict": "not_comparable", "blockers": []}, "", 0, 0)
    wrong = scoring.Answer(key.qid, "E", {"verdict": "comparable", "blockers": []}, "", 0, 0)
    assert scoring.score_one(right, key, corpus=None).correct is True
    assert scoring.score_one(wrong, key, corpus=None).correct is False


def test_kind_e_also_scores_which_fields_were_named_as_blockers():
    key = _kind_e_key()
    answer = scoring.Answer(
        key.qid,
        "E",
        {"verdict": "not_comparable", "blockers": ["pH_unreported", "instrument_mismatch"]},
        "",
        0,
        0,
    )
    scored = scoring.score_one(answer, key, corpus=None)
    assert scored.metric("blocker_precision") == pytest.approx(0.5)
    assert scored.metric("blocker_recall") == pytest.approx(0.5)
    assert scored.metric("blockers_exact") == pytest.approx(0.0)
