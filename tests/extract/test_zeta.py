import json
from types import SimpleNamespace

import pytest

from mnp import config
from mnp.corpus import jats, lines
from mnp.extract import coerce, llm, prompts, zeta
from mnp.schema import models


@pytest.fixture
def article(fixtures_dir):
    return jats.parse((fixtures_dir / "PMC5090179.xml").read_bytes())


class ScriptedLLM:
    """Stands in for llm.LLMClient: returns canned parsed JSON, records prompts."""

    def __init__(self, payloads, chain=("fake-model",)):
        self.payloads = list(payloads)
        self.chain = list(chain)
        self.calls = []

    def complete_json(self, system, user, **kw):
        self.calls.append((system, user))
        item = self.payloads.pop(0)
        if isinstance(item, Exception):
            raise item
        return item, SimpleNamespace(model=self.chain[0], cached=False, attempts=[])


def _payload(*rows):
    return {"measurements": list(rows)}


ROW_NACL = {
    "particle_name": "P1 plain",
    "material": "polystyrene",
    "quantity": "zeta potential",
    "value": "-50 ± 9.7",
    "unit": "mV",
    "conditions": {
        "medium_text": "10 mM NaCl",
        "ionic_strength": "10 mM NaCl",
        "pH": "between 6.8 and 7.2",
        "instrument": "Zetasizer NanoZS",
    },
    # The pH is stated in the body, the value in Table 1, so the quote carries both:
    # under the scope rule a condition must appear in the row's own evidence.
    "evidence_quote": (
        "Zeta potential in 10 mM NaCl (mV) b\t-50 ± 9.7\t-46.9 ± 4.0"
        " || at pH between 6.8 and 7.2 was determined with a Zetasizer NanoZS"
    ),
    "evidence_location": "Table 1; Results",
}


# -- identity with the schema ----------------------------------------------------


@pytest.fixture
def article_with_cm2():
    """An article whose mobility column is printed in cm2/Vs, as PMC11117817's is."""
    return jats.parse(
        b"""<?xml version="1.0"?>
<article><front><article-meta>
<article-id pub-id-type="pmcid">PMC1</article-id></article-meta></front>
<body><sec><title>Results</title>
<table-wrap id="T1"><caption><p>Particle properties.</p></caption>
<table><thead><tr><th>Sample</th><th>E. M. (cm 2/Vs)</th></tr></thead>
<tbody><tr><td>PS-MPs</td><td>-0.000298</td></tr></tbody></table></table-wrap>
</sec></body></article>"""
    )


def test_extraction_target_is_the_schema_surface_measurement():
    assert zeta.Measurement is models.SurfaceMeasurement


def test_prompt_embeds_the_surface_block_schema_and_the_rules():
    system = prompts.system_prompt()
    for key in (
        "medium_text",
        "ionic_strength",
        "pH",
        "temperature",
        "instrument",
        "evidence_quote",
    ):
        assert key in system
    assert "verbatim" in system.lower()
    assert "only what the text states" in system.lower()
    for cls in models.MediumClass:
        assert cls.value in system
    assert prompts.prompt_sha256() == prompts.prompt_sha256()
    assert len(prompts.prompt_sha256()) == 64


def test_user_prompt_wraps_the_extraction_text_untouched(article):
    text = jats.extraction_text(article)
    user = prompts.user_prompt(article.pmcid, text)
    assert text in user
    assert "PMC5090179" in user


# -- deterministic candidates ----------------------------------------------------


def test_find_candidates_reads_table_columns_with_a_zeta_header(article):
    text = jats.extraction_text(article)
    cands = zeta.find_candidates(text)
    zetas = [c for c in cands if c.quantity is models.Quantity.zeta_potential]
    assert len(zetas) == 14
    assert sorted(round(c.value, 1) for c in zetas)[:3] == [-55.6, -50.0, -46.9]
    nacl = [c for c in zetas if "10 mM NaCl" in c.context]
    assert len(nacl) == 7
    assert all(c.location.startswith("Table TB1") for c in zetas)


@pytest.mark.parametrize(
    "sentence, n, value, quantity",
    [
        ("The zeta potential was −42.3 ± 1.1 mV in PBS.", 1, -42.3, models.Quantity.zeta_potential),
        (
            "Mobility was -3.2 × 10-8 m2 V-1 s-1 at 1 mM.",
            1,
            -3.2,
            models.Quantity.electrophoretic_mobility,
        ),
        ("ζ = -20 mV and -35 mV for bare and COOH.", 2, -20.0, models.Quantity.zeta_potential),
        ("A potential of 150 mV was applied across the cell.", 0, None, None),
        ("Particles (100 nm) were dispersed in 10 mM NaCl.", 0, None, None),
    ],
)
def test_find_candidates_in_prose(sentence, n, value, quantity):
    cands = zeta.find_candidates(sentence)
    assert len(cands) == n
    if n:
        assert cands[0].value == pytest.approx(value)
        assert cands[0].quantity is quantity


# -- per-row verification against the article text ---------------------------------


def _row(quote, value=-50.0, **cond):
    conditions = models.MeasurementConditions(
        medium_text="10 mM NaCl",
        medium_class=models.MediumClass.salt_solution,
        ionic_strength_mM=10.0,
        ionic_strength_source=models.ValueSource.inferred_from_named_salt,
        instrument="Zetasizer NanoZS",
        **cond,
    )
    return models.SurfaceMeasurement(
        quantity=models.Quantity.zeta_potential,
        value=value,
        unit=models.Unit.mV,
        conditions=conditions,
        evidence=models.Evidence(quote=quote),
    )


def test_verify_row_marks_a_real_quote_verified(article):
    m = _row("Zeta potential in 10 mM NaCl (mV) b\t-50 ± 9.7")
    flags = zeta.verify_row(m, article.full_text)
    assert m.evidence.verified is True
    assert flags == []


def test_verify_row_tolerates_unicode_minus_and_spacing_in_the_quote(article):
    m = _row("Zeta  potential in 10 mM NaCl (mV) b   −50 ± 9.7")
    zeta.verify_row(m, article.full_text)
    assert m.evidence.verified is True


def test_verify_row_flags_a_quote_that_is_not_in_the_text(article):
    m = _row("The zeta potential was -50 mV in 10 mM NaCl at 25 °C.")
    flags = zeta.verify_row(m, article.full_text)
    assert m.evidence.verified is False
    assert "evidence_unverified" in flags


def test_verify_row_flags_a_value_absent_from_its_own_quote(article):
    m = _row("Zeta potential in 10 mM NaCl (mV) b\t-50 ± 9.7", value=-52.0)
    flags = zeta.verify_row(m, article.full_text)
    assert "value_not_in_quote" in flags


def test_verify_row_flags_conditions_absent_from_the_article(article):
    m = _row("Zeta potential in 10 mM NaCl (mV) b\t-50 ± 9.7", pH=5.5, temperature_C=41.0)
    flags = zeta.verify_row(m, article.full_text)
    assert "pH_not_in_text" in flags
    assert "temperature_not_in_text" in flags


def test_verify_row_accepts_conditions_that_are_in_the_article(article):
    m = _row("Zeta potential in 10 mM NaCl (mV) b\t-50 ± 9.7", pH_text="between 6.8 and 7.2")
    flags = zeta.verify_row(m, article.full_text)
    assert "pH_not_in_text" not in flags


def test_verify_row_without_evidence_is_unverified(article):
    m = _row("")
    m.evidence = None
    flags = zeta.verify_row(m, article.full_text)
    assert "evidence_missing" in flags


# -- the whole paper -------------------------------------------------------------


def test_extract_paper_coerces_verifies_and_reports_coverage(article):
    row_pm = dict(ROW_NACL)
    row_pm["value"] = "-13.1 ± 7.2"
    row_pm["conditions"] = {
        "medium_text": "perfusion medium (PM)",
        "instrument": "Zetasizer NanoZS",
    }
    row_pm["evidence_quote"] = "Zeta potential in PM (mV) b\t-13.1 ± 7.2"
    fake = ScriptedLLM([_payload(ROW_NACL, row_pm)])
    rec = zeta.extract_paper(article, fake)
    assert rec.pmcid == "PMC5090179"
    assert rec.model == "fake-model"
    assert rec.prompt_sha256 == prompts.prompt_sha256()
    assert rec.error is None
    assert len(rec.measurements) == 2
    first = rec.measurements[0]
    assert first.value == -50.0 and first.sd == 9.7
    assert first.conditions.ionic_strength_mM == 10.0
    assert first.evidence.verified is True
    assert rec.row_flags[0] == []
    assert rec.measurements[1].conditions.medium_class is models.MediumClass.culture_medium
    assert rec.n_candidates == 14
    assert rec.n_candidates_matched == 2
    assert rec.coverage == pytest.approx(2 / 14)
    assert len(rec.unmatched_candidates) == 12


def test_extract_paper_keeps_a_hallucinated_row_but_flags_it(article):
    bad = dict(ROW_NACL)
    bad["value"] = "-61.0"
    bad["evidence_quote"] = "The zeta potential was -61.0 mV."
    fake = ScriptedLLM([_payload(bad)])
    rec = zeta.extract_paper(article, fake)
    assert len(rec.measurements) == 1
    assert rec.measurements[0].evidence.verified is False
    assert "evidence_unverified" in rec.row_flags[0]
    assert rec.n_candidates_matched == 0


def test_extract_paper_drops_unparseable_rows_and_records_why(article):
    bad = dict(ROW_NACL)
    bad["value"] = "n.d."
    fake = ScriptedLLM([_payload(ROW_NACL, bad)])
    rec = zeta.extract_paper(article, fake)
    assert len(rec.measurements) == 1
    assert rec.dropped == [{"index": 1, "flags": ["value_unparseable"]}]


def test_extract_paper_records_llm_failure_instead_of_raising(article):
    fake = ScriptedLLM([llm.LLMError("all models failed: m1 429, m2 503")])
    rec = zeta.extract_paper(article, fake)
    assert rec.measurements == []
    assert "429" in rec.error


def test_extract_paper_tolerates_a_bare_list_or_a_single_object(article):
    fake = ScriptedLLM([{"measurements": ROW_NACL}])
    assert len(zeta.extract_paper(article, fake).measurements) == 1
    fake = ScriptedLLM([{"rows": [ROW_NACL]}])
    assert len(zeta.extract_paper(article, fake).measurements) == 1


def test_record_roundtrips_through_jsonl(article, tmp_path):
    fake = ScriptedLLM([_payload(ROW_NACL)])
    rec = zeta.extract_paper(article, fake)
    line = rec.to_json()
    back = zeta.ExtractionRecord.from_json(line)
    assert back.pmcid == rec.pmcid
    assert back.measurements[0].value == -50.0
    assert back.row_flags == rec.row_flags
    assert json.loads(line)["prompt_sha256"] == prompts.prompt_sha256()


def test_record_flattens_to_one_row_per_measurement(article):
    fake = ScriptedLLM([_payload(ROW_NACL)])
    rec = zeta.extract_paper(article, fake)
    rows = rec.to_rows()
    assert len(rows) == 1
    r = rows[0]
    assert r["pmcid"] == "PMC5090179"
    assert r["value"] == -50.0
    assert r["medium_reported"] is True
    assert r["ionic_strength_reported"] is True
    assert r["pH_reported"] is True
    assert r["temperature_reported"] is False
    assert r["instrument_reported"] is True
    assert r["conditions_complete"] is False
    assert r["evidence_verified"] is True
    assert r["flags"] == ""


def test_find_candidates_reads_column_oriented_tables_too():
    text = (
        "== Table T2\n"
        "Table 2. Surface charge.\n"
        "Sample\tSize (nm)\tZeta potential (mV)\tMobility (10-8 m2 V-1 s-1)\n"
        "PS-a\t100\t−41.2 ± 1.3\t−3.1\n"
        "PS-b\t200\tn.d.\t−2.4 ± 0.2\n"
        "PS-c\t500\t−22.0\t\n"
    )
    cands = zeta.find_candidates(text)
    zetas = sorted(c.value for c in cands if c.quantity is models.Quantity.zeta_potential)
    mobs = sorted(c.value for c in cands if c.quantity is models.Quantity.electrophoretic_mobility)
    assert zetas == [-41.2, -22.0]
    assert mobs == [-3.1, -2.4]
    assert all(c.location == "Table T2" for c in cands)
    assert {c.context for c in cands} == {"Zeta potential (mV)", "Mobility (10-8 m2 V-1 s-1)"}


def test_find_candidates_does_not_read_size_columns_as_zeta():
    text = "== Table T3\nSample\tDiameter (nm)\tPDI\nPS\t100\t0.1\n"
    assert zeta.find_candidates(text) == []


def test_extract_paper_keeps_a_range_only_row_and_verifies_its_text(article):
    row = dict(ROW_NACL)
    row["value"] = "-50 to -55"
    row["evidence_quote"] = "Zeta potential in 10 mM NaCl (mV) b\t-50 ± 9.7\t-46.9 ± 4.0"
    fake = ScriptedLLM([_payload(row)])
    rec = zeta.extract_paper(article, fake)
    assert len(rec.measurements) == 1
    m = rec.measurements[0]
    assert m.value is None and m.value_text == "-50 to -55"
    assert "value_is_range" in rec.row_flags[0]
    assert "value_text_not_in_quote" in rec.row_flags[0]  # that range is not in the quote
    assert rec.n_candidates_matched == 0  # text rows never claim a printed number
    assert rec.to_rows()[0]["value_text"] == "-50 to -55"


def test_find_candidates_counts_a_repeated_sentence_once_but_repeated_cells_twice():
    text = (
        "== Context 1\nzeta potential was -67.4 mV and -32.7 mV.\n\n"
        "== Characterization\nzeta potential was -67.4 mV and -32.7 mV.\n\n"
        "== Table T1\nZeta (mV)\t-13.1\t-13.1\n"
    )
    cands = zeta.find_candidates(text)
    assert sorted(c.value for c in cands) == [-67.4, -32.7, -13.1, -13.1]


def test_table_columns_take_their_quantity_from_the_caption_when_headers_only_carry_units():
    text = (
        "== Table t1\n"
        "Table 1. Zeta potential of the different effluents, before and after treatment.\n"
        "Industries\tBefore Treatment (mV)\tAfter Treatment (mV)\n"
        "Textile\t-20.1\t-11.4\n"
        "Paper\t-33.6\t-15.0\n"
    )
    cands = zeta.find_candidates(text)
    assert sorted(c.value for c in cands) == [-33.6, -20.1, -15.0, -11.4]
    assert all(c.quantity is models.Quantity.zeta_potential for c in cands)
    assert all(c.location == "Table t1" for c in cands)


def test_caption_quantity_does_not_leak_into_columns_with_other_units():
    text = (
        "== Table t2\n"
        "Table 2. Zeta potential and hydrodynamic size of the particles.\n"
        "Sample\tSize (nm)\tPDI\tZeta (mV)\n"
        "PS\t112\t0.05\t-41.2\n"
    )
    cands = zeta.find_candidates(text)
    assert [c.value for c in cands] == [-41.2]


def test_a_millivolt_column_is_claimed_even_when_nothing_names_the_quantity():
    """This once asserted the opposite. PMC11543686 settled it: its columns are headed
    "MPS-zate(mv)" — a typo, no "potential", no "zeta" — and 42 real values were being
    dropped. Millivolts in these papers mean zeta; the other potentials are excluded by
    name, and the material judgement belongs to the reader, not the scanner."""
    text = "== Table t3\nTable 3. Properties of the effluents.\nSite\tValue (mV)\nA\t-20.1\n"
    assert [c.value for c in zeta.find_candidates(text)] == [-20.1]


def test_a_group_header_spanning_two_columns_labels_both_of_them():
    text = (
        "== Table T9\n"
        "Table 9. Particle properties.\n"
        "Sample\tZeta potential (mV)\tZeta potential (mV)\tSize (nm)\n"
        "Sample\tBefore\tAfter\tSize (nm)\n"
        "PS\t-20.1\t-11.4\t112\n"
        "PE\t-33.6\t-15.0\t980\n"
    )
    cands = zeta.find_candidates(text)
    assert sorted(c.value for c in cands) == [-33.6, -20.1, -15.0, -11.4]
    assert 112 not in [c.value for c in cands]


def test_a_value_the_abstract_merely_restates_is_not_counted_twice():
    text = (
        "== Methods\nThe zeta potential was -41.2 mV in 10 mM NaCl.\n\n"
        "== Abstract\nWe found a zeta potential of -41.2 mV.\n"
    )
    cands = zeta.find_candidates(text)
    assert [c.value for c in cands] == [-41.2]
    assert cands[0].location == "Methods"


def test_a_value_printed_only_in_the_abstract_is_still_counted():
    text = (
        "== Methods\nZeta potential was measured on a Zetasizer.\n\n"
        "== Abstract\nThe mean zeta potential changed from -16.7 mV to -9.0 mV.\n"
    )
    cands = zeta.find_candidates(text)
    assert sorted(c.value for c in cands) == [-16.7, -9.0]
    assert all(c.location == "Abstract" for c in cands)


def test_a_gene_called_high_mobility_group_is_not_an_electrophoretic_mobility():
    """PMC10201517 generated 42 phantom candidates from a gene-expression table."""
    text = (
        "== Table T1\n"
        "Table 1. Differentially expressed genes.\n"
        "Gene\tFold change\tp value\n"
        "High mobility group box transcription factor 1 (Hbp1)\t2.31\t0.004\n"
    )
    assert zeta.find_candidates(text) == []


@pytest.mark.parametrize(
    "header",
    [
        "Electrophoretic mobility",
        "Mobility (10-8 m2 V-1 s-1)",
        "EPM (µm cm/Vs)",
        "Electrophoretic mobility (m2/Vs)",
    ],
)
def test_a_header_that_really_means_electrophoretic_mobility_still_reads(header):
    text = f"== Table T2\nTable 2. Particles.\nSample\t{header}\nPS\t-3.1\n"
    cands = zeta.find_candidates(text)
    assert [c.value for c in cands] == [-3.1]
    assert cands[0].quantity is models.Quantity.electrophoretic_mobility


def test_a_bare_mobility_header_without_a_unit_or_electrophoresis_is_ignored():
    text = "== Table T3\nTable 3. Cell motility.\nLine\tMobility\nA549\t2.4\n"
    assert zeta.find_candidates(text) == []


def test_en_dash_table_values_are_read_as_negative():
    """PMC10373654 prints every zeta with an en-dash; they were read as positive."""
    text = (
        "== Table T1\nTable 1. Nanoparticle properties.\n"
        "Zeta Potential (mV)\t–13.4 ± 0.8\t–16.1 ± 0.6\t–6.78 ± 0.18\n"
    )
    cands = zeta.find_candidates(text)
    assert sorted(c.value for c in cands) == [-16.1, -13.4, -6.78]
    assert [c.sd for c in cands] == [0.8, 0.6, 0.18]


def test_one_row_claims_the_same_value_restated_in_another_location():
    """A value printed in Table 1 and again in the Results text is one measurement."""
    text = (
        "== Table T1\nTable 1. Properties.\nZeta (mV)\t-41.2\n\n"
        "== Results\nThe zeta potential was -41.2 mV in 10 mM NaCl.\n"
    )
    cands = zeta.find_candidates(text)
    assert len(cands) == 2  # both printings are real printings
    m = models.SurfaceMeasurement(
        quantity=models.Quantity.zeta_potential, value=-41.2, unit=models.Unit.mV
    )
    matched, unmatched = zeta._match(cands, [m])
    assert matched == 2 and unmatched == []


def test_a_value_printed_twice_in_one_table_still_needs_two_rows():
    text = "== Table T1\nTable 1. Properties.\nZeta (mV)\t-13.1\t-13.1\n"
    cands = zeta.find_candidates(text)
    assert len(cands) == 2
    m = models.SurfaceMeasurement(
        quantity=models.Quantity.zeta_potential, value=-13.1, unit=models.Unit.mV
    )
    matched, unmatched = zeta._match(cands, [m])
    assert matched == 1 and len(unmatched) == 1


def test_a_hyphen_used_as_a_minus_is_read_as_negative():
    """PMC11653722 prints '‐31.63±0.45 mV' with U+2010; it read as positive."""
    text = "== Methods\nZeta potential of PS‐MPs in PBS was ‐31.63±0.45 mV.\n"
    cands = zeta.find_candidates(text)
    assert [c.value for c in cands] == [-31.63]


def test_comma_decimal_table_values_are_found():
    """PMC11532844 prints zeta with European decimals; the scanner saw nothing."""
    text = "== Table T1\nTable 1. Properties.\nZeta potential (mV)\t-31,63\t-30,63 ± 1,38\n"
    cands = zeta.find_candidates(text)
    assert sorted(c.value for c in cands) == [-31.63, -30.63]
    assert [c.sd for c in cands if c.sd] == [1.38]


def test_a_citation_list_next_to_a_unit_is_not_a_zeta_value():
    text = "== Methods\nThe zeta potential of PS has been reported [4,5] mV elsewhere.\n"
    assert zeta.find_candidates(text) == []
    text = "== Methods\nThe zeta potential was -41,2 mV [4,5].\n"
    assert [c.value for c in zeta.find_candidates(text)] == [-41.2]


def test_a_negative_standard_deviation_does_not_hide_its_value():
    """PMC12748894 prints '-52.42 ± -0.26 mV'; the value was skipped and the SD picked up."""
    text = "== Table T1\nTable 1. Zeta.\nZeta (mV)\t-52.42 ± -0.26\t-48.10 ± -0.31\n"
    cands = zeta.find_candidates(text)
    assert sorted(c.value for c in cands) == [-52.42, -48.10]
    assert [c.sd for c in cands] == [0.26, 0.31]  # an SD is a magnitude


def test_a_negative_standard_deviation_in_prose_does_not_hide_its_value():
    """The table path goes through coerce; prose goes through the scanner's own regex."""
    text = "== Results\nThe zeta potential was -52.42 ± -0.26 mV in DI water.\n"
    cands = zeta.find_candidates(text)
    assert [c.value for c in cands] == [-52.42]
    assert [c.sd for c in cands] == [0.26]


def test_a_repeated_header_cell_is_not_read_as_a_value():
    """PMC12955872: 'Zeta Potential (mV) ± Stdev (n = 3)' yielded a value of 3.0, because
    colspan expansion repeats the header into the columns it covers."""
    text = (
        "== Table T4\nTable 4. Particle properties.\n"
        "Zeta Potential (mV) ± Stdev (n = 3)\tZeta Potential (mV) ± Stdev (n = 3)\t-2.91 ± 1.21\n"
    )
    cands = zeta.find_candidates(text)
    assert [c.value for c in cands] == [-2.91]
    assert [c.sd for c in cands] == [1.21]


def test_a_data_cell_carrying_a_word_is_not_a_value():
    text = "== Table T5\nTable 5. Zeta.\nZeta (mV)\tnot determined\t-30.1\tsee Figure 2\n"
    assert [c.value for c in zeta.find_candidates(text)] == [-30.1]


def test_a_range_value_verifies_against_a_quote_that_prints_unicode_dashes():
    """PMC12955872 prints "−2–−3 mV". `coerce` stores the range with ASCII hyphens, so
    the comparison must flatten dashes on both sides or it fails on punctuation alone."""
    raw = {
        "quantity": "zeta potential",
        "value": "−2–−3",
        "unit": "mV",
        "conditions": {"medium_text": "PBS"},
        "evidence_quote": "The PEGylated particles had a zeta potential of −2–−3 mV in PBS.",
    }
    m, flags = coerce.coerce_measurement(raw)
    assert m is not None and m.value is None
    assert "value_is_range" in flags
    article = "The PEGylated particles had a zeta potential of −2–−3 mV in PBS."
    row_flags = zeta.verify_row(m, article)
    assert m.evidence.verified is True
    assert "value_text_not_in_quote" not in row_flags, row_flags


def test_a_row_claims_the_closest_printed_value_not_the_first_within_tolerance():
    """PMC13182541: PS-MPs -31.09 sat beside quartz -31.13, inside the tolerance window.
    First-fit gave the PS row the quartz number and reported the real one as missed."""
    text = "== Table T1\nTable 1. Zeta potential (mV).\nZeta (mV)\t-31.13\t-31.09\n"
    cands = zeta.find_candidates(text)
    assert sorted(c.value for c in cands) == [-31.13, -31.09]
    # One row only: the count cannot discriminate first-fit from closest-fit, but which
    # candidate the row claims can.
    row = models.SurfaceMeasurement(
        quantity=models.Quantity.zeta_potential, value=-31.09, unit=models.Unit.mV
    )
    matched, unmatched = zeta._match(cands, [row])
    assert matched == 1
    # first-fit claims -31.13 and reports the row's own number as missing
    assert [u["value"] for u in unmatched] == [-31.13]


def test_best_fit_matching_still_leaves_a_genuinely_missing_value_unmatched():
    text = "== Table T1\nTable 1. Zeta.\nZeta (mV)\t-31.13\t-52.40\n"
    cands = zeta.find_candidates(text)
    row = models.SurfaceMeasurement(
        quantity=models.Quantity.zeta_potential, value=-31.13, unit=models.Unit.mV
    )
    matched, unmatched = zeta._match(cands, [row])
    assert matched == 1
    assert [u["value"] for u in unmatched] == [-52.40]


def test_a_column_holding_two_quantities_yields_the_one_with_the_unit():
    """PMC2883929 heads a column "Size (ζ-potential)" and packs both into each cell:
    "95 nm (-13.7 mV ± 2.1)". The size was being read as a zeta potential."""
    text = (
        "== Table T1\nTable 1. Nanoparticles.\n"
        "Nanoparticle\tSize (ζ-potential)\tFluorescence\n"
        "IDA-NPs\t95 nm (-13.7 mV ± 2.1)\t485 nm\n"
        "BODIPY-NPs\t86 nm (-13.8 mV ± 0.16)\t500 nm\n"
    )
    cands = zeta.find_candidates(text)
    assert sorted(c.value for c in cands) == [-13.8, -13.7]
    assert [c.sd for c in cands] == [2.1, 0.16]


def test_a_plain_zeta_column_without_units_in_the_cells_still_reads():
    text = "== Table T2\nTable 2. Zeta.\nSample\tZeta potential (mV)\nPS\t-41.2 ± 1.1\n"
    assert [c.value for c in zeta.find_candidates(text)] == [-41.2]


def test_a_value_printed_with_a_decimal_comma_is_found_in_its_own_quote():
    """PMC6981174 prints "-35,2"; the verifier only tried the period form and
    false-flagged seven correctly-extracted rows as value_not_in_quote."""
    m = models.SurfaceMeasurement(
        quantity=models.Quantity.zeta_potential,
        value=-35.2,
        unit=models.Unit.mV,
        evidence=models.Evidence(quote="El potencial zeta fue -35,2 mV en agua."),
    )
    flags = zeta.verify_row(m, "El potencial zeta fue -35,2 mV en agua.")
    assert m.evidence.verified is True
    assert "value_not_in_quote" not in flags, flags


def test_a_value_genuinely_absent_is_still_flagged_with_comma_decimals_allowed():
    m = models.SurfaceMeasurement(
        quantity=models.Quantity.zeta_potential,
        value=-41.9,
        unit=models.Unit.mV,
        evidence=models.Evidence(quote="El potencial zeta fue -35,2 mV en agua."),
    )
    flags = zeta.verify_row(m, "El potencial zeta fue -35,2 mV en agua.")
    assert "value_not_in_quote" in flags


def test_a_claimed_unit_that_contradicts_the_printed_one_is_flagged():
    """The 25-row corruption: the paper prints cm2/Vs, the worker typed m2/Vs."""
    article_text = "== Table T1\nTable 1. Particles.\nSample\tE. M. (cm 2/Vs)\nPS\t-0.000298\n"
    m, _ = coerce.coerce_measurement(
        {
            "quantity": "electrophoretic mobility",
            "value": "-0.000298",
            "unit": "m2 V-1 s-1",
            "evidence_quote": "E. M. (cm 2/Vs) -0.000298",
        }
    )
    flags = zeta.check_units(m, {"m2 V-1 s-1"}, article_text)
    assert "unit_disagrees_with_article" in flags


def test_a_claimed_unit_matching_the_article_is_not_flagged():
    article_text = "== Table T1\nTable 1. Particles.\nSample\tE. M. (cm 2/Vs)\nPS\t-0.000298\n"
    m, _ = coerce.coerce_measurement(
        {
            "quantity": "electrophoretic mobility",
            "value": "-0.000298",
            "unit": "cm2/Vs",
            "evidence_quote": "E. M. (cm 2/Vs) -0.000298",
        }
    )
    assert zeta.check_units(m, {"cm2/Vs"}, article_text) == []


def test_units_are_not_checked_when_the_article_prints_none():
    m, _ = coerce.coerce_measurement(
        {"quantity": "zeta potential", "value": "-30", "unit": "mV", "evidence_quote": "q"}
    )
    assert zeta.check_units(m, {"mV"}, "== Methods\nNo units here.\n") == []


def test_extract_from_payload_flags_a_unit_the_article_contradicts(article_with_cm2):
    payload = {
        "measurements": [
            {
                "particle_name": "PS-MPs",
                "quantity": "electrophoretic mobility",
                "value": "-0.000298",
                "unit": "m2 V-1 s-1",
                "conditions": {"medium_text": "FMQ"},
                "evidence_quote": "PS-MPs\t-0.000298",
            }
        ]
    }
    rec = zeta.extract_from_payload(article_with_cm2, payload, "test")
    assert len(rec.measurements) == 1
    assert "unit_disagrees_with_article" in rec.row_flags[0]


def test_a_zeta_printed_without_any_unit_is_still_a_printed_value():
    """PMC10766629: "a zeta potential of -32.0" — no mV anywhere near it."""
    text = (
        "== Methods\nThe nano-MPs ranged from 50 to 100 nm with a zeta potential of -32.0 "
        "and a zeta deviation of 11.6, as determined by TEM.\n"
    )
    cands = zeta.find_candidates(text)
    assert [c.value for c in cands] == [-32.0]
    assert cands[0].quantity is models.Quantity.zeta_potential


def test_a_unitless_zeta_written_with_a_leading_plus_minus_keeps_its_magnitude():
    """PMC10819112: "the zeta potentials of PS and PVC MPs were ± 45 and ± 20"."""
    text = (
        "== Results\nAs listed in Table S3, the zeta potentials of PS and PVC MPs were "
        "± 45 and ± 20 (pH = 7 and 25 °C), respectively.\n"
    )
    cands = zeta.find_candidates(text)
    assert [abs(c.value) for c in cands] == [45.0]
    assert cands[0].sign_unknown is True


def test_a_sign_unknown_candidate_is_claimed_by_a_row_of_either_sign():
    text = "== Results\nThe zeta potential of PS was ± 45.\n"
    cands = zeta.find_candidates(text)
    row = models.SurfaceMeasurement(
        quantity=models.Quantity.zeta_potential, value=-45.0, unit=models.Unit.mV
    )
    matched, unmatched = zeta._match(cands, [row])
    assert matched == 1 and unmatched == []


def test_a_number_carrying_another_unit_is_not_a_unitless_zeta():
    for line in (
        "The zeta potential was measured at pH = 7.",
        "Particles with a zeta potential analyzer were 100 nm in size.",
        "Zeta potential was measured after 24 h of incubation.",
        "The zeta potential of the sample at 25 °C was studied.",
    ):
        assert zeta.find_candidates(f"== Methods\n{line}\n") == [], line


def test_zp_is_recognised_as_the_zeta_potential_abbreviation():
    """PMC10610651 writes "ZP (-23.6 mV)"; the scanner only knew "zeta" and "ζ"."""
    text = "== Results\nThe ZP of the PS particles was -23.6 mV and -24.5 mV after ageing.\n"
    assert sorted(c.value for c in zeta.find_candidates(text)) == [-24.5, -23.6]


def test_zp_needs_its_unit_and_does_not_fire_on_unrelated_words():
    assert zeta.find_candidates("== M\nThe ZP-1 cell line was grown for 24 h.\n") == []
    assert zeta.find_candidates("== M\nSamples were kept at ZP 4 conditions.\n") == []


@pytest.mark.parametrize(
    "line, values",
    [
        # PMC11288365: the closing bracket sits between the number and its unit
        (
            "The zeta potential of the three PS MPs/NPs was (-17.90 ± 0.42) mV, "
            "(-16.70 ± 1.41) mV and (-17.75 ± 0.92) mV.",
            [-17.90, -16.70, -17.75],
        ),
        # PMC11293132: the unit spelled out
        ("The particles exhibited a zeta potential of -30 millivolts, as in Fig. S1.", [-30.0]),
        ("A zeta potential of -12.4 millivolt was recorded.", [-12.4]),
        # PMC11312894: value bracketed, unit inside
        ("PS-NPs were negatively charged on surface (-43.4 mV) (Fig. 1C).", [-43.4]),
    ],
)
def test_values_printed_in_brackets_or_with_a_spelled_out_unit_are_found(line, values):
    cands = zeta.find_candidates(f"== Results\n{line}\n")
    assert [c.value for c in cands] == values


def test_the_deviation_inside_the_bracket_is_kept():
    cands = zeta.find_candidates("== R\nThe zeta potential was (-17.90 ± 0.42) mV.\n")
    assert cands[0].sd == 0.42


def test_charge_language_counts_as_naming_the_quantity():
    text = "== R\nPS-NPs were negatively charged on surface (-43.4 mV) (Fig. 1C).\n"
    assert [c.value for c in zeta.find_candidates(text)] == [-43.4]


@pytest.mark.parametrize(
    "line",
    [
        "An applied voltage of 150 mV was used for the separation.",
        "The membrane potential was -70 mV in resting cells.",
        "Electrodes were held at 500 mV versus Ag/AgCl.",
    ],
)
def test_other_things_measured_in_millivolts_are_not_zeta_potentials(line):
    assert zeta.find_candidates(f"== Methods\n{line}\n") == [], line


@pytest.mark.parametrize(
    "line",
    [
        # charge language AND a millivolt value that is NOT a zeta potential
        "Charged vesicles were clamped to a membrane potential of -70 mV.",
        "The charged electrode was held at 500 mV versus Ag/AgCl.",
        "Particles were charged under an applied voltage of 150 mV.",
    ],
)
def test_charge_language_does_not_drag_in_other_millivolt_quantities(line):
    assert zeta.find_candidates(f"== Methods\n{line}\n") == [], line


def test_mvolt_is_the_millivolt_unit_too():
    """PMC12250668 prints "-10 mvolt"."""
    assert [c.value for c in zeta.find_candidates("== R\nThe zeta potential was -10 mvolt.\n")] == [
        -10.0
    ]


def test_a_mobility_printed_in_micrometre_per_second_per_volt_per_cm_is_found():
    """PMC12526631 prints "(μm/s)/(V/cm)" — the practical mobility unit, numerically
    the same as 1e-8 m2/V/s."""
    from mnp.extract import coerce
    from mnp.schema.models import Unit

    unit, factor = coerce.normalise_unit("(μm/s)/(V/cm)")
    assert unit is Unit.um_cm_per_Vs
    assert factor == pytest.approx(1.0)
    unit, factor = coerce.normalise_unit("µm s-1 / V cm-1")
    assert unit is Unit.um_cm_per_Vs and factor == pytest.approx(1.0)


def test_a_column_measured_in_millivolts_is_a_zeta_column():
    """PMC11543686 heads its columns "MPS-zate(mv)" — a typo, no "potential" either —
    and hid 42 values. A column measured in millivolts, that is not some other
    potential and not a size, is the quantity whatever it calls itself."""
    text = (
        "== Table T1\nTable 1. Cotransport parameters.\n"
        "Materials\tIonic strength (mM)\tMPS-zate(mv)\tquartz sand-zate(mv)\n"
        "PS\t0\t-43.2\t-35.6\n"
    )
    assert sorted(c.value for c in zeta.find_candidates(text)) == [-43.2, -35.6]


@pytest.mark.parametrize(
    "header",
    ["Membrane potential (mV)", "Applied potential (mV)", "Redox potential (mV)"],
)
def test_another_potential_measured_in_millivolts_is_not_a_zeta_column(header):
    text = f"== Table T2\nTable 2. Electrophysiology.\nCell\t{header}\nA549\t-70.0\n"
    assert zeta.find_candidates(text) == []


# PMC3994290 verbatim: megavolts on an accelerator, in a sentence that also talks about
# charged particles — so the zeta keyword fires and only the guard stops it.
_ACCELERATOR_LINE = (
    "amline of the AIFIRA facility (Applications Interdisciplinaires des Faisceaux d’Ions "
    "en Région Aquitaine) at CENBG (Centre d’Etudes Nucléaires de Bordeaux Gradignan). The "
    "proton beam is provided by a 3.5 MV single stage electrostatic accelerator designed by"
    " the High Voltage Engineering Eur"
)


@pytest.mark.parametrize(
    "line",
    [
        _ACCELERATOR_LINE,
        "The charged particles were imaged at an accelerating voltage of 200 MV.",
    ],
)
def test_megavolts_on_an_accelerator_are_not_a_zeta_potential(line):
    assert zeta.find_candidates(f"== Methods\n{line}\n") == [], line


def test_a_paper_printing_millivolts_as_MV_is_still_read():
    """PMC11520165 prints "-15.9 ± 6.63 MV" for a zeta potential — the unit is a typo,
    but the sentence names the quantity, so it counts."""
    text = "== R\nThe zeta potential of the PS-NPs was -15.9 ± 6.63 MV in ultrapure water.\n"
    assert [c.value for c in zeta.find_candidates(text)] == [-15.9]


def test_a_distant_not_zeta_phrase_does_not_kill_real_values():
    """PMC11670363: two real zeta values in a paragraph that mentions a scanning electron
    microscope 400 characters later. The guard must apply near the number, not to the
    whole paragraph, or coverage is silently undercounted."""
    line = (
        "In this study, PET nanoplastics and microplastics were prepared by mechanically "
        "crushing white PET plastic sheets. The microplastics had a particle size of "
        "approximately 6.32 um with a zeta potential of -28.8 ± 0.2 mV, and the "
        "nanoplastics of about 210 nm with a zeta potential of -18.5 ± 0.1 mV. Morphology "
        "was examined with a scanning electron microscope operated at 5 kV."
    )
    cands = zeta.find_candidates(f"== Methods\n{line}\n")
    assert sorted(c.value for c in cands) == [-28.8, -18.5]


def test_a_not_zeta_phrase_beside_the_number_still_suppresses_it():
    for line in (
        "Particles were charged under an applied voltage of 150 mV during separation.",
        "Charged vesicles were clamped to a membrane potential of -70 mV.",
    ):
        assert zeta.find_candidates(f"== Methods\n{line}\n") == [], line


def test_the_ordinary_verb_accelerate_does_not_suppress_a_zeta_value():
    """'accelerat' matched the verb as well as 'accelerating voltage'. The verb is placed
    closer to the number than the zeta keyword here, so proximity alone will not save it —
    the pattern itself has to be narrow."""
    line = "The zeta potential mattered because sedimentation accelerates below -20.5 mV."
    assert [c.value for c in zeta.find_candidates(f"== R\n{line}\n")] == [-20.5]


def test_an_accelerating_voltage_is_still_suppressed():
    line = "The charged sample was imaged at an accelerating voltage of 200 MV."
    assert zeta.find_candidates(f"== Methods\n{line}\n") == []


def test_an_inequality_bound_is_not_a_candidate():
    text = "== R\nThe zeta potential of the PE and PS particles was <0 mV throughout.\n"
    assert zeta.find_candidates(text) == []


# -- Martin's scope rule, 2026-09-13 (tests/edge/key.yaml C5) ------------------------------

SCOPE_TEXT = (
    "Zeta potential of the PS particles was -50 mV. Our samples were all suspended in PBS "
    "buffer at pH 7.4, and therefore the albumin is expected to occupy the largest area. "
    "Figure 4 compares plasma and serum coronas. Particles were incubated at 37 °C for "
    "10 min prior to analysis."
)


def _scope_row(quote, **cond):
    return models.SurfaceMeasurement(
        quantity=models.Quantity.zeta_potential,
        value=-50.0,
        unit=models.Unit.mV,
        conditions=models.MeasurementConditions(**cond),
        evidence=models.Evidence(quote=quote),
    )


def test_a_condition_stated_elsewhere_in_the_paper_is_flagged_as_carried():
    """PMC4958399: the paper's only pH sits in a paragraph about isolated proteins; the
    disputed rows belong to the Fig. 4 plasma/serum experiment, where pH is never restated.
    The article check passes — 7.4 is in the text — so only the evidence check can catch it."""
    m = _scope_row("Zeta potential of the PS particles was -50 mV.", pH=7.4)
    flags = zeta.verify_row(m, SCOPE_TEXT)
    assert "pH_not_in_text" not in flags
    assert "pH_not_in_evidence" in flags


def test_a_condition_quoted_with_its_own_row_is_not_flagged():
    """Quoting the establishing sentence alongside the row — the ' || ' convention — is how
    a worker shows the condition belongs to this experiment."""
    m = _scope_row(
        "Zeta potential of the PS particles was -50 mV. || suspended in PBS buffer at pH 7.4",
        pH=7.4,
    )
    flags = zeta.verify_row(m, SCOPE_TEXT)
    assert "pH_not_in_evidence" not in flags
    assert m.evidence.verified is True


def test_a_temperature_quoted_as_an_incubation_is_flagged_even_when_it_is_in_the_quote():
    m = _scope_row(
        "Zeta potential of the PS particles was -50 mV. || Particles were incubated at "
        "37 °C for 10 min prior to analysis.",
        temperature_C=37.0,
    )
    flags = zeta.verify_row(m, SCOPE_TEXT)
    assert "temperature_not_in_evidence" not in flags
    assert "temperature_step_not_measurement" in flags


def test_an_ionic_strength_derived_from_a_salt_needs_that_salt_in_the_quote():
    computed = dict(
        ionic_strength_mM=139.7,
        ionic_strength_source=models.ValueSource.inferred_from_named_salt,
    )
    absent = _scope_row("Zeta potential of the PS particles was -50 mV.", **computed)
    assert "ionic_strength_not_in_evidence" in zeta.verify_row(absent, SCOPE_TEXT)
    present = _scope_row(
        "Zeta potential of the PS particles was -50 mV. || 0.137 M sodium chloride",
        **computed,
    )
    assert "ionic_strength_not_in_evidence" not in zeta.verify_row(present, SCOPE_TEXT)


def test_a_pH_range_carried_from_elsewhere_is_flagged_too():
    """pH_text takes the same scope rule as a numeric pH; checking only one left half the
    field unguarded, since a range is recorded as text."""
    m = _scope_row("Zeta potential of the PS particles was -50 mV.", pH_text="pH 7.4 buffer")
    flags = zeta.verify_row(m, SCOPE_TEXT)
    assert "pH_not_in_evidence" in flags


def test_the_other_step_test_looks_at_the_clause_carrying_the_temperature(article):
    """A quote may mention an incubation elsewhere and still state a measurement temperature.

    `OTHER_STEP_RE` was applied to the whole joined quote, so a row whose evidence included a
    sentence about exposure was flagged `temperature_step_not_measurement` even when its 25 °C
    came from a different sentence about the measurement itself. Two sweep workers hit it
    independently, and both worked around it by TRIMMING the evidence — the guard was
    punishing the more complete quote, which is exactly backwards.
    """
    quote = (
        "Particles were exposed to different ionic strengths for 24 h. || "
        "Zeta potential was measured at 25 °C using a Zetasizer NanoZS."
    )
    m = _row(quote, value=-50.0, temperature_C=25.0)
    flags = zeta.verify_row(m, quote)
    assert "temperature_step_not_measurement" not in flags, flags


def test_an_incubation_temperature_in_its_own_clause_is_still_caught(article):
    """The guard must keep catching the thing it was written for."""
    quote = "Particles were incubated at 37 °C for 24 h before zeta potential measurement."
    m = _row(quote, value=-50.0, temperature_C=37.0)
    assert "temperature_step_not_measurement" in zeta.verify_row(m, quote)


# -- citation scope: the value on the line, the conditions on the quote ---------------


def _doc(*texts: str) -> lines.LinedDoc:
    """A line-addressed document, one line per argument, all in one section."""
    rows = tuple(
        lines.Line(i + 1, t, "methods", i, lines.line_id("methods", i, t))
        for i, t in enumerate(texts)
    )
    return lines.LinedDoc(pmcid="PMC0", lines=rows, sections=())


CITED_LINE = "Zeta potential of the PS particles was -50 mV, measured in PBS buffer at pH 7.4."


def test_the_value_is_checked_against_the_cited_line_not_the_quote():
    """A trimmed quote no longer decides whether its own number is supported.

    The worker authors the quote and is judged on it, so trimming until the guard passes
    works. The line is the paper's, not the worker's, and cannot be trimmed.
    """
    m = _scope_row("Zeta potential of the PS particles was")
    assert "value_not_in_quote" in zeta.verify_row(_scope_row(m.evidence.quote), CITED_LINE)
    assert "value_not_in_quote" not in zeta.verify_row(m, CITED_LINE, _doc(CITED_LINE))


def test_a_value_text_absent_from_the_cited_line_is_still_flagged():
    m = _scope_row("Zeta potential of the PS particles was")
    m.value = None
    m.value_text = "strongly negative"
    assert "value_text_not_in_quote" in zeta.verify_row(m, CITED_LINE, _doc(CITED_LINE))


def test_a_condition_printed_in_the_cited_line_but_not_quoted_is_still_carried():
    """Martin's scope rule, 2026-09-13, is untouched by citation scope.

    The line is a paragraph and holds several experiments; the sentence is the unit within
    which a condition is established. Widening the value check does not widen this one.
    """
    m = _scope_row("Zeta potential of the PS particles was -50 mV", pH=7.4)
    flags = zeta.verify_row(m, CITED_LINE, _doc(CITED_LINE))
    assert "pH_not_in_evidence" in flags
    assert m.evidence.verified is True


def test_a_quote_the_article_holds_but_the_cited_lines_do_not_is_unverified():
    text = "A sentence nobody cited. " + CITED_LINE
    m = _scope_row("A sentence nobody cited.")
    assert zeta.verify_row(_scope_row(m.evidence.quote), text) == ["value_not_in_quote"]
    assert "evidence_unverified" in zeta.verify_row(m, text, _doc(CITED_LINE))
    assert m.evidence.verified is False


def test_the_lines_checked_are_the_ones_the_row_cites():
    doc = _doc(CITED_LINE, "A second paragraph, printing no number at all.")
    m = _scope_row("A second paragraph, printing no number at all.")
    m.evidence.line_ids = (doc.lines[1].line_id,)
    assert "value_not_in_quote" in zeta.verify_row(m, CITED_LINE, doc)


def test_a_passage_spanning_consecutive_lines_verifies():
    """16 stored rows quote a caption and the table rows beneath it as one passage.

    Those newlines are not a fabrication: `lines._match` addresses each line the passage
    covers, and the guard folded the newlines to spaces before ever accepting the quote.
    """
    doc = _doc("Table 1. Zeta potential of the particles.", "PS-COOH\t-48.3", "PS-NH2\t+31.2")
    quote = "Table 1. Zeta potential of the particles.\nPS-COOH\t-48.3"
    m = _scope_row(quote)
    m.value = -48.3
    assert lines.locate(doc, quote) == [1, 2]
    flags = zeta.verify_row(m, "\n".join(x.text for x in doc.lines), doc)
    assert m.evidence.verified is True
    assert flags == []


def test_a_passage_glued_across_non_consecutive_lines_does_not_verify():
    """`verify_adversarial.json` case 4, put through the line-addressed path.

    `lines._match` splits a passage on its newlines and answers with every line each
    fragment hits, which is right for a locator and would be wrong for a guard: here the
    fragments land on lines 1 and 3, and reading them as one sentence invents a row the
    paper never printed. A passage has to sit inside one run of consecutive lines.
    """
    case = json.loads(
        (config.ROOT / "tests" / "eval" / "fixtures" / "verify_adversarial.json").read_text()
    )[3]
    doc = _doc(*case["article_text"].split("\n"))
    m = _scope_row(case["quote"])
    m.value = case["value"]
    assert lines.locate(doc, case["quote"]) == [1, 3]
    flags = zeta.verify_row(m, case["article_text"], doc)
    assert m.evidence.verified is False
    assert case["expect_flag"] in flags
