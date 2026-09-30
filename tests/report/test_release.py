"""The vanilla dataset release: the two serialisations must agree, and the card must not lie.

The card is the deliverable that can rot silently. A hardcoded statistic looks right on the
day it is written and is wrong at the next rebuild, so the tests that matter here mutate the
inputs and demand that the card moves with them.
"""

import hashlib
import json
import re

import pandas as pd
import pytest

from mnp import config
from mnp.corpus import jats, lines
from mnp.corpus.licence import Licence
from mnp.report import quotes, release, scope

# Each fixture row's quote, verbatim in its fixture paper. PMCC-r1 joins two passages.
QUOTES = {
    "PMCA-r1": "The zeta potential of PS beads was -30.0 mV in 10 mM NaCl at pH 7.0 and 25 °C.",
    "PMCA-r2": "PE fragments measured -30.0 mV under the same conditions, by Zetasizer.",
    "PMCB-r1": "Zeta potential of the nanoplastics in river water was -30.0 mV at pH 7.0.",
    "PMCB-r2": "Values were measured but not printed for the aged particles in tap water.",
    "PMCC-r1": "The zeta potential of the PMMA particles was -30.0 mV in 10 mM NaCl. || "
    "Surface charge was measured with a Zetasizer Nano ZS in triplicate.",
    "PMCC-r2": "Surface charge of PVC reached -30.0 mV after ageing in the medium tested.",
}
# PMCA may be quoted; PMCB and PMCC may not.
LICENCES = {
    "PMCA": Licence("CC-BY", "url", "https://creativecommons.org/licenses/by/4.0/"),
    "PMCB": Licence("CC-BY-NC-ND", "url", "https://creativecommons.org/licenses/by-nc-nd/4.0/"),
    "PMCC": Licence("none", "no statement", ""),
}


def _methods(pmcid: str) -> str:
    passages = [
        part.strip()
        for row_id, quote in QUOTES.items()
        if row_id.startswith(pmcid)
        for part in quote.split("||")
    ]
    return "\n".join(["Particles were purchased from a commercial supplier.", *passages])


def _documents(pmcid: str) -> lines.LinedDoc | None:
    article = jats.Article(
        pmcid=pmcid, doi=None, title=None, year=None, journal=None, license=None,
        methods_text=_methods(pmcid), methods_source="title",
    )  # fmt: skip
    return lines.build_lines(article)


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
        base["evidence_quote"] = QUOTES[row_id]
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


def _build(out_dir, table=None, stats=None, **kw):
    return release.build(
        table if table is not None else _table(),
        stats if stats is not None else _stats(),
        out_dir,
        licences=kw.pop("licences", LICENCES),
        documents=kw.pop("documents", _documents),
        gold=kw.pop("gold", _gold()),
        **kw,
    )


def _card(written) -> str:
    return next(p for p in written if p.name == "DATASET_CARD.md").read_text()


def test_build_writes_the_five_release_files(tmp_path):
    written = _build(tmp_path / "release")
    assert {p.name for p in written} == {
        "dataset.parquet",
        "dataset.jsonl",
        "schema.json",
        "DATASET_CARD.md",
        "LICENSE",
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


def test_the_card_states_the_decided_licence(tmp_path):
    card = _card(_build(tmp_path / "release"))
    assert "UNRESOLVED" not in card
    assert "CC BY 4.0" in card
    assert "https://creativecommons.org/licenses/by/4.0/" in card
    low = card.lower()
    assert "not legal advice" in low
    assert "python -m mnp.report rehydrate" in card
    # what is a fact, what is a quote, and that the sources keep their own licences
    assert "facts" in low and "verbatim" in low
    assert "own licence" in low


def _licence_rows(card: str) -> dict[str, tuple[int, int, int, int]]:
    """The card's per-licence table, parsed back: code -> (papers, rows, shipped, withheld)."""
    out = {}
    for line in card.splitlines():
        m = re.match(r"^\| `([^`]+)` \| (\d+) \| (\d+) \| (\d+) \| (\d+) \|$", line)
        if m:
            out[m.group(1)] = tuple(int(x) for x in m.groups()[1:])
    return out


def _counts(table: pd.DataFrame) -> dict[str, tuple[int, int, int, int]]:
    out = {}
    for code, g in table.groupby("source_licence"):
        withheld = int(g["quote_withheld"].sum())
        out[code] = (g["pmcid"].nunique(), len(g), len(g) - withheld, withheld)
    return out


def test_the_card_licence_table_equals_the_tables_own_counts(tmp_path):
    out = tmp_path / "release"
    card = _card(_build(out))
    table = pd.read_parquet(out / "dataset.parquet")
    assert _licence_rows(card) == _counts(table)
    assert _licence_rows(card) == {
        "CC-BY": (1, 2, 2, 0),
        "CC-BY-NC-ND": (1, 2, 0, 2),
        "none": (1, 2, 0, 2),
    }


def test_the_card_licence_table_moves_when_a_decision_moves(tmp_path):
    card = _card(_build(tmp_path / "a"))
    tighter = {**LICENCES, "PMCA": Licence("CC-BY-NC", "wording", "Attribution-NonCommercial")}
    moved = _card(_build(tmp_path / "b", licences=tighter))
    assert _licence_rows(card) != _licence_rows(moved)
    assert _licence_rows(moved)["CC-BY-NC"] == (1, 2, 0, 2)


def test_withheld_rows_ship_an_address_and_a_hash_but_no_quote(tmp_path):
    out = tmp_path / "release"
    _build(out)
    table = pd.read_parquet(out / "dataset.parquet").set_index("row_id")
    for row_id, quote in QUOTES.items():
        row = table.loc[row_id]
        assert row["evidence_quote_sha256"] == hashlib.sha256(quote.encode()).hexdigest()
        if row_id.startswith("PMCA"):
            assert not row["quote_withheld"] and row["source_licence"] == "CC-BY"
            assert row["evidence_quote"] == quote
            assert pd.isna(row["evidence_quote_spans"])
        else:
            assert row["quote_withheld"]
            assert pd.isna(row["evidence_quote"])
            pieces = json.loads(row["evidence_quote_spans"])
            assert quotes.restore(_documents(row_id.split("-")[0]), pieces) == quote


def test_no_withheld_quote_reaches_any_release_file(tmp_path):
    out = tmp_path / "release"
    _build(out)
    withheld = [q for row_id, q in QUOTES.items() if not row_id.startswith("PMCA")]
    parts = [p.strip() for q in withheld for p in q.split("||") if len(p.strip()) > 30]
    frame = pd.read_parquet(out / "dataset.parquet")
    decoded = "\n".join(str(v) for v in frame.to_numpy().ravel())
    for path in out.iterdir():
        text = path.read_bytes().decode("utf-8", errors="replace")
        for part in parts:
            assert part not in text, f"{path.name} carries a withheld passage"
            assert json.dumps(part)[1:-1] not in text, f"{path.name} carries it JSON-escaped"
    for part in parts:
        assert part not in decoded


def test_every_paper_needs_a_licence_decision(tmp_path):
    partial = {k: v for k, v in LICENCES.items() if k != "PMCC"}
    with pytest.raises(ValueError, match="PMCC"):
        _build(tmp_path / "release", licences=partial)


def test_a_withheld_quote_that_cannot_be_addressed_refuses_the_build(tmp_path):
    """Withheld and unrecoverable is a row with its evidence silently deleted."""

    def drifted(pmcid):
        doc = _documents(pmcid)
        if pmcid != "PMCB":
            return doc
        article = jats.Article(
            pmcid=pmcid, doi=None, title=None, year=None, journal=None, license=None,
            methods_text="A different paper altogether.", methods_source="title",
        )  # fmt: skip
        return lines.build_lines(article)

    with pytest.raises(ValueError, match="PMCB-r1"):
        _build(tmp_path / "release", documents=drifted)
    assert not (tmp_path / "release" / "dataset.parquet").exists()


def test_a_withheld_quote_without_its_source_refuses_the_build(tmp_path):
    with pytest.raises(ValueError, match="PMCC"):
        _build(tmp_path / "release", documents=lambda p: None if p == "PMCC" else _documents(p))


def test_the_licence_file_is_cc_by_4_for_this_dataset(tmp_path):
    written = _build(tmp_path / "release")
    text = next(p for p in written if p.name == "LICENSE").read_text()
    assert "Creative Commons Attribution 4.0 International" in text
    assert "https://creativecommons.org/licenses/by/4.0/" in text
    assert release.DATASET_NAME in text
    assert "Attribution" in text


def test_the_licence_names_its_author():
    text = release.licence_notice()
    assert '", by Martin Durak. Licensed under' in text
    assert "not yet named" not in text


def test_the_card_states_absence_is_a_value(tmp_path):
    written = _build(tmp_path / "release")
    card = next(p for p in written if p.name == "DATASET_CARD.md").read_text()
    low = card.lower()
    assert "absence is a value, not a gap" in low
    assert "_reported" in card
    assert "0.0" in card and "never" in low


def test_the_card_states_the_rules_that_clear_a_reading(tmp_path):
    written = _build(tmp_path / "release")
    card = next(p for p in written if p.name == "DATASET_CARD.md").read_text()
    assert "0 mM" in card and "ionic_strength_zero_not_reported` (0 rows)" in card
    assert "incubation" in card and "temperature_step_not_measurement` (0 rows)" in card
    assert "stored at 37" in card and "temperature_from_other_step` (0 rows)" in card


def test_the_card_states_the_single_database_limit(tmp_path):
    written = _build(tmp_path / "release")
    card = next(p for p in written if p.name == "DATASET_CARD.md").read_text()
    assert "Europe PMC" in card
    assert "OpenAlex" in card


def _origin() -> dict:
    """The shape `report origin` writes, with the fields the card reads."""
    envs = (
        "freshwater",
        "seawater",
        "wastewater",
        "soil",
        "sediment",
        "air_dust",
        "biota",
        "other",
    )
    affected = {
        "medium": 0,
        "ionic_strength": 0,
        "pH": 1,
        "temperature": 0,
        "instrument": 1,
        "complete": 0,
    }
    rest = {
        "medium": 2,
        "ionic_strength": 1,
        "pH": 2,
        "temperature": 1,
        "instrument": 2,
        "complete": 0,
    }
    return {
        "rows": 6,
        "papers": 3,
        "hand_corrected": {
            "origin": {"rows": {"commercial": 3, "lab_fabricated": 1, "environmental": 1,
                                "unclear": 1, "unanswered": 0}},
            "synthetic": {"rows": 4},
            "environment": {"rows": {e: int(e == "wastewater") for e in envs},
                            "papers": {e: int(e == "wastewater") for e in envs}},
            "environmental_rows": {"rows": 1, "papers": 1},
        },
        "lost_methods": {
            "papers": 3, "papers_affected": 1, "pmcids": ["PMCB"],
            "affected": {"papers": 1, "rows": 2,
                         "any_row": {k: {"n": v, "share": v / 1} for k, v in affected.items()}},
            "unaffected": {"papers": 2, "rows": 4,
                           "any_row": {k: {"n": v, "share": v / 2} for k, v in rest.items()}},
        },
    }  # fmt: skip


def test_the_card_states_where_the_particles_came_from(tmp_path):
    card = _card(_build(tmp_path / "release", origin=_origin()))
    limits = card.split("## Limits a citer needs to state")[1].split("\n## ")[0]
    assert "**The measured particles are synthetic.**" in limits
    assert "4 / 6 — 66.7 %" in limits
    assert "1 row, from 1 paper" in limits and "wastewater 1" in limits
    assert "air or dust: 0" in limits
    assert "`out/tables/sample_origin_stats.json`" in card


def test_the_card_states_the_parser_defect_as_a_limit_of_the_extraction(tmp_path):
    card = _card(_build(tmp_path / "release", origin=_origin()))
    limits = card.split("## Limits a citer needs to state")[1].split("\n## ")[0]
    item = next(line for line in limits.splitlines() if "supplementary-materials" in line)
    assert "1 of 3 papers" in item
    assert "temperature 0.0 % against 50.0 %" in item
    assert "biased downward" in item
    higher = _origin()
    higher["lost_methods"]["affected"]["any_row"]["temperature"] = {"n": 1, "share": 1.0}
    card = _card(_build(tmp_path / "again", origin=higher))
    assert "temperature 100.0 % against 50.0 %" in card and "biased downward" not in card


def test_the_card_opens_with_the_scope_block_under_its_title(tmp_path):
    card = _card(_build(tmp_path / "release", origin=_origin()))
    block = "\n".join(scope.block(_table(), _stats(), _origin()))
    assert card.startswith(f"# {release.DATASET_TITLE}\n\n{block}\n\n"), card[:600]
    assert "4 / 6" in block and "55 hits, 40 of them open access, 44 full texts fetched" in block


def test_a_card_without_the_origin_table_says_nothing_about_origin(tmp_path):
    card = _card(_build(tmp_path / "release"))
    assert "synthetic" not in card and "supplementary-materials" not in card


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
    written = _build(tmp_path / "release", table=table, stats=stats)
    assert "brief_sha256" in _card(written)


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
    monkeypatch.setattr(config, "EPMC_XML_DIR", tmp_path / "raw" / "epmc" / "xml")
    return tmp_path


def _vendor_fixture_xmls(xml_dir):
    """The three fixture papers as JATS, so the CLI reads licences and lines as it does live."""
    urls = {"PMCA": "by/4.0", "PMCB": "by-nc-nd/4.0"}
    xml_dir.mkdir(parents=True, exist_ok=True)
    for pmcid in ("PMCA", "PMCB", "PMCC"):
        permissions = (
            f'<permissions><license xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'xlink:href="https://creativecommons.org/licenses/{urls[pmcid]}/"><license-p>'
            "Open access.</license-p></license></permissions>"
            if pmcid in urls
            else ""
        )
        paras = "".join(f"<p>{line}</p>" for line in _methods(pmcid).split("\n"))
        (xml_dir / f"{pmcid}.xml").write_text(
            f'<?xml version="1.0"?><article><front><article-meta>{permissions}</article-meta>'
            f'</front><body><sec sec-type="methods"><title>Methods</title>{paras}</sec></body>'
            "</article>"
        )


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
    _vendor_fixture_xmls(config.EPMC_XML_DIR)

    assert cli.main(["release", "--out", str(out)]) == 0
    for name in ("dataset.parquet", "dataset.jsonl", "schema.json", "DATASET_CARD.md", "LICENSE"):
        assert (out / "release" / name).is_file()
    assert capsys.readouterr().out.count("release: ") == 5
    table = pd.read_parquet(out / "release" / "dataset.parquet").set_index("row_id")
    assert table.loc["PMCA-r1", "source_licence"] == "CC-BY"
    assert table.loc["PMCB-r1", "source_licence"] == "CC-BY-NC-ND"
    assert table.loc["PMCC-r1", "source_licence"] == "none"
    assert table["quote_withheld"].sum() == 4


def test_release_without_its_source_xmls_refuses_rather_than_guessing(workspace, capsys):
    from mnp.report import __main__ as cli

    out = workspace / "out"
    (out / "tables").mkdir(parents=True)
    _table().to_csv(out / "tables" / "d1_zeta_table.csv", index=False)
    (out / "tables" / "d1_stats.json").write_text(json.dumps(_stats()))

    assert cli.main(["release", "--out", str(out)]) == 0
    assert not (out / "release" / "dataset.parquet").exists()
    assert "corpus restore" in capsys.readouterr().err


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
    # The statistics do not depend on the licences, so every paper is let through here.
    permissive = {p: Licence("CC-BY", "url", "") for p in table["pmcid"].unique()}
    written = release.build(table, stats, tmp_path / "release", licences=permissive)
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


def test_the_shipped_card_licence_table_equals_the_shipped_table():
    """The published card against the published parquet beside it — no rebuild involved."""
    shipped = config.ROOT / "out" / "release"
    if not (shipped / "dataset.parquet").is_file():
        pytest.skip("no committed release here")
    table = pd.read_parquet(shipped / "dataset.parquet")
    card = (shipped / "DATASET_CARD.md").read_text()
    assert _licence_rows(card) == _counts(table)
    total = f"| **total** | {table['pmcid'].nunique()} | {len(table)} |"
    assert total in card


def test_the_shipped_card_states_the_committed_origin(tmp_path, committed):
    path = config.ROOT / "out" / "tables" / "sample_origin_stats.json"
    if not path.is_file():
        pytest.skip("no committed origin table in this tree")
    table, stats = committed
    origin = json.loads(path.read_text())
    permissive = {p: Licence("CC-BY", "url", "") for p in table["pmcid"].unique()}
    written = release.build(table, stats, tmp_path / "release", licences=permissive, origin=origin)
    card = _card(written)
    h, n = origin["hand_corrected"], origin["rows"]
    k = h["synthetic"]["rows"]
    assert f"{k} / {n} — {100 * k / n:.1f} %" in card
    lm = origin["lost_methods"]
    assert f"{lm['papers_affected']} of {lm['papers']} papers" in card
    block = "\n".join(scope.block(table, stats, origin))
    assert card.startswith(f"# {release.DATASET_TITLE}\n\n{block}\n\n")
