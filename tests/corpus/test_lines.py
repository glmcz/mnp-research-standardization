"""S1 — the line-addressed document.

Two properties carry the whole design and both are tested here by mutation, not by
inspection: the numbering must lose no text (or the reader is shown a different paper
from the one the guard searches), and a `line_id` must not move when a line number does
(or every stored citation dies the next time the parser is fixed).
"""

import collections
import csv
import itertools
import re
import subprocess
import sys

import pytest

from mnp import config
from mnp.corpus import jats, lines

MINIMAL = """<?xml version="1.0"?>
<article><front><article-meta>
<article-id pub-id-type="pmcid">PMC1</article-id>
<abstract><p>Zeta fell from -16.7 to -9.0 mV.</p></abstract>
</article-meta></front>
<body>{body}</body></article>"""

NUMBERED = re.compile(r"^\d+\t")


def _article(body: str) -> jats.Article:
    return jats.parse(MINIMAL.format(body=body).encode())


def _unnumber(rendered: str) -> str:
    """render() with the line numbers taken back off — must be extraction_text() again."""
    return "\n".join(NUMBERED.sub("", line, count=1) for line in rendered.split("\n"))


@pytest.fixture
def fixture_xml(fixtures_dir):
    return (fixtures_dir / "PMC5090179.xml").read_bytes()


@pytest.fixture
def doc(fixture_xml):
    return lines.build_lines(jats.parse(fixture_xml))


# -- determinism --------------------------------------------------------------


def test_the_same_xml_builds_an_identical_document_twice(fixture_xml):
    a = lines.build_lines(jats.parse(fixture_xml))
    b = lines.build_lines(jats.parse(fixture_xml))
    assert lines.render(a).encode() == lines.render(b).encode()
    assert [x.line_id for x in a.lines] == [x.line_id for x in b.lines]
    assert [x.section_path for x in a.lines] == [x.section_path for x in b.lines]


def test_line_ids_are_the_same_in_a_fresh_process(fixtures_dir):
    """A line_id is stored in a database, so it may not depend on PYTHONHASHSEED."""
    code = (
        "import sys;from mnp.corpus import jats, lines;"
        "d=lines.build_lines(jats.parse(open(sys.argv[1],'rb').read()));"
        "print(','.join(x.line_id for x in d.lines))"
    )
    path = str(fixtures_dir / "PMC5090179.xml")
    out = []
    for seed in ("0", "1"):
        r = subprocess.run(
            [sys.executable, "-c", code, path],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": seed},
            check=True,
        )
        out.append(r.stdout.strip())
    assert out[0] == out[1]
    assert out[0]


# -- stability of the id under renumbering ------------------------------------


def test_a_line_id_ignores_the_global_line_number():
    """The id is (section, ordinal, text). Nothing else may enter it."""
    assert lines.line_id("methods", 3, "Zeta was -30 mV.") == lines.line_id(
        "methods", 3, "Zeta was -30 mV."
    )
    assert lines.line_id("methods", 3, "Zeta was -30 mV.") != lines.line_id(
        "methods", 4, "Zeta was -30 mV."
    )
    assert lines.line_id("methods", 3, "Zeta was -30 mV.") != lines.line_id(
        "table:T1", 3, "Zeta was -30 mV."
    )
    assert len(lines.line_id("methods", 3, "x")) == 16


def test_inserting_a_paragraph_early_does_not_move_ids_in_other_sections(fixture_xml):
    grown = fixture_xml.replace(
        b"<title>Particles</title>",
        b"<title>Particles</title><p>An inserted sentence that was not there before.</p>",
        1,
    )
    assert grown != fixture_xml
    before = lines.build_lines(jats.parse(fixture_xml))
    after = lines.build_lines(jats.parse(grown))
    assert len(after.lines) == len(before.lines) + 1

    def elsewhere(d):
        return {
            x.line_id: x.n for x in d.lines if not x.section_path.startswith(("methods", "extra:"))
        }

    moved = elsewhere(before)
    kept = elsewhere(after)
    assert set(moved) == set(kept), "an id outside the edited section changed"
    assert moved, "nothing outside the edited section — the test proves nothing"
    assert any(moved[k] != kept[k] for k in moved), "no line number moved; insertion was a no-op"


def test_two_tables_sharing_an_id_do_not_share_line_ids():
    a = _article(
        "<sec><title>Methods</title><p>M.</p>"
        '<table-wrap id="T1"><caption><p>Same caption.</p></caption>'
        "<table><tr><td>a</td></tr></table></table-wrap>"
        '<table-wrap id="T1"><caption><p>Same caption.</p></caption>'
        "<table><tr><td>a</td></tr></table></table-wrap></sec>"
    )
    d = lines.build_lines(a)
    ids = [x.line_id for x in d.lines]
    assert len(ids) == len(set(ids)), "identical rows in two tables collapsed to one id"


# -- coverage -----------------------------------------------------------------


def test_numbering_loses_no_text_from_the_fixture(fixture_xml):
    a = jats.parse(fixture_xml)
    assert _unnumber(lines.render(lines.build_lines(a))) == jats.extraction_text(a)


def test_every_non_empty_extraction_line_is_a_line_of_the_document(fixture_xml):
    a = jats.parse(fixture_xml)
    d = lines.build_lines(a)
    texts = {x.text for x in d.lines}
    body = [
        line
        for line in jats.extraction_text(a).splitlines()
        if line.strip() and not line.startswith("== ")
    ]
    assert body
    assert [line for line in body if line not in texts] == []


def test_numbering_loses_no_text_across_the_vendored_corpus():
    if not config.EPMC_XML_DIR.is_dir():
        pytest.skip("no corpus restored here")
    paths = sorted(config.EPMC_XML_DIR.glob("*.xml"))[::25]
    assert len(paths) > 10
    for p in paths:
        a = jats.parse(p.read_bytes())
        assert _unnumber(lines.render(lines.build_lines(a))) == jats.extraction_text(a), p.name


def test_section_paths_name_the_piece_each_line_came_from():
    a = _article(
        "<sec><title>Methods</title><p>Measured on a Zetasizer.</p></sec>"
        "<sec><title>Zeta potential characterisation</title><p>Zeta was -30 mV.</p></sec>"
        "<sec><title>Results</title><p>Electrophoretic mobility was low here.</p></sec>"
        '<fig id="F1"><label>Figure 1</label><caption><p>Zeta of PS.</p></caption></fig>'
        '<table-wrap id="T1"><caption><p>Cap.</p></caption>'
        "<table><tr><td>a</td></tr></table></table-wrap>"
    )
    d = lines.build_lines(a)
    paths = [s.path for s in d.sections]
    assert paths == [
        "methods",
        "extra:Zeta potential characterisation",
        "fig",
        "abstract",
        "table:T1",
        "context:1",
    ]
    assert [s.header for s in d.sections] == [
        "== Methods",
        "== Zeta potential characterisation",
        "== Figure captions",
        "== Abstract",
        "== Table T1",
        "== Context 1",
    ]
    assert _unnumber(lines.render(d)) == jats.extraction_text(a)


def test_lines_are_numbered_from_one_and_carry_their_ordinal_in_the_section(doc):
    assert [x.n for x in doc.lines] == list(range(1, len(doc.lines) + 1))
    for s in doc.sections:
        assert [x.ordinal for x in doc.lines[s.start : s.stop]] == list(range(s.stop - s.start))
        assert {x.section_path for x in doc.lines[s.start : s.stop]} <= {s.path}


# -- resolve ------------------------------------------------------------------


def test_every_line_number_resolves_and_nothing_outside_the_range_does(doc):
    assert doc.lines
    for n in range(1, len(doc.lines) + 1):
        line = lines.resolve(doc, n)
        assert line is not None and line.n == n
    assert lines.resolve(doc, 0) is None
    assert lines.resolve(doc, -1) is None
    assert lines.resolve(doc, len(doc.lines) + 1) is None


def test_a_stored_line_id_resolves_back_to_its_line(doc):
    for line in doc.lines:
        assert lines.resolve_id(doc, line.line_id) is line
    assert lines.resolve_id(doc, "0" * 16) is None


# -- locate -------------------------------------------------------------------

METHODS_QUOTE = (
    "The zeta potential of the PS beads in 10 mM sodium chloride and perfusion medium (PM) "
    "at pH between 6.8 and 7.2 was determined with a Zetasizer NanoZS"
)
TABLE_QUOTE = "Zeta potential in 10 mM NaCl (mV) b\t-50 ± 9.7"


def test_a_verbatim_quote_locates_to_its_line(doc):
    found = lines.locate(doc, METHODS_QUOTE)
    assert len(found) == 1
    line = lines.resolve(doc, found[0])
    assert line is not None
    assert METHODS_QUOTE in line.text
    assert line.section_path == "methods"


def test_a_multi_passage_quote_locates_one_line_per_part(doc):
    quote = f"{METHODS_QUOTE} || {TABLE_QUOTE}"
    found = lines.locate(doc, quote)
    assert len(found) == 2
    first, second = (lines.resolve(doc, n) for n in found)
    assert first is not None and second is not None
    assert METHODS_QUOTE in first.text
    assert TABLE_QUOTE in second.text
    assert first.section_path == "methods"
    assert second.section_path.startswith("table:")
    assert lines.locate_parts(doc, quote) == [[found[0]], [found[1]]]


def test_a_quote_that_is_not_in_the_document_locates_nowhere(doc):
    assert lines.locate(doc, "The zeta potential was measured on a moon of Jupiter.") == []
    assert lines.locate_parts(doc, "nothing here || also nothing") == [[], []]
    assert lines.locate(doc, "") == []


def test_fold_is_the_normalisation_the_evidence_guard_already_applies():
    """`locate` must accept exactly what `verify_row` accepted, or the retrofit loses rows.

    The two live in different layers and cannot share the function without `corpus`
    importing `extract`, so the equality is pinned here instead.
    """
    from mnp.extract import zeta

    samples = [
        "Zeta potential in 10 mM NaCl (mV) b\t-50 ± 9.7",
        "1.60–5.56 µm at 25 °C",
        "−31.63±0.45 mV",
        "a  b\tc\nd  e ",
        "PS–COOH in 2–3%ID/g",
    ]
    for s in samples:
        assert lines.fold(s) == zeta._norm(s), s


def test_a_quote_the_guard_flattened_still_locates(doc):
    """Stored quotes were verified against text with every tab collapsed to a space.

    116 of the 1 890 stored rows quote a table row that way; an exact-substring locate
    misses every one of them, because the line itself keeps its TSV tabs.
    """
    flattened = TABLE_QUOTE.replace("\t", " ")
    assert flattened not in "\n".join(x.text for x in doc.lines)
    assert lines.locate(doc, flattened) == lines.locate(doc, TABLE_QUOTE) != []


def test_a_quote_spanning_several_lines_locates_each_of_them(doc):
    """16 stored rows quote a caption plus its rows as one string. A line-addressed
    document answers that with a line per row rather than with nothing."""
    first, second = doc.lines[0], doc.lines[1]
    assert lines.locate(doc, f"{first.text}\n{second.text}") == [first.n, second.n]


def test_every_stored_quote_of_the_busiest_papers_locates():
    """The retrofit's own claim, on real rows: a verified quote resolves to lines."""
    table = config.OUT_TABLES / "d1_zeta_table.csv"
    if not table.is_file() or not config.EPMC_XML_DIR.is_dir():
        pytest.skip("no extracted table here")
    rows = _stored_rows(table)
    busiest = [p for p, _ in collections.Counter(r["pmcid"] for r in rows).most_common(5)]
    checked = 0
    for pmcid in busiest:
        path = config.EPMC_XML_DIR / f"{pmcid}.xml"
        if not path.is_file():
            continue
        d = lines.build_lines(jats.parse(path.read_bytes()))
        for r in (r for r in rows if r["pmcid"] == pmcid):
            found = lines.locate_parts(d, r["evidence_quote"])
            assert found and all(found), (pmcid, r["row_id"], r["evidence_quote"][:80])
            checked += 1
    assert checked > 100


@pytest.mark.slow
def test_every_stored_quote_in_the_corpus_locates():
    table = config.OUT_TABLES / "d1_zeta_table.csv"
    if not table.is_file() or not config.EPMC_XML_DIR.is_dir():
        pytest.skip("no extracted table here")
    rows = _stored_rows(table)
    assert len(rows) > 1800
    missed = []
    for pmcid, group in itertools.groupby(sorted(rows, key=lambda r: r["pmcid"]), _pmcid):
        path = config.EPMC_XML_DIR / f"{pmcid}.xml"
        if not path.is_file():
            continue
        d = lines.build_lines(jats.parse(path.read_bytes()))
        for r in group:
            found = lines.locate_parts(d, r["evidence_quote"])
            if not found or not all(found):
                missed.append((pmcid, r["row_id"]))
    assert missed == []


def _pmcid(row):
    return row["pmcid"]


def _stored_rows(table):
    with table.open(newline="") as fh:
        return [r for r in csv.DictReader(fh) if (r["evidence_quote"] or "").strip()]
