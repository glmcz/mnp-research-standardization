"""Query kinds A–D: the questions the tool-value grid is scored on.

Kind E already exists (`comparability.py`) and these match its shape: generated
deterministically from a seed, every question carrying the rows or papers it came from, every
answer re-derivable from the corpus so the key cannot drift away from the data.

The tests that matter most are the ones separating a **question** from its **answer key**.
A question the answering agent is shown must carry no field of the answer, or every cell in
the grid is measuring how well a model can copy. `TARGET_COLUMNS` is an allow-list for exactly
that reason, and `test_no_target_column_is_an_answer_column` is what stops it growing.
"""

import math

import pytest

from mnp import config
from mnp.eval import query_sets as qs
from mnp.eval.query_sets import QueryKind as K

ALL_KINDS = (K.a, K.b, K.c, K.d)


def records(kind):
    """Never let a test pass because the generator produced nothing."""
    found = qs.read_records(kind)
    assert found, f"no questions on disk for kind {kind.value}"
    return found


# -- shape: four kinds, on disk, regenerable -------------------------------------------------


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_every_kind_has_a_query_file_under_queries(kind):
    assert qs.KIND_PATHS[kind].parent == config.QUERIES
    assert qs.KIND_PATHS[kind].is_file(), qs.KIND_PATHS[kind]


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_the_file_on_disk_is_what_the_generator_produces(kind):
    assert records(kind) == qs.build(kind)


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_generation_is_deterministic(kind):
    assert qs.build(kind) == qs.build(kind)


def test_the_counts_are_roughly_thirty_thirty_ten_ten():
    counts = {kind: len(records(kind)) for kind in ALL_KINDS}
    assert counts[K.a] == 30
    assert counts[K.b] == 30
    assert counts[K.c] == 10
    assert counts[K.d] == 10


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_every_question_id_is_unique_and_names_its_kind(kind):
    qids = [record["qid"] for record in records(kind)]
    assert len(set(qids)) == len(qids)
    assert all(qid.startswith(f"{kind.value}-") for qid in qids)


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_every_question_carries_its_provenance(kind):
    for record in records(kind):
        assert record["source"], record["qid"]


# -- the separation of question from answer --------------------------------------------------


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_no_target_column_is_an_answer_column(kind):
    """The one line that decides whether this whole evaluation means anything.

    `Question.target` is what a static router is allowed to condition on. An answer column
    reaching it hands the router the answer, and every number downstream becomes a measure of
    copying rather than of retrieval.
    """
    assert set(qs.TARGET_COLUMNS[kind]) & qs.ANSWER_COLUMNS == set()


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_a_question_read_from_disk_carries_no_answer_value(kind):
    found = records(kind)
    questions = qs.read_questions(kind)
    assert len(questions) == len(found)
    for record, question in zip(found, questions, strict=True):
        rendered = f"{question.text}|{question.scope}|{sorted(question.target)}"
        for column in qs.ANSWER_COLUMNS:
            value = str(record.get(column, "")).strip()
            if len(value) < 3 or value in {"True", "False", "0", "[]"}:
                continue  # a boolean or a tiny number can coincide with question wording
            assert value not in rendered, f"{question.qid}: {column} leaked into the question"


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_the_answer_key_and_the_questions_line_up_one_to_one(kind):
    questions = qs.read_questions(kind)
    keys = qs.read_answer_key(kind)
    assert questions
    assert [q.qid for q in questions] == [k.qid for k in keys]


# -- kind A: conditioned lookup, ground truth from gold_50 -----------------------------------


def test_kind_a_ground_truth_comes_from_gold_50_and_still_matches_it():
    gold = qs.gold_rows()
    assert len(gold) > 100
    by_id = {row["row_id"]: row for row in gold}
    for record in records(K.a):
        row = by_id[record["gold_row_id"]]
        assert math.isclose(float(record["answer_value"]), float(row["value"]))
        assert record["answer_unit"] == row["unit"]
        assert record["pmcid"] == row["pmcid"]


def test_kind_a_asks_for_the_value_and_the_ionic_strength_together():
    for record in records(K.a):
        text = record["question"].lower()
        assert "ionic strength" in text
        assert record["pmcid"] in record["question"]


def test_kind_a_never_prints_the_answer_in_the_question():
    for record in records(K.a):
        assert record["answer_value"] not in record["question"]


def test_kind_a_evidence_line_ids_resolve_in_the_paper_they_name():
    for record in records(K.a):
        doc = qs.doc_for(record["pmcid"])
        known = {line.line_id for line in doc.lines}
        ids = set(record["evidence_line_ids"].split(";"))
        assert ids and ids <= known, record["qid"]


def test_every_kind_a_question_singles_out_exactly_one_gold_value():
    """A-001 and A-002 once asked one paper the same question and wanted 24.13 and -33.97:
    two particle sizes, one phrase. Whatever a cell answered, one of the pair was wrong by
    construction — 15 of 30 questions were like that when the first pilot read them."""
    gold = qs.gold_rows()
    for record in records(K.a):
        matching = [
            row
            for row in gold
            if qs._str(row["pmcid"]) == record["pmcid"]
            and qs._str(row.get("quantity")) == "zeta_potential"
            and qs._str(row.get("material")) == record["material"]
            and qs._str(row.get("functionalisation")) == record["functionalisation"]
            and qs._str(row.get("medium_text")) == record["medium_text"]
            and (
                not record["particle_name"]
                or qs._str(row.get("particle_name")) == record["particle_name"]
            )
        ]
        values = {qs._float(row.get("value")) for row in matching}
        assert values == {float(record["answer_value"])}, record["qid"]


def test_kind_a_names_the_particle_in_the_question_when_it_targets_one():
    named = [record for record in records(K.a) if record["particle_name"]]
    assert named, "no question needed a particle name, so the rule above is untested"
    for record in named:
        assert record["particle_name"] in record["question"], record["qid"]


def test_kind_a_spreads_across_papers_rather_than_draining_one():
    pmcids = [record["pmcid"] for record in records(K.a)]
    assert len(set(pmcids)) >= 8
    assert max(pmcids.count(p) for p in set(pmcids)) <= 4


# -- kind B: absence, a positive claim -------------------------------------------------------


def test_kind_b_is_not_all_absences_or_always_saying_no_would_score_full_marks():
    found = records(K.b)
    reported = [record["answer_reported"] == "True" for record in found]
    assert 0 < sum(reported) < len(reported)
    assert sum(reported) >= 8


def test_kind_b_ground_truth_is_the_reported_boolean_of_every_row_of_that_paper():
    table = qs.zeta_table()
    assert len(table) > 1000
    for record in records(K.b):
        field = record["field"]
        rows = [row for row in table if row["pmcid"] == record["pmcid"]]
        assert rows, record["qid"]
        flags = {bool(row[f"{field}_reported"]) for row in rows}
        assert len(flags) == 1, f"{record['qid']}: the paper disagrees with itself"
        assert flags.pop() is (record["answer_reported"] == "True")


def test_a_kind_b_absence_carries_no_value_at_all():
    absent = [r for r in records(K.b) if r["answer_reported"] == "False"]
    assert absent
    for record in absent:
        assert record["answer_value"] == ""


def test_a_kind_b_presence_carries_exactly_one_value():
    present = [r for r in records(K.b) if r["answer_reported"] == "True"]
    assert present
    for record in present:
        assert float(record["answer_value"]) == float(record["answer_value"])


def test_kind_b_covers_more_than_one_condition_field():
    fields = {record["field"] for record in records(K.b)}
    assert fields <= set(qs.ABSENCE_FIELDS)
    assert len(fields) >= 3


def test_kind_b_never_asks_about_a_field_the_question_does_not_name():
    for record in records(K.b):
        assert qs.ABSENCE_FIELDS[record["field"]].asked_as in record["question"]


# -- kind C: comparison, a structured filter -------------------------------------------------


def test_kind_c_ground_truth_is_reproducible_by_running_the_filter_again():
    table = qs.zeta_table()
    assert len(table) > 1000
    for record in records(K.c):
        spec = qs.filter_from_record(record)
        pmcids = sorted({row["pmcid"] for row in qs.apply_filter(table, spec)})
        assert pmcids == record["answer_pmcids"].split(";")


def test_kind_c_questions_are_asked_in_words_not_the_routers_codes():
    """C-001 once asked for PE 'functionalised as BARE'. BARE is the router's key; the rows
    say 'nonfunctionalized' and 'plain', so a reader answering from evidence found none."""
    for record in records(K.c):
        spec = qs.filter_from_record(record)
        assert "BARE" not in record["question"], record["qid"]
        if spec.material:
            assert qs.MATERIAL_WORDS[spec.material] in record["question"], record["qid"]
        if spec.functionalisation:
            words = qs.FUNCTIONALISATION_WORDS[spec.functionalisation]
            assert words in record["question"], record["qid"]


def test_kind_c_answers_are_neither_empty_nor_the_whole_corpus():
    for record in records(K.c):
        n = len(record["answer_pmcids"].split(";"))
        assert 1 <= n <= 40, record["qid"]


def test_kind_c_questions_are_corpus_wide_and_name_no_paper():
    questions = qs.read_questions(K.c)
    assert questions
    for question in questions:
        assert question.scope == ()


# -- kind D: mechanism, the kind that is meant to be won by prose ----------------------------


def test_kind_d_acceptable_evidence_exists_in_the_corpus_for_every_topic():
    for record in records(K.d):
        ids = record["acceptable_line_ids"].split(";")
        assert len(ids) >= qs.MIN_ACCEPTABLE_LINES, record["qid"]
        assert int(record["n_acceptable_papers"]) >= 5


def test_kind_d_acceptable_evidence_is_recomputable_from_the_topic_rules():
    corpus_lines = qs.corpus_lines()
    assert len(corpus_lines) > 10_000
    for record in records(K.d):
        topic = qs.MECHANISM_TOPICS[record["topic"]]
        found = sorted(qs.acceptable_lines(corpus_lines, topic))
        assert found == sorted(record["acceptable_line_ids"].split(";"))


def test_kind_d_acceptable_evidence_spans_papers_so_one_passage_is_not_the_only_right_answer():
    """The known weakness of judging against the passage a question was built from is that a
    correct answer grounded somewhere else scores zero. The acceptable set is corpus-wide for
    exactly that reason, and this is the test that keeps it that way."""
    for record in records(K.d):
        assert int(record["n_acceptable_papers"]) > 1
        assert record["seed_line_id"] in record["acceptable_line_ids"].split(";")


def test_kind_d_has_no_structured_field_and_says_so():
    """Kind D exists so the result is not rigged. If a mechanism were answerable from the
    table, the kind would not be doing its job."""
    for record in records(K.d):
        assert record["structured_field"] == "none"


def test_kind_d_content_terms_are_taken_from_the_corpus_not_invented():
    corpus_lines = qs.corpus_lines()
    assert len(corpus_lines) > 10_000
    by_id = {line.line_id: line for line in corpus_lines}
    for record in records(K.d):
        seed = by_id[record["seed_line_id"]]
        terms = record["content_terms"].split(";")
        assert terms
        assert all(term in seed.text.lower() for term in terms), record["qid"]


# -- determinism ------------------------------------------------------------------------------


def test_nothing_in_here_uses_a_clock_or_an_unseeded_random():
    with open(qs.__file__, encoding="utf-8") as handle:
        text = handle.read()
    assert "datetime.now" not in text
    assert "random.random()" not in text
    assert "random.shuffle(" not in text  # module-level random, not a seeded Random instance
