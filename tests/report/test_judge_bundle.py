"""A judge must not be able to find the answer by grepping the repository.

The first judge run was nominally blind: two readings labelled A and B, order flipped, the
mapping kept elsewhere. It leaked anyway — checking pipeline mechanics, the judge grepped for
a value and hit `gold_parts/*.json` and the counterpart order file. Eight files in the repo
contain it. Blinding by filename does not survive a grep, so the judge gets a bundle
containing only the article and the case, and nothing else.
"""

import json

import pytest

from mnp.report import judge_bundle

CASES = [
    {"case": "c1", "pmcid": "PMC1", "field": "pH", "reading_A": 7.0, "reading_B": None},
    {"case": "c2", "pmcid": "PMC2", "field": "temperature_C", "reading_A": None,
     "reading_B": 25.0},
]  # fmt: skip
ARTICLES = {"PMC1": "the pH was 7.0 throughout", "PMC2": "samples were incubated at 25 C"}


def test_a_bundle_contains_the_article_and_the_case_and_nothing_else(tmp_path):
    out = judge_bundle.write(CASES, ARTICLES, tmp_path / "judge-a", judge="a")
    names = sorted(p.name for p in out.iterdir())
    assert names == ["README.md", "articles", "cases.json"]
    assert sorted(p.name for p in (out / "articles").iterdir()) == ["PMC1.txt", "PMC2.txt"]


def test_the_bundle_never_says_which_reading_came_from_where(tmp_path):
    out = judge_bundle.write(CASES, ARTICLES, tmp_path / "judge-a", judge="a")
    blob = json.dumps(json.load(open(out / "cases.json")))
    assert "gold" not in blob.lower()
    assert "extraction" not in blob.lower()


def test_the_two_judges_get_opposite_orders(tmp_path):
    a = judge_bundle.write(CASES, ARTICLES, tmp_path / "a", judge="a")
    b = judge_bundle.write(CASES, ARTICLES, tmp_path / "b", judge="b")
    ca = {c["case"]: c for c in json.load(open(a / "cases.json"))}
    cb = {c["case"]: c for c in json.load(open(b / "cases.json"))}
    assert ca["c1"]["reading_A"] == cb["c1"]["reading_B"]
    assert ca["c1"]["reading_B"] == cb["c1"]["reading_A"]


def test_the_mapping_is_written_outside_the_bundle(tmp_path):
    out = judge_bundle.write(CASES, ARTICLES, tmp_path / "a", judge="a",
                             mapping_dir=tmp_path / "keys")  # fmt: skip
    mapping = json.load(open(tmp_path / "keys" / "a.mapping.json"))
    assert mapping["c1"] in ("A_is_gold", "A_is_extraction")
    assert not (out / "a.mapping.json").exists()
    assert "mapping" not in [p.name for p in out.iterdir()]


def test_a_bundle_refuses_to_be_written_inside_the_repository_data(tmp_path, monkeypatch):
    """The point is that the judge cannot reach the gold set; writing the bundle next to it
    defeats that, so it is refused rather than merely discouraged."""
    from mnp import config

    monkeypatch.setattr(config, "DATA_INTERIM", tmp_path / "interim")
    with pytest.raises(ValueError, match="refusing to write a judge bundle inside"):
        judge_bundle.write(CASES, ARTICLES, tmp_path / "interim" / "judge-a", judge="a")
