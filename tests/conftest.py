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
