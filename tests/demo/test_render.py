"""`render.py` writes `out/demo/README.md`, `out/demo/cases/NN-<slug>.md` (one per case) and
`out/demo/METHOD.md` from the committed cases/walk/questions/resample/harmonise modules and the
recorded reader runs. These tests build into a scratch directory -- never into the real `out/` --
and check the structural and determinism guarantees `docs/DESIGN_2026-09-28_demo.md` states:
every case page carries all seven sections, the README lists every case, rendering twice
is byte-identical, METHOD.md's headline numbers are the modules' own numbers (never typed by
hand), a missing run directory renders "not run", and a recorded usage-policy refusal renders as
one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from mnp import config
from mnp.demo import cases as cases_mod
from mnp.demo import harmonise, render, resample
from mnp.demo import questions as questions_mod
from mnp.eval import cells
from mnp.eval import comparability as comp
from mnp.report import scope

SECTIONS = (
    "## 1. Why this case",
    "## 2. Rows",
    "## 3. Standardisation walk",
    "## 4. Comparability",
    "## 5. Harmonised value",
    "## 6. Resampling",
    "## 7. Reader",
)


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("demo-build")
    render.build(root)
    return root / "demo"


def _case_path(built: Path, case: cases_mod.Case) -> Path:
    return built / "cases" / f"{case.nn}-{case.slug}.md"


def test_one_case_page_per_case_is_written(built: Path):
    pages = sorted((built / "cases").glob("*.md"))
    assert len(pages) == len(cases_mod.CASES)


def test_every_case_page_has_all_seven_sections(built: Path):
    for case in cases_mod.CASES:
        text = _case_path(built, case).read_text(encoding="utf-8")
        for heading in SECTIONS:
            assert heading in text, f"{case.nn}-{case.slug} missing {heading!r}"


def test_every_case_page_shows_its_own_mode(built: Path):
    for case in cases_mod.CASES:
        text = _case_path(built, case).read_text(encoding="utf-8")
        assert case.mode in text
        assert case.pmcid in text


def test_readme_lists_every_case(built: Path):
    text = (built / "README.md").read_text(encoding="utf-8")
    for case in cases_mod.CASES:
        assert case.nn in text
        assert case.slug in text
        for pmcid in case.pmcids:
            assert pmcid in text


def test_rendering_twice_is_byte_identical(tmp_path_factory):
    first = tmp_path_factory.mktemp("demo-a")
    second = tmp_path_factory.mktemp("demo-b")
    render.build(first)
    render.build(second)
    first_files = sorted(p.relative_to(first) for p in first.rglob("*") if p.is_file())
    second_files = sorted(p.relative_to(second) for p in second.rglob("*") if p.is_file())
    assert first_files == second_files
    for rel in first_files:
        assert (first / rel).read_bytes() == (second / rel).read_bytes(), rel


def test_method_reports_the_modules_own_comparability_numbers(built: Path):
    text = (built / "METHOD.md").read_text(encoding="utf-8")
    table = resample.load_table()
    rows = [comp.ZetaRow.from_mapping(r) for r in table.to_dict(orient="records")]
    census = comp.graded_census(rows)
    n_comparable = sum(1 for s in census if s.verdict.verdict is comp.Comparability.comparable)
    n_conditional = sum(
        1 for s in census if s.verdict.verdict is comp.Comparability.conditionally_comparable
    )
    assert f"**{n_comparable}**" in text
    assert f"**{n_conditional}**" in text


def test_method_reports_the_modules_own_conversion_scan_numbers(built: Path):
    text = (built / "METHOD.md").read_text(encoding="utf-8")
    table = resample.load_table()
    scan = harmonise.scan(table)
    assert f"**{scan.zeta_papers}**" in text
    assert f"**{scan.zeta_named}**" in text
    assert f"**{scan.zeta_not_named}**" in text
    assert f"**{scan.mobility_papers}**" in text
    assert f"**{scan.mobility_named}**" in text


def test_readme_e2e_table_matches_resample_estimates(built: Path):
    text = (built / "README.md").read_text(encoding="utf-8")
    table = resample.load_table()
    for estimate in resample.estimates(table):
        # per-paper headline, formatted exactly as render._pct does.
        assert f"{estimate.per_paper * 100:.1f}%" in text
        assert f"{estimate.per_row * 100:.1f}%" in text


# -- the reader section: not-run and usage-policy refusal -------------------------------------


def test_missing_run_directory_renders_not_run():
    answer = render.reader_answer("D", None, "X01-A", _fake_key(), _fake_corpus(), "PMC0", {})
    assert answer.status == "not_run"


def test_usage_policy_error_renders_as_refused(tmp_path, monkeypatch):
    directory = tmp_path / render.CELL_D_RUN
    directory.mkdir()
    (directory / "manifest.json").write_text("{}")
    (directory / "errors.jsonl").write_text(
        '{"qid": "X01-A", "error": "reader failed: usage policy violation", "at": "now"}\n'
    )
    monkeypatch.setattr(render.runs, "runs_dir", lambda: tmp_path)
    run = render.load_run("D")
    assert run is not None
    answer = render.reader_answer("D", run, "X01-A", _fake_key(), _fake_corpus(), "PMC0", {})
    assert answer.status == "refused"


def test_a_refusal_recorded_as_the_cells_answer_renders_refused_and_counts_wrong(
    tmp_path, monkeypatch
):
    """Martin, 2026-09-28: a refusal is the cell's answer -- shown as refused, in the
    denominator, scored wrong. The runner now writes it to answers.jsonl, not errors.jsonl."""
    directory = tmp_path / render.CELL_D_RUN
    directory.mkdir()
    (directory / "manifest.json").write_text("{}")
    (directory / "answers.jsonl").write_text(
        '{"qid": "X01-A", "cell": "D", "text": "reader refused: Usage Policy", '
        '"refused": true, "tokens_delivered": 0}\n'
    )
    monkeypatch.setattr(render.runs, "runs_dir", lambda: tmp_path)
    run = render.load_run("D")
    assert run is not None
    answer = render.reader_answer("D", run, "X01-A", _fake_key(), _fake_corpus(), "PMC0", {})
    assert answer.status == "refused"
    from mnp.eval.query_sets import QueryKind, Question

    question = Question(qid="X01-A", kind=QueryKind.a, text="q")
    summary = render._reader_summary_table("D", run, [(question, _fake_key())], _fake_corpus())
    assert "0 answered, 1 refused" in summary
    assert "\tA\t1\t0.000" in summary


def test_a_reader_failure_with_no_policy_wording_is_not_answered(tmp_path, monkeypatch):
    directory = tmp_path / render.CELL_D_RUN
    directory.mkdir()
    (directory / "manifest.json").write_text("{}")
    (directory / "errors.jsonl").write_text(
        '{"qid": "X01-A", "error": "timed out after 300 s", "at": "now"}\n'
    )
    monkeypatch.setattr(render.runs, "runs_dir", lambda: tmp_path)
    run = render.load_run("D")
    assert run is not None
    answer = render.reader_answer("D", run, "X01-A", _fake_key(), _fake_corpus(), "PMC0", {})
    assert answer.status == "not_answered"


def _fake_key():
    from mnp.eval.query_sets import AnswerKey, QueryKind

    return AnswerKey(qid="X01-A", kind=QueryKind.a, fields=())


def _fake_corpus():
    return cells.Corpus()


# -- METHOD.md rewrite: items 1-7 of the 2026-09-28 review -----------------------------------


def test_method_deletes_the_false_martin_review_claim(built: Path):
    """Martin never reviewed the Henry/Ohshima deviation rule; the old text said he did."""
    text = (built / "METHOD.md").read_text(encoding="utf-8")
    assert "agreed with Martin" not in text
    assert "decided in review on 2026-09-28, recorded in docs/DESIGN_2026-09-28_demo.md" in text


def test_method_states_the_ratified_three_rules_not_the_verdict_vocabulary(built: Path):
    text = (built / "METHOD.md").read_text(encoding="utf-8")
    assert "## Three extra rules" in text
    assert "1. **Scope.**" in text
    assert "2. **Absence is never imputed.**" in text
    assert "3. **Every figure here is an upper bound.**" in text
    assert "ratified 2026-09-13" in text
    census = render.same_particle_census(resample.load_table())
    assert f"**{census.count('lost_to_absence'):,}**" in text
    assert "81,624" not in text
    assert "upper bound" in text
    # the verdict vocabulary (reported/derived/nominal/unreported) is separate content
    assert "## Verdict vocabulary" in text
    for word in ("reported", "derived", "nominal", "unreported"):
        assert f"**{word}**" in text


def test_method_has_the_full_per_condition_table(built: Path):
    text = (built / "METHOD.md").read_text(encoding="utf-8")
    header = (
        "| condition | why a zeta value means nothing without it | counts as reported "
        "| does not count |"
    )
    assert header in text
    for condition in ("medium", "ionic strength (mM)", "pH", "temperature (°C)", "instrument"):
        assert f"\n| {condition} |" in text, condition
    # cells from docs/2026-09-21-cile-a-otazky-pro-vedce.md Part 1, translated
    assert "incubation, exposure, storage or culture temperature" in text
    assert '"PBS" or "HEPES" named alone' in text
    assert "nominal composition is never looked up" in text
    assert '"physiological pH" with no number attached' in text


def test_method_ionic_strength_sources_match_the_live_table(built: Path):
    text = (built / "METHOD.md").read_text(encoding="utf-8")
    table = resample.load_table()
    counts = table["ionic_strength_source"].value_counts()
    papers = table.groupby("ionic_strength_source")["pmcid"].nunique()
    for source in ("reported", "inferred_from_named_salt", "unreported"):
        assert f"| {source} | {int(counts.get(source, 0))} | {int(papers.get(source, 0))} |" in text
    assert "PMC10141840" in text
    assert "conductivity is printed instead of ionic strength" in text
    assert "a buffer is named" in text
    assert "culture or biological medium" in text


def test_method_comparability_reads_tolerances_and_strata_from_constants(built: Path):
    text = (built / "METHOD.md").read_text(encoding="utf-8")
    assert f"{comp.IONIC_STRENGTH_REL_TOL:.0%}" in text
    assert f"{comp.PH_TOL:g}" in text
    assert f"{comp.TEMPERATURE_TOL_C:g}" in text
    assert f"{comp.HENRY_REL_TOL:.0%}" in text
    for code in comp._AXIS_CODES:
        assert code in text
    for field in comp.BLOCKER_FIELDS:
        assert f"`{field}`" in text
    assert "four uniform seeded strata" not in text
    assert f"**{len(comp.STRATA)}**" in text
    for stratum in comp.STRATA:
        assert stratum in text


def test_method_resampling_has_worked_numbers(built: Path):
    text = (built / "METHOD.md").read_text(encoding="utf-8")
    table = resample.load_table()
    ests = {e.metric: e for e in resample.estimates(table)}
    temp = ests["temperature_reported"]
    ionic = ests["ionic_strength_reported"]
    assert f"±{temp.naive_half_width * 100:.1f} pp" in text
    assert f"±{temp.row_half_width * 100:.1f} pp" in text
    assert f"**{ionic.icc:.4f}**" in text
    assert "PMC8719689" in text
    loo = {item.metric: item for item in resample.leave_one_out(table, "PMC8719689")}
    temp_loo = loo["temperature_reported"]
    assert f"{temp_loo.per_row_full * 100:.1f}%" in text
    assert f"{temp_loo.per_row_without * 100:.1f}%" in text
    assert f"{temp_loo.per_paper_full * 100:.1f}%" in text
    assert f"{temp_loo.per_paper_without * 100:.1f}%" in text


def test_method_reader_grid_wording_is_corrected(built: Path):
    text = (built / "METHOD.md").read_text(encoding="utf-8")
    # old (wrong) claim: the harness itself enforces a one-retry limit
    assert "never retried a second time" not in text
    # corrected: the harness has no such limit; these two runs happened to be resumed once
    assert "resumed at most once" in text
    assert "carries no" in text
    assert "handed the matching structured rows" in text
    assert "illustration of the grid" in text
    table = resample.load_table()
    n_questions = sum(len(questions_mod.questions_for(c, table)) for c in cases_mod.CASES)
    assert f"{n_questions} questions" in text


# -- README.md: items 8-9 ---------------------------------------------------------------------


def test_readme_e2e_table_has_naive_and_cluster_columns(built: Path):
    text = (built / "README.md").read_text(encoding="utf-8")
    table = resample.load_table()
    assert "naive ± (row)" in text
    assert "cluster ± (row)" in text
    assert "cluster ± (paper)" in text
    for e in resample.estimates(table):
        assert f"{e.naive_half_width * 100:.1f} pp" in text
        assert f"{e.row_half_width * 100:.1f} pp" in text
        assert f"{e.paper_half_width * 100:.1f} pp" in text


def test_readme_lists_cell_b_fabrications_and_cell_d_wrong_answers_by_qid(built: Path):
    text = (built / "README.md").read_text(encoding="utf-8")
    assert "### Cell B fabrications" in text
    assert "### Cell D wrong answers" in text
    assert "[`X03-B`](cases/03-conductivity-not-ionic-strength.md)" in text
    assert "[`X07-B`](cases/07-incubation-not-measurement-temperature.md)" in text
    assert "[`X01-E`](cases/01-fully-conditioned.md)" in text


# -- case 06: convergence is checked against the paper's own rows, not assumed ----------------


def test_case_06_page_shows_computed_convergence_spreads(built: Path):
    text = (built / "cases" / "06-biological-medium.md").read_text(encoding="utf-8")
    table = resample.load_table()
    rows = table[(table["pmcid"] == "PMC8719689") & (table["quantity"] == "zeta_potential")]
    culture = rows[rows["medium_class"] == "culture_medium"]
    other = rows[rows["medium_class"] != "culture_medium"]
    culture_means = culture.groupby(["material", "functionalisation"])["value"].mean()
    other_means = other.groupby(["material", "functionalisation"])["value"].mean()
    shared = sorted(set(culture_means.index) & set(other_means.index))
    other_spread = max(other_means[k] for k in shared) - min(other_means[k] for k in shared)
    culture_spread = max(culture_means[k] for k in shared) - min(culture_means[k] for k in shared)
    assert f"{other_spread:.1f} mV" in text
    assert f"{culture_spread:.1f} mV" in text
    assert other_spread > culture_spread  # the claim the case's `why` makes: it narrows


def test_a_score_line_never_shows_the_answer_key():
    """`key_<verdict>` rides on a kind E score so recall can be counted per true verdict. It is
    the key, not a score, and printing it put `key_not_comparable=1.00` on every case page."""
    from mnp.eval import scoring
    from mnp.eval.query_sets import QueryKind

    scored = scoring.Scored(
        qid="X01-E",
        kind=QueryKind.e,
        cell="D",
        correct=True,
        extra=(("blockers_exact", 1.0), ("key_not_comparable", 1.0)),
    )
    line = render._score_line(scored)
    assert "blockers_exact=1.00" in line
    assert "key_" not in line


@pytest.mark.parametrize("name", ["README.md", "METHOD.md"])
def test_readme_and_method_open_with_the_scope_block(built: Path, name: str):
    tables = config.OUT_TABLES
    block = "\n".join(
        scope.block(
            pd.read_csv(tables / "d1_zeta_table.csv"),
            json.loads((tables / "d1_stats.json").read_text()),
            json.loads((tables / "sample_origin_stats.json").read_text()),
        )
    )
    text = (built / name).read_text(encoding="utf-8")
    title = text.split("\n", 1)[0]
    assert text.startswith(f"{title}\n\n{block}\n\n"), text[:500]


# -- a case built on a pair across two papers (case 14), and the count that follows CASES -------


def _pair_case() -> cases_mod.Case:
    found = [case for case in cases_mod.CASES if case.nn == "14"]
    assert found, "no case 14"
    return found[0]


def _section(page: str, n: int) -> str:
    return next(part for part in page.split("\n## ") if part.startswith(f"{n}. "))


@pytest.fixture(scope="module")
def pair_page() -> str:
    """Rendered without `build`, so it needs no scope block and no recorded run."""
    case = _pair_case()
    table = resample.load_table()
    corpus = cells.load_corpus(case.pmcids)
    return render.case_page(
        case,
        table,
        corpus,
        render.corpus_wide_census(table),
        comp.read_query_set(),
        {cell: None for cell in render.CELLS},
        render._line_index(corpus),
    )


@pytest.mark.parametrize("n", [1, 2, 3, 5, 6])
def test_a_pair_case_page_shows_both_papers(pair_page: str, n: int):
    for pmcid in _pair_case().pmcids:
        assert pmcid in _section(pair_page, n), (n, pmcid)


def test_a_pair_case_page_shows_its_cross_paper_pair(pair_page: str):
    a, b = _pair_case().pair
    assert f"| {a} | {b} | comparable | (none) |" in _section(pair_page, 4)


def test_readme_title_and_index_follow_the_case_count():
    table = resample.load_table()
    no_runs = {cell: None for cell in render.CELLS}
    text = render.readme(
        table, cells.Corpus(table=table), no_runs, [], [], render.same_particle_census(table)
    )
    assert f"{len(cases_mod.CASES)} real cases" in text.split("\n", 1)[0]
    assert "thirteen" not in text.lower()
    case = _pair_case()
    row = next(
        line for line in text.splitlines() if line.startswith(f"| {case.nn} | {case.slug} |")
    )
    for pmcid in case.pmcids:
        assert pmcid in row


# -- not different, just unreported: the same-particle census ---------------------------------
# Rendered without `build`, so neither needs the scope block's origin table.


@pytest.fixture(scope="module")
def census() -> comp.SameParticleCensus:
    return comp.same_particle_census(comp.load_rows())


@pytest.fixture(scope="module")
def direct() -> dict[str, str]:
    table = resample.load_table()
    corpus = cells.Corpus(table=table)
    sp = render.same_particle_census(table)
    no_runs = {cell: None for cell in render.CELLS}
    return {
        "README.md": render.readme(table, corpus, no_runs, [], [], sp),
        "METHOD.md": render.method(table, corpus, [], sp),
    }


def test_the_census_render_reads_is_the_modules_own(census):
    assert render.same_particle_census(resample.load_table()) == census


def test_readme_has_the_not_different_just_unreported_section(direct, census):
    text = direct["README.md"]
    part = text.split("\n## Not different, just unreported\n", 1)[1].split("\n## ", 1)[0]
    for name, n in census.categories:
        assert f"| {comp.SAME_PARTICLE_LABELS[name]} | {n:,} |" in part, name
    assert f"| all same-particle pairs | {census.pairs:,} |" in part
    only = dict(census.only_absent_field)
    rows = [line for line in part.splitlines() if line.startswith("| `")]
    assert rows == [f"| `{f}` | {n:,} | {only.get(f, 0):,} |" for f, n in census.absent_fields]
    assert f"**{census.count('lost_to_absence'):,}**" in part
    assert f"{census.absence_cross_paper:,} of them cross a paper" in part
    assert f"{census.absence_same_paper:,} sit inside one" in part
    assert "not a claim about what a default would" in part


def test_readme_says_an_unstated_surface_is_counted_as_absence(direct, census):
    part = direct["README.md"].split("## Not different, just unreported", 1)[1]
    surface = dict(census.absent_fields).get("functionalisation", 0)
    assert surface > 0
    assert f"{surface:,} of the pairs lost to absence leave the surface unstated" in part


def test_method_states_the_same_particle_rule(direct, census):
    text = direct["METHOD.md"]
    part = text.split("\n## The same-particle census\n", 1)[1].split("\n## ", 1)[0]
    for phrase in (
        "`material_key(material)`",
        "`functionalisation_key(functionalisation)`",
        "**every** blocker has kind `unreported`",
        "at least one blocker has kind `mismatch`",
        "`mnp.eval.comparability.same_particle_census`",
    ):
        assert phrase in part, phrase
    for name in comp.SAME_PARTICLE_CATEGORIES:
        assert f"**{comp.SAME_PARTICLE_LABELS[name]}**" in part, name


def test_method_replaces_the_typed_counterfactual_with_the_census(direct, census):
    text = direct["METHOD.md"]
    rule = text.split("2. **Absence is never imputed.**", 1)[1].split("\n3. ", 1)[0]
    assert f"**{census.count('lost_to_absence'):,}**" in rule
    assert f"{census.pairs:,} pairs" in rule
    assert "not a count of what any default would" in rule
    assert "81,624" not in text and "81 624" not in text


def test_no_counterfactual_literal_is_left_in_the_renderers():
    """REVIEW.md said no committed code produces 81 624; the demo printed it anyway."""
    from mnp.report import review_guide

    for module in (render, review_guide):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "81,624" not in source and "81 624" not in source, module.__name__
