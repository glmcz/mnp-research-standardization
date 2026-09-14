"""Soft particle: Ohshima 1994 thick-layer mobility (Makino & Ohshima 2011 eqs 1–6).

An ion-penetrable layer of thickness d carrying fixed charges of valence Z at number density N,
softness 1/λ, in a z:z electrolyte of number density n. Valid for d ≫ 1/λ, 1/κ:

  μ = (εε₀/η) · (ψ₀/κ_m + ψ_DON/λ) / (1/κ_m + 1/λ) + ZeN/(ηλ²)
  ψ_DON = (kT/ze) · asinh(ZN/2zn)
  ψ₀ = ψ_DON + (kT/ze) · [1 − sqrt(1 + (ZN/2zn)²)] / (ZN/2zn)
  κ_m = κ (1 + (ZN/2zn)²)^¼

Papers print the layer charge as "zN" in mol/L; ``ZN_M`` here is that signed molar value.
With ZN and c both in mM, ZN/2zn = ZN_mM / (2 z c_mM).
"""

from __future__ import annotations

import numpy as np
from scipy.constants import N_A, e

from mnp.ek import constants
from mnp.ek.constants import as_float_or_array
from mnp.ek.hard import debye_kappa


def _donnan_ratio(ZN_M, c_mM, z):
    """ZN/(2zn), dimensionless."""
    return 1000.0 * np.asarray(ZN_M, dtype=float) / (2 * z * np.asarray(c_mM, dtype=float))


def donnan_potential(ZN_M, c_mM, z=1, T_C=25.0):
    """ψ_DON (V); its sign is the sign of ZN."""
    vt = constants.thermal_voltage(T_C, z)
    return as_float_or_array(vt * np.arcsinh(_donnan_ratio(ZN_M, c_mM, z)))


def surface_potential(ZN_M, c_mM, z=1, T_C=25.0):
    """ψ₀ (V) at the layer/solution boundary; |ψ₀| < |ψ_DON|, same sign."""
    x = _donnan_ratio(ZN_M, c_mM, z)
    safe = np.where(np.abs(x) < 1e-8, 1.0, x)
    correction = np.where(np.abs(x) < 1e-8, -x / 2, (1 - np.sqrt(1 + x**2)) / safe)
    vt = constants.thermal_voltage(T_C, z)
    return as_float_or_array(donnan_potential(ZN_M, c_mM, z, T_C) + vt * correction)


def kappa_m(ZN_M, c_mM, z=1, T_C=25.0):
    """Debye–Hückel parameter of the surface layer (m⁻¹); equals κ when N = 0."""
    x = _donnan_ratio(ZN_M, c_mM, z)
    kappa = debye_kappa(z**2 * np.asarray(c_mM, dtype=float), T_C)
    return as_float_or_array(kappa * (1 + x**2) ** 0.25)


def fixed_charge_density(ZN_M):
    """ZeN in C/m³ from the molar layer charge."""
    return as_float_or_array(e * N_A * 1000.0 * np.asarray(ZN_M, dtype=float))


def plateau_mobility(ZN_M, lambda_inv_m, T_C=25.0):
    """High-salt limit ZeN/(ηλ²) = ZeN (1/λ)² / η, independent of ionic strength."""
    lam_inv = np.asarray(lambda_inv_m, dtype=float)
    return as_float_or_array(fixed_charge_density(ZN_M) * lam_inv**2 / constants.viscosity(T_C))


def mobility_soft(ZN_M, lambda_inv_m, c_mM, z=1, T_C=25.0):
    """Electrophoretic mobility (m² V⁻¹ s⁻¹) of a thick-layer soft particle.

    Broadcasts over ``ZN_M``/``lambda_inv_m`` (e.g. column vectors) against ``c_mM`` (row).
    """
    lam_inv = np.asarray(lambda_inv_m, dtype=float)
    inv_km = 1.0 / kappa_m(ZN_M, c_mM, z, T_C)
    psi_d = donnan_potential(ZN_M, c_mM, z, T_C)
    psi_0 = surface_potential(ZN_M, c_mM, z, T_C)
    prefactor = constants.permittivity(T_C) / constants.viscosity(T_C)
    layer_term = prefactor * (psi_0 * inv_km + psi_d * lam_inv) / (inv_km + lam_inv)
    return as_float_or_array(layer_term + plateau_mobility(ZN_M, lam_inv, T_C))


def layer_thickness_ok(d, lambda_inv, kappa_inv, factor=5.0):
    """Thick-layer validity d ≫ 1/λ, 1/κ, taken as d ≥ factor · max(1/λ, 1/κ). Any one unit."""
    return np.asarray(d) >= factor * np.maximum(np.asarray(lambda_inv), np.asarray(kappa_inv))
