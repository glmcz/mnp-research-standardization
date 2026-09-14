import json

import pandas as pd
import pytest

from mnp import config
from mnp.report import __main__ as cli


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_PROCESSED", tmp_path / "processed")
    monkeypatch.setattr(config, "EPMC_SEARCH_DIR", tmp_path / "search")
    monkeypatch.setattr(config, "DATA_RAW", tmp_path / "raw")
    return tmp_path


def test_d2_writes_schema_example_and_checklist(workspace, capsys):
    out = workspace / "out"
    assert cli.main(["d2", "--out", str(out)]) == 0
    assert (out / "schema" / "mnp_characterisation.schema.json").is_file()
    assert (out / "schema" / "example_instance.json").is_file()
    assert (out / "checklist.md").is_file()
    assert not (out / "schema" / "checklist.md").exists()
    printed = capsys.readouterr().out
    assert printed.count("d2: ") == 3


def test_d1_without_extraction_data_skips_cleanly(workspace, capsys):
    out = workspace / "out"
    assert cli.main(["d1", "--out", str(out)]) == 0
    assert "no zeta_table" in capsys.readouterr().err


def test_d1_with_a_table_writes_into_the_requested_root(workspace):
    (workspace / "processed").mkdir()
    (workspace / "search").mkdir()
    pd.DataFrame(
        [dict(pmcid="P", year=2020, journal="J", row_id="P-r1", quantity="zeta_potential",
              value=-30.0, unit="mV", medium_reported=True, ionic_strength_reported=False,
              pH_reported=True, temperature_reported=True, instrument_reported=True,
              conditions_complete=False, medium_matches_exposure=None, evidence_verified=True,
              flags="")]
    ).to_parquet(workspace / "processed" / "zeta_table.parquet", index=False)  # fmt: skip
    (workspace / "search" / "hit_counts.json").write_text(json.dumps({"hits_oa": 3, "hits_all": 5}))
    out = workspace / "out"
    assert cli.main(["d1", "--out", str(out)]) == 0
    stats = json.loads((out / "tables" / "d1_stats.json").read_text())
    assert stats["denominators"] == {"papers_with_verified_zeta": 1, "oa_records": 3, "all_hits": 5}
    assert (out / "figures" / "d1_missing_conditions.png").is_file()


def test_all_runs_every_deliverable_that_has_data(workspace, capsys):
    out = workspace / "out"
    assert cli.main(["all", "--out", str(out)]) == 0
    assert (out / "checklist.md").is_file()
