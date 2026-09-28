"""The thirteen demo cases: each pins a paper and a check that proves it still shows its mode.

`cases.verify` is what a pinned paper has to survive if the published table changes under it.
These tests run every check against the real `d1_zeta_table.csv`/corpus, and pin two mutation
cases (`test_verify_can_say_no`, `test_case_13_fails_without_its_paper`) so a check that always
returns `True` cannot pass silently.
"""

from __future__ import annotations

import pandas as pd
import pytest

from mnp import config
from mnp.demo import cases
from mnp.eval import cells


@pytest.fixture(scope="module")
def table() -> pd.DataFrame:
    return pd.read_csv(config.OUT_TABLES / "d1_zeta_table.csv")


@pytest.fixture(scope="module")
def corpus(table: pd.DataFrame) -> cells.Corpus:
    return cells.load_corpus([case.pmcid for case in cases.CASES])


def test_thirteen_cases():
    assert len(cases.CASES) == 13


def test_every_case_has_a_unique_nn_slug_and_pmcid():
    assert len({case.nn for case in cases.CASES}) == 13
    assert len({case.slug for case in cases.CASES}) == 13
    assert len({case.pmcid for case in cases.CASES}) == 13
    assert [case.nn for case in cases.CASES] == sorted(case.nn for case in cases.CASES)


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
