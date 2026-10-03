"""One directory per orchestrated run, so a row can be traced back to how it was produced.

The first corpus run cannot be audited: the brief lived in a scratchpad, the work lists drifted
and nothing recorded which code produced which record. A manifest is the cheapest fix — it
costs one file per run and answers "under what did this happen".
"""

import json

import pytest

from mnp import config, runs


@pytest.fixture
def run_root(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_INTERIM", tmp_path / "interim")
    return tmp_path / "interim" / "runs"


def test_a_manifest_records_the_code_that_produced_the_run(run_root, monkeypatch):
    monkeypatch.setattr(runs, "code_commit", lambda: ("abc1234", False))
    path = runs.start("r1", model="claude-code:opus", brief_sha256="beef")
    manifest = json.loads(path.read_text())
    assert manifest["run_id"] == "r1"
    assert manifest["code_commit"] == "abc1234"
    assert manifest["code_dirty"] is False
    assert manifest["model"] == "claude-code:opus"
    assert manifest["brief_sha256"] == "beef"
    assert manifest["started_at"].endswith("+00:00") or manifest["started_at"].endswith("Z")


def test_a_dirty_tree_is_recorded_as_dirty(run_root, monkeypatch):
    monkeypatch.setattr(runs, "code_commit", lambda: ("abc1234", True))
    manifest = json.loads(runs.start("r2").read_text())
    assert manifest["code_dirty"] is True, "a run from uncommitted code must say so"


def test_the_environment_is_recorded_by_key_name_and_never_by_value(run_root, monkeypatch):
    monkeypatch.setenv("OPENROUTER_KEY", "sk-do-not-write-me-down")
    monkeypatch.setattr(runs, "code_commit", lambda: ("abc1234", False))
    text = runs.start("r3").read_text()
    assert "OPENROUTER_KEY" in text
    assert "sk-do-not-write-me-down" not in text
    assert json.loads(text)["env_keys_present"].count("OPENROUTER_KEY") == 1


def test_starting_the_same_run_twice_keeps_the_first_start(run_root, monkeypatch):
    monkeypatch.setattr(runs, "code_commit", lambda: ("abc1234", False))
    first = json.loads(runs.start("r4").read_text())
    second = json.loads(runs.start("r4").read_text())
    assert second["started_at"] == first["started_at"], "resuming a run is not a new run"


def test_assignments_append_rather_than_overwrite(run_root, monkeypatch):
    monkeypatch.setattr(runs, "code_commit", lambda: ("abc1234", False))
    runs.start("r5")
    runs.assign("r5", worker="w1", pmcids=["PMC1", "PMC2"])
    runs.assign("r5", worker="w2", pmcids=["PMC3"])
    lines = (run_root / "r5" / "assignments.jsonl").read_text().splitlines()
    assert len(lines) == 2
    assert [json.loads(line)["worker"] for line in lines] == ["w1", "w2"]
    assert json.loads(lines[0])["pmcids"] == ["PMC1", "PMC2"]


def test_finishing_records_the_counts_and_the_end(run_root, monkeypatch):
    monkeypatch.setattr(runs, "code_commit", lambda: ("abc1234", False))
    runs.start("r6")
    runs.finish("r6", counts={"records": 12, "rows": 45})
    manifest = json.loads((run_root / "r6" / "manifest.json").read_text())
    assert manifest["counts"] == {"records": 12, "rows": 45}
    assert manifest["ended_at"]


def test_the_corpus_snapshot_is_pinned_when_there_is_one(run_root, monkeypatch, tmp_path):
    monkeypatch.setattr(runs, "code_commit", lambda: ("abc1234", False))
    manifest_file = tmp_path / "manifest.sha256"
    manifest_file.write_text("deadbeef  PMC1.xml\n")
    monkeypatch.setattr(config, "EPMC_XML_DIR", tmp_path / "xml")
    manifest = json.loads(runs.start("r7").read_text())
    assert manifest["corpus_manifest_sha256"], "a run is against one corpus; pin which"


def test_code_commit_reads_this_repository():
    """Not mocked: the function has to work here, or every manifest records null."""
    commit, dirty = runs.code_commit()
    assert commit and len(commit) >= 7
    assert isinstance(dirty, bool)


def test_an_untracked_file_does_not_make_the_code_dirty(tmp_path, monkeypatch):
    """`code_dirty` says whether the code that ran differs from its commit. An untracked note
    in docs/ changes no code, yet it marked every run dirty (register OD-06)."""
    import subprocess

    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "c")
    monkeypatch.setattr(config, "ROOT", tmp_path)
    (tmp_path / "notes.md").write_text("an untracked note")
    assert runs.code_commit()[1] is False
    (tmp_path / "tracked.py").write_text("x = 1")
    git("add", "tracked.py")
    assert runs.code_commit()[1] is True, "a staged change to code is still dirty"
