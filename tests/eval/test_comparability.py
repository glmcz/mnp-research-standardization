"""Query kind E: may these two measurements be compared?

The predicate is over a *pair* of rows, so no passage in any paper states it and no
retrieval can reach it. These tests pin the rules, and three of them exist only to stop the
rule set drifting into the two mistakes this dataset is about: letting an unreported
condition acquire a default, and letting the reported *value* count as evidence that two
particles are the same.
"""

import math
from collections import Counter

import pandas as pd
import pytest

from mnp import config
from mnp.eval import comparability as cmp
from mnp.eval.comparability import Comparability as C


def _row(row_id: str = "A-r1", pmcid: str = "PMCA", **over) -> cmp.ZetaRow:
    """A fully reported zeta row. Every test starts from something comparable and breaks it."""
    fields = {
        "quantity": "zeta_potential",
        "material": "polystyrene",
        "functionalisation": "carboxylated",
        "size_measured_nm": 100.0,
        "medium_text": "10 mM NaCl",
        "medium_class": "salt_solution",
        "ionic_strength_mM": 10.0,
        "ionic_strength_source": "reported",
        "pH": 7.4,
        "pH_text": None,
        "temperature_C": 25.0,
        "temperature_qualifier": None,
        "instrument": "Zetasizer Nano ZS (Malvern Instruments, Malvern, UK)",
    }
    fields.update(over)
    return cmp.ZetaRow.from_mapping({"row_id": row_id, "pmcid": pmcid, **fields})


def _codes(a: cmp.ZetaRow, b: cmp.ZetaRow) -> set[str]:
    return {blocker.code for blocker in cmp.comparable(a, b).blockers}


# --- the baseline: the key can say yes ----------------------------------------------------


def test_two_identically_reported_rows_are_comparable():
    verdict = cmp.comparable(_row("A-r1", "PMCA"), _row("B-r1", "PMCB"))
    assert verdict.blockers == ()
    assert verdict.verdict is C.comparable


def test_a_row_is_comparable_with_itself_under_a_different_id():
    assert cmp.comparable(_row("A-r1"), _row("A-r2")).verdict is C.comparable


def test_the_verdict_is_symmetric():
    a = _row("A-r1", "PMCA", pH=7.4)
    b = _row("B-r1", "PMCB", pH=5.0, functionalisation=None)
    assert cmp.comparable(a, b) == cmp.comparable(b, a)


# --- measurand ----------------------------------------------------------------------------


def test_zeta_potential_and_electrophoretic_mobility_are_not_the_same_quantity():
    zeta = _row("A-r1", "PMCA")
    mobility = _row("B-r1", "PMCB", quantity="electrophoretic_mobility")
    assert "quantity_mismatch" in _codes(zeta, mobility)
    assert cmp.comparable(zeta, mobility).verdict is C.not_comparable


def test_instrument_must_match_because_it_is_the_only_proxy_for_the_conversion():
    a = _row("A-r1", "PMCA", instrument="Zetasizer Nano ZS (Malvern, UK)")
    b = _row("B-r1", "PMCB", instrument="ZETA PALS zeta potential analyser (Brookhaven, USA)")
    assert "instrument_mismatch" in _codes(a, b)


def test_instrument_spelling_and_vendor_placement_do_not_block():
    a = _row("A-r1", "PMCA", instrument="Zetasizer Nano-ZS (Malvern Instruments, Malvern, UK)")
    b = _row("B-r1", "PMCB", instrument="Malvern ZetasizerNanoZS")
    assert _codes(a, b) == set()


def test_a_named_model_and_a_family_level_instrument_are_not_the_same_instrument():
    a = _row("A-r1", "PMCA", instrument="Zetasizer Nano ZS (Malvern, UK)")
    b = _row("B-r1", "PMCB", instrument="Zetasizer")
    assert "instrument_mismatch" in _codes(a, b)


def test_nano_zs_and_zs90_are_different_instruments():
    a = _row("A-r1", "PMCA", instrument="Zetasizer Nano ZS (Malvern, UK)")
    b = _row("B-r1", "PMCB", instrument="Zetasizer (Nano ZS90, Malvern Instruments)")
    assert "instrument_mismatch" in _codes(a, b)


# --- particle identity --------------------------------------------------------------------


def test_the_polymer_name_alone_does_not_establish_particle_identity():
    cooh = _row("A-r1", "PMCA", functionalisation="carboxylated")
    nh2 = _row("B-r1", "PMCB", functionalisation="amine-modified")
    assert "functionalisation_mismatch" in _codes(cooh, nh2)
    assert "material_mismatch" not in _codes(cooh, nh2)


def test_an_unreported_functionalisation_is_not_a_bare_surface():
    bare = _row("A-r1", "PMCA", functionalisation="plain")
    silent = _row("B-r1", "PMCB", functionalisation=None)
    assert "functionalisation_unreported" in _codes(bare, silent)


def test_unaged_is_a_weathering_state_not_a_bare_surface():
    """'Unaged' says the particle was not weathered. It says nothing about whether its surface
    carries COOH, so it cannot be merged with 'plain' (Martin, 2026-09-27)."""
    for spelling in ("unaged", "fresh (unaged)"):
        assert cmp.functionalisation_key(spelling) != "BARE", spelling
    unaged = _row("A-r1", "PMCA", functionalisation="unaged")
    plain = _row("B-r1", "PMCB", functionalisation="plain")
    assert "functionalisation_mismatch" in _codes(unaged, plain)


def test_spellings_of_the_same_surface_group_do_not_block():
    a = _row("A-r1", "PMCA", functionalisation="carboxylated (-COOH)")
    b = _row("B-r1", "PMCB", functionalisation="carboxyl groups")
    assert _codes(a, b) == set()


def test_a_surface_state_modifier_is_never_dropped_to_reach_a_match():
    plain = _row("A-r1", "PMCA", functionalisation="carboxylated")
    coronated = _row("B-r1", "PMCB", functionalisation="carboxylate; POPC lipid corona")
    assert "functionalisation_mismatch" in _codes(plain, coronated)


def test_material_spellings_merge_but_composites_never_do():
    assert cmp.material_key("polystyrene") == cmp.material_key("polystyrene (PS)")
    assert cmp.material_key("PS") == cmp.material_key("polystyrene")
    assert cmp.material_key("polystyrene") != cmp.material_key("polystyrene + polyethylene")
    assert cmp.material_key("polystyrene") != cmp.material_key(
        "polystyrene shell on polyacrylonitrile core"
    )
    assert cmp.material_key("polyethylene") != cmp.material_key("high-density polyethylene (HDPE)")


def test_an_unreported_material_blocks():
    assert "material_unreported" in _codes(_row("A-r1"), _row("B-r1", "PMCB", material=None))


# --- "not reported" is never "not present" ------------------------------------------------


@pytest.mark.parametrize(
    ("override", "code"),
    [
        ({"medium_text": None, "medium_class": "unreported"}, "medium_unreported"),
        (
            {"ionic_strength_mM": None, "ionic_strength_source": "unreported"},
            "ionic_strength_unreported",
        ),
        ({"pH": None, "pH_text": None}, "pH_unreported"),
        ({"temperature_C": None, "temperature_qualifier": None}, "temperature_unreported"),
        ({"instrument": None}, "instrument_unreported"),
    ],
)
def test_a_condition_either_row_fails_to_report_blocks_on_that_condition(override, code):
    a = _row("A-r1", "PMCA")
    b = _row("B-r1", "PMCB", **override)
    assert code in _codes(a, b)
    assert cmp.comparable(a, b).verdict is C.not_comparable


def test_both_rows_silent_on_a_condition_still_blocks_on_it():
    silent = {"ionic_strength_mM": None, "ionic_strength_source": "unreported"}
    a = _row("A-r1", "PMCA", **silent)
    b = _row("B-r1", "PMCB", **silent)
    assert "ionic_strength_unreported" in _codes(a, b)


def test_di_water_is_a_reported_medium_and_an_unreported_ionic_strength():
    water = {
        "medium_text": "deionised water",
        "medium_class": "DI_water",
        "ionic_strength_mM": None,
        "ionic_strength_source": "unreported",
    }
    a = _row("A-r1", "PMCA", **water)
    b = _row("B-r1", "PMCB", **water)
    codes = _codes(a, b)
    assert "ionic_strength_unreported" in codes
    assert "medium_unreported" not in codes


def test_a_pH_range_is_not_a_pH():
    a = _row("A-r1", "PMCA")
    b = _row("B-r1", "PMCB", pH=None, pH_text="from pH 2 to 7")
    assert "pH_not_numeric" in _codes(a, b)
    assert "pH_unreported" not in _codes(a, b)


def test_room_temperature_is_not_a_measurement_temperature():
    a = _row("A-r1", "PMCA")
    b = _row("B-r1", "PMCB", temperature_C=None, temperature_qualifier="room temperature")
    assert "temperature_not_numeric" in _codes(a, b)


def test_an_unreported_condition_never_acquires_a_default():
    """The mutation guard. Nothing may fill 25 degrees, pH 7, water or zero salt."""
    silent = _row(
        "B-r1",
        "PMCB",
        medium_text=None,
        medium_class="unreported",
        ionic_strength_mM=None,
        ionic_strength_source="unreported",
        pH=None,
        pH_text=None,
        temperature_C=None,
        temperature_qualifier=None,
        instrument=None,
    )
    nominal = _row(
        "A-r1",
        "PMCA",
        medium_text="water",
        medium_class="DI_water",
        ionic_strength_mM=0.0,
        ionic_strength_source="reported",
        pH=7.0,
        temperature_C=25.0,
    )
    assert _codes(nominal, silent) >= {
        "medium_unreported",
        "ionic_strength_unreported",
        "pH_unreported",
        "temperature_unreported",
        "instrument_unreported",
    }


# --- the value is never evidence ----------------------------------------------------------


def test_the_row_carries_no_reported_value_at_all():
    fields = {f.name for f in cmp.ZetaRow.comparison_fields()}
    assert fields.isdisjoint({"value", "value_text", "sd", "n", "unit"})


def test_value_columns_do_not_reach_the_row():
    plain = cmp.ZetaRow.from_mapping(
        {"row_id": "A-r1", "pmcid": "PMCA", **_ROW_COLUMNS, "value": -34.2}
    )
    loud = cmp.ZetaRow.from_mapping(
        {"row_id": "A-r1", "pmcid": "PMCA", **_ROW_COLUMNS, "value": 999.0, "sd": 4.0, "n": 3}
    )
    assert plain == loud


def test_similar_values_never_repair_a_blocked_pair():
    """Chemically distinct particles converge after corona formation. That is the point."""
    cooh = cmp.ZetaRow.from_mapping(
        {
            "row_id": "A-r1",
            "pmcid": "PMCA",
            **{**_ROW_COLUMNS, "functionalisation": "carboxylated"},
            "value": -30.1,
        }
    )
    nh2 = cmp.ZetaRow.from_mapping(
        {
            "row_id": "B-r1",
            "pmcid": "PMCB",
            **{**_ROW_COLUMNS, "functionalisation": "amine-modified"},
            "value": -30.2,
        }
    )
    verdict = cmp.comparable(cooh, nh2)
    assert verdict.verdict is C.not_comparable
    assert "functionalisation_mismatch" in {blocker.code for blocker in verdict.blockers}


def test_wildly_different_values_never_block_a_comparable_pair():
    a = cmp.ZetaRow.from_mapping({"row_id": "A-r1", "pmcid": "PMCA", **_ROW_COLUMNS, "value": -5.0})
    b = cmp.ZetaRow.from_mapping(
        {"row_id": "B-r1", "pmcid": "PMCB", **_ROW_COLUMNS, "value": -95.0}
    )
    assert cmp.comparable(a, b).verdict is C.comparable


# --- medium: class governs the verdict, text is checked inside the class -------------------


def test_two_different_media_of_the_same_class_block_on_the_text():
    a = _row("A-r1", "PMCA", medium_text="CV growth medium", medium_class="culture_medium")
    b = _row("B-r1", "PMCB", medium_text="HP growth medium", medium_class="culture_medium")
    codes = _codes(a, b)
    assert "medium_text_mismatch" in codes
    assert "medium_class_mismatch" not in codes


def test_a_class_difference_is_reported_as_the_class_not_the_text():
    a = _row("A-r1", "PMCA", medium_text="10 mM NaCl", medium_class="salt_solution")
    b = _row("B-r1", "PMCB", medium_text="10 mM HEPES", medium_class="buffer")
    codes = _codes(a, b)
    assert "medium_class_mismatch" in codes
    assert "medium_text_mismatch" not in codes


def test_whitespace_and_case_in_the_medium_text_do_not_block():
    a = _row("A-r1", "PMCA", medium_text="10 mM NaCl")
    b = _row("B-r1", "PMCB", medium_text="10  mM  nacl")
    assert _codes(a, b) == set()


# --- numeric agreement --------------------------------------------------------------------


def test_ionic_strength_within_tolerance_does_not_block():
    a = _row("A-r1", "PMCA", ionic_strength_mM=10.0)
    b = _row("B-r1", "PMCB", ionic_strength_mM=10.5)
    assert "ionic_strength_mismatch" not in _codes(a, b)


def test_a_salt_titration_step_blocks():
    a = _row("A-r1", "PMCA", ionic_strength_mM=10.0, medium_text="10 mM NaCl")
    b = _row("B-r1", "PMCA", ionic_strength_mM=100.0, medium_text="100 mM NaCl")
    assert "ionic_strength_mismatch" in _codes(a, b)


def test_pH_units_apart_block_because_the_sign_can_flip_across_them():
    a = _row("A-r1", "PMCA", pH=7.4)
    b = _row("B-r1", "PMCB", pH=4.0)
    assert "pH_mismatch" in _codes(a, b)


def test_a_rounded_pH_does_not_block():
    assert "pH_mismatch" not in _codes(_row("A-r1", pH=7.4), _row("B-r1", "PMCB", pH=7.35))


def test_temperature_apart_by_more_than_the_tolerance_blocks():
    a = _row("A-r1", "PMCA", temperature_C=25.0)
    b = _row("B-r1", "PMCB", temperature_C=37.0)
    assert "temperature_mismatch" in _codes(a, b)


# --- the mobility-to-zeta conversion regime -----------------------------------------------


def test_henry_function_spans_the_huckel_to_smoluchowski_factor_of_one_and_a_half():
    assert cmp.henry_f(1e-4) == pytest.approx(1.0, abs=1e-3)
    assert cmp.henry_f(1e6) == pytest.approx(1.5, abs=1e-3)
    assert 1.0 < cmp.henry_f(3.0) < 1.5


def test_debye_length_matches_the_textbook_one_to_one_electrolyte_value():
    assert cmp.debye_length_nm(1.0) == pytest.approx(9.61, abs=0.02)
    assert cmp.debye_length_nm(100.0) == pytest.approx(0.961, abs=0.01)


def test_two_zeta_rows_in_different_conversion_regimes_block():
    small_kappa_a = _row("A-r1", "PMCA", size_measured_nm=40.0, ionic_strength_mM=0.1)
    large_kappa_a = _row("B-r1", "PMCB", size_measured_nm=40.0, ionic_strength_mM=100.0)
    assert "conversion_regime_mismatch" in _codes(small_kappa_a, large_kappa_a)


def test_the_conversion_regime_is_not_checked_for_a_measured_mobility():
    a = _row("A-r1", "PMCA", quantity="electrophoretic_mobility", ionic_strength_mM=0.1)
    b = _row("B-r1", "PMCB", quantity="electrophoretic_mobility", ionic_strength_mM=100.0)
    codes = _codes(a, b)
    assert "conversion_regime_mismatch" not in codes
    assert "ionic_strength_mismatch" in codes


def test_a_missing_measured_size_blocks_a_zeta_pair():
    a = _row("A-r1", "PMCA")
    b = _row("B-r1", "PMCB", size_measured_nm=None)
    assert "size_measured_unreported" in _codes(a, b)


def test_a_nominal_size_never_substitutes_for_a_measured_one():
    fields = {f.name for f in cmp.ZetaRow.comparison_fields()}
    assert "size_nominal_nm" not in fields


# --- the three-valued verdict -------------------------------------------------------------


def test_a_stated_difference_in_one_condition_is_conditionally_comparable():
    a = _row("A-r1", "PMCA", pH=7.4)
    b = _row("B-r1", "PMCA", pH=5.0)
    verdict = cmp.comparable(a, b)
    assert verdict.verdict is C.conditionally_comparable
    assert {blocker.code for blocker in verdict.blockers} == {"pH_mismatch"}


def test_an_unreported_condition_is_never_conditionally_comparable():
    a = _row("A-r1", "PMCA")
    b = _row("B-r1", "PMCA", pH=None, pH_text=None)
    assert cmp.comparable(a, b).verdict is C.not_comparable


def test_a_different_particle_is_never_conditionally_comparable():
    a = _row("A-r1", "PMCA", functionalisation="carboxylated")
    b = _row("B-r1", "PMCA", functionalisation="amine")
    assert cmp.comparable(a, b).verdict is C.not_comparable


# --- the corpus and the query set ---------------------------------------------------------


#: `docs/FINDINGS_comparability.md` was published in this commit, its census measured on the table
#: committed with it (1 890 rows from 491 papers). The re-read of 2026-10-03 moved today's table.
FINDINGS_COMMIT = "0858865"


@pytest.fixture(scope="module")
def findings_rows(table_at) -> list[cmp.ZetaRow]:
    return cmp.load_rows(table_at(FINDINGS_COMMIT))


def test_rows_load_from_the_published_table(findings_rows):
    assert len(findings_rows) == 1890
    assert len({row.row_id for row in findings_rows}) == 1890
    frame = pd.read_csv(config.OUT_TABLES / "d1_zeta_table.csv")
    assert [row.row_id for row in cmp.load_rows()] == frame["row_id"].tolist()
    assert frame["row_id"].is_unique


def test_every_fully_comparable_pair_has_both_rows_condition_complete():
    """Why the exhaustive census only has to look at the condition-complete rows."""
    rows = cmp.load_rows()
    complete = [row for row in rows if row.conditions.conditions_complete]
    found = cmp.comparable_census(rows)
    assert 0 < len(complete) < len(rows)
    complete_ids = {row.row_id for row in complete}
    for pair in found:
        assert {pair.a.row_id, pair.b.row_id} <= complete_ids


def test_the_corpus_holds_sixteen_fully_comparable_pairs_and_none_of_them_cross_a_paper(
    findings_rows,
):
    """The headline, on the table it was measured on. Pinned, so relaxing a rule to make it look
    better shows up as a failure. The next tier, 35 conditionally comparable pairs, with it."""
    census = cmp.comparable_census(findings_rows)
    assert len(census) == 16
    assert all(pair.a.pmcid == pair.b.pmcid for pair in census)
    assert len({pair.a.pmcid for pair in census}) == 3
    graded = Counter(spec.verdict.verdict for spec in cmp.graded_census(findings_rows))
    assert graded[C.conditionally_comparable] == 35


def test_only_six_of_the_comparable_pairs_are_pairs_of_zeta_potentials(findings_rows):
    """The other ten compare the quantity that was actually measured, not the converted one."""
    quantities = Counter(
        (pair.a.quantity.value, pair.b.quantity.value)
        for pair in cmp.comparable_census(findings_rows)
    )
    assert quantities == {
        ("zeta_potential", "zeta_potential"): 6,
        ("electrophoretic_mobility", "electrophoretic_mobility"): 10,
    }


def test_the_query_set_on_disk_is_what_the_generator_produces():
    on_disk = cmp.read_query_set()
    regenerated = cmp.build_query_set(cmp.load_rows())
    assert len(on_disk) > 100
    assert [pair.as_record() for pair in regenerated] == on_disk


def test_the_query_set_covers_every_required_stratum():
    assert set(cmp.STRATA) == {
        "same_paper",
        "cross_paper_same_material",
        "cross_paper_different_functionalisation",
        "cross_paper_different_material",
        "both_conditions_complete",
    }
    counts = cmp.stratum_counts(cmp.read_query_set())
    for stratum in cmp.STRATA:
        assert counts.get(stratum, 0) > 0, stratum


def test_the_query_set_ground_truth_is_reproducible_from_the_rows():
    by_id = {row.row_id: row for row in cmp.load_rows()}
    records = cmp.read_query_set()
    assert len(records) > 100
    for record in records:
        verdict = cmp.comparable(by_id[record["row_id_a"]], by_id[record["row_id_b"]])
        assert verdict.verdict.value == record["verdict"]
        assert ";".join(b.code for b in verdict.blockers) == record["blockers"]
        assert ";".join(sorted({b.field for b in verdict.blockers})) == record["blocker_fields"]


def test_every_blocker_field_is_in_the_vocabulary_the_answer_contract_prints():
    fields = {
        field
        for record in cmp.read_query_set()
        for field in record["blocker_fields"].split(";")
        if field
    }
    assert fields
    assert fields <= set(cmp.BLOCKER_FIELDS)


def test_generation_is_deterministic():
    rows = cmp.load_rows()
    assert [p.as_record() for p in cmp.build_query_set(rows)] == [
        p.as_record() for p in cmp.build_query_set(rows)
    ]


def test_nothing_in_here_uses_a_clock_or_an_unseeded_random():
    source = cmp.__file__
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    assert "datetime.now" not in text
    assert "random.random()" not in text
    assert math.isfinite(cmp.henry_f(30.0))


_ROW_COLUMNS = {
    "quantity": "zeta_potential",
    "material": "polystyrene",
    "functionalisation": "carboxylated",
    "size_measured_nm": 100.0,
    "medium_text": "10 mM NaCl",
    "medium_class": "salt_solution",
    "ionic_strength_mM": 10.0,
    "ionic_strength_source": "reported",
    "pH": 7.4,
    "pH_text": None,
    "temperature_C": 25.0,
    "temperature_qualifier": None,
    "instrument": "Zetasizer Nano ZS (Malvern Instruments, Malvern, UK)",
}


# --- the same-particle census: not different, just unreported ----------------------------


def _census_rows() -> list[cmp.ZetaRow]:
    """Seven particles of two rows each, one pair per particle, plus three rows that describe no
    other row's particle. Every category is hit, and two traps sit beside it: an unreported
    blocker next to a stated difference, and one next to an undecidable value."""
    no_ionic = {"ionic_strength_mM": None, "ionic_strength_source": "unreported"}
    return [
        # comparable, across papers; the spellings differ but key to the same particle
        _row("A-r1", "PMCA"),
        _row("B-r1", "PMCB", material="PS", functionalisation="COOH"),
        # conditionally comparable: a stated pH step inside one paper
        _row("C-r1", "PMCC", material="polyethylene", pH=7.4),
        _row("C-r2", "PMCC", material="polyethylene", pH=5.0),
        # lost only to absence, across papers, and one number away: ionic strength alone
        _row("D-r1", "PMCD", material="polypropylene"),
        _row("E-r1", "PMCE", material="polypropylene", **no_ionic),
        # lost only to absence, inside one paper, three fields missing
        _row("F-r1", "PMCF", material="PET", pH=None, **no_ionic),
        _row("F-r2", "PMCF", material="PET", temperature_C=None),
        # a stated difference, though one blocker is unreported
        _row("G-r1", "PMCG", material="PVC", instrument=None),
        _row("H-r1", "PMCH", material="PVC", pH=4.0),
        # undecidable: a pH range beside an unreported temperature
        _row("I-r1", "PMCI", material="PMMA", pH=None, pH_text="from pH 2 to 7"),
        _row("I-r2", "PMCI", material="PMMA", temperature_C=None),
        # the surface unstated on both rows: grouped, and the silence is one of the absences
        _row("J-r1", "PMCJ", functionalisation=None),
        _row("K-r1", "PMCK", functionalisation=None),
        # never half of a same-particle pair: no material, another surface, another quantity
        _row("L-r1", "PMCL", material=None),
        _row("M-r1", "PMCM", functionalisation="amine"),
        _row("N-r1", "PMCN", quantity="electrophoretic_mobility"),
    ]


def test_every_same_particle_pair_lands_in_exactly_one_category():
    census = cmp.same_particle_census(_census_rows())
    assert dict(census.categories) == {
        "comparable": 1,
        "conditionally_comparable": 1,
        "lost_to_absence": 3,
        "stated_difference": 1,
        "undecidable": 1,
    }
    assert [name for name, _ in census.categories] == list(cmp.SAME_PARTICLE_CATEGORIES)
    assert census.pairs == 7


def test_an_unreported_blocker_beside_a_stated_difference_is_a_stated_difference():
    """The all/any guard. One unreported field does not make a pair "lost to absence" when the
    two rows also state a condition that differs: that pair would stay blocked if both papers
    reported everything."""
    rows = {row.row_id: row for row in _census_rows()}
    verdict = cmp.comparable(rows["G-r1"], rows["H-r1"])
    assert {blocker.kind for blocker in verdict.blockers} == {
        cmp.BlockerKind.unreported,
        cmp.BlockerKind.mismatch,
    }
    assert cmp.same_particle_category(verdict) == "stated_difference"


def test_an_unreported_blocker_beside_an_undecidable_one_is_not_absence():
    rows = {row.row_id: row for row in _census_rows()}
    verdict = cmp.comparable(rows["I-r1"], rows["I-r2"])
    assert cmp.same_particle_category(verdict) == "undecidable"


def test_only_unreported_blockers_are_absence():
    rows = {row.row_id: row for row in _census_rows()}
    verdict = cmp.comparable(rows["F-r1"], rows["F-r2"])
    assert {blocker.kind for blocker in verdict.blockers} == {cmp.BlockerKind.unreported}
    assert cmp.same_particle_category(verdict) == "lost_to_absence"


def test_an_unstated_surface_on_both_rows_is_absence_never_sameness():
    rows = {row.row_id: row for row in _census_rows()}
    a, b = rows["J-r1"], rows["K-r1"]
    assert cmp.same_particle_key(a) == cmp.same_particle_key(b)
    assert cmp.same_particle_key(a)[2] is None
    assert cmp.same_particle_category(cmp.comparable(a, b)) == "lost_to_absence"
    census = cmp.same_particle_census([a, b])
    assert dict(census.absent_fields) == {"functionalisation": 1}
    assert census.count("comparable") == 0


def test_rows_without_a_material_or_of_another_particle_are_never_paired():
    rows = _census_rows()
    strays = {"L-r1", "M-r1", "N-r1"}
    assert cmp.same_particle_key(next(r for r in rows if r.row_id == "L-r1")) is None
    without = cmp.same_particle_census([r for r in rows if r.row_id not in strays])
    assert cmp.same_particle_census(rows) == without


def test_missing_fields_are_counted_per_pair_and_ranked():
    census = cmp.same_particle_census(_census_rows())
    assert census.absent_fields == (
        ("ionic_strength", 2),
        ("functionalisation", 1),
        ("pH", 1),
        ("temperature", 1),
    )


def test_a_field_missing_alone_is_one_reported_number_from_decidable():
    census = cmp.same_particle_census(_census_rows())
    assert census.only_absent_field == (("functionalisation", 1), ("ionic_strength", 1))


def test_absence_is_split_across_and_within_papers():
    census = cmp.same_particle_census(_census_rows())
    assert (census.absence_cross_paper, census.absence_same_paper) == (2, 1)
    assert census.absence_cross_paper + census.absence_same_paper == census.count("lost_to_absence")


def test_the_per_particle_tallies_add_up_to_the_census():
    census = cmp.same_particle_census(_census_rows())
    assert len(census.particles) == 7
    for i, name in enumerate(cmp.SAME_PARTICLE_CATEGORIES):
        assert sum(p.counts[i] for p in census.particles) == census.count(name), name
    assert all(sum(p.counts) == p.pairs == p.rows * (p.rows - 1) // 2 for p in census.particles)
    assert sum(p.absence_cross_paper for p in census.particles) == census.absence_cross_paper


def test_the_census_does_not_depend_on_row_order():
    rows = _census_rows()
    assert cmp.same_particle_census(rows) == cmp.same_particle_census(rows[::-1])
    keys = [(p.quantity, p.material, p.functionalisation or "") for p in
            cmp.same_particle_census(rows).particles]  # fmt: skip
    assert keys == sorted(keys)


@pytest.fixture(scope="module")
def published_census():
    rows = cmp.load_rows()
    return rows, cmp.same_particle_census(rows)


def test_the_published_census_pairs_are_every_pair_within_a_particle(published_census):
    rows, census = published_census
    sizes = Counter(cmp.same_particle_key(row) for row in rows)
    sizes.pop(None, None)
    assert census.pairs == sum(n * (n - 1) // 2 for n in sizes.values())
    assert sum(n for _, n in census.categories) == census.pairs


def test_every_comparable_pair_in_the_corpus_is_a_same_particle_pair(published_census):
    """Comparable and conditionally comparable both forbid an identity blocker, so the graded
    census and the same-particle census must agree on those two counts."""
    rows, census = published_census
    graded = Counter(spec.verdict.verdict.value for spec in cmp.graded_census(rows))
    assert census.count("comparable") == graded["comparable"]
    assert census.count("conditionally_comparable") == graded["conditionally_comparable"]
