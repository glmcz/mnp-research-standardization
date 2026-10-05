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

import pytest

HERE = Path(__file__).resolve().parent
REF = "4a3087c"
ORIGIN_STATS = "out/tables/sample_origin_stats.json"
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


def _build(ref: str, out: Path) -> dict:
    run = subprocess.run(
        [sys.executable, str(HERE / "build_data.py"), "--ref", ref, "--out", str(out)],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stdout[-3000:] + run.stderr[-3000:]
    return json.loads(out.read_text(encoding="utf-8"))


def _show(ref: str, path: str) -> str | None:
    run = subprocess.run(
        ["git", "-C", str(HERE.parents[1]), "show", f"{ref}:{path}"], capture_output=True
    )
    return run.stdout.decode("utf-8") if run.returncode == 0 else None


def test_build_data_reproduces_the_reference(tmp_path: Path) -> None:
    got = _build(REF, tmp_path / "data.json")
    assert _show(REF, ORIGIN_STATS) is None and "origin" not in got and "scope" not in got
    assert "same_particle" not in got
    want = json.loads((HERE / "reference_4a3087c.json").read_text(encoding="utf-8"))
    assert got.pop("ref") == REF
    assert want.pop("ref") == "HEAD"

    diffs = _diffs(got, want)
    assert not diffs, f"{len(diffs)} differences, first ones:\n" + "\n".join(diffs[:25])


def test_the_origin_section_is_built_where_the_ref_has_the_origin_table(tmp_path: Path) -> None:
    text = _show("HEAD", ORIGIN_STATS)
    if text is None:
        pytest.skip("HEAD has no origin table")
    stats = json.loads(text)
    origin = _build("HEAD", tmp_path / "data.json")["origin"]
    # A HEAD committed before the rename still names this block `hand_corrected`.
    h = stats.get("after_second_reading") or stats["hand_corrected"]
    assert (origin["rows"], origin["papers"]) == (stats["rows"], stats["papers"])
    assert [c["key"] for c in origin["classes"]] == [
        "commercial", "lab_fabricated", "environmental", "unclear"
    ]  # fmt: skip
    for c in origin["classes"]:
        assert c["rows"] == h["origin"]["rows"][c["key"]]
        assert c["papers"] == h["origin"]["papers_any"][c["key"]]
    places = {e["key"]: e for e in origin["environments"]}
    assert places["air_dust"]["rows"] == h["environment"]["rows"]["air_dust"]
    assert sum(e["rows"] for e in origin["environments"]) == h["environmental_rows"]["rows"]
    conditions = {c["key"]: c["n"] for c in origin["env_conditions"]}
    reported = h["environmental_rows"]["reported"]
    assert conditions == {k: v["n"] for k, v in reported.items()}
    assert origin["env_rows"] == h["environmental_rows"]["rows"]


def test_the_scope_box_is_built_at_head_from_the_shared_block(tmp_path: Path) -> None:
    """The page's box carries the same sentences the generated documents open with."""
    import io

    import pandas as pd

    from mnp.report import scope

    stats = _show("HEAD", ORIGIN_STATS)
    if stats is None:
        pytest.skip("HEAD has no origin table")
    data = _build("HEAD", tmp_path / "data.json")
    table = pd.read_csv(io.StringIO(_show("HEAD", "out/tables/d1_zeta_table.csv")))
    d1 = json.loads(_show("HEAD", "out/tables/d1_stats.json"))
    items = scope.items(scope.gather(table, d1, json.loads(stats)))
    assert data["scope"]["title"] == scope.TITLE
    assert data["scope"]["items"] == [list(i) for i in items]
    review = _show("HEAD", "out/review/REVIEW.md") or ""
    assert data["scope"]["cross_checked"] == (scope.extract(review) is not None)


def test_the_scope_box_is_hidden_unless_the_data_carries_it() -> None:
    template = (HERE / "template.html").read_text(encoding="utf-8")
    box = next(line for line in template.splitlines() if 'id="scope"' in line)
    assert " hidden" in box, box
    # `hidden` only hides what no author rule displays; the box and the sections set display.
    assert "[hidden] { display: none !important; }" in template
    assert "DATA.scope" in template


# -- the same-particle census: built from the ref's table, held against C12 ---------------------


def _head_table():
    import io

    import pandas as pd

    return pd.read_csv(io.StringIO(_show("HEAD", "out/tables/d1_zeta_table.csv")))


@pytest.fixture(scope="module")
def build_data():
    sys.path.insert(0, str(HERE))
    try:
        import build_data
    finally:
        sys.path.remove(str(HERE))
    return build_data


@pytest.fixture(scope="module")
def head_census():
    from mnp.eval import comparability

    table = _head_table()
    rows = [comparability.ZetaRow.from_mapping(r) for r in table.to_dict(orient="records")]
    return table, comparability.same_particle_census(rows)


def test_the_census_on_the_page_is_the_modules_own(build_data, head_census) -> None:
    table, census = head_census
    sp = build_data.same_particle_section(table)
    assert sp["pairs"] == census.pairs
    assert [(c["key"], c["pairs"]) for c in sp["categories"]] == list(census.categories)
    assert [(f["field"], f["pairs"]) for f in sp["fields"]] == list(census.absent_fields)
    only = dict(census.only_absent_field)
    assert all(f["only"] == only.get(f["field"], 0) for f in sp["fields"])
    assert (sp["absence_cross"], sp["absence_same"]) == (
        census.absence_cross_paper,
        census.absence_same_paper,
    )


def _guide_text(table, census) -> str:
    """What REVIEW.md prints for the census: §5.7 and C12, rendered by the guide's own code."""
    from types import SimpleNamespace

    from mnp.report import review_guide

    facts = SimpleNamespace(table=table, same_particle=census)
    return "\n".join(
        [
            "## 5. Every formula",
            *review_guide.section_5_7(facts),
            "## 6. What the dataset proves, and what it does not",
            *review_guide._same_particle_claim(census),
        ]
    )


def test_the_census_checks_read_what_the_guide_prints(build_data, head_census) -> None:
    table, census = head_census
    sp = build_data.same_particle_section(table)
    text = _guide_text(table, census)
    checks = build_data.same_particle_checks(text, sp)
    # eight numbers of C12, its top field, the total row and the ranking, then one per table row
    assert len(checks) == 11 + len(sp["categories"]) + len(sp["fields"])
    assert all(c["ok"] for c in checks), [c for c in checks if not c["ok"]]

    every = f"| all same-particle pairs | {census.pairs:,} |".replace(",", " ")
    assert every in text
    tampered = build_data.same_particle_checks(
        text.replace(every, "| all same-particle pairs | 1 |"), sp
    )
    assert [c["name"] for c in tampered if not c["ok"]] == ["§5.7 all same-particle pairs"]


def test_the_census_block_is_hidden_unless_the_data_carries_it() -> None:
    template = (HERE / "template.html").read_text(encoding="utf-8")
    block = next(line for line in template.splitlines() if 'id="absence"' in line)
    assert " hidden" in block, block
    assert "DATA.same_particle" in template
    assert "if (!SP) return;" in template
