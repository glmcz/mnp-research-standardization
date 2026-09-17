"""The vanilla dataset release: the two serialisations must agree, and the card must not lie.

The card is the deliverable that can rot silently. A hardcoded statistic looks right on the
day it is written and is wrong at the next rebuild, so the tests that matter here mutate the
inputs and demand that the card moves with them.
"""

import json

import pandas as pd
import pytest

from mnp import config
from mnp.report import release


def _table() -> pd.DataFrame:
    """Six rows over three papers: one fully conditioned, one without a printed number."""
    rows = []

    def row(pmcid, row_id, **over):
        base = dict(
            pmcid=pmcid, doi=f"10.0/{pmcid}", year=2020, journal="J", row_id=row_id,
            material="polystyrene", quantity="zeta_potential", value=-30.0, value_text=None,
            unit="mV", medium_text="10 mM NaCl", ionic_strength_mM=10.0, pH=7.0,
            temperature_C=25.0, instrument="Zetasizer", medium_reported=True,
            ionic_strength_reported=True, pH_reported=True, temperature_reported=True,
            instrument_reported=True, conditions_complete=True, evidence_quote="q",
            evidence_location="Methods", evidence_verified=True, flags="",
            model="claude-code:opus", prompt_sha256="a" * 64,
        )  # fmt: skip
        base.update(over)
        return base

    rows.append(row("PMCA", "PMCA-r1"))
    rows.append(row("PMCA", "PMCA-r2", material="polyethylene"))
    rows.append(row("PMCB", "PMCB-r1", ionic_strength_reported=False, ionic_strength_mM=None,
                    conditions_complete=False, prompt_sha256="b" * 64))  # fmt: skip
    rows.append(row("PMCB", "PMCB-r2", pH_reported=False, pH=None, conditions_complete=False,
                    value=None, value_text="not printed", model="claude-code:sonnet"))  # fmt: skip
    rows.append(row("PMCC", "PMCC-r1", temperature_reported=False, temperature_C=None,
                    conditions_complete=False))  # fmt: skip
    rows.append(row("PMCC", "PMCC-r2", instrument_reported=False, instrument=None,
                    medium_reported=False, medium_text=None,
                    conditions_complete=False))  # fmt: skip
    return pd.DataFrame(rows)


def _stats() -> dict:
    """The shape d1 writes, with the fields the card reads."""
    return {
        "n_papers": 3,
        "n_papers_with_a_printed_number": 3,
        "n_papers_measured_but_no_number_printed": 0,
        "n_rows_verified": 6,
        "n_rows_total": 6,
        "n_papers_with_unverified_only": 0,
        "denominators": {"papers_with_verified_zeta": 3, "oa_records": 40, "all_hits": 55},
        "missing": [
            {"condition": "medium", "label": "Dispersion medium", "k_missing": 1, "n": 3,
             "fraction": 1 / 3, "wilson_lo": 0.06, "wilson_hi": 0.79},
            {"condition": "any", "label": "Any condition", "k_missing": 2, "n": 3,
             "fraction": 2 / 3, "wilson_lo": 0.21, "wilson_hi": 0.94},
        ],  # fmt: skip
        "complete_fraction": 1 / 3,
        "text_availability": {"fetched": 44, "with_retrievable_text": 42,
                              "no_retrievable_text": 2, "pmcids_without_text": ["X", "Y"]},
    }  # fmt: skip


def _gold() -> pd.DataFrame:
    return pd.DataFrame(
        {"pmcid": ["PMCA", "PMCA", "PMCB"], "row_id": ["r1", "r2", "r3"],
         "annotator": ["claude-opus-gold"] * 3}
    )  # fmt: skip


def _articles() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "pmcid": ["PMCA", "PMCB", "PMCC", "PMCD"],
            "license": [
                "Open Access, https://creativecommons.org/licenses/by/4.0/ applies.",
                "https://creativecommons.org/licenses/by-nc-nd/4.0/ non-commercial only.",
                "All rights reserved by the publisher.",
                None,
            ],
        }
    )


def _build(out_dir, table=None, stats=None, **kw):
    return release.build(
        table if table is not None else _table(),
        stats if stats is not None else _stats(),
        out_dir,
        articles=kw.pop("articles", _articles()),
        gold=kw.pop("gold", _gold()),
        **kw,
    )


def test_build_writes_the_four_release_files(tmp_path):
    written = _build(tmp_path / "release")
    assert {p.name for p in written} == {
        "dataset.parquet",
        "dataset.jsonl",
        "schema.json",
        "DATASET_CARD.md",
    }
    for p in written:
        assert p.is_file() and p.stat().st_size > 0


def test_parquet_and_jsonl_hold_exactly_the_rows_of_the_source_csv(tmp_path):
    """The release is the table, not a filtered view of it: no row may go missing."""
    source = tmp_path / "d1_zeta_table.csv"
    _table().to_csv(source, index=False)
    csv_rows = len(pd.read_csv(source))

    out = tmp_path / "release"
    _build(out, table=pd.read_csv(source))
    assert len(pd.read_parquet(out / "dataset.parquet")) == csv_rows
    lines = (out / "dataset.jsonl").read_text().splitlines()
    assert len(lines) == csv_rows


def test_parquet_and_jsonl_carry_identical_content(tmp_path):
    out = tmp_path / "release"
    _build(out)
    from_parquet = pd.read_parquet(out / "dataset.parquet")
    from_jsonl = pd.DataFrame(
        [json.loads(line) for line in (out / "dataset.jsonl").read_text().splitlines()]
    )
    assert list(from_jsonl.columns) == list(from_parquet.columns)
    a = from_parquet.astype(object).where(from_parquet.notna(), None)
    b = from_jsonl.astype(object).where(from_jsonl.notna(), None)
    assert a.values.tolist() == b.values.tolist()


def test_jsonl_is_valid_json_with_no_nan_literals(tmp_path):
    """`json.dumps` emits a bare NaN by default, which no other JSON parser accepts.

    Grepping the text for "NaN" would not do: the medium of a real row is `5 mM NaNO3`.
    `parse_constant` is the only check that distinguishes a literal from a sodium salt.
    """
    out = tmp_path / "release"
    _build(out)

    def refuse(token):
        raise AssertionError(f"bare {token} in the JSONL — not valid JSON")

    lines = (out / "dataset.jsonl").read_text().splitlines()
    assert lines
    for line in lines:
        json.loads(line, parse_constant=refuse)


def test_the_card_headline_moves_when_the_table_moves(tmp_path):
    """3.3 % is computed from `conditions_complete`, not typed in.

    A card that keeps saying 33.3 % after every complete row has been flipped is a card
    whose numbers were written by hand.
    """
    honest = _build(tmp_path / "a")
    card = next(p for p in honest if p.name == "DATASET_CARD.md").read_text()
    headline = "| **fully conditioned rows** (`conditions_complete`) | **2 / 6 — 33.3 %** |"
    assert headline in card, "two of the six fixture rows are fully conditioned"

    flipped = _table()
    flipped["conditions_complete"] = False
    moved = _build(tmp_path / "b", table=flipped)
    card2 = next(p for p in moved if p.name == "DATASET_CARD.md").read_text()
    assert headline not in card2, "the headline was written by hand"
    assert "2 / 6 — 33.3 %" not in card2
    assert "0 / 6 — 0.0 %" in card2


def test_the_card_paper_numbers_come_from_the_stats_file(tmp_path):
    """The paper-level denominators are d1's, so a changed d1_stats.json must reach the card."""
    stats = _stats()
    honest = _build(tmp_path / "a", stats=stats)
    card = next(p for p in honest if p.name == "DATASET_CARD.md").read_text()
    headline = "| **papers omitting at least one of the five conditions** | **2 / 3 — 66.7 %** |"
    assert headline in card, "two of the three papers omit at least one condition"
    assert "| open-access records the query returned | 40 |" in card
    assert "| all hits, including paywalled | 55 |" in card

    moved = dict(stats)
    moved["missing"] = [
        dict(stats["missing"][0]),
        {**stats["missing"][1], "k_missing": 3, "fraction": 1.0},
    ]
    moved["denominators"] = {**stats["denominators"], "oa_records": 4242}
    written = _build(tmp_path / "b", stats=moved)
    card2 = next(p for p in written if p.name == "DATASET_CARD.md").read_text()
    assert headline not in card2, "the paper-level headline was written by hand"
    assert "2 / 3 — 66.7 %" not in card2
    assert "3 / 3 — 100.0 %" in card2
    assert "| open-access records the query returned | 4242 |" in card2


def test_a_stats_file_that_does_not_describe_this_table_is_refused(tmp_path):
    """The repo's recurring defect: a published table fitted from data it no longer matches."""
    stats = {**_stats(), "n_rows_total": 99}
    with pytest.raises(ValueError, match="99"):
        _build(tmp_path / "release", stats=stats)


def test_the_card_says_the_kappa_audit_is_outstanding(tmp_path):
    written = _build(tmp_path / "release")
    card = next(p for p in written if p.name == "DATASET_CARD.md").read_text()
    low = card.lower()
    assert "κ" in card
    assert "has not been" in low and "audit" in low
    assert "provisional" in low
    assert "audit_10.csv" in card
    assert "claude-opus-gold" in card


def test_the_card_says_the_licence_is_undecided(tmp_path):
    written = _build(tmp_path / "release")
    card = next(p for p in written if p.name == "DATASET_CARD.md").read_text()
    assert "UNRESOLVED" in card
    assert "open decision" in card.lower()
    # what travels and what does not
    assert "full text" in card.lower()


def test_the_card_states_absence_is_a_value(tmp_path):
    written = _build(tmp_path / "release")
    card = next(p for p in written if p.name == "DATASET_CARD.md").read_text()
    low = card.lower()
    assert "absence is a value, not a gap" in low
    assert "_reported" in card
    assert "0.0" in card and "never" in low


def test_the_card_states_the_single_database_limit(tmp_path):
    written = _build(tmp_path / "release")
    card = next(p for p in written if p.name == "DATASET_CARD.md").read_text()
    assert "Europe PMC" in card
    assert "OpenAlex" in card


def test_the_card_reports_the_coarse_prompt_provenance(tmp_path):
    written = _build(tmp_path / "release")
    card = next(p for p in written if p.name == "DATASET_CARD.md").read_text()
    assert "prompt_sha256" in card
    assert "2 distinct" in card


def test_the_schema_is_the_exported_one_not_a_second_copy(tmp_path):
    """One source of truth: the shipped schema must be byte-identical to `schema export`."""
    from mnp.schema import export

    written = _build(tmp_path / "release")
    shipped = next(p for p in written if p.name == "schema.json").read_text()
    reference = export.write_artefacts(tmp_path / "ref")
    canonical = next(p for p in reference if p.name.endswith(".schema.json")).read_text()
    assert shipped == canonical


def test_running_the_release_twice_is_byte_identical(tmp_path):
    """A published artefact that moves between two identical runs is not a published artefact."""
    from mnp.report import reproduce

    first = tmp_path / "one"
    second = tmp_path / "two"
    _build(first)
    _build(second)
    assert reproduce.hash_tree(first) == reproduce.hash_tree(second)


def test_the_release_is_rebuilt_in_place_without_stale_files(tmp_path):
    out = tmp_path / "release"
    _build(out)
    before = (out / "DATASET_CARD.md").read_text()
    _build(out)
    assert (out / "DATASET_CARD.md").read_text() == before


def test_a_new_column_cannot_vanish_from_the_card(tmp_path):
    """Every column is listed; one the card does not know about is named, not dropped."""
    table = _table()
    table["brief_sha256"] = "c" * 64
    stats = {**_stats()}
    written = release.build(table, stats, tmp_path / "release", articles=_articles(), gold=_gold())
    card = next(p for p in written if p.name == "DATASET_CARD.md").read_text()
    assert "brief_sha256" in card


def test_the_corpus_hash_is_read_from_the_archive(tmp_path):
    archive = tmp_path / "xml.tar.gz"
    archive.write_bytes(b"not really a tarball")
    manifest = tmp_path / "manifest.sha256"
    manifest.write_text("aa  PMC1.xml\nbb  PMC2.xml\n")
    written = _build(tmp_path / "release", corpus_archive=archive, corpus_manifest=manifest)
    card = next(p for p in written if p.name == "DATASET_CARD.md").read_text()
    from mnp.report import reproduce

    assert reproduce.sha256_file(archive) in card
    assert "2 XML files" in card
    assert str(archive.stat().st_size) in card


def test_a_missing_corpus_archive_is_stated_not_silently_dropped(tmp_path):
    written = _build(
        tmp_path / "release",
        corpus_archive=tmp_path / "absent.tar.gz",
        corpus_manifest=tmp_path / "absent.sha256",
    )
    card = next(p for p in written if p.name == "DATASET_CARD.md").read_text()
    assert "not present in this tree" in card


# --- the CLI ---------------------------------------------------------------------------


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_PROCESSED", tmp_path / "processed")
    monkeypatch.setattr(config, "EPMC_SEARCH_DIR", tmp_path / "search")
    monkeypatch.setattr(config, "DATA_RAW", tmp_path / "raw")
    monkeypatch.setattr(config, "DATA_INTERIM", tmp_path / "interim")
    monkeypatch.setattr(config, "ANNOTATION", tmp_path / "interim" / "annotation")
    return tmp_path


def test_release_without_d1_output_skips_cleanly(workspace, capsys):
    from mnp.report import __main__ as cli

    out = workspace / "out"
    assert cli.main(["release", "--out", str(out)]) == 0
    assert "d1_zeta_table.csv" in capsys.readouterr().err


def test_release_reads_the_d1_table_from_the_requested_root(workspace, capsys):
    from mnp.report import __main__ as cli

    out = workspace / "out"
    (out / "tables").mkdir(parents=True)
    _table().to_csv(out / "tables" / "d1_zeta_table.csv", index=False)
    (out / "tables" / "d1_stats.json").write_text(json.dumps(_stats()))

    assert cli.main(["release", "--out", str(out)]) == 0
    assert (out / "release" / "dataset.parquet").is_file()
    assert (out / "release" / "dataset.jsonl").is_file()
    assert (out / "release" / "schema.json").is_file()
    assert (out / "release" / "DATASET_CARD.md").is_file()
    assert capsys.readouterr().out.count("release: ") == 4


def test_release_is_part_of_all(workspace):
    from mnp.report import __main__ as cli

    assert "release" in cli.RUNNERS


# --- the artefacts this repository actually ships --------------------------------------


@pytest.fixture
def committed():
    table = config.ROOT / "out" / "tables" / "d1_zeta_table.csv"
    stats = config.ROOT / "out" / "tables" / "d1_stats.json"
    if not (table.is_file() and stats.is_file()):
        pytest.skip("no committed d1 artefacts in this tree")
    return pd.read_csv(table), json.loads(stats.read_text())


def test_the_shipped_card_matches_the_committed_stats(tmp_path, committed):
    """The card built from this repository's own artefacts, checked against them.

    This is the test that catches a stale literal in the shipped card: it reads
    `d1_stats.json` itself and demands the card agree with it.
    """
    table, stats = committed
    written = release.build(table, stats, tmp_path / "release")
    card = next(p for p in written if p.name == "DATASET_CARD.md").read_text()

    def kn(k, n):
        return f"{k} / {n} — {100 * k / n:.1f} %"

    any_missing = next(m for m in stats["missing"] if m["condition"] == "any")
    assert kn(any_missing["k_missing"], any_missing["n"]) in card
    assert f"| papers with at least one verified measurement | {stats['n_papers']} |" in card
    oa = stats["denominators"]["oa_records"]
    assert f"| open-access records the query returned | {oa} |" in card
    assert f"| all hits, including paywalled | {stats['denominators']['all_hits']} |" in card
    assert f"| papers | {table['pmcid'].nunique()} |" in card
    assert kn(int(table["conditions_complete"].sum()), len(table)) in card
    assert kn(int(table["evidence_verified"].sum()), len(table)) in card
    assert f"| distinct `material` values | {table['material'].nunique()} |" in card
    assert f"Only {table['prompt_sha256'].nunique()} distinct" in card
