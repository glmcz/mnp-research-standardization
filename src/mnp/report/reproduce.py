"""Rebuild every published artefact from the stored corpus, offline, and diff the result.

"Reproducible" is a claim about someone else's machine, so it has to be checkable on this
one: rebuild the deliverables into a scratch directory with the network refused, then compare
byte for byte against what is committed. A difference is either a real change — which then
has to be explained and re-published — or a source of non-determinism that has no business
being in a scientific artefact.

The network is *refused* rather than merely unused: a rebuild that quietly re-fetched a paper
or called a model would pass a test that only checked the numbers.
"""

from __future__ import annotations

import hashlib
import socket
from collections.abc import Callable, Iterable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path


class NetworkRefused(RuntimeError):
    """A rebuild tried to reach the network. Reproduction may not depend on a live service."""


def _refuse(*args, **kwargs):
    raise NetworkRefused("offline replay: network access is refused during a rebuild")


@contextmanager
def no_network():
    """Block outbound connections for the duration, whatever library attempts them."""
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_create = socket.create_connection
    socket.socket.connect = _refuse
    socket.socket.connect_ex = _refuse
    socket.create_connection = _refuse
    try:
        yield
    finally:
        socket.socket.connect = real_connect
        socket.socket.connect_ex = real_connect_ex
        socket.create_connection = real_create


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def hash_tree(root: Path, skip_suffixes: Sequence[str] = (".png",)) -> dict[str, str]:
    """Relative path → sha256 for every file under `root`.

    Figures are excluded by default: matplotlib's PNG bytes move with the freetype and
    matplotlib versions, so pinning them would fail for a reason that says nothing about the
    science. The tables behind every figure are pinned instead.
    """
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix in skip_suffixes:
            continue
        out[path.relative_to(root).as_posix()] = sha256_file(path)
    return out


@dataclass
class Drift:
    changed: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.changed or self.missing or self.extra)

    def summary(self) -> str:
        if self.ok:
            return "reproduced: every committed artefact rebuilt byte for byte"
        return (
            f"DRIFT: {len(self.changed)} changed, {len(self.missing)} not rebuilt, "
            f"{len(self.extra)} unexpected"
        )


def drift(
    committed: dict[str, str], rebuilt: dict[str, str], only: Iterable[str] | None = None
) -> Drift:
    """What the rebuild failed to reproduce. `only` narrows it to a named set of artefacts."""
    names = set(only) if only is not None else set(committed) | set(rebuilt)
    result = Drift()
    for name in sorted(names):
        before, after = committed.get(name), rebuilt.get(name)
        if before is None:
            result.extra.append(name)
        elif after is None:
            result.missing.append(name)
        elif before != after:
            result.changed.append(name)
    return result


def run(
    committed: Path,
    rebuilt: Path,
    build: Callable[[Path], None],
    only: Iterable[str] | None = None,
) -> int:
    """Rebuild offline into `rebuilt`, compare with `committed`, print and return an exit code."""
    before = hash_tree(committed)
    with no_network():
        build(rebuilt)
    after = hash_tree(rebuilt) if rebuilt.exists() else {}
    result = drift(before, after, only=only)
    print(result.summary())
    for label, names in (
        ("changed", result.changed),
        ("not rebuilt", result.missing),
        ("unexpected", result.extra),
    ):
        for name in names:
            print(f"  {label}: {name}")
    return 0 if result.ok else 1
