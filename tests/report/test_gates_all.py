"""Gates 1 and 4, and the runner that reports all four.

Gate 1 asks whether a persona honoured its contract at all; gate 4 asks what it costs.
Neither needs the gold set, so both can run before any ground truth exists.
"""

import json

import pytest
import yaml

from mnp.report import gates


def _store(tmp_path, records):
    p = tmp_path / "extractions.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in records))
    return p


def _rec(pmcid, **over):
    r = {
        "pmcid": pmcid, "model": "claude-code:sonnet", "brief_sha256": "abc",
        "prompt_sha256": "x", "error": None, "measurements": [], "row_flags": [],
        "dropped": [], "n_candidates": 0, "n_candidates_matched": 0,
    }  # fmt: skip
    r.update(over)
    return r


VERIFIED = {"evidence": {"verified": True, "quote": "q"}, "value": -30.0, "unit": "mV"}
UNVERIFIED = {"evidence": {"verified": False, "quote": "q"}, "value": -30.0, "unit": "mV"}


def test_gate1_passes_a_compliant_run(tmp_path):
    store = _store(tmp_path, [
        _rec("P1", measurements=[VERIFIED], row_flags=[[]]),
        _rec("P2"),
    ])  # fmt: skip
    r = gates.contract(store, pmcids=["P1", "P2"])
    assert r["passed"] is True
    assert r["records"] == 2 and r["missing"] == []


def test_gate1_fails_when_a_record_has_no_brief(tmp_path):
    store = _store(tmp_path, [_rec("P1", brief_sha256=None)])
    r = gates.contract(store, pmcids=["P1"])
    assert r["passed"] is False
    assert "untraceable" in r["reasons"][0]


def test_gate1_fails_when_a_claimed_paper_has_no_record(tmp_path):
    """A worker that delegated and did nothing fails here, not in its own report."""
    store = _store(tmp_path, [_rec("P1")])
    r = gates.contract(store, pmcids=["P1", "P2"])
    assert r["passed"] is False
    assert r["missing"] == ["P2"]


def test_gate1_fails_on_an_unverified_row(tmp_path):
    store = _store(tmp_path, [_rec("P1", measurements=[UNVERIFIED], row_flags=[[]])])
    r = gates.contract(store, pmcids=["P1"])
    assert r["passed"] is False
    assert any("unverified" in x for x in r["reasons"])


def test_gate1_fails_on_an_errored_record(tmp_path):
    store = _store(tmp_path, [_rec("P1", error="all models failed")])
    r = gates.contract(store, pmcids=["P1"])
    assert r["passed"] is False


def test_gate4_reports_cost_per_paper(tmp_path):
    store = _store(tmp_path, [
        _rec("P1", measurements=[VERIFIED, VERIFIED], row_flags=[[], []]),
        _rec("P2", measurements=[VERIFIED], row_flags=[[]]),
        _rec("P3"),
    ])  # fmt: skip
    r = gates.pilot(store, pmcids=["P1", "P2", "P3"])
    assert r["papers"] == 3
    assert r["rows"] == 3
    assert r["papers_with_rows"] == 2
    assert r["rows_per_paper"] == pytest.approx(1.0)


def test_the_runner_reports_every_gate_without_stopping_at_the_first(tmp_path):
    store = _store(tmp_path, [_rec("P1", brief_sha256=None)])
    r = gates.run_all(store, pmcids=["P1"], key_path=None, gold=None, pred=None)
    names = [g["gate"] for g in r["gates"]]
    assert names == ["1 contract", "2 edge", "3 gold", "4 pilot"]
    assert r["gates"][0]["passed"] is False
    assert r["gates"][1]["passed"] is None  # no key given
    assert r["gates"][2]["passed"] is None  # no gold given


def test_gate2_is_not_evaluated_when_no_persona_was_asked(tmp_path):
    """The key gained its first answers on 2026-09-13. The runner passed `{}` for the
    persona, so an answered key with nobody to score turned into a 0% FAIL — a failure
    nobody's work caused. Not asking and disagreeing are different outcomes."""
    key = tmp_path / "key.yaml"
    key.write_text(yaml.safe_dump({"C1": {"verdict": "reported, derived"}}))
    store = _store(tmp_path, [_rec("PMC1")])
    r = gates.run_all(store=store, pmcids=["PMC1"], key_path=key)
    g2 = next(g for g in r["gates"] if g["gate"] == "2 edge")
    assert g2["passed"] is None
    assert g2["answered"] == 1
    assert "no persona verdicts" in g2["reason"]
    assert "**FAIL**" not in gates.markdown(r).split("## Gate 3")[0]


def test_gate2_still_fails_a_persona_that_was_asked_and_disagreed(tmp_path):
    key = tmp_path / "key.yaml"
    key.write_text(yaml.safe_dump({"C1": {"verdict": "reported, derived"}}))
    store = _store(tmp_path, [_rec("PMC1")])
    r = gates.run_all(
        store=store, pmcids=["PMC1"], key_path=key, persona_answers={"C1": "not reported"}
    )
    g2 = next(g for g in r["gates"] if g["gate"] == "2 edge")
    assert g2["passed"] is False
