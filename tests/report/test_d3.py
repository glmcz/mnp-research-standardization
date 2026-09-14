import numpy as np
import pandas as pd

from mnp.report import d3
from mnp.rescale import powerlaw as pl


def _table():
    return pd.DataFrame(
        {
            "study": ["a", "b", "c", "d", "mass", "areal"],
            "matrix": ["freshwater", "freshwater", "drinking water", "wastewater", "x", "y"],
            "size_min_um": [333.0, 20.0, 1.0, 10.0, 300.0, 300.0],
            "size_max_um": [5000.0, 1000.0, 100.0, np.nan, 5000.0, 5000.0],
            "concentration_value": [0.004, 0.03, 300.0, 5.0, 2.0, 40000.0],
            "concentration_unit": ["#/L", "#/L", "#/L", "#/L", "mg/L", "#/km2"],
            "method": ["m"] * 6,
            "notes": [""] * 6,
        }
    )


def test_build_writes_the_three_artefacts(tmp_path):
    tables, figures = tmp_path / "tables", tmp_path / "figures"
    written = d3.build(tables, figures, table=_table())
    names = {p.name for p in written}
    assert names == {"d3_rescaled.csv", "d3_spread.csv", "d3_before_after.png"}
    for p in written:
        assert p.is_file() and p.stat().st_size > 0
    assert (figures / "d3_before_after.png").stat().st_size > 1000


def test_rescaled_csv_has_one_row_per_study_target_alpha(tmp_path):
    d3.build(tmp_path / "t", tmp_path / "f", table=_table())
    out = pd.read_csv(tmp_path / "t" / "d3_rescaled.csv")
    assert len(out) == 6 * len(pl.TARGETS) * len(pl.ALPHA_SENSITIVITY)
    assert {"cf", "rescaled_value", "upper_assumed", "excluded_reason", "alpha_source"} <= set(
        out.columns
    )
    assert out.loc[out["study"] == "mass", "excluded_reason"].eq("mass_units").all()
    assert out.loc[out["alpha"] == 3.1, "alpha_source"].str.contains("abstract only").all()


def test_spread_csv_has_before_and_after_rows(tmp_path):
    d3.build(tmp_path / "t", tmp_path / "f", table=_table())
    spread = pd.read_csv(tmp_path / "t" / "d3_spread.csv")
    required = {"target", "alpha", "unit", "n", "min", "max", "log10_range", "iqr_log10", "gcv"}
    assert required <= set(spread.columns)
    before = spread[spread["target"] == "measured"]
    assert len(before) >= 1
    assert before.loc[before["unit"] == "n/L", "n"].iloc[0] == 4
    after = spread[spread["target"] != "measured"]
    assert set(after["alpha"].dropna()) == set(pl.ALPHA_SENSITIVITY)
    assert set(after["target"]) == {"1-5000 µm", "0.1-5000 µm"}
    assert (spread["max"] >= spread["min"]).all()
    assert after.loc[after["alpha"] == 2.6, "alpha_source"].str.contains("abstract only").all()


def test_spread_stats_are_computed_on_log10_of_positive_values():
    rescaled = pl.rescale_table(_table(), targets=(pl.TARGET_DEFAULT,), alphas=(1.6,))
    spread = d3.spread_table(rescaled)
    row = spread[(spread["target"] == "measured") & (spread["unit"] == "n/L")].iloc[0]
    values = np.array([0.004, 0.03, 300.0, 5.0])
    logs = np.log10(values)
    assert row["n"] == 4
    assert row["min"] == values.min() and row["max"] == values.max()
    assert row["log10_range"] == (logs.max() - logs.min())
    q75, q25 = np.percentile(logs, [75, 25])
    assert row["iqr_log10"] == (q75 - q25)
    s = np.log(values).std(ddof=1)
    assert row["gcv"] == np.sqrt(np.exp(s**2) - 1)


def test_build_can_also_write_the_processed_parquet(tmp_path):
    parquet = tmp_path / "processed" / "rescaled.parquet"
    d3.build(tmp_path / "t", tmp_path / "f", table=_table(), processed=parquet)
    assert parquet.is_file()
    assert len(pd.read_parquet(parquet)) == 6 * len(pl.TARGETS) * len(pl.ALPHA_SENSITIVITY)
