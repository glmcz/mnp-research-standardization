"""The per-cell context builders — the exact text an answering subagent is handed.

Four cells of `docs/DESIGN_2026-09-17_tool-value-grid.md` §1: B is S1 x C2 (one-shot retrieval),
D is S2 x C3 (a static route through the table with a prose fallback), C and E are S1/S2 x C4
(the agent decides what to fetch). B and D are fully precomputable and are computed here; C and
E cannot be, so what is built for them is the tool *contract* plus a deterministic
implementation the parent session can drive.

Nothing in this module calls a model. The whole point is that a run can be inspected, re-run
and diffed without spending a token.

The test that would invalidate everything if it were missing is
`test_no_cell_leaks_the_answer_key_into_its_prompt`. If an answer reaches the prompt, every
number the grid produces is a measure of copying.
"""

import pytest

from mnp.corpus import lines
from mnp.eval import cells, comparability, selectors
from mnp.eval import query_sets as qs
from mnp.eval.query_sets import QueryKind as K


def _question(kind, text, scope=(), **target):
    return qs.Question(
        qid=f"{kind.value}-test",
        kind=kind,
        text=text,
        scope=tuple(scope),
        target=tuple(sorted(target.items())),
    )


# -- the retrieval index is the tuned BM25 of selectors.py, not a second one -----------------


def test_the_corpus_index_reproduces_the_tuned_bm25_ranking_exactly(corpus):
    """`selectors.py` already holds the swept BM25. This index only makes it fast enough to
    run corpus-wide; it must return the identical ranking or the E6 tuning does not transfer.
    """
    flat, addresses = cells.flatten(corpus)
    query = "zeta potential of PS-COOH in seawater"
    expected = [addresses[n - 1] for n in selectors.select_bm25(flat, selectors.Query(text=query))]
    assert cells.index(corpus).ranking(query) == expected


def test_the_index_can_be_scoped_to_one_paper(corpus):
    hits = cells.index(corpus).search("zeta potential", k=10, pmcid="PMCBBB")
    assert hits
    assert {hit.pmcid for hit in hits} == {"PMCBBB"}


def test_the_index_returns_line_ids_that_resolve_in_the_paper(corpus):
    hits = cells.index(corpus).search("zeta potential", k=5)
    assert hits
    for hit in hits:
        assert lines.resolve_id(corpus.docs[hit.pmcid], hit.line_id) is not None


# -- cell B: one shot, top-k, no tools -------------------------------------------------------


def test_cell_b_delivers_exactly_the_bm25_top_k_and_nothing_else(corpus):
    """The temptation is to slip the evidence lines in so the baseline looks strong. This is
    the test that makes that show up as a failure rather than as a good result."""
    question = _question(
        K.a,
        "In PMCAAA, what zeta potential was reported for polystyrene?",
        scope=("PMCAAA",),
    )
    built = cells.build_b(question, corpus, k=2)
    hits = cells.index(corpus).search(question.text, k=2, pmcid="PMCAAA")
    assert len(hits) == 2
    assert built.line_ids == tuple(hit.line_id for hit in hits)


def test_cell_b_does_not_top_up_with_the_lines_the_records_were_read_from(corpus, doc_a):
    """The temptation, and the one that would invalidate the baseline if it were taken.

    `corpus` carries `evidence_line_ids` on every record, so a builder can "help" cell B by
    unioning them in. Then cell B is no longer retrieval, it is the answer key with retrieval
    stapled to it. The question here is chosen so the evidence line is NOT in the top hit, or
    the union would add nothing and this test would pass without testing anything.
    """
    question = _question(
        K.a, "How were the particles dispersed for measurement?", scope=("PMCAAA",)
    )
    built = cells.build_b(question, corpus, k=1)
    evidence = doc_a.lines[1].line_id
    assert (
        evidence not in cells.index(corpus).search(question.text, k=1, pmcid="PMCAAA")[0].line_id
    ), "fixture drifted: the evidence line is already the top hit"
    assert len(built.line_ids) == 1
    assert evidence not in built.line_ids


def test_cell_b_scopes_to_the_paper_the_question_names(corpus):
    question = _question(K.b, "What ionic strength was used in PMCAAA?", scope=("PMCAAA",))
    built = cells.build_b(question, corpus)
    assert built.line_ids
    for line_id in built.line_ids:
        assert lines.resolve_id(corpus.docs["PMCAAA"], line_id) is not None


def test_cell_b_searches_the_whole_corpus_when_the_question_names_no_paper(corpus, doc_b):
    question = _question(K.c, "papers reporting zeta potential for polyethylene")
    built = cells.build_b(question, corpus)
    assert set(built.line_ids) & {line.line_id for line in doc_b.lines}


def test_cell_b_prompt_prints_a_citable_number_next_to_every_line(corpus):
    question = _question(K.a, "In PMCAAA, what zeta potential was reported?", scope=("PMCAAA",))
    built = cells.build_b(question, corpus, k=2)
    assert "PMCAAA:L2" in built.prompt or "PMCAAA:L1" in built.prompt


def test_cell_b_never_hands_over_the_structured_table(corpus):
    question = _question(K.a, "In PMCAAA, what zeta potential was reported?", scope=("PMCAAA",))
    built = cells.build_b(question, corpus)
    assert built.row_ids == ()
    assert "conditions_complete" not in built.prompt
    assert "PMCAAA-r1" not in built.prompt


# -- cell D: static route, structured first, prose fallback ---------------------------------


def test_cell_d_answers_a_lookup_from_the_table(corpus):
    question = _question(
        K.a,
        "In PMCAAA, what zeta potential was reported for polystyrene, carboxylated in seawater?",
        scope=("PMCAAA",),
        material="polystyrene",
        medium_text="seawater",
        quantity="zeta_potential",
    )
    built = cells.build_d(question, corpus)
    assert built.route == "structured"
    assert "PMCAAA-r1" in built.row_ids


def test_cell_d_shows_the_absence_boolean_not_a_blank(corpus):
    """`ionic_strength_reported = False` is a positive statement. A blank is not."""
    question = _question(
        K.b,
        "What ionic strength was used in PMCAAA?",
        scope=("PMCAAA",),
        field="ionic_strength",
    )
    built = cells.build_d(question, corpus)
    assert built.route == "structured"
    assert "ionic_strength_reported" in built.prompt
    assert "False" in built.prompt


def test_cell_d_falls_back_to_prose_when_the_table_has_no_field_for_the_question(corpus):
    """C3 is a static *route*, not a table-only cell. Without the fallback, kind D would be
    engineered to lose and the grid would prove nothing."""
    question = _question(K.d, "Why does a protein corona change a measured zeta potential?")
    built = cells.build_d(question, corpus)
    assert built.route == "prose_fallback"
    assert built.line_ids
    assert built.line_ids == cells.build_b(question, corpus).line_ids


def test_cell_d_on_kind_e_carries_the_verdict_and_its_blockers(corpus):
    question = _question(
        K.a,
        "May PMCAAA-r1 be compared with PMCBBB-r1?",
        row_id_a="PMCAAA-r1",
        row_id_b="PMCBBB-r1",
    )
    built = cells.build_d_comparability(question, corpus, "PMCAAA-r1", "PMCBBB-r1")
    assert "not_comparable" in built.prompt
    assert "ionic_strength_unreported" in built.prompt


# -- cells C and E: the tool contract --------------------------------------------------------


def test_cell_c_offers_prose_tools_and_withholds_the_knowledge_base(corpus):
    session = cells.session_c(_question(K.c, "papers reporting PS zeta between 100 and 200 mM"))
    names = {tool.name for tool in session.tools}
    assert "search_lines" in names
    assert names & {tool.name for tool in cells.TOOLS_KB} == set()


def test_cell_e_offers_both_tool_sets(corpus):
    session = cells.session_e(_question(K.c, "papers reporting PS zeta between 100 and 200 mM"))
    names = {tool.name for tool in session.tools}
    assert len(cells.TOOLS_PROSE) >= 3 and len(cells.TOOLS_KB) >= 3
    assert {tool.name for tool in cells.TOOLS_PROSE} <= names
    assert {tool.name for tool in cells.TOOLS_KB} <= names


def test_a_withheld_tool_cannot_be_called_from_cell_c(corpus):
    session = cells.session_c(_question(K.c, "papers reporting PS zeta"))
    result = cells.dispatch(session, corpus, cells.ToolCall("query_rows", {"material": "PS"}))
    assert result.error
    assert "query_rows" in result.text


def test_search_lines_is_the_same_retrieval_cell_b_gets(corpus):
    question = _question(K.c, "zeta potential of PS-COOH in seawater")
    session = cells.session_c(question)
    result = cells.dispatch(
        session, corpus, cells.ToolCall("search_lines", {"query": question.text, "k": 3})
    )
    expected = tuple(hit.line_id for hit in cells.index(corpus).search(question.text, k=3))
    assert expected
    assert result.line_ids == expected


def test_query_rows_filters_the_table_the_way_kind_c_ground_truth_does(corpus):
    session = cells.session_e(_question(K.c, "polyethylene zeta between 5 and 20 mM"))
    result = cells.dispatch(
        session,
        corpus,
        cells.ToolCall(
            "query_rows",
            {"material": "polyethylene", "ionic_strength_min": 5, "ionic_strength_max": 20},
        ),
    )
    assert result.row_ids == ("PMCBBB-r1",)


def test_every_tool_result_reports_what_it_cost(corpus):
    session = cells.session_e(_question(K.c, "zeta"))
    result = cells.dispatch(session, corpus, cells.ToolCall("search_lines", {"query": "zeta"}))
    assert result.tokens > 0
    assert result.tokens == cells.approx_tokens(result.text)


def test_an_unknown_tool_is_an_error_not_an_exception(corpus):
    session = cells.session_e(_question(K.c, "zeta"))
    result = cells.dispatch(session, corpus, cells.ToolCall("rm_rf", {}))
    assert result.error


def test_dispatch_is_deterministic(corpus):
    session = cells.session_e(_question(K.c, "zeta"))
    call = cells.ToolCall("search_lines", {"query": "zeta potential", "k": 2})
    assert cells.dispatch(session, corpus, call) == cells.dispatch(session, corpus, call)


# -- fairness: the instructions are the same in every cell -----------------------------------


@pytest.mark.parametrize("kind", [K.a, K.b, K.c, K.d])
def test_every_cell_is_given_the_same_rules_and_the_same_output_contract(corpus, kind):
    question = _question(kind, "In PMCAAA, what zeta potential was reported?", scope=("PMCAAA",))
    prompts = [
        cells.build_b(question, corpus).prompt,
        cells.build_d(question, corpus).prompt,
        cells.session_c(question).prompt,
        cells.session_e(question).prompt,
    ]
    rules, output = cells.rules_block(kind), cells.answer_contract(kind)
    assert len(rules) > 50 and len(output) > 20
    for prompt in prompts:
        assert rules in prompt
        assert output in prompt


def test_the_rules_tell_every_cell_that_not_reported_is_an_allowed_answer(corpus):
    assert "not reported" in cells.rules_block(K.b).lower()


# -- the test that would invalidate the whole evaluation if it were missing -------------------


SENTINEL = "-99999.5"


@pytest.mark.parametrize("kind", [K.a, K.b, K.c, K.d])
def test_no_cell_leaks_the_answer_key_into_its_prompt(corpus, kind):
    """A synthetic record whose answer is a string printed nowhere in the corpus. If any cell
    prints it, that cell is measuring the model's ability to copy from its own prompt."""
    record = {column: "" for column in qs.FIELDNAMES[kind]}
    record.update(
        qid=f"{kind.value}-leak",
        question="In PMCAAA, what zeta potential was reported for polystyrene in seawater?",
        pmcid="PMCAAA",
        source="synthetic",
    )
    for column in qs.ANSWER_COLUMNS & set(qs.FIELDNAMES[kind]):
        record[column] = SENTINEL
    question = qs.question_from_record(record)
    assert question.text
    built = [
        cells.build_b(question, corpus).prompt,
        cells.build_d(question, corpus).prompt,
        cells.session_c(question).prompt,
        cells.session_e(question).prompt,
    ]
    for prompt in built:
        assert len(prompt) > 100
        assert SENTINEL not in prompt


def test_nothing_in_here_calls_a_model_or_a_clock():
    with open(cells.__file__, encoding="utf-8") as handle:
        text = handle.read()
    for forbidden in ("openai", "httpx", "datetime.now", "random.random()"):
        assert forbidden not in text


# -- kind E runs through the same harness rather than a second one --------------------------


def _kind_e_record():
    return {
        "stratum": "same_paper",
        "row_id_a": "PMCAAA-r1",
        "row_id_b": "PMCBBB-r1",
        "pmcid_a": "PMCAAA",
        "pmcid_b": "PMCBBB",
        "same_paper": "False",
        "verdict": "not_comparable",
        "n_blockers": "3",
        "blockers": "functionalisation_unreported;ionic_strength_unreported;pH_unreported",
        "blocker_kinds": "unreported;unreported;unreported",
        "question": "May PMCAAA-r1 be compared with PMCBBB-r1, and what blocks it?",
    }


def test_a_kind_e_pair_becomes_a_question_carrying_no_verdict():
    question = qs.question_from_record(_kind_e_record())
    assert question.kind is K.e
    assert question.scope == ("PMCAAA", "PMCBBB")
    rendered = f"{question.text}|{sorted(question.target)}"
    assert "not_comparable" not in rendered
    assert "unreported" not in rendered


def test_cell_d_routes_a_kind_e_question_to_the_verdict_without_being_told_to(corpus):
    question = qs.question_from_record(_kind_e_record())
    built = cells.build_d(question, corpus)
    assert built.route == "structured"
    assert "comparability_verdict=not_comparable" in built.prompt
    assert built.row_ids == ("PMCAAA-r1", "PMCBBB-r1")


def test_kind_e_gets_its_own_answer_contract(corpus):
    contract = cells.answer_contract(K.e)
    assert "conditionally_comparable" in contract
    assert contract in cells.session_e(qs.question_from_record(_kind_e_record())).prompt


def test_the_kind_e_contract_names_every_field_a_blocker_can_be(corpus):
    """Cells B and C read prose and never see the key's field names. Without the vocabulary in
    the contract they could only lose on blockers, and the grid would be rigged."""
    contract = cells.answer_contract(K.e)
    for field in comparability.BLOCKER_FIELDS:
        assert field in contract


def test_cell_b_searches_every_paper_a_question_names_not_only_the_first(corpus, doc_a, doc_b):
    """A kind E question names two papers. Retrieving from one of them is not a weak baseline,
    it is a baseline that cannot answer the question at all."""
    question = _question(
        K.e,
        "May the zeta potential in PMCAAA be compared with the one in PMCBBB?",
        scope=("PMCAAA", "PMCBBB"),
    )
    built = cells.build_b(question, corpus)
    delivered = set(built.line_ids)
    assert delivered & {line.line_id for line in doc_a.lines}
    assert delivered & {line.line_id for line in doc_b.lines}
