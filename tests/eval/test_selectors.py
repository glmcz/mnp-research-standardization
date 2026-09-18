"""The selector bake-off: does knowing the question help you pick the lines that answer it?

Every row of `out/tables/d1_zeta_table.csv` carries the ids of the lines its evidence was
read from, so "which lines answer this question" has 1 890 answers already on disk. These
tests pin the machinery that scores a selector against them: the tokeniser, the four rivals
and the floor, the metrics, and — the one that matters most — that the incumbent is the real
`jats.extraction_text` budget loop and not a flattering imitation of it.
"""

import pytest

from mnp.corpus import jats, lines
from mnp.eval import selectors


def _doc(*pieces: tuple[str, str, list[str]]) -> lines.LinedDoc:
    """(path, header, texts) -> a LinedDoc built the way `lines.build_lines` builds one."""
    rows: list[lines.Line] = []
    spans: list[lines.SectionSpan] = []
    for path, header, texts in pieces:
        start = len(rows)
        for ordinal, text in enumerate(texts):
            rows.append(
                lines.Line(len(rows) + 1, text, path, ordinal, lines.line_id(path, ordinal, text))
            )
        spans.append(lines.SectionSpan(path, header, start, len(rows)))
    return lines.LinedDoc(pmcid="PMCTEST", lines=tuple(rows), sections=tuple(spans))


def _ids(doc: lines.LinedDoc, *numbers: int) -> frozenset[str]:
    return frozenset(doc.lines[n - 1].line_id for n in numbers)


TINY = _doc(
    ("methods", "== Methods", ["Particles were dispersed in ultrapure water."]),
    (
        "extra:Zeta",
        "== Zeta",
        [
            "The zeta potential of PS-COOH was -34.2 mV in seawater.",
            "Water water water water water water water water water water.",
        ],
    ),
    ("context:1", "== Context 1", ["Measurements used a Zetasizer Nano ZS."]),
)


# -- tokenisation --------------------------------------------------------------


def test_tokenise_keeps_a_signed_decimal_as_one_term():
    assert selectors.tokenise("Zeta was -34.2 mV") == ("zeta", "was", "-34.2", "mv")


def test_tokenise_folds_a_publisher_minus_to_ascii_so_a_query_number_can_match():
    assert "-34.2" in selectors.tokenise("zeta −34.2 mV")


# -- every selector must be a ranking of the whole document --------------------


@pytest.mark.parametrize("name", sorted(selectors.SELECTORS))
def test_every_selector_ranks_every_line_exactly_once(name):
    ranked = selectors.SELECTORS[name](TINY, selectors.value_query({"material": "polystyrene"}))
    assert sorted(ranked) == [line.n for line in TINY.lines]


# -- the incumbent is the real thing -------------------------------------------


def test_incumbent_reproduces_extraction_text_verbatim_under_its_real_budget(fixtures_dir):
    article = jats.parse((fixtures_dir / "PMC5090179.xml").read_bytes())
    doc = lines.build_lines(article)
    for budget in (200, 500, 1_000, 2_000, 4_000, 12_000, None):
        assert selectors.incumbent_text(doc, budget) == jats.extraction_text(
            article, max_tokens=budget
        ), budget


def test_incumbent_puts_keyword_windows_before_methods_the_way_the_budget_loop_does():
    ranked = selectors.select_incumbent(TINY, selectors.label_query({}))
    assert ranked[0] == 4  # == Context 1
    assert ranked[-1] == 1  # == Methods


def test_incumbent_is_query_blind():
    a = selectors.select_incumbent(TINY, selectors.value_query({"material": "polystyrene"}))
    b = selectors.select_incumbent(TINY, selectors.value_query({"instrument": "Zetasizer"}))
    assert a == b


# -- bm25 ----------------------------------------------------------------------


def test_bm25_puts_the_line_carrying_the_query_terms_first():
    query = selectors.Query(text="zeta potential PS-COOH seawater -34.2 mV")
    assert selectors.select_bm25(TINY, query)[0] == 2


def test_bm25_prefers_the_rare_term_over_the_common_one():
    doc = _doc(
        ("methods", "== Methods", ["water was used", "water and a zetasizer", "water again"]),
    )
    ranked = selectors.select_bm25(doc, selectors.Query(text="water zetasizer"))
    assert ranked[0] == 2


def test_bm25_saturates_a_repeated_term_rather_than_letting_it_win_outright():
    doc = _doc(
        (
            "methods",
            "== Methods",
            ["zeta zeta zeta zeta zeta zeta zeta zeta zeta zeta", "zeta in seawater"],
        ),
    )
    ranked = selectors.select_bm25(doc, selectors.Query(text="zeta seawater"))
    assert ranked[0] == 2


# -- structured ----------------------------------------------------------------


def test_structured_ranks_the_line_printing_the_value_above_one_that_only_shares_words():
    doc = _doc(
        (
            "methods",
            "== Methods",
            [
                "Polystyrene particles were studied in seawater.",
                "The value was -34.2 mV.",
            ],
        ),
    )
    query = selectors.value_query(
        {"material": "polystyrene", "medium_text": "seawater", "value": -34.2, "unit": "mV"}
    )
    assert selectors.select_structured(doc, query)[0] == 2


def test_structured_matches_a_number_printed_with_a_publisher_minus_sign():
    doc = _doc(("methods", "== Methods", ["nothing here", "zeta −34.2 mV"]))
    query = selectors.value_query({"value": -34.2, "unit": "mV", "quantity": "zeta_potential"})
    assert selectors.select_structured(doc, query)[0] == 2


# -- the floor -----------------------------------------------------------------


def test_random_is_reproducible_for_a_seed_and_different_across_seeds():
    q = selectors.label_query({})
    assert selectors.select_random(TINY, q, seed=7) == selectors.select_random(TINY, q, seed=7)
    assert selectors.select_random(TINY, q, seed=7) != selectors.select_random(TINY, q, seed=8)


# -- metrics -------------------------------------------------------------------


def test_recall_at_k_demands_every_evidence_line_not_merely_one():
    evidence = _ids(TINY, 2, 4)
    assert selectors.recall_at_k(TINY, (2, 1, 3, 4), evidence, k=2) == 0.0
    assert selectors.recall_at_k(TINY, (2, 4, 1, 3), evidence, k=2) == 1.0


def test_partial_recall_counts_the_lines_the_strict_metric_throws_away():
    evidence = _ids(TINY, 2, 4)
    assert selectors.partial_recall_at_k(TINY, (2, 1, 3, 4), evidence, k=2) == 0.5


def test_tokens_at_k_counts_only_what_was_delivered():
    one = selectors.tokens_at_k(TINY, (1, 2, 3, 4), k=1)
    assert one == jats.approx_tokens(TINY.lines[0].text) + 1
    assert selectors.tokens_at_k(TINY, (1, 2, 3, 4), k=99) == sum(
        jats.approx_tokens(x.text) + 1 for x in TINY.lines
    )


def test_a_selector_that_returns_everything_does_not_win_on_recall_per_token():
    cases = (
        selectors.Case(
            pmcid="PMCTEST",
            row_id="r1",
            doc=TINY,
            evidence=_ids(TINY, 2),
            query=selectors.Query(text="zeta potential seawater"),
        ),
    )
    sharp = selectors.score(cases, "bm25", selectors.select_bm25, ks=(1,))[0]
    blunt = selectors.score(cases, "whole", selectors.select_whole, ks=(99,))[0]
    assert sharp.recall == blunt.recall == 1.0
    assert sharp.recall_per_1k_tokens > blunt.recall_per_1k_tokens


def test_score_separates_a_selector_that_ranks_evidence_first_from_one_that_ranks_it_last():
    cases = (
        selectors.Case(
            pmcid="PMCTEST",
            row_id="r1",
            doc=TINY,
            evidence=_ids(TINY, 2),
            query=selectors.Query(text="zeta potential PS-COOH seawater -34.2"),
        ),
    )
    good = selectors.score(cases, "bm25", selectors.select_bm25, ks=(1,))[0]
    bad = selectors.score(
        cases, "reversed", lambda d, q: tuple(reversed(selectors.select_bm25(d, q))), ks=(1,)
    )[0]
    assert good.recall == 1.0
    assert bad.recall == 0.0


# -- the confound --------------------------------------------------------------


def test_a_value_query_leaks_its_terms_into_the_target_line():
    query = selectors.value_query(
        {"material": "PS-COOH", "value": -34.2, "unit": "mV", "medium_text": "seawater"}
    )
    case = selectors.Case(
        pmcid="PMCTEST", row_id="r1", doc=TINY, evidence=_ids(TINY, 2), query=query
    )
    target, elsewhere = selectors.leakage(case, seed=1)
    assert target > elsewhere


def test_the_label_query_carries_no_value_from_the_row():
    row = {
        "material": "polystyrene",
        "functionalisation": "carboxylated",
        "value": -34.2,
        "unit": "mV",
        "medium_text": "artificial seawater",
        "instrument": "Zetasizer Nano ZS",
        "quantity": "zeta_potential",
    }
    text = selectors.label_query(row).text.lower()
    for leaked in ("polystyrene", "carboxylated", "-34.2", "artificial", "zetasizer", "nano"):
        assert leaked not in text, leaked


def test_the_label_query_is_the_same_question_for_every_row_of_a_quantity():
    a = selectors.label_query({"quantity": "zeta_potential", "material": "polystyrene"})
    b = selectors.label_query({"quantity": "zeta_potential", "material": "PET"})
    assert a == b
