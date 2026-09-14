"""Every row must trace to the instructions that produced it.

The first corpus run stored one `prompt_sha256` for all 845 records — the CLI's own system
prompt — while the brief that actually shaped each judgement lived in a session scratchpad
and was deleted. These tests pin the fix.
"""

import hashlib
import json

import pytest

from mnp.extract import provenance


def test_a_brief_is_identified_by_the_hash_of_its_content(tmp_path):
    b = tmp_path / "extraction.md"
    b.write_text("Report only what the text states.\n")
    ref = provenance.load_brief(b)
    assert ref.sha256 == hashlib.sha256(b.read_bytes()).hexdigest()
    assert ref.path == "extraction.md"
    assert ref.text.startswith("Report only")


def test_the_same_brief_hashes_the_same_from_any_directory(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    for d in ("a", "b"):
        (tmp_path / d / "extraction.md").write_text("same rules\n")
    assert (
        provenance.load_brief(tmp_path / "a" / "extraction.md").sha256
        == provenance.load_brief(tmp_path / "b" / "extraction.md").sha256
    )


def test_editing_a_brief_changes_its_hash(tmp_path):
    b = tmp_path / "extraction.md"
    b.write_text("rule one\n")
    first = provenance.load_brief(b).sha256
    b.write_text("rule one\nrule two\n")
    assert provenance.load_brief(b).sha256 != first


def test_a_missing_brief_is_an_error_not_a_silent_none(tmp_path):
    with pytest.raises(provenance.BriefNotFound) as exc:
        provenance.load_brief(tmp_path / "nope.md")
    assert "nope.md" in str(exc.value)


def test_the_repository_briefs_are_discoverable():
    briefs = provenance.available_briefs()
    assert briefs, "docs/briefs/ should hold at least one brief"
    assert all(b.sha256 and b.path.endswith(".md") for b in briefs)


def test_a_record_carries_the_brief_it_was_produced_under(tmp_path):
    from mnp.extract.zeta import ExtractionRecord

    b = tmp_path / "extraction.md"
    b.write_text("the rules\n")
    ref = provenance.load_brief(b)
    rec = ExtractionRecord(
        pmcid="PMC1", doi=None, model="claude-code:sonnet", prompt_sha256="x",
        brief_path=ref.path, brief_sha256=ref.sha256,
    )  # fmt: skip
    back = json.loads(rec.to_json())
    assert back["brief_sha256"] == ref.sha256
    assert back["brief_path"] == "extraction.md"


def test_a_record_without_a_brief_says_so_rather_than_pretending(tmp_path):
    from mnp.extract.zeta import ExtractionRecord

    rec = ExtractionRecord(pmcid="PMC1", doi=None, model="m", prompt_sha256="x")
    assert json.loads(rec.to_json())["brief_sha256"] is None


def test_audit_reports_which_records_cannot_be_traced(tmp_path):
    path = tmp_path / "extractions.jsonl"
    path.write_text(
        json.dumps({"pmcid": "PMC1", "brief_sha256": "abc", "model": "m"})
        + "\n"
        + json.dumps({"pmcid": "PMC2", "brief_sha256": None, "model": "m"})
        + "\n"
        + json.dumps({"pmcid": "PMC3", "brief_sha256": "abc", "model": "m"})
        + "\n"
    )
    report = provenance.audit(path)
    assert report["records"] == 3
    assert report["untraceable"] == 1
    assert report["untraceable_pmcids"] == ["PMC2"]
    assert report["briefs"] == {"abc": 2}
