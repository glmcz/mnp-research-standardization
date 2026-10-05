import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from mnp import config


@pytest.fixture(autouse=True)
def isolated_env(tmp_path_factory, monkeypatch):
    """No test reads the real .env or inherits a contact address from the shell."""
    monkeypatch.setenv("MNP_ENV_FILE", str(tmp_path_factory.mktemp("env") / "absent.env"))
    monkeypatch.delenv("MNP_CONTACT_EMAIL", raising=False)


@pytest.fixture
def fixtures_dir():
    return config.ROOT / "tests" / "fixtures"


@pytest.fixture(scope="session")
def table_at(tmp_path_factory) -> Callable[[str], Path]:
    """`out/tables/d1_zeta_table.csv` as committed at `commit`, copied to a scratch file.

    A published number is pinned on the table it was measured on. Today's table moves with every
    re-extraction; a committed one never does. No history, no test: `git show` failing is an
    error, never a skip.
    """
    root = tmp_path_factory.mktemp("committed-tables")

    def load(commit: str) -> Path:
        path = root / f"{commit}.csv"
        if not path.is_file():
            shown = subprocess.run(
                ["git", "show", f"{commit}:out/tables/d1_zeta_table.csv"],
                cwd=config.ROOT,
                capture_output=True,
                check=True,
            )
            path.write_bytes(shown.stdout)
        return path

    return load
