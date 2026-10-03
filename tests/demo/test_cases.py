"""The demo cases: each pins a paper and a check that proves it still shows its mode.

`cases.verify` is what a pinned paper has to survive if the published table changes under it.
These tests run every check against the real `d1_zeta_table.csv`/corpus, and pin mutation
cases (`test_verify_can_say_no`, the case 01/11/14 mutations) so a check that always returns
`True` cannot pass silently.
"""

from __future__ import annotations

import dataclasses
import re

import pandas as pd
import pytest

from mnp import config
from mnp.demo import cases, harmonise
from mnp.eval import cells
from mnp.eval import comparability as comp

_UNIQUENESS_RE = re.compile(r"\bthe one paper\b|\bthe only paper\b", re.IGNORECASE)

#: The only cross-paper comparable pair on the 2026-10-03 table (Martin, case 14).
CASE_14_PAIR = ("PMC10260929-r1", "PMC13298883-r1")


@pytest.fixture(scope="module")
def table() -> pd.DataFrame:
    return pd.read_csv(config.OUT_TABLES / "d1_zeta_table.csv")


@pytest.fixture(scope="module")
def corpus(table: pd.DataFrame) -> cells.Corpus:
    return cells.load_corpus([case.pmcid for case in cases.CASES])


def _case(nn: str) -> cases.Case:
    found = [case for case in cases.CASES if case.nn == nn]
    assert found, f"no case {nn}"
    return found[0]


def _census_pairs(table: pd.DataFrame) -> set[tuple[str, str]]:
    rows = [comp.ZetaRow.from_mapping(r) for r in table.to_dict(orient="records")]
    return {(spec.a.row_id, spec.b.row_id) for spec in comp.comparable_census(rows)}


def test_fourteen_cases():
    assert len(cases.CASES) == 14


def test_every_case_has_a_unique_nn_slug_and_pmcid():
    n = len(cases.CASES)
    assert len({case.nn for case in cases.CASES}) == n
    assert len({case.slug for case in cases.CASES}) == n
    papers = [pmcid for case in cases.CASES for pmcid in case.pmcids]
    assert len(set(papers)) == len(papers), "a paper belongs to two cases"
    assert [case.nn for case in cases.CASES] == [f"{i:02d}" for i in range(1, n + 1)]


def test_every_nn_is_a_zero_padded_two_digit_string():
    for case in cases.CASES:
        assert len(case.nn) == 2 and case.nn.isdigit()


def test_every_why_is_two_to_three_sentences():
    for case in cases.CASES:
        sentences = [s for s in case.why.split(". ") if s.strip()]
        assert 2 <= len(sentences) <= 3, (case.nn, case.why)


@pytest.mark.parametrize("case", cases.CASES, ids=lambda c: f"{c.nn}-{c.slug}")
def test_every_pinned_case_passes_its_own_check(case, table, corpus):
    reason = cases.verify(case, table, corpus)
    assert reason is None, reason


def test_verify_can_say_no_not_only_yes():
    """A check that can never fail is not a check. Feed case 13's check an empty corpus."""
    case = next(c for c in cases.CASES if c.nn == "13")
    empty_corpus = cells.Corpus(docs={}, table=pd.read_csv(config.OUT_TABLES / "d1_zeta_table.csv"))
    reason = cases.verify(case, empty_corpus.table, empty_corpus)
    assert reason is not None


def test_no_case_why_claims_uniqueness_unless_only_one_paper_qualifies(table):
    """Case 01 used to say it was "the one paper" reporting all five conditions on more than one
    row. It is not: count papers with more than one `conditions_complete` row in the live table,
    and a `why` may only claim uniqueness ("the one paper", "the only paper") when that count is
    exactly 1. This must fail red against the old case 01 text before the fix."""
    multi_conditioned_papers = (table.groupby("pmcid")["conditions_complete"].sum() > 1).sum()
    for case in cases.CASES:
        if _UNIQUENESS_RE.search(case.why):
            assert multi_conditioned_papers == 1, (
                f"case {case.nn} claims uniqueness but {multi_conditioned_papers} papers have "
                "more than one conditions_complete row"
            )


def test_case_04_derived_check_fails_on_a_paper_with_no_derived_row(table, corpus):
    """Mutation: point case 04's check at case 05's paper, which never derives an ionic strength."""
    case_04 = next(c for c in cases.CASES if c.nn == "04")
    case_05 = next(c for c in cases.CASES if c.nn == "05")
    mutated = cases.Case(
        nn=case_04.nn,
        slug=case_04.slug,
        pmcid=case_05.pmcid,
        mode=case_04.mode,
        why=case_04.why,
        check=case_04.check,
    )
    reason = cases.verify(mutated, table, corpus)
    assert reason is not None


# -- case 01: the pair has to sit inside the paper ---------------------------------------------


def test_case_01_pin_holds_a_comparable_pair_inside_it(table, corpus):
    """Martin, 2026-10-03: PMC11099890 lost its pairs once R3 cleared "5 mM phosphate" (a buffer
    concentration) as an ionic strength. PMC12955872 has one: its PEGylated 20 and 40 nm PS-COOH."""
    case = _case("01")
    prefix = f"{case.pmcid}-r"
    inside = [
        (a, b) for a, b in _census_pairs(table) if a.startswith(prefix) and b.startswith(prefix)
    ]
    assert inside, f"{case.pmcid} has no comparable pair inside it"
    assert cases.verify(case, table, corpus) is None


def test_case_01_check_needs_both_rows_of_the_pair_in_its_paper(table, corpus):
    """A cross-paper pair is case 14's mode. PMC10260929 holds one side of the only cross-paper
    comparable pair and no pair inside itself, so case 01's check pointed at it must say no."""
    mutated = dataclasses.replace(_case("01"), pmcid="PMC10260929")
    assert cases.verify(mutated, table, corpus) is not None


# -- case 11: what the paper prints, not a reader's medium_class ---------------------------------


def _case_11_rows(table: pd.DataFrame) -> pd.DataFrame:
    return table[table["pmcid"] == _case("11").pmcid].copy()


def test_case_11_check_passes_on_the_medium_text_whatever_the_class(table, corpus):
    """medium_class is a reader's label; the re-read filed these industrial effluents under
    `other`. The check must hold on the paper's own words alone."""
    rows = _case_11_rows(table)
    rows["medium_class"] = "other"
    assert cases.verify(_case("11"), rows, corpus) is None


def test_case_11_check_fails_when_the_text_names_no_environmental_water(table, corpus):
    """Mutate the text and keep the old label: the label alone must not carry the check."""
    rows = _case_11_rows(table)
    rows["medium_class"] = "environmental_water"
    rows["medium_text"] = "deionised water"
    assert cases.verify(_case("11"), rows, corpus) is not None


@pytest.mark.parametrize(
    "text, names_one",
    [
        ("textile industry effluent sample, before in-house WWTP treatment", True),
        ("Lake Taihu water", True),
        ("filtered seawater", True),
        ("riverine humic acid in 10 mM NaCl", False),
        ("PS flakes in DI water", False),
    ],
)
def test_environmental_water_is_matched_as_whole_words(text, names_one):
    assert bool(cases.ENVIRONMENTAL_WATER_RE.search(text)) is names_one


# -- case 14: comparable on all five conditions, 34 mV apart, one lab ---------------------------


def test_case_14_pins_the_cross_paper_comparable_pair(table, corpus):
    case = _case("14")
    assert case.pair == CASE_14_PAIR
    assert set(case.pmcids) == {"PMC10260929", "PMC13298883"}
    assert CASE_14_PAIR in _census_pairs(table)
    values = table.set_index("row_id").loc[list(CASE_14_PAIR), "value"]
    assert abs(values.iloc[0] - values.iloc[1]) >= 20.0
    assert cases.verify(case, table, corpus) is None


@pytest.mark.parametrize(
    "column, value",
    [("value", -40.0), ("pH", 6.0)],
    ids=["gap-closes-to-8.7-mV", "pH-no-longer-matches"],
)
def test_case_14_check_fails_when_the_pair_closes_or_stops_being_comparable(
    table, corpus, column, value
):
    mutated = table.copy()
    mutated.loc[mutated["row_id"] == CASE_14_PAIR[1], column] = value
    assert cases.verify(_case("14"), mutated, corpus) is not None


def test_case_14_check_fails_on_a_paper_outside_its_pair(table, corpus):
    mutated = dataclasses.replace(_case("14"), pmcid="PMC12955872")
    assert cases.verify(mutated, table, corpus) is not None


def test_case_14_gap_survives_either_conversion_limit(table):
    """Its `why` says the gap is not the conversion model's: neither paper names one, and with
    f_m left open between Hueckel and Smoluchowski on both rows the intervals still do not meet."""
    case = _case("14")
    harmonised = {h.row_id: h for p in case.pmcids for h in harmonise.harmonise_paper(p, table)}
    a, b = (harmonised[row_id] for row_id in case.pair)
    assert None not in (a.low, a.high, b.low, b.high)
    assert a.high < b.low or b.high < a.low
