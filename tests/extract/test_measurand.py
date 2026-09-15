"""Finding papers where the thing measured may not be the plastic.

Ratified rule S8 (2026-09-15): the measurand must be the plastic particle itself. A zeta of a
supernatant, a treated water, a protein or a cell is not a plastic measurement, however
clearly the paper attributes the shift to plastic.

That is a judgement, so this does not decide it — it produces a reviewable list. The rule was
found by a worker reading one paper; nothing in the pipeline would have surfaced it, and 443
papers of the sweep are still unread.
"""

from mnp.extract import measurand


def test_a_removal_before_the_measurement_is_flagged():
    text = (
        "After each incubation stage, PET MNPs were removed from the suspension prior to "
        "optical measurements using a 0.2 um syringe membrane filter."
    )
    hits = measurand.suspicions(text)
    assert any(h.kind == "removed_before_measurement" for h in hits)
    assert hits[0].quote


def test_a_zeta_of_another_material_exposed_to_plastic_is_flagged():
    text = "Table 1. Zeta Potential of Abeta When Exposed to MNP and Non-Exposed"
    assert any(h.kind == "other_material_exposed" for h in measurand.suspicions(text))


def test_a_supernatant_measurement_is_flagged():
    text = "The zeta potential of the supernatant was measured after centrifugation."
    assert any(h.kind == "supernatant_measured" for h in measurand.suspicions(text))


def test_an_ordinary_particle_measurement_is_not_flagged():
    text = (
        "The zeta potential of the PS beads in 10 mM NaCl was -50 mV, measured with a "
        "Zetasizer NanoZS at 25 C."
    )
    assert measurand.suspicions(text) == []


def test_a_filtration_before_a_different_analysis_is_not_flagged():
    """ "Filtered prior to HPLC analysis" says nothing about what the zeta was measured on.

    The first version of this scan matched it, and 16 of its 25 hits were this shape.
    """
    text = (
        "Samples were passed through a 0.45 um filter prior to HPLC analysis. The zeta "
        "potential of the microplastics was -22 mV."
    )
    assert measurand.suspicions(text) == []
