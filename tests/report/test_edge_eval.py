"""Gate 2: score a persona's judgement against the human answer key.

The key is Martin's decisions, not the pipeline's. Until he fills it in, the gate must say
"unanswered" rather than invent agreement.
"""

import pytest
import yaml

from mnp.report import edge


def _key(tmp_path, answers):
    p = tmp_path / "key.yaml"
    p.write_text(yaml.safe_dump(answers, sort_keys=False))
    return p


def test_an_unanswered_key_cannot_be_scored(tmp_path):
    key = _key(tmp_path, {"M1": {"pmcid": "P1", "question": "q", "verdict": "", "reasoning": ""}})
    r = edge.score(key, {"M1": "counts"})
    assert r["answered"] == 0
    assert r["scored"] is False
    assert r["agreement"] is None


def test_agreement_counts_only_answered_cases(tmp_path):
    key = _key(tmp_path, {
        "M1": {"verdict": "counts"},
        "M2": {"verdict": "does not count"},
        "M3": {"verdict": ""},
    })  # fmt: skip
    r = edge.score(key, {"M1": "counts", "M2": "counts", "M3": "counts"})
    assert r["answered"] == 2
    assert r["agree"] == 1
    assert r["agreement"] == pytest.approx(0.5)
    assert r["disagreements"] == [{"case": "M2", "key": "does not count", "persona": "counts"}]


@pytest.mark.parametrize(
    "key_verdict, persona_verdict",
    [
        ("counts", "Counts"),
        ("does not count", "does_not_count"),
        ("not reported", "NOT REPORTED"),
        ("ambiguous - paper does not say", "ambiguous"),
    ],
)
def test_verdicts_match_regardless_of_spelling(tmp_path, key_verdict, persona_verdict):
    key = _key(tmp_path, {"M1": {"verdict": key_verdict}})
    assert edge.score(key, {"M1": persona_verdict})["agree"] == 1


def test_a_case_the_persona_did_not_answer_is_a_disagreement(tmp_path):
    key = _key(tmp_path, {"M1": {"verdict": "counts"}})
    r = edge.score(key, {})
    assert r["agree"] == 0
    assert r["disagreements"][0]["persona"] is None


def test_markdown_says_plainly_when_the_key_is_empty(tmp_path):
    key = _key(tmp_path, {"M1": {"verdict": ""}})
    md = edge.markdown(edge.score(key, {"M1": "counts"}))
    assert "not yet answered" in md.lower()
