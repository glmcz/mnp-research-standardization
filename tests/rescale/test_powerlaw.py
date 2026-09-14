"""Power-law size rescaling.

pdf ∝ x^−α. Correction factor moving a concentration measured over [x1M, x2M]
onto the default range [x1D, x2D]:

    CF = (x2D^(1−α) − x1D^(1−α)) / (x2M^(1−α) − x1M^(1−α))   for α ≠ 1
    CF = ln(x2D / x1D) / ln(x2M / x1M)                        at α = 1

rescaled = measured × CF. Default target 1–5000 µm, α = 1.6 (Kooi & Koelmans 2019
ES&T Lett 6:551; Koelmans et al. 2020 ES&T 54:12307 eq. 2).

Oracles: Koelmans 2020 Table 1 (α = 1.6, target 1–5000 µm).
"""

import math

import numpy as np
import pandas as pd
import pytest
from scipy.integrate import quad

from mnp.rescale import powerlaw as pl

KOELMANS_2020_TABLE_1 = [
    ((333, 5000), 40.37),
    ((300, 5000), 37.36),
    ((100, 5000), 17.42),
    ((20, 5000), 6.22),
    ((20, 1000), 6.63),
    ((30, 2000), 8.32),
]


def _quad_ratio(x1m, x2m, x1d, x2d, alpha):
    num, _ = quad(lambda x: x**-alpha, x1d, x2d)
    den, _ = quad(lambda x: x**-alpha, x1m, x2m)
    return num / den


@pytest.mark.parametrize("alpha", [1.2, 1.6, 2.2])
@pytest.mark.parametrize("measured", [(333, 5000), (20, 1000), (0.5, 50), (10, 5000)])
def test_closed_form_matches_numerical_integral(alpha, measured):
    x1m, x2m = measured
    closed = pl.cf_closed(x1m, x2m, 1.0, 5000.0, alpha)
    numeric = _quad_ratio(x1m, x2m, 1.0, 5000.0, alpha)
    assert closed == pytest.approx(numeric, rel=1e-6)
    assert pl.cf_numeric(x1m, x2m, 1.0, 5000.0, alpha) == pytest.approx(numeric, rel=1e-9)


@pytest.mark.parametrize(("measured", "expected"), KOELMANS_2020_TABLE_1)
def test_koelmans_2020_table_1_to_two_decimals(measured, expected):
    x1m, x2m = measured
    cf = pl.cf_closed(x1m, x2m, 1.0, 5000.0, 1.6)
    assert round(cf, 2) == expected


def test_defaults_are_the_published_target_and_alpha():
    assert pl.TARGET_DEFAULT == (1.0, 5000.0)
    assert pl.ALPHA_DEFAULT == 1.6
    assert round(pl.cf_closed(333, 5000), 2) == 40.37


def test_alpha_one_uses_the_log_form():
    cf = pl.cf_closed(20, 1000, 1.0, 5000.0, 1.0)
    assert cf == pytest.approx(math.log(5000 / 1) / math.log(1000 / 20))


def test_closed_form_is_continuous_at_alpha_one():
    at_one = pl.cf_closed(20, 1000, 1.0, 5000.0, 1.0)
    for eps in (1e-6, -1e-6):
        assert pl.cf_closed(20, 1000, 1.0, 5000.0, 1.0 + eps) == pytest.approx(at_one, rel=1e-5)


@pytest.mark.parametrize("alpha", [1.0, 1.3, 1.6, 3.1])
def test_identity_when_measured_range_equals_target(alpha):
    assert pl.cf_closed(1.0, 5000.0, 1.0, 5000.0, alpha) == pytest.approx(1.0)
    assert pl.cf_closed(0.1, 5000.0, 0.1, 5000.0, alpha) == pytest.approx(1.0)


def test_nano_target_moves_the_333_study_to_about_160():
    cf = pl.cf_closed(333, 5000, *pl.TARGET_NANO, alpha=1.6)
    assert 155 < cf < 165


def test_rescale_multiplies_by_the_correction_factor():
    assert pl.rescale(2.0, 333, 5000) == pytest.approx(2.0 * pl.cf_closed(333, 5000))


@pytest.mark.parametrize("bad", [(0, 5000), (5000, 5000), (5000, 333), (-1, 10)])
def test_invalid_ranges_raise(bad):
    with pytest.raises(ValueError):
        pl.cf_closed(*bad)


def test_alpha_sensitivity_labels_the_abstract_only_values():
    assert pl.ALPHA_SENSITIVITY == (1.3, 1.6, 2.0, 2.2, 2.6, 3.1)
    for alpha in (2.2, 2.6, 3.1):
        assert "abstract only" in pl.alpha_source(alpha)
        assert "Kooi" in pl.alpha_source(alpha) and "2021" in pl.alpha_source(alpha)
    for alpha in (1.3, 1.6, 2.0):
        assert "abstract only" not in pl.alpha_source(alpha)


@pytest.mark.parametrize(
    "unit",
    ["#/L", "# /L", "particles/L", "items/L", "n/m3", "#/km2", "particles/km2", "SAL L-1", "MP/L"],
)
def test_particle_number_units_are_number(unit):
    assert pl.classify_unit(unit) == "number"


@pytest.mark.parametrize("unit", ["µg/L", "ug/L", "mg/L", "mg/kg", "g/m3", "mg/km2"])
def test_mass_units_are_mass(unit):
    assert pl.classify_unit(unit) == "mass"


def test_normalise_unit_puts_volumetric_on_per_litre_and_areal_on_per_km2():
    assert pl.normalise_unit("#/L") == ("n/L", 1.0)
    assert pl.normalise_unit("particles/m3") == ("n/L", pytest.approx(1e-3))
    assert pl.normalise_unit("#/km-2") == ("n/km2", 1.0)
    assert pl.normalise_unit("items/km2") == ("n/km2", 1.0)


def _table():
    return pd.DataFrame(
        {
            "study": ["closed", "lower_only", "mass", "no_size", "areal"],
            "matrix": ["freshwater"] * 5,
            "size_min_um": [333.0, 333.0, 100.0, np.nan, 300.0],
            "size_max_um": [5000.0, np.nan, 5000.0, np.nan, 5000.0],
            "concentration_value": [2.0, 2.0, 5.0, 1.0, 1e4],
            "concentration_unit": ["#/L", "#/L", "mg/L", "#/L", "#/km2"],
            "method": ["m"] * 5,
            "notes": [""] * 5,
        }
    )


def test_rescale_table_has_one_row_per_study_target_alpha():
    out = pl.rescale_table(_table(), targets=pl.TARGETS, alphas=pl.ALPHA_SENSITIVITY)
    assert len(out) == 5 * 2 * 6
    assert set(out["alpha"]) == set(pl.ALPHA_SENSITIVITY)
    assert set(zip(out["target_min_um"], out["target_max_um"], strict=True)) == set(pl.TARGETS)
    assert out.loc[out["alpha"] == 2.2, "alpha_source"].str.contains("abstract only").all()


def test_lower_bound_only_assumes_5000_and_flags_it():
    out = pl.rescale_table(_table())
    row = out[(out["study"] == "lower_only") & (out["alpha"] == 1.6)].iloc[0]
    assert row["size_max_um"] == 5000.0
    assert bool(row["upper_assumed"]) is True
    assert pd.isna(row["excluded_reason"])
    assert row["cf"] == pytest.approx(40.37, abs=0.005)
    closed = out[(out["study"] == "closed") & (out["alpha"] == 1.6)].iloc[0]
    assert bool(closed["upper_assumed"]) is False


def test_mass_units_are_excluded_not_rescaled():
    out = pl.rescale_table(_table())
    mass = out[out["study"] == "mass"]
    assert (mass["excluded_reason"] == "mass_units").all()
    assert mass["cf"].isna().all()
    assert mass["rescaled_value"].isna().all()


def test_missing_size_range_is_excluded():
    out = pl.rescale_table(_table())
    assert (out.loc[out["study"] == "no_size", "excluded_reason"] == "no_size_range").all()


def test_missing_concentration_is_reported_before_the_unit_is_judged():
    table = _table()
    table.loc[0, ["concentration_value", "concentration_unit"]] = [np.nan, ""]
    out = pl.rescale_table(table)
    assert (out.loc[out["study"] == "closed", "excluded_reason"] == "no_concentration").all()


def test_number_units_rescale_and_areal_units_keep_their_family():
    out = pl.rescale_table(_table())
    closed = out[(out["study"] == "closed") & (out["alpha"] == 1.6)]
    default = closed[closed["target_min_um"] == 1.0].iloc[0]
    nano = closed[closed["target_min_um"] == 0.1].iloc[0]
    assert default["rescaled_value"] == pytest.approx(2.0 * 40.37, rel=1e-3)
    assert nano["rescaled_value"] == pytest.approx(2.0 * pl.cf_closed(333, 5000, 0.1, 5000))
    assert default["unit_norm"] == "n/L"
    areal = out[out["study"] == "areal"].iloc[0]
    assert areal["unit_norm"] == "n/km2"
    assert pd.isna(areal["excluded_reason"])
