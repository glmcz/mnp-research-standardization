"""`extract retrofit` — stored quotes become line citations without re-reading a paper.

The retrofit's whole claim is that an address outlives the numbering it was written
against, so the tests that matter here are the two that fail if it stores the wrong
thing: an id must resolve back to a line that really contains the quote, and it must
still resolve after the document has been renumbered underneath it. A quote that does
not resolve is the other half — it must arrive in the table flagged, never dropped,
because the line document is a subset of the text the quote guard searched and a silent
drop would hide exactly the difference this migration exists to measure.
"""

import shutil

import pandas as pd
import pytest

from mnp import config
from mnp.corpus import lines
from mnp.extract import __main__ as cli
from mnp.extract import zeta
from mnp.report import d1

PMCID = "PMC5090179"

ROW = {
    "particle_name": "P1",
    "quantity": "zeta potential",
    "value": "-50 ± 9.7",
    "unit": "mV",
    "conditions": {"medium_text": "10 mM NaCl", "instrument": "Zetasizer NanoZS"},
    "evidence_quote": "Zeta potential in 10 mM NaCl (mV) b\t-50 ± 9.7",
}

NOT_IN_THE_PAPER = "No sentence in this article says anything remotely like this one."

EMPTY_XML = (
    b'<?xml version="1.0"?><article><front><article-meta>'
    b'<article-id pub-id-type="pmcid">PMC0000002</article-id>'
    b"</article-meta></front><body></body></article>"
)


@pytest.fixture
def workspace(tmp_path, monkeypatch, fixtures_dir):
    xml_dir = tmp_path / "xml"
    xml_dir.mkdir()
    shutil.copy(fixtures_dir / f"{PMCID}.xml", xml_dir / f"{PMCID}.xml")
    monkeypatch.setattr(config, "EPMC_XML_DIR", xml_dir)
    monkeypatch.setattr(config, "DATA_INTERIM", tmp_path / "interim")
    monkeypatch.setattr(config, "DATA_PROCESSED", tmp_path / "processed")
    monkeypatch.setattr(config, "OUT_TABLES", tmp_path / "out" / "tables")
    return tmp_path


def _seed(pmcid: str = PMCID, quote: str | None = None) -> zeta.ExtractionRecord:
    """One stored record, made the way the corpus was: coerced, verified, no line ids."""
    article = cli._article(PMCID)
    rec = zeta.extract_from_payload(article, {"measurements": [dict(ROW)]}, "test")
    assert rec.measurements, "fixture stopped producing a measurement"
    if quote is not None:
        rec.measurements[0].evidence.quote = quote
    if pmcid != PMCID:
        rec.pmcid = pmcid
        rec.measurements[0].row_id = f"{pmcid}-r1"
    _write({rec.pmcid: rec})
    return rec


def _write(done: dict[str, zeta.ExtractionRecord]) -> None:
    path = cli._jsonl_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    cli._rewrite(path, done)


def _stored(pmcid: str = PMCID) -> zeta.ExtractionRecord:
    return cli._load_records(cli._jsonl_path())[pmcid]


def _doc(pmcid: str = PMCID):
    return lines.build_lines(cli._article(pmcid))


def test_retrofit_stores_ids_that_resolve_back_to_a_line_holding_the_quote(workspace):
    _seed()
    assert cli.main(["retrofit"]) == 0
    stored = _stored().measurements[0].evidence
    assert stored.line_ids, "the quote located but no id was stored"
    doc = _doc()
    for ident in stored.line_ids:
        line = lines.resolve_id(doc, ident)
        assert line is not None, f"{ident} resolves to nothing"
        assert lines.fold(ROW["evidence_quote"]) in lines.fold(line.text)


def test_the_stored_address_survives_a_renumbering_of_the_document(workspace):
    """The whole reason the id is a hash: a parser fix that shifts every line number
    below it must leave a stored citation pointing at the same line."""
    _seed()
    assert cli.main(["retrofit"]) == 0
    ident = _stored().measurements[0].evidence.line_ids[0]
    before = lines.resolve_id(_doc(), ident)

    article = cli._article(PMCID)
    article.methods_text = "An injected sentence that shifts every number below it.\n" + (
        article.methods_text or ""
    )
    after = lines.resolve_id(lines.build_lines(article), ident)

    assert after is not None, "the address did not survive renumbering — a line number was stored"
    assert after.text == before.text
    assert after.n != before.n, "the document was not actually renumbered; the test proves nothing"


def test_line_ids_survive_the_json_round_trip(workspace):
    _seed()
    assert cli.main(["retrofit"]) == 0
    rec = _stored()
    again = zeta.ExtractionRecord.from_json(rec.to_json())
    ids = rec.measurements[0].evidence.line_ids
    assert ids and again.measurements[0].evidence.line_ids == ids


def test_the_parquet_and_the_published_csv_carry_the_column(workspace, tmp_path):
    _seed()
    assert cli.main(["retrofit"]) == 0
    table = pd.read_parquet(workspace / "processed" / "zeta_table.parquet")
    assert "evidence_line_ids" in table.columns
    ids = _stored().measurements[0].evidence.line_ids
    assert table.loc[0, "evidence_line_ids"] == ";".join(ids)

    d1.build(table, None, tmp_path / "t", tmp_path / "f")
    csv = pd.read_csv(tmp_path / "t" / "d1_zeta_table.csv")
    assert csv.loc[0, "evidence_line_ids"] == ";".join(ids)


def test_running_it_twice_leaves_the_record_byte_identical(workspace):
    _seed()
    assert cli.main(["retrofit"]) == 0
    once = cli._jsonl_path().read_bytes()
    assert cli.main(["retrofit"]) == 0
    assert cli._jsonl_path().read_bytes() == once


def test_a_quote_that_does_not_locate_is_flagged_and_kept(workspace, capsys):
    _seed(quote=NOT_IN_THE_PAPER)
    assert cli.main(["retrofit"]) == 0
    rec = _stored()
    assert rec.measurements[0].evidence.line_ids is None
    assert "evidence_not_located" in rec.row_flags[0]
    table = pd.read_parquet(workspace / "processed" / "zeta_table.parquet")
    assert len(table) == 1, "an unlocatable row was dropped from the table"
    assert pd.isna(table.loc[0, "evidence_line_ids"])
    out = capsys.readouterr().out
    assert f"{PMCID}-r1" in out, "the unlocatable row was not named"
    assert "not located" in out


def test_a_row_that_locates_loses_a_stale_not_located_flag(workspace):
    """The ids are a function of the article and the quote, not of the last run."""
    rec = _seed()
    rec.row_flags[0].append("evidence_not_located")
    _write({rec.pmcid: rec})
    assert cli.main(["retrofit"]) == 0
    assert "evidence_not_located" not in _stored().row_flags[0]


def test_dry_run_reports_and_writes_nothing(workspace, capsys):
    _seed()
    before = cli._jsonl_path().read_bytes()
    assert cli.main(["retrofit", "--dry-run"]) == 0
    assert cli._jsonl_path().read_bytes() == before
    assert _stored().measurements[0].evidence.line_ids is None
    assert not (workspace / "processed" / "zeta_table.parquet").is_file()
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "located: 1" in out


def test_a_missing_xml_is_reported_rather_than_a_crash(workspace, capsys):
    _seed(pmcid="PMC0000001")
    assert cli.main(["retrofit"]) == 0
    rec = _stored("PMC0000001")
    assert rec.measurements[0].evidence.line_ids is None
    assert "line_document_unavailable" in rec.row_flags[0]
    assert "PMC0000001" in capsys.readouterr().out


def test_an_article_with_no_retrievable_text_is_reported_rather_than_a_crash(workspace, capsys):
    (config.EPMC_XML_DIR / "PMC0000002.xml").write_bytes(EMPTY_XML)
    _seed(pmcid="PMC0000002")
    assert cli.main(["retrofit"]) == 0
    rec = _stored("PMC0000002")
    assert rec.measurements[0].evidence.line_ids is None
    assert "line_document_unavailable" in rec.row_flags[0]
    assert "PMC0000002" in capsys.readouterr().out
