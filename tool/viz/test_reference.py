"""build_data.py at 4a3087c must rebuild reference_4a3087c.json, the data the lost script wrote.

The reference was inlined into the published page when HEAD was 4a3087c, so it records
`"ref": "HEAD"`. Built here with `--ref 4a3087c`, the only difference allowed is that field.

    unset VIRTUAL_ENV; uv run pytest tool/viz/test_reference.py
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REF = "4a3087c"
REL_TOL = 1e-9


def _diffs(got, want, path: str = "$") -> list[str]:
    if type(got) is not type(want):
        return [f"{path}: {type(got).__name__} {got!r:.80} != {type(want).__name__} {want!r:.80}"]
    if isinstance(want, dict):
        out = (
            [f"{path}: keys {sorted(got.keys() ^ want.keys())} differ"]
            if got.keys() != want.keys()
            else []
        )
        for key in (k for k in want if k in got):
            out += _diffs(got[key], want[key], f"{path}.{key}")
        return out
    if isinstance(want, list):
        if len(got) != len(want):
            return [f"{path}: length {len(got)} != {len(want)}"]
        return [
            d
            for i, (g, w) in enumerate(zip(got, want, strict=True))
            for d in _diffs(g, w, f"{path}[{i}]")
        ]
    if isinstance(want, float):
        return (
            []
            if math.isclose(got, want, rel_tol=REL_TOL, abs_tol=0.0)
            else [f"{path}: {got!r} != {want!r}"]
        )
    return [] if got == want else [f"{path}: {got!r:.80} != {want!r:.80}"]


def test_build_data_reproduces_the_reference(tmp_path: Path) -> None:
    out = tmp_path / "data.json"
    run = subprocess.run(
        [sys.executable, str(HERE / "build_data.py"), "--ref", REF, "--out", str(out)],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stdout[-3000:] + run.stderr[-3000:]

    got = json.loads(out.read_text(encoding="utf-8"))
    want = json.loads((HERE / "reference_4a3087c.json").read_text(encoding="utf-8"))
    assert got.pop("ref") == REF
    assert want.pop("ref") == "HEAD"

    diffs = _diffs(got, want)
    assert not diffs, f"{len(diffs)} differences, first ones:\n" + "\n".join(diffs[:25])
