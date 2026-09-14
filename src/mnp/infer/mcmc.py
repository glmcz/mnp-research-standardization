"""Reference posterior with emcee: 32 walkers × 400 steps, seeded.

Likelihood: Gaussian with the simulator's own noise model,
log L = −½ Σ ((y − μ(θ)) / s(θ))² − Σ log s(θ), s = sqrt((5 % μ)² + (1.5 % range)²),
plus the uniform box prior. Walkers start in a small ball around the MAP (Nelder–Mead from
the best of 256 prior draws) so 400 steps are enough for a two-parameter posterior.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import emcee
import numpy as np
from scipy.optimize import minimize

from mnp.infer.simulator import Simulator

N_WALKERS = 32
N_STEPS = 400
BURN = 100


def log_posterior(theta, sim: Simulator, y_obs):
    theta = np.asarray(theta, dtype=float)
    batch = np.atleast_2d(theta)
    y = np.asarray(y_obs, dtype=float)
    out = np.full(batch.shape[0], -np.inf)
    inside = np.isfinite(sim.log_prior(batch))
    if np.any(inside):
        mu = sim.forward(batch[inside])
        s = sim.noise_std(mu)
        out[inside] = -0.5 * np.sum(((y - mu) / s) ** 2, axis=-1) - np.sum(np.log(s), axis=-1)
    return out[0] if theta.ndim == 1 else out


@dataclass
class MCMCResult:
    samples: np.ndarray  # (n_walkers · (n_steps − burn), 2)
    chain: np.ndarray  # (n_steps, n_walkers, 2)
    mean: np.ndarray
    std: np.ndarray
    acceptance: float
    param_names: tuple[str, str]
    theta_map: np.ndarray


def run_mcmc(
    sim: Simulator,
    y_obs,
    seed: int = 0,
    n_walkers: int = N_WALKERS,
    n_steps: int = N_STEPS,
    burn: int = BURN,
) -> MCMCResult:
    if burn >= n_steps:
        raise ValueError(f"burn ({burn}) must be smaller than n_steps ({n_steps})")
    y = np.asarray(y_obs, dtype=float)
    rng = np.random.default_rng(seed)
    starts = sim.sample_prior(rng, 256)
    best = starts[int(np.argmax(log_posterior(starts, sim, y)))]
    opt = minimize(lambda t: -log_posterior(t, sim, y), best, method="Nelder-Mead")
    center = opt.x if np.isfinite(opt.fun) and np.isfinite(sim.log_prior(opt.x)) else best
    width = sim.prior_high - sim.prior_low
    p0 = center + 0.01 * width * rng.standard_normal((n_walkers, 2))
    p0 = np.clip(p0, sim.prior_low + 1e-6 * width, sim.prior_high - 1e-6 * width)

    sampler = emcee.EnsembleSampler(n_walkers, 2, log_posterior, args=(sim, y), vectorize=True)
    sampler.random_state = np.random.RandomState(seed).get_state()
    sampler.run_mcmc(p0, n_steps, progress=False)
    chain = sampler.get_chain()
    samples = sampler.get_chain(discard=burn, flat=True)
    return MCMCResult(
        samples=samples,
        chain=chain,
        mean=samples.mean(axis=0),
        std=samples.std(axis=0),
        acceptance=float(np.mean(sampler.acceptance_fraction)),
        param_names=tuple(sim.param_names),
        theta_map=np.asarray(center, dtype=float),
    )


def save_posterior(
    path, result: MCMCResult, sim: Simulator, y_obs, theta_true, key, model, observation="synthetic"
):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        path,
        samples=result.samples,
        chain=result.chain,
        mean=result.mean,
        std=result.std,
        acceptance=result.acceptance,
        theta_map=result.theta_map,
        param_names=np.array(result.param_names),
        y_obs=np.asarray(y_obs, dtype=float),
        I_grid_mM=sim.I_grid_mM,
        axis_range=sim.axis_range,
        T_C=sim.T_C,
        theta_true=np.asarray(theta_true, dtype=float),
        key=str(key),
        model=str(model),
        observation=str(observation),
    )


def load_posterior(path) -> dict:
    with np.load(path, allow_pickle=False) as data:
        return {k: (data[k].item() if data[k].ndim == 0 else data[k]) for k in data.files}
