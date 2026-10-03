"""The row rules Martin ratified on 2026-09-28 and 29, and the record they must leave alone.

R1: an ionic strength of exactly 0 mM is not a reported one ("no added electrolyte" is not a
zero). R2: a temperature the verifier flags `temperature_step_not_measurement` belongs to an
incubation or exposure step, never to the measurement. R2b: a temperature the row's own quote
does not state, whose source prints it only for another step (the medium label "RPMI (stored at
37 ˚C for 24 h)", or a paper that gives it only for an incubation), is not the measurement's
either. All clear the value where a record becomes a row; the record keeps what the model read.
"""

from __future__ import annotations

import json
import re

import pandas as pd
import pytest

from mnp import config
from mnp.eval import comparability as comp
from mnp.extract import coerce, zeta
from mnp.schema import models

STEP = "temperature_step_not_measurement"
ZERO = "ionic_strength_zero_not_reported"
OTHER = "temperature_from_other_step"
STORED = "RPMI (stored at 37 ˚C for 24 h)"

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


def _record(
    flags: list[str], quote: str = "The zeta potential was -30.0 mV.", **conditions
) -> zeta.ExtractionRecord:
    m = models.SurfaceMeasurement(
        particle_name="PS",
        material="polystyrene",
        quantity=models.Quantity.zeta_potential,
        value=-30.0,
        unit=models.Unit.mV,
        conditions=models.MeasurementConditions(**{**COMPLETE, **conditions}),
        evidence=models.Evidence(quote=quote),
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


# -- R2b ---------------------------------------------------------------------------------------


def _cleared(row: dict) -> bool:
    return (
        row["temperature_C"] is None
        and row["temperature_qualifier"] is None
        and row["temperature_reported"] is False
        and OTHER in row["flags"].split(";")
    )


def test_a_storage_temperature_read_off_the_medium_label_is_cleared():
    """PMC8719689: the column "RPMI (stored at 37 ˚C for 24 h)", the quote only the table row."""
    row = _record([], medium_text=STORED, temperature_C=37.0).to_rows()[0]
    assert _cleared(row)
    assert row["conditions_complete"] is False
    assert row["medium_text"] == STORED


def test_room_temperature_at_zero_hours_is_kept():
    """The same table's "(0 h at RT)" columns were measured straight away: that RT stands."""
    row = _record(
        [], medium_text="RPMI (0 h at RT)", temperature_C=None, temperature_qualifier="RT"
    ).to_rows()[0]
    assert row["temperature_qualifier"] == "RT"
    assert row["temperature_reported"] is True
    assert OTHER not in row["flags"]


def test_a_measurement_temperature_is_kept():
    paper = "Cells were incubated at 37 °C. The zeta potential was measured at 25 °C."
    quote = "The zeta potential was -30.0 mV, measured at 25 °C."
    row = _record([], quote=quote, temperature_C=25.0).to_rows(paper=paper)[0]
    assert row["temperature_C"] == 25.0
    assert row["temperature_reported"] is True
    assert OTHER not in row["flags"]


def test_a_label_temperature_the_quote_also_states_is_kept():
    quote = "The zeta potential, measured at 37 °C, was -30.0 mV."
    row = _record([], quote=quote, medium_text=STORED, temperature_C=37.0).to_rows()[0]
    assert row["temperature_C"] == 37.0
    assert OTHER not in row["flags"]


def test_a_step_label_at_another_temperature_leaves_the_row_alone():
    """PMC13520334: "t = 24 h (incubated at 37 °C)", measured at room temperature."""
    medium = "cell culture medium, t = 24 h (incubated at 37 °C)"
    rt = _record(
        [], medium_text=medium, temperature_C=None, temperature_qualifier="room temperature"
    ).to_rows()[0]
    assert rt["temperature_qualifier"] == "room temperature"
    assert OTHER not in rt["flags"]
    at_25 = _record([], medium_text=medium, temperature_C=25.0).to_rows()[0]
    assert at_25["temperature_C"] == 25.0
    assert OTHER not in at_25["flags"]


def test_a_temperature_the_paper_gives_only_for_a_step_is_cleared():
    """PMC13288247: 37 °C appears once, for the SGF incubation; the quote has no temperature."""
    paper = (
        "Particles were incubated in simulated gastric fluid (SGF) at 37 °C for 30 min, after "
        "which zeta potential was measured in triplicate."
    )
    row = _record([], medium_text="simulated gastric fluid (SGF)", temperature_C=37.0)
    assert _cleared(row.to_rows(paper=paper)[0])


def test_one_measurement_sentence_in_the_paper_keeps_it():
    paper = "Cells were incubated at 37 °C. The zeta potential was measured at 37 °C."
    row = _record([], temperature_C=37.0).to_rows(paper=paper)[0]
    assert row["temperature_C"] == 37.0
    assert OTHER not in row["flags"]


def test_a_temperature_the_paper_never_prints_in_degrees_is_kept():
    """PMC10734291 prints 298 K; the row holds 24.85 °C. Absence is not a step."""
    row = _record([], temperature_C=24.85).to_rows(paper="Measured at T = 298 K.")[0]
    assert row["temperature_C"] == 24.85
    assert OTHER not in row["flags"]


def test_without_the_paper_only_the_row_is_read():
    row = _record([], temperature_C=37.0).to_rows()[0]
    assert row["temperature_C"] == 37.0


def test_r2b_leaves_the_record_alone():
    rec = _record([], medium_text=STORED, temperature_C=37.0)
    before = rec.to_json()
    assert _cleared(rec.to_rows()[0])
    assert rec.to_json() == before
    assert rec.row_flags == [[]]


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


# A number with a degree sign, as a medium label prints a temperature. Deliberately not the
# rule's own helper: the check below must be able to disagree with it.
_DEGREE_NUMBER = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:±\s*[\d.,]+\s*)?[°˚º℃]")


def _step_phrase_temperatures(medium: str) -> set[float]:
    found = set()
    for segment in re.split(r"[(),;]", medium):
        if coerce.OTHER_STEP_RE.search(segment):
            found |= {float(n.replace(",", ".")) for n in _DEGREE_NUMBER.findall(segment)}
    return found


def test_no_committed_temperature_sits_in_a_step_phrase_of_its_own_medium(table):
    """R2b on the artefact: "RPMI (stored at 37 ˚C for 24 h)" never leaves 37 °C behind."""
    wrong = [
        (r["row_id"], r["temperature_C"], r["medium_text"])
        for r in table.to_dict(orient="records")
        if isinstance(r["medium_text"], str)
        and pd.notna(r["temperature_C"])
        and r["temperature_C"] in _step_phrase_temperatures(r["medium_text"])
    ]
    assert wrong == []


def test_no_other_step_flagged_committed_row_has_a_temperature(table):
    # Since the re-read under the current brief (92db4fb) no record holds another step's
    # temperature, so R2b clears none and this can hold with no row. R2b itself is proven on
    # real cases by the tests above; the committed data is checked by the step-phrase test.
    other = table[_flagged(table, OTHER)]
    assert other["temperature_C"].isna().all()
    assert other["temperature_qualifier"].isna().all()
    assert not other["temperature_reported"].astype(bool).any()


def test_the_record_still_holds_every_other_step_temperature():
    """Provenance for R2b: each row it cleared still carries its temperature in the record."""
    held = {}
    for line in (config.DATA_INTERIM / "extractions.jsonl").read_text().splitlines():
        if line.strip():
            for m in json.loads(line)["measurements"]:
                held[m["row_id"]] = m["conditions"].get("temperature_C")
    built = pd.read_parquet(config.DATA_PROCESSED / "zeta_table.parquet")
    cleared = built.loc[_flagged(built, OTHER), "row_id"].tolist()
    # empty since 92db4fb, for the reason given above
    assert [r for r in cleared if held.get(r) is None] == []
