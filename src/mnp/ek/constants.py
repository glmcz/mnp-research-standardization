"""Physical constants and water properties for the electrokinetic models.

The plan fixes ε_r = 78.5 and η = 0.89 mPa·s at 25 °C. Temperature dependence comes
from two published fits, each rescaled so the 25 °C anchor is exact:

- ε_r(t): Malmberg & Maryott 1956, J. Res. Natl. Bur. Stand. 56:1,
  ε_r = 87.740 − 0.40008 t + 9.398e−4 t² − 1.410e−6 t³ (t in °C, 0–100 °C).
  The polynomial alone gives 78.30 at 25 °C.
- η(T): Vogel form η = 2.414e−5 · 10^(247.8 / (T − 140)) Pa·s (T in K), the CRC Handbook
  parametrisation; 0.8905 mPa·s at 25 °C.

Limiting molar conductances Λ° at 25 °C (S m²/mol) are from the CRC Handbook of Chemistry
and Physics, 82nd ed.; K⁺ and Cl⁻ are the values Kobayashi 2008 used. They set the ionic
drag coefficient in the relaxation term and are not corrected for temperature.
"""

from __future__ import annotations

import numpy as np
from scipy.constants import N_A, e, epsilon_0, k

EPS_R_25C = 78.5
ETA_25C = 0.89e-3  # Pa·s

# ion → (Λ° in S m²/mol, valence)
LIMITING_CONDUCTANCE: dict[str, tuple[float, int]] = {
    "K+": (73.48e-4, 1),
    "Na+": (50.08e-4, 1),
    "Li+": (38.66e-4, 1),
    "Cl-": (76.31e-4, -1),
    "NO3-": (71.42e-4, -1),
}

# electrolyte → (cation, anion); only z:z salts, which is all the models support
ELECTROLYTES: dict[str, tuple[str, str]] = {
    "KCl": ("K+", "Cl-"),
    "NaCl": ("Na+", "Cl-"),
    "LiCl": ("Li+", "Cl-"),
    "KNO3": ("K+", "NO3-"),
    "NaNO3": ("Na+", "NO3-"),
}


def as_float_or_array(x) -> float | np.ndarray:
    arr = np.asarray(x, dtype=float)
    return float(arr) if arr.ndim == 0 else arr


def kelvin(T_C):
    return np.asarray(T_C, dtype=float) + 273.15


def _malmberg_maryott(t_C):
    t = np.asarray(t_C, dtype=float)
    return 87.740 - 0.40008 * t + 9.398e-4 * t**2 - 1.410e-6 * t**3


def eps_r(T_C=25.0):
    """Relative permittivity of water, anchored to 78.5 at 25 °C."""
    return as_float_or_array(EPS_R_25C * _malmberg_maryott(T_C) / _malmberg_maryott(25.0))


def permittivity(T_C=25.0):
    """εε₀ in F/m."""
    return as_float_or_array(eps_r(T_C) * epsilon_0)


def _vogel(T_K):
    return 2.414e-5 * 10 ** (247.8 / (np.asarray(T_K, dtype=float) - 140.0))


def viscosity(T_C=25.0):
    """Viscosity of water in Pa·s, anchored to 0.89 mPa·s at 25 °C."""
    return as_float_or_array(ETA_25C * _vogel(kelvin(T_C)) / _vogel(kelvin(25.0)))


def thermal_voltage(T_C=25.0, z=1):
    """kT/(ze) in volts: 25.69 mV at 25 °C for z = 1."""
    return as_float_or_array(k * kelvin(T_C) / (z * e))


def number_density(c_mM):
    """Number density (m⁻³) of a species at c mM; 1 mM = 1 mol/m³, so this is N_A·c."""
    return N_A * np.asarray(c_mM, dtype=float)
