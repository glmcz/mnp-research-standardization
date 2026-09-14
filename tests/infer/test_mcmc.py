"""emcee reference posterior: 32 walkers × 400 steps, seeded, Gaussian likelihood with the
simulator's own noise model. Recovery within 2σ on a synthetic dataset (small grid)."""

import numpy as np
import pytest

from mnp.infer import mcmc
from mnp.infer import simulator as sm

SOFT_GRID = np.logspace(0, np.log10(200), 6)
HARD_GRID = np.logspace(-1, np.log10(200), 6)


def synthetic(sim, theta_true, seed=0):
    return sim.simulate(theta_true, np.random.default_rng(seed))


def test_mcmc_recovers_injected_soft_parameters_within_2sigma():
    sim = sm.SoftSimulator(SOFT_GRID, axis_range=3.0)
    theta_true = sim.theta_from(-0.0015, 1.2)
    result = mcmc.run_mcmc(sim, synthetic(sim, theta_true), seed=1)
    assert result.samples.shape == (32 * (400 - mcmc.BURN), 2)
    assert np.all(np.abs(result.mean - theta_true) <= 2 * result.std), (result.mean, result.std)
    assert 0.15 < result.acceptance < 0.9
    assert result.param_names == sim.param_names


def test_mcmc_recovers_injected_hard_parameters_within_2sigma():
    sim = sm.HardSimulator(HARD_GRID, axis_range=12.0)
    theta_true = sim.theta_from(-0.07, 1400.0)
    result = mcmc.run_mcmc(sim, synthetic(sim, theta_true), seed=2)
    assert np.all(np.abs(result.mean - theta_true) <= 2 * result.std), (result.mean, result.std)


def test_log_posterior_is_minus_inf_outside_the_prior_and_finite_inside():
    sim = sm.SoftSimulator(SOFT_GRID, axis_range=3.0)
    theta_true = sim.theta_from(-0.0015, 1.2)
    y = synthetic(sim, theta_true)
    inside = mcmc.log_posterior(theta_true, sim, y)
    assert np.isfinite(inside)
    outside = mcmc.log_posterior(np.array([sim.prior_high[0] + 1, 0.0]), sim, y)
    assert np.isneginf(outside)
    batch = mcmc.log_posterior(np.stack([theta_true, theta_true + 0.5]), sim, y)
    assert batch.shape == (2,) and batch[0] > batch[1]


def test_burn_in_must_leave_samples():
    sim = sm.SoftSimulator(SOFT_GRID, axis_range=3.0)
    y = synthetic(sim, sim.theta_from(-0.0015, 1.2))
    with pytest.raises(ValueError):
        mcmc.run_mcmc(sim, y, seed=3, n_steps=60)


def test_mcmc_is_seeded():
    sim = sm.SoftSimulator(SOFT_GRID, axis_range=3.0)
    y = synthetic(sim, sim.theta_from(-0.0015, 1.2))
    a = mcmc.run_mcmc(sim, y, seed=3, n_steps=60, burn=20)
    b = mcmc.run_mcmc(sim, y, seed=3, n_steps=60, burn=20)
    assert np.array_equal(a.chain, b.chain)


def test_posterior_round_trips_through_npz(tmp_path):
    sim = sm.SoftSimulator(SOFT_GRID, axis_range=3.0)
    theta_true = sim.theta_from(-0.0015, 1.2)
    y = synthetic(sim, theta_true)
    result = mcmc.run_mcmc(sim, y, seed=4, n_steps=60, burn=20)
    path = tmp_path / "mcmc_test.npz"
    mcmc.save_posterior(path, result, sim, y, theta_true, key="test", model="soft")
    loaded = mcmc.load_posterior(path)
    assert np.array_equal(loaded["samples"], result.samples)
    assert np.allclose(loaded["theta_true"], theta_true)
    assert loaded["model"] == "soft" and loaded["key"] == "test"
    assert list(loaded["param_names"]) == list(sim.param_names)
