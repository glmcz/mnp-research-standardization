"""Hard-sphere electrokinetics: Debye length, Grahame, Henry, relaxation.

Oracles (README, "Provenance of every oracle number"):

- κ⁻¹ = sqrt(εε₀kT / (2 N_A e² I)); 150 mM, 25 °C → 0.79 nm.
- Henry function, Ohshima approximation
  f(κa) = 2/3 [1 + 1/(2(1 + 2.5/(κa(1 + 2e^(−κa))))³)] → 2/3 (κa → 0), 1 (κa → ∞).
- Grahame σ = sqrt(8 εε₀ kT n) sinh(zeψ₀/2kT), n = number density of a z:z electrolyte.
- Kobayashi 2008, Colloid Polym Sci 286:935, sulfate latex σ = −0.07 C/m², 2a = 2.8 µm, KCl,
  298 K, zero free parameters: the relaxation effect produces a maximum of |μ| between
  1 and 10 mM (the paper's Fig. 1). The datasets doc prints no data point for this figure;
  the numbers below are read off the paper's own theory curve (rendered PDF, ±10 %).
"""

import numpy as np
import pytest

from mnp.ek import constants, hard

KOBAYASHI_SIGMA = -0.07  # C/m²
KOBAYASHI_RADIUS = 1.4e-6  # m (2a = 2.8 µm)
GRID_MM = np.logspace(-1, 3, 81)


def test_debye_length_150mM_25C_is_0p79nm():
    length = hard.debye_length(150.0)
    assert 0.78e-9 <= length <= 0.80e-9


def test_debye_length_scales_as_inverse_sqrt_of_ionic_strength():
    assert hard.debye_length(1.0) / hard.debye_length(100.0) == pytest.approx(10.0)


def test_debye_kappa_is_reciprocal_of_debye_length():
    ionic = np.array([0.1, 10.0, 1000.0])
    assert np.allclose(hard.debye_kappa(ionic) * hard.debye_length(ionic), 1.0)


def test_henry_limits_two_thirds_and_one():
    assert hard.henry_f(1e-6) == pytest.approx(2 / 3, rel=1e-4)
    assert hard.henry_f(1e6) == pytest.approx(1.0, rel=1e-4)


def test_henry_is_monotone_between_its_limits():
    ka = np.logspace(-3, 4, 200)
    f = hard.henry_f(ka)
    assert np.all(np.diff(f) > 0)
    assert np.all((f > 2 / 3 - 1e-9) & (f < 1 + 1e-9))


def test_grahame_is_linear_at_low_potential():
    # zeψ₀ ≪ 2kT: σ → εε₀ κ ψ₀ (Debye–Hückel)
    psi, c = 1e-3, 10.0
    sigma = hard.grahame_sigma(psi, c)
    assert sigma == pytest.approx(constants.permittivity() * hard.debye_kappa(c) * psi, rel=1e-3)


def test_grahame_roundtrip_and_sign():
    for psi in (-0.2, -0.05, 0.03, 0.15):
        sigma = hard.grahame_sigma(psi, 10.0)
        assert np.sign(sigma) == np.sign(psi)
        assert hard.grahame_psi0(sigma, 10.0) == pytest.approx(psi, rel=1e-9)


def test_ionic_drag_coefficient_for_KCl_is_near_the_literature_value():
    # Ohshima quotes m ≈ 0.184 for KCl at 25 °C; with the CRC Λ° values Kobayashi 2008 used
    # (K⁺ 73.48, Cl⁻ 76.31 ×10⁻⁴ S m²/mol) and ε_r = 78.5 the definition
    # m = 2εε₀kT N_A / (3η|z|Λ°) gives 0.176 and 0.169.
    assert 0.16 <= hard.ionic_drag_m("K+") <= 0.19
    assert 0.16 <= hard.ionic_drag_m("Cl-") <= 0.19


def test_kobayashi_2008_hard_latex_shows_a_mobility_maximum():
    mu = hard.mobility_hard(KOBAYASHI_SIGMA, KOBAYASHI_RADIUS, GRID_MM, electrolyte="KCl")
    assert np.all(mu < 0)
    absmu = np.abs(mu)
    i = int(np.argmax(absmu))
    assert 0 < i < len(GRID_MM) - 1, "maximum must be interior"
    assert 1.0 <= GRID_MM[i] <= 10.0
    assert np.all((absmu > 1e-8) & (absmu < 12e-8))


def test_kobayashi_2008_curve_matches_the_papers_own_theory_curve():
    # Fig. 1 solid line ("Ohshima"): ≈ −4.8 at 0.1 mM, ≈ −10.3 at the minimum (2–4 mM),
    # ≈ −5.9 at 100 mM, in 10⁻⁸ m² V⁻¹ s⁻¹.
    mu = hard.mobility_hard(KOBAYASHI_SIGMA, KOBAYASHI_RADIUS, np.array([0.1, 100.0])) / 1e-8
    assert mu[0] == pytest.approx(-4.8, abs=0.6)
    assert mu[1] == pytest.approx(-5.9, abs=0.6)
    peak = np.abs(hard.mobility_hard(KOBAYASHI_SIGMA, KOBAYASHI_RADIUS, GRID_MM)).max() / 1e-8
    assert peak == pytest.approx(10.3, abs=1.0)


def test_without_relaxation_mobility_magnitude_is_monotone_in_I():
    mu = hard.mobility_hard(KOBAYASHI_SIGMA, KOBAYASHI_RADIUS, GRID_MM, relaxation=False)
    assert np.all(np.diff(np.abs(mu)) < 0)


def test_relaxation_is_negligible_at_low_charge_and_large_kappa_a():
    # σ = −0.001 C/m², a = 1.4 µm, 10 mM: ζ ≈ −4 mV, κa ≈ 460 → both forms ≈ Smoluchowski
    with_relax = hard.mobility_hard(-0.001, KOBAYASHI_RADIUS, 10.0, relaxation=True)
    henry = hard.mobility_hard(-0.001, KOBAYASHI_RADIUS, 10.0, relaxation=False)
    assert with_relax == pytest.approx(henry, rel=0.01)


def test_mobility_sign_follows_surface_charge():
    assert hard.mobility_hard(+0.02, 5e-7, 10.0) > 0
    assert hard.mobility_hard(-0.02, 5e-7, 10.0) < 0


def test_mobility_broadcasts_over_parameter_columns_and_concentration_rows():
    sigma = np.array([[-0.01], [-0.05]])
    mu = hard.mobility_hard(sigma, 5e-7, GRID_MM[:5])
    assert mu.shape == (2, 5)


def test_water_properties_anchored_at_25C():
    assert constants.eps_r(25.0) == pytest.approx(78.5)
    assert constants.viscosity(25.0) == pytest.approx(0.89e-3)
    # CRC Handbook: ε_r(40 °C) ≈ 73.2, η(40 °C) ≈ 0.653 mPa·s, η(20 °C) ≈ 1.002 mPa·s
    assert 72.5 <= constants.eps_r(40.0) <= 74.0
    assert 0.63e-3 <= constants.viscosity(40.0) <= 0.67e-3
    assert 0.98e-3 <= constants.viscosity(20.0) <= 1.02e-3


def test_hard_validity_flag_requires_large_kappa_a():
    assert hard.kappa_a_ok(50.0)
    assert not hard.kappa_a_ok(5.0)
    assert hard.kappa_a_ok(np.array([5.0, 50.0])).tolist() == [False, True]
