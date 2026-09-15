"""The fetched corpus as one vendored archive plus a manifest of hashes.

Europe PMC is not an archive: records are withdrawn, re-versioned and re-typeset, so a fetch
run in a year's time returns a different corpus and every published count moves with it. The
XMLs therefore travel with the repository, and reproduction starts by checking them against
the manifest rather than by trusting the directory.

The archive is built deterministically — sorted names, no ownership, no timestamps — so the
same corpus always produces the same bytes and its hash can be pinned in the documentation.
"""

from __future__ import annotations

import gzip
import hashlib
import tarfile
from dataclasses import dataclass, field
from pathlib import Path

CHUNK = 1 << 20
PATTERN = "*.xml"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def _files(xml_dir: Path) -> list[Path]:
    return sorted(xml_dir.glob(PATTERN), key=lambda p: p.name)


def write_manifest(xml_dir: Path, manifest: Path) -> int:
    """`sha256  name` per file, sorted by name — the sha256sum format, checkable by hand."""
    lines = [f"{sha256_file(p)}  {p.name}" for p in _files(xml_dir)]
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text("\n".join(lines) + "\n")
    return len(lines)


def read_manifest(manifest: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in manifest.read_text().splitlines():
        if not line.strip():
            continue
        digest, name = line.split("  ", 1)
        out[name] = digest
    return out


@dataclass
class VerifyReport:
    checked: int = 0
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.missing or self.extra or self.changed)

    def summary(self) -> str:
        if self.ok:
            return f"corpus verified: {self.checked} files, every hash matches"
        return (
            f"corpus does NOT match the manifest: {len(self.missing)} missing, "
            f"{len(self.extra)} extra, {len(self.changed)} changed (of {self.checked} expected)"
        )


def verify(xml_dir: Path, manifest: Path) -> VerifyReport:
    """Every named file present with its recorded hash, and nothing else in the directory."""
    expected = read_manifest(manifest)
    report = VerifyReport(checked=len(expected))
    present = {p.name: p for p in _files(xml_dir)}
    for name, digest in expected.items():
        path = present.pop(name, None)
        if path is None:
            report.missing.append(name)
        elif sha256_file(path) != digest:
            report.changed.append(name)
    report.extra = sorted(present)
    return report


def write_archive(xml_dir: Path, archive: Path) -> int:
    """A byte-reproducible tar.gz: sorted, mode 0644, no uid/gid/uname/gname, mtime 0."""
    paths = _files(xml_dir)
    archive.parent.mkdir(parents=True, exist_ok=True)
    with archive.open("wb") as raw:
        # mtime=0: gzip stores the build time in its header otherwise, and the archive's own
        # hash would change on every rebuild of an unchanged corpus. filename="" for the same
        # reason — GzipFile copies the output file's name into the header when it can.
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", compresslevel=6, mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode="w", format=tarfile.GNU_FORMAT) as tar:
                for path in paths:
                    info = tar.gettarinfo(str(path), arcname=path.name)
                    info.mtime = 0
                    info.mode = 0o644
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    with path.open("rb") as fh:
                        tar.addfile(info, fh)
    return len(paths)


def restore(archive: Path, xml_dir: Path) -> int:
    """Unpack into `xml_dir`. A member that names a path outside it is refused, not skipped."""
    xml_dir.mkdir(parents=True, exist_ok=True)
    target = xml_dir.resolve()
    written = 0
    with tarfile.open(archive, mode="r:gz") as tar:
        for member in tar:
            if not member.isfile():
                continue
            destination = (target / member.name).resolve()
            if destination != target and target not in destination.parents:
                raise ValueError(f"archive member {member.name!r} resolves outside {target}")
            source = tar.extractfile(member)
            if source is None:  # pragma: no cover - isfile() already excludes these
                continue
            with source, destination.open("wb") as out:
                while chunk := source.read(CHUNK):
                    out.write(chunk)
            written += 1
    return written
