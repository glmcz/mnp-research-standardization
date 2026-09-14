"""Neural posterior estimation with sbi 0.27 — the only module that imports sbi or torch.

Training follows the pinned API: ``NPE(prior).append_simulations(theta, x).train()`` and
``build_posterior()``. Simulation-based calibration (Talts et al. 2018): for n_sbc prior
draws θ_i with simulated x_i, the rank of θ_i among n_post posterior samples is uniform on
{0, …, n_post} when the posterior is calibrated; a KS test per parameter gives the p-value.
Ranks are jittered inside their bin before the KS test so the null is exactly continuous
uniform (the discrete lattice would otherwise bias the statistic by ~1/n_post).

Observations are embedded as x' = arcsinh(μ / 10⁻⁸ m² V⁻¹ s⁻¹) before training, inference
and SBC. The map is a bijection, so the posterior is unchanged, but the corner of the soft
prior with |ZN| ~ 0.3 M and 1/λ ~ 30 nm produces |μ| up to ~3000 ×10⁻⁸ (1 % of draws exceed
770) while every particle in the bank sits below 12; without the compression sbi's z-scoring
squeezes the realistic region into a sliver and the soft NPE fails SBC (KS p ≈ 0.001).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
from sbi.inference import NPE
from sbi.utils import BoxUniform
from scipy.stats import kstest

from mnp.infer.simulator import Simulator

DEFAULT_N_SIMS = 5000
X_SCALE = 1.0  # in 10⁻⁸ m² V⁻¹ s⁻¹: linear below ~1, logarithmic above


def embed(x) -> np.ndarray:
    """arcsinh compression of the mobility observation; applied everywhere x enters sbi."""
    return np.arcsinh(np.asarray(x, dtype=float) / X_SCALE)


def make_prior(sim: Simulator) -> BoxUniform:
    return BoxUniform(
        low=torch.as_tensor(sim.prior_low, dtype=torch.float32),
        high=torch.as_tensor(sim.prior_high, dtype=torch.float32),
    )


def simulate_training_set(sim: Simulator, n_sims: int, seed: int = 0):
    rng = np.random.default_rng(seed)
    theta = sim.sample_prior(rng, n_sims)
    return theta, sim.simulate(theta, rng)


def train_npe(sim: Simulator, n_sims: int = DEFAULT_N_SIMS, seed: int = 0, theta=None, x=None):
    if theta is None or x is None:
        theta, x = simulate_training_set(sim, n_sims, seed)
    torch.manual_seed(seed)
    inference = NPE(prior=make_prior(sim), show_progress_bars=False)
    inference.append_simulations(
        torch.as_tensor(np.asarray(theta), dtype=torch.float32),
        torch.as_tensor(embed(x), dtype=torch.float32),
    )
    estimator = inference.train(show_train_summary=False)
    return inference.build_posterior(estimator)


def sample_posterior(posterior, x_obs, n: int = 2000, seed: int | None = None) -> np.ndarray:
    if seed is not None:
        torch.manual_seed(seed)
    x = torch.as_tensor(embed(x_obs), dtype=torch.float32)
    samples = posterior.sample((n,), x=x, show_progress_bars=False)
    return samples.detach().cpu().numpy().astype(float)


def sbc_ranks(posterior, sim: Simulator, n_sbc=200, n_post=100, seed=0) -> np.ndarray:
    """Rank of each prior draw among n_post posterior samples of its own simulated data."""
    rng = np.random.default_rng(seed)
    torch.manual_seed(seed)
    theta = sim.sample_prior(rng, n_sbc)
    x = sim.simulate(theta, rng)
    ranks = np.empty((n_sbc, theta.shape[1]), dtype=int)
    for i in range(n_sbc):
        ranks[i] = np.sum(sample_posterior(posterior, x[i], n_post) < theta[i], axis=0)
    return ranks


def sbc_ks_pvalues(ranks, n_post: int, seed: int = 0) -> np.ndarray:
    ranks = np.asarray(ranks, dtype=float)
    jitter = np.random.default_rng(seed).uniform(size=ranks.shape)
    u = (ranks + jitter) / (n_post + 1)
    return np.array([kstest(u[:, j], "uniform").pvalue for j in range(u.shape[1])])


def save_posterior(posterior, path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    torch.save(posterior, path)


def load_posterior(path):
    return torch.load(path, weights_only=False)


def save_sims(path, model: str, theta, x) -> None:
    """Keep one sims.npz holding theta_<model>/x_<model> for every trained model."""
    path = Path(path)
    existing = {}
    if path.is_file():
        with np.load(path) as data:
            existing = {k: data[k] for k in data.files}
    existing[f"theta_{model}"] = np.asarray(theta)
    existing[f"x_{model}"] = np.asarray(x)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(path, **existing)
