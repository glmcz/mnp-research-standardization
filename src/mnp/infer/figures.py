"""D4 figures: recovery vs printed fits, SBC rank histograms and "same zeta, different
(ρ, λ, d)". Matplotlib only — no sbi or torch — and every function takes its output path so
the report module can call it with its own directories.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
from scipy.optimize import brentq

from mnp.ek import constants, hard, soft
from mnp.ek.qa import MU_UNIT, PALETTE, style_axes

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import NullFormatter  # noqa: E402

PARAM_LABELS = {
    "log10_absZN_M": "log₁₀ |ZN| (M)",
    "log10_lambda_inv_nm": "log₁₀ (1/λ) (nm)",
    "sigma_C_m2": "σ (C/m²)",
    "log10_radius_nm": "log₁₀ a (nm)",
}
NOISE_NOTE = (
    "synthetic observations from printed fits; noise 5 % relative + 1.5 % of axis range (assumed)"
)
MARK = dict(ms=6, mew=1.5, mec=PALETTE["surface"])  # ≥ 8 px marker with a surface ring


def load_npz(path) -> dict:
    with np.load(path, allow_pickle=False) as data:
        return {k: (data[k].item() if data[k].ndim == 0 else data[k]) for k in data.files}


def load_recovery_records(posterior_dir) -> list[dict]:
    """Merge ``mcmc_<key>.npz`` and ``npe_<key>.npz`` files into one record per key."""
    posterior_dir = Path(posterior_dir)
    records: dict[str, dict] = {}

    def fresh(d: dict) -> dict:
        return {
            "key": d["key"],
            "label": d["key"],
            "model": d["model"],
            "param_names": tuple(d["param_names"]),
            "theta_true": np.asarray(d["theta_true"], dtype=float),
            "mcmc_mean": None,
            "mcmc_std": None,
            "npe_mean": None,
            "npe_std": None,
            "observation": d.get("observation", "synthetic"),
        }

    for prefix in ("mcmc", "npe"):
        for path in sorted(posterior_dir.glob(f"{prefix}_*.npz")):
            d = load_npz(path)
            rec = records.setdefault(d["key"], fresh(d))
            rec[f"{prefix}_mean"] = np.asarray(d["mean"], dtype=float)
            rec[f"{prefix}_std"] = np.asarray(d["std"], dtype=float)
    return list(records.values())


def recovery_figure(records: list[dict], path, note: str = NOISE_NOTE) -> None:
    """Printed parameter (x) against the inferred mean ± 2σ (y), one panel per parameter."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    names: list[str] = []
    for rec in records:
        names += [n for n in rec["param_names"] if n not in names]
    ncols = min(2, max(1, len(names)))
    nrows = max(1, -(-len(names) // ncols))
    blue, orange = PALETTE["series"][:2]
    fig, axes = plt.subplots(
        nrows, ncols, figsize=(4.6 * ncols, 3.8 * nrows), squeeze=False,
        facecolor=PALETTE["surface"],
    )  # fmt: skip
    for ax in axes.flat:
        ax.set_visible(False)
    for ax, name in zip(axes.flat, names, strict=False):
        ax.set_visible(True)
        style_axes(ax)
        printed = []
        for rec in records:
            if name not in rec["param_names"]:
                continue
            j = rec["param_names"].index(name)
            x = float(rec["theta_true"][j])
            printed.append(x)
            if rec["mcmc_mean"] is not None:
                ax.errorbar(x, rec["mcmc_mean"][j], yerr=2 * rec["mcmc_std"][j], fmt="o",
                            color=blue, elinewidth=1.5, capsize=0, label="MCMC (emcee), ±2σ",
                            **MARK)  # fmt: skip
            if rec["npe_mean"] is not None:
                ax.errorbar(x, rec["npe_mean"][j], yerr=2 * rec["npe_std"][j], fmt="^",
                            color=orange, elinewidth=1.5, capsize=0, label="NPE (sbi), ±2σ",
                            **MARK)  # fmt: skip
        if printed:
            lo, hi = min(printed), max(printed)
            pad = 0.15 * ((hi - lo) or 1.0)
            ax.plot([lo - pad, hi + pad], [lo - pad, hi + pad], color=PALETTE["axis"], lw=1,
                    zorder=0)  # fmt: skip
        label = PARAM_LABELS.get(name, name)
        ax.set_xlabel(f"printed {label}")
        ax.set_ylabel(f"inferred {label}")
        ax.set_title(label, fontsize=10)
        handles, labels = ax.get_legend_handles_labels()
        unique = dict(zip(labels, handles, strict=True))
        if unique:
            ax.legend(unique.values(), unique.keys(), fontsize=8, frameon=False,
                      labelcolor=PALETTE["ink2"])  # fmt: skip
    if not names:
        axes[0, 0].set_visible(True)
        axes[0, 0].text(0.5, 0.5, "no posteriors found", ha="center", va="center")
    fig.suptitle("D4 recovery: printed fits vs inferred parameters", fontsize=11,
                 color=PALETTE["ink"])  # fmt: skip
    fig.text(0.5, 0.008, note, ha="center", fontsize=7.5, color=PALETTE["muted"])
    fig.tight_layout(rect=(0, 0.03, 1, 0.97))
    fig.savefig(path, dpi=130, facecolor=PALETTE["surface"])
    plt.close(fig)


def sbc_figure(ranks, n_post: int, path, param_names, pvalues=None, model: str = "") -> None:
    """Rank histograms with the 99 % band a uniform would produce."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ranks = np.asarray(ranks)
    n_sbc, k = ranks.shape
    n_bins = 20
    edges = np.linspace(0, n_post + 1, n_bins + 1)
    expected = n_sbc / n_bins
    half_width = 2.576 * np.sqrt(n_sbc * (1 / n_bins) * (1 - 1 / n_bins))
    blue = PALETTE["series"][0]
    fig, axes = plt.subplots(1, k, figsize=(3.9 * k, 3.4), squeeze=False,
                             facecolor=PALETTE["surface"])  # fmt: skip
    for j, ax in enumerate(axes[0]):
        style_axes(ax)
        ax.axhspan(expected - half_width, expected + half_width, color=blue, alpha=0.10, lw=0)
        ax.axhline(expected, color=PALETTE["axis"], lw=1)
        ax.hist(ranks[:, j], bins=edges, color=blue, edgecolor=PALETTE["surface"], linewidth=1.5)
        title = PARAM_LABELS.get(param_names[j], param_names[j])
        if pvalues is not None:
            title += f"\nKS p = {pvalues[j]:.2f}"
        ax.set_title(title, fontsize=9)
        ax.set_xlabel(f"rank of true θ among {n_post} posterior samples", fontsize=8)
        ax.set_ylabel("count", fontsize=8)
    label = f" ({model} model)" if model else ""
    fig.suptitle(f"Simulation-based calibration{label}: {n_sbc} draws, band = 99 % of uniform",
                 fontsize=10, color=PALETTE["ink"])  # fmt: skip
    fig.tight_layout()
    fig.savefig(path, dpi=130, facecolor=PALETTE["surface"])
    plt.close(fig)


def match_soft_to_mobility(mu_target_1e8, lambda_inv_nm, I_mM, T_C=25.0, z=1) -> float:
    """The (negative) ZN in M whose thick-layer mobility equals the target at I_mM."""

    def gap(log10_zn):
        mu = soft.mobility_soft(-(10.0**log10_zn), lambda_inv_nm * 1e-9, I_mM, z, T_C)
        return mu / MU_UNIT - mu_target_1e8

    return -(10.0 ** brentq(gap, -7.0, 0.5, xtol=1e-13))


def same_zeta_figure(
    path,
    I_match_mM: float = 10.0,
    hard_sigma_C_m2: float = -0.01,
    hard_radius_nm: float = 1000.0,
    soft_lambda_inv_nm: tuple[float, float] = (1.0, 3.0),
    T_C: float = 25.0,
) -> dict:
    """One hard and two soft particles matched by root-finding to the same μ at I_match.

    d is annotated as the thick-layer validity condition d ≥ 5·max(1/λ, 1/κ), not fitted.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    grid = np.logspace(-1, 3, 300)
    radius_m = hard_radius_nm * 1e-9
    mu_hard = hard.mobility_hard(hard_sigma_C_m2, radius_m, grid, T_C=T_C) / MU_UNIT
    mu_match = float(hard.mobility_hard(hard_sigma_C_m2, radius_m, I_match_mM, T_C=T_C) / MU_UNIT)
    zeta_mV = 1e3 * constants.viscosity(T_C) * mu_match * MU_UNIT / constants.permittivity(T_C)
    kappa_inv_low = float(hard.debye_length(grid[0], T_C) * 1e9)
    kappa_inv_match = float(hard.debye_length(I_match_mM, T_C) * 1e9)
    d_required = 5 * max(max(soft_lambda_inv_nm), kappa_inv_low)
    d_required_match = 5 * max(max(soft_lambda_inv_nm), kappa_inv_match)
    softs = []
    for lam in soft_lambda_inv_nm:
        zn = match_soft_to_mobility(mu_match, lam, I_match_mM, T_C)
        mu = soft.mobility_soft(zn, lam * 1e-9, grid, T_C=T_C) / MU_UNIT
        softs.append({"ZN_M": zn, "lambda_inv_nm": lam, "mu": mu})

    blue, orange, aqua = PALETTE["series"][:3]
    fig, ax = plt.subplots(figsize=(7.4, 5.4), facecolor=PALETTE["surface"])
    style_axes(ax)
    hard_label = f"hard sphere: σ = {hard_sigma_C_m2:g} C/m², a = {hard_radius_nm:g} nm"
    ax.semilogx(grid, mu_hard, color=blue, lw=2, solid_capstyle="round", label=hard_label)
    for s, colour in zip(softs, (orange, aqua), strict=True):
        soft_label = f"soft, thick layer: ZN = {s['ZN_M']:.3g} M, 1/λ = {s['lambda_inv_nm']:g} nm"
        ax.semilogx(grid, s["mu"], color=colour, lw=2, solid_capstyle="round", label=soft_label)
    ax.axvline(I_match_mM, color=PALETTE["axis"], lw=1)
    ax.plot([I_match_mM], [mu_match], "o", color=PALETTE["ink"], zorder=5, **MARK)
    ax.annotate(
        f"same μ = {mu_match:.2f} ×10⁻⁸ m² V⁻¹ s⁻¹ at {I_match_mM:g} mM\n"
        f"⇒ same apparent ζ (Smoluchowski) = {zeta_mV:.0f} mV",
        xy=(I_match_mM, mu_match), xytext=(0.56, 0.42), textcoords="axes fraction",
        fontsize=8, color=PALETTE["ink2"], arrowprops=dict(arrowstyle="-", color=PALETTE["axis"]),
    )  # fmt: skip
    ax.text(
        0.02, 0.97,
        "thick-layer model requires d ≥ 5·max(1/λ, 1/κ):\n"
        f"d ≥ {d_required_match:.0f} nm at {I_match_mM:g} mM, d ≥ {d_required:.0f} nm at "
        f"{grid[0]:g} mM\n(d is a validity condition here, not a fitted parameter)",
        transform=ax.transAxes, fontsize=7.5, va="top", color=PALETTE["muted"],
    )  # fmt: skip
    ax.set_xlabel("ionic strength I (mM)")
    ax.set_ylabel("μ (10⁻⁸ m² V⁻¹ s⁻¹)")
    ax.set_title("One zeta potential at 10 mM, three different particles", fontsize=11)
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), fontsize=8, frameon=False,
              labelcolor=PALETTE["ink2"])  # fmt: skip
    fig.tight_layout()
    fig.savefig(path, dpi=130, facecolor=PALETTE["surface"])
    plt.close(fig)
    return {
        "I_match_mM": I_match_mM,
        "mu_match_1e8": mu_match,
        "zeta_apparent_mV": zeta_mV,
        "d_required_nm": d_required,
        "d_required_at_match_nm": d_required_match,
        "hard": {"sigma_C_m2": hard_sigma_C_m2, "radius_nm": hard_radius_nm},
        "soft": [{"ZN_M": s["ZN_M"], "lambda_inv_nm": s["lambda_inv_nm"]} for s in softs],
    }
