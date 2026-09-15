"""Paths must follow the configuration, not the import order.

`BANK_PATH = config.DATA_RAW / …` at module level freezes whatever `DATA_RAW` happened to be
when the module was first imported. A test that redirects `DATA_RAW` then gets the real path
or the redirected one depending on which test ran first — and a run that redirects the data
root for real gets silently ignored. The same trap made `report reproduce` write into the
committed `out/tables`.
"""

import pandas as pd
import pytest

from mnp import config
from mnp.ek import qa
from mnp.rescale import koelmans2019


@pytest.fixture
def redirected_raw(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_RAW", tmp_path / "raw")
    return tmp_path / "raw"


def test_the_printed_fit_bank_follows_a_redirected_data_root(redirected_raw):
    assert qa.bank_path() == redirected_raw / "digitised" / "printed_params.csv"
    assert qa.digitised_dir() == redirected_raw / "digitised"


def test_load_bank_reads_from_the_redirected_root(redirected_raw):
    (redirected_raw / "digitised").mkdir(parents=True)
    real = pd.read_csv(config.ROOT / "data" / "raw" / "digitised" / "printed_params.csv")
    real.head(1).to_csv(redirected_raw / "digitised" / "printed_params.csv", index=False)
    assert len(qa.load_bank()) == 1


def test_the_koelmans_si_directory_follows_it_too(redirected_raw):
    assert koelmans2019.raw_dir() == redirected_raw / "koelmans2019"
    assert koelmans2019.csv_path() == redirected_raw / "koelmans2019" / "table_s1.csv"
