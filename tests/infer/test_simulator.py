"""Forward-model wrappers θ → μ(I_grid) with the assumed digitising noise
σ = sqrt((5 % · μ)² + (1.5 % · axis range)²)."""

import numpy as np
import pytest

from mnp.ek import hard, qa, soft
from mnp.infer import simulator as sm

GRID = np.logspace(0, np.log10(200), 8)


def test_soft_forward_matches_the_physics_in_1e8_units():
    sim = sm.SoftSimulator(GRID, axis_range=3.0)
    theta = sim.theta_from(-0.0015, 1.2)
    expected = soft.mobility_soft(-0.0015, 1.2e-9, GRID) / sm.MU_UNIT
    assert sim.forward(theta).shape == (8,)
    assert np.allclose(sim.forward(theta), expected)
    batch = np.stack([theta, theta + 0.1])
    assert sim.forward(batch).shape == (2, 8)
    assert np.allclose(sim.forward(batch)[0], expected)


def test_hard_forward_matches_the_physics_in_1e8_units():
    grid = np.logspace(-1, np.log10(200), 8)
    sim = sm.HardSimulator(grid, axis_range=12.0, electrolyte="KCl")
    theta = sim.theta_from(-0.07, 1400.0)
    expected = hard.mobility_hard(-0.07, 1.4e-6, grid, electrolyte="KCl") / sm.MU_UNIT
    assert np.allclose(sim.forward(theta), expected)


def test_theta_roundtrip_both_models():
    soft_sim = sm.SoftSimulator(GRID, axis_range=3.0)
    zn, lam = soft_sim.params_from(soft_sim.theta_from(-0.0038, 6.44))
    assert zn == pytest.approx(-0.0038) and lam == pytest.approx(6.44)
    hard_sim = sm.HardSimulator(GRID, axis_range=12.0)
    sigma, radius = hard_sim.params_from(hard_sim.theta_from(-0.011, 125.0))
    assert sigma == pytest.approx(-0.011) and radius == pytest.approx(125.0)


def test_noise_scales_with_axis_range():
    theta = sm.SoftSimulator(GRID, axis_range=1.0).theta_from(-0.0015, 1.2)
    stds = {}
    for axis_range in (1.0, 4.0):
        sim = sm.SoftSimulator(GRID, axis_range=axis_range)
        clean = sim.forward(theta)
        rng = np.random.default_rng(0)
        draws = sim.simulate(np.repeat(theta[None, :], 20000, axis=0), rng)
        assert draws.shape == (20000, 8)
        stds[axis_range] = draws.std(axis=0)
        expected = np.sqrt((sm.REL_NOISE * clean) ** 2 + (sm.AXIS_NOISE * axis_range) ** 2)
        assert np.allclose(stds[axis_range], expected, rtol=0.05)
        assert np.allclose(sim.noise_std(clean), expected)
    assert np.all(stds[4.0] > stds[1.0])
    # the additive part alone quadruples; the relative part is untouched
    additive_1 = np.sqrt(stds[1.0] ** 2 - (sm.REL_NOISE * clean) ** 2)
    additive_4 = np.sqrt(stds[4.0] ** 2 - (sm.REL_NOISE * clean) ** 2)
    assert np.allclose(additive_4 / additive_1, 4.0, rtol=0.1)


def test_relative_part_makes_noise_larger_where_mobility_is_larger():
    sim = sm.SoftSimulator(GRID, axis_range=0.1)
    clean = sim.forward(sim.theta_from(-0.0015, 1.2))
    std = sim.noise_std(clean)
    assert std[0] > std[-1]  # |μ| is largest at the lowest ionic strength


def test_prior_sampling_and_log_prior():
    sim = sm.SoftSimulator(GRID, axis_range=3.0)
    rng = np.random.default_rng(1)
    theta = sim.sample_prior(rng, 500)
    assert theta.shape == (500, 2)
    assert np.all(theta >= sim.prior_low) and np.all(theta <= sim.prior_high)
    assert np.all(sim.log_prior(theta) == 0.0)
    outside = np.array([[sim.prior_high[0] + 1.0, 0.0], [0.0, sim.prior_low[1] - 1.0]])
    assert np.all(np.isneginf(sim.log_prior(outside)))
    assert sim.log_prior(theta[0]) == 0.0


def test_printed_fits_lie_inside_the_priors():
    for fit in qa.load_bank():
        if not fit.complete:
            continue
        sim, theta = sm.simulator_for_fit(fit)
        assert sim.log_prior(theta) == 0.0, fit.key


def test_simulator_for_fit_uses_the_rows_grid_temperature_and_parameters():
    fit = qa.PrintedFit.from_row(
        {
            "dataset": "hakim_2016",
            "figure": "Fig. 1",
            "particle": "0.25 um",
            "model": "hard",
            "sigma_C_m2": "-0.011",
            "radius_nm": "125",
            "T_C": "20",
            "electrolyte": "KCl",
            "z": "1",
            "I_min_mM": "0.1",
            "I_max_mM": "100",
        }  # fmt: skip
    )
    sim, theta = sm.simulator_for_fit(fit)
    assert isinstance(sim, sm.HardSimulator)
    assert sim.T_C == 20.0 and sim.axis_range == sm.KOBAYASHI_FIG1_AXIS_RANGE
    assert np.allclose(sim.I_grid_mM, fit.grid())
    assert np.allclose(sim.forward(theta), fit.curve(fit.grid()))
    assert sim.params_from(theta) == pytest.approx((-0.011, 125.0))


def test_with_grid_keeps_model_temperature_and_noise():
    sim = sm.HardSimulator(GRID, axis_range=12.0, T_C=20.0, electrolyte="KCl")
    other = sim.with_grid(GRID[[0, 4]])
    assert other.n_obs == 2 and other.T_C == 20.0 and other.axis_range == 12.0
    assert other.electrolyte == "KCl" and sim.n_obs == 8
    theta = sim.theta_from(-0.07, 1400.0)
    assert np.allclose(other.forward(theta), sim.forward(theta)[[0, 4]])
