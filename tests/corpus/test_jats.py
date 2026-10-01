import pytest

from mnp.corpus import jats

MINIMAL = """<?xml version="1.0"?>
<article><front><article-meta>
<article-id pub-id-type="pmcid">PMC1</article-id>
<article-id pub-id-type="doi">10.1/x</article-id>
<title-group><article-title>T</article-title></title-group>
<pub-date pub-type="epub"><year>2021</year></pub-date>
</article-meta></front>
<body>{body}</body></article>"""


def _article(body: str) -> jats.Article:
    return jats.parse(MINIMAL.format(body=body).encode())


def test_methods_selected_by_sec_type():
    a = _article(
        "<sec><title>Introduction</title><p>Intro text.</p></sec>"
        '<sec sec-type="materials|methods"><title>Experimental</title>'
        "<p>Zeta was measured in 10 mM NaCl.</p></sec>"
        "<sec><title>Results</title><p>Result text.</p></sec>"
    )
    assert a.methods_source == "sec-type"
    assert "10 mM NaCl" in a.methods_text
    assert "Intro text" not in a.methods_text
    assert "Result text" not in a.methods_text


@pytest.mark.parametrize(
    "title",
    [
        "Materials and methods",
        "Materials &amp; Methods",
        "Methods",
        "Method",
        "Experimental",
        "Experimental section",
        "MATERIALS AND METHODS",
        "2. Materials and methods",
    ],
)
def test_methods_falls_back_to_a_title_regex(title):
    a = _article(
        "<sec><title>Introduction</title><p>Intro text.</p></sec>"
        f"<sec><title>{title}</title><p>Measured with a Zetasizer.</p></sec>"
    )
    assert a.methods_source == "title"
    assert "Zetasizer" in a.methods_text
    assert "Intro" not in a.methods_text


def test_no_methods_section_means_source_none_and_empty_methods_text():
    a = _article("<sec><title>Introduction</title><p>Intro.</p></sec>")
    assert a.methods_source == "none"
    assert a.methods_text == ""


def test_the_first_sec_is_not_mistaken_for_methods():
    """Mutation guard: selecting body/sec[1] would pick the introduction here."""
    a = _article(
        "<sec><title>Introduction</title><p>Intro says zeta too.</p></sec>"
        "<sec><title>Methods</title><p>Real methods.</p></sec>"
    )
    assert "Real methods" in a.methods_text
    assert "Intro says" not in a.methods_text


SUPPLEMENT = (
    '<sec sec-type="supplementary-materials"><title>Supplementary Materials</title>'
    "<p>Figure S1 and Table S2.</p></sec>"
)


def test_a_supplementary_materials_section_is_not_the_methods():
    """sec-type "supplementary-materials" matches "materials"; taking it stopped the title
    fallback, and the real methods never reached methods_text in 208 of 491 papers."""
    a = _article(
        "<sec><title>Introduction</title><p>Intro text.</p></sec>"
        "<sec><title>Materials and methods</title>"
        "<p>PS beads from Magsphere were dispersed in 10 mM NaCl.</p></sec>" + SUPPLEMENT
    )
    assert "10 mM NaCl" in a.methods_text
    assert "Figure S1" not in a.methods_text
    assert a.methods_source == "title"


def test_a_real_methods_sec_type_is_taken_and_the_supplement_beside_it_is_not():
    a = _article(
        '<sec sec-type="materials|methods"><title>Experimental</title>'
        "<p>Zeta was measured in 1 mM KCl.</p></sec>" + SUPPLEMENT
    )
    assert a.methods_source == "sec-type"
    assert "1 mM KCl" in a.methods_text
    assert "Figure S1" not in a.methods_text


def test_characterisation_sections_outside_methods_are_always_added():
    a = _article(
        "<sec><title>Methods</title><p>M.</p></sec>"
        "<sec><title>Results</title>"
        "<sec><title>Surface charge and zeta potential</title><p>Zeta was -30 mV.</p></sec>"
        "<sec><title>DLS characterisation</title><p>Size 100 nm.</p></sec>"
        "<sec><title>Toxicity</title><p>Cells died.</p></sec>"
        "</sec>"
    )
    titles = [s.title for s in a.extra_sections]
    assert titles == ["Surface charge and zeta potential", "DLS characterisation"]
    assert "Cells died" not in " ".join(s.text for s in a.extra_sections)


def test_tables_are_flattened_to_tsv_with_caption_and_footnotes():
    a = _article(
        "<sec><title>Methods</title><p>M.</p>"
        '<table-wrap id="T1"><label>Table 1</label><caption><p>Bead properties.</p></caption>'
        "<table><thead><tr><th>Bead</th><th>Zeta in 10 mM NaCl (mV)<sup>a</sup></th></tr></thead>"
        "<tbody><tr><td>PS-NH2</td><td>−50 ± 9</td></tr>"
        "<tr><td>PS-COOH</td><td>−45 ± 3</td></tr></tbody></table>"
        '<table-wrap-foot><fn id="a"><label>a</label><p>Measured at 25 °C.</p></fn>'
        "</table-wrap-foot>"
        "</table-wrap></sec>"
    )
    assert len(a.tables) == 1
    t = a.tables[0]
    assert t.id == "T1"
    assert t.caption == "Table 1. Bead properties."
    assert t.tsv.splitlines() == [
        "Bead\tZeta in 10 mM NaCl (mV) a",
        "PS-NH2\t-50 ± 9",
        "PS-COOH\t-45 ± 3",
    ]
    assert t.footnotes == ["a Measured at 25 °C."]
    assert "Measured at 25 °C" in t.text


def test_unicode_minus_and_whitespace_are_normalised_once_everywhere():
    a = _article("<sec><title>Methods</title><p>Zeta  was\n−42.3 ± 1.1 mV at 25 °C.</p></sec>")
    assert "Zeta was -42.3 ± 1.1 mV at 25 °C." in a.methods_text
    assert "Zeta was -42.3 ± 1.1 mV at 25 °C." in a.full_text


def test_keyword_windows_capture_paragraph_context_around_hits():
    paras = "".join(f"<p>Para {i} filler.</p>" for i in range(10))
    paras = paras.replace("<p>Para 5 filler.</p>", "<p>The Zetasizer gave ζ = -20 mV.</p>")
    a = _article(f"<sec><title>Discussion</title>{paras}</sec>")
    assert a.methods_source == "none"
    assert len(a.keyword_windows) == 1
    w = a.keyword_windows[0]
    assert "Para 3" in w and "Para 7" in w
    assert "Para 2" not in w and "Para 8" not in w


def test_adjacent_keyword_windows_are_merged():
    paras = "".join(f"<p>Para {i} filler.</p>" for i in range(10))
    paras = paras.replace("<p>Para 4 filler.</p>", "<p>zeta here.</p>")
    paras = paras.replace("<p>Para 6 filler.</p>", "<p>mobility here.</p>")
    a = _article(f"<sec><title>Discussion</title>{paras}</sec>")
    assert len(a.keyword_windows) == 1


def test_extraction_text_prefers_keyword_windows_when_capped():
    long_methods = " ".join(f"word{i}" for i in range(4000))
    a = _article(
        f"<sec><title>Methods</title><p>{long_methods}</p></sec>"
        "<sec><title>Results</title><p>Zeta potential was -33 mV in PBS.</p></sec>"
    )
    text = jats.extraction_text(a, max_tokens=300)
    assert "-33 mV in PBS" in text
    assert jats.approx_tokens(text) <= 300
    assert "== Methods" in text


def test_extraction_text_uncapped_contains_methods_tables_and_extra_sections():
    a = _article(
        "<sec><title>Methods</title><p>M text.</p>"
        '<table-wrap id="T1"><caption><p>Cap.</p></caption><table><tr><td>cell</td></tr></table>'
        "</table-wrap></sec>"
        "<sec><title>Results</title><sec><title>Zeta potential</title><p>Z text.</p></sec></sec>"
    )
    text = jats.extraction_text(a)
    expected = (
        "M text.",
        "Cap.",
        "cell",
        "Z text.",
        "== Methods",
        "== Table T1",
        "== Zeta potential",
    )
    for piece in expected:
        assert piece in text
    assert text.count("M text.") == 1
    assert text.count("cell") == 1


def test_every_extraction_text_line_is_a_substring_of_full_text():
    """The evidence guard depends on this: whatever the model reads, it can quote."""
    a = _article(
        "<sec><title>Methods</title><p>Zeta  −42 mV.</p>"
        '<table-wrap id="T1"><caption><p>Cap.</p></caption><table><tr><td>a</td><td>b</td></tr>'
        "</table></table-wrap></sec>"
    )
    text = jats.extraction_text(a)
    for line in text.splitlines():
        if line.startswith("==") or not line.strip():
            continue
        assert line in a.full_text, line


def test_real_fixture_pmc5090179(fixtures_dir):
    a = jats.parse((fixtures_dir / "PMC5090179.xml").read_bytes())
    assert a.pmcid == "PMC5090179"
    assert a.doi == "10.1088/1468-6996/16/4/044602"
    assert a.year == 2015
    assert a.methods_source == "title"
    assert (
        "was determined with a Zetasizer NanoZS (Malvern Instruments, Worcestershire, UK)"
        in a.methods_text
    )
    assert "10 mM sodium chloride and perfusion medium (PM) at pH between 6.8 and 7.2" in (
        a.methods_text
    )
    # "Particle characterization" is a Methods subsection: already in methods_text, not repeated
    assert [s.title for s in a.extra_sections] == ["Surface modification and charge"]
    t1 = next(t for t in a.tables if t.id == "TB1")
    assert "Zeta potential in 10 mM NaCl (mV)" in t1.tsv
    assert "-50 ± 9" in t1.tsv
    assert a.license and "Creative Commons Attribution 3.0" in a.license


def test_nested_inline_elements_keep_document_order():
    """A tail must follow the element's children, not its text."""
    a = _article(
        "<sec><title>Results</title><p>Values were +25.4 mV for <bold>BC-1</bold> and "
        '<bold>BC-2</bold> (<xref rid="f2">Figure <xref rid="f2">2</xref>\n</xref>b), '
        "respectively.</p></sec>"
    )
    assert "Values were +25.4 mV for BC-1 and BC-2 (Figure 2 b), respectively." in a.full_text


def test_minus_sign_followed_by_a_thin_space_keeps_its_sign():
    a = _article("<sec><title>Methods</title><p>zeta potential of − 43.3 ± 2 mV.</p></sec>")
    assert "zeta potential of -43.3 ± 2 mV." in a.full_text
    assert jats.normalise_minus("− 43.3") == "-43.3"
    assert jats.normalise_minus("20 − 30") == "20 - 30"  # a spaced range keeps its spaces


def test_keyword_windows_do_not_repeat_paragraphs_already_in_a_section():
    paras = "".join(f"<p>Para {i} filler.</p>" for i in range(6))
    a = _article(
        "<sec><title>Methods</title><p>M.</p></sec>"
        "<sec><title>Characterization</title><p>zeta was -67.4 mV.</p></sec>"
        f"<sec><title>Discussion</title>{paras}</sec>"
    )
    text = jats.extraction_text(a)
    assert text.count("zeta was -67.4 mV.") == 1


FLOATS = """<?xml version="1.0"?>
<article><front><article-meta>
<article-id pub-id-type="pmcid">PMC1</article-id></article-meta></front>
<body><sec><title>Methods</title><p>Zeta was measured.</p></sec></body>
<floats-group>
<table-wrap position="float" id="t1"><label>Table 1</label>
<caption><p>Zeta potential of the effluents.</p></caption>
<table><tbody><tr><td>Before</td><td>-20.1</td></tr></tbody></table></table-wrap>
<fig id="f1"><label>Figure 1</label>
<caption><p>Zeta potential of PS was -33.2 mV at pH 7.</p></caption>
<graphic xlink:href="img.jpg" xmlns:xlink="http://www.w3.org/1999/xlink"/></fig>
</floats-group></article>"""


def test_tables_parked_in_floats_group_are_still_parsed():
    """9% of the corpus puts every table outside <body>; missing them loses real data."""
    a = jats.parse(FLOATS.encode())
    assert [t.id for t in a.tables] == ["t1"]
    assert "Before\t-20.1" in a.tables[0].tsv
    assert "Zeta potential of the effluents" in a.tables[0].caption
    assert "Before\t-20.1" in jats.extraction_text(a)


def test_figure_captions_are_captured_and_searchable():
    a = jats.parse(FLOATS.encode())
    assert a.figure_captions == ["Figure 1. Zeta potential of PS was -33.2 mV at pH 7."]
    assert "Zeta potential of PS was -33.2 mV at pH 7." in a.full_text
    text = jats.extraction_text(a)
    assert "== Figure captions" in text
    assert "-33.2 mV" in text
    assert "img.jpg" not in text


def test_a_table_inside_the_body_is_not_counted_twice():
    a = _article(
        "<sec><title>Methods</title><p>M.</p>"
        '<table-wrap id="T1"><caption><p>Cap.</p></caption>'
        "<table><tr><td>a</td></tr></table></table-wrap></sec>"
    )
    assert [t.id for t in a.tables] == ["T1"]
    assert jats.extraction_text(a).count("Cap.") == 1


def test_colspan_headers_are_expanded_so_columns_line_up():
    a = _article(
        "<sec><title>Methods</title>"
        '<table-wrap id="T9"><caption><p>Cap.</p></caption><table>'
        "<thead>"
        '<tr><th rowspan="2">Sample</th><th colspan="2">Zeta potential (mV)</th>'
        '<th rowspan="2">Size (nm)</th></tr>'
        "<tr><th>Before</th><th>After</th></tr>"
        "</thead><tbody>"
        "<tr><td>PS</td><td>-20.1</td><td>-11.4</td><td>112</td></tr>"
        "</tbody></table></table-wrap></sec>"
    )
    assert a.tables[0].tsv.splitlines() == [
        "Sample\tZeta potential (mV)\tZeta potential (mV)\tSize (nm)",
        "Sample\tBefore\tAfter\tSize (nm)",
        "PS\t-20.1\t-11.4\t112",
    ]


def test_a_spanning_data_cell_is_not_duplicated_into_a_second_value():
    a = _article(
        "<sec><title>Methods</title>"
        '<table-wrap id="T8"><table><tbody>'
        '<tr><td>Zeta (mV)</td><td colspan="2">-30.5</td><td>-12.0</td></tr>'
        "</tbody></table></table-wrap></sec>"
    )
    assert a.tables[0].tsv.splitlines() == ["Zeta (mV)\t-30.5\t\t-12.0"]


def test_rowspan_repeats_a_row_label_but_not_a_number():
    a = _article(
        "<sec><title>Methods</title>"
        '<table-wrap id="T7"><table><tbody>'
        '<tr><th rowspan="2">PS-COOH</th><td rowspan="2">-41.2</td><td>pH 5</td></tr>'
        "<tr><td>pH 7</td></tr>"
        "</tbody></table></table-wrap></sec>"
    )
    assert a.tables[0].tsv.splitlines() == ["PS-COOH\t-41.2\tpH 5", "PS-COOH\t\tpH 7"]


ABSTRACT_XML = """<?xml version="1.0"?>
<article><front><article-meta>
<article-id pub-id-type="pmcid">PMC1</article-id>
<abstract><p>The mean zeta potential changed from -16.7 to -9.0 mV.</p></abstract>
<abstract abstract-type="graphical"><p>Ignore me.</p></abstract>
</article-meta></front>
<body><sec><title>Methods</title><p>Measured on a Zetasizer.</p></sec></body></article>"""


def test_the_abstract_is_captured_and_reaches_the_extraction_text():
    a = jats.parse(ABSTRACT_XML.encode())
    assert a.abstract == "The mean zeta potential changed from -16.7 to -9.0 mV."
    assert a.abstract in a.full_text
    text = jats.extraction_text(a)
    assert "== Abstract" in text
    assert "-16.7 to -9.0 mV" in text


def test_a_graphical_abstract_is_not_treated_as_the_abstract():
    a = jats.parse(ABSTRACT_XML.encode())
    assert "Ignore me" not in a.abstract


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("–13.4 ± 0.8", "-13.4 ± 0.8"),  # en-dash as a leading minus
        ("\t–16.1\t–6.78", "\t-16.1\t-6.78"),  # every cell of a table row
        ("ζ = –41.2 mV", "ζ = -41.2 mV"),
        ("(–7.00)", "(-7.00)"),
        ("— 9.0 mV", "-9.0 mV"),  # em-dash with a space
        ("2–3%ID/g", "2–3%ID/g"),  # a real range: untouched
        ("20 – 30 mV", "20 – 30 mV"),
        ("0.5–1.0 mM", "0.5–1.0 mM"),
        ("PS–COOH", "PS–COOH"),  # not a number at all
    ],
)
def test_a_dash_acting_as_a_minus_sign_becomes_one_but_ranges_survive(raw, expected):
    assert jats.normalise_minus(raw) == expected


@pytest.mark.parametrize(
    "dash, name",
    [
        ("‐", "hyphen"),
        ("‑", "non-breaking hyphen"),
        ("‒", "figure dash"),
        ("–", "en dash"),
        ("—", "em dash"),
        ("―", "horizontal bar"),
        ("−", "minus sign"),
        ("－", "fullwidth hyphen-minus"),
    ],
)
def test_every_dash_character_used_as_a_sign_becomes_an_ascii_minus(dash, name):
    assert jats.normalise_minus(f"{dash}31.63±0.45 mV") == "-31.63±0.45 mV", name
    # between digits it is a range: the article text keeps the dash it printed
    assert jats.normalise_minus(f"1.60{dash}5.56 µm") == f"1.60{dash}5.56 µm".replace(
        "\u2212", "-"
    ), name
    # ...and the parser still reads it as a range rather than as one value
    from mnp.extract import coerce

    assert coerce.parse_number(f"1.60{dash}5.56")[2] == ["range"], name


def test_a_sign_is_closed_up_while_the_rest_of_the_text_stays_faithful():
    a = _article(
        "<sec><title>Methods</title><p>Zeta of PS‐MPs in PBS was ‐31.63±0.45 mV.</p></sec>"
    )
    assert "Zeta of PS‐MPs in PBS was -31.63±0.45 mV." in a.full_text
