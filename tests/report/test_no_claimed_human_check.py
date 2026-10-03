"""No generated text may say a person checked what a Claude agent checked.

The origin check of 2026-09-29 (`data/interim/origin/hand_check-*.jsonl`, the file name is
history) was a second reading by a Claude agent with each paper's full text, and the gold set
was annotated by Claude. No row has been checked by a person: `out/review/audit_sample.csv` is
the worksheet for that, and its verdict columns are empty. Martin's standard (ideas.md R6) is
that a dataset must be reproducible by others, so the text has to say who did each check.

These render the text from the committed tables with the same functions `report` uses, so the
committed documents themselves are not what is tested.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from mnp import config
from mnp.corpus.licence import Licence
from mnp.report import release, review, scope

# Each says, or implies, that a person did a check that a Claude agent did.
FALSE_CLAIMS = (
    "person's verdict",
    "hand-checked",
    "Hand-checked",
    "annotated by hand",
    "hand checker",
    "hand check",
    "hand-corrected",
    "a person checked",
    "a person confirmed",
    "a person re-read",
    "read by hand",
    "origin by hand",
)


def _claims(text: str) -> list[str]:
    return [phrase for phrase in FALSE_CLAIMS if phrase in text]


@pytest.fixture(scope="module")
def committed() -> tuple[pd.DataFrame, dict, dict]:
    tables = config.OUT_TABLES
    return (
        pd.read_csv(tables / "d1_zeta_table.csv"),
        json.loads((tables / "d1_stats.json").read_text()),
        json.loads((tables / "sample_origin_stats.json").read_text()),
    )


def test_the_scope_block_names_the_agent(committed):
    text = "\n".join(scope.block(*committed))
    origin = next(line for line in text.splitlines() if "Where the particles came from." in line)
    assert _claims(text) == []
    assert "second reading" in origin and "Claude" in origin


def test_the_card_names_the_agent(tmp_path, committed):
    table, stats, origin = committed
    permissive = {p: Licence("CC-BY", "url", "") for p in table["pmcid"].unique()}
    gold = pd.read_csv(config.ANNOTATION / "gold_50.csv")
    written = release.build(table, stats, tmp_path, licences=permissive, gold=gold, origin=origin)
    card = next(p for p in written if p.name == "DATASET_CARD.md").read_text()
    limit = next(
        line for line in card.splitlines() if "The measured particles are synthetic" in line
    )
    assert "## The κ audit has not been done" in card
    assert _claims(card) == []
    assert "second reading" in limit and "Claude" in limit


def test_the_review_guide_names_the_agent(tmp_path, committed):
    root = tmp_path
    (root / "tables").mkdir()
    (root / "release").mkdir()
    for name in ("d1_zeta_table.csv", "d1_stats.json", "sample_origin_stats.json"):
        shutil.copyfile(config.OUT_TABLES / name, root / "tables" / name)
    shutil.copyfile(
        config.OUT / "release" / "dataset.parquet", root / "release" / "dataset.parquet"
    )
    review.build(root)
    guide = (root / "review" / "REVIEW.md").read_text(encoding="utf-8")
    c11 = guide.split("#### C11.", 1)[1].split("\n#### ", 1)[0]
    assert "### The environmental rows' conditions" in guide
    assert _claims(guide) == []
    assert "second reading" in c11 and "Claude" in c11


def test_the_gold_set_denominator_note_names_the_annotator(tmp_path: Path):
    from mnp.report import __main__ as cli

    cli.run_d1_gold(argparse.Namespace(out=str(tmp_path)))
    note = json.loads((tmp_path / "tables" / "d1_gold_stats.json").read_text())["denominator_note"]
    markdown = (tmp_path / "tables" / "d1_gold_stats.md").read_text(encoding="utf-8")
    assert note in markdown
    assert _claims(note) == []
    assert "Claude" in note
