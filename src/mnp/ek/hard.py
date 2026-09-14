"""Hard sphere: Debye length, Grahame charge–potential relation, Henry retardation and the
Ohshima 1983/2001 relaxation correction.

Formulas (all SI; concentrations in mM, which equal mol/m³):

  κ = sqrt(2 N_A e² I / (εε₀ kT)),        I = ionic strength = z² c for a z:z salt
  σ = sqrt(8 εε₀ kT n) sinh(zeψ₀ / 2kT),  n = N_A c   (Grahame)
  f(κa) = 2/3 [1 + 1 / (2 (1 + 2.5 / (κa (1 + 2e^(−κa))))³)]   (Ohshima 1994 fit to Henry)

Relaxation (Ohshima, Healy & White 1983 as simplified by Ohshima 2001, JCIS 239:587; this is
the form Kobayashi 2008 eqs 11–13 used with zero free parameters), z:z electrolyte, κa ≳ 30:

  μ = sgn(ζ) (εε₀/η) [ |ζ| − (2F/(1+F)) (kT/ze) ln((1 + e^(z|ζ̃|/2)) / 2) ]
  F = (2/κa)(1 + 3m)(e^(z|ζ̃|/2) − 1),   ζ̃ = eζ/kT
  m = 2 εε₀ kT λ / (3 η z² e²),   λ = N_A e² |z| / Λ°   (drag coefficient of the counter-ion)

With ``relaxation=False`` the mobility is Henry's, μ = (εε₀ζ/η) f(κa), valid for any κa
but only for low ζ. ζ is taken equal to the Grahame surface potential (no slip-plane shift).
"""

from __future__ import annotations

import numpy as np
from scipy.constants import N_A, e, k

from mnp.ek import constants
from mnp.ek.constants import as_float_or_array

KAPPA_A_MIN = 30.0  # Kobayashi 2008: "Ohshima's equations are valid when κa ≥ 30"


def debye_kappa(I_mM, T_C=25.0):
    """Debye–Hückel parameter κ (m⁻¹) for ionic strength I in mM."""
    ionic = np.asarray(I_mM, dtype=float)  # mol/m³
    kT = k * constants.kelvin(T_C)
    return as_float_or_array(np.sqrt(2 * N_A * e**2 * ionic / (constants.permittivity(T_C) * kT)))


def debye_length(I_mM, T_C=25.0):
    """Debye length 1/κ (m). 150 mM, 25 °C → 0.79 nm."""
    return as_float_or_array(1.0 / debye_kappa(I_mM, T_C))


def _grahame_scale(c_mM, T_C):
    kT = k * constants.kelvin(T_C)
    return np.sqrt(8 * constants.permittivity(T_C) * kT * constants.number_density(c_mM))


def grahame_sigma(psi0_V, c_mM, z=1, T_C=25.0):
    """Surface charge density (C/m²) from surface potential, z:z electrolyte at c mM."""
    vt = constants.thermal_voltage(T_C, z)
    return as_float_or_array(_grahame_scale(c_mM, T_C) * np.sinh(np.asarray(psi0_V) / (2 * vt)))


def grahame_psi0(sigma_C_m2, c_mM, z=1, T_C=25.0):
    """Inverse of Grahame: ψ₀ = (2kT/ze) asinh(σ / sqrt(8εε₀kTn))."""
    vt = constants.thermal_voltage(T_C, z)
    ratio = np.asarray(sigma_C_m2) / _grahame_scale(c_mM, T_C)
    return as_float_or_array(2 * vt * np.arcsinh(ratio))


def henry_f(kappa_a):
    """Henry's function, Ohshima's approximation: 2/3 at κa → 0, 1 at κa → ∞."""
    ka = np.asarray(kappa_a, dtype=float)
    inner = 1 + 2.5 / (ka * (1 + 2 * np.exp(-ka)))
    return as_float_or_array(2 / 3 * (1 + 1 / (2 * inner**3)))


def ionic_drag_m(ion: str, T_C=25.0) -> float:
    """Dimensionless ionic drag coefficient m = 2εε₀kT N_A / (3η|z|Λ°)."""
    conductance, valence = constants.LIMITING_CONDUCTANCE[ion]
    kT = k * constants.kelvin(T_C)
    return float(
        2
        * constants.permittivity(T_C)
        * kT
        * N_A
        / (3 * constants.viscosity(T_C) * abs(valence) * conductance)
    )


def relaxation_correction(zeta_V, kappa_a, m, z=1, T_C=25.0):
    """Potential (V) subtracted from |ζ| by double-layer relaxation; ≥ 0."""
    vt = constants.thermal_voltage(T_C, z)
    half = np.exp(np.abs(np.asarray(zeta_V)) / (2 * vt))  # e^(z|ζ̃|/2)
    F = (2 / np.asarray(kappa_a)) * (1 + 3 * m) * (half - 1)
    return (2 * F / (1 + F)) * vt * np.log((1 + half) / 2)


def mobility_hard(sigma_C_m2, radius_m, c_mM, z=1, T_C=25.0, electrolyte="KCl", relaxation=True):
    """Electrophoretic mobility (m² V⁻¹ s⁻¹) of a hard sphere of radius a with constant σ.

    Broadcasts over ``sigma_C_m2``/``radius_m`` (e.g. column vectors) against ``c_mM`` (row).
    """
    sigma = np.asarray(sigma_C_m2, dtype=float)
    zeta = grahame_psi0(sigma, c_mM, z, T_C)
    kappa_a = debye_kappa(z**2 * np.asarray(c_mM, dtype=float), T_C) * np.asarray(radius_m)
    prefactor = constants.permittivity(T_C) / constants.viscosity(T_C)
    if not relaxation:
        return as_float_or_array(prefactor * zeta * henry_f(kappa_a))
    cation, anion = constants.ELECTROLYTES[electrolyte]
    m = np.where(zeta < 0, ionic_drag_m(cation, T_C), ionic_drag_m(anion, T_C))
    corrected = np.abs(zeta) - relaxation_correction(zeta, kappa_a, m, z, T_C)
    return as_float_or_array(np.sign(zeta) * prefactor * corrected)


def kappa_a_ok(kappa_a, minimum=KAPPA_A_MIN):
    """Validity of the large-κa relaxation expression."""
    return np.asarray(kappa_a) >= minimum
