"""D4: recompute the printed-fit bank, overlay any digitised points, and regenerate
the inference figures from the posteriors on disk.

Heavy work (MCMC, NPE training, SBC) is not done here — `python -m mnp.infer` owns it.
This only renders what exists, so `report all` stays fast and deterministic.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from mnp.ek import qa

FIGURES = ("d4_qa_overlay.png", "d4_recovery.png", "d4_same_zeta.png", "d4_sbc_ranks.png")
TABLES = ("d4_params.csv", "d4_qa_residuals.csv")


def build(out_tables: Path, out_figures: Path, posterior_dir: Path | None = None) -> list[Path]:
    out_tables, out_figures = Path(out_tables), Path(out_figures)
    out_tables.mkdir(parents=True, exist_ok=True)
    out_figures.mkdir(parents=True, exist_ok=True)
    qa.run_qa(tables_dir=out_tables, figures_dir=out_figures)

    from mnp.infer import __main__ as infer_cli  # torch import stays lazy

    posterior_dir = Path(posterior_dir) if posterior_dir else infer_cli.POSTERIOR_DIR
    if posterior_dir.is_dir() and any(posterior_dir.glob("mcmc_*.npz")):
        infer_cli.cmd_figures(SimpleNamespace(posterior_dir=posterior_dir, figures=out_figures))
    written = [out_tables / t for t in TABLES] + [out_figures / f for f in FIGURES]
    return [p for p in written if p.is_file()]
