"""QA of the printed-curve bank: recompute every printed fit on the paper's own I grid,
overlay digitised points when a CSV exists, gate the residual at 2 % of the axis range and
check that digitised x-values sit within 10 % of a nominal salt concentration."""

import csv

import numpy as np
import pytest

from mnp.ek import hard, qa, soft

COLUMNS = [
    "dataset", "figure", "particle", "model", "sigma_C_m2", "radius_nm", "ZN_M", "rho_C_m3",
    "lambda_inv_nm", "d_nm", "T_C", "electrolyte", "z", "I_grid_mM", "I_min_mM", "I_max_mM",
    "source_note",
]  # fmt: skip

MAKINO = {
    "dataset": "makino_ohshima_2011", "figure": "Fig. 2", "particle": "PS/PNIPAM 25 C",
    "model": "soft", "ZN_M": "-0.0015", "lambda_inv_nm": "1.2", "T_C": "25",
    "electrolyte": "phosphate buffer", "z": "1", "I_grid_mM": "1;2;5;10;20;50;100;200",
    "source_note": "test",
}  # fmt: skip
KOBAYASHI = {
    "dataset": "kobayashi_2008", "figure": "Fig. 1", "particle": "sulfate latex 2.8 um",
    "model": "hard", "sigma_C_m2": "-0.07", "radius_nm": "1400", "T_C": "25",
    "electrolyte": "KCl", "z": "1", "I_min_mM": "0.1", "I_max_mM": "200", "source_note": "test",
}  # fmt: skip


def write_bank(tmp_path, rows):
    path = tmp_path / "printed_params.csv"
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in COLUMNS})
    return path


def write_digitised(tmp_path, fit, ionic, mu):
    path = tmp_path / f"{fit.dataset}.csv"
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["figure", "particle", "I_mM", "mu_1e8"])
        for x, y in zip(ionic, mu, strict=True):
            writer.writerow([fit.figure, fit.particle, x, y])
    return path


def test_soft_row_recomputes_the_printed_curve(tmp_path):
    (fit,) = qa.load_bank(write_bank(tmp_path, [MAKINO]))
    assert fit.complete and fit.missing == []
    expected = soft.mobility_soft(-0.0015, 1.2e-9, 10.0) / qa.MU_UNIT
    assert fit.curve(10.0) == pytest.approx(expected)
    assert fit.grid().tolist() == [1, 2, 5, 10, 20, 50, 100, 200]
    assert fit.grid_source == "printed"


def test_hard_row_recomputes_on_a_log_grid_over_the_stated_range(tmp_path):
    (fit,) = qa.load_bank(write_bank(tmp_path, [KOBAYASHI]))
    assert fit.complete
    grid = fit.grid()
    assert grid[0] == pytest.approx(0.1) and grid[-1] == pytest.approx(200.0)
    assert "log grid" in fit.grid_source
    expected = hard.mobility_hard(-0.07, 1.4e-6, 10.0) / qa.MU_UNIT
    assert fit.curve(10.0) == pytest.approx(expected)


def test_rho_in_C_per_m3_converts_to_molar_ZN(tmp_path):
    row = dict(MAKINO, ZN_M="", rho_C_m3="-9.3e5")
    (fit,) = qa.load_bank(write_bank(tmp_path, [row]))
    assert fit.zn_M == pytest.approx(-9.3e5 / 96485.33 / 1000, rel=1e-4)  # mol/L
    assert fit.complete


def test_incomplete_row_is_flagged_not_crashed(tmp_path):
    row = dict(KOBAYASHI, sigma_C_m2="")
    (fit,) = qa.load_bank(write_bank(tmp_path, [row]))
    assert not fit.complete
    assert fit.missing == ["sigma_C_m2"]
    result = qa.qa_row(fit, tmp_path)
    assert result["status"] == "incomplete"
    assert result["residual_pass"] is None


def test_non_zz_electrolyte_makes_a_hard_row_incomplete(tmp_path):
    row = dict(KOBAYASHI, electrolyte="Na2SO4", z="")
    (fit,) = qa.load_bank(write_bank(tmp_path, [row]))
    assert "electrolyte" in fit.missing and "z" in fit.missing


def test_temperature_defaults_to_25C_and_is_flagged_when_blank(tmp_path):
    (fit,) = qa.load_bank(write_bank(tmp_path, [dict(MAKINO, T_C="")]))
    assert fit.T_assumed and fit.temperature() == 25.0
    (fit,) = qa.load_bank(write_bank(tmp_path, [MAKINO]))
    assert not fit.T_assumed


def test_digitised_points_within_two_percent_pass_the_gate(tmp_path):
    (fit,) = qa.load_bank(write_bank(tmp_path, [MAKINO]))
    grid = fit.grid()
    write_digitised(tmp_path, fit, grid, fit.curve(grid) * 1.005)
    result = qa.qa_row(fit, tmp_path)
    assert result["status"] == "recomputed+digitised"
    assert result["n_digitised"] == len(grid)
    assert result["residual_pass"] is True
    assert result["residual_max_frac"] < qa.RESIDUAL_GATE
    assert result["x_on_grid_pass"] is True


def test_digitised_points_offset_by_five_percent_of_range_fail_the_gate(tmp_path):
    (fit,) = qa.load_bank(write_bank(tmp_path, [MAKINO]))
    grid = fit.grid()
    mu = fit.curve(grid)
    write_digitised(tmp_path, fit, grid, mu + 0.05 * (mu.max() - mu.min()))
    result = qa.qa_row(fit, tmp_path)
    assert result["residual_pass"] is False
    assert result["residual_max_frac"] > qa.RESIDUAL_GATE
    assert result["x_on_grid_pass"] is True


def test_x_value_off_the_nominal_grid_fails_the_x_check(tmp_path):
    (fit,) = qa.load_bank(write_bank(tmp_path, [MAKINO]))
    grid = fit.grid().copy()
    grid[3] = 13.0  # 30 % away from 10 mM, not within 10 % of any nominal value
    write_digitised(tmp_path, fit, grid, fit.curve(grid))
    result = qa.qa_row(fit, tmp_path)
    assert result["residual_pass"] is True
    assert result["x_on_grid_pass"] is False


def test_x_check_is_undefined_without_a_printed_grid(tmp_path):
    (fit,) = qa.load_bank(write_bank(tmp_path, [KOBAYASHI]))
    grid = fit.grid()[::5]
    write_digitised(tmp_path, fit, grid, fit.curve(grid))
    result = qa.qa_row(fit, tmp_path)
    assert result["residual_pass"] is True
    assert result["x_on_grid_pass"] is None


def test_digitised_file_selects_the_matching_series(tmp_path):
    other = dict(MAKINO, particle="PS/PNIPAM 40 C", ZN_M="-0.03", lambda_inv_nm="0.9")
    fit, fit40 = qa.load_bank(write_bank(tmp_path, [MAKINO, other]))
    grid = fit.grid()
    write_digitised(tmp_path, fit40, grid, fit40.curve(grid))
    assert qa.load_digitised(fit, tmp_path) is None
    ionic, mu = qa.load_digitised(fit40, tmp_path)
    assert len(ionic) == len(grid)
    assert np.allclose(mu, fit40.curve(grid))


def test_hard_validity_flags_small_kappa_a(tmp_path):
    big, small = qa.load_bank(write_bank(tmp_path, [KOBAYASHI, dict(KOBAYASHI, radius_nm="50")]))
    assert big.validity(big.grid())[0] is True
    ok, note = small.validity(small.grid())
    assert ok is False and "κa" in note


def test_soft_validity_uses_the_layer_thickness_flag(tmp_path):
    thin = dict(MAKINO, ZN_M="-0.17", lambda_inv_nm="0.7", d_nm="25")
    fit_d, fit_no_d = qa.load_bank(write_bank(tmp_path, [thin, MAKINO]))
    assert fit_d.validity(np.array([1.0]))[0] is False  # 1/κ = 9.6 nm, 5 × 9.6 > 25
    assert fit_d.validity(np.array([100.0]))[0] is True
    ok, note = fit_no_d.validity(np.array([100.0]))
    assert ok is None and "d" in note


def test_run_qa_writes_tables_and_overlay(tmp_path):
    bank = write_bank(
        tmp_path, [MAKINO, KOBAYASHI, dict(KOBAYASHI, figure="Fig. 2", sigma_C_m2="")]
    )
    tables, figures = tmp_path / "tables", tmp_path / "figures"
    rows = qa.run_qa(bank, tmp_path, tables, figures)
    assert len(rows) == 3
    assert (tables / "d4_qa_residuals.csv").is_file()
    assert (tables / "d4_params.csv").is_file()
    assert (figures / "d4_qa_overlay.png").stat().st_size > 1000
    with (tables / "d4_qa_residuals.csv").open() as f:
        written = list(csv.DictReader(f))
    assert [r["status"] for r in written] == ["recomputed", "recomputed", "incomplete"]
    assert qa.all_gates_pass(rows)


def test_run_qa_reports_a_failed_gate(tmp_path):
    bank = write_bank(tmp_path, [MAKINO])
    (fit,) = qa.load_bank(bank)
    grid = fit.grid()
    mu = fit.curve(grid)
    write_digitised(tmp_path, fit, grid, mu + 0.1 * (mu.max() - mu.min()))
    rows = qa.run_qa(bank, tmp_path, tmp_path / "t", tmp_path / "f")
    assert not qa.all_gates_pass(rows)


def test_real_bank_loads_and_every_complete_row_recomputes():
    bank = qa.load_bank()
    assert len(bank) >= 20
    makino = [f for f in bank if f.dataset == "makino_ohshima_2011" and f.figure == "Fig. 2"]
    assert len(makino) == 1 and makino[0].zn_M == -0.0015 and makino[0].lambda_inv_nm == 1.2
    complete = [f for f in bank if f.complete]
    assert len(complete) >= 10
    for fit in complete:
        mu = fit.curve(fit.grid())
        assert np.all(np.isfinite(mu)) and np.all(mu < 0), fit.key
    assert len({f.key for f in bank}) == len(bank), "row keys must be unique"
