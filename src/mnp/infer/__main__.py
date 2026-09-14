"""``python -m mnp.infer {mcmc,npe,sbc,figures}`` — D4 inference on the printed-curve bank.

``mcmc``   emcee posterior per complete bank row on the row's own grid (digitised points when
           ``data/raw/digitised/<dataset>.csv`` exists, else a synthetic observation from the
           printed fit); writes ``data/processed/posteriors/mcmc_<key>.npz`` and the recovery
           and same-zeta figures.
``npe``    trains sbi NPE on the reference grid (``--n-sims``), saves ``npe_<model>.pt`` and
           ``sims.npz``, then infers every complete row of that model from a synthetic
           observation on the reference grid (``npe_<key>.npz``).
``sbc``    simulation-based calibration of the saved NPE; ``out/tables/d4_sbc.csv`` and
           ``out/figures/d4_sbc_ranks.png``.
``figures`` regenerates every D4 inference figure from what is on disk.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

from mnp import config
from mnp.ek import qa
from mnp.infer import figures, mcmc
from mnp.infer import simulator as sm

POSTERIOR_DIR = config.DATA_PROCESSED / "posteriors"
SIMS_PATH = config.DATA_PROCESSED / "sims.npz"
MODELS = ("soft", "hard")


def npe_path(model: str) -> Path:
    return config.DATA_PROCESSED / f"npe_{model}.pt"


def sbc_path(model: str) -> Path:
    return config.DATA_PROCESSED / f"sbc_ranks_{model}.npz"


def complete_rows(bank_path: Path, model: str | None = None) -> list[qa.PrintedFit]:
    bank = qa.load_bank(bank_path)
    return [f for f in bank if f.complete and (model is None or f.model == model)]


def print_recovery(names, theta_true, mean, std) -> None:
    for name, true, m, s in zip(names, theta_true, mean, std, strict=True):
        z = (m - true) / s if s > 0 else float("nan")
        print(f"    {name:22s} printed {true:9.4f}   inferred {m:9.4f} ± {s:.4f}   z = {z:+.2f}")


def write_static_figures(posterior_dir: Path, figures_dir: Path) -> None:
    figures_dir.mkdir(parents=True, exist_ok=True)
    records = figures.load_recovery_records(posterior_dir)
    figures.recovery_figure(records, figures_dir / "d4_recovery.png")
    matched = figures.same_zeta_figure(figures_dir / "d4_same_zeta.png")
    print(f"figures: {figures_dir}/d4_recovery.png ({len(records)} rows), d4_same_zeta.png")
    print(f"  same zeta: {matched['zeta_apparent_mV']:.1f} mV at {matched['I_match_mM']:g} mM; "
          f"hard {matched['hard']}, soft {matched['soft']}")  # fmt: skip


def cmd_mcmc(args) -> int:
    config.ensure_dirs()
    args.posterior_dir.mkdir(parents=True, exist_ok=True)
    for i, fit in enumerate(complete_rows(args.bank)):
        sim, theta_true = sm.simulator_for_fit(fit)
        digitised = qa.load_digitised(fit, args.digitised_dir)
        if digitised is not None:
            ionic, y = digitised
            sim, observation = sim.with_grid(ionic), "digitised"
        else:
            y = sim.simulate(theta_true, np.random.default_rng(args.seed + i))
            observation = "synthetic"
        result = mcmc.run_mcmc(
            sim, y, seed=args.seed, n_walkers=args.n_walkers, n_steps=args.n_steps
        )
        out = args.posterior_dir / f"mcmc_{fit.key}.npz"
        mcmc.save_posterior(out, result, sim, y, theta_true, fit.key, fit.model, observation)
        print(f"{fit.key} [{observation}] acceptance {result.acceptance:.2f} -> {out.name}")
        print_recovery(sim.param_names, theta_true, result.mean, result.std)
    write_static_figures(args.posterior_dir, args.figures)
    return 0


def cmd_npe(args) -> int:
    from mnp.infer import npe  # torch import only when asked for

    config.ensure_dirs()
    args.posterior_dir.mkdir(parents=True, exist_ok=True)
    for model in MODELS if args.model == "both" else (args.model,):
        sim = sm.reference_simulator(model)
        theta, x = npe.simulate_training_set(sim, args.n_sims, args.seed)
        npe.save_sims(SIMS_PATH, model, theta, x)
        posterior = npe.train_npe(sim, seed=args.seed, theta=theta, x=x)
        npe.save_posterior(posterior, npe_path(model))
        print(f"trained NPE ({model}) on {args.n_sims} simulations -> {npe_path(model)}")
        for i, fit in enumerate(complete_rows(args.bank, model)):
            _, theta_true = sm.simulator_for_fit(fit)
            x_obs = sim.simulate(theta_true, np.random.default_rng(args.seed + 1000 + i))
            samples = npe.sample_posterior(posterior, x_obs, n=args.n_samples, seed=args.seed)
            out = args.posterior_dir / f"npe_{fit.key}.npz"
            np.savez(
                out, samples=samples, mean=samples.mean(axis=0), std=samples.std(axis=0),
                theta_true=theta_true, x_obs=x_obs, I_grid_mM=sim.I_grid_mM, key=fit.key,
                model=model, param_names=np.array(sim.param_names),
                observation="synthetic (reference grid, 25 °C)",
            )  # fmt: skip
            print(f"{fit.key} -> {out.name}")
            print_recovery(sim.param_names, theta_true, samples.mean(axis=0), samples.std(axis=0))
    write_static_figures(args.posterior_dir, args.figures)
    return 0


def cmd_sbc(args) -> int:
    from mnp.infer import npe

    config.ensure_dirs()
    models = MODELS if args.model == "both" else (args.model,)
    ranks_all, names_all, pvalues_all, table = [], [], [], []
    for model in models:
        if not npe_path(model).is_file():
            print(f"{npe_path(model)} missing: run `python -m mnp.infer npe --model {model}` first",
                  file=sys.stderr)  # fmt: skip
            return 2
        posterior = npe.load_posterior(npe_path(model))
        sim = sm.reference_simulator(model)
        ranks = npe.sbc_ranks(posterior, sim, args.n_sbc, args.n_post, args.seed)
        pvalues = npe.sbc_ks_pvalues(ranks, args.n_post)
        np.savez(sbc_path(model), ranks=ranks, n_post=args.n_post, pvalues=pvalues,
                 param_names=np.array(sim.param_names), model=model)  # fmt: skip
        ranks_all.append(ranks)
        names_all += [f"{model}: {figures.PARAM_LABELS.get(n, n)}" for n in sim.param_names]
        pvalues_all.append(pvalues)
        for name, p in zip(sim.param_names, pvalues, strict=True):
            table.append({"model": model, "param": name, "n_sbc": args.n_sbc, "n_post": args.n_post,
                          "ks_pvalue": p, "pass": bool(p > 0.01)})  # fmt: skip
            print(f"SBC {model:5s} {name:22s} KS p = {p:.3f} {'pass' if p > 0.01 else 'FAIL'}")
    args.tables.mkdir(parents=True, exist_ok=True)
    with (args.tables / "d4_sbc.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(table[0]))
        writer.writeheader()
        writer.writerows(table)
    figures.sbc_figure(np.hstack(ranks_all), args.n_post, args.figures / "d4_sbc_ranks.png",
                       names_all, np.concatenate(pvalues_all), model="+".join(models))  # fmt: skip
    print(f"table: {args.tables}/d4_sbc.csv; figure: {args.figures}/d4_sbc_ranks.png")
    return 0 if all(row["pass"] for row in table) else 1


def cmd_figures(args) -> int:
    write_static_figures(args.posterior_dir, args.figures)
    saved = [m for m in MODELS if sbc_path(m).is_file()]
    if saved:
        loaded = [figures.load_npz(sbc_path(m)) for m in saved]
        names = [f"{d['model']}: {figures.PARAM_LABELS.get(n, n)}" for d in loaded
                 for n in d["param_names"]]  # fmt: skip
        figures.sbc_figure(np.hstack([d["ranks"] for d in loaded]), int(loaded[0]["n_post"]),
                           args.figures / "d4_sbc_ranks.png", names,
                           np.concatenate([d["pvalues"] for d in loaded]),
                           model="+".join(saved))  # fmt: skip
        print(f"figure: {args.figures}/d4_sbc_ranks.png")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m mnp.infer")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--bank", type=Path, default=qa.BANK_PATH)
        p.add_argument("--posterior-dir", type=Path, default=POSTERIOR_DIR)
        p.add_argument("--figures", type=Path, default=config.OUT_FIGURES)
        p.add_argument("--tables", type=Path, default=config.OUT_TABLES)
        p.add_argument("--seed", type=int, default=0)

    p = sub.add_parser("mcmc", help="emcee posterior for every complete printed fit")
    common(p)
    p.add_argument("--digitised-dir", type=Path, default=qa.DIGITISED_DIR)
    p.add_argument("--n-walkers", type=int, default=mcmc.N_WALKERS)
    p.add_argument("--n-steps", type=int, default=mcmc.N_STEPS)
    p.set_defaults(func=cmd_mcmc)

    p = sub.add_parser("npe", help="train sbi NPE and infer every complete printed fit")
    common(p)
    p.add_argument("--n-sims", type=int, required=True)
    p.add_argument("--model", choices=("soft", "hard", "both"), default="soft")
    p.add_argument("--n-samples", type=int, default=2000)
    p.set_defaults(func=cmd_npe)

    p = sub.add_parser("sbc", help="simulation-based calibration of the saved NPE")
    common(p)
    p.add_argument("--model", choices=("soft", "hard", "both"), default="soft")
    p.add_argument("--n-sbc", type=int, default=200)
    p.add_argument("--n-post", type=int, default=100)
    p.set_defaults(func=cmd_sbc)

    p = sub.add_parser("figures", help="regenerate D4 inference figures from disk")
    common(p)
    p.set_defaults(func=cmd_figures)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
