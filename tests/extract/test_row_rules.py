"""The two row rules Martin ratified on 2026-09-28, and the record they must leave alone.

R1: an ionic strength of exactly 0 mM is not a reported one ("no added electrolyte" is not a
zero). R2: a temperature the verifier flags `temperature_step_not_measurement` belongs to an
incubation or exposure step, never to the measurement. Both clear the value where a record
becomes a row; the record keeps what the model read.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from mnp import config
from mnp.eval import comparability as comp
from mnp.extract import zeta
from mnp.schema import models

STEP = "temperature_step_not_measurement"
ZERO = "ionic_strength_zero_not_reported"

# Every other condition reported, so `conditions_complete` is True until a rule clears one.
COMPLETE = {
    "medium_text": "DI water",
    "medium_class": models.MediumClass.DI_water,
    "ionic_strength_mM": 10.0,
    "ionic_strength_source": models.ValueSource.reported,
    "pH": 7.0,
    "temperature_C": 25.0,
    "instrument": "Zetasizer Nano ZS",
}


def _record(flags: list[str], **conditions) -> zeta.ExtractionRecord:
    m = models.SurfaceMeasurement(
        particle_name="PS",
        material="polystyrene",
        quantity=models.Quantity.zeta_potential,
        value=-30.0,
        unit=models.Unit.mV,
        conditions=models.MeasurementConditions(**{**COMPLETE, **conditions}),
        evidence=models.Evidence(quote="The zeta potential was -30.0 mV."),
    )
    return zeta.ExtractionRecord(
        pmcid="PMC1",
        doi=None,
        model="m",
        prompt_sha256="0" * 64,
        measurements=[m],
        row_flags=[list(flags)],
    )


def test_the_baseline_row_is_complete():
    row = _record([]).to_rows()[0]
    assert row["conditions_complete"] is True
    assert row["flags"] == ""


def test_zero_ionic_strength_is_unreported_and_flagged():
    row = _record([], ionic_strength_mM=0.0).to_rows()[0]
    assert row["ionic_strength_mM"] is None
    assert row["ionic_strength_source"] == "unreported"
    assert row["ionic_strength_reported"] is False
    assert row["conditions_complete"] is False
    assert ZERO in row["flags"].split(";")


def test_zero_rule_applies_whatever_the_source_claimed():
    row = _record(
        [], ionic_strength_mM=0.0, ionic_strength_source=models.ValueSource.inferred_from_named_salt
    ).to_rows()[0]
    assert row["ionic_strength_mM"] is None
    assert row["ionic_strength_source"] == "unreported"
    assert ZERO in row["flags"].split(";")


def test_a_small_nonzero_ionic_strength_stands():
    row = _record([], ionic_strength_mM=0.1).to_rows()[0]
    assert row["ionic_strength_mM"] == 0.1
    assert row["ionic_strength_reported"] is True
    assert row["conditions_complete"] is True
    assert ZERO not in row["flags"]


def test_step_flagged_temperature_is_cleared_and_the_flag_stays():
    row = _record([STEP], temperature_C=37.0).to_rows()[0]
    assert row["temperature_C"] is None
    assert row["temperature_qualifier"] is None
    assert row["temperature_reported"] is False
    assert row["conditions_complete"] is False
    assert row["flags"].split(";") == [STEP]


def test_step_rule_clears_a_qualifier_too():
    row = _record([STEP], temperature_C=37.0, temperature_qualifier="incubation").to_rows()[0]
    assert row["temperature_C"] is None
    assert row["temperature_qualifier"] is None
    assert row["temperature_reported"] is False


def test_an_unflagged_temperature_stands():
    row = _record(["temperature_not_in_evidence"], temperature_C=37.0).to_rows()[0]
    assert row["temperature_C"] == 37.0
    assert row["temperature_reported"] is True


def test_the_record_keeps_what_the_model_read():
    rec = _record([STEP], ionic_strength_mM=0.0, temperature_C=37.0)
    before = rec.to_json()
    rec.to_rows()
    assert rec.to_json() == before
    c = rec.measurements[0].conditions
    assert c.ionic_strength_mM == 0.0 and c.temperature_C == 37.0
    assert rec.row_flags == [[STEP]]


# -- the committed artefacts -------------------------------------------------------------------

TABLES = {
    "d1_zeta_table.csv": lambda: pd.read_csv(config.OUT_TABLES / "d1_zeta_table.csv"),
    "zeta_table.parquet": lambda: pd.read_parquet(config.DATA_PROCESSED / "zeta_table.parquet"),
}


@pytest.fixture(scope="module", params=sorted(TABLES))
def table(request) -> pd.DataFrame:
    return TABLES[request.param]()


def _flagged(table: pd.DataFrame, flag: str) -> pd.Series:
    return table["flags"].fillna("").str.split(";").map(lambda parts: flag in parts)


def test_no_committed_row_has_an_ionic_strength_of_zero(table):
    assert not (table["ionic_strength_mM"] == 0).any()


def test_no_step_flagged_committed_row_has_a_temperature(table):
    step = table[_flagged(table, STEP)]
    assert step["temperature_C"].isna().all()
    assert step["temperature_qualifier"].isna().all()
    assert not step["temperature_reported"].astype(bool).any()


def test_every_zero_flagged_row_is_unreported(table):
    zero = table[_flagged(table, ZERO)]
    assert zero["ionic_strength_mM"].isna().all()
    assert (zero["ionic_strength_source"] == "unreported").all()


def test_committed_flags_follow_from_the_committed_fields(table):
    """The five `*_reported` columns and `conditions_complete` recompute from the row's fields."""
    names = [
        "medium_reported",
        "ionic_strength_reported",
        "pH_reported",
        "temperature_reported",
        "instrument_reported",
        "conditions_complete",
    ]
    wrong = []
    for record in table.to_dict(orient="records"):
        c = comp.ZetaRow.from_mapping(record).conditions
        for name in names:
            if bool(record[name]) is not getattr(c, name):
                wrong.append((record["row_id"], name))
    assert wrong == []


def test_the_record_still_holds_what_the_rules_cleared():
    """Provenance: every zero and every step temperature is still in extractions.jsonl, one for
    one with the rows the rules cleared in the parquet table built from it."""
    zeros = steps = 0
    for line in (config.DATA_INTERIM / "extractions.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        for m, flags in zip(rec["measurements"], rec["row_flags"], strict=True):
            c = m["conditions"]
            zeros += c.get("ionic_strength_mM") == 0
            if STEP in flags:
                assert c.get("temperature_C") is not None
                steps += 1
    built = pd.read_parquet(config.DATA_PROCESSED / "zeta_table.parquet")
    assert zeros > 0 and steps > 0
    assert int(_flagged(built, ZERO).sum()) == zeros
    assert int(_flagged(built, STEP).sum()) == steps
