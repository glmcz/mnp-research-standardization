"""Where the queue is allowed to look for a database.

A `pytest` run with no `MNP_DB_URL` used to fall through to `DATABASE_URL`, which
`config.load_env()` reads out of the Rust service's `.env`. The queue's integration tests
therefore pointed at the live application database and tried to create schemas in it; only a
permission error stopped them. The queue gets one variable of its own, and an ambient
`DATABASE_URL` is not it.
"""

import pytest

from mnp import queue as q


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """No .env on disk, so only what a test sets is visible."""
    monkeypatch.setenv("MNP_ENV_FILE", str(tmp_path / "absent.env"))
    monkeypatch.delenv("MNP_DB_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return monkeypatch


def test_ambient_database_url_is_never_the_queue(isolated_env, monkeypatch):
    isolated_env.setenv("DATABASE_URL", "postgresql://app:app@localhost:5432/nanoplastics")

    def explode(*args, **kwargs):  # pragma: no cover - the assertion is that it is not called
        raise AssertionError("the queue tried to connect to an ambient DATABASE_URL")

    if q.psycopg is not None:
        monkeypatch.setattr(q.psycopg, "connect", explode)

    assert q.dsn() is None
    assert q.available() is False
    with pytest.raises(RuntimeError) as exc:
        q.Queue()
    assert "MNP_DB_URL" in str(exc.value)
    assert "DATABASE_URL" not in str(exc.value)


def test_its_own_variable_is_used_when_set(isolated_env):
    isolated_env.setenv("MNP_DB_URL", "postgresql://mnp:mnp@localhost:55432/mnp")
    assert q.dsn() == "postgresql://mnp:mnp@localhost:55432/mnp"


def test_a_blank_url_is_no_url(isolated_env):
    isolated_env.setenv("MNP_DB_URL", "   ")
    assert q.dsn() is None
    assert q.available() is False
