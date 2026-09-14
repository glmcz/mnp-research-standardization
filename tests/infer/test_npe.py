"""Phase 9: NPE with sbi (confined to infer/npe.py), simulation-based calibration, figures.

Slow tests (NPE training, SBC) carry ``@pytest.mark.slow`` and run with ``-m slow``.
"""

import re
from pathlib import Path

import numpy as np
import pytest

from mnp import config
from mnp.ek import hard, soft
from mnp.infer import figures, mcmc
from mnp.infer import simulator as sm

IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+(?:sbi|torch)(?:[.\s]|$)", re.MULTILINE)


def test_npe_module_is_the_only_one_importing_sbi_or_torch():
    package = config.ROOT / "src" / "mnp"
    offenders = {
        str(path.relative_to(package))
        for path in package.rglob("*.py")
        if IMPORT_RE.search(path.read_text())
    }
    assert offenders == {"infer/npe.py"}


def test_same_zeta_curves_agree_at_10mM_and_diverge_elsewhere(tmp_path):
    out = figures.same_zeta_figure(tmp_path / "d4_same_zeta.png", I_match_mM=10.0)
    assert (tmp_path / "d4_same_zeta.png").stat().st_size > 1000
    ionic = np.array([0.1, 10.0, 1000.0])
    hard_mu = hard.mobility_hard(out["hard"]["sigma_C_m2"], out["hard"]["radius_nm"] * 1e-9, ionic)
    softs = [soft.mobility_soft(s["ZN_M"], s["lambda_inv_nm"] * 1e-9, ionic) for s in out["soft"]]
    assert len(softs) == 2
    assert out["soft"][0]["lambda_inv_nm"] != out["soft"][1]["lambda_inv_nm"]
    assert out["soft"][0]["ZN_M"] != out["soft"][1]["ZN_M"]
    for mu in softs:
        assert mu[1] == pytest.approx(hard_mu[1], rel=1e-5)  # same μ (same apparent ζ) at 10 mM
        assert abs(mu[0] - hard_mu[0]) > 0.05 * abs(hard_mu[0])
        assert abs(mu[2] - hard_mu[2]) > 0.05 * abs(hard_mu[2])
    assert out["mu_match_1e8"] == pytest.approx(hard_mu[1] / sm.MU_UNIT)
    assert out["zeta_apparent_mV"] < 0
    assert out["d_required_nm"] > 0


def test_match_soft_to_mobility_solves_for_ZN():
    target = soft.mobility_soft(-0.01, 2e-9, 10.0) / sm.MU_UNIT
    zn = figures.match_soft_to_mobility(target, lambda_inv_nm=2.0, I_mM=10.0)
    assert zn == pytest.approx(-0.01, rel=1e-6)


def test_recovery_figure_writes_png(tmp_path):
    records = [
        {
            "key": "a", "label": "row a", "model": "soft",
            "param_names": ("log10_absZN_M", "log10_lambda_inv_nm"),
            "theta_true": np.array([-2.8, 0.08]),
            "mcmc_mean": np.array([-2.7, 0.1]), "mcmc_std": np.array([0.1, 0.05]),
            "npe_mean": np.array([-2.9, 0.05]), "npe_std": np.array([0.15, 0.06]),
        },
        {
            "key": "b", "label": "row b", "model": "hard",
            "param_names": ("sigma_C_m2", "log10_radius_nm"),
            "theta_true": np.array([-0.07, 3.15]),
            "mcmc_mean": np.array([-0.068, 3.1]), "mcmc_std": np.array([0.005, 0.2]),
            "npe_mean": None, "npe_std": None,
        },
    ]  # fmt: skip
    figures.recovery_figure(records, tmp_path / "d4_recovery.png")
    assert (tmp_path / "d4_recovery.png").stat().st_size > 1000


def test_sbc_figure_writes_png(tmp_path):
    ranks = np.random.default_rng(0).integers(0, 101, size=(200, 2))
    figures.sbc_figure(
        ranks, 100, tmp_path / "d4_sbc_ranks.png", ("log10_absZN_M", "log10_lambda_inv_nm"),
        pvalues=np.array([0.5, 0.2]), model="soft",
    )  # fmt: skip
    assert (tmp_path / "d4_sbc_ranks.png").stat().st_size > 1000


def test_recovery_records_merge_mcmc_and_npe_posteriors_by_key(tmp_path):
    sim = sm.SoftSimulator(sm.SOFT_REFERENCE_GRID_MM, axis_range=3.0)
    theta_true = sim.theta_from(-0.0015, 1.2)
    y = sim.simulate(theta_true, np.random.default_rng(0))
    result = mcmc.run_mcmc(sim, y, seed=0, n_steps=40, burn=10)
    mcmc.save_posterior(tmp_path / "mcmc_k1.npz", result, sim, y, theta_true, "k1", "soft")
    np.savez(
        tmp_path / "npe_k1.npz", samples=np.zeros((5, 2)), mean=np.array([-2.8, 0.1]),
        std=np.array([0.1, 0.1]), theta_true=theta_true, key="k1", model="soft",
        param_names=np.array(sim.param_names),
    )  # fmt: skip
    records = figures.load_recovery_records(tmp_path)
    assert [r["key"] for r in records] == ["k1"]
    assert np.allclose(records[0]["mcmc_mean"], result.mean)
    assert np.allclose(records[0]["npe_mean"], [-2.8, 0.1])
    assert np.allclose(records[0]["theta_true"], theta_true)


@pytest.mark.slow
def test_npe_smoke_train_on_500_simulations():
    from mnp.infer import npe

    sim = sm.reference_simulator("soft")
    posterior = npe.train_npe(sim, n_sims=500, seed=0)
    theta_true = sim.theta_from(-0.0015, 1.2)
    x_obs = sim.simulate(theta_true, np.random.default_rng(1))
    samples = npe.sample_posterior(posterior, x_obs, n=300)
    assert samples.shape == (300, 2)
    assert np.all(samples >= sim.prior_low - 1e-6) and np.all(samples <= sim.prior_high + 1e-6)


@pytest.mark.slow
def test_sbc_ranks_are_uniform_and_the_makino_fit_is_recovered(tmp_path):
    from mnp.infer import npe

    sim = sm.reference_simulator("soft")
    posterior = npe.train_npe(sim, n_sims=4000, seed=0)
    npe.save_posterior(posterior, tmp_path / "npe_soft.pt")
    posterior = npe.load_posterior(tmp_path / "npe_soft.pt")

    ranks = npe.sbc_ranks(posterior, sim, n_sbc=200, n_post=100, seed=1)
    assert ranks.shape == (200, 2)
    assert ranks.min() >= 0 and ranks.max() <= 100
    pvalues = npe.sbc_ks_pvalues(ranks, n_post=100)
    assert np.all(pvalues > 0.01), pvalues

    theta_true = sim.theta_from(-0.0015, 1.2)
    x_obs = sim.simulate(theta_true, np.random.default_rng(2))
    samples = npe.sample_posterior(posterior, x_obs, n=2000)
    assert np.all(np.abs(samples.mean(0) - theta_true) <= 3 * samples.std(0) + 0.1)


def test_slow_tests_are_excluded_by_default():
    assert "-m 'not slow'" in (config.ROOT / "pyproject.toml").read_text()
    assert Path(__file__).name == "test_npe.py"
