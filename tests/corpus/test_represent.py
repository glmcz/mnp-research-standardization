"""E1 — the seven representations, and the one property that makes the comparison mean anything.

E1's whole claim is a *ratio*: raw JATS costs 7.8× what a parsed markdown does, and exact
citability costs 2 %. A ratio between two serialisations is only a fact about serialisation
when both carry the same content. The first pass of E1 did not, and reported `md_anchored` at
**0.72× — cheaper than the plain text it is a decorated copy of.** The markdown build had
silently omitted the keyword-context windows, a third of the document.

So the tests that matter here are not about anchors or braces. They are about content: every
arm must carry every sentence of the one shared block set, and a serialiser that drops a block
kind must fail loudly rather than quietly win the bake-off.
"""

import json
import re

import pytest

from mnp.corpus import jats, lines, represent

# Six block kinds in one article — methods, an extra section, a figure caption, an abstract,
# a table, and a keyword-context window pulled out of Results. The window is the block the
# published correction was about, so no fixture without one can guard against that defect.
ARTICLE_XML = """<?xml version="1.0"?>
<article><front><article-meta>
<article-id pub-id-type="pmcid">PMC9</article-id>
<abstract><p>Polystyrene beads were characterised. Zeta fell from -16.7 to -9.0 mV.</p></abstract>
</article-meta></front>
<body>
<sec sec-type="methods"><title>Materials and Methods</title>
<p>Beads were washed three times in ultrapure water at 25 degrees C. Suspensions were diluted
to 50 mg/L before each run.</p></sec>
<sec><title>Zeta potential characterisation</title>
<p>A Zetasizer Nano ZS was used, e.g. for all measurements reported here. Each value is the
mean of three runs.</p></sec>
<sec><title>Results</title>
<p>Aggregation was observed above 10 mM NaCl.</p>
<p>The zeta potential of the beads was -34.2 mV in ultrapure water. It rose to -9.0 mV at
100 mM.</p>
<p>No further change was seen after 24 h.</p></sec>
<sec><title>Discussion</title><p>These beads behave like others of their class.</p></sec>
<table-wrap id="T1"><label>Table 1</label><caption><p>Zeta potential by medium.</p></caption>
<table><thead><tr><th>Medium</th><th>Zeta (mV)</th></tr></thead>
<tbody><tr><td>water</td><td>-34.2</td></tr><tr><td>10 mM NaCl</td><td>-21.0</td></tr></tbody>
</table></table-wrap>
<fig id="F1"><label>Fig 1</label><caption><p>Zeta potential versus ionic strength.</p></caption>
</fig>
</body></article>"""


@pytest.fixture
def article():
    return jats.parse(ARTICLE_XML.encode())


@pytest.fixture
def doc(article):
    return lines.build_lines(article)


@pytest.fixture
def reps(article):
    return represent.representations(article, ARTICLE_XML)


def _every_sentence(doc: lines.LinedDoc) -> list[str]:
    return [s for x in doc.lines for s in represent.sentences(x.text)]


# -- the shared block set: every arm carries the same content ------------------


def test_the_fixture_actually_exercises_every_block_kind(doc):
    """A guard on the guard: the content tests below are vacuous without all six kinds."""
    kinds = {represent.block_kind(s.path) for s in doc.sections}
    assert kinds == {"methods", "section", "figure_caption", "abstract", "table", "context"}


def test_every_text_arm_carries_every_sentence_of_the_shared_block_set(doc, reps):
    """The E1 correction, as a test. A serialiser that drops a block kind fails here."""
    for arm in ("text_current", "md_plain", "md_anchored", "md_linenum", "md_spanids"):
        folded = lines.fold(reps[arm])
        for sentence in _every_sentence(doc):
            assert lines.fold(sentence) in folded, f"{arm} lost {sentence[:50]!r}"


def test_ir_json_carries_every_sentence_as_a_span(doc, reps):
    """JSON escapes tabs and quotes, so it is checked against the parsed spans, not the text."""
    spans = {s["text"] for s in json.loads(reps["ir_json"])["spans"]}
    for sentence in _every_sentence(doc):
        assert sentence in spans, f"ir_json lost {sentence[:50]!r}"


def test_no_arm_is_cheaper_than_plain_text(article):
    """`md_anchored` at 0.72× was the symptom. Decoration cannot make a document smaller."""
    counts = represent.token_counts(article, ARTICLE_XML)
    for arm in ("md_anchored", "md_linenum", "md_spanids", "ir_json"):
        assert counts[arm] >= counts["md_plain"], f"{arm} came out cheaper than md_plain"


def test_the_keyword_windows_are_a_third_of_the_document_and_reach_every_arm(doc, reps):
    """Named separately from the sentence sweep because this is the block that went missing."""
    windows = [x.text for x in doc.lines if x.section_path.startswith("context:")]
    assert windows, "fixture has no keyword window to lose"
    for arm in ("md_plain", "md_anchored", "md_linenum", "md_spanids"):
        folded = lines.fold(reps[arm])
        for line in windows:
            for sentence in represent.sentences(line):
                assert lines.fold(sentence) in folded, f"{arm} dropped a keyword window"
    spans = {s["text"] for s in json.loads(reps["ir_json"])["spans"]}
    assert {s for line in windows for s in represent.sentences(line)} <= spans


# -- md_plain is text_current, to the character and therefore to the token -----


def test_md_plain_is_the_text_readers_get_today(article, reps):
    """E1's own sanity check. If this fails the block set is not the parser's own."""
    assert reps["md_plain"] == jats.extraction_text(article)
    assert reps["text_current"] == reps["md_plain"]
    assert represent.count_tokens(reps["md_plain"]) == represent.count_tokens(reps["text_current"])


def test_md_linenum_is_the_committed_converter_and_not_a_second_copy_of_it(article, reps):
    assert reps["md_linenum"] == lines.render(lines.build_lines(article))


# -- the three serialisers this experiment had to write ------------------------


def test_md_anchored_anchors_every_section_header_and_touches_nothing_else(doc, reps):
    anchored = reps["md_anchored"].split("\n")
    slugs = [m.group(1) for m in (re.search(r"\{#([a-z0-9-]+)\}$", ln) for ln in anchored) if m]
    assert len(slugs) == len(doc.sections), "one anchor per section header, no more, no fewer"
    assert len(set(slugs)) == len(slugs), f"anchors are addresses and must be unique: {slugs}"
    stripped = "\n".join(re.sub(r" \{#[a-z0-9-]+\}$", "", ln) for ln in anchored)
    assert stripped == reps["md_plain"], "md_anchored is md_plain plus anchors and nothing else"


def test_md_spanids_numbers_every_sentence_once_in_order(doc, reps):
    ids = re.findall(r"\[s(\d{4})\]", reps["md_spanids"])
    assert ids == [f"{i:04d}" for i in range(1, len(_every_sentence(doc)) + 1)]
    stripped = re.sub(r"\[s\d{4}\] ", "", reps["md_spanids"])
    assert stripped == reps["md_plain"], "the ids are the only thing md_spanids adds"


def test_ir_json_types_every_span_from_a_closed_vocabulary(reps):
    payload = json.loads(reps["ir_json"])
    assert payload["doc_id"] == "PMC9"
    assert {s["type"] for s in payload["spans"]} <= set(represent.BLOCK_KINDS)
    assert [s["id"] for s in payload["spans"]] == [
        f"s{i:04d}" for i in range(1, len(payload["spans"]) + 1)
    ]
    assert {s["section"] for s in payload["spans"]} == {s["id"] for s in payload["sections"]}


def test_ir_json_keeps_the_section_titles_the_markdown_arms_print(doc, reps):
    """Content parity: `== ` is markdown syntax, the title after it is content."""
    titles = {s["title"] for s in json.loads(reps["ir_json"])["sections"]}
    assert titles == {s.header.removeprefix("== ") for s in doc.sections}


# -- sentence segmentation, where the spec was silent --------------------------


@pytest.mark.parametrize(
    "line,expected",
    [
        ("One. Two.", ["One.", "Two."]),
        ("Table 1. Zeta potential by medium.", ["Table 1. Zeta potential by medium."]),
        ("Fig 1. Zeta versus ionic strength.", ["Fig 1. Zeta versus ionic strength."]),
        (
            "Reported by Smith et al. Values were low.",
            ["Reported by Smith et al. Values were low."],
        ),
        ("Diluted to 0.5 mg/L. Then measured.", ["Diluted to 0.5 mg/L.", "Then measured."]),
        (
            "Held at 25 degrees C. Suspensions settled.",
            ["Held at 25 degrees C. Suspensions settled."],
        ),
        ("water\t-34.2\t10 mM", ["water\t-34.2\t10 mM"]),
        ("", []),
    ],
)
def test_sentence_segmentation_is_the_rule_the_module_documents(line, expected):
    assert represent.sentences(line) == expected


def test_sentences_reassemble_into_the_line_they_came_from(doc):
    for x in doc.lines:
        assert " ".join(represent.sentences(x.text)) == x.text


# -- the tokeniser -------------------------------------------------------------


def test_tokens_are_counted_with_cl100k_base_and_no_network():
    assert represent.count_tokens("") == 0
    assert represent.count_tokens("The zeta potential was -34.2 mV") == 11
    assert represent.count_tokens("<|endoftext|>") > 1, "special markup is text, not a token"


def test_xml_raw_is_the_file_as_served(article, reps):
    assert reps["xml_raw"] == ARTICLE_XML


def test_every_arm_in_the_published_table_is_measured(article):
    assert set(represent.token_counts(article, ARTICLE_XML)) == set(represent.ARMS)
    assert set(represent.ADDRESSABLE) == set(represent.ARMS)
