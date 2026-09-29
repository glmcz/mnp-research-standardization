"""Sample origin, per row: the reader's per-particle answers matched back to the zeta rows,
counted, checked against the suppliers the table already names, and sampled for hand checking."""

import json

import pandas as pd
import pytest

from mnp.report import origin as report

_REPORTED = {
    "medium_reported": True,
    "ionic_strength_reported": False,
    "pH_reported": False,
    "temperature_reported": True,
    "instrument_reported": True,
    "conditions_complete": False,
}


def _row(pmcid, n, name, **extra):
    return {
        "pmcid": pmcid,
        "row_id": f"{pmcid}-r{n}",
        "particle_name": name,
        "material": "polystyrene",
        "supplier": None,
        "medium_text": "water",
        "medium_class": "DI_water",
        "evidence_quote": "",
        **_REPORTED,
        **extra,
    }


TABLE = pd.DataFrame(
    [
        _row("PMCA", 1, "PS-COOH", supplier="Polysciences"),
        _row("PMCA", 2, "PS-COOH", supplier="Polysciences", medium_class="environmental_water"),
        _row("PMCA", 3, "PE  fragments", supplier="Sigma (PE pellets)"),
        _row(
            "PMCB",
            1,
            "Beach MPs",
            medium_text="seawater, conductivity 52 mS/cm",
            medium_class="environmental_water",
        ),
        _row(
            "PMCB",
            2,
            "Beach MPs",
            medium_text="10 mM NaCl",
            medium_class="salt_solution",
            ionic_strength_reported=True,
        ),
        _row("PMCC", 1, "NPs", evidence_quote="EC was 850 µS cm-1"),
        _row("PMCD", 1, "PS"),
    ]
)


def _answer(pmcid, *particles, refused=False, text=None):
    body = text if text is not None else json.dumps({"particles": list(particles)})
    return {"pmcid": pmcid, "text": body, "refused": refused, "particle_names": []}


def _p(name, origin, env=None, aged=False, cites=("PMCX:L1",)):
    return {
        "particle_name": name,
        "origin": origin,
        "aged_in_lab": aged,
        "environment": env,
        "citations": list(cites),
        "reason": f"{name} is {origin}",
    }


ANSWERS = {
    "PMCA": _answer(
        "PMCA",
        _p("PS-COOH", "commercial"),
        _p("PE fragments", "lab_fabricated", aged=True),  # the table has two spaces
        _p("PP", "commercial"),  # not a row of this paper
    ),
    "PMCB": _answer("PMCB", _p("Beach MPs", "environmental", env="sediment")),
    "PMCC": _answer("PMCC", _p("NPs", "unclear", aged=None)),
    "PMCD": _answer("PMCD", refused=True, text="reader refused: Usage Policy"),
}


def _rows():
    return report.attach(TABLE, report.classifications(ANSWERS))


def test_answers_are_matched_back_to_rows_by_particle_name():
    rows = _rows().set_index("row_id")
    assert rows.loc["PMCA-r1", "origin"] == "commercial"
    assert rows.loc["PMCA-r3", "origin"] == "lab_fabricated"
    assert rows.loc["PMCA-r3", "matched_by"] == "folded"
    assert rows.loc["PMCB-r1", "environment"] == "sediment"
    assert rows.loc["PMCD-r1", "origin"] == "unanswered", "a refused paper's rows are not guessed"
    assert len(rows) == len(TABLE)


def test_origin_counts_rows_and_papers_and_names_every_environment():
    stats = report.stats(_rows(), report.classifications(ANSWERS))
    assert stats["origin"]["rows"] == {
        "commercial": 2,
        "lab_fabricated": 1,
        "environmental": 2,
        "unclear": 1,
        "unanswered": 1,
    }
    assert stats["origin"]["papers_any"]["commercial"] == 1
    assert stats["origin"]["papers_only"]["environmental"] == 1
    assert stats["environment"]["rows"]["air_dust"] == 0
    assert stats["environment"]["rows"]["sediment"] == 2
    assert stats["aged_in_lab"]["rows_true"] == 1
    assert stats["answers"]["refused"] == 1
    assert stats["matching"]["names_not_in_rows"] == [["PMCA", "PP"]]
    assert stats["synthetic"]["medium"] == {
        "lab_liquid": 2, "environmental_water": 1, "other": 0, "unreported": 0
    }  # fmt: skip


def test_environmental_rows_report_their_conditions_conductivity_and_own_water():
    env = report.stats(_rows(), report.classifications(ANSWERS))["environmental_rows"]
    assert env["rows"] == 2 and env["papers"] == 1
    assert env["reported"]["ionic_strength"] == {"n": 1, "share": 0.5}
    assert env["conditions_complete"] == {"n": 0, "share": 0.0}
    assert env["conductivity_printed"] == 1
    assert env["own_environmental_water"] == 1 and env["lab_liquid"] == 1


def test_conductivity_is_read_from_the_medium_or_the_quote():
    assert report.prints_conductivity("seawater (EC 52 mS/cm)", "")
    assert report.prints_conductivity("river water", "conductivity of 410 µS cm-1")
    assert report.prints_conductivity("tap water", "EC = 850 uS/cm")
    assert not report.prints_conductivity("10 mM NaCl", "zeta was -30 mV at 25 cm depth")


def test_rows_that_name_a_supplier_but_are_not_commercial_are_listed():
    listed = report.supplier_disagreements(_rows())
    assert [d["row_id"] for d in listed] == ["PMCA-r3"]
    assert listed[0]["origin"] == "lab_fabricated"


def test_the_hand_check_sample_takes_every_environmental_particle_and_is_seeded():
    classes = pd.DataFrame(
        [{"pmcid": f"P{i}", "particle_name": "x", "origin": "commercial"} for i in range(100)]
        + [{"pmcid": f"E{i}", "particle_name": "x", "origin": "environmental"} for i in range(7)]
        + [{"pmcid": f"U{i}", "particle_name": "x", "origin": "unclear"} for i in range(55)]
    )
    sample = report.hand_check_sample(classes, seed=1, n=40)
    counts = sample["stratum"].value_counts().to_dict()
    assert counts == {"random": 40, "unclear": 40, "environmental": 7}
    assert set(sample.loc[sample.stratum == "random", "origin"]) == {"commercial"}
    again = report.hand_check_sample(classes, seed=1, n=40)
    assert sample.equals(again)
    small = report.hand_check_sample(classes, seed=1, n=5)
    assert small["stratum"].value_counts().to_dict() == {
        "environmental": 7,
        "random": 5,
        "unclear": 5,
    }


def test_agreement_is_counted_per_stratum_and_on_the_synthetic_split():
    sample = pd.DataFrame(
        [
            {"pmcid": "A", "particle_name": "x", "stratum": "random", "origin": "commercial"},
            {"pmcid": "B", "particle_name": "x", "stratum": "random", "origin": "commercial"},
            {
                "pmcid": "C",
                "particle_name": "x",
                "stratum": "environmental",
                "origin": "environmental",
            },
        ]
    )
    hand = pd.DataFrame(
        [
            {"pmcid": "A", "particle_name": "x", "hand_origin": "commercial", "note": ""},
            {"pmcid": "B", "particle_name": "x", "hand_origin": "lab_fabricated", "note": "milled"},
            {"pmcid": "C", "particle_name": "x", "hand_origin": "lab_fabricated", "note": "no"},
        ]
    )
    got = report.agreement(sample, hand)
    assert got["random"] == {"n": 2, "agree": 1, "share": 0.5, "agree_synthetic_split": 2}
    assert got["environmental"]["agree"] == 0
    assert [d["pmcid"] for d in got["disagreements"]] == ["B", "C"]


def test_agreement_ignores_the_hand_files_own_stratum_column():
    sample = pd.DataFrame(
        [{"pmcid": "A", "particle_name": "x", "stratum": "random", "origin": "commercial"}]
    )
    hand = pd.DataFrame(
        [
            {
                "pmcid": "A",
                "particle_name": "x",
                "stratum": "random",
                "hand_origin": "commercial",
                "note": "",
            }
        ]
    )
    assert report.agreement(sample, hand)["random"]["agree"] == 1


def test_hand_verdicts_override_the_readers_origin_for_those_rows_only():
    hand = pd.DataFrame(
        [
            {
                "pmcid": "PMCB",
                "particle_name": "Beach MPs",
                "hand_origin": "lab_fabricated",
                "hand_environment": None,
            },
            {
                "pmcid": "PMCC",
                "particle_name": "NPs",
                "hand_origin": "environmental",
                "hand_environment": "other",
            },
        ]
    )
    fixed = report.apply_hand(_rows(), hand).set_index("row_id")
    assert fixed.loc["PMCB-r1", "origin"] == "lab_fabricated"
    assert pd.isna(fixed.loc["PMCB-r1", "environment"])
    assert fixed.loc["PMCC-r1", "environment"] == "other"
    assert fixed.loc["PMCA-r1", "origin"] == "commercial"
    assert (fixed["origin"] != _rows().set_index("row_id")["origin"]).sum() == 3


def test_a_medium_class_of_other_is_not_counted_as_a_lab_liquid():
    """Both environmental rows filed under "other" were measured in their own sample liquid."""
    table = pd.DataFrame([_row("PMCE", 1, "Effluent MPs", medium_class="other")])
    answers = {"PMCE": _answer("PMCE", _p("Effluent MPs", "environmental", env="wastewater"))}
    env = report.stats(
        report.attach(table, report.classifications(answers)), report.classifications(answers)
    )["environmental_rows"]
    assert env["lab_liquid"] == 0 and env["medium_other"] == 1


def test_the_row_table_carries_the_hand_verdict_beside_the_readers():
    hand = pd.DataFrame(
        [
            {
                "pmcid": "PMCB",
                "particle_name": "Beach MPs",
                "hand_origin": "lab_fabricated",
                "hand_environment": None,
            }
        ]
    )
    out = report.with_final(_rows(), hand).set_index("row_id")
    assert out.loc["PMCB-r1", "origin"] == "environmental", "the reader's answer is kept"
    assert out.loc["PMCB-r1", "final_origin"] == "lab_fabricated"
    assert pd.isna(out.loc["PMCB-r1", "final_environment"])
    assert out.loc["PMCB-r1", "hand_checked"] and out.loc["PMCB-r2", "hand_checked"]
    assert not out.loc["PMCA-r1", "hand_checked"]
    assert out.loc["PMCA-r1", "final_origin"] == "commercial"
    fixed = report.apply_hand(_rows(), hand)
    assert out["final_origin"].tolist() == fixed["origin"].tolist()


def test_papers_whose_methods_the_parser_lost_are_compared_with_the_rest():
    got = report.lost_methods(TABLE, {"PMCB"})
    assert got["papers"] == 4 and got["papers_affected"] == 1
    assert got["pmcids"] == ["PMCB"]
    affected, rest = got["affected"], got["unaffected"]
    assert (affected["papers"], affected["rows"]) == (1, 2)
    assert (rest["papers"], rest["rows"]) == (3, 5)
    assert affected["any_row"]["ionic_strength"] == {"n": 1, "share": 1.0}
    assert rest["any_row"]["ionic_strength"] == {"n": 0, "share": 0.0}
    assert rest["any_row"]["medium"] == {"n": 3, "share": 1.0}
    assert set(affected["any_row"]) == {"medium", "ionic_strength", "pH", "temperature",
                                        "instrument", "complete"}  # fmt: skip


def test_rows_that_are_not_the_authors_own_measurement_are_listed_by_row_id():
    got = report.not_own_rows(TABLE, {"PMCA-r3": "a fabric"})
    assert got == [
        {"row_id": "PMCA-r3", "pmcid": "PMCA", "particle_name": "PE  fragments", "why": "a fabric"}
    ]
    with pytest.raises(ValueError, match="PMCZ-r1"):
        report.not_own_rows(TABLE, {"PMCZ-r1": "a row that is gone"})


def test_papers_measuring_the_whole_sample_are_read_from_the_hand_notes():
    hand = pd.DataFrame(
        [
            {"pmcid": "PMCB", "hand_origin": "environmental",
             "note": "agree; the zeta potential is of the collected effluent as a whole"},
            {"pmcid": "PMCC", "hand_origin": "environmental", "note": "agree"},
            {"pmcid": "PMCD", "hand_origin": "unclear", "note": "the sample as a whole"},
        ]
    )  # fmt: skip
    assert report.whole_sample_papers(hand) == ["PMCB"]


def test_a_printed_conductivity_value_is_found_sentence_by_sentence():
    from mnp.corpus import lines

    texts = (
        "Samples were filtered. The effluent had a conductivity of 1000 to 1050 μS cm-1.",
        "The electrode was placed on a conductive substrate.",
        "Wastewaters had conductivities of 330 μS cm-1 and 1.2 mS/cm, respectively.",
    )
    doc = lines.LinedDoc(
        "PMCB",
        tuple(
            lines.Line(i + 1, t, "methods", i, lines.line_id("methods", i, t))
            for i, t in enumerate(texts)
        ),  # fmt: skip
        (),
    )
    got = report.conductivity_sentences(doc)
    assert got == [
        ("PMCB:L1", "The effluent had a conductivity of 1000 to 1050 μS cm-1."),
        ("PMCB:L3", texts[2]),
    ]


def test_a_conductivity_in_an_environmental_paper_needs_a_recorded_reason():
    found = {"PMCB": [("PMCB:L1", "EC 850 µS/cm.")]}
    with pytest.raises(ValueError, match="PMCB"):
        report.conductivity_in_text(found, reasons={}, quotable={"PMCB"})
    got = report.conductivity_in_text(found, reasons={"PMCB": "why"}, quotable=set())
    assert got == [
        {"pmcid": "PMCB", "why": "why", "lines": [{"line": "PMCB:L1", "sentence": None}]}
    ]
    shown = report.conductivity_in_text(found, reasons={"PMCB": "why"}, quotable={"PMCB"})
    assert shown[0]["lines"][0]["sentence"] == "EC 850 µS/cm."


def test_origin_is_a_runner_after_d1_and_before_release_and_review():
    from mnp.report import __main__ as cli

    names = list(cli.RUNNERS)
    assert names.index("d1") < names.index("origin") < names.index("release")
    assert names.index("origin") < names.index("review")


def test_origin_without_d1_output_skips_cleanly(tmp_path, capsys):
    from mnp.report import __main__ as cli

    assert cli.main(["origin", "--out", str(tmp_path / "out")]) == 0
    assert "d1_zeta_table.csv" in capsys.readouterr().err
    assert not (tmp_path / "out" / "tables" / "sample_origin.csv").exists()
