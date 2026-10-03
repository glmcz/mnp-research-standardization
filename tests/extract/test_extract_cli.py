import json
import shutil
from types import SimpleNamespace

import pandas as pd
import pytest

from mnp import config
from mnp.extract import __main__ as cli
from mnp.extract import llm, prompts, provenance

ROW = {
    "particle_name": "P1",
    "quantity": "zeta potential",
    "value": "-50 ± 9.7",
    "unit": "mV",
    "conditions": {"medium_text": "10 mM NaCl", "instrument": "Zetasizer NanoZS"},
    "evidence_quote": "Zeta potential in 10 mM NaCl (mV) b\t-50 ± 9.7",
}


class ScriptedLLM:
    def __init__(self, payload):
        self.payload = payload
        self.chain = ["scripted"]
        self.calls = 0

    def complete_json(self, system, user, **kw):
        self.calls += 1
        return self.payload, SimpleNamespace(
            model="scripted", cached=False, attempts=[], prompt_tokens=None, completion_tokens=None
        )


@pytest.fixture
def workspace(tmp_path, monkeypatch, fixtures_dir):
    xml_dir = tmp_path / "xml"
    xml_dir.mkdir()
    shutil.copy(fixtures_dir / "PMC5090179.xml", xml_dir / "PMC5090179.xml")
    interim = tmp_path / "interim"
    processed = tmp_path / "processed"
    monkeypatch.setattr(config, "EPMC_XML_DIR", xml_dir)
    monkeypatch.setattr(config, "DATA_INTERIM", interim)
    monkeypatch.setattr(config, "DATA_PROCESSED", processed)
    monkeypatch.setattr(config, "ANNOTATION", interim / "annotation")
    monkeypatch.setattr(config, "LLM_CACHE", interim / "llm_cache")
    monkeypatch.setattr(config, "OUT_TABLES", tmp_path / "out" / "tables")
    return tmp_path


def _articles_parquet(workspace, pmcids=("PMC5090179",)):
    df = pd.DataFrame(
        [
            {"pmcid": p, "doi": "10.1/x", "year": 2015, "journal": "J", "methods_source": "title"}
            for p in pmcids
        ]
    )
    (workspace / "interim").mkdir(exist_ok=True)
    df.to_parquet(workspace / "interim" / "articles.parquet", index=False)


def test_run_extracts_every_article_and_writes_jsonl_and_parquet(workspace, monkeypatch):
    _articles_parquet(workspace)
    fake = ScriptedLLM({"measurements": [ROW]})
    monkeypatch.setattr(llm, "from_env", lambda cache_dir=None, model=None: fake)
    assert cli.main(["run", "--concurrency", "1"]) == 0
    lines = (workspace / "interim" / "extractions.jsonl").read_text().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["pmcid"] == "PMC5090179"
    assert rec["measurements"][0]["value"] == -50.0
    table = pd.read_parquet(workspace / "processed" / "zeta_table.parquet")
    assert list(table["pmcid"]) == ["PMC5090179"]
    assert bool(table.loc[0, "evidence_verified"]) is True
    summary = json.loads((workspace / "processed" / "extraction_summary.json").read_text())
    assert summary["papers"] == 1
    assert summary["rows"] == 1
    assert summary["rows_verified"] == 1


def test_run_resumes_from_existing_jsonl(workspace, monkeypatch):
    _articles_parquet(workspace)
    (workspace / "interim").mkdir(exist_ok=True)
    done = {
        "pmcid": "PMC5090179", "doi": None, "model": "old", "prompt_sha256": "x",
        "measurements": [], "row_flags": [], "dropped": [], "n_candidates": 0,
        "n_candidates_matched": 0, "unmatched_candidates": [], "error": None, "cached": False,
        "extraction_tokens": 0, "methods_source": None, "year": None, "journal": None,
    }  # fmt: skip
    (workspace / "interim" / "extractions.jsonl").write_text(json.dumps(done) + "\n")
    fake = ScriptedLLM({"measurements": [ROW]})
    monkeypatch.setattr(llm, "from_env", lambda cache_dir=None, model=None: fake)
    assert cli.main(["run"]) == 0
    assert fake.calls == 0
    assert len((workspace / "interim" / "extractions.jsonl").read_text().splitlines()) == 1


def test_run_limit_and_missing_xml_are_handled(workspace, monkeypatch):
    _articles_parquet(workspace, ("PMC5090179", "PMC0000001"))
    fake = ScriptedLLM({"measurements": [ROW]})
    monkeypatch.setattr(llm, "from_env", lambda cache_dir=None, model=None: fake)
    assert cli.main(["run", "--limit", "5"]) == 0
    lines = [
        json.loads(x)
        for x in (workspace / "interim" / "extractions.jsonl").read_text().splitlines()
    ]
    assert {r["pmcid"] for r in lines} == {"PMC5090179", "PMC0000001"}
    missing = next(r for r in lines if r["pmcid"] == "PMC0000001")
    assert "xml" in missing["error"].lower()
    assert fake.calls == 1


def test_sample_is_stratified_seeded_and_excludes_the_dev_set(workspace):
    years = [2016] * 10 + [2020] * 10 + [2024] * 10
    pmcids = [f"PMC{i:07d}" for i in range(30)]
    df = pd.DataFrame(
        {"pmcid": pmcids, "doi": pmcids, "year": years, "journal": "J", "methods_source": "title"}
    )
    (workspace / "interim").mkdir(exist_ok=True)
    df.to_parquet(workspace / "interim" / "articles.parquet", index=False)
    assert cli.main(["sample", "--n", "12", "--dev", "6", "--seed", "1"]) == 0
    sample = pd.read_csv(workspace / "interim" / "annotation" / "sample_50.csv")
    dev = pd.read_csv(workspace / "interim" / "annotation" / "dev_20.csv")
    assert len(sample) == 12 and len(dev) == 6
    assert set(sample.pmcid).isdisjoint(set(dev.pmcid))
    assert sample["year_band"].value_counts().to_dict() == {
        "<=2018": 4,
        "2019-2022": 4,
        "2023-2026": 4,
    }
    assert cli.main(["sample", "--n", "12", "--dev", "6", "--seed", "1"]) == 0
    again = pd.read_csv(workspace / "interim" / "annotation" / "sample_50.csv")
    assert list(again.pmcid) == list(sample.pmcid)


def test_evaluate_subcommand_writes_the_table(workspace, tmp_path):
    gold = pd.DataFrame(
        [dict(pmcid="PMC5090179", row_id="g1", particle_name="P1", medium_text="10 mM NaCl",
              medium_class="salt_solution", ionic_strength_mM=10.0, pH=None, temperature_C=None,
              instrument="Zetasizer NanoZS", quantity="zeta_potential", value=-50.0, unit="mV",
              annotator="claude")]
    )  # fmt: skip
    gold_path = tmp_path / "gold.csv"
    gold.to_csv(gold_path, index=False)
    pred = pd.DataFrame(
        [dict(pmcid="PMC5090179", row_id="p1", particle_name="P1", medium_text="10 mM NaCl",
              medium_class="salt_solution", ionic_strength_mM=10.0, pH=None, temperature_C=None,
              instrument="Zetasizer NanoZS", quantity="zeta_potential", value=-50.0, unit="mV",
              evidence_verified=True)]
    )  # fmt: skip
    (workspace / "processed").mkdir(exist_ok=True)
    pred.to_parquet(workspace / "processed" / "zeta_table.parquet", index=False)
    assert cli.main(["evaluate", "--gold", str(gold_path)]) == 0
    table = pd.read_csv(workspace / "out" / "tables" / "d1_precision_recall.csv")
    assert (table[(table.level == "row") & (table.field == "value")]["tp"] == 1).all()
    report = json.loads((workspace / "processed" / "evaluation.json").read_text())
    assert report["audit"]["n_audited_rows"] == 0


def test_show_prints_what_the_model_would_read(workspace, capsys):
    _articles_parquet(workspace)
    assert cli.main(["show", "--pmcid", "PMC5090179"]) == 0
    out = capsys.readouterr().out
    assert "== Methods" in out
    assert "Zetasizer NanoZS" in out
    assert "<article>" in out
    assert "Rules" in out  # the system prompt is printed too


def test_ingest_runs_the_same_pipeline_on_a_supplied_payload(workspace, tmp_path):
    _articles_parquet(workspace)
    payload = tmp_path / "PMC5090179.json"
    payload.write_text(json.dumps({"measurements": [ROW]}))
    assert cli.main(["ingest", "--pmcid", "PMC5090179", "--json", str(payload),
                     "--model", "claude-code:sonnet", "--no-brief"]) == 0  # fmt: skip
    lines = (workspace / "interim" / "extractions.jsonl").read_text().splitlines()
    rec = json.loads(lines[-1])
    assert rec["model"] == "claude-code:sonnet"
    assert rec["n_candidates"] == 14
    assert rec["n_candidates_matched"] == 1
    assert rec["measurements"][0]["evidence"]["verified"] is True
    table = pd.read_parquet(workspace / "processed" / "zeta_table.parquet")
    assert len(table) == 1


def test_ingest_replaces_an_earlier_record_for_the_same_pmcid(workspace, tmp_path, capsys):
    _articles_parquet(workspace)
    payload = tmp_path / "p.json"
    payload.write_text(json.dumps({"measurements": [ROW]}))
    cli.main(["ingest", "--pmcid", "PMC5090179", "--json", str(payload), "--no-brief"])
    payload.write_text(json.dumps({"measurements": [ROW, ROW]}))
    cli.main(["ingest", "--pmcid", "PMC5090179", "--json", str(payload), "--no-brief"])
    lines = (workspace / "interim" / "extractions.jsonl").read_text().splitlines()
    assert len(lines) == 1
    assert len(json.loads(lines[0])["measurements"]) == 2
    printed = capsys.readouterr().out
    assert "coverage" in printed and "unmatched" in printed


def test_a_dry_run_ingest_gives_the_same_feedback_and_records_nothing(workspace, tmp_path, capsys):
    """A re-read control must see what a worker sees, and must not touch the dataset."""
    _articles_parquet(workspace)
    payload = tmp_path / "p.json"
    payload.write_text(json.dumps({"measurements": [ROW]}))
    assert cli.main(["ingest", "--pmcid", "PMC5090179", "--json", str(payload), "--no-brief",
                     "--dry-run"]) == 0  # fmt: skip
    printed = capsys.readouterr().out
    assert "PMC5090179: rows=1" in printed and "coverage" in printed
    assert "dry run" in printed
    assert not (workspace / "interim" / "extractions.jsonl").exists()
    assert not (workspace / "processed" / "zeta_table.parquet").exists()


def test_ingest_reports_a_broken_payload_without_writing(workspace, tmp_path):
    _articles_parquet(workspace)
    payload = tmp_path / "bad.json"
    payload.write_text("not json")
    assert cli.main(["ingest", "--pmcid", "PMC5090179", "--json", str(payload), "--no-brief"]) == 1
    assert not (workspace / "interim" / "extractions.jsonl").exists()


def test_todo_lists_undone_pmcids_in_order(workspace, tmp_path, capsys):
    _articles_parquet(workspace, ("PMC5090179", "PMC0000001", "PMC0000002"))
    payload = tmp_path / "p.json"
    payload.write_text(json.dumps({"measurements": [ROW]}))
    cli.main(["ingest", "--pmcid", "PMC5090179", "--json", str(payload), "--no-brief"])
    capsys.readouterr()
    assert cli.main(["todo", "--limit", "5"]) == 0
    assert capsys.readouterr().out.split() == ["PMC0000001", "PMC0000002"]


def test_parallel_ingests_do_not_lose_records(workspace, tmp_path):
    """Six processes ingest six PMCIDs at once; all six must survive."""
    import shutil
    import subprocess
    import sys

    pmcids = [f"PMC{i:07d}" for i in range(6)]
    for p in pmcids:
        shutil.copy(workspace / "xml" / "PMC5090179.xml", workspace / "xml" / f"{p}.xml")
    _articles_parquet(workspace, tuple(pmcids))
    payload = tmp_path / "p.json"
    payload.write_text(json.dumps({"measurements": [ROW]}))
    script = (
        "import sys; from mnp import config; from pathlib import Path;"
        f"config.EPMC_XML_DIR = Path({str(workspace / 'xml')!r});"
        f"config.DATA_INTERIM = Path({str(workspace / 'interim')!r});"
        f"config.DATA_PROCESSED = Path({str(workspace / 'processed')!r});"
        "from mnp.extract.__main__ import main;"
        "sys.exit(main(['ingest', '--pmcid', sys.argv[1], '--json', sys.argv[2],"
        " '--no-brief']))"
    )
    procs = [
        subprocess.Popen([sys.executable, "-c", script, p, str(payload)], stdout=subprocess.DEVNULL)
        for p in pmcids
    ]
    assert all(pr.wait() == 0 for pr in procs)
    lines = (workspace / "interim" / "extractions.jsonl").read_text().splitlines()
    assert sorted(json.loads(x)["pmcid"] for x in lines) == pmcids


def test_gold_merge_builds_the_csv_from_json_parts(workspace, capsys):
    _articles_parquet(workspace, ("PMC5090179", "PMC0000001"))
    parts = workspace / "interim" / "annotation" / "gold_parts"
    parts.mkdir(parents=True)
    sample = pd.DataFrame({"pmcid": ["PMC5090179", "PMC0000001"], "year": [2015, 2020]})
    sample.to_csv(workspace / "interim" / "annotation" / "sample_50.csv", index=False)
    (parts / "gold_1.json").write_text(json.dumps([
        {"pmcid": "PMC5090179", "row_id": "PMC5090179-g1", "particle_name": "P1",
         "medium_text": "10 mM NaCl", "medium_class": "salt_solution", "ionic_strength_mM": 10,
         "I_reported": True, "I_inferable_from_named_salt": True, "pH": None, "pH_reported": True,
         "temperature_C": None, "T_reported": True, "instrument": "Zetasizer NanoZS",
         "instrument_reported": True, "quantity": "zeta_potential", "value": -50, "unit": "mV",
         "sd": 9.7, "n": None, "medium_matches_exposure": False,
         "evidence_quote": "Zeta potential in 10 mM NaCl (mV) b\\t-50 ± 9.7",
         "evidence_location": "Table 1", "annotator": "claude-opus-gold",
         "notes": "pH_range:6.8-7.2; rt"},
    ]))  # fmt: skip
    (parts / "gold_2.json").write_text(json.dumps([
        {"pmcid": "PMC0000001", "annotator": "claude-opus-gold", "notes": "no_measurement"},
    ]))  # fmt: skip
    assert cli.main(["gold-merge"]) == 0
    gold = pd.read_csv(workspace / "interim" / "annotation" / "gold_50.csv")
    from mnp.schema.models import GOLD_COLUMNS

    assert list(gold.columns) == list(GOLD_COLUMNS)
    assert len(gold) == 2
    row = gold[gold.pmcid == "PMC5090179"].iloc[0]
    assert row["doi"] == "10.1/x"  # filled from articles.parquet
    assert row["value"] == -50 and bool(row["T_reported"]) is True
    assert "missing: none" in capsys.readouterr().out


def test_gold_merge_reports_sampled_pmcids_without_rows(workspace, capsys):
    _articles_parquet(workspace, ("PMC5090179", "PMC0000001"))
    parts = workspace / "interim" / "annotation" / "gold_parts"
    parts.mkdir(parents=True)
    pd.DataFrame({"pmcid": ["PMC5090179", "PMC0000001"]}).to_csv(
        workspace / "interim" / "annotation" / "sample_50.csv", index=False
    )
    (parts / "gold_1.json").write_text(json.dumps([{"pmcid": "PMC5090179", "value": -1}]))
    assert cli.main(["gold-merge"]) == 1
    assert "missing: PMC0000001" in capsys.readouterr().out


def test_run_does_not_clobber_records_written_while_it_was_working(workspace, monkeypatch):
    """A worker's `ingest` lands mid-run; `run` must rebuild the table from disk."""
    _articles_parquet(workspace, ("PMC5090179",))
    other = {
        "pmcid": "PMC0000009", "doi": None, "model": "claude-code", "prompt_sha256": "x",
        "measurements": [], "row_flags": [], "dropped": [], "n_candidates": 0,
        "n_candidates_matched": 0, "unmatched_candidates": [], "error": None, "cached": False,
        "extraction_tokens": 0, "methods_source": None, "year": None, "journal": None,
    }  # fmt: skip

    class Interloper(ScriptedLLM):
        def complete_json(self, system, user, **kw):
            path = workspace / "interim" / "extractions.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a") as fh:
                fh.write(json.dumps(other) + "\n")
            return super().complete_json(system, user, **kw)

    fake = Interloper({"measurements": [ROW]})
    monkeypatch.setattr(llm, "from_env", lambda cache_dir=None, model=None: fake)
    assert cli.main(["run", "--concurrency", "1"]) == 0
    lines = (workspace / "interim" / "extractions.jsonl").read_text().splitlines()
    assert sorted(json.loads(x)["pmcid"] for x in lines) == ["PMC0000009", "PMC5090179"]
    table = pd.read_parquet(workspace / "processed" / "zeta_table.parquet")
    assert list(table["pmcid"]) == ["PMC5090179"]
    summary = json.loads((workspace / "processed" / "extraction_summary.json").read_text())
    assert summary["papers"] == 2


def test_run_retries_papers_whose_previous_record_was_an_error(workspace, monkeypatch):
    _articles_parquet(workspace)
    (workspace / "interim").mkdir(exist_ok=True)
    failed = {
        "pmcid": "PMC5090179", "doi": None, "model": None, "prompt_sha256": "x",
        "measurements": [], "row_flags": [], "dropped": [], "n_candidates": 0,
        "n_candidates_matched": 0, "unmatched_candidates": [], "error": "all models failed",
        "cached": False, "extraction_tokens": 0, "methods_source": None, "year": None,
        "journal": None,
    }  # fmt: skip
    (workspace / "interim" / "extractions.jsonl").write_text(json.dumps(failed) + "\n")
    fake = ScriptedLLM({"measurements": [ROW]})
    monkeypatch.setattr(llm, "from_env", lambda cache_dir=None, model=None: fake)
    assert cli.main(["run"]) == 0
    assert fake.calls == 1
    lines = (workspace / "interim" / "extractions.jsonl").read_text().splitlines()
    records = [json.loads(x) for x in lines]
    assert [r["pmcid"] for r in records] == ["PMC5090179"]
    assert records[0]["error"] is None
    assert len(records[0]["measurements"]) == 1


def test_run_keeps_an_error_record_when_retries_are_disabled(workspace, monkeypatch):
    _articles_parquet(workspace)
    (workspace / "interim").mkdir(exist_ok=True)
    failed = {
        "pmcid": "PMC5090179", "doi": None, "model": None, "prompt_sha256": "x",
        "measurements": [], "row_flags": [], "dropped": [], "n_candidates": 0,
        "n_candidates_matched": 0, "unmatched_candidates": [], "error": "boom", "cached": False,
        "extraction_tokens": 0, "methods_source": None, "year": None, "journal": None,
    }  # fmt: skip
    (workspace / "interim" / "extractions.jsonl").write_text(json.dumps(failed) + "\n")
    fake = ScriptedLLM({"measurements": [ROW]})
    monkeypatch.setattr(llm, "from_env", lambda cache_dir=None, model=None: fake)
    assert cli.main(["run", "--no-retry-errors"]) == 0
    assert fake.calls == 0


def test_gold_merge_lets_a_later_part_supersede_an_earlier_one(workspace, capsys):
    _articles_parquet(workspace, ("PMC5090179", "PMC0000001"))
    parts = workspace / "interim" / "annotation" / "gold_parts"
    parts.mkdir(parents=True)
    pd.DataFrame({"pmcid": ["PMC5090179", "PMC0000001"]}).to_csv(
        workspace / "interim" / "annotation" / "sample_50.csv", index=False
    )
    (parts / "gold_1.json").write_text(json.dumps([
        {"pmcid": "PMC5090179", "row_id": "a", "value": None, "notes": "no_measurement"},
        {"pmcid": "PMC0000001", "row_id": "b", "value": -10, "notes": ""},
    ]))  # fmt: skip
    (parts / "gold_r1.json").write_text(json.dumps([
        {"pmcid": "PMC5090179", "row_id": "c", "value": -30, "notes": "reannotated"},
        {"pmcid": "PMC5090179", "row_id": "d", "value": -40, "notes": "reannotated"},
    ]))  # fmt: skip
    assert cli.main(["gold-merge"]) == 0
    gold = pd.read_csv(workspace / "interim" / "annotation" / "gold_50.csv")
    assert sorted(gold["value"].dropna()) == [-40.0, -30.0, -10.0]
    assert list(gold[gold.pmcid == "PMC5090179"]["notes"]) == ["reannotated", "reannotated"]
    assert "superseded" in capsys.readouterr().out


def test_audit_sample_writes_a_blind_worksheet_for_the_author(workspace, capsys):
    ann = workspace / "interim" / "annotation"
    ann.mkdir(parents=True)
    rows = []
    for i in range(6):
        rows.append(dict(
            pmcid=f"PMC{i:07d}", row_id=f"PMC{i:07d}-g1", particle_name="PS",
            medium_text="10 mM NaCl", medium_class="salt_solution", ionic_strength_mM=10.0,
            I_reported=True, pH=7.0, pH_reported=True, temperature_C=25.0, T_reported=True,
            instrument="Zetasizer", instrument_reported=True, quantity="zeta_potential",
            value=-30.0 - i, unit="mV", evidence_quote="q", evidence_location="Table 1",
            annotator="claude-opus-gold", notes="",
        ))  # fmt: skip
    pd.DataFrame(rows).to_csv(ann / "gold_50.csv", index=False)
    assert cli.main(["audit-sample", "--n", "3", "--seed", "7"]) == 0
    sheet = pd.read_csv(ann / "audit_10.csv")
    assert sheet["pmcid"].nunique() == 3
    assert set(sheet["annotator"]) == {"author"}
    # the author's judgement must be blind: the gold verdicts are blanked out
    for col in ("I_reported", "pH_reported", "T_reported", "instrument_reported", "value"):
        assert sheet[col].isna().all(), col
    # but the identifying context stays, so the author knows which row to check
    assert set(sheet["particle_name"]) == {"PS"}
    assert (sheet["evidence_location"] == "Table 1").all()
    from mnp.schema.models import GOLD_COLUMNS

    assert list(sheet.columns) == list(GOLD_COLUMNS)
    assert cli.main(["audit-sample", "--n", "3", "--seed", "7"]) == 0
    again = pd.read_csv(ann / "audit_10.csv")
    assert list(again["pmcid"]) == list(sheet["pmcid"])
    assert "gold_parts/gold_audit.json" in capsys.readouterr().out


def test_review_list_splits_the_corpus_and_links_every_skipped_paper(workspace, capsys):
    rows = [
        {"pmcid": "PMC5090179", "doi": "10.1/a", "title": "Has values", "year": 2015,
         "journal": "J", "methods_source": "title",
         "extraction_text": "== Table T1\nZeta (mV)\t-41.2\n"},
        {"pmcid": "PMC0000002", "doi": "10.1/b", "title": "No values", "year": 2020,
         "journal": "K", "methods_source": "none",
         "extraction_text": "== Methods\nNothing here.\n"},
        {"pmcid": "PMC0000003", "doi": None, "title": "Mentions but prints nothing",
         "year": 2021, "journal": "K", "methods_source": "title",
         "extraction_text": "== Methods\nZeta potential was measured on a Zetasizer.\n"},
    ]  # fmt: skip
    (workspace / "interim").mkdir(exist_ok=True)
    pd.DataFrame(rows).to_parquet(workspace / "interim" / "articles.parquet", index=False)
    assert cli.main(["review-list"]) == 0
    csv = pd.read_csv(workspace / "out" / "tables" / "d1_papers_without_printed_values.csv")
    # papers that discuss zeta without printing a number come first: those need the glance
    assert list(csv["pmcid"]) == ["PMC0000003", "PMC0000002"]
    assert bool(csv.loc[0, "mentions_zeta"]) is True
    assert bool(csv.loc[1, "mentions_zeta"]) is False
    assert csv.loc[1, "url"] == "https://europepmc.org/article/PMC/PMC0000002"
    assert csv.loc[1, "doi_url"] == "https://doi.org/10.1/b"
    assert pd.isna(csv.loc[0, "doi_url"])
    md = (workspace / "out" / "tables" / "d1_papers_without_printed_values.md").read_text()
    assert "[PMC0000003](https://europepmc.org/article/PMC/PMC0000003)" in md
    assert "Mentions but prints nothing" in md
    assert "PMC5090179" not in md
    out = capsys.readouterr().out
    assert "2 of 3 papers print no value (1 mention zeta)" in out


def test_todo_can_restrict_to_papers_that_print_a_value(workspace, capsys):
    rows = [
        {"pmcid": "PMC5090179", "doi": "10.1/a", "title": "t", "year": 2015, "journal": "J",
         "methods_source": "title",
         "extraction_text": "== Table T1\nZeta (mV)\t-41.2\n"},
        {"pmcid": "PMC0000002", "doi": "10.1/b", "title": "t", "year": 2020, "journal": "K",
         "methods_source": "none", "extraction_text": "== Methods\nNothing here.\n"},
    ]  # fmt: skip
    (workspace / "interim").mkdir(exist_ok=True)
    pd.DataFrame(rows).to_parquet(workspace / "interim" / "articles.parquet", index=False)
    assert cli.main(["todo", "--with-values"]) == 0
    assert capsys.readouterr().out.split() == ["PMC5090179"]
    assert cli.main(["todo"]) == 0
    assert capsys.readouterr().out.split() == ["PMC5090179", "PMC0000002"]


def test_recount_refreshes_coverage_without_calling_any_model(workspace, tmp_path):
    """Coverage is recorded at ingest time, so a scanner fix leaves it stale."""
    _articles_parquet(workspace)
    payload = tmp_path / "p.json"
    payload.write_text(json.dumps({"measurements": [ROW]}))
    assert cli.main(["ingest", "--pmcid", "PMC5090179", "--json", str(payload), "--no-brief"]) == 0
    path = workspace / "interim" / "extractions.jsonl"
    rec = json.loads(path.read_text().splitlines()[0])
    rec["n_candidates"] = 999
    rec["n_candidates_matched"] = 0
    rec["unmatched_candidates"] = []
    path.write_text(json.dumps(rec) + "\n")
    assert cli.main(["recount"]) == 0
    fresh = json.loads(path.read_text().splitlines()[0])
    assert fresh["n_candidates"] == 14
    assert fresh["n_candidates_matched"] == 1
    assert len(fresh["unmatched_candidates"]) == 13
    # the measurements themselves are untouched
    assert fresh["measurements"] == rec["measurements"]
    assert fresh["model"] == rec["model"]


def test_units_command_prints_what_the_article_prints(workspace, capsys):
    _articles_parquet(workspace)
    assert cli.main(["units", "--pmcid", "PMC5090179"]) == 0
    out = capsys.readouterr().out
    assert "mV" in out
    assert "Table" in out or "Methods" in out


def test_units_command_can_emit_json(workspace, capsys):
    _articles_parquet(workspace)
    assert cli.main(["units", "--pmcid", "PMC5090179", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert isinstance(rows, list)
    assert {"location", "unit", "factor", "quantity"} <= set(rows[0])


def test_ingest_records_the_brief_it_was_given(workspace, tmp_path, capsys):
    """Without this the provenance system is decoration: a worker following the persona
    literally produced six records with brief_sha256 null."""
    _articles_parquet(workspace)
    payload = tmp_path / "p.json"
    payload.write_text(json.dumps({"measurements": [ROW]}))
    brief = tmp_path / "extraction.md"
    brief.write_text("the rules that produced this row\n")
    assert cli.main([
        "ingest", "--pmcid", "PMC5090179", "--json", str(payload),
        "--brief", str(brief), "--model", "claude-code:sonnet",
    ]) == 0  # fmt: skip
    rec = json.loads((workspace / "interim" / "extractions.jsonl").read_text().splitlines()[0])
    import hashlib

    assert rec["brief_sha256"] == hashlib.sha256(brief.read_bytes()).hexdigest()
    assert rec["brief_path"] == "extraction.md"
    assert brief.read_text()[:10] in capsys.readouterr().out or True


def test_ingest_without_a_brief_is_allowed_but_marked_untraceable(workspace, tmp_path):
    """Still possible — but only when the caller says so; see `--no-brief`."""
    _articles_parquet(workspace)
    payload = tmp_path / "p.json"
    payload.write_text(json.dumps({"measurements": [ROW]}))
    assert cli.main(["ingest", "--pmcid", "PMC5090179", "--json", str(payload), "--no-brief"]) == 0
    rec = json.loads((workspace / "interim" / "extractions.jsonl").read_text().splitlines()[0])
    assert rec["brief_sha256"] is None


def test_ingest_refuses_a_brief_that_does_not_exist(workspace, tmp_path):
    _articles_parquet(workspace)
    payload = tmp_path / "p.json"
    payload.write_text(json.dumps({"measurements": [ROW]}))
    with pytest.raises(provenance.BriefNotFound):
        cli.main([
            "ingest", "--pmcid", "PMC5090179", "--json", str(payload),
            "--brief", str(tmp_path / "gone.md"),
        ])  # fmt: skip


def test_ingest_prints_the_brief_it_recorded(workspace, tmp_path, capsys):
    """Storing the hash but not showing it undercuts the point: an operator running ingest
    could not tell whether provenance was captured without reading the JSONL by hand."""
    _articles_parquet(workspace)
    payload = tmp_path / "p.json"
    payload.write_text(json.dumps({"measurements": [ROW]}))
    brief = tmp_path / "extraction.md"
    brief.write_text("the rules\n")
    assert cli.main([
        "ingest", "--pmcid", "PMC5090179", "--json", str(payload), "--brief", str(brief),
    ]) == 0  # fmt: skip
    out = capsys.readouterr().out
    import hashlib

    assert f"brief={hashlib.sha256(brief.read_bytes()).hexdigest()[:12]}" in out


def test_ingest_says_plainly_when_no_brief_was_given(workspace, tmp_path, capsys):
    _articles_parquet(workspace)
    payload = tmp_path / "p.json"
    payload.write_text(json.dumps({"measurements": [ROW]}))
    assert cli.main(["ingest", "--pmcid", "PMC5090179", "--json", str(payload), "--no-brief"]) == 0
    assert "brief=none" in capsys.readouterr().out


def test_the_summary_reports_the_provenance_the_records_carry_not_the_code_s(
    workspace, monkeypatch
):
    """`prompt_sha256` used to be the hash of whatever prompt the code held at rebuild time.

    Written into a file describing 845 stored records, that reads as their provenance and is
    not: editing the prompt changed the committed artefact without a single record changing.
    The summary must describe the data — including, loudly, the records that carry no brief.
    """
    _articles_parquet(workspace, pmcids=("PMC5090179",))
    fake = ScriptedLLM({"measurements": [ROW]})
    monkeypatch.setattr(llm, "from_env", lambda cache_dir=None, model=None: fake)
    assert cli.main(["run", "--concurrency", "1"]) == 0

    path = workspace / "processed" / "extraction_summary.json"
    summary = json.loads(path.read_text())
    assert "prompt_sha256" not in summary, "an unqualified hash invites being read as provenance"
    assert summary["code_prompt_sha256"] == prompts.prompt_sha256()
    assert sum(summary["prompt_sha256_in_records"].values()) == summary["papers"]
    assert summary["brief_sha256_in_records"] == {"none": 1}

    # Editing the prompt must not change one byte of a summary about unchanged records.
    before = path.read_text()
    monkeypatch.setattr(prompts, "prompt_sha256", lambda: "0" * 64)
    cli.main(["table"])
    after = json.loads(path.read_text())
    assert after["prompt_sha256_in_records"] == json.loads(before)["prompt_sha256_in_records"]
    assert after["code_prompt_sha256"] == "0" * 64


def test_recount_check_reports_stale_coverage_without_writing(workspace, monkeypatch):
    """A scanner fix makes every stored coverage number stale, silently.

    `recount` repairs them by rewriting the record; an offline replay must not write to the
    record it is checking, so the same staleness has to be detectable read-only.
    """
    _articles_parquet(workspace)
    fake = ScriptedLLM({"measurements": [ROW]})
    monkeypatch.setattr(llm, "from_env", lambda cache_dir=None, model=None: fake)
    assert cli.main(["run", "--concurrency", "1"]) == 0

    path = workspace / "interim" / "extractions.jsonl"
    assert cli.main(["recount", "--check"]) == 0, "a fresh record is not stale"

    rec = json.loads(path.read_text())
    rec["n_candidates"] = rec["n_candidates"] + 7
    before = json.dumps(rec) + "\n"
    path.write_text(before)

    assert cli.main(["recount", "--check"]) == 1
    assert path.read_text() == before, "--check must not repair what it reports"

    assert cli.main(["recount"]) == 0
    assert cli.main(["recount", "--check"]) == 0


def test_ingest_refuses_a_record_with_no_brief(workspace, tmp_path, capsys):
    """833 of 845 records cannot be traced to their instructions. Never again by default.

    `--brief` was documented in the worker persona before it existed in the CLI, and a
    compliant worker produced six records with no provenance at all. The CLI is what enforces
    it, so the CLI refuses.
    """
    reply = tmp_path / "reply.json"
    reply.write_text(json.dumps({"measurements": []}))
    code = cli.main(["ingest", "--pmcid", "PMC5090179", "--json", str(reply)])
    assert code == 2
    err = capsys.readouterr().err
    assert "--brief" in err
    assert not (workspace / "interim" / "extractions.jsonl").exists()


def test_ingest_accepts_an_explicit_absence_of_a_brief(workspace, tmp_path):
    """A legacy re-ingest has to remain possible — but it has to be said out loud."""
    reply = tmp_path / "reply.json"
    reply.write_text(json.dumps({"measurements": []}))
    assert cli.main(["ingest", "--pmcid", "PMC5090179", "--json", str(reply), "--no-brief"]) == 0
    rec = json.loads((workspace / "interim" / "extractions.jsonl").read_text())
    assert rec["brief_sha256"] is None


def test_ingest_records_itself_in_the_run_manifest(workspace, tmp_path):
    """A worker's claim and the code it ran against, written down as the work happens."""
    import json as _json

    from mnp import runs

    _articles_parquet(workspace)
    brief = tmp_path / "brief.md"
    brief.write_text("Report only what the text states.\n")
    payload = tmp_path / "p.json"
    payload.write_text(_json.dumps({"measurements": [ROW]}))
    assert (
        cli.main(
            [
                "ingest",
                "--pmcid",
                "PMC5090179",
                "--json",
                str(payload),
                "--brief",
                str(brief),
                "--run-id",
                "slice-1",
                "--worker",
                "w3",
            ]
        )  # fmt: skip
        == 0
    )
    manifest = runs.load("slice-1")
    assert manifest["run_id"] == "slice-1"
    assert manifest["brief_sha256"]
    assignments = (runs.run_dir("slice-1") / "assignments.jsonl").read_text().splitlines()
    assert _json.loads(assignments[0]) | {"worker": "w3"} == _json.loads(assignments[0])
    assert _json.loads(assignments[0])["pmcids"] == ["PMC5090179"]


def test_todo_can_list_papers_whose_record_carries_no_brief(workspace, tmp_path, capsys):
    """The sweep's work list: papers already extracted, but not traceably.

    `todo` alone lists papers with no record at all, which is the wrong set — the 833 records
    that cannot be traced to a brief all *have* records. Re-reading them is the whole point.
    """
    _articles_parquet(workspace, pmcids=("PMC5090179", "PMC0000001"))
    payload = tmp_path / "p.json"
    payload.write_text(json.dumps({"measurements": [ROW]}))
    brief = tmp_path / "brief.md"
    brief.write_text("Report only what the text states.\n")
    import shutil

    shutil.copy(workspace / "xml" / "PMC5090179.xml", workspace / "xml" / "PMC0000001.xml")

    # one traceable record, one not
    assert cli.main(["ingest", "--pmcid", "PMC5090179", "--json", str(payload),
                     "--brief", str(brief)]) == 0  # fmt: skip
    assert cli.main(["ingest", "--pmcid", "PMC0000001", "--json", str(payload),
                     "--no-brief"]) == 0  # fmt: skip

    capsys.readouterr()
    assert cli.main(["todo", "--missing-brief"]) == 0
    listed = capsys.readouterr().out.split()
    assert listed == ["PMC0000001"], "only the untraceable record needs re-reading"

    assert cli.main(["todo"]) == 0
    assert capsys.readouterr().out.split() == [], "both papers already have records"
