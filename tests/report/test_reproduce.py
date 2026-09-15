"""Offline replay: the published numbers must come back out of the stored corpus.

The claim this makes checkable is "a stranger with this repository reproduces every published
number". Two things must hold: the rebuild reaches no network and no model, and what it
rebuilds is byte-identical to what is committed.
"""

import socket

import pytest

from mnp.report import reproduce


def test_network_is_refused_not_merely_unused():
    with pytest.raises(reproduce.NetworkRefused, match="offline"):
        with reproduce.no_network():
            socket.create_connection(("example.org", 80), timeout=1)


def test_the_guard_is_lifted_afterwards():
    with reproduce.no_network():
        pass
    s = socket.socket()
    s.close()  # constructing a socket still works; only connecting was blocked


def test_the_guard_survives_an_exception_inside_it():
    with pytest.raises(ValueError):
        with reproduce.no_network():
            raise ValueError("boom")
    assert socket.socket.connect is not reproduce._refuse


def test_hash_tree_covers_every_file(tmp_path):
    (tmp_path / "a.csv").write_text("x\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.json").write_text("{}\n")
    tree = reproduce.hash_tree(tmp_path)
    assert sorted(tree) == ["a.csv", "sub/b.json"]


def test_drift_names_the_file_whose_number_moved(tmp_path):
    before, after = tmp_path / "before", tmp_path / "after"
    for d in (before, after):
        (d / "tables").mkdir(parents=True)
        (d / "tables" / "stable.csv").write_text("a,1\n")
    (before / "tables" / "d1_stats.md").write_text("papers | 498\n")
    (after / "tables" / "d1_stats.md").write_text("papers | 497\n")
    result = reproduce.drift(reproduce.hash_tree(before), reproduce.hash_tree(after))
    assert result.changed == ["tables/d1_stats.md"], "a moved number must be named"
    assert result.missing == [] and result.extra == [] and result.ok is False

    # An artefact the rebuild never produced is a different failure, reported as its own.
    (after / "tables" / "d1_stats.md").unlink()
    result = reproduce.drift(reproduce.hash_tree(before), reproduce.hash_tree(after))
    assert result.missing == ["tables/d1_stats.md"] and result.changed == []

    # `only` narrows the comparison without hiding a difference inside it.
    (after / "tables" / "d1_stats.md").write_text("papers | 497\n")
    (after / "tables" / "stable.csv").write_text("a,2\n")
    result = reproduce.drift(
        reproduce.hash_tree(before), reproduce.hash_tree(after), only=["tables/d1_stats.md"]
    )
    assert result.changed == ["tables/d1_stats.md"] and result.ok is False


def test_no_drift_is_ok(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    for d in (a, b):
        d.mkdir()
        (d / "t.csv").write_text("same\n")
    assert reproduce.drift(reproduce.hash_tree(a), reproduce.hash_tree(b)).ok


def test_the_runner_exits_non_zero_on_drift(tmp_path, monkeypatch):
    committed, rebuilt = tmp_path / "out", tmp_path / "rebuilt"
    committed.mkdir()
    (committed / "d1_stats.md").write_text("papers | 498\n")

    def fake_build(out_dir):
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "d1_stats.md").write_text("papers | 497\n")

    code = reproduce.run(committed=committed, rebuilt=rebuilt, build=fake_build)
    assert code == 1

    def faithful_build(out_dir):
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "d1_stats.md").write_text("papers | 498\n")

    assert reproduce.run(committed=committed, rebuilt=rebuilt, build=faithful_build) == 0


def test_the_build_runs_with_the_network_refused(tmp_path):
    """The guard is the runner's job, not the caller's."""
    seen = {}

    def build(out_dir):
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            socket.create_connection(("example.org", 80), timeout=1)
        except reproduce.NetworkRefused:
            seen["refused"] = True

    committed = tmp_path / "out"
    committed.mkdir()
    reproduce.run(committed=committed, rebuilt=tmp_path / "r", build=build)
    assert seen.get("refused") is True
