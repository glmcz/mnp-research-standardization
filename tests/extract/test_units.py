"""The printed unit is a property of the article, not of whatever a worker retyped."""

import pytest

from mnp.extract import units
from mnp.schema.models import Quantity, Unit


@pytest.mark.parametrize(
    "header, unit_text, factor",
    [
        ("Zeta Potential (mV)", "mV", 1.0),
        ("ζ-potential (mV)", "mV", 1.0),
        ("Zeta Potential, mV", "mV", 1.0),
        ("E. M. (cm 2/Vs)", "cm 2/Vs", 1e4),
        ("Electrophoretic mobility (10-8 m2 V-1 s-1)", "10-8 m2 V-1 s-1", 1.0),
        ("EM (µm cm/Vs)", "µm cm/Vs", 1.0),
        ("linear electrophoretic mobility × 10 –4 (cm 2 V -1 s -1)", None, 1.0),
    ],
)
def test_a_unit_is_read_out_of_a_table_header(header, unit_text, factor):
    m = units.unit_in(header)
    assert m is not None, header
    if unit_text is not None:
        assert m.text == unit_text
    assert m.factor == pytest.approx(factor)


def test_a_header_with_no_unit_yields_nothing():
    assert units.unit_in("Sample") is None
    assert units.unit_in("Size (nm)") is None
    assert units.unit_in("Zeta potential") is None


def test_a_nonlinear_mobility_unit_is_refused():
    assert units.unit_in("nonlinear mobility (× 10 –10 cm 4 V -3 s -1)") is None


def test_units_are_found_per_table_column_with_their_location():
    text = (
        "== Table t1\n"
        "Table 1. Particle properties.\n"
        "Sample\tZeta Potential (mV)\tE. M. (cm 2/Vs)\tSize (nm)\n"
        "PS\t-38.50\t-0.000298\t80\n"
    )
    found = units.find_units(text)
    by_header = {u.header: u for u in found}
    assert by_header["Zeta Potential (mV)"].quantity is Quantity.zeta_potential
    assert by_header["Zeta Potential (mV)"].unit is Unit.mV
    assert by_header["E. M. (cm 2/Vs)"].quantity is Quantity.electrophoretic_mobility
    assert by_header["E. M. (cm 2/Vs)"].factor == pytest.approx(1e4)
    assert all(u.location == "Table t1" for u in found)
    assert "Size (nm)" not in by_header


def test_a_unit_printed_only_in_the_caption_covers_the_table():
    text = (
        "== Table t2\n"
        "Table 2. Zeta potential (mV) of the different effluents.\n"
        "Industries\tBefore Treatment\tAfter Treatment\n"
        "Textile\t-20.1\t-11.4\n"
    )
    found = units.find_units(text)
    assert [u.unit for u in found] == [Unit.mV]
    assert found[0].source == "caption"


def test_a_unit_is_read_from_a_prose_sentence():
    text = "== Methods\nThe mobility was -3.08 × 10⁻⁸ m² V⁻¹ s⁻¹ in 10 mM NaCl.\n"
    found = units.find_units(text)
    assert found[0].quantity is Quantity.electrophoretic_mobility
    assert found[0].factor == pytest.approx(1.0)
    assert found[0].source == "prose"


def test_the_report_lists_every_printed_unit_once_per_location():
    text = (
        "== Table t1\nTable 1. Properties.\nSample\tZeta (mV)\n PS\t-30\n\n"
        "== Methods\nZeta potential was -30 mV.\n"
    )
    rows = units.report(text)
    assert {r["location"] for r in rows} == {"Table t1", "Methods"}
    assert all(r["unit"] == "mV" for r in rows)


def test_disagreement_is_detected_between_a_claimed_unit_and_the_printed_one():
    """The failure that corrupted 25 rows: a worker typed m2/Vs where the paper
    printed cm2/Vs, and the converter multiplied by 1e8 instead of 1e4."""
    printed = units.unit_in("E. M. (cm 2/Vs)")
    assert units.disagrees(claimed="m2 V-1 s-1", printed=printed) is True
    assert units.disagrees(claimed="cm2/Vs", printed=printed) is False
    assert units.disagrees(claimed=None, printed=printed) is False
    assert units.disagrees(claimed="mV", printed=None) is False
