"""`report review` writes out/review/: REVIEW.md, a guide for checking the dataset by hand, and
six CSV worksheets a spreadsheet can recompute. These tests build into a scratch root seeded with
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
from mnp.report import review, review_guide, scope

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
    "same_particle_census.csv",
)

FLAGS = (
    "medium_reported",
    "ionic_strength_reported",
    "pH_reported",
    "temperature_reported",
    "instrument_reported",
)


def _seed_root(root: Path, origin: bool = True) -> Path:
    (root / "tables").mkdir(parents=True)
    (root / "release").mkdir(parents=True)
    names = ("d1_zeta_table.csv", "d1_stats.json") + ("sample_origin_stats.json",) * origin
    for name in names:
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


def test_section_8_carries_the_methods_defect_as_fixed_with_its_effect(guide: str, table):
    s8 = _part(guide, "## 8. Open issues and decisions", "\n## ")
    item = next(line for line in s8.splitlines() if "`9b17a6c`" in line)
    assert item.endswith("Closed.") and "Open" not in item
    assert item.split(". ", 1)[1] == review_guide._methods_fix(review.methods_fix(table))
    assert not any("Open, a decision for Martin" in line and "Methods" in line
                   for line in s8.splitlines())  # fmt: skip


def test_section_8_carries_the_rows_that_are_not_an_own_measurement(guide: str, origin):
    """Open while rows are listed, naming each; closed, not dropped, once none is left, so the
    decision stays on record where `docs/DECISIONS.md` OD-01 points (§8 item 19)."""
    s8 = _part(guide, "## 8. Open issues and decisions", "\n## ")
    (own,) = [line for line in s8.splitlines() if "own measurement" in line]
    assert own.startswith("19. ")
    listed = origin["not_own_measurement"]
    for row in listed:
        assert f"`{row['row_id']}`" in own
    assert own.endswith("Closed.") == (not listed)


def test_the_own_measurement_item_names_every_row_while_open_and_closes_when_none_is_left():
    rows = [
        {"row_id": row_id, "pmcid": row_id.split("-")[0], "particle_name": "x", "why": why}
        for row_id, why in (("PMCA-r1", "a fabric"), ("PMCA-r2", "a fabric"), ("PMCB-r4", "cited"))
    ]
    (item,) = review_guide._origin_open({"not_own_measurement": rows})
    assert item.startswith("**3 rows are not the authors' own measurement")
    assert "`PMCA-r1`, `PMCA-r2` (a fabric); `PMCB-r4` (cited)" in item
    assert "Open:" in item and "Closed" not in item
    (closed,) = review_guide._origin_open({"not_own_measurement": []})
    assert "own measurement" in closed and "OD-01" in closed
    assert closed.endswith("Closed.") and "Open" not in closed


def test_the_methods_fix_reads_before_from_its_impact_file_and_now_from_the_table(table):
    """Before is history, measured on the table the fix was made against (`d538ce5`'s, 1 890 rows
    from 491 papers) and committed beside the fix; now moves with the table."""
    impact = json.loads((config.DATA_INTERIM / "methods_fix_impact.json").read_text())
    changed = set(impact["MEASURED"]["parse"]["changed_pmcids_with_rows"])
    rows = table[table["pmcid"].isin(changed)]
    item = review_guide._methods_fix(review.methods_fix(table))
    assert "Methods of 208 of 491 papers" in item
    assert "medium 81.5 % → " in item and "pH 20.0 % → " in item
    assert "temperature 19.5 % → " in item and "769 rows then" in item
    assert "1 890 rows from 491 papers before the fix" in item and "rows 61 → " in item
    for flag in FLAGS:
        assert f" → {100 * rows[flag].astype(bool).mean():.1f} %" in item, flag
    assert f"{len(rows)} from {rows['pmcid'].nunique()} papers now" in item
    complete = int(table["conditions_complete"].astype(bool).sum())
    assert f"{len(table):,} from {table['pmcid'].nunique()} now".replace(",", " ") in item
    assert f"rows 61 → {complete}." in item
    for commit in ("`d4be112`", "`9b17a6c`", "`5012fdf`", "`92db4fb`"):
        assert commit in item


def test_the_methods_fix_item_survives_papers_with_no_rows_left():
    """`report origin` built after the fix wrote `lost_methods` with 0 papers affected, and the
    open item divided by that. Neither a stale stats file nor an empty side may crash the guide."""
    keys = ("medium", "ionic_strength", "pH", "temperature", "instrument", "complete")

    def side(papers: int, n: int) -> dict:
        any_row = {k: {"n": n, "share": n / max(papers, 1)} for k in keys}
        return {"papers": papers, "rows": 4 * papers, "any_row": any_row}

    stale = {"lost_methods": {"papers": 467, "papers_affected": 0, "pmcids": [],
                              "affected": side(0, 0), "unaffected": side(467, 9)}}  # fmt: skip
    assert review_guide._origin_open(stale) == []
    empty = {"papers": 0, "rows": 0, "reported": dict.fromkeys(FLAGS, 0),
             "table": {"rows": 0, "papers": 0, "complete": 0}}  # fmt: skip
    item = review_guide._methods_fix({"before": empty, "now": empty})
    assert "medium — → —" in item and "It fell" not in item and "rose" not in item


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


# -- C12, not different, just unreported --------------------------------------------------------
# Built without the origin table, so these hold whether or not `report origin` has run.


@pytest.fixture(scope="module")
def plain(tmp_path_factory) -> Path:
    root = _seed_root(tmp_path_factory.mktemp("review-plain"), origin=False)
    review.build(root)
    return root / "review"


@pytest.fixture(scope="module")
def plain_guide(plain: Path) -> str:
    return (plain / "REVIEW.md").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def census(table) -> comp.SameParticleCensus:
    return comp.same_particle_census(
        [comp.ZetaRow.from_mapping(r) for r in table.to_dict("records")]
    )


def _i(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def test_the_same_particle_worksheet_adds_up_to_the_census(plain: Path, plain_guide: str, census):
    name = "same_particle_census.csv"
    sheet = _sheet(plain, name)
    assert sheet.columns.tolist() == list(review.COLUMNS[name])
    undocumented = [c for c in sheet.columns if f"`{c}`" not in plain_guide]
    assert not undocumented, undocumented
    assert len(sheet) == len(census.particles)
    for category, n in census.categories:
        assert sheet[category].sum() == n, category
    assert (sheet["pairs"] == sheet["rows"] * (sheet["rows"] - 1) // 2).all()
    assert (sheet[list(comp.SAME_PARTICLE_CATEGORIES)].sum(axis=1) == sheet["pairs"]).all()
    assert sheet["lost_to_absence_cross_paper"].sum() == census.absence_cross_paper
    assert sheet["functionalisation"].isna().sum() == sum(
        p.functionalisation is None for p in census.particles
    )


def test_section_5_7_states_the_rule_and_the_census(plain_guide: str, census):
    part = _part(plain_guide, "### 5.7 Not different, just unreported", "\n### ", "\n## ")
    assert "every blocker kind unreported" in part
    assert "at least one blocker kind mismatch" in part
    for category, n in census.categories:
        assert f"(`{category}`) | {_i(n)} |" in part, category
    assert f"| all same-particle pairs | {_i(census.pairs)} |" in part
    only = dict(census.only_absent_field)
    rows = [line for line in part.splitlines() if line.startswith("| `")]
    assert rows == [f"| `{f}` | {_i(n)} | {_i(only.get(f, 0))} |" for f, n in census.absent_fields]
    assert "`same_particle_census.csv`" in part


def test_section_5_7_works_one_pair_that_one_reported_number_would_decide(plain_guide, table):
    part = _part(plain_guide, "### 5.7 Not different, just unreported", "\n### ", "\n## ")
    a, b = re.search(r"Pair `(PMC\d+-r\d+)` × `(PMC\d+-r\d+)`", part).groups()
    rows = {r["row_id"]: comp.ZetaRow.from_mapping(r) for r in table.to_dict("records")}
    verdict = comp.comparable(rows[a], rows[b])
    assert comp.same_particle_key(rows[a]) == comp.same_particle_key(rows[b])
    assert [blocker.kind for blocker in verdict.blockers] == [comp.BlockerKind.unreported]
    assert f"`{verdict.blockers[0].code}`" in part


def test_c12_states_the_census(plain_guide: str, census):
    c12 = _part(plain_guide, "#### C12. Not different, just unreported", "\n#### ", "\n### ")
    absence = census.count("lost_to_absence")
    assert (
        f"{_i(census.pairs)} pairs of rows describe the same particle; {_i(absence)} of them" in c12
    )
    assert f"{_i(census.absence_cross_paper)} of those across papers and " in c12
    assert f"{_i(census.absence_same_paper)} inside one paper" in c12
    assert f"{_i(census.count('stated_difference'))} differ in a stated condition" in c12
    assert f"{_i(census.count('undecidable'))} are undecidable" in c12
    assert f"{_i(census.count('comparable'))} comparable." in c12
    field, n = census.absent_fields[0]
    assert f"`{field}` is missing in {_i(n)} of them" in c12
    assert "not a claim about what a default would do" in c12
    assert "`same_particle_census.csv`" in c12


def test_the_pair_count_recipe_the_guide_prints_gives_the_census(plain_guide: str, table, census):
    imports, expression = review_guide.SAME_PARTICLE_RECIPE
    assert f"`{imports}`" in plain_guide and f"`{expression}`" in plain_guide
    namespace = {"t": table.copy()}
    exec(imports, namespace)
    assert int(eval(expression, namespace)) == census.pairs


def test_the_guide_no_longer_quotes_the_counterfactual(plain_guide: str):
    assert "81 624" not in plain_guide and "81,624" not in plain_guide
    s8 = _part(plain_guide, "## 8. Open issues and decisions", "\n## ")
    item = next(line for line in s8.splitlines() if "§4c" in line)
    assert "no committed code produces" in item and "C12" in item


def test_the_grid_runs_the_guide_reports_answered_todays_question_sets():
    """RUN_IDS named the 2026-09-27/28 sweeps after the question sets were regenerated, so C9 and
    the results page reported a grid over questions that no longer exist."""
    from mnp.eval import grid
    from mnp.report import review

    current = {q.qid for q in grid.all_questions()}
    for cell, run_id in review.RUN_IDS.items():
        asked = (config.DATA_INTERIM / "runs" / run_id / "asked.txt").read_text().split()
        assert set(asked) == current, (cell, run_id, len(set(asked) ^ current))
