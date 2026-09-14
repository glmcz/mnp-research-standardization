"""Forward-model wrappers θ → μ(I_grid) for inference, in 10⁻⁸ m² V⁻¹ s⁻¹.

Soft (Ohshima 1994): θ = (log10 |ZN| [M], log10 (1/λ) [nm]); ZN is taken negative (every
particle in the bank is anionic). Hard: θ = (σ [C/m²], log10 a [nm]) with KCl and the
Grahame surface potential as ζ. Priors are uniform boxes wide enough to contain every printed
fit in ``printed_params.csv``.

Noise model, ASSUMED (no digitising has been done to estimate it): each observed point is
μ_clean + ε with ε ~ N(0, σ²), σ² = (5 % · μ_clean)² + (1.5 % · axis range)². The axis range
is the y-axis span of the figure the data would be digitised from — 3 ×10⁻⁸ for Makino &
Ohshima 2011 Fig. 2, 12 ×10⁻⁸ for Kobayashi 2008 Fig. 1 — and is the module-level default
per model for rows whose figure was not looked at.
"""

from __future__ import annotations

import copy

import numpy as np

from mnp.ek import hard, qa, soft

MU_UNIT = 1e-8
REL_NOISE = 0.05
AXIS_NOISE = 0.015
MAKINO_FIG2_AXIS_RANGE = 3.0  # y-axis 0 … −3 µm s⁻¹ V⁻¹ cm
KOBAYASHI_FIG1_AXIS_RANGE = 12.0  # y-axis 0 … −12 ×10⁻⁸ m² V⁻¹ s⁻¹
SOFT_REFERENCE_GRID_MM = np.logspace(0, np.log10(200), 8)  # Makino sweep, ~8 points
HARD_REFERENCE_GRID_MM = np.logspace(-1, np.log10(200), 8)  # Kobayashi sweep


class Simulator:
    param_names: tuple[str, str]
    prior_low: np.ndarray
    prior_high: np.ndarray
    model: str

    def __init__(self, I_grid_mM, axis_range: float, T_C: float = 25.0, z: int = 1):
        self.I_grid_mM = np.asarray(I_grid_mM, dtype=float)
        self.axis_range = float(axis_range)
        self.T_C = float(T_C)
        self.z = int(z)

    @property
    def n_obs(self) -> int:
        return len(self.I_grid_mM)

    def with_grid(self, I_grid_mM) -> Simulator:
        """Same model, temperature and noise on another set of ionic strengths."""
        clone = copy.copy(self)
        clone.I_grid_mM = np.asarray(I_grid_mM, dtype=float)
        return clone

    def _mobility(self, theta: np.ndarray) -> np.ndarray:
        raise NotImplementedError

    def forward(self, theta) -> np.ndarray:
        """Clean μ(I_grid) in 10⁻⁸ units; (n_obs,) for one θ, (n, n_obs) for a batch."""
        theta = np.asarray(theta, dtype=float)
        mu = self._mobility(np.atleast_2d(theta)) / MU_UNIT
        return mu[0] if theta.ndim == 1 else mu

    def noise_std(self, mu_clean) -> np.ndarray:
        mu_clean = np.asarray(mu_clean, dtype=float)
        return np.sqrt((REL_NOISE * mu_clean) ** 2 + (AXIS_NOISE * self.axis_range) ** 2)

    def simulate(self, theta, rng: np.random.Generator) -> np.ndarray:
        clean = self.forward(theta)
        return clean + rng.standard_normal(clean.shape) * self.noise_std(clean)

    def sample_prior(self, rng: np.random.Generator, n: int) -> np.ndarray:
        return rng.uniform(self.prior_low, self.prior_high, size=(n, 2))

    def log_prior(self, theta):
        theta = np.asarray(theta, dtype=float)
        inside = np.all((theta >= self.prior_low) & (theta <= self.prior_high), axis=-1)
        return np.where(inside, 0.0, -np.inf)

    def theta_from(self, first, second) -> np.ndarray:
        raise NotImplementedError

    def params_from(self, theta) -> tuple[float, float]:
        raise NotImplementedError


class SoftSimulator(Simulator):
    model = "soft"
    param_names = ("log10_absZN_M", "log10_lambda_inv_nm")
    prior_low = np.array([-5.0, -0.5])  # 10 µM … 0.32 M; 0.32 nm … 32 nm
    prior_high = np.array([-0.5, 1.5])
    sign = -1.0

    def _mobility(self, theta):
        zn = self.sign * 10 ** theta[:, :1]
        lam_inv = 1e-9 * 10 ** theta[:, 1:2]
        return soft.mobility_soft(zn, lam_inv, self.I_grid_mM[None, :], self.z, self.T_C)

    def theta_from(self, ZN_M, lambda_inv_nm):
        return np.array([np.log10(abs(ZN_M)), np.log10(lambda_inv_nm)])

    def params_from(self, theta):
        return self.sign * 10 ** float(theta[0]), 10 ** float(theta[1])


class HardSimulator(Simulator):
    model = "hard"
    param_names = ("sigma_C_m2", "log10_radius_nm")
    prior_low = np.array([-0.15, 1.0])  # 10 nm … 3.2 µm
    prior_high = np.array([-0.001, 3.5])

    def __init__(self, I_grid_mM, axis_range, T_C=25.0, z=1, electrolyte="KCl"):
        super().__init__(I_grid_mM, axis_range, T_C, z)
        self.electrolyte = electrolyte

    def _mobility(self, theta):
        sigma = theta[:, :1]
        radius = 1e-9 * 10 ** theta[:, 1:2]
        return hard.mobility_hard(
            sigma, radius, self.I_grid_mM[None, :], self.z, self.T_C, self.electrolyte
        )

    def theta_from(self, sigma_C_m2, radius_nm):
        return np.array([sigma_C_m2, np.log10(radius_nm)])

    def params_from(self, theta):
        return float(theta[0]), 10 ** float(theta[1])


def reference_simulator(model: str, T_C: float = 25.0) -> Simulator:
    """The fixed-grid simulator NPE is trained on (one per model)."""
    if model == "hard":
        return HardSimulator(HARD_REFERENCE_GRID_MM, KOBAYASHI_FIG1_AXIS_RANGE, T_C)
    return SoftSimulator(SOFT_REFERENCE_GRID_MM, MAKINO_FIG2_AXIS_RANGE, T_C)


def simulator_for_fit(fit: qa.PrintedFit) -> tuple[Simulator, np.ndarray]:
    """Simulator on the row's own grid and temperature, plus the printed θ."""
    if fit.model == "hard":
        sim = HardSimulator(
            fit.grid(), KOBAYASHI_FIG1_AXIS_RANGE, fit.temperature(), fit.z, fit.electrolyte
        )
        return sim, sim.theta_from(fit.sigma_C_m2, fit.radius_nm)
    sim = SoftSimulator(fit.grid(), MAKINO_FIG2_AXIS_RANGE, fit.temperature(), fit.z)
    return sim, sim.theta_from(fit.zn_M, fit.lambda_inv_nm)
