import pandas as pd

from mnp.report import d4


def test_build_recomputes_the_bank_and_renders_what_exists(tmp_path):
    written = d4.build(tmp_path / "tables", tmp_path / "figures", posterior_dir=tmp_path / "none")
    names = {p.name for p in written}
    assert {"d4_params.csv", "d4_qa_residuals.csv", "d4_qa_overlay.png"} <= names
    # no posteriors were offered, so no inference figures are claimed
    assert "d4_recovery.png" not in names
    params = pd.read_csv(tmp_path / "tables" / "d4_params.csv")
    assert len(params) >= 12
    residuals = pd.read_csv(tmp_path / "tables" / "d4_qa_residuals.csv")
    assert "validity_ok" in residuals.columns or "validity" in " ".join(residuals.columns)
