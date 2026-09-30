"""The scope block every reader-facing document opens with (Martin, 2026-09-30).

"Reveal the truth at the beginning so the scope is clear": REVIEW.md, the dataset card and the
demo's README and METHOD each open, right under their title, with the same short block saying
what the dataset is, that a zeta potential only exists in a liquid, where the particles came
from, which liquids they were measured in, which corpus they were read from, and what the data
can and cannot be used for. One function renders it, from the committed tables, so the four
documents cannot drift apart and no number in it is typed.
"""

from __future__ import annotations

import copy
import json

import pandas as pd
import pytest

from mnp import config
from mnp.report import scope

DOCS = ("review/REVIEW.md", "release/DATASET_CARD.md", "demo/README.md", "demo/METHOD.md")

# The wording the block uses for each class, pinned here so a relabel is a deliberate edit.
LIQUIDS = {
    "DI_water": "DI water",
    "culture_medium": "culture medium",
    "salt_solution": "salt solution",
    "buffer": "buffer",
    "environmental_water": "environmental water",
    "biofluid": "biofluid",
    "other": "other",
    "unreported": "unreported",
}
AMBIENT = {
    "air_dust": "air or dust",
    "freshwater": "freshwater",
    "seawater": "seawater",
    "soil": "soil",
    "sediment": "sediment",
}


def _n(k: int) -> str:
    return f"{int(k):,}".replace(",", " ")


@pytest.fixture(scope="module")
def committed() -> tuple[pd.DataFrame, dict, dict]:
    tables = config.OUT_TABLES
    return (
        pd.read_csv(tables / "d1_zeta_table.csv"),
        json.loads((tables / "d1_stats.json").read_text()),
        json.loads((tables / "sample_origin_stats.json").read_text()),
    )


@pytest.fixture(scope="module")
def text(committed) -> str:
    return "\n".join(scope.block(*committed))


def test_the_block_states_what_the_dataset_is(text: str, committed):
    table = committed[0]
    q = table["quantity"].value_counts()
    assert "surface charge of micro- and nanoplastic particles" in text
    assert "measured in liquids in laboratory studies" in text
    assert f"{_n(len(table))} rows from {_n(table['pmcid'].nunique())} papers" in text
    assert f"{_n(q['zeta_potential'])} zeta potentials" in text
    assert f"{_n(q['electrophoretic_mobility'])} electrophoretic mobilities" in text
    assert "exists only in a liquid" in text
    assert "not in the environment it came from" in text


def test_the_block_states_the_hand_corrected_origin(text: str, committed):
    _, _, origin = committed
    h, n = origin["hand_corrected"], origin["rows"]
    syn, env, where = h["synthetic"]["rows"], h["environmental_rows"], h["environment"]
    share = f"{100 * syn / n:.1f} % of rows ({_n(syn)} / {_n(n)})"
    assert f"{share} measure a synthetic particle" in text
    assert f"Only {env['rows']} rows, from {env['papers']} papers," in text
    rows, papers = where["rows"], where["papers"]
    assert f"{rows['wastewater']} from wastewater effluent ({papers['wastewater']} papers)" in text
    if rows["other"]:
        noun = "paper" if papers["other"] == 1 else "papers"
        assert f'{rows["other"]} classed "other" ({papers["other"]} {noun})' in text
    zero = [label for key, label in AMBIENT.items() if not rows[key]]
    assert zero, "the committed stats have no empty ambient environment; rewrite this check"
    listed = ", ".join(zero[:-1]) + " or " + zero[-1] if len(zero) > 1 else zero[0]
    assert f"From {listed}: 0 rows" in text
    assert "`sample_origin_stats.json`" in text and "C11" in text


def test_the_block_states_the_measurement_liquids(text: str, committed):
    counts = committed[0]["medium_class"].value_counts()
    line = next(t for t in text.splitlines() if "The measurement liquids." in t)
    shown = [f"{label} {_n(counts.get(key, 0))}" for key, label in LIQUIDS.items()]
    assert ", ".join(shown) in line
    assert sum(counts) == len(committed[0])


def test_the_block_states_the_corpus(text: str, committed):
    _, stats, _ = committed
    d = stats["denominators"]
    chain = (
        f"{_n(d['all_hits'])} hits, {_n(d['oa_records'])} of them open access, "
        f"{_n(stats['text_availability']['fetched'])} full texts fetched, "
        f"{_n(stats['n_papers'])} papers with a measurement"
    )
    assert "one database (Europe PMC) for one query" in text
    assert chain in text
    hits = json.loads((config.EPMC_SEARCH_DIR / "hit_counts.json").read_text())
    assert (d["all_hits"], d["oa_records"]) == (hits["hits_all"], hits["hits_oa"])
    assert f"`{scope.NOTES}`" in text


def test_the_block_says_what_it_can_and_cannot_be_used_for(text: str):
    line = next(t for t in text.splitlines() if "used for" in t)
    assert "How laboratory measurements are reported and whether they can be compared" in line
    assert "Not how plastics behave in air, water or soil" in line


def test_the_block_is_five_to_eight_lines(committed):
    lines = scope.block(*committed)
    assert 5 <= len(lines) <= 8, lines
    assert lines[0] == f"**{scope.TITLE}**"
    assert lines[-1].strip(), "the caller adds the blank line after the block"


def test_the_block_moves_with_the_stats(committed):
    table, stats, origin = committed
    moved = copy.deepcopy(origin)
    h = moved["hand_corrected"]
    h["environment"]["rows"]["seawater"] = 2
    h["environment"]["papers"]["seawater"] = 1
    h["environmental_rows"]["rows"] += 2
    h["environmental_rows"]["papers"] += 1
    more = copy.deepcopy(stats)
    more["denominators"]["all_hits"] += 1000
    text = "\n".join(scope.block(table, more, moved))
    assert "2 from seawater (1 paper)" in text
    assert "From air or dust, freshwater, soil or sediment: 0 rows" in text
    assert f"{_n(stats['denominators']['all_hits'] + 1000)} hits" in text


def test_without_the_origin_table_the_block_says_nothing_about_origin(committed):
    table, stats, _ = committed
    text = "\n".join(scope.block(table, stats, None))
    assert "synthetic" not in text and "real environment" not in text
    assert "exists only in a liquid" in text and "one database (Europe PMC)" in text


def test_extract_finds_the_block_and_nothing_else(text: str):
    doc = f"# Title\n\n{text}\n\nThe first paragraph after it.\n\n## 1. A section\n"
    assert scope.extract(doc) == text.rstrip("\n")
    assert scope.extract("# Title\n\nNo block here.\n") is None


@pytest.mark.parametrize("name", DOCS)
def test_every_shipped_document_opens_with_the_block(name: str, committed):
    path = config.OUT / name
    doc = path.read_text(encoding="utf-8")
    block = scope.extract(doc)
    assert block is not None, f"{name} has no scope block"
    title = doc.split("\n", 1)[0]
    assert title.startswith("# ")
    assert doc.startswith(f"{title}\n\n{block}\n"), f"{name}: the block is not under the title"
    assert doc.index(block) < doc.index("\n## ")
    assert block == "\n".join(scope.block(*committed)).rstrip("\n")


def test_the_shipped_documents_carry_the_same_block_word_for_word():
    blocks = {name: scope.extract((config.OUT / name).read_text(encoding="utf-8")) for name in DOCS}
    assert None not in blocks.values(), [k for k, v in blocks.items() if v is None]
    assert len(set(blocks.values())) == 1, "the scope block differs between documents"


def test_the_corpus_notes_exist_and_name_the_query():
    notes = config.ROOT / scope.NOTES
    assert notes.is_file(), scope.NOTES
    text = notes.read_text(encoding="utf-8")
    hits = json.loads((config.EPMC_SEARCH_DIR / "hit_counts.json").read_text())
    assert hits["query_all"] in text
    assert "Martin, 2026-09-30" in text
    for n in (hits["hits_all"], hits["hits_oa"], hits["hits_all"] - hits["hits_oa"]):
        assert _n(n) in text, n


def test_the_handoff_points_to_the_corpus_notes():
    handoff = (config.ROOT / "HANDOFF_2026-09-28.md").read_text(encoding="utf-8")
    last = handoff.rsplit("\n## ", 1)[-1]
    assert scope.NOTES in last


def test_demo_is_built_after_origin_whose_stats_its_block_reads():
    from mnp.report import __main__ as cli

    names = list(cli.RUNNERS)
    assert names.index("origin") < names.index("demo") < names.index("review")
