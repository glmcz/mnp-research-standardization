"""Every number on the deck, held against its source.

`build_slides.build("HEAD")` gives the deck's values. `expected` reads each source again without
the builder, by another route where one exists (REVIEW.md's printed numbers rather than the
module, the runs' own score files, DECISIONS.md's wording, the demo case's own sentence), and every
value must agree with it. A value nothing here traces fails the first test. The rendered page is
then scanned: every digit a viewer can see sits inside a `data-k` element whose text is that
value, or matches one of the identifiers in `ALLOWED`, each of which is looked up in its source.

    unset VIRTUAL_ENV; uv run pytest -q -p no:cacheprovider tool/slides/test_slides.py
"""

from __future__ import annotations

import csv
import importlib.util
import io
import json
import math
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

from mnp.demo import cases
from mnp.report import release

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
REF = "HEAD"
# The runs the guide reports; test_review checks they answered today's question sets.
RUNS = __import__("mnp.report.review", fromlist=["RUN_IDS"]).RUN_IDS
CITED = ("PMC12280233", "09c11cd")
NBSP, MINUS = "\u00a0", "\u2212"


def show(path: str, ref: str = REF) -> str:
    run = subprocess.run(["git", "-C", str(REPO), "show", f"{ref}:{path}"], capture_output=True)
    assert run.returncode == 0, f"{ref}:{path} is not committed"
    return run.stdout.decode("utf-8")


def flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def n(s: str) -> int:
    return int(re.sub(r"\s", "", s))


def one(text: str, pattern: str) -> tuple[str, ...]:
    m = re.search(pattern, text)
    assert m, f"the source no longer says: {pattern}"
    return m.groups()


def rows_by_id(text: str) -> dict[str, dict]:
    return {r["row_id"]: r for r in csv.DictReader(io.StringIO(text))}


def entry(register: str, eid: str) -> str:
    """One DECISIONS.md entry, from its bold id to the next entry or heading."""
    start = register.index(f"**{eid} · ")
    end = re.compile(r"\*\*[A-Z]{2}-\d{2} · | ## ").search(register, start + 4)
    return register[start : end.start() if end else None]


class Near:
    def __init__(self, x: float, tol: float) -> None:
        self.x, self.tol = x, tol

    def __repr__(self) -> str:
        return f"Near({self.x}, ±{self.tol})"


class Quoted:
    """The value is one of the strings the source puts in double quotes."""

    def __init__(self, source: str) -> None:
        self.quotes = set(re.findall(r"\"([^\"]+)\"", source))

    def __repr__(self) -> str:
        return f"Quoted({sorted(self.quotes)[:4]}…)"


class Within:
    """The value is a passage of the source, word for word."""

    def __init__(self, source: str) -> None:
        self.source = source

    def __repr__(self) -> str:
        return f"Within({self.source[:60]!r}…)"


MISSING = object()


def agrees(got, want) -> bool:
    if want is MISSING:
        return False
    if isinstance(want, Near):
        return abs(got - want.x) <= want.tol
    if isinstance(want, Quoted):
        return got in want.quotes
    if isinstance(want, Within):
        return isinstance(got, str) and got in want.source
    if isinstance(want, float) or isinstance(got, float):
        return got is not None and math.isclose(got, want, rel_tol=1e-9, abs_tol=1e-12)
    return got == want


def mismatches(values: dict, want: dict) -> list[str]:
    return [
        k
        for k, v in values.items()
        if v["kind"] != "tick" and not agrees(v["v"], want.get(k, MISSING))
    ]


# ---- what each source says ----------------------------------------------------------------------


def expected(get=show) -> dict:
    """key -> what its source says, read without the builder."""
    E: dict = {}
    review = flat(get("out/review/REVIEW.md"))
    register = flat(get("docs/DECISIONS.md"))

    # the corpus and the release
    manifest = get("data/raw/epmc/manifest.sha256").splitlines()
    E["papers_read"] = sum(1 for ln in manifest if ln.rstrip().endswith(".xml"))
    E["records"] = sum(1 for ln in get("data/interim/extractions.jsonl").splitlines() if ln.strip())
    rows, papers = one(review, r"rows ([\d ]+), from (\d+) papers \(out/tables/d1_zeta_table")
    E["rows"], E["row_papers"] = n(rows), int(papers)
    E["dataset"], E["author"] = release.DATASET_NAME, release.AUTHOR
    E["licence"] = release.LICENCE_SHORT

    # case 14: the demo case's own sentence, the table and the harmonisation worksheet
    case = next(c for c in cases.CASES if c.nn == "14")
    why = flat(case.why)
    va, sda, _supplier, sza, vb, sdb, szb = one(
        why,
        r"report (-?[\d.]+) \+/- ([\d.]+) mV \(([^,]+), ([\d.]+) nm measured\) and "
        r"(-?[\d.]+) \+/- ([\d.]+) mV \(supplier not stated, ([\d.]+) nm measured\)",
    )
    salt, ph, temp, instrument = one(
        why,
        r"conditions -- ([\d.]+) mM NaCl, pH ([\d.]+), (\d+) C, "
        r"(\S+ \S+) --",
    )
    newer, older = one(why, r"every author of the (\d{4}) paper also signs the (\d{4}) one")
    d1 = rows_by_id(get("out/tables/d1_zeta_table.csv"))
    harm = rows_by_id(get("out/review/harmonised_all_rows.csv"))
    a_id, b_id = case.pair
    E["c14.lab"] = one(why, r"from one laboratory \(([^;]+);")[0]
    E["c14.medium"] = f"{salt} mM NaCl"
    E["c14.pH"], E["c14.T"], E["c14.instrument"] = float(ph), float(temp), instrument
    E["c14.size_nominal"] = int(one(why, r"measure nominally (\d+) nm")[0])
    for side, rid, value, sd, size, year in (
        ("a", a_id, va, sda, sza, older),
        ("b", b_id, vb, sdb, szb, newer),
    ):
        E[f"c14.{side}.pmcid"] = rid.rsplit("-r", 1)[0]
        E[f"c14.{side}.year"] = int(year)
        E[f"c14.{side}.value"], E[f"c14.{side}.sd"] = float(value), float(sd)
        E[f"c14.{side}.size"] = float(size)
        E[f"c14.{side}.supplier"] = d1[rid]["supplier"] or None
        E[f"c14.{side}.lo"], E[f"c14.{side}.hi"] = float(harm[rid]["low"]), float(harm[rid]["high"])
    E["c14.years"] = int(newer) - int(older)
    E["c14.gap"] = abs(float(va) - float(vb))
    E["c14.igap"] = float(harm[b_id]["low"]) - float(harm[a_id]["high"])

    # case 02
    c02 = next(c for c in cases.CASES if c.nn == "02")
    rows02 = sorted((r for r in d1.values() if r["pmcid"] == c02.pmcid), key=lambda r: r["row_id"])
    E["c02.pmcid"] = c02.pmcid
    E["c02.size"] = float(one(flat(c02.why), r"One ([\d.]+) micron polystyrene particle")[0])
    E["c02.supplier"], E["c02.instrument"] = rows02[0]["supplier"], rows02[0]["instrument"]
    E["c02.pH"], E["c02.T"] = float(rows02[0]["pH"]), float(rows02[0]["temperature_C"])
    for i, r in enumerate(rows02, 1):
        E[f"c02.r{i}.medium"], E[f"c02.r{i}.value"] = r["medium_text"], float(r["value"])
    values02 = [float(r["value"]) for r in rows02]
    E["c02.spread"] = max(values02) - min(values02)

    # the five conditions: the per-paper worksheet, the reasons in METHOD.md
    per_paper = list(csv.DictReader(io.StringIO(get("out/review/conditions_per_paper.csv"))))
    method = get("out/demo/METHOD.md")
    cells = {
        ln.split("|")[1].strip(): ln.split("|")[2].strip()
        for ln in method.splitlines()
        if ln.startswith("| ") and ln.count("|") >= 5
    }
    names = {
        "medium_reported": "medium",
        "ionic_strength_reported": "ionic strength (mM)",
        "pH_reported": "pH",
        "temperature_reported": "temperature (°C)",
        "instrument_reported": "instrument",
    }
    for flag, name in names.items():
        E[f"five.{flag}"] = sum(float(p[f"{flag}_share"]) for p in per_paper) / len(per_paper)
        E[f"five.why.{flag}"] = cells[name].replace("**", "")
    E["five.complete"] = n(one(review, r"#### C1\. [^#]*?\*\*Number\.\*\* ([\d ]+) / ")[0])
    E["five.complete_paper"] = sum(float(p["conditions_complete_share"]) for p in per_paper) / len(
        per_paper
    )

    # the same-particle census, as REVIEW.md prints it (C12, §5.7)
    total, absence, absence_pct, cross, _same, stated, undecidable, conditional, comparable = one(
        review,
        r"([\d ]+) pairs of rows describe the same particle; ([\d ]+) of them \(([\d.]+) %\) "
        r"are lost only to absence, ([\d ]+) of those across papers and ([\d ]+) inside one "
        r"paper\. ([\d ]+) differ in a stated condition, ([\d ]+) are undecidable, ([\d ]+) are "
        r"conditionally "
        r"comparable and ([\d ]+) comparable\.",
    )
    E["sp.pairs"], E["sp.absence_cross"] = n(total), n(cross)
    for key, count in (
        ("comparable", comparable),
        ("conditionally_comparable", conditional),
        ("lost_to_absence", absence),
        ("stated_difference", stated),
        ("undecidable", undecidable),
    ):
        E[f"sp.cat.{key}"] = n(count)
    E["sp.absence_pct"] = Near(float(absence_pct) / 100, 0.0005)
    E["sp.cat_pct.stated_difference"] = n(stated) / n(total)
    top_pct = one(review, r"`ionic_strength` is missing in [\d ]+ of them \(([\d.]+) %\)")[0]
    E["sp.top_pct"] = Near(float(top_pct) / 100, 0.0005)
    part = review.split("### 5.7 ", 1)[1].split("## 6. ", 1)[0]
    fields = re.findall(r"\| `(\w+)` \| ([\d ]+?) \| ([\d ]+?) \|", part)
    assert len(fields) == 7, fields
    for field, missing, only in fields:
        E[f"sp.field.{field}.pairs"], E[f"sp.field.{field}.only"] = n(missing), n(only)
    E["sp.only_total"] = sum(n(only) for _, _, only in fields)

    # the rules and their real examples (DECISIONS.md RC-05, RC-09, RC-10; REVIEW.md §8 item 14)
    E["ai.defaults"] = one(entry(register, "RC-05"), r"a default \(([^)]+)\)")[0]
    E["r1.example"] = one(review, r"14\. \*\*0 mM, decided\.\*\* [^\"]*\"([^\"]+)\"")[0]
    rc09 = entry(register, "RC-09")
    E["r2.pmcid"], E["r2.example"], rows36 = one(
        rc09,
        r"(PMC\d+) labels its media \"([^\"]+)\"\. "
        r"(\d+) rows took that",
    )
    E["r2.rows"] = int(rows36)
    rc10 = entry(register, "RC-10")
    E["r3.example"] = one(rc10, r"Question: \"([^\"]+)\" was stored")[0]
    E["r3.ions"] = one(rc10, r"Why: ([^.]+ of ions)\.")[0]

    # one row and its line addresses
    row = d1[a_id]
    E["arch.row_id"] = a_id
    E["arch.quote"] = row["evidence_quote"].split(" || ")[0]
    E["arch.lines"], E["arch.location"] = row["evidence_line_ids"], row["evidence_location"]
    verified, of = one(review, r"#### C10\. [^#]*?\*\*Number\.\*\* ([\d ]+) / ([\d ]+) \(")
    E["arch.verified"] = [n(verified), n(of)]

    # Henry's function, from the formulas REVIEW.md §5.4 prints, and the cases of §5.5
    debye = float(one(review, r"κ⁻¹ = (0\.\d+) / √\(I\[M\]\) nm")[0])
    f_lo, f_hi = (
        float(x)
        for x in one(
            review,
            r"It runs from ([\d.]+) \(the \*\*Hückel\*\* limit, "
            r"κa ≪ 1\) to ([\d.]+) \(the \*\*Smoluchowski",
        )
    )
    E["h.radius"] = E["c14.size_nominal"] / 2
    E["h.debye_c"], E["h.f_lo"], E["h.f_hi"] = debye, f_lo, f_hi
    E["h.hw_f"] = (f_hi - f_lo) / (f_hi + f_lo)
    lo_div, hi_mul = (
        float(x)
        for x in one(
            review,
            r"anywhere between ζ_rep / (\d+(?:\.\d+)?) and ζ_rep × "
            r"(\d+(?:\.\d+)?)",
        )
    )
    E["h.hw_z4"] = (hi_mul - 1 / lo_div) / (hi_mul + 1 / lo_div)
    E["h.z4"] = n(one(review, r"\| Z4 \| [^|]+ \| ([\d ]+) \|")[0])
    E["h.points"] = n(one(review, r"κa is known on ([\d ]+) /")[0])
    with_ionic = n(one(review, r"#### C3\. [^#]*?per row ([\d ]+) / ")[0])
    E["h.rug"] = with_ionic - E["h.points"]
    E["h.band"] = E["rows"] - with_ionic

    # the re-read control
    control = json.loads(get("data/interim/reread_control/summary.json"))["A_vs_B"]
    E["rr.papers"], E["rr.same_count"] = control["papers"], control["papers_same_row_count"]
    E["rr.rows_a"], E["rr.rows_b"] = control["rows"]
    E["rr.matched"] = control["row_pairs_matched_by_value"]
    for flag, c in control["per_condition"].items():
        E[f"rr.agree.{flag}"] = [c["row_pairs_agreeing"], control["row_pairs_matched_by_value"]]
    E["rr.cited"] = int(
        one(entry(register, "EX-09"), r"In (\d+) of the \d+ papers the recorded")[0]
    )

    # what the agents got wrong: the register's record of agent actions
    actions = register.split("## Agent actions and how they were checked", 1)[1]
    actions = actions.split("## Open decisions", 1)[0]
    E["g.n.pmcid"] = one(actions, r"(PMC\d+) carried an n")[0]
    E["g.dlvo.pmcid"] = one(actions, r"(PMC\d+) recorded DLVO model inputs")[0]
    E["g.twice.pmcid"] = one(actions, r"(PMC\d+) \(one reading counted as both")[0]
    E["g.reread"] = int(one(register, r"\| EX-10 \| Re-read the (\d+) papers")[0])
    pmcid, commit = CITED
    before = next(
        json.loads(ln)
        for ln in get("data/interim/extractions.jsonl", commit).splitlines()
        if f'"pmcid": "{pmcid}"' in ln
    )
    E["g.cited.pmcid"] = pmcid
    E["g.cited.quote"] = Within(" ".join(m["evidence"]["quote"] for m in before["measurements"]))
    ex12, ex14 = entry(register, "EX-12"), entry(register, "EX-14")
    for key in ("molar", "comma", "looked1", "looked2", "mmol", "pow", "kelvin", "step", "asked"):
        E[f"gd.{key}"] = Quoted(ex12)
    for key in ("worker", "harmed", "mmol_text", "pow_read"):
        E[f"gd.{key}"] = Within(ex12)
    E["gd.bpa"], E["gd.bpa_mM"] = Quoted(ex14), Within(ex14)
    E["gd.window"] = int(one(ex14, r"within (\d+) characters after")[0])

    # the grid over the final table: each run's score files, answers and manifest
    for cell, run in RUNS.items():
        base = f"data/interim/runs/{run}"
        verdicts = {
            r["true_verdict"]: r
            for r in csv.DictReader(io.StringIO(get(f"{base}/verdicts.tsv")), delimiter="\t")
        }
        scores = {
            r["kind"]: r
            for r in csv.DictReader(io.StringIO(get(f"{base}/scores.tsv")), delimiter="\t")
        }
        answers = [json.loads(ln) for ln in get(f"{base}/answers.jsonl").splitlines() if ln.strip()]
        manifest = json.loads(get(f"{base}/manifest.json"))
        comp = verdicts["comparable"]
        E[f"gr.{cell}.run"] = run
        E[f"gr.{cell}.comparable"] = [int(comp["correct"]), int(comp["n"])]
        E[f"gr.{cell}.bal"] = Near(float(verdicts["balanced_accuracy"]["recall"]), 0.0005)
        kc = scores["C"]
        E[f"gr.{cell}.C"] = [round(float(kc["accuracy"]) * int(kc["n"])), int(kc["n"])]
        E[f"gr.{cell}.tokens"] = sum(a.get("input_tokens") or 0 for a in answers)
        E["gr.model"], E["gr.asked"] = manifest["model"], manifest["counts"]["asked"]
        if cell == "B":
            ke = scores["E"]
            E["gr.B.E"] = [round(float(ke["accuracy"]) * int(ke["n"])), int(ke["n"])]
            E["gr.B.said_not"] = sum(
                1
                for a in answers
                if a["kind"] == "E"
                and re.search(r"\"verdict\"\s*:\s*\"not_comparable\"", a.get("text") or "")
            )

    # the scope block, as REVIEW.md opens with it
    E["sc.synthetic"] = one(review, r"\*\*Where the particles came from\.\*\* (.+? in a lab\.)")[0]
    E["sc.corpus"] = one(review, r"\*\*The corpus\.\*\* (.+?) \(`d1_stats\.json`\)")[0] + "."
    E["sc.use"] = one(review, r"\*\*What it can be used for\.\*\* (.+? soil\.)")[0]
    return E


# ---- fixtures -----------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def bs():
    spec = importlib.util.spec_from_file_location("build_slides", HERE / "build_slides.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def deck(bs):
    return bs.build(REF)


@pytest.fixture(scope="module")
def page(bs, deck):
    return bs.render(deck)


@pytest.fixture(scope="module")
def want():
    return expected()


# ---- the values ---------------------------------------------------------------------------------


def test_every_value_is_held_against_a_source(deck, want) -> None:
    untraced = [k for k, v in deck["values"].items() if v["kind"] != "tick" and k not in want]
    assert not untraced, f"values with no source: {untraced}"
    bad = mismatches(deck["values"], want)
    assert not bad, "\n".join(
        f"{k}: deck {deck['values'][k]['v']!r}, source {want[k]!r}" for k in bad
    )


def test_the_results_pages_checks_against_review_all_pass(deck) -> None:
    # The count follows the data (one check per verdict cell B gave: two on 2026-09-28, one on the
    # final grid). Which checks exist is pinned exactly by tool/viz/test_reference.py at 4a3087c;
    # here every one of them must agree, and there must be the page's full set, not a stub.
    rc = deck["review_checks"]
    assert rc["n"] >= 140 and rc["ok"] == rc["n"], rc


def _parse(v: dict):
    text = v["text"].replace(NBSP, " ").replace(MINUS, "-")
    kind = v["kind"]
    if kind == "frac":
        a, b = text.split(" / ")
        return [int(a.replace(" ", "")), int(b.replace(" ", ""))]
    if kind == "pct":
        return float(text.removesuffix(" %").replace(" ", "")) / 100
    if kind == "mega":
        return float(text.removesuffix(" M")) * 1e6
    return float(text.replace(" ", ""))


def test_the_text_shown_is_the_value_rounded(deck) -> None:
    for key, v in deck["values"].items():
        if v["kind"] == "text":
            assert v["text"] == (v["v"] if v["v"] is not None else "not stated"), key
            continue
        shown, raw = _parse(v), v["v"]
        if v["kind"] in ("int", "year", "frac"):
            assert shown == raw, (key, v["text"], raw)
            continue
        unit = {"pct": 0.01, "mega": 1e6}.get(v["kind"], 1) * 10 ** -v.get("d", 0)
        assert abs(shown - raw) <= unit / 2 + 1e-12, (key, v["text"], raw)


def test_the_register_and_the_guide_state_what_the_data_holds(deck, want) -> None:
    """The second sources: REVIEW.md, DECISIONS.md and the demo case say what the tables hold."""
    register = flat(show("docs/DECISIONS.md"))
    review = flat(show("out/review/REVIEW.md"))
    V = {k: v["v"] for k, v in deck["values"].items()}
    assert n(one(review, r"XMLs ([\d ]+) vendored")[0]) == V["papers_read"]
    assert n(one(review, r"extraction records ([\d ]+), one per paper read")[0]) == V["records"]

    ex09 = entry(register, "EX-09")
    medium, matched = V["rr.agree.medium_reported"]
    assert f"medium {medium}/{matched}" in ex09
    assert f"agree {V['rr.agree.pH_reported'][0]}/{matched}" in ex09
    assert f"same row count in {V['rr.same_count']} of {V['rr.papers']} papers" in ex09

    gr15 = entry(register, "GR-15")
    d, b = V["gr.D.comparable"], V["gr.B.comparable"]
    assert f"comparable pairs found: D {d[0]}/{d[1]}, B {b[0]}/{b[1]}" in gr15
    assert f"balanced accuracy {V['gr.D.bal']:.2f} vs {V['gr.B.bal']:.2f}" in gr15
    dc, bc = V["gr.D.C"], V["gr.B.C"]
    assert f"Kind C: {dc[0]}/{dc[1]} vs {bc[0]}/{bc[1]}" in gr15
    assert f"Input tokens: {V['gr.D.tokens'] / 1e6:.2f} M vs {V['gr.B.tokens'] / 1e6:.2f} M" in gr15
    assert f"({V['gr.asked']} questions each)" in gr15

    case02 = next(c for c in cases.CASES if c.nn == "02")
    assert round(V["c02.spread"]) == int(one(case02.mode, r"moves zeta (\d+) mV")[0])
    # rows in d1 agree with the case-14 sentence the expectations were read from
    d1 = rows_by_id(show("out/tables/d1_zeta_table.csv"))
    a_id, b_id = next(c for c in cases.CASES if c.nn == "14").pair
    assert (
        float(d1[a_id]["value"]) == V["c14.a.value"]
        and float(d1[b_id]["value"]) == V["c14.b.value"]
    )
    assert d1[a_id]["instrument"].startswith(V["c14.instrument"] + " (")

    licence = flat(show("out/release/LICENSE"))
    assert f'"{V["dataset"]} — ' in licence and f"by {V['author']}." in licence
    assert f"({V['licence']})" in licence


def test_case_14_is_the_one_comparable_pair_across_papers(deck) -> None:
    import pandas as pd

    from mnp.eval import comparability

    table = pd.read_csv(io.StringIO(show("out/tables/d1_zeta_table.csv")))
    rows = [comparability.ZetaRow.from_mapping(r) for r in table.to_dict(orient="records")]
    cross = [s for s in comparability.comparable_census(rows) if s.a.pmcid != s.b.pmcid]
    assert [(s.a.row_id, s.b.row_id) for s in cross] == [
        next(c for c in cases.CASES if c.nn == "14").pair
    ]
    review = flat(show("out/review/REVIEW.md"))
    assert one(review, r"#### C5\. [^#]*?; (\d+) cross a paper boundary")[0] == "1"


def test_the_harmonised_intervals_follow_the_guides_rule(deck) -> None:
    """Z3 (model open, κa known): [v·1.5/f, v/f]; Z4: [v/1.5, v·1.5], on every row of the sheet."""
    harm = rows_by_id(show("out/review/harmonised_all_rows.csv"))
    for side in ("a", "b"):
        r = harm[next(c for c in cases.CASES if c.nn == "14").pair["ab".index(side)]]
        v, f = float(r["value"]), float(r["henry_f"])
        assert math.isclose(float(r["low"]), v * 1.5 / f, rel_tol=1e-6)
        assert math.isclose(float(r["high"]), v / f, rel_tol=1e-6)
    hw = deck["values"]["h.hw_z4"]["v"]
    z4 = [r for r in harm.values() if r["case"] == "Z4" and float(r["value"]) != 0]
    assert z4 and all(
        abs(abs(float(r["high"]) - float(r["low"])) / abs(float(r["high"]) + float(r["low"])) - hw)
        < 1e-4
        for r in z4
    )


def _f(ka: float) -> float:
    """Henry's f as REVIEW.md §5.4 prints it, with the code's two edges (κa ≤ 0, κa > 700)."""
    if ka <= 0:
        return 1.0
    if ka > 700:
        return 1.5
    return 1 + 1 / (2 * (1 + 2.5 / (ka * (1 + 2 * math.exp(-ka)))) ** 3)


def test_the_henry_chart_is_recomputed_from_the_printed_formula(deck, want) -> None:
    c = deck["charts"]["henry"]
    debye = lambda mM: want["h.debye_c"] / math.sqrt(mM / 1000)  # noqa: E731
    radius = want["h.radius"]
    for mM, f in c["curve"]:
        assert math.isclose(f, _f(radius / debye(mM)), rel_tol=1e-9)
    d1 = rows_by_id(show("out/tables/d1_zeta_table.csv"))
    harm = rows_by_id(show("out/review/harmonised_all_rows.csv"))
    ours = sorted(
        (
            float(d1[i]["ionic_strength_mM"]),
            _f(float(d1[i]["size_measured_nm"]) / 2 / debye(float(d1[i]["ionic_strength_mM"]))),
        )
        for i, h in harm.items()
        if h["kappa_a"]
    )
    assert len(ours) == len(c["points"])
    for (m1, f1), (m2, f2) in zip(ours, sorted(map(tuple, c["points"])), strict=True):
        assert m1 == m2 and abs(f1 - f2) < 5e-6, (m1, f1, f2)
    assert len(c["rug"]) == want["h.rug"]


def test_every_axis_label_names_a_value_its_chart_reaches(deck) -> None:
    charts = deck["charts"]
    ticks = [v for v in deck["values"].values() if v["kind"] == "tick"]
    assert {t["chart"] for t in ticks} == {"c14", "c02", "fields", "henry"}
    for t in ticks:
        lo, hi = charts[t["chart"]][t["axis"]]
        assert lo - 1e-9 <= t["v"] <= hi + 1e-9, t
    for name in ("c14", "c02", "fields"):
        lo, hi = charts[name]["x"]
        assert all(lo <= m <= hi for m in charts[name]["marks"]), name
    h = charts["henry"]
    xs = [p[0] for p in h["points"]] + h["rug"] + [p[0] for p in h["curve"]]
    assert h["x"][0] <= min(xs) and max(xs) <= h["x"][1] * (1 + 1e-9)
    assert all(h["y"][0] <= p[1] <= h["y"][1] for p in h["points"] + h["curve"])


# ---- a check that catches a wrong number --------------------------------------------------------


def test_a_wrong_deck_value_is_caught(deck, want) -> None:
    values = json.loads(json.dumps(deck["values"]))
    values["sp.cat.lost_to_absence"]["v"] += 1
    assert mismatches(values, want) == ["sp.cat.lost_to_absence"]


def test_a_changed_source_is_caught(deck) -> None:
    path = "data/interim/reread_control/summary.json"
    control = json.loads(show(path))
    control["A_vs_B"]["per_condition"]["medium_reported"]["row_pairs_agreeing"] -= 1
    tampered = json.dumps(control)
    want = expected(lambda p, ref=REF: tampered if p == path else show(p, ref))
    assert mismatches(deck["values"], want) == ["rr.agree.medium_reported"]


# ---- the page -----------------------------------------------------------------------------------

#: Digits a viewer may see outside a data slot: identifiers, each looked up in its source below.
ALLOWED = (
    (r"\b(?:CP|EX|RC|CM|HM|RS|GR|DM|RV|LR|OS|PR|OD)-\d{2}\b", None, "register"),
    (r"\bC\d{1,2}\b", None, "claim"),
    (r"§\d+(?:\.\d+)?", None, "section"),
    (r"\bR(?:1|2b?|3)\b", None, "rule"),
    (r"\bZ[1-4]\b", None, "case"),
    (r"\b[Cc]ase \d{2}\b", None, "demo"),
    (r"\bBM25\b", None, "method"),
    (r"[\w/.-]*\d[\w/.-]*\.(?:csv|md|json|jsonl|py)\b", None, "path"),
    (r"\b1:1\b", "debye-note", "electrolyte"),
    (r"\b25 °C\b", "debye-note", "temperature"),
    (r"^\d{2}$", "idx", "slide"),
)
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}


class Scan(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, dict, list[str]]] = []
        self.owned: list[tuple[str, str]] = []
        self.free: list[tuple[str, set[str], str | None]] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID:
            self.stack.append((tag, dict(attrs), []))

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack or self.stack[-1][0] != tag:
            self.errors.append(f"</{tag}> closes <{self.stack[-1][0] if self.stack else None}>")
            return
        _, attrs, buf = self.stack.pop()
        if "data-k" in attrs:
            self.owned.append((attrs["data-k"], "".join(buf)))

    def handle_data(self, data):
        if any(t in ("script", "style", "title") for t, _, _ in self.stack):
            return
        owner = next((s for s in reversed(self.stack) if "data-k" in s[1]), None)
        if owner:
            owner[2].append(data)
            return
        classes = {c for _, a, _ in self.stack for c in (a.get("class") or "").split()}
        slide = next(
            (a["id"] for _, a, _ in self.stack if re.fullmatch(r"s\d+", a.get("id", ""))), None
        )
        self.free.append((data, classes, slide))


@pytest.fixture(scope="module")
def scan(page):
    s = Scan()
    s.feed(page)
    s.close()
    return s


def test_the_markup_nests_and_quotes_its_attributes(page, scan) -> None:
    assert not scan.errors, scan.errors[:5]
    assert not scan.stack, [t for t, _, _ in scan.stack]
    unquoted = re.findall(r"<[a-zA-Z][^>]*?\s[\w:-]+=(?![\"'])[^\s>]+", page)
    assert not unquoted, unquoted[:5]
    assert "{{" not in page and "__DATA__" not in page


def test_every_slot_shows_its_value_and_every_value_is_shown(deck, scan) -> None:
    values = deck["values"]
    wrong = [(k, t, values[k]["text"]) for k, t in scan.owned if t != values[k]["text"]]
    assert not wrong, wrong[:5]
    unshown = set(values) - {k for k, _ in scan.owned}
    assert not unshown, sorted(unshown)


def _allowed_tokens(scan) -> tuple[list[tuple[str, str, str]], list[tuple[str, str]]]:
    tokens, stray = [], []
    for text, classes, slide in scan.free:
        covered = []
        for pattern, need, kind in ALLOWED:
            if need and need not in classes:
                continue
            for m in re.finditer(pattern, text.strip() if kind == "slide" else text):
                covered.append(m.span() if kind != "slide" else (0, len(text)))
                tokens.append((kind, m.group(0), slide))
        for d in re.finditer(r"\d+", text):
            if not any(a <= d.start() and d.end() <= b for a, b in covered):
                stray.append((d.group(0), text.strip()[:80]))
    return tokens, stray


def test_no_digit_on_the_deck_is_untraced(scan) -> None:
    _, stray = _allowed_tokens(scan)
    assert not stray, stray[:10]


def test_every_identifier_shown_exists_in_its_source(scan) -> None:
    register = show("docs/DECISIONS.md")
    review = show("out/review/REVIEW.md")
    tokens, _ = _allowed_tokens(scan)
    nns = {c.nn for c in cases.CASES}
    files = subprocess.run(
        ["git", "-C", str(REPO), "ls-tree", "-r", "--name-only", REF],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    for kind, token, slide in tokens:
        if kind == "register":
            assert f"**{token} · " in register, token
        elif kind == "claim":
            assert f"#### {token}." in review, token
        elif kind == "section":
            assert re.search(rf"^#{{2,3}} {re.escape(token[1:])}[. ]", review, re.M), token
        elif kind == "rule":
            assert token in register, token
        elif kind == "case":
            assert re.search(rf"^\| {token} \|", review, re.M), token
        elif kind == "demo":
            assert token[-2:] in nns, token
        elif kind == "method":
            assert "BM25" in register
        elif kind == "electrolyte":
            assert "1:1 electrolyte" in review
        elif kind == "temperature":
            assert "1:1 electrolyte, water, 25 °C" in review
        elif kind == "slide":
            assert slide == f"s{int(token)}", (token, slide)
        elif kind == "path":
            assert any(f == token or f.endswith("/" + token) for f in files), token


def test_the_data_is_inlined_whole(deck, page) -> None:
    m = re.search(r'<script type="application/json" id="deck-data">(.*?)</script>', page, re.S)
    assert m and json.loads(m.group(1)) == json.loads(json.dumps(deck))


def test_sixteen_slides_each_with_a_title_a_message_and_notes(page) -> None:
    slides = re.findall(
        r'<section class="slide[^"]*" id="(s\d+)"(.*?)</section>'
        r'\s*(?=<section class="slide|</main>)',
        page,
        re.S,
    )
    assert [s for s, _ in slides] == [f"s{i}" for i in range(1, 17)]
    for sid, body in slides:
        assert re.search(r"<h[12]>", body), sid
        assert sid == "s1" or 'class="msg"' in body, sid
        notes = re.findall(r'<aside class="notes"[^>]*>(.*?)</aside>', body, re.S)
        assert len(notes) == 1, sid
        prose = re.sub(r"<[^>]+>", "", re.sub(r'<span class="label">[^<]*</span>', "", notes[0]))
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", prose.strip()) if s]
        assert 2 <= len(sentences) <= 4, (sid, len(sentences))


def test_the_page_follows_the_artifact_contract(page) -> None:
    title = one(page, r"<title>([^<]+)</title>")[0]
    assert 2 <= len(title.split()) <= 4 and ":" not in title
    assert not re.search(r"<!doctype|<(?:html|head|body)[\s>]", page, re.I)
    hosts = set(re.findall(r"https?://([^/\"' )]+)", page))
    assert hosts <= {"fonts.googleapis.com", "fonts.gstatic.com"}, hosts
    for banned in ("window.print", "alert(", "confirm(", " download", "localStorage"):
        assert banned not in page, banned
    style = page.split("<style>", 1)[1].split("</style>", 1)[0]
    root = set(re.findall(r"(--[\w-]+):", one(style, r"(?s):root \{(.*?)\}")[0]))
    dark_media = one(style, r"(?s):root:not\(\[data-theme=\"light\"\]\) \{(.*?)\}")[0]
    dark_attr = one(style, r"(?s):root\[data-theme=\"dark\"\] \{(.*?)\}")[0]
    assert "@media (prefers-color-scheme: dark)" in style
    for block in (dark_media, dark_attr):
        assert "color-scheme: dark" in block
        assert set(re.findall(r"(--[\w-]+):", block)) == root - {"--display", "--text", "--mono"}
    assert re.search(r"body \{[^}]*background: var\(--paper\)", style)
    markup = page.split("<main", 1)[1].split("<script", 1)[0]
    assert ".notes { display: none; }" in style and "show-notes" not in markup
    assert ":focus-visible" in style and "prefers-reduced-motion" in page
