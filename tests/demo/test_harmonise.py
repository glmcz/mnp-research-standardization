"""Rebuilds FINDINGS E2b (the conversion-model scan) and pins the four-way zeta interval logic
and the mobility-to-zeta conversion against hand-computed numbers. `mnp.demo.harmonise` did
not exist before this file; the first run against an empty module is the required red run.
"""

from __future__ import annotations

import pandas as pd
import pytest

from mnp import config
from mnp.demo.harmonise import (
    ScanResult,
    harmonise,
    harmonise_paper,
    models_named,
    scan,
)
from mnp.ek.constants import permittivity, viscosity
from mnp.eval.comparability import debye_length_nm, henry_f
from mnp.schema.models import Quantity

#: FINDINGS E2b's corrected denominator was published in this commit, measured on the table
#: committed with it (1 890 rows from 491 papers).
E2B_COMMIT = "9ce15fa"


@pytest.fixture(scope="module")
def table() -> pd.DataFrame:
    return pd.read_csv(config.OUT_TABLES / "d1_zeta_table.csv")


@pytest.fixture(scope="module")
def e2b_table(table_at) -> pd.DataFrame:
    return pd.read_csv(table_at(E2B_COMMIT))


def _papers(table: pd.DataFrame, quantity: str, *, valued: bool = False) -> int:
    rows = table[table["quantity"] == quantity]
    if valued:
        rows = rows[rows["value"].notna()]
    return rows["pmcid"].nunique()


# --- the E2b census -------------------------------------------------------------------------


def test_scan_reproduces_findings_e2b(e2b_table):
    """FINDINGS.md E2b, "Correction - the denominator was wrong": 485 papers report a zeta
    value, 33 name a conversion model, 452 do not; 13 report a mobility, 6 name one. Run on the
    table E2b was measured on, which a re-extraction cannot move.
    """
    result = scan(e2b_table)
    assert result == ScanResult(
        zeta_papers=485, zeta_named=33, mobility_papers=13, mobility_named=6
    )
    assert result.zeta_not_named == 452
    assert result.mobility_not_named == 7


def test_denominator_counts_rows_with_a_null_value_too(table, e2b_table):
    """The right denominator is "the paper printed a row of this quantity", not "the row
    survived extraction with a number". Papers with only null-valued rows of a quantity still
    count: on the E2b table, filtering them out would undercount 485 to 348 and 13 to 9, neither
    of which reproduces FINDINGS. `scan` must use that denominator on today's table too.
    """
    assert _papers(e2b_table, "zeta_potential") == 485
    assert _papers(e2b_table, "electrophoretic_mobility") == 13
    assert _papers(e2b_table, "zeta_potential", valued=True) == 348
    assert _papers(e2b_table, "electrophoretic_mobility", valued=True) == 9
    for frame in (e2b_table, table):
        result = scan(frame)
        assert result.zeta_papers == _papers(frame, "zeta_potential")
        assert result.mobility_papers == _papers(frame, "electrophoretic_mobility")


def test_models_named_is_cached():
    first = models_named("PMC11117817")
    second = models_named("PMC11117817")
    assert first is second


def test_henry_pattern_needs_function_equation_or_formula_not_the_bare_surname():
    # Henry named as the function/equation is a hit; Henry the bare surname (a citation, a
    # co-author, "Henry et al.") must not be. This is the widening FINDINGS E2b needed.
    from mnp.demo.harmonise import _HENRY_RE

    assert _HENRY_RE.search("we used Henry's equation to convert mobility to zeta")
    assert _HENRY_RE.search("via the Henry function")
    assert _HENRY_RE.search("WE USED HENRY'S FORMULA")  # case-insensitive
    assert not _HENRY_RE.search("as shown by Henry (1931) and later Ohshima")
    assert not _HENRY_RE.search("Henry et al. reported a similar trend")


def test_missing_xml_yields_no_models_named(tmp_path, monkeypatch):
    from mnp import config as cfg

    monkeypatch.setattr(cfg, "EPMC_XML_DIR", tmp_path)
    models_named.cache_clear()
    try:
        assert models_named("PMC00000000") == frozenset()
    finally:
        models_named.cache_clear()


# --- synthetic zeta rows: the four cases + Henry-consistent --------------------------------


def _zeta_row(row_id="R-r1", pmcid="PMCX", *, value, size_nm=None, ionic_mM=None):
    row = {
        "row_id": row_id,
        "pmcid": pmcid,
        "quantity": "zeta_potential",
        "material": "polystyrene",
        "functionalisation": "carboxylated",
        "value": value,
        "unit": "mV",
        "size_measured_nm": size_nm,
        "ionic_strength_mM": ionic_mM,
        "ionic_strength_source": "reported" if ionic_mM is not None else "unreported",
        "medium_text": "10 mM NaCl",
        "medium_class": "salt_solution",
        "pH": 7.0,
        "temperature_C": 25.0,
        "instrument": "Zetasizer Nano ZS",
    }
    return row


# a size/ionic-strength pair with a non-trivial, hand-checkable f(kappa*a)
_SIZE_NM = 100.0
_IONIC_MM = 10.0
_KAPPA_A = (_SIZE_NM / 2.0) / debye_length_nm(_IONIC_MM)
_F = henry_f(_KAPPA_A)
_VALUE = -40.0


def test_case_model_named_kappa_known_is_a_point():
    row = _zeta_row(value=_VALUE, size_nm=_SIZE_NM, ionic_mM=_IONIC_MM)
    result = harmonise(row, frozenset({"smoluchowski"}))
    assert result.point == pytest.approx(_VALUE * 1.5 / _F)
    assert result.low is None and result.high is None
    assert result.model == "smoluchowski"
    assert result.kappa_a == pytest.approx(_KAPPA_A)
    assert result.f == pytest.approx(_F)


def test_case_model_named_kappa_unknown_is_an_interval():
    row = _zeta_row(value=_VALUE, size_nm=None, ionic_mM=None)
    result = harmonise(row, frozenset({"huckel"}))
    expected = sorted([_VALUE * 1.0 * (1 / 1.5), _VALUE * 1.0 * (1 / 1.0)])
    assert result.point is None
    assert [result.low, result.high] == pytest.approx(expected)
    assert result.low <= result.high
    assert result.kappa_a is None  # never imputed


def test_case_model_unnamed_kappa_known_is_an_interval_of_two_points():
    row = _zeta_row(value=_VALUE, size_nm=_SIZE_NM, ionic_mM=_IONIC_MM)
    result = harmonise(row, frozenset())
    expected = sorted([_VALUE * 1.0 / _F, _VALUE * 1.5 / _F])
    assert result.point is None
    assert [result.low, result.high] == pytest.approx(expected)
    assert result.low <= result.high
    assert result.model is None


def test_case_both_unknown_is_the_widest_interval():
    row = _zeta_row(value=_VALUE, size_nm=None, ionic_mM=None)
    result = harmonise(row, frozenset())
    expected = sorted([_VALUE * (1 / 1.5), _VALUE * 1.5])
    assert result.point is None
    assert [result.low, result.high] == pytest.approx(expected)
    assert result.low <= result.high
    assert result.kappa_a is None
    assert result.f is None


def test_negative_value_bounds_are_sorted_low_le_high():
    """The interval formulas multiply by factors that straddle 1, so for a negative reported
    value the algebraically larger product is the more negative number. If bounds were
    reported in raw (b1, b2) order rather than sorted, this would fail.
    """
    row = _zeta_row(value=-40.0, size_nm=None, ionic_mM=None)
    result = harmonise(row, frozenset())
    assert result.low < result.high
    assert result.low == pytest.approx(-60.0)
    assert result.high == pytest.approx(-26.666666666666664)


def test_positive_value_bounds_are_also_sorted_low_le_high():
    row = _zeta_row(value=40.0, size_nm=None, ionic_mM=None)
    result = harmonise(row, frozenset())
    assert result.low < result.high
    assert result.low == pytest.approx(26.666666666666664)
    assert result.high == pytest.approx(60.0)


def test_henry_named_gives_a_point_equal_to_the_reported_value():
    row = _zeta_row(value=_VALUE, size_nm=_SIZE_NM, ionic_mM=_IONIC_MM)
    result = harmonise(row, frozenset({"henry"}))
    assert result.point == pytest.approx(_VALUE)
    assert result.model == "henry"
    assert result.kappa_a == pytest.approx(_KAPPA_A)


def test_ohshima_named_gives_a_point_even_with_kappa_unknown():
    """Deviation from a literal reading of the design doc, documented in harmonise._zeta_case:
    Henry's function needs no assumed f_m at any kappa*a, so the point does not depend on
    whether kappa*a is independently known - only the contextual kappa_a/f fields do.
    """
    row = _zeta_row(value=_VALUE, size_nm=None, ionic_mM=None)
    result = harmonise(row, frozenset({"ohshima"}))
    assert result.point == pytest.approx(_VALUE)
    assert result.kappa_a is None
    assert result.f is None


def test_both_textbook_limits_named_kappa_unknown_is_an_interval():
    """Correction to the design doc (Martin, overriding it): naming both Smoluchowski and
    Huckel together is NOT Henry-consistent - a mention scan cannot tell which one was
    actually applied ("used Smoluchowski rather than Huckel" reads the same as the reverse).
    So this is treated exactly like no model named: f_m is unknown, in {1, 1.5}.
    """
    row = _zeta_row(value=_VALUE, size_nm=None, ionic_mM=None)
    result = harmonise(row, frozenset({"smoluchowski", "huckel"}))
    expected = sorted([_VALUE * (1 / 1.5), _VALUE * 1.5])
    assert result.point is None
    assert result.model is None
    assert [result.low, result.high] == pytest.approx(expected)
    assert result.low <= result.high
    assert result.kappa_a is None


def test_both_textbook_limits_named_kappa_known_is_a_two_point_interval():
    row = _zeta_row(value=_VALUE, size_nm=_SIZE_NM, ionic_mM=_IONIC_MM)
    result = harmonise(row, frozenset({"smoluchowski", "huckel"}))
    expected = sorted([_VALUE * 1.0 / _F, _VALUE * 1.5 / _F])
    assert result.point is None
    assert result.model is None
    assert [result.low, result.high] == pytest.approx(expected)
    assert result.low <= result.high
    assert result.kappa_a == pytest.approx(_KAPPA_A)


def test_missing_value_yields_no_value_at_all():
    row = _zeta_row(value=None, size_nm=_SIZE_NM, ionic_mM=_IONIC_MM)
    result = harmonise(row, frozenset())
    assert result.reported_value is None
    assert result.point is None and result.low is None and result.high is None
    assert "no reported value" in result.why


def test_no_default_is_ever_used_for_missing_ionic_strength():
    """A row missing ionic strength must never yield a point, whatever the model. This checks
    it across every model-naming combination, not just the one case above.
    """
    for models in (frozenset(), frozenset({"smoluchowski"}), frozenset({"huckel"})):
        row = _zeta_row(value=_VALUE, size_nm=100.0, ionic_mM=None)
        result = harmonise(row, models)
        if models:
            assert result.point is None, models
        assert result.kappa_a is None, models


# --- mobility rows ---------------------------------------------------------------------------


def _mobility_row(
    row_id="M-r1", pmcid="PMCM", *, value, unit="um_cm_per_Vs", T=None, size_nm=None, ionic_mM=None
):
    return {
        "row_id": row_id,
        "pmcid": pmcid,
        "quantity": "electrophoretic_mobility",
        "material": "polystyrene",
        "functionalisation": "carboxylated",
        "value": value,
        "unit": unit,
        "size_measured_nm": size_nm,
        "ionic_strength_mM": ionic_mM,
        "ionic_strength_source": "reported" if ionic_mM is not None else "unreported",
        "medium_text": "10 mM NaCl",
        "medium_class": "salt_solution",
        "pH": 7.0,
        "temperature_C": T,
        "instrument": "Zetasizer Nano ZS",
    }


def test_mobility_with_temperature_and_known_kappa_is_a_point():
    T = 25.0
    mu_val = -3.53
    row = _mobility_row(value=mu_val, T=T, size_nm=_SIZE_NM, ionic_mM=_IONIC_MM)
    result = harmonise(row, frozenset())
    eta = float(viscosity(T))
    eps = float(permittivity(T))
    f = henry_f(_KAPPA_A)
    expected_mV = (3.0 * eta * (mu_val * 1e-8) / (2.0 * eps * f)) * 1000.0
    assert result.point == pytest.approx(expected_mV)
    assert result.low is None and result.high is None
    assert result.kappa_a == pytest.approx(_KAPPA_A)


def test_mobility_with_temperature_and_unknown_kappa_is_an_interval():
    T = 25.0
    mu_val = -3.53
    row = _mobility_row(value=mu_val, T=T, size_nm=None, ionic_mM=None)
    result = harmonise(row, frozenset())
    eta = float(viscosity(T))
    eps = float(permittivity(T))
    z1 = (3.0 * eta * (mu_val * 1e-8) / (2.0 * eps * 1.0)) * 1000.0
    z2 = (3.0 * eta * (mu_val * 1e-8) / (2.0 * eps * 1.5)) * 1000.0
    expected = sorted([z1, z2])
    assert result.point is None
    assert [result.low, result.high] == pytest.approx(expected)
    assert result.low <= result.high


def test_mobility_without_temperature_yields_no_value_and_says_why():
    row = _mobility_row(value=-3.53, T=None, size_nm=_SIZE_NM, ionic_mM=_IONIC_MM)
    result = harmonise(row, frozenset())
    assert result.point is None and result.low is None and result.high is None
    assert result.why == "needs the measurement temperature"
    # temperature is never defaulted, even though size/ionic strength were known here


def test_mobility_unrecognised_unit_yields_no_value():
    row = _mobility_row(value=-3.53, unit="mV", T=25.0)  # wrong unit for this quantity
    result = harmonise(row, frozenset())
    assert result.point is None and result.low is None and result.high is None
    assert "unit" in result.why


# --- real papers -----------------------------------------------------------------------------


def test_pmc11117817_mobility_rows_all_need_temperature(table):
    """PMC11117817 is the design's mode-09 "mobility-reported" case. Every row in the vendored
    table has temperature_C unreported, so every mobility row must come back with no value.
    """
    results = harmonise_paper("PMC11117817", table)
    mobility = [r for r in results if r.quantity is Quantity.electrophoretic_mobility]
    assert len(mobility) == 16
    for r in mobility:
        assert r.point is None and r.low is None and r.high is None
        assert r.why == "needs the measurement temperature"


def test_pmc10145996_size_regime_rows_are_both_unknown_intervals(table):
    """PMC10145996 (mode-10, "size-regime": 50 nm vs 1 um PS-NH2) reports zeta directly, names
    no conversion model, and its rows have no ionic strength - so kappa*a is unknown and both
    rows land in the widest interval, ζ_rep * [1/1.5, 1.5].
    """
    results = harmonise_paper("PMC10145996", table)
    assert len(results) == 2
    by_row = {r.row_id: r for r in results}

    r1 = by_row["PMC10145996-r1"]
    assert r1.reported_value == pytest.approx(24.13)
    assert r1.point is None
    assert r1.kappa_a is None
    assert [r1.low, r1.high] == pytest.approx(sorted([24.13 / 1.5, 24.13 * 1.5]))

    r2 = by_row["PMC10145996-r2"]
    assert r2.reported_value == pytest.approx(-33.97)
    assert r2.point is None
    assert [r2.low, r2.high] == pytest.approx(sorted([-33.97 / 1.5, -33.97 * 1.5]))
    assert r2.low < r2.high


def test_pmc10145996_and_pmc11117817_name_no_model(table):
    assert models_named("PMC10145996") == frozenset()
    assert models_named("PMC11117817") == frozenset()
