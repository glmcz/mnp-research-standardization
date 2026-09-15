"""The corpus as a vendored, checksummed artefact.

The published numbers are derived from 859 Europe PMC XMLs. Re-fetching them years later
gives a different corpus: records are withdrawn, re-versioned and re-typeset. So the corpus
travels with the repository as one archive plus a manifest, and every claim of reproduction
begins by checking the manifest.
"""

import gzip
import hashlib
import io
import tarfile

import pytest

from mnp.corpus import snapshot


@pytest.fixture
def xml_dir(tmp_path):
    d = tmp_path / "xml"
    d.mkdir()
    for name, body in (
        ("PMC0001.xml", "<article>one</article>"),
        ("PMC0002.xml", "<article>two</article>"),
        ("PMC0003.xml", "<article>three</article>"),
    ):
        (d / name).write_text(body)
    return d


def test_manifest_has_one_sorted_line_per_file(xml_dir, tmp_path):
    manifest = tmp_path / "manifest.sha256"
    snapshot.write_manifest(xml_dir, manifest)
    lines = manifest.read_text().splitlines()
    assert len(lines) == 3
    names = [line.split("  ", 1)[1] for line in lines]
    assert names == sorted(names) == ["PMC0001.xml", "PMC0002.xml", "PMC0003.xml"]
    first = lines[0].split("  ", 1)[0]
    assert first == hashlib.sha256((xml_dir / "PMC0001.xml").read_bytes()).hexdigest()


def test_verify_is_green_on_an_untouched_corpus(xml_dir, tmp_path):
    manifest = tmp_path / "manifest.sha256"
    snapshot.write_manifest(xml_dir, manifest)
    report = snapshot.verify(xml_dir, manifest)
    assert report.ok and report.checked == 3
    assert not report.missing and not report.extra and not report.changed


def test_one_flipped_byte_is_caught(xml_dir, tmp_path):
    manifest = tmp_path / "manifest.sha256"
    snapshot.write_manifest(xml_dir, manifest)
    (xml_dir / "PMC0002.xml").write_text("<article>two </article>")
    report = snapshot.verify(xml_dir, manifest)
    assert not report.ok
    assert report.changed == ["PMC0002.xml"]


def test_a_missing_file_is_caught(xml_dir, tmp_path):
    manifest = tmp_path / "manifest.sha256"
    snapshot.write_manifest(xml_dir, manifest)
    (xml_dir / "PMC0003.xml").unlink()
    report = snapshot.verify(xml_dir, manifest)
    assert not report.ok and report.missing == ["PMC0003.xml"]


def test_an_extra_file_is_caught(xml_dir, tmp_path):
    """A corpus with an extra paper is a different corpus, even though nothing is corrupt."""
    manifest = tmp_path / "manifest.sha256"
    snapshot.write_manifest(xml_dir, manifest)
    (xml_dir / "PMC0009.xml").write_text("<article>nine</article>")
    report = snapshot.verify(xml_dir, manifest)
    assert not report.ok and report.extra == ["PMC0009.xml"]


def test_archive_round_trips_every_hash(xml_dir, tmp_path):
    archive, manifest = tmp_path / "xml.tar.gz", tmp_path / "manifest.sha256"
    snapshot.write_archive(xml_dir, archive)
    snapshot.write_manifest(xml_dir, manifest)
    restored = tmp_path / "restored"
    n = snapshot.restore(archive, restored)
    assert n == 3
    assert snapshot.verify(restored, manifest).ok


def test_the_archive_is_byte_identical_when_built_twice(xml_dir, tmp_path):
    """Timestamps and ownership must not leak in, or the pinned hash changes for nothing."""
    a, b = tmp_path / "a.tar.gz", tmp_path / "b.tar.gz"
    snapshot.write_archive(xml_dir, a)
    snapshot.write_archive(xml_dir, b)
    assert a.read_bytes() == b.read_bytes()


def test_restore_refuses_to_write_outside_the_target(tmp_path):
    """A tar member may name any path it likes; ours may not escape the corpus directory."""
    archive = tmp_path / "evil.tar.gz"
    payload = b"<article>evil</article>"
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tar:
        info = tarfile.TarInfo("../escaped.xml")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    archive.write_bytes(gzip.compress(raw.getvalue()))
    with pytest.raises(ValueError, match="outside"):
        snapshot.restore(archive, tmp_path / "xml")
    assert not (tmp_path / "escaped.xml").exists()


def test_the_committed_manifest_matches_the_corpus_on_disk():
    """Skips on a fresh clone that has not restored yet; fails if the two disagree."""
    from mnp import config

    manifest = config.EPMC_XML_DIR.parent / "manifest.sha256"
    if not manifest.is_file() or not config.EPMC_XML_DIR.is_dir():
        pytest.skip("no corpus restored here")
    report = snapshot.verify(config.EPMC_XML_DIR, manifest)
    assert report.ok, (
        f"missing={report.missing[:3]} extra={report.extra[:3]} changed={report.changed[:3]}"
    )
