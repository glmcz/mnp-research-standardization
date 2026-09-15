import json

import pandas as pd
import pytest

from mnp.report import d1


def _table():
    """Four papers. A complete; B lacks I and T; C has only the medium; D has
    only an unverified row and must not count."""
    rows = []

    def row(pmcid, verified=True, **over):
        base = dict(
            pmcid=pmcid, year=2020, journal="J", row_id=f"{pmcid}-r1", quantity="zeta_potential",
            value=-30.0, unit="mV", medium_text="10 mM NaCl", medium_class="salt_solution",
            ionic_strength_mM=10.0, pH=7.0, pH_text=None, temperature_C=25.0,
            temperature_qualifier=None, instrument="Zetasizer", medium_reported=True,
            ionic_strength_reported=True, pH_reported=True, temperature_reported=True,
            instrument_reported=True, conditions_complete=True, medium_matches_exposure=True,
            evidence_verified=verified, flags="",
        )  # fmt: skip
        base.update(over)
        return base

    rows.append(row("A"))
    rows.append(row("B", ionic_strength_reported=False, temperature_reported=False,
                    conditions_complete=False))  # fmt: skip
    rows.append(row("B", row_id="B-r2", ionic_strength_reported=False, temperature_reported=False,
                    conditions_complete=False))  # fmt: skip
    rows.append(row("C", ionic_strength_reported=False, pH_reported=False,
                    temperature_reported=False, instrument_reported=False,
                    conditions_complete=False, medium_matches_exposure=None))  # fmt: skip
    rows.append(row("D", verified=False, flags="evidence_unverified"))
    df = pd.DataFrame(rows)
    df["value_text"] = None
    df.loc[df.pmcid == "C", ["value", "value_text"]] = [None, "not printed"]
    return df


def _records():
    return pd.DataFrame(
        {
            "pmcid": ["A", "B", "C", "D", "E", "F"],
            "year": [2016, 2020, 2024, 2024, 2020, 2016],
            "journal": ["J", "J", "K", "K", "K", "L"],
            "is_oa": [True, True, True, True, False, False],
        }
    )


def test_paper_stats_use_verified_rows_only_and_any_row_per_paper():
    stats = d1.paper_stats(_table())
    assert stats["n_papers"] == 3
    assert stats["n_papers_with_unverified_only"] == 1
    assert stats["n_papers_with_a_printed_number"] == 2
    assert stats["n_papers_measured_but_no_number_printed"] == 1
    missing = {m["condition"]: m for m in stats["missing"]}
    assert missing["ionic_strength"]["k_missing"] == 2
    assert missing["temperature"]["k_missing"] == 2
    assert missing["pH"]["k_missing"] == 1
    assert missing["instrument"]["k_missing"] == 1
    assert missing["medium"]["k_missing"] == 0
    assert missing["any"]["k_missing"] == 2
    assert missing["ionic_strength"]["fraction"] == pytest.approx(2 / 3)
    lo, hi = missing["ionic_strength"]["wilson_lo"], missing["ionic_strength"]["wilson_hi"]
    assert 0.0 < lo < 2 / 3 < hi <= 1.0


def test_both_denominators_are_reported():
    stats = d1.paper_stats(_table(), n_oa_records=4, n_all_hits=6)
    ionic = next(m for m in stats["missing"] if m["condition"] == "ionic_strength")
    assert ionic["n"] == 3
    assert ionic["fraction_of_oa_records"] == pytest.approx(2 / 4)
    assert ionic["fraction_of_all_hits_lower_bound"] == pytest.approx(2 / 6)
    assert stats["denominators"] == {"papers_with_verified_zeta": 3, "oa_records": 4, "all_hits": 6}


def test_oa_bias_table_compares_year_bands_and_journals():
    bias = d1.oa_bias(_records())
    by_year = bias[bias.dimension == "year_band"].set_index("level")
    assert by_year.loc["<=2018", "oa"] == 1 and by_year.loc["<=2018", "non_oa"] == 1
    assert by_year.loc["2023-2026", "oa"] == 2 and by_year.loc["2023-2026", "non_oa"] == 0
    by_journal = bias[bias.dimension == "journal"].set_index("level")
    assert by_journal.loc["K", "oa"] == 2 and by_journal.loc["K", "non_oa"] == 1
    assert set(bias.columns) >= {"dimension", "level", "oa", "non_oa", "oa_share"}


def test_build_writes_every_reviewer_artefact(tmp_path):
    written = d1.build(
        _table(),
        _records(),
        tmp_path / "tables",
        tmp_path / "figures",
        hit_counts={"hits_oa": 4, "hits_all": 6},
    )
    names = {p.name for p in written}
    assert names == {
        "d1_zeta_table.csv",
        "d1_stats.json",
        "d1_stats.md",
        "d1_oa_bias.csv",
        "d1_missing_conditions.png",
    }
    stats = json.loads((tmp_path / "tables" / "d1_stats.json").read_text())
    assert stats["n_papers"] == 3
    md = (tmp_path / "tables" / "d1_stats.md").read_text()
    assert "ionic strength" in md.lower()
    assert "67%" in md or "66.7%" in md
    assert "open-access" in md.lower()
    table = pd.read_csv(tmp_path / "tables" / "d1_zeta_table.csv")
    assert len(table) == 5
    assert (tmp_path / "figures" / "d1_missing_conditions.png").stat().st_size > 1000


def test_build_with_an_empty_table_still_writes_stats(tmp_path):
    empty = _table().iloc[0:0]
    written = d1.build(empty, _records(), tmp_path / "t", tmp_path / "f")
    stats = json.loads((tmp_path / "t" / "d1_stats.json").read_text())
    assert stats["n_papers"] == 0
    assert len(written) == 5


def test_build_with_a_prefix_writes_a_separate_artefact_set(tmp_path):
    written = d1.build(_table(), _records(), tmp_path / "t", tmp_path / "f", prefix="d1_gold")
    assert {p.name for p in written} == {
        "d1_gold_zeta_table.csv",
        "d1_gold_stats.json",
        "d1_gold_stats.md",
        "d1_gold_oa_bias.csv",
        "d1_gold_missing_conditions.png",
    }


def test_gold_table_is_prepared_from_the_annotation_columns():
    """The gold CSV names booleans I_reported/T_reported and has no verified column."""
    gold = pd.DataFrame(
        [
            dict(pmcid="A", row_id="A-g1", quantity="zeta_potential", value=-30.0, unit="mV",
                 medium_text="10 mM NaCl", ionic_strength_mM=10.0, I_reported=True, pH=None,
                 pH_reported=False, temperature_C=None, T_reported=True, instrument="Zetasizer",
                 instrument_reported=True, notes=""),
            dict(pmcid="B", row_id="B-g1", quantity=None, value=None, unit=None, medium_text=None,
                 ionic_strength_mM=None, I_reported=False, pH=None, pH_reported=False,
                 temperature_C=None, T_reported=False, instrument=None, instrument_reported=False,
                 notes="no_measurement"),
        ]
    )  # fmt: skip
    prepared = d1.prepare_gold(gold)
    assert list(prepared["pmcid"]) == ["A"]  # the no_measurement placeholder is dropped
    assert bool(prepared.loc[0, "evidence_verified"]) is True
    assert bool(prepared.loc[0, "temperature_reported"]) is True
    assert bool(prepared.loc[0, "conditions_complete"]) is False
    stats = d1.paper_stats(prepared)
    assert stats["n_papers"] == 1
    assert next(m for m in stats["missing"] if m["condition"] == "pH")["k_missing"] == 1


def test_denominator_note_is_carried_into_the_markdown(tmp_path):
    d1.build(
        _table(), _records(), tmp_path / "t", tmp_path / "f",
        hit_counts={"hits_oa": 50},
        denominator_note="the 50 papers of the stratified random sample",
    )  # fmt: skip
    md = (tmp_path / "t" / "d1_stats.md").read_text()
    assert "the 50 papers of the stratified random sample" in md
    assert "all open-access records the query returned" not in md


def test_papers_with_no_retrievable_text_are_counted_separately(tmp_path):
    """An empty deposit is not a paper that was read and found to report nothing.

    Eleven of the 858 fetched XMLs carry no body at all — conference-abstract volumes and
    "available as a PDF" stubs. Counting them in the same denominator as papers that were
    actually read makes the corpus look better covered than it is, and makes an empty
    extraction indistinguishable from a real negative.
    """
    import pandas as pd

    from mnp.report import d1

    articles = pd.DataFrame(
        [
            {"pmcid": "PMC1", "extraction_text": "Zeta potential was -30 mV.", "year": 2020},
            {"pmcid": "PMC2", "extraction_text": "", "year": 2021},
            {"pmcid": "PMC3", "extraction_text": None, "year": 2022},
        ]
    )
    counts = d1.text_availability(articles)
    assert counts["fetched"] == 3
    assert counts["with_retrievable_text"] == 1
    assert counts["no_retrievable_text"] == 2
    assert counts["pmcids_without_text"] == ["PMC2", "PMC3"]
