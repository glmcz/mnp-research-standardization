"""A two-paper synthetic corpus for the grid tests.

Small enough that every ranking, filter and verdict can be written out by hand, and shaped so
the two things the grid is about are both present: a row whose ionic strength was **not**
reported (PMCAAA) and one whose was (PMCBBB).
"""

import pandas as pd
import pytest

from mnp.corpus import lines
from mnp.eval import cells


def build_doc(pmcid: str, *pieces: tuple[str, str, list[str]]) -> lines.LinedDoc:
    rows: list[lines.Line] = []
    spans: list[lines.SectionSpan] = []
    for path, header, texts in pieces:
        start = len(rows)
        for ordinal, text in enumerate(texts):
            rows.append(
                lines.Line(len(rows) + 1, text, path, ordinal, lines.line_id(path, ordinal, text))
            )
        spans.append(lines.SectionSpan(path, header, start, len(rows)))
    return lines.LinedDoc(pmcid=pmcid, lines=tuple(rows), sections=tuple(spans))


DOC_A = build_doc(
    "PMCAAA",
    ("methods", "== Methods", ["Particles were dispersed in ultrapure water at 25 C."]),
    (
        "extra:Zeta",
        "== Zeta",
        [
            "The zeta potential of PS-COOH was -34.2 mV in seawater.",
            "Aggregation followed, because the electrical double layer was screened.",
        ],
    ),
)

DOC_B = build_doc(
    "PMCBBB",
    ("methods", "== Methods", ["Polyethylene was suspended in 10 mM NaCl."]),
    ("extra:Zeta", "== Zeta", ["A zeta potential of -12.0 mV was recorded for PE."]),
)

_COMMON = {
    "doi": None,
    "year": 2024,
    "journal": "J",
    "supplier": None,
    "sd": None,
    "n": None,
    "instrument": "Zetasizer Nano ZS",
    "medium_reported": True,
    "temperature_reported": True,
    "instrument_reported": True,
    "medium_matches_exposure": None,
    "evidence_quote": "",
    "evidence_location": "",
    "evidence_verified": True,
    "flags": "",
    "model": "test",
    "prompt_sha256": "",
    "temperature_C": 25.0,
    "temperature_qualifier": None,
    "quantity": "zeta_potential",
    "unit": "mV",
}

TABLE = pd.DataFrame(
    [
        {
            **_COMMON,
            "pmcid": "PMCAAA",
            "row_id": "PMCAAA-r1",
            "material": "polystyrene",
            "functionalisation": "carboxylated",
            "particle_name": "PS-COOH",
            "size_measured_nm": 100.0,
            "size_nominal_nm": 100.0,
            "value": -34.2,
            "value_text": "-34.2",
            "medium_text": "seawater",
            "medium_class": "environmental_water",
            "ionic_strength_mM": None,
            "ionic_strength_source": "unreported",
            "pH": None,
            "pH_text": None,
            "ionic_strength_reported": False,
            "pH_reported": False,
            "conditions_complete": False,
            "evidence_line_ids": DOC_A.lines[1].line_id,
        },
        {
            **_COMMON,
            "pmcid": "PMCBBB",
            "row_id": "PMCBBB-r1",
            "material": "polyethylene",
            "functionalisation": None,
            "particle_name": "PE",
            "size_measured_nm": 200.0,
            "size_nominal_nm": None,
            "value": -12.0,
            "value_text": "-12.0",
            "medium_text": "10 mM NaCl",
            "medium_class": "salt_solution",
            "ionic_strength_mM": 10.0,
            "ionic_strength_source": "reported",
            "pH": 7.0,
            "pH_text": None,
            "ionic_strength_reported": True,
            "pH_reported": True,
            "conditions_complete": True,
            "evidence_line_ids": DOC_B.lines[1].line_id,
        },
    ]
)


@pytest.fixture
def doc_a():
    return DOC_A


@pytest.fixture
def doc_b():
    return DOC_B


@pytest.fixture
def corpus():
    return cells.Corpus(docs={"PMCAAA": DOC_A, "PMCBBB": DOC_B}, table=TABLE)
