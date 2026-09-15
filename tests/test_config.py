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


def test_by_default_only_this_service_own_env_is_read(monkeypatch):
    """The sibling Rust service's .env is not read unless someone asks for it."""
    monkeypatch.delenv("MNP_ENV_FILE", raising=False)
    monkeypatch.delenv("MNP_ALLOW_SIBLING_ENV", raising=False)
    assert config.env_files() == (config.ROOT / ".env",)


def test_the_sibling_env_is_opt_in_and_ranks_below_our_own(monkeypatch):
    monkeypatch.delenv("MNP_ENV_FILE", raising=False)
    monkeypatch.setenv("MNP_ALLOW_SIBLING_ENV", "1")
    assert config.env_files() == (
        config.ROOT / ".env",
        config.ROOT.parent / "nanoSolve-backend" / ".env",
    )


def test_mnp_env_file_replaces_the_search_rather_than_extending_it(tmp_path, monkeypatch):
    monkeypatch.setenv("MNP_ENV_FILE", str(tmp_path / "custom.env"))
    monkeypatch.setenv("MNP_ALLOW_SIBLING_ENV", "1")
    assert config.env_files() == (tmp_path / "custom.env",)


def test_our_own_env_wins_over_the_sibling(tmp_path, monkeypatch):
    own, sibling = tmp_path / "own.env", tmp_path / "sibling.env"
    own.write_text("OPENROUTER_MODEL=from-own\n")
    sibling.write_text("OPENROUTER_MODEL=from-sibling\nGROQ_API_KEY=from-sibling\n")
    monkeypatch.delenv("MNP_ENV_FILE", raising=False)
    monkeypatch.setattr(config, "env_files", lambda: (own, sibling))
    for key in ("OPENROUTER_MODEL", "GROQ_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    config.load_env()
    assert config.getenv("OPENROUTER_MODEL") == "from-own"
    assert config.getenv("GROQ_API_KEY") == "from-sibling"


def test_env_example_documents_every_key_the_code_reads():
    """A key the code asks for but the example never mentions is undiscoverable.

    Parsed with ast rather than grepped: `require("MNP_CONTACT_EMAIL", hint)` is split across
    lines, and a regex over source lines misses exactly that call.
    """
    import ast

    wanted: set[str] = set()
    for path in (config.ROOT / "src" / "mnp").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name not in ("require", "getenv"):
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                wanted.add(first.value)

    example = config.ROOT / ".env.example"
    assert example.is_file(), ".env.example is missing"
    documented = {
        line.split("=", 1)[0].removeprefix("#").strip()
        for line in example.read_text().splitlines()
        if "=" in line
    }
    assert wanted, "no configuration keys found in the source; the scan is broken"
    assert wanted <= documented, f"undocumented in .env.example: {sorted(wanted - documented)}"


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
