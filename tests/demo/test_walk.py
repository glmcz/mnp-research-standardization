"""The standardisation walk: one `Step` per condition, five per row, in a fixed order.

G1 (`docs/2026-09-21-cile-a-otazky-pro-vedce.md`) is the running example: PMC10141840's three
rows share particle, pH, temperature and instrument, and differ only in medium — and every one
of the three fails "ionic strength" for a *different* reason. That is the test that matters
most here: three `unreported` verdicts, three distinct causes, never the same sentence twice.
"""

from __future__ import annotations

import pandas as pd
import pytest

from mnp import config
from mnp.corpus.lines import LinedDoc
from mnp.demo import walk
from mnp.eval import cells


@pytest.fixture(scope="module")
def table() -> pd.DataFrame:
    return pd.read_csv(config.OUT_TABLES / "d1_zeta_table.csv")


@pytest.fixture(scope="module")
def corpus() -> cells.Corpus:
    return cells.load_corpus(["PMC10141840", "PMC12312160", "PMC13520334"])


def _row(table: pd.DataFrame, row_id: str) -> dict:
    hit = table[table["row_id"] == row_id]
    assert not hit.empty, row_id
    return hit.to_dict(orient="records")[0]


def test_step_order_is_fixed(table, corpus):
    row = _row(table, "PMC10141840-r1")
    steps = walk.walk_row(row, corpus.docs["PMC10141840"])
    assert [s.condition for s in steps] == [
        "medium",
        "ionic_strength",
        "pH",
        "temperature",
        "instrument",
    ]


def test_medium_ph_temperature_instrument_reported_for_pmc10141840_r1(table, corpus):
    row = _row(table, "PMC10141840-r1")
    by = {s.condition: s for s in walk.walk_row(row, corpus.docs["PMC10141840"])}
    assert by["medium"].verdict == "reported"
    assert by["pH"].verdict == "reported"
    assert by["temperature"].verdict == "reported"
    assert by["instrument"].verdict == "reported"


def test_g1_three_rows_three_distinct_unreported_reasons(table, corpus):
    doc = corpus.docs["PMC10141840"]
    reasons = {}
    for row_id in ("PMC10141840-r1", "PMC10141840-r2", "PMC10141840-r3"):
        row = _row(table, row_id)
        ionic = next(s for s in walk.walk_row(row, doc) if s.condition == "ionic_strength")
        assert ionic.verdict == "unreported"
        reasons[row_id] = ionic.reason
    assert len(set(reasons.values())) == 3, reasons
    assert "conductiv" in reasons["PMC10141840-r1"].lower()
    assert "buffer" in reasons["PMC10141840-r2"].lower()
    assert "culture" in reasons["PMC10141840-r3"].lower()


def test_derived_row_pmc12312160(table, corpus):
    row = _row(table, "PMC12312160-r1")
    ionic = next(
        s for s in walk.walk_row(row, corpus.docs["PMC12312160"]) if s.condition == "ionic_strength"
    )
    assert ionic.verdict == "derived"
    assert "composition" in ionic.reason.lower()
    assert "1 mM" in ionic.reason  # the row's own NaCl concentration, not the HEPES buffer's


def test_nominal_temperature_pmc13520334(table, corpus):
    row = _row(table, "PMC13520334-r1")
    temp = next(
        s for s in walk.walk_row(row, corpus.docs["PMC13520334"]) if s.condition == "temperature"
    )
    assert temp.verdict == "nominal"
    assert "room temperature" in temp.reason.lower()


def test_citations_are_pmcid_colon_l_line_numbers(table, corpus):
    row = _row(table, "PMC10141840-r1")
    steps = walk.walk_row(row, corpus.docs["PMC10141840"])
    seen_any = False
    for step in steps:
        for cite in step.citations:
            seen_any = True
            assert cite.startswith("PMC10141840:L")
            assert cite.split(":L")[1].isdigit()
    assert seen_any


def test_unreported_synthetic_rows_every_branch():
    """Pins the branches G1's three real rows don't reach: nothing printed, and DI/pure water."""
    empty_doc = LinedDoc(pmcid="PMCX", lines=(), sections=())
    base = {
        "pmcid": "PMCX",
        "row_id": "PMCX-r1",
        "medium_reported": False,
        "medium_text": "",
        "medium_class": "unreported",
        "ionic_strength_reported": False,
        "ionic_strength_source": "unreported",
        "ionic_strength_mM": None,
        "pH_reported": False,
        "pH": None,
        "pH_text": "",
        "temperature_reported": False,
        "temperature_C": None,
        "temperature_qualifier": "",
        "instrument_reported": False,
        "instrument": "",
        "flags": "",
        "evidence_line_ids": "",
    }
    by = {s.condition: s for s in walk.walk_row(base, empty_doc)}
    assert by["medium"].verdict == "unreported"
    assert by["pH"].verdict == "unreported"
    assert by["instrument"].verdict == "unreported"
    assert by["temperature"].verdict == "unreported"
    assert by["ionic_strength"].verdict == "unreported"
    assert "nothing" in by["ionic_strength"].reason.lower()

    di = dict(base, medium_reported=True, medium_text="deionised water", medium_class="DI_water")
    di_by = {s.condition: s for s in walk.walk_row(di, empty_doc)}
    assert di_by["ionic_strength"].verdict == "unreported"
    assert "never imputed" in di_by["ionic_strength"].reason.lower()


def test_reported_ph_range_and_reported_ionic_strength_number():
    empty_doc = LinedDoc(pmcid="PMCX", lines=(), sections=())
    row = {
        "pmcid": "PMCX",
        "row_id": "PMCX-r1",
        "medium_reported": True,
        "medium_text": "10 mM NaCl",
        "medium_class": "salt_solution",
        "ionic_strength_reported": True,
        "ionic_strength_source": "reported",
        "ionic_strength_mM": 10.0,
        "pH_reported": True,
        "pH": None,
        "pH_text": "between 6.8 and 7.2",
        "temperature_reported": True,
        "temperature_C": 25.0,
        "temperature_qualifier": "",
        "instrument_reported": True,
        "instrument": "Zetasizer Nano ZS",
        "flags": "",
        "evidence_line_ids": "",
    }
    by = {s.condition: s for s in walk.walk_row(row, empty_doc)}
    assert by["ionic_strength"].verdict == "reported"
    assert by["pH"].verdict == "reported"
    assert "6.8" in by["pH"].reason and "7.2" in by["pH"].reason
    assert by["temperature"].verdict == "reported"
