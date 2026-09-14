"""The gate: score a persona's output against gold and decide pass/fail on stated thresholds.

A gate that a human has to assemble by hand is a gate that stops being run.
"""

import json

import pandas as pd

from mnp.report import gate


def _gold():
    return pd.DataFrame([
        dict(pmcid="P1", row_id="g1", quantity="zeta_potential", value=-30.0, unit="mV",
             medium_text="10 mM NaCl", ionic_strength_mM=10.0, I_reported=True, pH=7.0,
             pH_reported=True, temperature_C=25.0, T_reported=True, instrument="Zetasizer",
             instrument_reported=True, notes=""),
        dict(pmcid="P2", row_id="g2", quantity=None, value=None, unit=None, medium_text=None,
             ionic_strength_mM=None, I_reported=False, pH=None, pH_reported=False,
             temperature_C=None, T_reported=False, instrument=None,
             instrument_reported=False, notes="no_measurement"),
    ])  # fmt: skip


def _pred(value=-30.0):
    return pd.DataFrame([
        dict(pmcid="P1", row_id="r1", quantity="zeta_potential", value=value, unit="mV",
             medium_text="10 mM NaCl", ionic_strength_mM=10.0, pH=7.0, temperature_C=25.0,
             instrument="Zetasizer", evidence_verified=True, flags=""),
    ])  # fmt: skip


def test_a_matching_extraction_passes_every_threshold():
    r = gate.run(_pred(), _gold(), thresholds={"paper:instrument_reported": 0.9})
    assert r["passed"] is True
    assert r["checks"][0]["field"] == "paper:instrument_reported"
    assert r["checks"][0]["passed"] is True


def test_a_threshold_that_is_not_met_fails_the_gate():
    r = gate.run(_pred(value=-99.0), _gold(), thresholds={"row:value": 0.9})
    assert r["passed"] is False
    assert r["checks"][0]["passed"] is False
    assert r["checks"][0]["observed"] == 0.0


def test_a_field_with_no_ground_truth_is_reported_not_scored():
    """The real case from gate 3: the extraction claimed an ionic strength, the gold set
    recorded none anywhere, so precision was 0.00 on zero true positives. That number says
    nothing about the persona and must not fail the gate."""
    import numpy as np

    gold = _gold()
    gold["ionic_strength_mM"] = np.nan  # the gold set records no ionic strength at all
    gold["I_reported"] = False
    r = gate.run(_pred(), gold, thresholds={"row:ionic_strength_mM": 0.9})
    check = r["checks"][0]
    assert check["tp"] == 0 and check["fn"] == 0 and check["fp"] >= 1
    assert check["passed"] is None
    assert check["reason"] == "no ground truth"
    assert r["passed"] is True  # unscoreable fields must not fail the gate


def test_the_default_thresholds_are_the_ones_the_plan_states():
    assert gate.DEFAULT_THRESHOLDS["paper:medium_reported"] == 0.90
    assert gate.DEFAULT_THRESHOLDS["paper:instrument_reported"] == 0.90
    assert gate.DEFAULT_THRESHOLDS["row:value"] == 0.75


def test_the_report_names_every_untraceable_record(tmp_path):
    store = tmp_path / "extractions.jsonl"
    store.write_text(
        json.dumps({"pmcid": "P1", "brief_sha256": "abc"})
        + "\n"
        + json.dumps({"pmcid": "P2", "brief_sha256": None})
        + "\n"
    )
    r = gate.run(_pred(), _gold(), store=store)
    assert r["provenance"]["untraceable"] == 1
    assert r["provenance"]["untraceable_pmcids"] == ["P2"]


def test_markdown_states_the_verdict_and_every_check():
    md = gate.markdown(gate.run(_pred(), _gold()))
    assert "PASS" in md or "FAIL" in md
    assert "paper:instrument_reported" in md
