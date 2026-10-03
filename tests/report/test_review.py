"""`report review` writes out/review/: REVIEW.md, a guide for checking the dataset by hand, and
five CSV worksheets a spreadsheet can recompute. These tests build into a scratch root seeded with
copies of the committed table, stats and release, never into the real `out/`.

What they pin is the promise the guide makes: every number in it comes out of the repo's own code
at build time. So the worksheets are held against the modules they claim to reproduce
(`resample`, `harmonise`, `comparability`), the counts in REVIEW.md against the worksheets, and
the audit sample against the licence decision it has to respect.
"""

from __future__ import annotations

import json
import math
import re
import shutil
from pathlib import Path

import pandas as pd
import pytest

from mnp import config
from mnp.demo import harmonise, resample
from mnp.eval import comparability as comp
from mnp.report import review, scope

HEADINGS = (
    "## 1. How to use this guide",
    "## 2. Where the dataset comes from",
    "## 3. Every column",
    "## 4. The five parameters",
    "## 5. Every formula",
    "## 6. What the dataset proves, and what it does not",
    "## 7. How to review it yourself, step by step",
    "## 8. Open issues and decisions",
)

WORKSHEETS = (
    "conditions_per_paper.csv",
    "icc_worksheet.csv",
    "harmonised_all_rows.csv",
    "comparability_worked_pairs.csv",
    "audit_sample.csv",
)

FLAGS = (
    "medium_reported",
    "ionic_strength_reported",
    "pH_reported",
    "temperature_reported",
    "instrument_reported",
)


def _seed_root(root: Path) -> Path:
    (root / "tables").mkdir(parents=True)
    (root / "release").mkdir(parents=True)
    for name in ("d1_zeta_table.csv", "d1_stats.json", "sample_origin_stats.json"):
        shutil.copyfile(config.OUT_TABLES / name, root / "tables" / name)
    shutil.copyfile(
        config.OUT / "release" / "dataset.parquet", root / "release" / "dataset.parquet"
    )
    return root


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    root = _seed_root(tmp_path_factory.mktemp("review-build"))
    review.build(root)
    return root / "review"


@pytest.fixture(scope="module")
def guide(built: Path) -> str:
    return (built / "REVIEW.md").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def origin() -> dict:
    return json.loads((config.OUT_TABLES / "sample_origin_stats.json").read_text())


def _part(text: str, start: str, *ends: str) -> str:
    """The text from `start` up to the first of `ends` after it."""
    assert start in text, start
    rest = text.split(start, 1)[1]
    cut = min((rest.find(e) for e in ends if e in rest), default=len(rest))
    return rest[:cut]


def _kn(k: int, n: int) -> str:
    return f"{k:,} / {n:,} ({100 * k / n:.1f} %)".replace(",", " ")


@pytest.fixture(scope="module")
def table() -> pd.DataFrame:
    return pd.read_csv(config.OUT_TABLES / "d1_zeta_table.csv")


def _sheet(built: Path, name: str) -> pd.DataFrame:
    return pd.read_csv(built / name, keep_default_na=False, na_values=[""])


def test_all_eight_sections_are_present_in_order(guide: str):
    positions = [guide.find(heading) for heading in HEADINGS]
    assert all(p >= 0 for p in positions), [
        h for h, p in zip(HEADINGS, positions, strict=True) if p < 0
    ]
    assert positions == sorted(positions)


@pytest.mark.parametrize("name", WORKSHEETS)
def test_every_worksheet_exists_with_its_documented_columns(built: Path, guide: str, name: str):
    path = built / name
    assert path.is_file(), name
    header = pd.read_csv(path, nrows=0).columns.tolist()
    assert header == list(review.COLUMNS[name])
    assert f"`{name}`" in guide
    undocumented = [c for c in header if f"`{c}`" not in guide]
    assert not undocumented, f"{name}: columns never explained in REVIEW.md: {undocumented}"


def test_conditions_complete_is_the_and_of_the_five_flags_on_every_row(built: Path, table):
    rows = _sheet(built, "harmonised_all_rows.csv")
    assert len(rows) == len(table)
    assert rows["row_id"].tolist() == table["row_id"].tolist()
    anded = rows[list(FLAGS)].astype(bool).all(axis=1)
    assert (rows["conditions_complete"].astype(bool) == anded).all()
    assert (rows["conditions_complete"].astype(bool) == table["conditions_complete"]).all()


def test_per_paper_counts_add_up_to_the_table(built: Path, table):
    papers = _sheet(built, "conditions_per_paper.csv")
    assert len(papers) == table["pmcid"].nunique()
    assert papers["n_rows"].sum() == len(table)
    for metric in (*FLAGS, "conditions_complete"):
        assert papers[f"{metric}_rows"].sum() == int(table[metric].sum()), metric
        share = papers[f"{metric}_rows"] / papers["n_rows"]
        assert (share - papers[f"{metric}_share"]).abs().max() < 1e-9, metric


def test_icc_summary_equals_the_resample_module(built: Path, guide: str, table):
    summary = {s.metric: s for s in review.icc_summary(table)}
    for est in resample.estimates(table):
        s = summary[est.metric]
        assert s.anova.icc == pytest.approx(est.icc, abs=1e-12)
        assert s.anova.deff == pytest.approx(est.deff, abs=1e-12)
        assert s.n_eff == pytest.approx(est.n_eff, abs=1e-9)
        assert f"{est.icc:.4f}" in guide, est.metric
        assert f"{est.deff:.4f}" in guide, est.metric
        assert f"{est.n_eff:.1f}" in guide, est.metric
    sheet = _sheet(built, "icc_worksheet.csv")
    assert sheet["n_i"].sum() == len(table)
    assert len(sheet) == table["pmcid"].nunique()
    for metric in resample.METRICS:
        assert sheet[f"{metric}_succ"].sum() == int(table[metric].sum())


def test_icc_recomputed_from_the_worksheet_alone_matches(built: Path, table):
    """What Martin will do in a spreadsheet: only n_i and the successes, nothing imported."""
    sheet = _sheet(built, "icc_worksheet.csv")
    n_i = sheet["n_i"].astype(float)
    big_n, k = n_i.sum(), len(n_i)
    for est in resample.estimates(table):
        succ = sheet[f"{est.metric}_succ"].astype(float)
        p = succ / n_i
        pbar = succ.sum() / big_n
        msb = (n_i * (p - pbar) ** 2).sum() / (k - 1)
        msw = (n_i * p * (1 - p)).sum() / (big_n - k)
        m0 = (big_n - (n_i**2).sum() / big_n) / (k - 1)
        icc = (msb - msw) / (msb + (m0 - 1) * msw)
        assert icc == pytest.approx(est.icc, rel=1e-9), est.metric


def test_harmonised_rows_agree_with_harmonise_on_a_sample(built: Path, table):
    rows = _sheet(built, "harmonised_all_rows.csv").set_index("row_id")
    records = {r["row_id"]: r for r in table.to_dict(orient="records")}
    sample = table["row_id"].sample(n=80, random_state=7).tolist()
    for row_id in sample:
        record = records[row_id]
        want = harmonise.harmonise(record, harmonise.models_named(record["pmcid"]))
        got = rows.loc[row_id]
        assert got["why"] == want.why, row_id
        for field in ("point", "low", "high", "kappa_a"):
            expected = getattr(want, field)
            value = got[field if field != "kappa_a" else "kappa_a"]
            if expected is None:
                assert pd.isna(value), (row_id, field)
            else:
                assert float(value) == pytest.approx(expected, rel=1e-9), (row_id, field)


def test_harmonisation_counts_in_the_guide_match_the_worksheet(built: Path, guide: str):
    rows = _sheet(built, "harmonised_all_rows.csv")
    counts = rows["result"].value_counts().to_dict()
    assert set(counts) <= {"point", "interval", "none"}
    for result in ("point", "interval", "none"):
        assert f"| {result} | {counts.get(result, 0)} |" in guide, result
    point = rows["point"].notna()
    interval = rows["low"].notna() & rows["high"].notna()
    assert (point == (rows["result"] == "point")).all()
    assert (interval == (rows["result"] == "interval")).all()
    assert not (point & interval).any()


def test_the_release_carries_no_harmonised_value(guide: str):
    release = pd.read_parquet(config.OUT / "release" / "dataset.parquet")
    assert not [c for c in release.columns if "harmon" in c or c in ("point", "low", "high")]
    assert "does not contain harmonised values" in guide


def test_worked_pairs_have_the_verdicts_comparable_gives(built: Path, table):
    sheet = _sheet(built, "comparability_worked_pairs.csv")
    records = {r["row_id"]: r for r in table.to_dict(orient="records")}
    seen = set()
    for pair_id, group in sheet.groupby("pair_id"):
        a = comp.ZetaRow.from_mapping(records[group["row_id_a"].iloc[0]])
        b = comp.ZetaRow.from_mapping(records[group["row_id_b"].iloc[0]])
        verdict = comp.comparable(a, b)
        assert set(group["verdict"]) == {verdict.verdict.value}, pair_id
        codes = {c for c in group["blocker_code"].dropna() if c}
        assert codes == set(verdict.codes), pair_id
        seen.add(verdict.verdict.value)
    assert sheet["pair_id"].nunique() >= 3
    assert seen == {"comparable", "conditionally_comparable", "not_comparable"}


def test_audit_sample_is_deterministic_and_stratified(table):
    release = pd.read_parquet(config.OUT / "release" / "dataset.parquet")
    first = review.audit_sample(release)
    second = review.audit_sample(release)
    pd.testing.assert_frame_equal(first, second)
    assert len(first) == 20
    assert first["row_id"].is_unique
    other = review.audit_sample(release, seed=review.AUDIT_SEED + 1)
    assert other["row_id"].tolist() != first["row_id"].tolist()
    for flag in FLAGS:
        values = set(first[flag].astype(bool))
        assert values == {True, False}, flag
    for column in ("value_ok", "medium_ok", "ionic_strength_ok", "pH_ok", "temperature_ok",
                   "instrument_ok", "note"):  # fmt: skip
        assert column in first.columns
        assert first[column].fillna("").eq("").all()


def test_audit_sample_ships_no_text_from_a_withheld_source(built: Path, table):
    text = (built / "audit_sample.csv").read_text(encoding="utf-8")
    sheet = _sheet(built, "audit_sample.csv")
    withheld = sheet[sheet["quote_withheld"].astype(bool)]
    for column in ("evidence_quote", "evidence_line_text"):
        assert withheld[column].isna().all(), column
    shipped = sheet[~sheet["quote_withheld"].astype(bool)]
    assert shipped["evidence_line_text"].notna().all()
    assert set(sheet["source_licence"][sheet["quote_withheld"].astype(bool)]).isdisjoint(
        {"CC-BY", "CC0"}
    )
    release = pd.read_parquet(config.OUT / "release" / "dataset.parquet")
    hidden = set(release.loc[release["quote_withheld"], "row_id"])
    quotes = table.loc[table["row_id"].isin(hidden), "evidence_quote"].dropna()
    for quote in quotes:
        for passage in quote.split("||"):
            passage = passage.strip()
            if len(passage) >= 40:
                assert passage not in text, passage[:60]
    assert sheet["evidence_lines"].str.match(r"^PMC\d+:L\d+(;PMC\d+:L\d+)*$").all()


def test_rendering_twice_is_byte_identical(tmp_path_factory):
    first = _seed_root(tmp_path_factory.mktemp("review-a"))
    second = _seed_root(tmp_path_factory.mktemp("review-b"))
    review.build(first)
    review.build(second)
    names = sorted(p.name for p in (first / "review").iterdir())
    assert names == sorted(p.name for p in (second / "review").iterdir())
    assert names == sorted(["REVIEW.md", *WORKSHEETS])
    for name in names:
        assert (first / "review" / name).read_bytes() == (second / "review" / name).read_bytes()


def test_no_nan_or_none_leaks_into_the_guide(guide: str):
    assert not re.search(r"\bnan\b", guide, re.IGNORECASE)
    assert not re.search(r"\bNone\b", guide)
    assert "inf " not in guide.replace("infinite", "")


def test_the_key_numbers_are_the_modules_own(guide: str, table):
    census = comp.graded_census([comp.ZetaRow.from_mapping(r) for r in table.to_dict("records")])
    comparable = [s for s in census if s.verdict.verdict is comp.Comparability.comparable]
    assert f"**{len(comparable)}**" in guide
    scan = harmonise.scan(table)
    assert f"{scan.zeta_not_named} / {scan.zeta_papers}" in guide
    n_pairs = math.comb(len(table), 2)
    assert f"{n_pairs:,}".replace(",", " ") in guide


def test_review_is_a_runner_after_release():
    from mnp.report import __main__ as cli

    names = list(cli.RUNNERS)
    assert "review" in names
    assert names.index("review") > names.index("release")


def test_c11_states_where_the_particles_came_from(guide: str, origin: dict):
    h, n = origin["after_second_reading"], origin["rows"]
    c11 = _part(guide, "#### C11. The particles measured are almost all synthetic", "\n#### ",
                "\n### ")  # fmt: skip
    assert _kn(h["synthetic"]["rows"], n) in c11
    for name in ("commercial", "lab_fabricated", "environmental", "unclear"):
        assert _kn(h["origin"]["rows"][name], n) in c11, name
    env, where = h["environmental_rows"], h["environment"]
    assert f"from {env['papers']} papers" in c11
    ww = f"{where['rows']['wastewater']} of them wastewater effluent, from "
    assert ww + f"{where['papers']['wastewater']} papers" in c11
    assert f"Air or dust: {where['rows']['air_dust']} rows" in c11
    hc = origin["second_reading"]
    for stratum in ("environmental", "unclear", "random"):
        assert f"{hc[stratum]['agree']} / {hc[stratum]['n']}" in c11, stratum
    assert f"{hc['random']['agree_synthetic_split']} / {hc['random']['n']} on synthetic" in c11
    assert "`out/tables/sample_origin.csv`" in c11 and "`final_origin`" in c11


def test_the_environmental_rows_ionic_strength_is_stated_as_not_estimable(guide: str, origin):
    env = origin["after_second_reading"]["environmental_rows"]
    sub = _part(guide, "### The environmental rows' conditions", "\n### ", "\n## ")
    n_is = env["reported"]["ionic_strength"]["n"]
    assert f"| ionic strength | **{n_is} / {env['rows']}** |" in sub
    for name in ("medium", "pH", "temperature", "instrument"):
        assert f"| {name} | {env['reported'][name]['n']} / {env['rows']} |" in sub, name
    assert "Griffin" in sub and "0.013" in sub
    assert "marked as estimated, never as reported" in sub
    assert "not possible for any of them" in sub
    assert f"{env['conductivity_printed']} / {env['rows']}" in sub
    for paper in env["conductivity_in_text"]:
        assert paper["why"] in sub
        for entry in paper["lines"]:
            assert f"`{entry['line']}`" in sub
    assert f"{env['own_sample_liquid']} / {env['rows']}" in sub
    whole = env["whole_sample_papers"]
    assert f"In {len(whole)} of the {env['papers']} papers" in sub


def test_the_guide_does_not_claim_how_environmental_plastics_behave(guide: str, origin):
    part = _part(guide, "### What the dataset does NOT prove", "\n## ")
    assert "How environmental micro- and nanoplastics behave" in part
    assert (
        f"air or dust {origin['after_second_reading']['environment']['rows']['air_dust']}" in part
    )


def test_section_8_carries_the_parser_defect_as_open_with_its_bias(guide: str, origin):
    s8 = _part(guide, "## 8. Open issues and decisions", "\n## ")
    lm = origin["lost_methods"]
    item = next(line for line in s8.splitlines() if "supplementary-materials" in line)
    assert f"{lm['papers_affected']} of {lm['papers']} papers" in item
    for name in ("medium", "ionic_strength", "temperature"):
        a, u = lm["affected"]["any_row"][name], lm["unaffected"]["any_row"][name]
        assert f"{100 * a['n'] / lm['affected']['papers']:.1f} %" in item, name
        assert f"{100 * u['n'] / lm['unaffected']['papers']:.1f} %" in item, name
    assert "Open" in item and "Martin" in item
    own = next(line for line in s8.splitlines() if "own measurement" in line)
    for row in origin["not_own_measurement"]:
        assert f"`{row['row_id']}`" in own


def test_section_1_lists_the_origin_tables(guide: str):
    s1 = _part(guide, "## 1. How to use this guide", "\n## 2.")
    assert "`out/tables/sample_origin.csv`" in s1
    assert "`out/tables/sample_origin_stats.json`" in s1


def test_the_guide_opens_with_the_scope_block(guide: str, table, origin):
    stats = json.loads((config.OUT_TABLES / "d1_stats.json").read_text())
    block = "\n".join(scope.block(table, stats, origin))
    title = guide.split("\n", 1)[0]
    assert guide.startswith(f"{title}\n\n{block}\n\n"), guide[:400]
    assert guide.index(block) < guide.index("## 1. How to use this guide")


def test_section_8_points_to_the_corpus_notes(guide: str):
    s8 = _part(guide, "## 8. Open issues and decisions", "\n## ")
    line = next(t for t in s8.splitlines() if scope.NOTES in t)
    assert "Martin, 2026-09-30" in line
