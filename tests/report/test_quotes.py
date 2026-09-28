"""A withheld quote travels as an address, and the address must give the quote back exactly.

`address` and `restore` are one encoder and its decoder. The property that matters is the
round trip — byte for byte, checked by sha256 — and the property that makes withholding
honest is that the address itself carries no text: between the line slices it may hold only
the separators, whitespace and dash characters a slice cannot supply.
"""

import hashlib
import json

import pandas as pd
import pytest

from mnp import config
from mnp.corpus import jats, lines
from mnp.report import quotes


def _doc(methods: str, tables: tuple[jats.Table, ...] = ()) -> lines.LinedDoc:
    article = jats.Article(
        pmcid="PMCX", doi=None, title=None, year=None, journal=None, license=None,
        methods_text=methods, methods_source="title", tables=list(tables),
    )  # fmt: skip
    return lines.build_lines(article)


METHODS = (
    "Particles were dispersed in 10 mM NaCl at pH 7.0 before measurement.\n"
    "The zeta potential of the PS particles was -31.6 ± 0.4 mV at 25 °C.\n"
    "Measurements used a Malvern Zetasizer Nano ZS in triplicate."
)
TABLE = jats.Table(
    id="tab1",
    caption="Table 1. Zeta potential of the particles in lake water.",
    tsv="Particle\tSize\tZeta (mV)\nPS\t1 µm\t-12.42 ± 0.65\n\t12 µm\t-5.98 ± 0.27",
    footnotes=[],
)


def _round_trip(doc, quote, prefer=()):
    pieces = quotes.address(doc, quote, prefer=prefer)
    assert pieces is not None, f"could not address {quote!r}"
    assert quotes.restore(doc, pieces) == quote
    return pieces


def _glue(pieces):
    return [p for p in pieces if isinstance(p, str)]


def test_a_single_sentence_is_one_slice():
    doc = _doc(METHODS)
    quote = "The zeta potential of the PS particles was -31.6 ± 0.4 mV at 25 °C."
    pieces = _round_trip(doc, quote)
    assert len(pieces) == 1 and not _glue(pieces)
    line_id, start, end = pieces[0]
    assert doc.lines[1].line_id == line_id and (start, end) == (0, len(quote))


def test_parts_joined_by_the_separator_become_slices_and_the_separator_is_glue():
    doc = _doc(METHODS)
    quote = "dispersed in 10 mM NaCl at pH 7.0 || was -31.6 ± 0.4 mV at 25 °C"
    pieces = _round_trip(doc, quote)
    assert _glue(pieces) == [" || "]


@pytest.mark.parametrize("sep", ["||", "\t || ", " ||  "])
def test_the_separator_as_actually_written_is_restored(sep):
    """Real rows join with '||', '\\t || ' and ' || \\t' as well as ' || '."""
    doc = _doc(METHODS)
    quote = f"dispersed in 10 mM NaCl{sep}Malvern Zetasizer Nano ZS"
    _round_trip(doc, quote)


def test_a_passage_across_table_lines_is_one_slice_per_line():
    """A caption and the rows beneath it: the guard folded the newlines, the address keeps them."""
    doc = _doc(METHODS, (TABLE,))
    quote = "PS\t1 µm\t-12.42 ± 0.65\n\t12 µm\t-5.98 ± 0.27"
    pieces = _round_trip(doc, quote)
    assert _glue(pieces) == ["\n"]
    assert len([p for p in pieces if not isinstance(p, str)]) == 2


def test_a_quote_that_differs_only_in_dashes_and_whitespace_is_addressed_with_that_glue():
    """The model wrote an en dash and spaces where the parsed line has a hyphen and tabs."""
    doc = _doc(METHODS, (TABLE,))
    quote = "PS 1 µm –12.42 ± 0.65"
    pieces = _round_trip(doc, quote)
    for g in _glue(pieces):
        assert set(g) <= quotes.GLUE_ALPHABET, repr(g)


def test_the_address_never_carries_a_letter_or_a_digit():
    doc = _doc(METHODS, (TABLE,))
    for quote in (
        "PS 1 µm –12.42 ± 0.65",
        "dispersed in 10 mM NaCl||Malvern Zetasizer Nano ZS",
        "PS\t1 µm\t-12.42 ± 0.65\n\t12 µm\t-5.98 ± 0.27",
    ):
        for g in _glue(_round_trip(doc, quote)):
            assert not any(ch.isalnum() for ch in g), repr(g)


def test_a_quote_that_is_not_in_the_document_has_no_address():
    doc = _doc(METHODS)
    assert quotes.address(doc, "The zeta potential was -45 mV in seawater.") is None
    # Folding may not paper over a real difference of wording either.
    assert quotes.address(doc, "The zeta potential of the PE particles was -31.6") is None


def test_the_cited_line_is_preferred_over_an_earlier_identical_one():
    doc = _doc("Zeta was -20 mV.\nSomething else.\nZeta was -20 mV.")
    second = doc.lines[2].line_id
    pieces = _round_trip(doc, "Zeta was -20 mV.", prefer=(second,))
    assert pieces[0][0] == second


def test_restore_refuses_a_line_that_is_not_in_the_document():
    doc = _doc(METHODS)
    with pytest.raises(KeyError):
        quotes.restore(doc, [["0" * 16, 0, 4]])


def test_the_spans_serialise_to_json_and_back():
    doc = _doc(METHODS, (TABLE,))
    quote = "dispersed in 10 mM NaCl || PS 1 µm –12.42 ± 0.65"
    pieces = _round_trip(doc, quote)
    assert quotes.restore(doc, json.loads(quotes.dumps(pieces))) == quote


# --- rehydrate, on the release this repository ships -------------------------------------


@pytest.fixture
def shipped():
    release = config.ROOT / "out" / "release" / "dataset.parquet"
    source = config.ROOT / "out" / "tables" / "d1_zeta_table.csv"
    if not (release.is_file() and source.is_file()):
        pytest.skip("no committed release here")
    if not any(config.EPMC_XML_DIR.glob("PMC*.xml")):
        pytest.skip("no corpus restored here")
    table = pd.read_parquet(release)
    if "quote_withheld" not in table.columns:
        pytest.fail("the committed release predates quote withholding — rebuild it")
    return table, pd.read_csv(source)


def test_rehydrate_restores_every_withheld_quote_exactly(shipped, tmp_path):
    """All of them, not a sample: the whole corpus parses in a few seconds."""
    table, source = shipped
    withheld = table[table["quote_withheld"]]
    assert len(withheld), "nothing is withheld — the licence decision did not reach the table"
    result = quotes.rehydrate(
        config.ROOT / "out" / "release", tmp_path / "rehydrated", xml_dir=config.EPMC_XML_DIR
    )
    assert result.failed == [] and result.missing_xml == []
    assert result.restored == len(withheld)

    restored = pd.read_parquet(tmp_path / "rehydrated" / "dataset.parquet").set_index("row_id")
    original = source.set_index("row_id")["evidence_quote"]
    for row_id in withheld["row_id"]:
        quote = restored.loc[row_id, "evidence_quote"]
        assert quote == original[row_id], row_id
        digest = hashlib.sha256(quote.encode()).hexdigest()
        assert digest == restored.loc[row_id, "evidence_quote_sha256"]


def test_rehydrate_names_a_quote_that_does_not_match_its_hash(shipped, tmp_path):
    """A source re-typeset upstream moves its offsets; the sha256 check has to catch that."""
    table, _ = shipped
    release = tmp_path / "release"
    release.mkdir()
    tampered = table.copy()
    row = tampered.index[tampered["quote_withheld"]][0]
    pieces = json.loads(tampered.at[row, "evidence_quote_spans"])
    first = next(p for p in pieces if not isinstance(p, str))
    first[1] += 1  # one character later: the text a moved line would now give back
    tampered.at[row, "evidence_quote_spans"] = quotes.dumps(pieces)
    tampered.to_parquet(release / "dataset.parquet", index=False)
    result = quotes.rehydrate(release, tmp_path / "out", xml_dir=config.EPMC_XML_DIR)
    assert result.failed == [tampered.at[row, "row_id"]]
    assert result.restored == int(table["quote_withheld"].sum()) - 1
    restored = pd.read_parquet(tmp_path / "out" / "dataset.parquet")
    assert (
        restored.loc[restored["row_id"] == tampered.at[row, "row_id"], "evidence_quote"]
        .isna()
        .all()
    )


def test_rehydrate_reports_a_missing_source_instead_of_skipping_it(shipped, tmp_path):
    table, _ = shipped
    withheld_papers = table.loc[table["quote_withheld"], "pmcid"].unique()
    empty = tmp_path / "xml"
    empty.mkdir()
    result = quotes.rehydrate(config.ROOT / "out" / "release", tmp_path / "out", xml_dir=empty)
    assert sorted(result.missing_xml) == sorted(withheld_papers)
    assert result.restored == 0


def test_allowed_rows_ship_their_quote_unchanged(shipped):
    table, source = shipped
    allowed = table[~table["quote_withheld"]].set_index("row_id")
    original = source.set_index("row_id")["evidence_quote"]
    assert len(allowed)
    for row_id, quote in allowed["evidence_quote"].items():
        assert quote == original[row_id], row_id


def test_no_withheld_quote_text_appears_in_any_release_file(shipped):
    """Every file, decoded as its reader would decode it — parquet is compressed on disk."""
    table, source = shipped
    withheld_ids = set(table.loc[table["quote_withheld"], "row_id"])
    original = source.set_index("row_id")["evidence_quote"]
    parts = {
        p.strip()
        for row_id in withheld_ids
        for p in original[row_id].split(lines.EVIDENCE_SEP)
        if len(p.strip()) > 30
    }
    assert parts

    release = config.ROOT / "out" / "release"
    haystacks = {}
    for path in sorted(release.rglob("*")):
        if not path.is_file():
            continue
        raw = path.read_bytes()
        texts = [raw.decode("utf-8", errors="replace")]
        if path.suffix == ".parquet":
            frame = pd.read_parquet(path)
            texts.append("\n".join(str(v) for v in frame.to_numpy().ravel()))
        if path.suffix == ".jsonl":
            texts += [json.dumps(json.loads(line)) for line in texts[0].splitlines()]
            texts += [str(v) for line in texts[0].splitlines() for v in json.loads(line).values()]
        haystacks[path.name] = "\n".join(texts)
    assert {"dataset.parquet", "dataset.jsonl", "DATASET_CARD.md", "LICENSE"} <= set(haystacks)
    leaks = [(name, p[:60]) for name, text in haystacks.items() for p in parts if p in text]
    assert not leaks, f"{len(leaks)} withheld passages found in the release: {leaks[:5]}"


# --- the CLI ------------------------------------------------------------------------------


def test_rehydrate_is_not_a_builder_so_all_and_reproduce_never_run_it():
    from mnp.report import __main__ as cli

    assert "rehydrate" not in cli.RUNNERS
    assert "rehydrate" in cli.COMMANDS


def test_report_all_does_not_call_rehydrate(tmp_path, monkeypatch):
    from mnp.report import __main__ as cli

    def boom(args):
        raise AssertionError("report all ran rehydrate")

    ran = []
    monkeypatch.setattr(cli, "run_rehydrate", boom)
    # The dispatch is what is under test, not the builders: swap them for no-ops.
    monkeypatch.setattr(
        cli, "RUNNERS", {k: (lambda a, k=k: ran.append(k) or []) for k in cli.RUNNERS}
    )
    assert cli.main(["all", "--out", str(tmp_path / "out")]) == 0
    assert ran and "release" in ran


def test_rehydrate_refuses_to_write_into_the_published_tree(shipped, tmp_path, capsys):
    from mnp.report import __main__ as cli

    assert cli.main(["rehydrate", "--out", str(config.OUT / "release")]) != 0
    assert cli.main(["rehydrate", "--out", str(config.OUT / "anything")]) != 0
    assert "out/" in capsys.readouterr().err


def test_rehydrate_cli_writes_a_local_copy(shipped, tmp_path, capsys):
    from mnp.report import __main__ as cli

    target = tmp_path / "local"
    assert cli.main(["rehydrate", "--out", str(target)]) == 0
    assert (target / "dataset.parquet").is_file() and (target / "dataset.jsonl").is_file()
    assert "restored" in capsys.readouterr().out
