"""QA of the printed-curve bank.

``data/raw/digitised/printed_params.csv`` holds one row per fitted curve printed in the
datasets doc (parameters only, never digitised values). For every complete row the curve is
recomputed on the paper's own salt grid; when ``<digitised_dir>/<dataset>.csv`` exists its
points (optionally selected by ``figure``/``particle`` columns) are overlaid and gated:

- residual: max |μ_model − μ_digitised| ≤ 2 % of the axis range (max − min of the model
  curve and the points together, in 10⁻⁸ m² V⁻¹ s⁻¹);
- x-values: each digitised I must lie within 10 % of a nominal salt concentration, when the
  doc prints one.

Rows missing a parameter are reported as ``incomplete`` and never silently filled in — the
only defaults are T = 25 °C when the doc gives no temperature (flagged ``T_assumed``) and a
25-point log grid over the stated sweep range when no nominal points are printed.

Validity is surfaced, not enforced: soft rows need d ≥ 5·max(1/λ, 1/κ) (``None`` when d is
not printed), hard rows need κa ≥ 30 for the relaxation expression.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path

import matplotlib
import numpy as np
from scipy.constants import N_A, e

from mnp import config
from mnp.ek import constants, hard, soft

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import NullFormatter  # noqa: E402


def bank_path() -> Path:
    """Resolved on each call: a module-level constant freezes the data root at import time."""
    return config.DATA_RAW / "digitised" / "printed_params.csv"


def digitised_dir() -> Path:
    return config.DATA_RAW / "digitised"


MU_UNIT = 1e-8  # figures print mobility in 10⁻⁸ m² V⁻¹ s⁻¹ (= µm s⁻¹ V⁻¹ cm)
RESIDUAL_GATE = 0.02
X_TOLERANCE = 0.10
DEFAULT_T_C = 25.0
LOG_GRID_POINTS = 25
FARADAY = e * N_A

# D4 figure system (dataviz reference palette, light surface); every D4 figure reads from here.
PALETTE = {
    "series": ("#2a78d6", "#eb6834", "#1baf7a"),  # categorical slots 1–3, fixed order
    "surface": "#fcfcfb",
    "ink": "#0b0b0b",
    "ink2": "#52514e",
    "muted": "#898781",
    "grid": "#e1e0d9",
    "axis": "#c3c2b7",
}


def style_axes(ax) -> None:
    """Recessive chrome: hairline solid grid, two spines, ink-coloured text."""
    ax.set_facecolor(PALETTE["surface"])
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(PALETTE["axis"])
        ax.spines[side].set_linewidth(1.0)
    ax.grid(True, color=PALETTE["grid"], linewidth=0.8, linestyle="-")
    ax.set_axisbelow(True)
    ax.tick_params(colors=PALETTE["muted"], labelcolor=PALETTE["ink2"], length=3, width=0.8)
    ax.xaxis.label.set_color(PALETTE["ink2"])
    ax.yaxis.label.set_color(PALETTE["ink2"])
    ax.title.set_color(PALETTE["ink"])


RESULT_COLUMNS = [
    "dataset", "figure", "particle", "key", "model", "complete", "missing", "T_assumed",
    "grid_source", "n_grid", "n_digitised", "axis_range_1e8", "residual_max_frac",
    "residual_pass", "x_on_grid_pass", "validity_ok", "validity_note", "status",
]  # fmt: skip


def _float(value) -> float | None:
    return None if value is None or str(value).strip() == "" else float(value)


def _grid(value) -> list[float] | None:
    if value is None or str(value).strip() == "":
        return None
    return [float(v) for v in str(value).split(";") if v.strip()]


@dataclass
class PrintedFit:
    dataset: str
    figure: str
    particle: str
    model: str
    sigma_C_m2: float | None = None
    radius_nm: float | None = None
    ZN_M: float | None = None
    rho_C_m3: float | None = None
    lambda_inv_nm: float | None = None
    d_nm: float | None = None
    T_C: float | None = None
    electrolyte: str = ""
    z: int | None = None
    I_grid_mM: list[float] | None = None
    I_min_mM: float | None = None
    I_max_mM: float | None = None
    source_note: str = ""

    @classmethod
    def from_row(cls, row: dict[str, str]) -> PrintedFit:
        z = _float(row.get("z"))
        return cls(
            dataset=row["dataset"].strip(),
            figure=row["figure"].strip(),
            particle=row["particle"].strip(),
            model=row["model"].strip(),
            sigma_C_m2=_float(row.get("sigma_C_m2")),
            radius_nm=_float(row.get("radius_nm")),
            ZN_M=_float(row.get("ZN_M")),
            rho_C_m3=_float(row.get("rho_C_m3")),
            lambda_inv_nm=_float(row.get("lambda_inv_nm")),
            d_nm=_float(row.get("d_nm")),
            T_C=_float(row.get("T_C")),
            electrolyte=(row.get("electrolyte") or "").strip(),
            z=None if z is None else int(z),
            I_grid_mM=_grid(row.get("I_grid_mM")),
            I_min_mM=_float(row.get("I_min_mM")),
            I_max_mM=_float(row.get("I_max_mM")),
            source_note=(row.get("source_note") or "").strip(),
        )

    @property
    def key(self) -> str:
        raw = f"{self.dataset}__{self.figure}__{self.particle}".lower()
        return "".join(ch if ch.isalnum() else "_" for ch in raw).strip("_")

    @property
    def zn_M(self) -> float | None:
        """Layer charge in mol/L; derived from ρ (C/m³) as ρ/F per litre when only ρ is printed."""
        if self.ZN_M is not None:
            return self.ZN_M
        if self.rho_C_m3 is not None:
            return self.rho_C_m3 / FARADAY / 1000.0
        return None

    @property
    def T_assumed(self) -> bool:
        return self.T_C is None

    def temperature(self) -> float:
        return DEFAULT_T_C if self.T_C is None else self.T_C

    @property
    def missing(self) -> list[str]:
        gaps: list[str] = []
        if self.model == "hard":
            if self.sigma_C_m2 is None:
                gaps.append("sigma_C_m2")
            if self.radius_nm is None:
                gaps.append("radius_nm")
            if self.electrolyte not in constants.ELECTROLYTES:
                gaps.append("electrolyte")
        elif self.model == "soft":
            if self.zn_M is None:
                gaps.append("ZN_M")
            if self.lambda_inv_nm is None:
                gaps.append("lambda_inv_nm")
        else:
            gaps.append("model")
        if self.z is None:
            gaps.append("z")
        if self.I_grid_mM is None and (self.I_min_mM is None or self.I_max_mM is None):
            gaps.append("I_grid_mM")
        return gaps

    @property
    def complete(self) -> bool:
        return not self.missing

    @property
    def grid_source(self) -> str:
        if self.I_grid_mM is not None:
            return "printed"
        return "log grid over the stated sweep range (nominal points not in the doc)"

    def grid(self) -> np.ndarray:
        if self.I_grid_mM is not None:
            return np.asarray(self.I_grid_mM, dtype=float)
        return np.logspace(np.log10(self.I_min_mM), np.log10(self.I_max_mM), LOG_GRID_POINTS)

    def curve(self, I_mM) -> np.ndarray | float:
        """Recomputed mobility in 10⁻⁸ m² V⁻¹ s⁻¹ on the given ionic strengths (mM)."""
        if self.missing:
            raise ValueError(f"{self.key}: cannot recompute, missing {self.missing}")
        T = self.temperature()
        if self.model == "hard":
            mu = hard.mobility_hard(
                self.sigma_C_m2, self.radius_nm * 1e-9, I_mM, self.z, T, self.electrolyte
            )
        else:
            mu = soft.mobility_soft(self.zn_M, self.lambda_inv_nm * 1e-9, I_mM, self.z, T)
        return mu / MU_UNIT

    def validity(self, I_mM) -> tuple[bool | None, str]:
        ionic = np.asarray(I_mM, dtype=float)
        T = self.temperature()
        if self.model == "hard":
            ka = hard.debye_kappa(self.z**2 * ionic, T) * self.radius_nm * 1e-9
            ok = bool(np.all(hard.kappa_a_ok(ka)))
            return (
                ok,
                f"relaxation expression needs κa ≥ {hard.KAPPA_A_MIN:g}; min κa = {ka.min():.1f}",
            )
        if self.d_nm is None:
            return None, "d not printed; thick-layer validity d ≫ 1/λ, 1/κ unchecked"
        kappa_inv_nm = hard.debye_length(self.z**2 * ionic, T) * 1e9
        ok = bool(np.all(soft.layer_thickness_ok(self.d_nm, self.lambda_inv_nm, kappa_inv_nm)))
        need = 5 * max(self.lambda_inv_nm, float(kappa_inv_nm.max()))
        return ok, f"d = {self.d_nm:g} nm vs 5·max(1/λ, 1/κ) = {need:.1f} nm at the lowest I"


def load_bank(path: Path | None = None) -> list[PrintedFit]:
    with Path(path or bank_path()).open(newline="") as f:
        return [PrintedFit.from_row(row) for row in csv.DictReader(f)]


def load_digitised(fit: PrintedFit, directory: Path | None = None):
    """(I_mM, μ_1e8) arrays for this fit, or None when no digitised series exists."""
    path = Path(directory or digitised_dir()) / f"{fit.dataset}.csv"
    if not path.is_file():
        return None
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        points = []
        for row in reader:
            if row.get("figure", "").strip() and row["figure"].strip() != fit.figure:
                continue
            if row.get("particle", "").strip() and row["particle"].strip() != fit.particle:
                continue
            points.append((float(row["I_mM"]), float(row["mu_1e8"])))
    if not points:
        return None
    points.sort()
    ionic, mu = zip(*points, strict=True)
    return np.asarray(ionic), np.asarray(mu)


def residual_check(fit: PrintedFit, ionic, mu_digitised, gate: float = RESIDUAL_GATE) -> dict:
    model_points = fit.curve(ionic)
    everything = np.concatenate([fit.curve(fit.grid()), np.asarray(mu_digitised), model_points])
    axis_range = max(float(everything.max() - everything.min()), 1e-9)
    frac = float(np.max(np.abs(model_points - mu_digitised)) / axis_range)
    return {
        "axis_range_1e8": axis_range,
        "residual_max_frac": frac,
        "residual_pass": bool(frac <= gate),
    }


def x_on_grid_check(ionic, nominal, tol: float = X_TOLERANCE) -> bool | None:
    if nominal is None:
        return None
    x = np.asarray(ionic, dtype=float)[:, None]
    g = np.asarray(nominal, dtype=float)[None, :]
    return bool(np.all(np.min(np.abs(x - g) / g, axis=1) <= tol))


def qa_row(fit: PrintedFit, digitised: Path | None = None) -> dict:
    row = {
        "dataset": fit.dataset,
        "figure": fit.figure,
        "particle": fit.particle,
        "key": fit.key,
        "model": fit.model,
        "complete": fit.complete,
        "missing": ";".join(fit.missing),
        "T_assumed": fit.T_assumed,
        "grid_source": fit.grid_source if fit.complete else "",
        "n_grid": 0,
        "n_digitised": 0,
        "axis_range_1e8": None,
        "residual_max_frac": None,
        "residual_pass": None,
        "x_on_grid_pass": None,
        "validity_ok": None,
        "validity_note": "",
        "status": "incomplete",
    }
    if not fit.complete:
        return row
    grid = fit.grid()
    row.update(n_grid=len(grid), status="recomputed", _grid=grid, _curve=fit.curve(grid))
    row["validity_ok"], row["validity_note"] = fit.validity(grid)
    series = load_digitised(fit, digitised)
    if series is not None:
        ionic, mu = series
        row.update(residual_check(fit, ionic, mu))
        row["x_on_grid_pass"] = x_on_grid_check(ionic, fit.I_grid_mM)
        row.update(n_digitised=len(ionic), status="recomputed+digitised", _digitised=series)
    return row


def all_gates_pass(rows: list[dict]) -> bool:
    return all(r["residual_pass"] is not False and r["x_on_grid_pass"] is not False for r in rows)


def write_params_table(bank: list[PrintedFit], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [*asdict(bank[0]).keys(), "zn_M_used", "key", "complete", "missing", "T_assumed"]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for fit in bank:
            record = asdict(fit)
            if fit.I_grid_mM is not None:
                record["I_grid_mM"] = ";".join(f"{v:g}" for v in fit.I_grid_mM)
            record.update(
                zn_M_used=fit.zn_M, key=fit.key, complete=fit.complete,
                missing=";".join(fit.missing), T_assumed=fit.T_assumed,
            )  # fmt: skip
            writer.writerow({c: "" if record[c] is None else record[c] for c in columns})


def write_residual_table(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RESULT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: "" if row[c] is None else row[c] for c in RESULT_COLUMNS})


def overlay_figure(rows: list[dict], path: Path) -> None:
    """Recomputed curves; digitised points only where they exist."""
    path.parent.mkdir(parents=True, exist_ok=True)
    drawn = [r for r in rows if r["status"] != "incomplete"]
    ncols = min(4, max(1, len(drawn)))
    nrows = max(1, -(-len(drawn) // ncols))
    blue, orange = PALETTE["series"][:2]
    fig, axes = plt.subplots(
        nrows, ncols, figsize=(3.6 * ncols, 2.9 * nrows), squeeze=False,
        facecolor=PALETTE["surface"],
    )  # fmt: skip
    for ax in axes.flat:
        ax.set_visible(False)
    validity = {True: "within validity", False: "outside validity", None: "validity unchecked"}
    for ax, row in zip(axes.flat, drawn, strict=False):
        ax.set_visible(True)
        style_axes(ax)
        ax.semilogx(row["_grid"], row["_curve"], color=blue, lw=2, solid_capstyle="round",
                    label="printed fit, recomputed")  # fmt: skip
        if "_digitised" in row:
            ionic, mu = row["_digitised"]
            verdict = "pass" if row["residual_pass"] else "FAIL"
            label = f"digitised, residual {100 * row['residual_max_frac']:.1f} % ({verdict})"
            ax.plot(ionic, mu, "o", ms=6, color=orange, mec=PALETTE["surface"], mew=1.5,
                    label=label)  # fmt: skip
            ax.legend(fontsize=6.5, loc="lower right", frameon=False, labelcolor=PALETTE["ink2"])
        else:
            ax.text(0.03, 0.06, "synthetic from printed fits", transform=ax.transAxes,
                    fontsize=7, color=PALETTE["muted"])  # fmt: skip
        ax.set_title(f"{row['dataset']} {row['figure']}\n{row['particle']}", fontsize=7.5)
        ax.text(0.97, 0.94, validity[row["validity_ok"]], transform=ax.transAxes, fontsize=7,
                ha="right", va="top", color=PALETTE["muted"])  # fmt: skip
        ax.xaxis.set_minor_formatter(NullFormatter())
        ax.set_xlabel("I (mM)", fontsize=8)
        ax.set_ylabel("μ (10⁻⁸ m² V⁻¹ s⁻¹)", fontsize=8)
        ax.tick_params(labelsize=7)
    if not drawn:
        axes[0, 0].set_visible(True)
        axes[0, 0].text(0.5, 0.5, "no complete rows in the bank", ha="center", va="center")
    fig.suptitle("D4 QA: printed fits recomputed on the papers' own salt grids", fontsize=10,
                 color=PALETTE["ink"])  # fmt: skip
    fig.tight_layout()
    fig.savefig(path, dpi=130, facecolor=PALETTE["surface"])
    plt.close(fig)


def run_qa(
    bank: Path | None = None,
    digitised: Path | None = None,
    tables_dir: Path | None = None,
    figures_dir: Path | None = None,
) -> list[dict]:
    fits = load_bank(bank)
    rows = [qa_row(fit, digitised) for fit in fits]
    tables = Path(tables_dir or config.OUT_TABLES)
    figures = Path(figures_dir or config.OUT_FIGURES)
    write_params_table(fits, tables / "d4_params.csv")
    write_residual_table(rows, tables / "d4_qa_residuals.csv")
    overlay_figure(rows, figures / "d4_qa_overlay.png")
    return rows
