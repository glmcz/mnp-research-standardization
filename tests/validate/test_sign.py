"""The code half of the validation system: what it accepts from a reader, offline."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from mnp.corpus.lines import Line, LinedDoc, SectionSpan
from mnp.validate import judge, sign


def doc(*texts: str) -> LinedDoc:
    lines = tuple(Line(i + 1, t, "body", i, f"id{i + 1}") for i, t in enumerate(texts))
    return LinedDoc("PMC1", lines, (SectionSpan("body", "== Body", 0, len(lines)),))


DOC = doc(
    "Zeta potential was measured in RPMI medium with 10% FBS.",
    "The pH of the suspension was 7.4.",
    "Particles were dispersed in 10 mM phosphate buffer.",
    "Amine-modified polystyrene beads were purchased from Bangs.",
    "The weather was fine.",
    "In FMQ, FIL ions rapidly coated the cationic PS-NH2 NP surface.",
)
ROW = {"zeta_mV": -12.6, "evidence_quote": "PS-NH2 had a zeta potential of −12.6 mV"}


@pytest.mark.parametrize(
    ("cause", "cites", "want"),
    [
        ("corona", ["PMC1:L1"], "corona"),
        ("corona", ["PMC1:L5"], "unsupported"),  # a line that names no protein or organic matter
        # The rule counts "another coating adsorbed" as corona; a surfactant coat is one
        # (PMC11117817, found when V1 rejected 13 well-cited answers on 2026-10-19).
        ("corona", ["PMC1:L6"], "corona"),
        ("ph", ["L2"], "ph"),
        ("ph", ["PMC1:L1"], "unsupported"),
        ("ions", ["PMC1:L3"], "ions"),
        ("label_error", ["PMC1:L4"], "label_error"),
        ("corona", ["PMC9:L1"], "unsupported"),  # another paper's line
        ("corona", ["PMC1:L99"], "unsupported"),  # no such line
        ("corona", [], "unsupported"),
        ("other_stated", ["PMC1:L5"], "other_stated"),
        ("unexplained", [], "unexplained"),
    ],
)
def test_a_cause_is_kept_only_with_the_evidence_it_needs(cause, cites, want):
    assert sign.decide({"cause": cause, "citations": cites}, DOC, ROW).cause == want


def test_an_invalid_or_missing_cause_is_unparsed():
    assert sign.decide({"cause": "magic"}, DOC, ROW).cause == "unparsed"
    assert sign.decide(None, DOC, ROW).cause == "unparsed"


@pytest.mark.parametrize(
    ("quote", "value", "want"),
    [
        ("zeta potential of −12.6 mV", -12.6, -1),
        ("zeta potential of -12.6 mV", -12.6, -1),
        ("zeta potential of 12.6 mV", -12.6, +1),
        ("zeta potential of +12.6 mV", -12.6, +1),
        ("ranged 3 ± 12.6 mV and −12.6 mV", -12.6, -1),  # skips the one after ±
        ("no number here", -12.6, None),
        ("value 112.6 mV", -12.6, None),  # 12.6 inside a longer number does not count
    ],
)
def test_printed_sign_reads_the_quote(quote, value, want):
    assert sign.printed_sign(quote, value) == want


def test_extraction_error_needs_the_quote_to_print_the_other_sign():
    same = sign.decide({"cause": "extraction_error", "citations": ["PMC1:L1"]}, DOC, ROW)
    flipped = sign.decide(
        {"cause": "extraction_error", "citations": ["PMC1:L1"]},
        DOC,
        {"zeta_mV": -12.6, "evidence_quote": "had a zeta potential of 12.6 mV"},
    )
    assert (same.cause, flipped.cause) == ("unsupported", "extraction_error")


def test_kappa():
    assert sign.kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"]) == 1.0
    assert sign.kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"]) == pytest.approx(0.0)
    assert sign.kappa([], []) is None


def test_v2_keeps_a_cause_only_when_both_readers_pass_and_agree(monkeypatch):
    monkeypatch.setattr(sign.origin, "load_doc", lambda p: DOC)
    cands = pd.DataFrame(
        [
            {
                "pmcid": "PMC1",
                "row_id": f"r{i}",
                "zeta_mV": -12.6,
                "surface": "amine",
                "medium_class": "culture_medium",
                "evidence_quote": ROW["evidence_quote"],
            }
            for i in (1, 2, 3)
        ]
    )

    def reply(entries):
        return {"text": json.dumps({"rows": entries})}

    answers = {
        "A": {
            "PMC1": reply(
                [
                    {"row_id": "r1", "cause": "corona", "citations": ["PMC1:L1"]},
                    {"row_id": "r2", "cause": "corona", "citations": ["PMC1:L1"]},
                    {"row_id": "r3", "cause": "corona", "citations": ["PMC1:L5"]},
                ]
            )
        },
        "B": {
            "PMC1": reply(
                [
                    {"row_id": "r1", "cause": "corona", "citations": ["PMC1:L1"]},
                    {"row_id": "r2", "cause": "ph", "citations": ["PMC1:L2"]},
                    {"row_id": "r3", "cause": "corona", "citations": ["PMC1:L1"]},
                ]
            )
        },
    }
    v = sign.verdicts(cands, answers).set_index("row_id")
    assert list(v.V0) == ["corona", "corona", "corona"]
    assert list(v.V1) == ["corona", "corona", "unsupported"]
    assert list(v.V2) == ["corona", "abstain", "abstain"]


def test_metrics_score_against_labels_and_count_false_explanations():
    v = pd.DataFrame(
        {
            "pmcid": ["P"] * 4,
            "row_id": ["r1", "r2", "r3", "r4"],
            "raw_A": ["corona", "ph", "ions", "unexplained"],
            "raw_B": ["corona", "ph", "ph", "ph"],
            "v1_A": ["corona", "ph", "unsupported", "unexplained"],
            "v1_B": ["corona", "ph", "ph", "ph"],
            "V0": ["corona", "ph", "ions", "unexplained"],
            "V1": ["corona", "ph", "unsupported", "unexplained"],
            "V2": ["corona", "ph", "abstain", "abstain"],
        }
    )
    labels = {
        ("P", "r1"): "corona",
        ("P", "r2"): "corona",
        ("P", "r3"): "ions",
        ("P", "r4"): "unexplained",
    }
    m = sign.metrics(v, {}, labels)
    # V0 says ph for a corona row: one confident wrong cause in four rows
    assert m["V0"]["false_explanation_rate"] == 0.25
    assert m["V0"]["accuracy"] == 0.75
    # V2 abstains on r3 and r4; V3 hands those to the label
    assert m["V2"]["coverage"] == 0.5
    assert m["V3"] == {"accuracy": 0.75, "human_labels_used": 2}


def test_judge_scoring_counts_order_flips_and_accepted_decoys():
    v = pd.DataFrame(
        {
            "pmcid": ["P", "P"],
            "row_id": ["r1", "r2"],
            "raw_A": ["corona", "ph"],
            "raw_B": ["corona", "ph"],
            "v1_A": ["corona", "unsupported"],
            "v1_B": ["corona", "ph"],
        }
    )

    jd0 = judge.JURY[0]

    def item(variant, rows, jd=jd0):
        return {
            "judge": jd,
            "pmcid": "P",
            "reader": "A",
            "variant": variant,
            "order": [],
            "answer": {"rows": rows},
        }

    items = [
        item(
            "order0",
            [
                {"row_id": "r1", "J1": "yes", "J2": "corona", "J3": "no"},
                {"row_id": "r2", "J1": "yes", "J2": "ph", "J3": "no"},
            ],
        ),
        item(
            "order1",
            [
                {"row_id": "r1", "J1": "yes", "J2": "corona", "J3": "no"},
                {"row_id": "r2", "J1": "yes", "J2": "ions", "J3": "no"},
            ],
        ),
        item(
            "decoy",
            [
                {"row_id": "r1", "J1": "yes", "J2": "corona", "J3": "no"},
                {"row_id": "r2", "J1": "no", "J2": "ph", "J3": "no"},
            ],
        ),
        {
            "judge": jd0,
            "pmcid": "reisser_1.9",
            "reader": "-",
            "variant": "trap",
            "order": [],
            "answer": {"J1": "yes"},
        },
    ]
    m = judge.score(v, items, {})
    j = m["per_judge"][jd0]
    assert j["order_flip_rate_J2"] == 0.5
    assert j["decoy_accepted_rate"] == 0.5
    assert j["J1_agrees_with_code_V1"] == 0.5  # r2: the judge accepts what code rejected
    assert m["traps_caught"][jd0] == 0
    assert m["traps_run"][jd0] == 1


def test_a_judge_call_recorded_twice_counts_once():
    """Two runs can overlap and both record one call; the later record is the one scored."""
    trap = {"judge": judge.JURY[0], "pmcid": "reisser_1.9", "reader": "-", "variant": "trap"}
    items = [trap | {"answer": {"J1": "yes"}}, trap | {"answer": {"J1": "no"}}]
    assert judge.latest(items) == [items[1]]
    v = pd.DataFrame(
        {
            "pmcid": ["P"],
            "row_id": ["r1"],
            "raw_A": ["ph"],
            "raw_B": ["ph"],
            "v1_A": ["ph"],
            "v1_B": ["ph"],
        }
    )
    row = {"row_id": "r1", "J1": "yes", "J2": "ph", "J3": "no"}
    judged = trap | {"pmcid": "P", "reader": "A", "variant": "order0", "answer": {"rows": [row]}}
    m = judge.score(v, [judged, judged, *items], {})
    assert m["per_judge"][judge.JURY[0]]["rows_judged"] == 1
    assert m["traps_caught"][judge.JURY[0]] == 1
    assert m["traps_run"][judge.JURY[0]] == 1
