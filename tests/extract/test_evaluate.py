import math

import pandas as pd
import pytest

from mnp.extract import evaluate

# Three hand-computed toy papers.
#
# P1: gold one row, fully reported; prediction identical.
# P2: gold one row in PBS with nothing else; prediction has the right value
#     (within 1 mV), invents a pH (FP), leaves I/T/instrument null (None–None,
#     not counted).
# P3: gold two rows (NaCl and PBS); prediction finds only the NaCl row, with
#     the temperature 3 °C off (FP for T and FN for T). The PBS gold row is
#     unmatched: FN for every non-null gold field (value, medium).


def _gold():
    return pd.DataFrame(
        [
            dict(pmcid="P1", row_id="P1-1", particle_name="PS-COOH 100", medium_text="10 mM NaCl",
                 medium_class="salt_solution", ionic_strength_mM=10.0, pH=7.0, temperature_C=25.0,
                 instrument="Zetasizer", quantity="zeta_potential", value=-40.0, unit="mV"),
            dict(pmcid="P2", row_id="P2-1", particle_name="PS 50", medium_text="PBS",
                 medium_class="buffer", ionic_strength_mM=None, pH=None, temperature_C=None,
                 instrument=None, quantity="zeta_potential", value=-20.0, unit="mV"),
            dict(pmcid="P3", row_id="P3-1", particle_name="PS-NH2", medium_text="1 mM NaCl",
                 medium_class="salt_solution", ionic_strength_mM=1.0, pH=6.0, temperature_C=25.0,
                 instrument="Zetasizer", quantity="zeta_potential", value=-30.0, unit="mV"),
            dict(pmcid="P3", row_id="P3-2", particle_name="PS-NH2", medium_text="PBS",
                 medium_class="buffer", ionic_strength_mM=None, pH=7.4, temperature_C=None,
                 instrument="Zetasizer", quantity="zeta_potential", value=-10.0, unit="mV"),
        ]
    )  # fmt: skip


def _pred():
    return pd.DataFrame(
        [
            dict(pmcid="P1", row_id="P1-r1", particle_name="PS-COOH 100 nm",
                 medium_text="10 mM NaCl",
                 medium_class="salt_solution", ionic_strength_mM=10.0, pH=7.0, temperature_C=25.0,
                 instrument="Malvern Zetasizer", quantity="zeta_potential", value=-40.0, unit="mV",
                 evidence_verified=True),
            dict(pmcid="P2", row_id="P2-r1", particle_name="PS 50 nm", medium_text="PBS",
                 medium_class="buffer", ionic_strength_mM=None, pH=7.4, temperature_C=None,
                 instrument=None, quantity="zeta_potential", value=-20.5, unit="mV",
                 evidence_verified=True),
            dict(pmcid="P3", row_id="P3-r1", particle_name="PS-NH2", medium_text="1 mM NaCl",
                 medium_class="salt_solution", ionic_strength_mM=1.0, pH=6.0, temperature_C=28.0,
                 instrument="Zetasizer", quantity="zeta_potential", value=-30.0, unit="mV",
                 evidence_verified=True),
        ]
    )  # fmt: skip


def test_row_matching_is_by_pmcid_fuzzy_particle_and_medium_class():
    pairs = evaluate.match_rows(_pred(), _gold())
    assert sorted((p, g) for p, g in pairs.matched) == [
        ("P1-r1", "P1-1"),
        ("P2-r1", "P2-1"),
        ("P3-r1", "P3-1"),
    ]
    assert pairs.unmatched_gold == ["P3-2"]
    assert pairs.unmatched_pred == []


def test_particle_name_similarity_threshold_is_0_8():
    assert evaluate.name_similarity("PS-COOH 100", "PS-COOH 100 nm") >= 0.8
    assert evaluate.name_similarity("PS-COOH 100", "PE fibre") < 0.8
    assert evaluate.name_similarity(None, "x") == 1.0  # a missing name never blocks a match


def test_row_level_value_scores_use_field_tolerances():
    scores = evaluate.row_level(_pred(), _gold())
    by = {s.field: s for s in scores}
    # value: P1 exact, P2 within 1 mV, P3-1 exact → 3 TP; P3-2 unmatched → 1 FN
    assert (by["value"].tp, by["value"].fp, by["value"].fn) == (3, 0, 1)
    # pH: P1 TP, P2 FP (gold null), P3-1 TP, P3-2 FN (gold 7.4 unmatched)
    assert (by["pH"].tp, by["pH"].fp, by["pH"].fn) == (2, 1, 1)
    # temperature: P1 TP; P2 None–None not counted; P3-1 28 vs 25 → FP + FN; P3-2 None
    assert (by["temperature_C"].tp, by["temperature_C"].fp, by["temperature_C"].fn) == (1, 1, 1)
    # ionic strength: P1 TP, P3-1 TP; P2/P3-2 None–None
    ionic = by["ionic_strength_mM"]
    assert (ionic.tp, ionic.fp, ionic.fn) == (2, 0, 0)
    assert by["value"].precision == 1.0
    assert by["value"].recall == pytest.approx(0.75)
    assert by["pH"].f1 == pytest.approx(2 * (2 / 3) * (2 / 3) / ((2 / 3) + (2 / 3)))


def test_none_none_is_never_a_true_positive():
    """Mutation guard: an evaluator that scores None == None would score P2's T as TP."""
    scores = {s.field: s for s in evaluate.row_level(_pred(), _gold())}
    assert scores["temperature_C"].tp == 1


@pytest.mark.parametrize(
    "field, a, b, ok",
    [
        ("value", -40.0, -40.9, True),
        ("value", -40.0, -42.5, False),  # 2.5 off; 5% of 42.5 is 2.1
        ("value", -100.0, -104.9, True),  # 5% beats 1 mV for large values
        ("pH", 7.0, 7.1, True),
        ("pH", 7.0, 7.15, False),
        ("temperature_C", 25.0, 26.0, True),
        ("temperature_C", 25.0, 26.5, False),
        ("ionic_strength_mM", 10.0, 11.0, True),
        ("ionic_strength_mM", 10.0, 11.5, False),
    ],
)
def test_field_tolerances(field, a, b, ok):
    assert evaluate.within_tolerance(field, a, b) is ok


def test_paper_level_booleans_take_any_row_and_skip_none_none():
    scores = {s.field: s for s in evaluate.paper_level(_pred(), _gold())}
    # medium_reported: all three papers True in both → 3 TP
    medium = scores["medium_reported"]
    assert (medium.tp, medium.fp, medium.fn) == (3, 0, 0)
    # pH_reported: P1 both True; P2 gold False pred True → FP; P3 gold True pred True → TP
    assert (scores["pH_reported"].tp, scores["pH_reported"].fp, scores["pH_reported"].fn) == (
        2,
        1,
        0,
    )
    # conditions_complete: P1 both True; P2 both False (a TN, not a TP); P3 both True
    complete = scores["conditions_complete"]
    assert (complete.tp, complete.fp, complete.fn) == (2, 0, 0)
    assert scores["conditions_complete"].accuracy == pytest.approx(1.0)
    assert scores["pH_reported"].accuracy == pytest.approx(2 / 3)


def test_papers_with_no_gold_rows_count_as_no_measurement_papers():
    gold = _gold()
    gold = pd.concat([gold, pd.DataFrame([dict(pmcid="P4", row_id="P4-none", value=None)])])
    pred = _pred()
    report = evaluate.evaluate(pred, gold)
    assert report["papers"]["gold"] == 4
    assert report["papers"]["gold_without_measurements"] == 1
    assert report["papers"]["pred_without_measurements_agreeing"] == 1


def test_wilson_interval_matches_known_values():
    lo, hi = evaluate.wilson_ci(0, 10)
    assert lo == 0.0 and hi == pytest.approx(0.2775, abs=1e-3)
    lo, hi = evaluate.wilson_ci(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-3) and hi == pytest.approx(0.7634, abs=1e-3)
    lo, hi = evaluate.wilson_ci(10, 10)
    assert lo == pytest.approx(0.7225, abs=1e-3) and hi == 1.0
    assert evaluate.wilson_ci(0, 0) == (float("nan"), float("nan")) or all(
        math.isnan(x) for x in evaluate.wilson_ci(0, 0)
    )


def test_cohens_kappa():
    assert evaluate.cohens_kappa([True, True, False, False], [True, True, False, False]) == 1.0
    assert evaluate.cohens_kappa([True, True, False, False], [True, False, True, False]) == 0.0
    assert math.isnan(evaluate.cohens_kappa([], []))
    # all-True by both: agreement 1 but expected 1 → undefined → 1.0 by convention
    assert evaluate.cohens_kappa([True, True], [True, True]) == 1.0


def test_audit_kappa_pairs_annotator_and_auditor_rows_by_row_id():
    gold = pd.DataFrame(
        [
            dict(pmcid="P1", row_id="P1-1", annotator="claude", medium_text="NaCl", pH=7.0,
                 ionic_strength_mM=1.0, temperature_C=25.0, instrument="Z"),
            dict(pmcid="P1", row_id="P1-1", annotator="author", medium_text="NaCl", pH=None,
                 ionic_strength_mM=1.0, temperature_C=25.0, instrument="Z"),
            dict(pmcid="P2", row_id="P2-1", annotator="claude", medium_text=None, pH=None,
                 ionic_strength_mM=None, temperature_C=None, instrument=None),
        ]
    )  # fmt: skip
    k = evaluate.audit_kappa(gold)
    assert k["n_audited_rows"] == 1
    assert k["kappa"]["pH_reported"] == 0.0 or math.isnan(k["kappa"]["pH_reported"])
    assert k["kappa"]["medium_reported"] == 1.0
    assert evaluate.audit_kappa(gold[gold.annotator == "claude"])["n_audited_rows"] == 0


def test_evaluate_writes_the_precision_recall_table(tmp_path):
    report = evaluate.evaluate(_pred(), _gold())
    path = evaluate.write_precision_recall(report, tmp_path / "d1_precision_recall.csv")
    df = pd.read_csv(path)
    assert set(df.columns) >= {"level", "field", "tp", "fp", "fn", "precision", "recall", "f1", "n"}
    assert {"row", "paper"} == set(df["level"])
    assert report["headline"]["conditions_complete_accuracy"] == pytest.approx(1.0)
    assert "medium_matches_exposure_accuracy" in report["headline"]


def test_gold_column_aliases_drive_the_paper_level_booleans():
    """'room temperature' is T_reported=True with temperature_C blank; the alias must win
    over deriving the boolean from the blank number."""
    gold = pd.DataFrame(
        [dict(pmcid="P1", row_id="g1", value=-30.0, medium_text="10 mM NaCl",
              ionic_strength_mM=10.0, I_reported=True, pH=None, pH_reported=False,
              temperature_C=None, T_reported=True, instrument="Zetasizer",
              instrument_reported=True)]
    )  # fmt: skip
    pred = pd.DataFrame(
        [dict(pmcid="P1", row_id="p1", value=-30.0, medium_text="10 mM NaCl",
              ionic_strength_mM=10.0, pH=None, temperature_C=None,
              temperature_qualifier="room temperature", instrument="Zetasizer")]
    )  # fmt: skip
    scores = {s.field: s for s in evaluate.paper_level(pred, gold)}
    assert (scores["temperature_reported"].tp, scores["temperature_reported"].fn) == (1, 0)
    assert scores["ionic_strength_reported"].tp == 1


def test_evaluation_scores_only_the_annotated_papers():
    """Predictions on papers nobody annotated are not false positives — there is no
    ground truth for them. Scoring 341 extracted papers against a 50-paper gold set
    drove precision to 0.05 and made the numbers meaningless."""
    gold = _gold()
    pred = _pred()
    extra = pred.iloc[[0]].copy()
    extra["pmcid"] = "NOT_ANNOTATED"
    extra["row_id"] = "x1"
    pred_with_extra = pd.concat([pred, extra], ignore_index=True)

    def counts(report):
        # NaN never equals itself, so compare the counts rather than whole dicts
        return [
            (r["level"], r["field"], r["tp"], r["fp"], r["fn"])
            for r in report["row"] + report["paper"]
        ]

    base = evaluate.evaluate(pred, gold)
    widened = evaluate.evaluate(pred_with_extra, gold)
    assert counts(widened) == counts(base)
    assert widened["papers"]["pred_outside_gold"] == 1
    assert widened["papers"]["pred"] == base["papers"]["pred"]
