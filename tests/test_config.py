import pytest

from mnp import config


def test_root_and_data_dirs_point_inside_the_service():
    assert config.ROOT.name == "mnp-research"
    assert config.DATA_RAW == config.ROOT / "data" / "raw"
    assert config.DATA_INTERIM == config.ROOT / "data" / "interim"
    assert config.DATA_PROCESSED == config.ROOT / "data" / "processed"
    assert config.OUT == config.ROOT / "out"
    for d in (config.DATA_RAW, config.DATA_INTERIM, config.DATA_PROCESSED, config.OUT):
        assert d.is_dir(), f"{d} missing"


def test_default_env_file_is_the_backend_env(monkeypatch):
    monkeypatch.delenv("MNP_ENV_FILE", raising=False)
    assert config.env_file() == config.ROOT.parent / "nanoSolve-backend" / ".env"


def test_load_env_reads_the_file_named_by_mnp_env_file(tmp_path, monkeypatch):
    envf = tmp_path / "custom.env"
    envf.write_text('OPENROUTER_KEY=sk-from-file\nQUOTED="q"\n')
    monkeypatch.setenv("MNP_ENV_FILE", str(envf))
    monkeypatch.delenv("OPENROUTER_KEY", raising=False)
    monkeypatch.delenv("QUOTED", raising=False)
    config.load_env()
    assert config.getenv("OPENROUTER_KEY") == "sk-from-file"
    assert config.getenv("QUOTED") == "q"


def test_load_env_does_not_override_the_real_environment(tmp_path, monkeypatch):
    envf = tmp_path / "custom.env"
    envf.write_text("OPENROUTER_KEY=sk-from-file\n")
    monkeypatch.setenv("MNP_ENV_FILE", str(envf))
    monkeypatch.setenv("OPENROUTER_KEY", "sk-from-shell")
    config.load_env()
    assert config.getenv("OPENROUTER_KEY") == "sk-from-shell"


def test_load_env_is_quiet_when_the_file_is_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("MNP_ENV_FILE", str(tmp_path / "nope.env"))
    config.load_env()


def test_user_agent_embeds_the_contact_email(monkeypatch):
    monkeypatch.setenv("MNP_CONTACT_EMAIL", "someone@example.org")
    ua = config.user_agent()
    assert "someone@example.org" in ua
    assert ua.startswith("NanoSolve-mnp-research/")


def test_user_agent_fails_loud_when_contact_email_is_unset(monkeypatch, tmp_path):
    monkeypatch.setenv("MNP_ENV_FILE", str(tmp_path / "nope.env"))
    monkeypatch.delenv("MNP_CONTACT_EMAIL", raising=False)
    with pytest.raises(config.MissingConfig) as exc:
        config.user_agent()
    assert "MNP_CONTACT_EMAIL" in str(exc.value)


def test_require_returns_value_or_raises(monkeypatch):
    monkeypatch.setenv("PRESENT_KEY", "v")
    monkeypatch.setenv("BLANK_KEY", "   ")
    assert config.require("PRESENT_KEY") == "v"
    with pytest.raises(config.MissingConfig):
        config.require("BLANK_KEY")
