"""Soft-particle electrokinetics (Ohshima 1994; Makino & Ohshima 2011 eqs 1–6).

Thick layer, d ≫ 1/λ, 1/κ:

  μ = (εε₀/η) · (ψ₀/κ_m + ψ_DON/λ) / (1/κ_m + 1/λ) + ZeN/(ηλ²)
  ψ_DON = (kT/ze) · asinh(ZN/2zn)
  ψ₀ = ψ_DON + (kT/ze) · [1 − sqrt(1 + (ZN/2zn)²)] / (ZN/2zn)
  κ_m = κ (1 + (ZN/2zn)²)^¼

Printed oracle: Makino & Ohshima 2011 Fig. 2, zN = −0.0015 M, 1/λ = 1.2 nm, 25 °C.
The datasets doc prints no y-values for that figure, so the 5 % printed-value check has no
target; the numeric anchors below are hand calculations from the printed fit.
"""

import numpy as np
import pytest

from mnp.ek import hard, soft

MAKINO_ZN = -0.0015  # M (= zN in the paper's notation)
MAKINO_LAMBDA_INV = 1.2e-9  # m


def test_high_salt_plateau_is_ZeN_over_eta_lambda_squared():
    # ZeN = −1.447e5 C/m³, ηλ² = 0.89e-3 × (1/1.2 nm)² = 6.18e14 → −2.34e-10 m² V⁻¹ s⁻¹
    plateau = soft.plateau_mobility(MAKINO_ZN, MAKINO_LAMBDA_INV)
    assert plateau == pytest.approx(-2.34e-10, rel=0.03)
    assert soft.mobility_soft(MAKINO_ZN, MAKINO_LAMBDA_INV, 1e5) == pytest.approx(plateau, rel=0.01)
    seq = np.abs(soft.mobility_soft(MAKINO_ZN, MAKINO_LAMBDA_INV, np.array([1e2, 1e3, 1e4, 1e5])))
    assert np.all(np.diff(seq) < 0)
    assert seq[-1] > abs(plateau)


def test_donnan_potential_sign_follows_sign_of_ZN():
    neg = soft.donnan_potential(-0.0015, 10.0)
    pos = soft.donnan_potential(+0.0015, 10.0)
    assert neg < 0 < pos
    assert neg == pytest.approx(-pos)
    assert soft.donnan_potential(0.0, 10.0) == 0.0


def test_donnan_potential_value_at_10mM():
    # (kT/e) asinh(−0.0015 / (2 × 0.010)) = 25.69 mV × asinh(−0.075) = −1.925 mV
    assert soft.donnan_potential(MAKINO_ZN, 10.0) == pytest.approx(-1.925e-3, rel=0.01)


def test_kappa_m_equals_kappa_when_layer_is_uncharged():
    c = np.array([1.0, 10.0, 100.0])
    assert np.allclose(soft.kappa_m(0.0, c), hard.debye_kappa(c))


def test_kappa_m_exceeds_kappa_by_the_quarter_power_factor():
    # ZN/2zn = −0.75 at 1 mM → (1 + 0.5625)^¼ = 1.11803
    ratio = soft.kappa_m(MAKINO_ZN, 1.0) / hard.debye_kappa(1.0)
    assert ratio == pytest.approx((1 + 0.75**2) ** 0.25, rel=1e-9)
    assert ratio > 1


def test_surface_potential_is_smaller_than_donnan_and_has_the_same_sign():
    for c in (0.5, 5.0, 50.0):
        donnan = soft.donnan_potential(MAKINO_ZN, c)
        surface = soft.surface_potential(MAKINO_ZN, c)
        assert np.sign(surface) == np.sign(donnan)
        assert abs(surface) < abs(donnan)
    assert soft.surface_potential(0.0, 10.0) == 0.0


def test_makino_fig2_printed_fit_is_smooth_and_monotone_toward_the_plateau():
    ionic = np.logspace(0, np.log10(200), 60)
    mu = soft.mobility_soft(MAKINO_ZN, MAKINO_LAMBDA_INV, ionic)
    plateau = soft.plateau_mobility(MAKINO_ZN, MAKINO_LAMBDA_INV)
    assert np.all(mu < 0)
    assert np.all(np.diff(np.abs(mu)) < 0)
    assert np.all(np.abs(mu) > abs(plateau))
    curvature = np.diff(np.log(np.abs(mu)), 2)
    assert np.max(np.abs(curvature)) < 0.05, "log-curve has a kink"
    # hand calculation from the printed fit
    at_1, at_10 = soft.mobility_soft(MAKINO_ZN, MAKINO_LAMBDA_INV, np.array([1.0, 10.0]))
    assert at_1 == pytest.approx(-0.83e-8, rel=0.05)
    assert at_10 == pytest.approx(-0.12e-8, rel=0.05)


def test_layer_thickness_validity_flag():
    assert soft.layer_thickness_ok(25.0, 0.7, 3.0)
    assert not soft.layer_thickness_ok(25.0, 0.7, 9.6)
    assert soft.layer_thickness_ok(25.0, 0.7, 9.6, factor=2)
    flags = soft.layer_thickness_ok(25.0, 0.7, np.array([3.0, 9.6]))
    assert flags.tolist() == [True, False]


def test_bacterial_scale_mobility_is_plausible():
    # zN = −0.02 M, 1/λ = 2 nm at 10 mM → hand calc −2.2e-8; bacteria sit at −2…−3 ×10⁻⁸
    mu = soft.mobility_soft(-0.02, 2e-9, 10.0)
    assert -3e-8 < mu < -1.5e-8


def test_temperature_enters_through_water_properties():
    warm = soft.mobility_soft(MAKINO_ZN, MAKINO_LAMBDA_INV, 10.0, T_C=40.0)
    cold = soft.mobility_soft(MAKINO_ZN, MAKINO_LAMBDA_INV, 10.0, T_C=25.0)
    assert warm != cold


def test_mobility_broadcasts_over_parameter_columns_and_concentration_rows():
    zn = np.array([[-0.001], [-0.01]])
    lam = np.array([[1e-9], [3e-9]])
    mu = soft.mobility_soft(zn, lam, np.logspace(0, 2, 7))
    assert mu.shape == (2, 7)
