"""Where a measured particle came from: the lines a reader is shown, what it is asked, how its
reply is read back, and the run that asks every paper once."""

import json

import pandas as pd
import pytest

from mnp import config
from mnp.corpus import jats, lines
from mnp.eval import grid
from mnp.extract import origin


def _doc(pmcid: str, *texts: str, path: str = "methods") -> lines.LinedDoc:
    rows = tuple(
        lines.Line(i + 1, t, path, i, lines.line_id(path, i, t)) for i, t in enumerate(texts)
    )
    return lines.LinedDoc(pmcid, rows, (lines.SectionSpan(path, "== Methods", 0, len(rows)),))


DOC = _doc(
    "PMC1",
    "Polystyrene nanoplastics (100 nm) were purchased from Polysciences (Warrington, PA, USA).",
    "Polyethylene film was cryogenically milled and sieved below 50 um.",
    "The zeta potential of PS and PE was measured with a Zetasizer Nano ZS.",
    "Cells were cultured in DMEM with 10% serum.",
    "Surface water was collected from the Elbe river and filtered.",
    "Part of the PE was aged under UV light for 30 days.",
)
CITED = frozenset({DOC.lines[2].line_id})


# -- which lines the reader sees -------------------------------------------------------------------


def test_cue_lines_and_cited_lines_are_shown_and_nothing_else():
    ev = origin.select(DOC, CITED)
    assert [x.n for x in ev.shown] == [1, 2, 3, 5, 6]
    assert ev.dropped == 0


def test_every_cue_family_is_recognised():
    assert "supplier" in origin.cues("Beads were obtained from Bangs Laboratories.")
    assert "fabrication" in origin.cues("Pellets were ground in a ball mill.")
    assert "ageing" in origin.cues("The particles were weathered for 60 d.")
    assert "environmental" in origin.cues("Sediment was sampled at three sites.")
    assert origin.cues("Cells were cultured in DMEM with 10% serum.") == {}
    # a word that merely contains a cue is not one, and zeta papers' own vocabulary is not
    assert "environmental" not in origin.cues("The pair of hairs was repaired.")
    assert origin.cues("Mobility was measured in an applied electric field.") == {}
    assert origin.cues("UV-Vis spectra were recorded after baseline correction.") == {}
    assert "ageing" in origin.cues("Particles were exposed to UV-A for 7 d.")


def test_a_capped_paper_keeps_the_highest_signal_lines_and_says_so():
    filler = [f"Instrument {i} was made by Malvern Instruments Ltd (UK)." for i in range(40)]
    doc = _doc("PMC2", *filler, "PS beads were purchased from Sigma-Aldrich.", *filler)
    cited = frozenset({doc.lines[0].line_id})
    ev = origin.select(doc, cited, budget=60)
    texts = [x.text for x in ev.shown]
    assert "PS beads were purchased from Sigma-Aldrich." in texts
    assert doc.lines[0] in ev.shown, "a cited line outranks a line with only a company suffix"
    assert ev.dropped > 0
    assert ev.tokens <= 60
    assert [x.n for x in ev.shown] == sorted(x.n for x in ev.shown), "shown in reading order"
    assert f"{ev.dropped} " in origin.prompt_for("PMC2", ["PS"], evidence=ev)


def test_evidence_on_a_real_paper_shows_its_supplier_and_every_cited_line():
    path = config.EPMC_XML_DIR / "PMC10458608.xml"
    table = config.OUT_TABLES / "d1_zeta_table.csv"
    if not path.is_file() or not table.is_file():
        pytest.skip("no corpus restored here")
    ev = origin.evidence_lines("PMC10458608")
    shown = {x.line_id for x in ev.shown}
    rows = pd.read_csv(table).query("pmcid == 'PMC10458608'")
    cited = {i for ids in rows["evidence_line_ids"] for i in str(ids).split(";") if i}
    assert cited and cited <= shown
    assert any("purchased from Magsphere" in x.text for x in ev.shown)
    assert ev.tokens <= origin.BUDGET_TOKENS


def test_a_sentence_that_names_the_particles_and_their_source_wins_the_budget():
    doc = _doc(
        "PMC4",
        "MPs were added to the wells. DAPI was purchased from Sigma.",
        "PS beads were purchased from Bangs.",
    )
    ev = origin.select(doc, frozenset(), budget=20)  # room for either line, not both
    assert [x.n for x in ev.shown] == [2]


def test_a_long_line_is_cut_to_its_cue_sentences_only_when_the_paper_is_over_budget():
    assay = "Cells were seeded at 5000 per well and incubated for 24 h at 37 degrees. " * 40
    long = f"{assay}The PS beads were purchased from Bangs Laboratories. {assay}"
    doc = _doc("PMC3", long, "The zeta potential of PS was -30 mV.")
    cited = frozenset({doc.lines[1].line_id})

    roomy = origin.select(doc, cited, ["PS"], budget=5000)
    assert roomy.texts[0] == long and roomy.excerpted == 0

    tight = origin.select(doc, cited, ["PS"], budget=400)
    assert tight.texts[0] == "[…] The PS beads were purchased from Bangs Laboratories. […]"
    assert [x.n for x in tight.shown] == [1, 2] and tight.dropped == 0
    prompt = origin.prompt_for("PMC3", ["PS"], evidence=tight)
    assert "PMC3:L1\t[…] The PS beads were purchased" in prompt
    assert "1 long lines are shown as their relevant sentences only" in prompt


_XML = """<?xml version="1.0"?>
<article><front><article-meta>
<article-id pub-id-type="pmcid">PMC9</article-id>
<abstract><p>Zeta potential of PS beads was -30 mV.</p></abstract>
</article-meta></front>
<body>{body}</body></article>"""

LOST_METHODS = (
    "<sec><title>Introduction</title><p>Plastics are milled by waves at sea.</p></sec>"
    "<sec><title>Experimental Section</title><sec><title>Nanoplastics</title>"
    "<p>PS beads were purchased from Magsphere.</p></sec></sec>"
    '<sec sec-type="supplementary-materials"><title>Supplementary Materials</title>'
    "<p>Data S1.</p></sec>"
)


def _write(tmp_path, body: str) -> None:
    (tmp_path / "PMC9.xml").write_text(_XML.format(body=body))


def _canonical(tmp_path) -> lines.LinedDoc:
    return lines.build_lines(jats.parse((tmp_path / "PMC9.xml").read_bytes()))


def test_the_methods_beside_a_supplementary_section_reach_the_reader_through_the_parser(tmp_path):
    """Before 9b17a6c the parser took sec-type "supplementary-materials" for the methods and
    never tried the "Experimental Section" title (208 of 491 papers), and `load_doc` appended
    the lost paragraphs for the origin reader alone. Now the parser finds them, so the supplier
    line is a Methods line of the document every consumer reads."""
    _write(tmp_path, LOST_METHODS)
    doc = origin.load_doc("PMC9", xml_dir=tmp_path)
    supplier = next(x for x in doc.lines if x.text == "PS beads were purchased from Magsphere.")
    assert supplier.section_path == "methods"
    assert doc == _canonical(tmp_path)


FOUND = (
    "<sec><title>Introduction</title><p>Plastics are milled by waves at sea.</p></sec>"
    "<sec><title>Materials and methods</title><p>PS beads were purchased from Magsphere.</p></sec>"
)
#: The two shapes the old repair still patched after the fix: no section the parser takes for
#: the methods, and a methods-typed subsection that hides its untyped "Materials" sibling.
NO_METHODS = "<sec><title>Results</title><p>PS beads were purchased from Magsphere.</p></sec>"
TYPED_SUBSECTION = (
    "<sec><title>2. Materials and Methods</title>"
    "<sec><title>2.1. Materials</title><p>PS beads were purchased from Magsphere.</p></sec>"
    '<sec sec-type="methods"><title>2.2. Procedure</title><p>Beads were dispersed.</p></sec>'
    "</sec>"
)


@pytest.mark.parametrize(
    "body",
    [LOST_METHODS, FOUND, NO_METHODS, TYPED_SUBSECTION],
    ids=["supplement_beside_methods", "found", "no_methods", "typed_subsection"],
)
def test_the_origin_reader_reads_the_line_document_every_consumer_reads(tmp_path, body):
    """Nothing is appended for origin alone: a Methods the parser misses is missed for the
    extraction too, and is fixed in the parser or not at all."""
    _write(tmp_path, body)
    assert origin.load_doc("PMC9", xml_dir=tmp_path) == _canonical(tmp_path)


# -- the prompt ------------------------------------------------------------------------------------


def test_the_prompt_names_every_particle_and_carries_the_rules():
    ev = origin.select(DOC, CITED)
    prompt = origin.prompt_for("PMC1", ["PS", "PE (aged)"], evidence=ev)
    assert '"PS"' in prompt and '"PE (aged)"' in prompt
    assert "PMC1:L1\tPolystyrene nanoplastics" in prompt
    assert "Cells were cultured" not in prompt
    for rule in (
        "environmental ONLY if the particles were collected from a real environment",
        "not the liquid it was measured in",
        "lab_fabricated",
        "aged_in_lab is separate from origin",
        "unclear when the lines do not say",
        "Answer only from the lines",
        "Cite every claim",
    ):
        assert rule in prompt, rule
    for key in ('"origin"', '"aged_in_lab"', '"environment"', '"citations"', '"reason"'):
        assert key in prompt
    assert "dropped" not in prompt, "nothing was dropped, so the prompt must not say so"
    # the pilot's reader copied a "PMCID:Lnn" placeholder verbatim; none may be left to copy
    assert "PMCID" not in prompt
    assert '"citations": ["PMC1:L<n>", ...]' in prompt
    assert prompt == origin.prompt_for("PMC1", ["PS", "PE (aged)"], evidence=ev)


# -- reading the reply back ------------------------------------------------------------------------

CANNED = """Here is the classification.
{"particles": [
  {"particle_name": "PS", "origin": "commercial", "aged_in_lab": false, "environment": null,
   "citations": ["PMC1:L1"], "reason": "Bought from Polysciences."},
  {"particle_name": "PE (aged)", "origin": "lab_fabricated", "aged_in_lab": true,
   "environment": null, "citations": ["PMC1:L2", "PMC1:L6"], "reason": "Milled film, UV aged."}
]}
Done."""


def test_the_parser_reads_a_canned_reply():
    parsed = origin.parse_reply(CANNED)
    assert not parsed.unparsed and parsed.problems == ()
    assert [p["particle_name"] for p in parsed.particles] == ["PS", "PE (aged)"]
    assert parsed.particles[1]["origin"] == "lab_fabricated"
    assert parsed.particles[1]["aged_in_lab"] is True


def test_the_parser_flags_what_it_cannot_use():
    bad = json.dumps(
        {
            "particles": [
                {
                    "particle_name": "PS",
                    "origin": "bought",
                    "aged_in_lab": None,
                    "environment": None,
                    "citations": [],
                    "reason": "x",
                },
                {
                    "particle_name": "MP",
                    "origin": "environmental",
                    "aged_in_lab": False,
                    "environment": "river",
                    "citations": ["PMC1:L5"],
                    "reason": "y",
                },
            ]
        }
    )
    parsed = origin.parse_reply(bad)
    assert not parsed.unparsed
    assert any("origin" in p and "bought" in p for p in parsed.problems)
    assert any("environment" in p and "river" in p for p in parsed.problems)
    assert origin.parse_reply("I cannot tell from these lines.").unparsed
    assert origin.parse_reply('{"answer": "commercial"}').unparsed


def test_citations_resolve_only_to_lines_of_that_paper():
    got = origin.check_citations(DOC, ["PMC1:L1", "L2", "PMC2:L1", "PMC1:L99", "row:PMC1-r1", "x"])
    assert got.resolved == ("PMC1:L1", "L2")
    assert got.unresolved == ("PMC2:L1", "PMC1:L99", "row:PMC1-r1", "x")


# -- the run ---------------------------------------------------------------------------------------


def _reply(text: str = CANNED) -> grid.Reply:
    return grid.Reply(text=text, model=grid.READER_MODEL, input_tokens=1000, output_tokens=50)


def _jobs(*pmcids: str) -> list[origin.Job]:
    return [origin.Job(p, ("PS",), f"prompt for {p}", 3, 0) for p in pmcids]


def _records(directory):
    path = directory / "answers.jsonl"
    return [json.loads(x) for x in path.read_text().splitlines()] if path.is_file() else []


def test_the_run_skips_answered_papers_and_retries_a_failure_once(tmp_path):
    calls: list[str] = []
    failed_once: set[str] = set()

    def reader(prompt: str) -> grid.Reply:
        calls.append(prompt)
        if "PMCB" in prompt and "PMCB" not in failed_once:
            failed_once.add("PMCB")
            raise grid.ReaderError("timed out")
        if "PMCC" in prompt:
            raise grid.ReaderError("rate limited")
        return _reply()

    counts = origin.run(_jobs("PMCA", "PMCB", "PMCC"), tmp_path, "r1", reader=reader, jobs=2)
    assert counts["answered_now"] == 2 and counts["reader_failures"] == 1
    assert calls.count("prompt for PMCB") == 2 and calls.count("prompt for PMCC") == 2
    assert {r["pmcid"] for r in _records(tmp_path)} == {"PMCA", "PMCB"}
    rec = _records(tmp_path)[0]
    for key in ("pmcid", "prompt_sha256", "text", "model", "input_tokens", "cost_usd", "at"):
        assert key in rec

    calls.clear()
    again = origin.run(_jobs("PMCA", "PMCB", "PMCC"), tmp_path, "r1", reader=reader, jobs=2)
    assert calls == ["prompt for PMCC", "prompt for PMCC"], "only the failed paper is asked again"
    assert again["already_answered"] == 2


def test_a_refusal_is_recorded_as_the_answer_and_not_asked_again(tmp_path):
    def reader(prompt: str) -> grid.Reply:
        raise grid.Refused("reader refused: Usage Policy")

    counts = origin.run(_jobs("PMCA"), tmp_path, "r1", reader=reader)
    assert counts["refused"] == 1
    (rec,) = _records(tmp_path)
    assert rec["refused"] is True
    assert origin.run(_jobs("PMCA"), tmp_path, "r1", reader=reader)["already_answered"] == 1


def test_an_answer_to_the_identical_prompt_is_reused_not_bought_again(tmp_path):
    origin.run(_jobs("PMCA", "PMCB"), tmp_path, "r0", reader=lambda p: _reply())
    earlier = origin.load_answers(tmp_path, "r0")
    changed = [*_jobs("PMCA"), origin.Job("PMCB", ("PS",), "a repaired prompt for PMCB", 4, 0)]
    asked: list[str] = []

    def reader(prompt: str) -> grid.Reply:
        asked.append(prompt)
        return _reply()

    counts = origin.run(changed, tmp_path, "r1", reader=reader, reuse=earlier)
    assert asked == ["a repaired prompt for PMCB"]
    assert counts["reused"] == 1 and counts["answered_now"] == 1
    now = origin.load_answers(tmp_path, "r1")
    assert now["PMCA"]["reused_from"] == "r0" and now["PMCA"]["text"] == earlier["PMCA"]["text"]
    assert "reused_from" not in now["PMCB"]


def test_the_budget_counts_what_every_run_in_the_directory_was_billed(tmp_path):
    origin.run(_jobs("PMCA"), tmp_path, "r0", reader=lambda p: _reply())  # billed 1000
    counts = origin.run(
        _jobs("PMCB", "PMCC"), tmp_path, "r1", reader=lambda p: _reply(), limit=1500
    )
    assert counts["answered_now"] == 1 and counts["over_budget"] == 1


def test_the_run_stops_at_the_input_token_budget(tmp_path):
    counts = origin.run(
        _jobs("PMCA", "PMCB", "PMCC"), tmp_path, "r1", reader=lambda p: _reply(), limit=1500
    )
    assert counts["answered_now"] == 2 and counts["over_budget"] == 1
