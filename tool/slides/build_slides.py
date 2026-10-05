"""Build the conference deck, `tool/slides/slides.html`, from one committed snapshot.

The deck is the results page's sibling (`tool/viz/`). Every number on a slide is a value in the
deck's data, read with `git show <ref>:<path>` or computed by the repo's own code fed that
snapshot, and stored with its source. `template.html` holds the words and `{{key}}` slots: a
slot becomes `<span data-k="key">` around the value's text, each `{{svg:name}}` becomes a chart
drawn here from the same values, and the data is inlined as JSON the way
`tool/viz/build_page.py` does it.

The run first builds the results page's data at the same ref (`tool/viz/build_data.py`), whose
checks hold 149 numbers against REVIEW.md, and stops if any disagree. The only things typed
here are identifiers: the final grid's run ids, the paper and commit of the cited-value example,
and the words that name fields.

    unset VIRTUAL_ENV
    uv run python tool/slides/build_slides.py [--ref HEAD] [--out tool/slides/slides.html]
"""

from __future__ import annotations

import argparse
import csv
import html
import importlib.util
import io
import json
import math
import re
from collections import Counter
from pathlib import Path

import pandas as pd

from mnp.demo import cases, harmonise
from mnp.eval import comparability, scoring
from mnp.eval.query_sets import QueryKind

HERE = Path(__file__).resolve().parent
VIZ = HERE.parent / "viz"


def _viz(name: str):
    spec = importlib.util.spec_from_file_location(name, VIZ / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_data = _viz("build_data")
build_page = _viz("build_page")
show = build_data.show

# The grid runs are the ones REVIEW.md C9 reports at the same ref (build_data.grid_runs), so
# the deck and the guide can never show two different grids.
# The cited-value example (slide 11): the paper, and the commit at which its recorded row was the
# value another study measured (EX-09's re-read control was committed there).
CITED_PMCID = "PMC12280233"
CITED_BEFORE = "09c11cd"
REREAD = "data/interim/reread_control"

FIELD_WORDS = {
    "ionic_strength": "ionic strength",
    "pH": "pH",
    "temperature": "temperature",
    "medium": "medium",
    "size_measured_nm": "measured size",
    "functionalisation": "surface chemistry",
    "instrument": "instrument",
}
METHOD_ROWS = {
    "medium_reported": "medium",
    "ionic_strength_reported": "ionic strength (mM)",
    "pH_reported": "pH",
    "temperature_reported": "temperature (°C)",
    "instrument_reported": "instrument",
}
SLOT = re.compile(r"\{\{([\w.:-]+)\}\}")

NBSP, MINUS = "\u00a0", "\u2212"


def num(x: float, d: int = 0) -> str:
    s = f"{abs(x):,.{d}f}".replace(",", NBSP)
    negative = x < 0 and float(s.replace(NBSP, "")) != 0
    return (MINUS if negative else "") + s


def flat(text: str) -> str:
    """A Markdown file's prose with its line wrapping folded, so a phrase can be found whole."""
    return re.sub(r"\s+", " ", text)


def find(doc: str, text: str, pattern: str) -> tuple[str, ...]:
    m = re.search(pattern, text)
    if m is None:
        raise SystemExit(f"{doc} no longer matches: {pattern}")
    return m.groups()


def blank(s) -> bool:
    return s is None or (isinstance(s, float) and math.isnan(s)) or not str(s).strip()


class Values:
    """Every value a slide shows: its raw value, the text shown, and where it comes from."""

    def __init__(self) -> None:
        self.v: dict[str, dict] = {}

    def _put(self, key: str, kind: str, raw, text: str, src: str, **extra) -> None:
        if key in self.v:
            raise ValueError(f"value {key} is set twice")
        self.v[key] = {"kind": kind, "v": raw, "text": text, "src": src, **extra}

    def int(self, key: str, n: int, src: str) -> None:
        self._put(key, "int", int(n), num(n), src)

    def year(self, key: str, n: int, src: str) -> None:
        self._put(key, "year", int(n), str(int(n)), src)

    def float(self, key: str, x: float, d: int, src: str) -> None:
        self._put(key, "float", float(x), num(x, d), src, d=d)

    def pct(self, key: str, share: float, d: int, src: str) -> None:
        self._put(key, "pct", float(share), f"{num(share * 100, d)}{NBSP}%", src, d=d)

    def frac(self, key: str, a: int, b: int, src: str) -> None:
        self._put(key, "frac", [int(a), int(b)], f"{num(a)}{NBSP}/{NBSP}{num(b)}", src)

    def mega(self, key: str, n: int, d: int, src: str) -> None:
        self._put(key, "mega", int(n), f"{num(n / 1e6, d)}{NBSP}M", src, d=d)

    def text(self, key: str, s: str | None, src: str, empty: str = "not stated") -> None:
        """Words as the source prints them: a quote, an id, a unit. Shown in the mono face."""
        self._put(key, "text", s, empty if s is None else s, src, style="q")

    def words(self, key: str, s: str, src: str) -> None:
        """A name or a sentence read from a source, shown in the running text's face."""
        self._put(key, "text", s, s, src, style="t")

    def tick(self, key: str, x: float, d: int, chart: str, axis: str) -> None:
        self._put(
            key,
            "tick",
            float(x),
            num(x, d),
            f"axis tick of chart {chart}",
            d=d,
            chart=chart,
            axis=axis,
        )


# ---- the slides' values ---------------------------------------------------------------------


def corpus_values(V: Values, ref: str, base: dict) -> None:
    funnel = {s["label"]: s["n"] for s in base["funnel"]}
    V.int("papers_read", funnel["full texts fetched"], "data/raw/epmc/manifest.sha256 (XMLs)")
    records = [ln for ln in show(ref, "data/interim/extractions.jsonl").splitlines() if ln.strip()]
    V.int("records", len(records), "data/interim/extractions.jsonl (one record per paper read)")
    V.int("rows", funnel["measurement rows"], "out/tables/d1_zeta_table.csv")
    V.int("row_papers", funnel["papers with a measurement"], "out/tables/d1_zeta_table.csv")
    licence = flat(show(ref, "out/release/LICENSE"))
    name, author, short = find(
        "out/release/LICENSE",
        licence,
        r"Attribution: \"(.+?) — .+?\", by ([^.]+)\. Licensed under "
        r"(CC BY [\d.]+),",
    )
    V.words("dataset", name, "out/release/LICENSE, attribution line")
    V.words("author", author, "out/release/LICENSE, attribution line")
    V.words("licence", short, "out/release/LICENSE, attribution line")


def _rows_by_id(text: str) -> dict[str, dict]:
    return {r["row_id"]: r for r in csv.DictReader(io.StringIO(text))}


def case14(V: Values, charts: dict, d1: dict, harm: dict, table: pd.DataFrame, base: dict) -> None:
    case = next(c for c in cases.CASES if c.nn == "14")
    first, second = case.pair
    a, b = d1[first], d1[second]
    src = "out/tables/d1_zeta_table.csv, case 14's pair (src/mnp/demo/cases.py)"
    for field in ("medium_text", "ionic_strength_mM", "pH", "temperature_C", "size_nominal_nm"):
        assert a[field] == b[field], (field, a[field], b[field])
    instrument = a["instrument"].split(" (")[0]
    assert b["instrument"].startswith(instrument + " ("), (a["instrument"], b["instrument"])

    rows = [comparability.ZetaRow.from_mapping(r) for r in table.to_dict(orient="records")]
    cross = [s for s in comparability.comparable_census(rows) if s.a.pmcid != s.b.pmcid]
    assert [(s.a.row_id, s.b.row_id) for s in cross] == [case.pair], cross
    assert base["census"]["comparable_cross"] == 1

    lab = find("src/mnp/demo/cases.py case 14", case.why, r"from one laboratory \(([^;]+);")[0]
    # cases.py spells the city in ASCII; the slide gives it its Polish name.
    V.words("c14.lab", lab, "src/mnp/demo/cases.py, case 14 why")
    V.text("c14.medium", a["medium_text"], src)
    V.float("c14.pH", float(a["pH"]), 1, src)
    V.float("c14.T", float(a["temperature_C"]), 0, src)
    V.text("c14.instrument", instrument, src)
    V.int("c14.size_nominal", float(a["size_nominal_nm"]), src)
    for side, r in (("a", a), ("b", b)):
        h = harm[r["row_id"]]
        V.text(f"c14.{side}.pmcid", r["pmcid"], src)
        V.year(f"c14.{side}.year", int(r["year"]), src)
        V.float(f"c14.{side}.value", float(r["value"]), 1, src)
        sd = r["sd"]
        V.float(f"c14.{side}.sd", float(sd), len(sd.split(".")[1]) if "." in sd else 0, src)
        V.float(f"c14.{side}.size", float(r["size_measured_nm"]), 1, src)
        V.text(f"c14.{side}.supplier", r["supplier"] or None, src)
        hsrc = "out/review/harmonised_all_rows.csv (case Z3: f_m open, κa known)"
        V.float(f"c14.{side}.lo", float(h["low"]), 1, hsrc)
        V.float(f"c14.{side}.hi", float(h["high"]), 1, hsrc)
    V.int("c14.years", int(b["year"]) - int(a["year"]), src)
    V.float("c14.gap", abs(float(a["value"]) - float(b["value"])), 1, src)
    upper, lower = sorted((harm[first], harm[second]), key=lambda h: float(h["high"]))
    gap = float(lower["low"]) - float(upper["high"])
    assert gap > 0, "case 14's harmonised intervals overlap"
    V.float("c14.igap", gap, 1, "out/review/harmonised_all_rows.csv")

    marks = [float(harm[i][k]) for i in case.pair for k in ("low", "high")]
    charts["c14"] = _mv_axis(V, "c14", marks)


def _mv_axis(V: Values, chart: str, marks: list[float]) -> dict:
    lo, hi = math.floor(min(marks) / 10) * 10, math.ceil(max(marks) / 10) * 10
    for i, t in enumerate(range(lo, hi + 1, 10)):
        V.tick(f"{chart}.x.{i}", t, 0, chart, "x")
    return {"x": [lo, hi], "marks": marks}


def case02(V: Values, charts: dict, table: pd.DataFrame) -> None:
    case = next(c for c in cases.CASES if c.nn == "02")
    rows = table[table["pmcid"] == case.pmcid].sort_values("row_id").to_dict(orient="records")
    src = f"out/tables/d1_zeta_table.csv, {case.pmcid} (case 02)"
    assert len(rows) == 3 and len({r["medium_class"] for r in rows}) == 3
    assert not any(r["ionic_strength_reported"] for r in rows)
    for field in ("pH", "temperature_C", "instrument", "size_nominal_nm", "supplier"):
        assert len({r[field] for r in rows}) == 1, field
    r0 = rows[0]
    V.text("c02.pmcid", case.pmcid, src)
    V.float("c02.size", r0["size_nominal_nm"] / 1000, 2, src + ": size_nominal_nm in µm")
    V.text("c02.supplier", r0["supplier"], src)
    V.float("c02.pH", r0["pH"], 1, src)
    V.float("c02.T", r0["temperature_C"], 0, src)
    V.text("c02.instrument", r0["instrument"], src)
    for i, r in enumerate(rows, 1):
        V.text(f"c02.r{i}.medium", r["medium_text"], src)
        V.float(f"c02.r{i}.value", r["value"], 2, src)
    values = [r["value"] for r in rows]
    V.float("c02.spread", max(values) - min(values), 2, src)
    charts["c02"] = _mv_axis(V, "c02", values)


def five_values(V: Values, ref: str, base: dict) -> None:
    method = show(ref, "out/demo/METHOD.md")
    for p in base["five"]["params"]:
        flag = p["key"]
        V.pct(f"five.{flag}", p["paper_mean_share"], 1, "out/review/conditions_per_paper.csv")
        cell = re.escape(METHOD_ROWS[flag])
        why = find("out/demo/METHOD.md", method, rf"(?m)^\| {cell} \| ([^|]+) \|")[0]
        V.words(f"five.why.{flag}", why.replace("**", "").strip(), "out/demo/METHOD.md")
    V.int("five.complete", base["five"]["complete_rows"], "out/tables/d1_zeta_table.csv")
    V.pct(
        "five.complete_paper",
        base["five"]["complete_paper_mean"],
        1,
        "out/review/conditions_per_paper.csv",
    )


def census_values(V: Values, charts: dict, base: dict) -> None:
    sp = base["same_particle"]
    src = "comparability.same_particle_census on out/tables/d1_zeta_table.csv"
    by = {c["key"]: c["pairs"] for c in sp["categories"]}
    V.int("sp.pairs", sp["pairs"], src)
    for key, n in by.items():
        V.int(f"sp.cat.{key}", n, src)
    V.pct("sp.cat_pct.stated_difference", by["stated_difference"] / sp["pairs"], 1, src)
    V.pct("sp.absence_pct", by["lost_to_absence"] / sp["pairs"], 1, src)
    V.int("sp.absence_cross", sp["absence_cross"], src)
    for f in sp["fields"]:
        V.int(f"sp.field.{f['field']}.pairs", f["pairs"], src)
        V.int(f"sp.field.{f['field']}.only", f["only"], src)
    top = sp["fields"][0]
    assert top["field"] == "ionic_strength", top
    V.pct("sp.top_pct", top["pairs"] / by["lost_to_absence"], 1, src)
    V.int("sp.only_total", sum(f["only"] for f in sp["fields"]), src)
    end = by["lost_to_absence"]
    for i, t in enumerate(range(0, end + 1, 10_000)):
        V.tick(f"fields.x.{i}", t, 0, "fields", "x")
    charts["fields"] = {"x": [0, end], "marks": [f["pairs"] for f in sp["fields"]]}
    charts["census"] = {
        "order": [
            "stated_difference",
            "lost_to_absence",
            "undecidable",
            "conditionally_comparable",
            "comparable",
        ]
    }


def rules_values(V: Values, ref: str) -> None:
    dec = flat(show(ref, "docs/DECISIONS.md"))
    review = flat(show(ref, "out/review/REVIEW.md"))
    D, R = "docs/DECISIONS.md", "out/review/REVIEW.md"
    V.text(
        "ai.defaults",
        find(D, dec, r"give a missing condition a default \(([^)]+)\)")[0],
        D + " RC-05",
    )
    V.text("r1.example", find(R, review, r"\"(cation type 0[^\"]*)\"")[0], R + " §8 item 14")
    pmcid, label, rows = find(D, dec, r"Why: (PMC\d+) labels its media \"([^\"]+)\"\. (\d+) rows")
    V.text("r2.pmcid", pmcid, D + " RC-09")
    V.text("r2.example", label, D + " RC-09")
    V.int("r2.rows", int(rows), D + " RC-09")
    V.text(
        "r3.example",
        find(D, dec, r"Question: \"([^\"]+)\" was stored as a reported")[0],
        D + " RC-10",
    )
    ions = r"Why: (\d+ mM phosphate at pH \d+ holds about \d+ mM of ions)"
    V.words("r3.ions", find(D, dec, ions)[0], D + " RC-10")


def line_values(V: Values, d1: dict, table: pd.DataFrame) -> None:
    case = next(c for c in cases.CASES if c.nn == "14")
    row = d1[case.pair[0]]
    src = f"out/tables/d1_zeta_table.csv, {row['row_id']}"
    V.text("arch.row_id", row["row_id"], src)
    V.text("arch.quote", row["evidence_quote"].split(" || ")[0], src + ": evidence_quote")
    V.text("arch.lines", row["evidence_line_ids"], src + ": evidence_line_ids")
    V.text("arch.location", row["evidence_location"], src + ": evidence_location")
    verified = int(table["evidence_verified"].sum())
    V.frac("arch.verified", verified, len(table), "out/tables/d1_zeta_table.csv: evidence_verified")


def henry_values(V: Values, charts: dict, harm_rows: list[dict], base: dict, d1: dict) -> None:
    case = next(c for c in cases.CASES if c.nn == "14")
    size = float(d1[case.pair[0]]["size_nominal_nm"])
    module = "src/mnp/eval/comparability.py"
    V.float("h.radius", size / 2, 0, "case 14's nominal size, halved")
    V.float("h.debye_c", comparability.debye_length_nm(1000.0), 3, module + " debye_length_nm")
    f_lo, f_hi = comparability.henry_f(0.0), comparability.henry_f(1e6)
    V.float("h.f_lo", f_lo, 1, module + " henry_f")
    V.float("h.f_hi", f_hi, 1, module + " henry_f")
    V.pct("h.hw_f", (f_hi - f_lo) / (f_hi + f_lo), 0, "f anywhere in [f_lo, f_hi]")
    *_, low, high, _point, _why = harmonise._zeta_case(1.0, None, frozenset())
    V.pct("h.hw_z4", (high - low) / (high + low), 0, "src/mnp/demo/harmonise.py case Z4")
    V.int("h.z4", base["harmonise"]["cases"]["Z4"], "out/review/harmonised_all_rows.csv")

    reported = [r for r in harm_rows if r["ionic_strength_reported"] == "True"]
    points = [
        [float(r["ionic_strength_mM"]), float(r["henry_f"])]
        for r in reported
        if not blank(r["kappa_a"])
    ]
    rug = [float(r["ionic_strength_mM"]) for r in reported if blank(r["kappa_a"])]
    hsrc = "out/review/harmonised_all_rows.csv"
    V.int("h.points", len(points), hsrc + ": ionic strength and size reported")
    V.int("h.rug", len(rug), hsrc + ": ionic strength reported, size not")
    V.int("h.band", len(harm_rows) - len(reported), hsrc + ": ionic strength unreported")
    xs = [p[0] for p in points] + rug
    lo, hi = math.floor(math.log10(min(xs))), math.ceil(math.log10(max(xs)))
    for i, e in enumerate(range(lo, hi + 1)):
        V.tick(f"henry.x.{i}", 10.0**e, max(0, -e), "henry", "x")
    for i in range(6):
        V.tick(f"henry.y.{i}", f_lo + i * (f_hi - f_lo) / 5, 1, "henry", "y")
    radius = size / 2
    curve = []
    for i in range(161):
        mM = 10 ** (lo + (hi - lo) * i / 160)
        curve.append([mM, comparability.henry_f(radius / comparability.debye_length_nm(mM))])
    charts["henry"] = {
        "x": [10.0**lo, 10.0**hi],
        "y": [f_lo, f_hi],
        "points": points,
        "rug": rug,
        "curve": curve,
    }


def reread_values(V: Values, ref: str) -> None:
    s = json.loads(show(ref, f"{REREAD}/summary.json"))["A_vs_B"]
    src = f"{REREAD}/summary.json"
    V.int("rr.papers", s["papers"], src)
    V.int("rr.same_count", s["papers_same_row_count"], src)
    V.int("rr.rows_a", s["rows"][0], src)
    V.int("rr.rows_b", s["rows"][1], src)
    V.int("rr.matched", s["row_pairs_matched_by_value"], src)
    for flag, c in s["per_condition"].items():
        V.frac(f"rr.agree.{flag}", c["row_pairs_agreeing"], s["row_pairs_matched_by_value"], src)
    dec = flat(show(ref, "docs/DECISIONS.md"))
    cited = find(
        "docs/DECISIONS.md", dec, r"In (\d+) of the \d+ papers the recorded rows are values"
    )
    V.int("rr.cited", int(cited[0]), "docs/DECISIONS.md EX-09")


def gallery_values(V: Values, ref: str) -> None:
    dec = flat(show(ref, "docs/DECISIONS.md"))
    D = "docs/DECISIONS.md"
    record = next(
        json.loads(ln)
        for ln in show(ref, "data/interim/extractions.jsonl").splitlines()
        if f'"pmcid": "{CITED_PMCID}"' in ln
    )
    assert record["measurements"] == [], "the cited value is back in the record"
    for reading in ("A", "B"):
        blind = json.loads(show(ref, f"{REREAD}/{reading}-{CITED_PMCID}.json"))
        assert blind["measurements"] == [], (reading, CITED_PMCID)
    context = " ".join(c["context"] for c in record["unmatched_candidates"])
    quote = find(
        f"extractions.jsonl {CITED_PMCID}",
        context,
        r"(a zeta potential of .*?\([A-Z][a-z]+ et al\. \d{4}\))",
    )[0]
    before = next(
        json.loads(ln)
        for ln in show(CITED_BEFORE, "data/interim/extractions.jsonl").splitlines()
        if f'"pmcid": "{CITED_PMCID}"' in ln
    )
    assert any(quote in m["evidence"]["quote"] for m in before["measurements"]), CITED_BEFORE
    V.text("g.cited.pmcid", CITED_PMCID, "data/interim/extractions.jsonl")
    V.text("g.cited.quote", quote, f"data/interim/extractions.jsonl; a row at {CITED_BEFORE}")
    V.text("g.n.pmcid", find(D, dec, r"(PMC\d+) carried an n the paper never states")[0], D)
    V.text(
        "g.dlvo.pmcid", find(D, dec, r"(PMC\d+) recorded DLVO model inputs as measurements")[0], D
    )
    V.text(
        "g.twice.pmcid",
        find(D, dec, r"(PMC\d+) \(one reading counted as both zeta and mobility\)")[0],
        D,
    )
    V.int("g.reread", int(find(D, dec, r"\*\*EX-10 · Re-read the (\d+) papers")[0]), D + " EX-10")

    q = r"\"([^\"]+)\""
    molar, comma = find(D, dec, rf"printed in molar \({q}\) or with a decimal comma \({q}\)")
    v1, v2 = find(D, dec, rf"because the check looked for {q} and {q}")
    worker, harmed = find(D, dec, r"Worker (\w+) deleted (PMC\d+)'s value to clear the flag")
    V.text("gd.molar", molar, D + " EX-12")
    V.text("gd.comma", comma, D + " EX-12")
    V.text("gd.looked1", v1, D + " EX-12")
    V.text("gd.looked2", v2, D + " EX-12")
    V.text("gd.worker", worker, D + " EX-12")
    V.text("gd.harmed", harmed, D + " EX-12")
    unit, medium = find(
        D,
        dec,
        rf"- {q} / \"[^\"]+\": the exponent sat .*? a medium stating "
        r"([^,]+) recorded no ionic strength",
    )
    V.text("gd.mmol", unit, D + " EX-12")
    V.text("gd.mmol_text", medium, D + " EX-12")
    power, read_as = find(D, dec, rf"- {q} was read as (\S+ mM), and the rows dropped")
    V.text("gd.pow", power, D + " EX-12")
    V.text("gd.pow_read", read_as, D + " EX-12")
    V.text(
        "gd.kelvin",
        find(D, dec, rf"A temperature in kelvin \({q}\) was not found")[0],
        D + " EX-12",
    )
    V.text(
        "gd.step",
        find(D, dec, rf"read the whole quote passage, so {q} in the next")[0],
        D + " EX-12",
    )
    V.text("gd.asked", find(D, dec, rf"The re-read brief asked for {q}")[0], D + " EX-12")
    bpa, mm = find(D, dec, rf"{q}, a co-exposure, made (\S+ mM) look supported")
    V.text("gd.bpa", bpa, D + " EX-14")
    V.text("gd.bpa_mM", mm, D + " EX-14")
    V.int("gd.window", int(find(D, dec, r"comes within (\d+) characters after")[0]), D + " EX-14")


def _runs(ref: str) -> dict:
    out = {}
    for cell, run in build_data.grid_runs(ref).items():
        base = f"data/interim/runs/{run}"
        scored = build_data.load_scored(show(ref, f"{base}/scored.jsonl"))
        kinds = Counter()
        correct = Counter()
        for item in scored:
            kinds[item.kind.value] += 1
            correct[item.kind.value] += bool(item.correct)
        recall = {}
        for line in scoring.verdict_table(scored).splitlines()[1:]:
            _, verdict, n, right, value = line.split("\t")
            recall[verdict] = (int(n), None if right == "-" else int(right), float(value))
        answers = build_data.read_jsonl(ref, f"{base}/answers.jsonl")
        said = Counter()
        for a in answers:
            if a.get("kind") == QueryKind.e.value:
                parsed = scoring.parse_answer(a["qid"], a["cell"], a.get("text") or "")
                said["unreadable" if parsed.unparsed else parsed.payload.get("verdict")] += 1
        manifest = json.loads(show(ref, f"{base}/manifest.json"))
        out[cell] = {
            "kinds": kinds,
            "correct": correct,
            "recall": recall,
            "said": said,
            "tokens": sum(a.get("input_tokens") or 0 for a in answers),
            "model": manifest["model"],
            "asked": manifest["counts"]["asked"],
        }
    return out


def grid_values(V: Values, ref: str) -> None:
    g = _runs(ref)
    runs = build_data.grid_runs(ref)
    assert g["D"]["model"] == g["B"]["model"] and g["D"]["asked"] == g["B"]["asked"]
    src = "data/interim/runs/{}: scored.jsonl, answers.jsonl, manifest.json"
    V.text("gr.model", g["D"]["model"], src.format(runs["D"]))
    V.int("gr.asked", g["D"]["asked"], src.format(runs["D"]))
    for cell, r in g.items():
        s = src.format(runs[cell])
        V.text(f"gr.{cell}.run", runs[cell], s)
        n, right, _ = r["recall"]["comparable"]
        V.frac(f"gr.{cell}.comparable", right, n, s)
        V.float(f"gr.{cell}.bal", r["recall"]["balanced_accuracy"][2], 2, s)
        V.frac(f"gr.{cell}.C", r["correct"]["C"], r["kinds"]["C"], s)
        V.mega(f"gr.{cell}.tokens", r["tokens"], 2, s)
    b = g["B"]
    V.frac("gr.B.E", b["correct"]["E"], b["kinds"]["E"], src.format(runs["B"]))
    V.int("gr.B.said_not", b["said"]["not_comparable"], src.format(runs["B"]))


def scope_values(V: Values, base: dict) -> None:
    items = dict((lead, text) for lead, text in base["scope"]["items"])
    src = "mnp.report.scope, as REVIEW.md, the card and the results page open"
    origin = items["Where the particles came from."]
    V.words("sc.synthetic", origin.split(". ")[0] + ".", src)
    V.words("sc.corpus", items["The corpus."].split(" (`")[0] + ".", src)
    V.words("sc.use", items["What it can be used for."], src)


def audit_state(ref: str) -> None:
    """Slide 14 says no person has checked a row. Stop if the audit sheet holds a verdict."""
    rows = build_data.read_csv(ref, "out/review/audit_sample.csv")
    filled = [r["row_id"] for r in rows for k, v in r.items() if k.endswith("_ok") and v.strip()]
    if filled:
        raise SystemExit(f"audit_sample.csv holds verdicts ({filled[:3]}): slide 14 must change")


def build(ref: str) -> dict:
    base = build_data.build(ref)
    bad = [c for c in base["checks"] if not c["ok"]]
    if bad:
        raise SystemExit(f"{len(bad)} of build_data's checks against REVIEW.md disagree: {bad[:3]}")
    if "same_particle" not in base or "scope" not in base:
        raise SystemExit(f"{ref} predates the same-particle census; the deck needs it")
    audit_state(ref)

    d1_text = show(ref, "out/tables/d1_zeta_table.csv")
    table = pd.read_csv(io.StringIO(d1_text))
    d1 = _rows_by_id(d1_text)
    harm_text = show(ref, "out/review/harmonised_all_rows.csv")
    harm = _rows_by_id(harm_text)

    V, charts = Values(), {}
    corpus_values(V, ref, base)
    case14(V, charts, d1, harm, table, base)
    case02(V, charts, table)
    five_values(V, ref, base)
    census_values(V, charts, base)
    rules_values(V, ref)
    line_values(V, d1, table)
    henry_values(V, charts, list(harm.values()), base, d1)
    reread_values(V, ref)
    gallery_values(V, ref)
    grid_values(V, ref)
    scope_values(V, base)
    return {
        "ref": ref,
        "commit": base["commit"],
        "values": V.v,
        "charts": charts,
        "review_checks": {"n": len(base["checks"]), "ok": len(base["checks"]) - len(bad)},
    }


# ---- drawing ----------------------------------------------------------------------------------


def esc(s: str) -> str:
    return html.escape(s, quote=False)


def slots(text: str, values: dict, tag: str = "span") -> str:
    """`{{key}}` in plain text -> `<tag class=… data-k=key>value</tag>`, the rest escaped."""
    out, last = [], 0
    for m in SLOT.finditer(text):
        out.append(esc(text[last : m.start()]))
        out.append(_slot(m.group(1), values, tag))
        last = m.end()
    return "".join(out) + esc(text[last:])


def _slot(key: str, values: dict, tag: str) -> str:
    if key not in values:
        raise KeyError(f"slot {{{{{key}}}}} has no value")
    v = values[key]
    cls = v.get("style", "n")
    return f'<{tag} class="{cls}" data-k="{key}">{esc(v["text"])}</{tag}>'


def T(x: float, y: float, text: str, values: dict, cls: str = "", anchor: str = "start") -> str:
    c = f' class="{cls}"' if cls else ""
    a = "" if anchor == "start" else f' text-anchor="{anchor}"'
    return f'<text x="{x:.1f}" y="{y:.1f}"{c}{a}>{slots(text, values, "tspan")}</text>'


def svg(w: int, h: int, body: list[str], label: str, cls: str = "chart") -> str:
    return (
        f'<svg class="{cls}" viewBox="0 0 {w} {h}" preserveAspectRatio="xMinYMin meet" '
        f'role="img" aria-label="{html.escape(label)}">' + "".join(body) + "</svg>"
    )


def line(x1, y1, x2, y2, cls) -> str:
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" class="{cls}"/>'


def rect(x, y, w, h, cls, rx=0) -> str:
    r = f' rx="{rx}"' if rx else ""
    return (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w, 0):.2f}" height="{h:.1f}" class="{cls}"{r}/>'
    )


def _mv_scale(chart: dict, x0: float, x1: float):
    lo, hi = chart["x"]
    return lambda v: x0 + (v - lo) / (hi - lo) * (x1 - x0)


def _mv_ticks(values: dict, chart: str, sx, y: float, top: float) -> list[str]:
    keys = _ticks(values, chart, "x")
    out = [line(sx(values[keys[0]]["v"]), y, sx(values[keys[-1]]["v"]), y, "ax")]
    for key in keys:
        x = sx(values[key]["v"])
        out += [
            line(x, top, x, y, "grid"),
            line(x, y, x, y + 6, "ax"),
            T(x, y + 26, "{{" + key + "}}", values, "tick", "middle"),
        ]
    return out


def _ticks(values: dict, chart: str, axis: str) -> list[str]:
    prefix = f"{chart}.{axis}."
    return sorted((k for k in values if k.startswith(prefix)), key=lambda k: int(k.rsplit(".")[-1]))


def chart_c14(values: dict, charts: dict) -> str:
    W, H, x0, x1 = 900, 312, 190, 870
    sx = _mv_scale(charts["c14"], x0, x1)
    body = _mv_ticks(values, "c14", sx, 250, 20)
    ys = {"a": 78, "b": 178}
    for side, y in ys.items():
        lo, hi, mid = (sx(values[f"c14.{side}.{k}"]["v"]) for k in ("lo", "hi", "value"))
        body += [
            rect(lo, y - 13, hi - lo, 26, "iv", 2),
            f'<circle cx="{mid:.1f}" cy="{y}" r="8" class="pt"/>',
            T(mid, y - 24, "{{c14." + side + ".value}} mV", values, "val", "middle"),
            T(lo - 8, y + 6, "{{c14." + side + ".lo}}", values, "lim", "end"),
            T(hi + 8, y + 6, "{{c14." + side + ".hi}}", values, "lim", "start"),
            T(0, y - 2, "{{c14." + side + ".year}}", values, "row-h"),
            T(0, y + 22, "{{c14." + side + ".pmcid}}", values, "row-s"),
        ]
    a_hi, b_lo = values["c14.a.hi"]["v"], values["c14.b.lo"]["v"]
    ym = (ys["a"] + ys["b"]) / 2
    body += [
        line(sx(a_hi), ym, sx(b_lo), ym, "gap"),
        line(sx(a_hi), ym - 7, sx(a_hi), ym + 7, "gap"),
        line(sx(b_lo), ym - 7, sx(b_lo), ym + 7, "gap"),
        T((sx(a_hi) + sx(b_lo)) / 2, ym - 10, "{{c14.igap}} mV between", values, "gap-t", "middle"),
        T(x1, 306, "zeta potential (mV)", values, "ax-t", "end"),
    ]
    return svg(W, H, body, "Case 14: two zeta values with their harmonised intervals, apart")


def chart_c02(values: dict, charts: dict) -> str:
    W, H, x0, x1 = 620, 300, 20, 600
    sx = _mv_scale(charts["c02"], x0, x1)
    body = _mv_ticks(values, "c02", sx, 236, 10)
    for i, y in ((1, 48), (2, 108), (3, 168)):
        x = sx(values[f"c02.r{i}.value"]["v"])
        right = x > (x0 + x1) / 2
        body += [
            f'<circle cx="{x:.1f}" cy="{y}" r="8" class="pt"/>',
            T(
                x + (-16 if right else 16),
                y - 4,
                "{{c02.r" + str(i) + ".medium}}",
                values,
                "row-s",
                "end" if right else "start",
            ),
            T(
                x + (-16 if right else 16),
                y + 20,
                "{{c02.r" + str(i) + ".value}} mV",
                values,
                "val-s",
                "end" if right else "start",
            ),
        ]
    lo = sx(min(values[f"c02.r{i}.value"]["v"] for i in (1, 2, 3)))
    hi = sx(max(values[f"c02.r{i}.value"]["v"] for i in (1, 2, 3)))
    body += [
        line(lo, 200, hi, 200, "gap"),
        line(lo, 193, lo, 207, "gap"),
        line(hi, 193, hi, 207, "gap"),
        T((lo + hi) / 2, 192, "{{c02.spread}} mV", values, "gap-t", "middle"),
        T(x1, 290, "zeta potential (mV)", values, "ax-t", "end"),
    ]
    return svg(W, H, body, "Case 02: one particle in three liquids")


def chart_layer(values: dict, charts: dict) -> str:
    """A schematic of the electric double layer: not data, so no number on it."""
    W, H = 560, 380
    surface, slip, base_y, top_y = 110, 158, 300, 70
    zeta_y = 150
    debye = 95.0

    def psi(x: float) -> float:
        if x <= slip:
            return top_y + (zeta_y - top_y) * (x - surface) / (slip - surface)
        return base_y - (base_y - zeta_y) * math.exp(-(x - slip) / debye)

    pts = " ".join(f"{x:.1f},{psi(x):.1f}" for x in range(surface, 545, 4))
    body = [
        rect(0, 0, surface, H, "particle"),
        T(14, H - 14, "particle", values, "lab-b"),
        line(surface, base_y, W, base_y, "grid"),
    ]
    for i in range(8):
        body.append(T(surface - 14, 52 + i * 34, "−", values, "ion-n", "middle"))
        body.append(T(surface + 22, 52 + i * 34, "+", values, "ion-p", "middle"))
    for i in range(70):
        x = slip + 16 + (i * 67) % 370
        y = 44 + (i * 41) % 236
        keep = ((i * 37) % 100) / 100 < 0.15 + 0.85 * math.exp(-(x - slip) / 110)
        if keep and abs(y - psi(x)) > 20:
            sign, cls = ("+", "ion-p") if i % 4 else ("−", "ion-n")
            body.append(T(x, y, sign, values, cls + " faint", "middle"))
    kx = slip + debye
    body += [
        line(slip, 22, slip, base_y + 8, "slip"),
        T(slip + 6, 16, "slipping plane", values, "lab"),
        f'<polyline points="{pts}" class="psi"/>',
        f'<circle cx="{slip}" cy="{zeta_y}" r="6" class="pt"/>',
        T(slip + 12, zeta_y - 10, "ζ", values, "sym"),
        T(surface + 8, top_y - 12, "ψ", values, "sym"),
        line(slip, base_y + 30, kx, base_y + 30, "gap"),
        line(slip, base_y + 23, slip, base_y + 37, "gap"),
        line(kx, base_y + 23, kx, base_y + 37, "gap"),
        T(kx + 10, base_y + 36, "κ⁻¹, the Debye length", values, "lab"),
        T(W - 4, base_y - 8, "bulk liquid", values, "lab", "end"),
        T(W - 4, H - 6, "schematic, not to scale", values, "note", "end"),
    ]
    return svg(W, H, body, "The electric double layer around a particle", "chart layer")


def chart_census(values: dict, charts: dict) -> str:
    W, H, x0, x1, y, h = 960, 270, 10, 950, 96, 60
    total = values["sp.pairs"]["v"]
    order = charts["census"]["order"]
    sx = lambda n: (x1 - x0) * n / total  # noqa: E731
    body, x = [], x0
    cls = {
        "stated_difference": "seg-q",
        "lost_to_absence": "seg-a",
        "undecidable": "seg-i",
        "conditionally_comparable": "seg-i",
        "comparable": "seg-i",
    }
    for key in order:
        w = sx(values[f"sp.cat.{key}"]["v"])
        body.append(rect(x, y, w, h, cls[key]))
        x += w
    a0 = x0 + sx(values["sp.cat.stated_difference"]["v"])
    body += [
        T(x0, y - 44, "a stated difference", values, "seg-l"),
        T(
            x0,
            y - 16,
            "{{sp.cat.stated_difference}} pairs · {{sp.cat_pct.stated_difference}}",
            values,
            "seg-n",
        ),
        T(x1, y - 44, "lost only to absence", values, "seg-l abs", "end"),
        T(
            x1,
            y - 16,
            "{{sp.cat.lost_to_absence}} · {{sp.absence_pct}}",
            values,
            "seg-n abs",
            "end",
        ),
        line(a0, y - 60, a0, y + h, "tick-a"),
    ]
    end = x1
    callouts = [
        ("undecidable", "{{sp.cat.undecidable}} undecidable", "co"),
        (
            "conditionally_comparable",
            "{{sp.cat.conditionally_comparable}} conditionally comparable",
            "co",
        ),
        ("comparable", "{{sp.cat.comparable}} comparable", "co-b"),
    ]
    last = y + h + 34 + (len(callouts) - 1) * 32 - 6
    body.append(line(end, y + h, end, last, "lead"))
    for i, (_key, text, c) in enumerate(callouts):
        ty = y + h + 34 + i * 32
        body += [
            line(end - 10, ty - 6, end, ty - 6, "lead"),
            T(end - 16, ty, text, values, c, "end"),
        ]
    body.append(
        T(
            x0,
            y + h + 34,
            "every pair of rows with the same quantity, material and surface",
            values,
            "note",
        )
    )
    return svg(W, H, body, "Same-particle pairs by category, to scale")


def chart_fields(values: dict, charts: dict) -> str:
    sp_fields = [
        k.split(".")[2] for k in values if k.startswith("sp.field.") and k.endswith(".pairs")
    ]
    W, row, top = 960, 40, 40
    H = top + row * len(sp_fields) + 40
    x0, x1, only_x = 200, 770, 950
    end = charts["fields"]["x"][1]
    sx = lambda n: x0 + (x1 - x0) * n / end  # noqa: E731
    yb = top + row * len(sp_fields)
    body = [
        T(only_x, 22, "only this missing", values, "col-h", "end"),
        T(x0, 22, "pairs lost to absence that miss it", values, "col-h"),
    ]
    for key in _ticks(values, "fields", "x"):
        x = sx(values[key]["v"])
        body += [
            line(x, top - 8, x, yb, "grid"),
            T(x, yb + 24, "{{" + key + "}}", values, "tick", "middle"),
        ]
    body += [
        line(x1, top - 8, x1, yb, "ax"),
        T(x1, yb + 24, "{{sp.cat.lost_to_absence}}", values, "tick-b", "middle"),
    ]
    for i, f in enumerate(sp_fields):
        y = top + i * row
        n = values[f"sp.field.{f}.pairs"]["v"]
        body += [
            T(x0 - 14, y + 26, FIELD_WORDS[f], values, "row-l" + (" abs" if i == 0 else ""), "end"),
            rect(x0, y + 6, sx(n) - x0, row - 12, "bar-a" if i == 0 else "bar-s"),
            T(
                sx(n) - 10,
                y + 26,
                "{{sp.field." + f + ".pairs}}",
                values,
                "val-in-a" if i == 0 else "val-in",
                "end",
            ),
            T(only_x, y + 26, "{{sp.field." + f + ".only}}", values, "only", "end"),
        ]
    return svg(W, H, body, "Missing fields among the pairs lost to absence, ranked")


def chart_henry(values: dict, charts: dict) -> str:
    c = charts["henry"]
    W, H = 960, 330
    x0, x1, y0, y1 = 80, 690, 262, 26
    band_x, band_w = 762, 84
    lx0, lx1 = math.log10(c["x"][0]), math.log10(c["x"][1])
    flo, fhi = c["y"]
    sx = lambda v: x0 + (math.log10(v) - lx0) / (lx1 - lx0) * (x1 - x0)  # noqa: E731
    pad = (fhi - flo) * 0.04
    sy = lambda f: y0 - (f - flo + pad) / (fhi - flo + 2 * pad) * (y0 - y1)  # noqa: E731
    body = []
    for key in _ticks(values, "henry", "y"):
        y = sy(values[key]["v"])
        body += [
            line(x0, y, x1, y, "grid"),
            T(x0 - 10, y + 6, "{{" + key + "}}", values, "tick", "end"),
        ]
    for key in _ticks(values, "henry", "x"):
        x = sx(values[key]["v"])
        body += [
            line(x, y1, x, y0, "grid"),
            line(x, y0, x, y0 + 6, "ax"),
            T(x, y0 + 24, "{{" + key + "}}", values, "tick", "middle"),
        ]
    body.append(line(x0, y0, x1, y0, "ax"))
    for mM in c["rug"]:
        x = sx(mM)
        body.append(line(x, y0 - 12, x, y0 - 2, "rug"))
    curve = " ".join(f"{sx(m):.1f},{sy(f):.1f}" for m, f in c["curve"])
    body.append(f'<polyline points="{curve}" class="curve"/>')
    for mM, f in c["points"]:
        body.append(f'<circle cx="{sx(mM):.1f}" cy="{sy(f):.1f}" r="5" class="dot"/>')
    end_m, end_f = c["curve"][-1]
    body += [
        T(sx(end_m) + 8, sy(end_f) + 5, "{{c14.size_nominal}} nm", values, "lab"),
        T(x0 + 8, sy(fhi) - 9, "Smoluchowski limit", values, "lim-t"),
        T(x1 - 8, sy(flo) - 9, "Hückel limit", values, "lim-t", "end"),
        rect(band_x, sy(fhi), band_w, sy(flo) - sy(fhi), "band"),
        T(band_x + band_w / 2, sy(fhi) - 9, "no ionic strength", values, "band-t", "middle"),
        T(
            band_x + band_w / 2,
            (sy(fhi) + sy(flo)) / 2 + 4,
            "{{h.band}}",
            values,
            "band-n",
            "middle",
        ),
        T(band_x + band_w / 2, (sy(fhi) + sy(flo)) / 2 + 28, "rows", values, "band-t", "middle"),
        T(x1, y0 + 50, "ionic strength I (mM), log scale", values, "ax-t", "end"),
        f'<text x="20" y="{(y0 + y1) / 2:.1f}" class="ax-t" text-anchor="middle" '
        f'transform="rotate(-90 20 {(y0 + y1) / 2:.1f})">Henry’s function f(κa)</text>',
    ]
    return svg(W, H, body, "Henry's function against ionic strength, with the rows placed on it")


def chart_arch(values: dict, charts: dict) -> str:
    W, H, bh = 960, 340, 100
    top = [
        ("paper", "JATS XML,", "{{papers_read}} full texts", "box"),
        ("line-addressed text", "every paragraph", "gets a line id", "box"),
        ("Claude agent worker", "reads every line", "under one brief", "box-m"),
        ("verbatim quote", "with the addresses", "of its lines", "box"),
    ]
    bottom = [
        ("verifier", "is the quote", "in the paper?", "box"),
        ("“not reported”", "stored as", "a value", "box-a"),
        ("table", "{{rows}} rows,", "{{row_papers}} papers", "box"),
        ("comparability", "and the census,", "decided in code", "box"),
        ("rebuild", "report reproduce,", "byte for byte", "box"),
    ]
    body = [
        '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" '
        'class="arrowhead"/></marker></defs>',
        T(W, 22, "a model reads", values, "lane", "end"),
        T(W, 212, "code decides", values, "lane", "end"),
    ]

    def lane(items, y, w, gap):
        out, xs = [], []
        for i, (title, sub1, sub2, cls) in enumerate(items):
            x = i * (w + gap)
            xs.append(x)
            head = "box-t abs" if cls == "box-a" else "box-t"
            out += [
                rect(x, y, w, bh, cls, 3),
                T(x + 12, y + 32, title, values, head),
                T(x + 12, y + 60, sub1, values, "box-s"),
                T(x + 12, y + 82, sub2, values, "box-s"),
            ]
            if i:
                out.append(line(x - gap + 3, y + bh / 2, x - 3, y + bh / 2, "arrow"))
        return out, xs

    t, txs = lane(top, 34, 222, 24)
    b, bxs = lane(bottom, 224, 172, 25)
    qx, bx = txs[-1] + 111, bxs[0] + 86
    body += t + b
    body.append(
        f'<polyline points="{qx},{34 + bh} {qx},{180} {bx},{180} {bx},{221}" class="arrow"/>'
    )
    return svg(
        W,
        H,
        body,
        "From paper to table: the reading is a model's, every decision is code's",
        "chart arch",
    )


CHARTS = {
    "c14": chart_c14,
    "c02": chart_c02,
    "layer": chart_layer,
    "census": chart_census,
    "fields": chart_fields,
    "henry": chart_henry,
    "arch": chart_arch,
}


def bars(deck: dict, template: str) -> str:
    """`{{w:key}}` -> a bar's CSS width: a fraction's share, or a share of the largest of a set."""
    values = deck["values"]

    def width(m: re.Match) -> str:
        key = m.group(1)
        v = values[key]
        if v["kind"] == "frac":
            share = v["v"][0] / v["v"][1]
        elif v["kind"] in ("pct", "float"):
            share = v["v"]
        else:  # a count, against the largest of its kind across the cells (the token bars)
            peers = [
                x["v"]
                for k, x in values.items()
                if k.rsplit(".", 1)[-1] == key.rsplit(".", 1)[-1] and x["kind"] == v["kind"]
            ]
            share = v["v"] / max(peers)
        return f"{share * 100:.2f}%"

    return re.sub(r"\{\{w:([\w.:-]+)\}\}", width, template)


def render(deck: dict, template: str | None = None) -> str:
    if template is None:
        template = (HERE / "template.html").read_text(encoding="utf-8")
    values = deck["values"]
    page = bars(deck, template)
    page = re.sub(r"\{\{svg:(\w+)\}\}", lambda m: CHARTS[m.group(1)](values, deck["charts"]), page)
    page = SLOT.sub(lambda m: _slot(m.group(1), values, "span"), page)
    return build_page.inline(page, deck)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ref", default="HEAD", help="git ref to read every input from")
    ap.add_argument("--out", default=str(HERE / "slides.html"))
    args = ap.parse_args()

    deck = build(args.ref)
    out = Path(args.out)
    out.write_text(render(deck), encoding="utf-8")
    rc = deck["review_checks"]
    print(f"{args.ref} ({deck['commit']}): wrote {out}, {out.stat().st_size:,} bytes")
    print(
        f"{len(deck['values'])} values; build_data's checks against REVIEW.md: {rc['ok']}/{rc['n']}"
    )


if __name__ == "__main__":
    main()
