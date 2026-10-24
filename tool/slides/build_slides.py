"""Build the conference deck, `tool/slides/slides.html`, from one committed snapshot.

The deck is the results page's sibling (`tool/viz/`). Every number on a slide is a value in the
deck's data, read with `git show <ref>:<path>` or computed by the repo's own code fed that
snapshot, and stored with its source. `template.html` holds the words and `{{key}}` slots: a
slot becomes `<span data-k="key">` around the value's text, each `{{svg:name}}` becomes a chart
drawn here from the same values, and the data is inlined as JSON the way
`tool/viz/build_page.py` does it.

The run first builds the results page's data at the same ref (`tool/viz/build_data.py`), whose
checks hold its numbers against REVIEW.md, and stops if any disagree. The only things typed
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
import inspect
import io
import json
import math
import re
import subprocess
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from mnp.demo import cases, harmonise
from mnp.ek import constants, hard, soft
from mnp.ek.qa import MU_UNIT
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
# The cited-value example (slide 34): the paper, and the commit at which its recorded row was the
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
# The liquids of slide 27, as `medium_class` names them.
MEDIUM_WORDS = {
    "DI_water": "DI water",
    "unreported": "liquid not named",
    "culture_medium": "culture medium",
    "other": "other liquids",
    "salt_solution": "salt solution",
    "buffer": "buffer",
    "environmental_water": "environmental water",
    "biofluid": "biofluid",
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


def si_values(V: Values, ref: str, base: dict) -> None:
    """Slide 15: ionic strength once the supplements are read too (the 2026-10-12 SI census)."""
    si = json.loads(show(ref, SI_RATES))
    main = next(p for p in base["five"]["params"] if p["key"] == "ionic_strength_reported")
    if abs(si["main_text"]["paper_mean_pct"] / 100 - main["paper_mean_share"]) > 5e-4:
        raise SystemExit(f"{SI_RATES} counted a different main text than slide 15's bar")
    V.pct("si.mean", si["main_plus_si"]["paper_mean_pct"] / 100, 1, SI_RATES + ": main_plus_si")
    V.int("si.new", si["accepted_papers_new"], SI_RATES + ": accepted_papers_new")


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


def _mM(V: Values, key: str, x: float, src: str) -> None:
    V.float(key, x, 0 if float(x).is_integer() else 1, src)


def lab_values(V: Values, charts: dict, table: pd.DataFrame) -> None:
    """Slide 27: whether a row states its ionic strength depends on the liquid, and where it is
    stated it runs over decades, so "a lab uses water" is not one value to fill in."""
    src = "out/tables/d1_zeta_table.csv: medium_class, ionic_strength_reported, ionic_strength_mM"
    stated = table[table["ionic_strength_reported"].astype(bool)]
    order = table["medium_class"].value_counts().index.tolist()
    unknown = set(order) - set(MEDIUM_WORDS)
    if unknown:
        raise SystemExit(f"slide 27 has no words for medium_class {sorted(unknown)}")
    points = {}
    for c in order:
        mM = stated.loc[stated["medium_class"] == c, "ionic_strength_mM"].astype(float)
        V.int(f"lab.{c}.rows", int((table["medium_class"] == c).sum()), src)
        V.int(f"lab.{c}.stated", len(mM), src)
        if len(mM) and mM.min() != mM.max():
            _mM(V, f"lab.{c}.lo", mM.min(), src)
            _mM(V, f"lab.{c}.hi", mM.max(), src)
        elif len(mM):
            _mM(V, f"lab.{c}.at", mM.min(), src)
        points[c] = sorted(set(mM.tolist()))
    salt = table[table["medium_class"] == "salt_solution"]
    V.pct("lab.salt.share", float(salt["ionic_strength_reported"].astype(bool).mean()), 0, src)
    every = stated["ionic_strength_mM"].astype(float)
    lo, hi = float(every.min()), float(every.max())
    _mM(V, "lab.lo", lo, src)
    _mM(V, "lab.hi", hi, src)
    e0, e1 = math.floor(math.log10(lo)), math.ceil(math.log10(hi))
    for i, e in enumerate(range(e0, e1 + 1)):
        V.tick(f"lab.x.{i}", 10.0**e, max(0, -e), "lab", "x")
    charts["lab"] = {
        "x": [10.0**e0, 10.0**e1],
        "order": order,
        "points": points,
        "rows": int(table["medium_class"].value_counts().max()),
        "marks": [lo, hi],
    }


def curve_values(V: Values, charts: dict) -> None:
    """Slide 23 (backup): the method the talk started from. One hard and two soft particles,
    matched to the same mobility at one ionic strength by the physics demo's own figure function,
    so one zeta cannot tell them apart while the curves across salt can."""
    from mnp.infer import figures

    src = "src/mnp/infer/figures.py same_zeta_figure"
    p = {
        k: v.default
        for k, v in inspect.signature(figures.same_zeta_figure).parameters.items()
        if v.default is not inspect.Parameter.empty
    }
    salt, T = p["I_match_mM"], p["T_C"]
    radius_m = p["hard_radius_nm"] * 1e-9
    match = float(hard.mobility_hard(p["hard_sigma_C_m2"], radius_m, salt, T_C=T) / MU_UNIT)
    zeta = 1e3 * constants.viscosity(T) * match * MU_UNIT / constants.permittivity(T)
    V.float("curve.I", salt, 0, src + ", the matching ionic strength (mM)")
    V.float("curve.T", T, 0, src + ", the temperature (°C)")
    V.float("curve.zeta", zeta, 0, src + ": the matched mobility as a Smoluchowski zeta (mV)")
    grid = np.logspace(-1, 3, 161)
    softs = []
    for lam in p["soft_lambda_inv_nm"]:
        zn = figures.match_soft_to_mobility(match, lam, salt, T)
        mu = soft.mobility_soft(zn, lam * 1e-9, grid, T_C=T) / MU_UNIT
        plateau = float(soft.plateau_mobility(zn, lam * 1e-9, T) / MU_UNIT)
        softs.append({"lambda_inv_nm": lam, "mu": mu.tolist(), "plateau": plateau})
    hard_mu = (hard.mobility_hard(p["hard_sigma_C_m2"], radius_m, grid, T_C=T) / MU_UNIT).tolist()
    if not all(abs(hard_mu[-1]) < abs(s["plateau"]) for s in softs):
        raise SystemExit("the hard particle no longer falls below the soft plateaus: slide 23")
    e0, e1 = round(math.log10(grid[0])), round(math.log10(grid[-1]))
    for i, e in enumerate(range(e0, e1 + 1)):
        V.tick(f"curve.x.{i}", 10.0**e, max(0, -e), "curve", "x")
    charts["curve"] = {
        "x": [float(grid[0]), float(grid[-1])],
        "grid": grid.tolist(),
        "hard": hard_mu,
        "soft": softs,
        "match": [salt, match],
    }


def d4_values(V: Values, ref: str) -> None:
    """Slide 23 (backup): what of the curve method is built, and that no measured curve met it."""
    log = flat(show(ref, "CHANGELOG.md"))
    sims = find("CHANGELOG.md", log, r"trained at ([\d,]+) simulations")[0]
    V.int("d4.sims", int(sims.replace(",", "")), "CHANGELOG.md, the physics demo")
    sbc = list(csv.DictReader(io.StringIO(show(ref, "out/tables/d4_sbc.csv"))))
    if not all(r["pass"] == "True" for r in sbc):
        raise SystemExit("out/tables/d4_sbc.csv: a calibration no longer passes; slide 23")
    V.int("d4.sbc_params", len(sbc), "out/tables/d4_sbc.csv")
    V.float("d4.ks_min", min(float(r["ks_pvalue"]) for r in sbc), 2, "out/tables/d4_sbc.csv")
    tree = subprocess.run(
        [
            "git",
            "-C",
            str(HERE.parents[1]),
            "ls-tree",
            "-r",
            "--name-only",
            ref,
            "data/raw/digitised/",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    measured = [f for f in tree if f.endswith(".csv") and not f.endswith("/printed_params.csv")]
    V.int(
        "d4.measured", len(measured), "data/raw/digitised/: curve files beside printed_params.csv"
    )


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
    """Slide 38 says no person has checked a row. Stop if the audit sheet holds a verdict."""
    rows = build_data.read_csv(ref, "out/review/audit_sample.csv")
    filled = [r["row_id"] for r in rows for k, v in r.items() if k.endswith("_ok") and v.strip()]
    if filled:
        raise SystemExit(f"audit_sample.csv holds verdicts ({filled[:3]}): slide 38 must change")


# ---- the hypotheses and their tests (2026-10-19) ----------------------------------------------

MOTIVATION = "docs/2026-10-19-motivation-sources.md"
DESIGN = "docs/DESIGN_2026-10-18_hypotheses-method-evaluation.md"
PREREG = "out/tables/p2_prereg_results.json"
P2Z = "out/tables/p2_zeta_size.csv"
WESER = "out/tables/p2_weser_pairs.csv"
TOWS = "tool/colocation/reisser_eriksen/out_2026-10-12/tow_identity_R_E.csv"
TOWS_README = "tool/colocation/reisser_eriksen/README.md"
VSIGN = "out/tables/validate_sign_metrics.json"
VJUDGE = "out/tables/validate_judge_metrics.json"
VRESULTS = "docs/2026-10-19-validation-results.md"
SI_RATES = "out/tables/si_rates.json"
#: A polymer gets its own row on the polymer slide only with at least this many values.
POLYMER_MIN_ROWS = 10


def motivation_values(V: Values, ref: str) -> None:
    """Slide 2: two reviews say, in their own abstracts, that surface charge decides the effect."""
    text = flat(show(ref, MOTIVATION))
    shen = find(
        MOTIVATION,
        text,
        r"> (Positively charged nanoplastics .+? than negatively charged "
        r"nanoplastics),",
    )[0]
    xu = find(
        MOTIVATION,
        text,
        r"> A few studies attempted .+? and (identified several determining "
        r"factors .+? not benchmarked or considered by most studies)\.",
    )[0]
    s_year, s_jr = find(MOTIVATION, text, r"## Shen et al\. (\d{4}) .+? (Environ Pollut \d+)")
    x_year, x_jr = find(MOTIVATION, text, r"## Xu et al\. (\d{4}) .+? (Sci Total Environ \d+)")
    V.words("mot.shen", shen, MOTIVATION + ", Shen et al., abstract")
    V.words("mot.xu", xu, MOTIVATION + ", Xu et al., abstract")
    V.words("mot.shen.ref", f"Shen et al. {s_year}, {s_jr}", MOTIVATION)
    V.words("mot.xu.ref", f"Xu et al. {x_year}, {x_jr}", MOTIVATION)


def basics_values(V: Values, table: pd.DataFrame) -> None:
    """Slide 12: the instrument measures mobility; papers print the zeta computed from it."""
    q = table["quantity"].value_counts()
    src = "out/tables/d1_zeta_table.csv: quantity"
    V.int("zb.zeta_rows", int(q["zeta_potential"]), src)
    V.int("zb.mob_rows", int(q["electrophoretic_mobility"]), src)
    instr = table["instrument"].dropna()
    V.frac(
        "zb.zetasizer",
        int(instr.str.contains("zetasizer", case=False).sum()),
        len(instr),
        "out/tables/d1_zeta_table.csv: instrument",
    )


def hypotheses_values(V: Values, ref: str) -> None:
    """Slide 3: the five hypotheses, each an abstract sentence as the design doc quotes it."""
    design = show(ref, DESIGN)
    for n, (quote, name) in enumerate(
        re.findall(r'^\| "(.+?)" \| \*\*H\d ([^.*]+)\.\*\*', design, re.M), start=1
    ):
        V.words(f"hyp.H{n}.quote", quote, DESIGN + f" §0, H{n}")
        V.words(f"hyp.H{n}.name", name, DESIGN + f" §0, H{n}")
    prereg = json.loads(show(ref, PREREG))
    V.text("pr.commit", prereg["prereg_commit"], PREREG + ": prereg_commit")


def p2_values(V: Values, charts: dict, ref: str) -> None:
    """Slide 13: zeta against size, polymer and surface label, from the P2 table."""
    from scipy.stats import spearmanr

    t = pd.read_csv(io.StringIO(show(ref, P2Z)))
    src = P2Z
    V.int("p2.rows", len(t), src)
    V.int("p2.papers", t["pmcid"].nunique(), src)
    V.float(
        "p2.rho",
        float(spearmanr(np.log10(t["size_nm"]), t["zeta_mV"]).statistic),
        2,
        src + ": Spearman, log10 size_nm against zeta_mV",
    )
    rows = []
    for g, x in t.groupby("material_group"):
        if g == "other" or len(x) < POLYMER_MIN_ROWS:
            continue
        q = x["zeta_mV"].quantile([0.1, 0.5, 0.9]).tolist()
        rows.append(
            {
                "g": g,
                "n": len(x),
                "papers": x["pmcid"].nunique(),
                "p10": q[0],
                "med": q[1],
                "p90": q[2],
                "top": int(x["pmcid"].value_counts().iat[0]),
            }
        )
    rows.sort(key=lambda r: -r["n"])
    for r in rows:
        V.float(f"p2.pol.{r['g']}.med", r["med"], 1, src + f": material_group {r['g']}, median")
    neg = [r for r in rows if r["med"] < 0]
    pos = [r for r in rows if r["med"] > 0]
    V.int("p2.neg_n", len(neg), src + f": polymers with ≥ {POLYMER_MIN_ROWS} values")
    V.int("p2.named_n", len(rows), src + f": polymers with ≥ {POLYMER_MIN_ROWS} values")
    V.float("p2.neg_lo", min(r["med"] for r in neg), 1, src)
    V.float("p2.neg_hi", max(r["med"] for r in neg), 1, src)
    if len(pos) != 1:
        raise SystemExit(f"slide 13 names one exception; the table now has {len(pos)}")
    e = pos[0]
    V.words("p2.exc", e["g"], src)
    V.int("p2.exc_papers", e["papers"], src)
    V.int("p2.exc_top", e["top"], src + ": values from the exception's top paper")
    V.int("p2.exc_n", e["n"], src)
    am = t[(t["material_group"] == "PS") & (t["surface"] == "amine")]
    V.int("p2.amine_neg", int((am["zeta_mV"] < 0).sum()), src + ": PS, amine, negative")
    V.int("p2.amine_n", len(am), src + ": PS, amine")
    lo = math.floor(min(r["p10"] for r in rows) / 20) * 20
    hi = math.ceil(max(r["p90"] for r in rows) / 20) * 20
    for i, x in enumerate(range(lo, hi + 1, 20)):
        V.tick(f"pol.x.{i}", x, 0, "pol", "x")
    charts["pol"] = {"x": [lo, hi], "rows": rows}


def p4_values(V: Values, charts: dict, ref: str) -> None:
    """Slide 17: the pre-registered zeta model, out of paper, against the leaky split."""
    r = json.loads(show(ref, PREREG))
    p4, sec = r["P4"], r["secondary"]
    src = PREREG + ": P4"
    V.int("p4.rows", p4["rows"], src)
    V.int("p4.papers", p4["papers"], src)
    for k, v in p4["feature_sets"].items():
        V.float(f"p4.{k}", v["r2"], 2, src + f", {k}")
    V.float("p4.leak", sec["P4_random_split_r2_all"], 2, PREREG + ": secondary")
    V.float("p4.paper_only", sec["P4_random_split_r2_paper_mean_only"], 2, PREREG + ": secondary")
    V.words("p4.verdict", p4["verdict"], src)
    V.tick("r2.x.0", 0.0, 0, "r2", "x")
    charts["r2"] = {
        "x": [-0.4, 0.4],
        "sets": list(p4["feature_sets"]),
        "ci": {k: v["r2_ci95"] for k, v in p4["feature_sets"].items()},
    }


def window_ratio(alpha: float, small: tuple[float, float], large: tuple[float, float]) -> float:
    """Power-law count in `small` over the count in `large`, for n(d) ∝ d^−α (α ≠ 1)."""
    return (small[0] ** (1 - alpha) - small[1] ** (1 - alpha)) / (
        large[0] ** (1 - alpha) - large[1] ** (1 - alpha)
    )


def window_values(V: Values, ref: str) -> None:
    """Slide 11: one river's two size windows, then the three pre-registered tests."""
    w = pd.read_csv(io.StringIO(show(ref, WESER)))
    small = (float(w["small_lo_um"].iat[0]), float(w["small_hi_um"].iat[0]))
    large = (float(w["large_lo_um"].iat[0]), float(w["large_hi_um"].iat[0]))
    both = w[w["large"] > 0]
    ratio = float((both["small"] / both["large"]).median())
    lo, hi = 1.01, 6.0
    for _ in range(100):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if window_ratio(mid, small, large) < ratio else (lo, mid)
    src = WESER + " (PANGAEA 937685, 938143)"
    V.int("w.stations", len(both), src + ": stations with both fractions above zero")
    for k, (a, b) in (("small", small), ("large", large)):
        V.int(f"w.{k}.lo", int(a), src)
        V.int(f"w.{k}.hi", int(b), src)
    V.int("w.ratio", round(ratio), src + ": median small over large")
    r = json.loads(show(ref, PREREG))
    V.float("w.alpha0", r["alpha_default"], 1, PREREG + ": alpha_default")
    V.float(
        "w.pred",
        window_ratio(r["alpha_default"], small, large),
        0,
        "power law n(d) ∝ d^−α at alpha_default, over the two windows",
    )
    V.float("w.alpha", (lo + hi) / 2, 2, "the α at which the power law gives the median ratio")
    p1, p2, p3, sec = r["P1"], r["P2"], r["P3"], r["secondary"]
    V.int("p1.studies", p1["studies"], PREREG + ": P1")
    V.float("p1.rho", p1["rho"], 2, PREREG + ": P1")
    V.float("p1.slope", p1["slope"], 2, PREREG + ": P1")
    V.words("p1.verdict", p1["verdict"], PREREG + ": P1")
    V.int("p2t.cells", p2["cells"], PREREG + ": P2")
    V.pct("p2t.reduction", p2["median_reduction"], 0, PREREG + ": P2")
    V.words("p2t.verdict", p2["verdict"], PREREG + ": P2")
    d = sec["P2_cells_with_different_windows"]
    V.int("p2t.diff_cells", d["cells"], PREREG + ": secondary")
    V.pct("p2t.wider", d["share_wider_after"], 0, PREREG + ": secondary")
    V.int("p3.n", p3["distributions"], PREREG + ": P3")
    V.pct("p3.outside", 1 - p3["share_within_1.6pm0.3"], 0, PREREG + ": P3")
    V.float("p3.median", p3["median_alpha"], 2, PREREG + ": P3")
    V.float("p3.lod_median", sec["P3_lod_filtered"]["median_alpha"], 2, PREREG + ": secondary")
    V.words("p3.verdict", p3["verdict"], PREREG + ": P3")
    band = r["alpha_band"]
    V.float("p3.band_lo", band[0], 1, PREREG + ": alpha_band")
    V.float("p3.band_hi", band[1], 1, PREREG + ": alpha_band")


def reisser_values(V: Values, ref: str) -> None:
    """Slide 29 (backup): the same tows twice in one database, and a coincidence like a cause."""
    t = pd.read_csv(io.StringIO(show(ref, TOWS)))
    both = t[(t["value_R"] > 0) & (t["value_E"] > 0)]
    ratio = both["value_R"] / both["value_E"]
    by = ratio.groupby(both["Sampling Method"]).median()
    V.int("re.tows", len(t), TOWS)
    V.float("re.manta", float(by["Manta net"]), 2, TOWS + ": Manta tows, median ratio")
    V.float("re.neuston", float(by["Neuston net"]), 2, TOWS + ": Neuston tows, median ratio")
    V.int("re.zero", int(((t["value_E"] == 0) & (t["value_R"] > 0)).sum()), TOWS)
    readme = flat(show(ref, TOWS_README))
    V.float(
        "re.trap",
        float(find(TOWS_README, readme, r"wind-mixing median of ([\d.]+)")[0]),
        1,
        TOWS_README,
    )
    V.int(
        "re.same",
        int(find(TOWS_README, readme, r"agree within 0\.1 % for (\d+) of")[0]),
        TOWS_README,
    )


def validation_values(V: Values, ref: str) -> None:
    """Slide 32 (backup): the validation ladder on Q2, and the guard wrong on the first run."""
    m = json.loads(show(ref, VSIGN))
    src = VSIGN
    V.int("v.cands", m["candidates"], src)
    V.int("v.papers", m["papers"], src)
    V.int("v.v0", m["candidates"] - m["V0"]["abstained"], src + ": V0, causes given")
    V.int("v.v1_rej", m["v1_rejected"]["A"], src + ": V1, reader A's causes rejected")
    V.int("v.v2_kept", m["candidates"] - m["V2"]["abstained"], src + ": V2, causes kept")
    V.int("v.v2_abst", m["V2"]["abstained"], src + ": V2, abstained")
    V.float("v.kappa", m["reader_kappa_raw"], 2, src + ": Cohen's kappa, readers A and B")
    V.pct("v.agree", m["reader_agreement_raw"], 0, src + ": readers A and B, same cause")
    V.text("v.modelA", m["cost_A"]["model"], src)
    V.text("v.modelB", m["cost_B"]["model"], src)
    V.int("v.tokA", m["cost_A"]["input_tokens"], src + ": reader A input tokens")
    V.int("v.secA", round(m["cost_A"]["seconds"]), src + ": reader A seconds")
    V.int("v.labelled", m["labelled"], src + ": rows with Martin's blind label")
    builder = show(ref, "tool/validate/build_labels.py")
    target = int(find("tool/validate/build_labels.py", builder, r"\nN = (\d+)")[0])
    if m["labelled"] >= target:
        raise SystemExit("every blind label is in: slide 32 and its card must report accuracy")
    V.int("v.label_target", target, "tool/validate/build_labels.py: N")
    notes = flat(show(ref, VRESULTS))
    first, a, b = find(
        VRESULTS,
        notes,
        r"rejected (\d+) reader answers at V1: (\d+) of reader A's "
        r"and (\d+) of reader B's",
    )
    V.int("v.first_rej", int(first), VRESULTS)
    V.int(
        "v.guard", int(find(VRESULTS, notes, r"(\d+) of them were \"corona\" answers")[0]), VRESULTS
    )


def judge_name(model: str) -> str:
    """`groq:openai/gpt-oss-120b` -> `gpt-oss-120b`: the model, without provider or route."""
    return model.split(":", 1)[-1].rsplit("/", 1)[-1].removesuffix("-instruct")


def judge_values(V: Values, ref: str) -> None:
    """Slide 33 (backup): three judges from other families, and Claude judging its own reader."""
    m = json.loads(show(ref, VJUDGE))
    cands = json.loads(show(ref, VSIGN))["candidates"]
    per = m["per_judge"]
    seats = [*m["judges"], "claude"]
    for i, jd in enumerate(seats, start=1):
        p, src = per[jd], f"{VJUDGE}: per_judge[{jd}]"
        V.text(f"j.{i}.name", m["self_preference_probe"] if jd == "claude" else judge_name(jd), src)
        V.frac(f"j.{i}.rows", p["rows_judged_A"], cands, src + ", reader A rows judged")
        V.pct(f"j.{i}.yes", p["J1_yes_rate_on_reader_A"], 0, src + ", supported on reader A")
        V.pct(f"j.{i}.flip", p["order_flip_rate_J2"], 0, src + ", pick changed with the order")
        if p["decoy_accepted_rate"] is None:
            V.words(f"j.{i}.decoy", "not asked", src)
        else:
            V.pct(f"j.{i}.decoy", p["decoy_accepted_rate"], 0, src + ", decoy accepted")
        V.frac(f"j.{i}.traps", m["traps_caught"][jd], m["traps_run"][jd], f"{VJUDGE}: traps")
    top = max(m["judges"], key=lambda jd: per[jd]["decoy_accepted_rate"])
    V.text("j.decoy_top.name", judge_name(top), f"{VJUDGE}: the jury's most accepted decoy")
    V.pct("j.decoy_top", per[top]["decoy_accepted_rate"], 0, f"{VJUDGE}: per_judge[{top}]")


SV_P7 = "out/tables/survey_p7.json"
SV_COLOC = "out/tables/survey_colocated.json"
SV_DUP = "out/tables/survey_duplicates.csv"
SV_MISS = "out/tables/survey_completeness.csv"
DS_SEARCH = "out/tables/dataset_search.json"
#: The survey's datasets by the key their slide values use; the search agent's PANGAEA finds are
#: the pangaea_<id> datasets, shown as one row.
SV_NAMES = {"ncei": "ncei", "mpsed": "mpsed", "soil": "soil", "pangaea_weser": "weser",
            "emodnet": "emodnet", "air_fu2023": "air"}  # fmt: skip


def survey_values(V: Values, ref: str) -> None:
    """The dataset slides: the table, the pooled rise and its series, same place, held twice."""
    coloc = json.loads(show(ref, SV_COLOC))
    recs = coloc["records"]
    found = sorted(k for k in recs if re.fullmatch(r"pangaea_\d+", k))
    if set(recs) != set(SV_NAMES) | set(found):
        raise SystemExit(f"{SV_COLOC}: a dataset has no row on slide 7: {sorted(recs)}")
    for ds, key in SV_NAMES.items():
        V.int(f"sv.n.{key}", recs[ds], SV_COLOC + ": records")
    V.int("sv.n.found", sum(recs[k] for k in found), SV_COLOC + ": records, pangaea_<id>")
    V.int("sv.n.datasets", len(recs), SV_COLOC + ": records, datasets")
    V.int("sv.total", sum(recs.values()), SV_COLOC + ": records, summed")

    ds = json.loads(show(ref, DS_SEARCH))
    for key in ("found", "distinct", "on_topic", "to_verify"):
        V.int(f"ds.{key}", ds[key], DS_SEARCH)
    for key in ("usable", "partial", "not_verifiable"):
        V.int(f"ds.{key}", ds["verdicts"][key], DS_SEARCH + ": verdicts")
    V.int("ds.joined", len(found), SV_COLOC + ": records, pangaea_<id> datasets")

    miss = pd.read_csv(io.StringIO(show(ref, SV_MISS))).set_index("dataset")
    V.pct("sv.miss.emodnet.mesh", miss.loc["emodnet", "size_min_um"], 0, SV_MISS + ": emodnet")
    V.pct("sv.miss.air.date", miss.loc["air_fu2023", "date"], 0, SV_MISS + ": air, date")
    V.pct("sv.miss.air.method", miss.loc["air_fu2023", "method"], 0, SV_MISS + ": air, method")
    V.int(
        "sv.found_nolower",
        int((miss.loc[found, "size_min_um"] == 1).sum()),
        SV_MISS + ": pangaea_<id> with no lower limit at all",
    )
    V.pct("sv.miss.mpsed.lat", miss.loc["mpsed", "lat"], 0, SV_MISS + ": mpsed, lat")
    V.pct("sv.miss.mpsed.year", miss.loc["mpsed", "year"], 0, SV_MISS + ": mpsed, year")
    V.pct("sv.miss.soil.method", miss.loc["soil", "method"], 0, SV_MISS + ": soil, method")
    V.pct("sv.miss.soil.year", miss.loc["soil", "year"], 0, SV_MISS + ": soil, year")
    V.pct("sv.miss.ncei.mesh", miss.loc["ncei", "size_min_um"], 2, SV_MISS + ": ncei, mesh")

    p7 = json.loads(show(ref, SV_P7))
    periods = {int(p["period"]): p for p in p7["P7c"]["periods"]}
    V.float("sv.pooled", p7["P7c"]["pooled_ratio_last_over_2000s_per_record"], 0, SV_P7 + ": P7c")
    for key, start in (("from", 2000), ("to", 2020), ("peak", 2015)):
        V.year(f"sv.y_{key}", start, SV_P7 + ": P7c, a five-year period")
        V.year(f"sv.y_{key}_end", start + 4, SV_P7 + ": P7c, a five-year period")
    V.int("sv.studies_from", periods[2000]["studies"], SV_P7 + ": P7c, 2000-2004")
    V.int("sv.studies_to", periods[2020]["studies"], SV_P7 + ": P7c, 2020-2024")
    V.int("sv.studies_peak", periods[2015]["studies"], SV_P7 + ": P7c, 2015-2019")
    a = p7["P7a"]
    V.float("sv.law_rho", a["spearman_rho"], 2, SV_P7 + ": P7a")
    V.int("sv.law_tows", a["tows"], SV_P7 + ": P7a")
    V.year("sv.law_y0", a["years"][0], SV_P7 + ": P7a")
    V.year("sv.law_y1", a["years"][1], SV_P7 + ": P7a")
    V.words("sv.p7a", a["verdict"], SV_P7 + ": P7a verdict")
    V.words("sv.p7b", p7["P7b"]["verdict"], SV_P7 + ": P7b verdict")
    series = {s["series"]: s for s in p7["P7b"]["series"]}
    V.float("sv.goldstein", series["Goldstein et al. 2013"]["ratio_last_over_first"], 0, SV_P7)
    V.float("sv.law14", series["Law et al. 2014"]["ratio_last_over_first"], 1, SV_P7)
    z = p7["P7_secondary_law2014_zone"]
    if not z["ratio_inside_zone"] < z["ratio_whole_series"]:
        raise SystemExit(f"{SV_P7}: Law 2014 no longer rises less inside its zone; slide 8")
    V.float("sv.law14_zone", z["ratio_inside_zone"], 1, SV_P7 + ": secondary")
    V.pct("sv.zone_first", z["share_in_zone_first_third"], 0, SV_P7 + ": secondary")
    V.pct("sv.zone_last", z["share_in_zone_last_third"], 0, SV_P7 + ": secondary")

    same, anym = coloc["same_method_50km_365d"], coloc["any_method_50km_365d"]
    med = coloc["mediterranean_same_method_50km_365d"]
    V.int("sv.co.km", same["km"], SV_COLOC)
    V.int("sv.co.days", same["days"], SV_COLOC)
    V.float("sv.co.median", same["median_fold"], 1, SV_COLOC + ": same method")
    V.float("sv.co.p90", same["p90_fold"], 0, SV_COLOC + ": same method")
    V.int("sv.co.pairs", same["pairs"], SV_COLOC + ": same method")
    V.int("sv.co.studypairs", same["study_pairs"], SV_COLOC + ": same method")
    V.int("sv.co.excluded", same["excluded_held_twice"], SV_COLOC + ": same method")
    V.float("sv.co.any_median", anym["median_fold"], 1, SV_COLOC + ": any method")
    V.float("sv.co.any_p90", anym["p90_fold"], 0, SV_COLOC + ": any method")
    V.float("sv.co.med_median", med["median_fold"], 1, SV_COLOC + ": Mediterranean")
    V.int("sv.co.med_studypairs", med["study_pairs"], SV_COLOC + ": Mediterranean")

    x = coloc["across_datasets_100km_any_year"]
    src = SV_COLOC + ": across_datasets_100km_any_year"
    groups = {(g["datasets"], g["decision"]): g for g in x["by_dataset_pair"]}
    want = {("emodnet vs ncei", "caveat"), ("ncei vs pangaea_990052", "caveat"),
            ("ncei vs pangaea_990052", "refuse")}  # fmt: skip
    if set(groups) != want:
        raise SystemExit(f"{src}: slide 9 names these database pairs: {sorted(want)}")
    nets, pump = groups[("emodnet vs ncei", "caveat")], groups[("ncei vs pangaea_990052", "caveat")]
    refused = groups[("ncei vs pangaea_990052", "refuse")]
    V.int("sv.x.km", x["km"], src)
    V.int("sv.x.compared", nets["pairs"], src + ", EMODnet against NCEI")
    V.float("sv.x.median", nets["median_fold"], 1, src + ", EMODnet against NCEI")
    V.float("sv.x.p90", nets["p90_fold"], 0, src + ", EMODnet against NCEI")
    V.float("sv.x.years", nets["median_years_apart"], 0, src + ", median years apart")
    V.int("sv.x.refused", refused["pairs"], src + ", the pump, refused")
    V.float("sv.x.refused_fold", refused["median_fold"], 0, src + ", the pump, refused")
    V.int("sv.x.cav", pump["pairs"], src + ", the pump, caveated")
    V.float("sv.x.residual", pump["median_residual_fold"], 0, src + ", the pump, after the window")
    V.float("sv.x.raw_p90", x["unguarded"]["p90_fold"], 0, src + ", unguarded")

    dup = pd.read_csv(io.StringIO(show(ref, SV_DUP)))
    V.int("sv.dup.n", len(dup), SV_DUP)
    V.int("sv.dup.identical", int((dup.median_ratio_a_over_b - 1).abs().lt(0.01).sum()), SV_DUP)
    re_pair = dup[
        dup.study_a.str.endswith("pone.0080466") & dup.study_b.str.endswith("pone.0111913")
    ]
    V.int("sv.dup.re_found", int(re_pair.records_a.iat[0]), SV_DUP + ": Reisser/Eriksen")


AG = "out/tables/p2_aging.json"
AG_PAIRS = "out/tables/p2_aging_pairs.csv"
KIND_WORDS = {"photo": "light", "chemical": "oxidant"}


def aging_values(V: Values, charts: dict, ref: str) -> None:
    """Slide 14: an aged particle against its own virgin form, inside one paper (P11)."""
    a = json.loads(show(ref, AG))
    p = pd.read_csv(io.StringIO(show(ref, AG_PAIRS)))
    V.int("ag.aged_rows", a["aged_rows"], AG)
    V.int("ag.aged_papers", a["aged_papers"], AG)
    V.int("ag.pairs", a["pairs"], AG)
    V.int("ag.paired_papers", a["paired_papers"], AG)
    p11a, p11b = a["P11a"], a["P11b"]
    src = AG + ": P11a"
    V.int("ag.a.papers", p11a["papers"], src)
    V.int("ag.a.neg", p11a["papers_more_negative"], src)
    V.int("ag.a.pos", p11a["papers_less_negative"], src)
    V.float("ag.a.median", p11a["median_delta_mV"], 1, src)
    V.float("ag.a.lo", p11a["ci95"][0], 1, src + ", 95 % interval")
    V.float("ag.a.hi", p11a["ci95"][1], 1, src + ", 95 % interval")
    V.float("ag.a.p", p11a["sign_test_p"], 2, src + ", sign test")
    V.words("ag.a.verdict", p11a["verdict"], src)
    src = AG + ": P11b"
    V.float("ag.b.median", p11b["median_difference_mV"], 1, src)
    V.float("ag.b.lo", p11b["ci95"][0], 1, src + ", 95 % interval")
    V.float("ag.b.hi", p11b["ci95"][1], 1, src + ", 95 % interval")
    V.float("ag.b.ratio", p11b["width_ratio_unpaired_over_paired"], 1, src)
    V.words("ag.b.verdict", p11b["verdict"], src)
    after = a["chosen_after_the_results"]
    iqr = after["virgin_between_papers"]["PS"]["iqr_mV"]
    V.float("ag.iqr.PS", iqr, 0, AG + ": virgin PS between papers, IQR (after the results)")
    V.float("ag.scale", iqr / abs(p11a["median_delta_mV"]), 0, AG + ": that IQR over P11a's median")
    swapped = after["papers_printing_swapped_values"]
    if len(swapped) != 1:
        raise SystemExit(f"{AG}: slide 14 names one paper that swaps its values; now {swapped}")
    V.text("ag.swap", swapped[0], AG + ": papers printing swapped values")
    ox = p[p.kind.isin(KIND_WORDS)]
    rows = []
    for _, g in ox.groupby("pmcid"):
        rows.append(
            {
                "label": f"{'/'.join(sorted(set(g.polymer)))} · "
                + " and ".join(KIND_WORDS[k] for k in sorted(set(g.kind), reverse=True)),
                "med": float(g.delta_mV.median()),
                "lo": float(g.delta_mV.min()),
                "hi": float(g.delta_mV.max()),
            }
        )
    if len(rows) != p11a["papers"]:
        raise SystemExit(f"{AG_PAIRS}: {len(rows)} oxidative papers, P11a counts {p11a['papers']}")
    rows.sort(key=lambda r: r["med"])
    for i, r in enumerate(rows):
        V.float(f"ag.paper.{i}", r["med"], 1, AG_PAIRS + ": a paper's median, oxidative pairs")
    lo = math.floor(min(min(r["lo"] for r in rows), -iqr / 2) / 10) * 10
    hi = math.ceil(max(max(r["hi"] for r in rows), iqr / 2) / 10) * 10
    for i, x in enumerate(range(lo, hi + 1, 10)):
        V.tick(f"aging.x.{i}", x, 0, "aging", "x")
    charts["aging"] = {"x": [lo, hi], "rows": rows, "iqr": iqr}


def prereg_tally(V: Values) -> None:
    """Slide 20: every pre-registered prediction with a verdict, read from the values above."""
    keys = ("p1.verdict", "p2t.verdict", "p3.verdict", "p4.verdict", "sv.p7a", "sv.p7b",
            "hy.p8", "hy.p9", "ag.a.verdict", "ag.b.verdict")  # fmt: skip
    verdicts = [V.v[k]["v"] for k in keys]
    if set(verdicts) - {"supported", "partly", "refuted"}:
        raise SystemExit(f"slide 20 counts three verdicts; found {sorted(set(verdicts))}")
    src = "docs/PREREG_2026-10.md: P1-P4, P7a/b, P8, P9 (guard), P11a/b"
    V.int("pv.n", len(verdicts), src)
    for v in ("supported", "partly", "refuted"):
        V.int(f"pv.{v}", verdicts.count(v), src + f", {v}")


HY = "out/tables/hybrid_results.json"
HY_Q = "queries/hybrid_questions.jsonl"
PREREG_DOC = "docs/PREREG_2026-10.md"
ARM_KEYS = ("N0", "N2", "H", "Hg", "Hng")


def hybrid_verdicts(m: dict, p9_min: float) -> tuple[str, str]:
    """P8 and P9 read against the rules PREREG committed before the runs."""
    h, n2 = m["arms"]["H"], m["arms"]["N2"]
    p = n2["vs_H"]["p"]
    if n2["correct"] >= h["correct"]:
        p8 = "refuted"
    else:
        p8 = "supported" if p < 0.05 else "not significant"
    drop = h["correct_flag_required"] - m["arms"]["Hg"]["correct_flag_required"]
    p9 = "supported" if drop >= p9_min else ("refuted" if drop < 0.1 else "partly")
    return p8, p9


def hybrid_values(V: Values, ref: str) -> None:
    """The naive-vs-hybrid slides: every arm on the same questions, and one stage removed."""
    m = json.loads(show(ref, HY))
    qs = [json.loads(x) for x in show(ref, HY_Q).splitlines() if x.strip()]
    V.int("hy.q", len(qs), HY_Q)
    V.int("hy.flagq", sum(q["verdict"] != "allow" for q in qs), HY_Q + ": verdict caveat or refuse")
    V.int("hy.adv", sum(q["adversarial"] for q in qs), HY_Q + ": adversarial")
    V.int("hy.reps", len(m["arms"]["H"]["reps"]), HY + ": reps")
    for arm in ARM_KEYS:
        a, src = m["arms"][arm], f"{HY}: arms[{arm}]"
        V.pct(f"hy.{arm}.correct", a["correct"], 0, src + ", correct")
        if arm in ("N0", "N2", "H"):  # slide 18 compares the arms on the traps
            V.pct(f"hy.{arm}.adv", a["correct_adversarial"], 0, src + ", correct on the traps")
        if arm in ("H", "Hg", "Hng"):  # slide 19 splits the ablations by the flag needed
            V.pct(f"hy.{arm}.flag", a["correct_flag_required"], 0, src + ", flag-required")
            V.pct(f"hy.{arm}.noflag", a["correct_no_flag"], 0, src + ", no flag needed")
        if a["ungrounded_numbers_per_answer"] is None:
            V.words(f"hy.{arm}.ungrounded", "not scored", src)
        else:
            V.float(f"hy.{arm}.ungrounded", a["ungrounded_numbers_per_answer"], 2, src)
        if arm in ("N0", "N2", "H"):
            V.int(f"hy.{arm}.tokens", round(a["input_tokens_per_q"]), src + ", input tokens per q")
            V.float(f"hy.{arm}.sec", a["seconds_per_q"], 0, src + ", seconds per question")
    vs = m["arms"]["N2"]["vs_H"]
    V.int("hy.only_H", vs["only_H_right"], HY + ": N2 vs H")
    V.int("hy.only_N2", vs["only_this_right"], HY + ": N2 vs H")
    if vs["p"] < 0.001:
        V.words("hy.p", "< 0.001", HY + ": N2 vs H, exact McNemar")
    else:
        V.float("hy.p", vs["p"], 3, HY + ": N2 vs H, exact McNemar")
    V.int("hy.paired", m["arms"]["N2"]["answers"], HY + ": N2 answers, paired with H")
    V.pct("hy.H.plan", m["arms"]["H"]["plan_matches_ref"], 0, HY + ": H, plan = reference op")
    prereg = flat(show(ref, PREREG_DOC))
    p9_min = float(
        find(PREREG_DOC, prereg, r"flag-required questions by at least (\d+(?:\.\d+)?)")[0]
    )
    V.float("hy.p9_min", p9_min, 1, PREREG_DOC + ": P9")
    V.text("hy.code", find(PREREG_DOC, prereg, r"Code at `([0-9a-f]{7})`")[0], PREREG_DOC + ": P8")
    p8, p9 = hybrid_verdicts(m, p9_min)
    V.words("hy.p8", p8, HY + " against PREREG P8")
    V.words("hy.p9", p9, HY + " against PREREG P9")


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
    si_values(V, ref, base)
    census_values(V, charts, base)
    rules_values(V, ref)
    lab_values(V, charts, table)
    curve_values(V, charts)
    d4_values(V, ref)
    line_values(V, d1, table)
    henry_values(V, charts, list(harm.values()), base, d1)
    reread_values(V, ref)
    gallery_values(V, ref)
    grid_values(V, ref)
    scope_values(V, base)
    motivation_values(V, ref)
    basics_values(V, table)
    hypotheses_values(V, ref)
    p2_values(V, charts, ref)
    p4_values(V, charts, ref)
    window_values(V, ref)
    reisser_values(V, ref)
    validation_values(V, ref)
    judge_values(V, ref)
    survey_values(V, ref)
    hybrid_values(V, ref)
    aging_values(V, charts, ref)
    prereg_tally(V)
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


def chart_lab(values: dict, charts: dict) -> str:
    c = charts["lab"]
    W, row, top = 960, 38, 40
    yb = top + row * len(c["order"])
    H = yb + 58
    x0, x1, r0, r1 = 200, 500, 640, 910
    lx0, lx1 = math.log10(c["x"][0]), math.log10(c["x"][1])
    sx = lambda v: r0 + (math.log10(v) - lx0) / (lx1 - lx0) * (r1 - r0)  # noqa: E731
    bw = lambda n: (x1 - x0) * n / c["rows"]  # noqa: E731
    body = [
        T(x0, 22, "rows: ionic strength stated, not stated", values, "col-h"),
        T(r0, 22, "where stated, it runs over", values, "col-h"),
    ]
    for key in _ticks(values, "lab", "x"):
        x = sx(values[key]["v"])
        body += [
            line(x, top - 8, x, yb, "grid"),
            T(x, yb + 24, "{{" + key + "}}", values, "tick", "middle"),
        ]
    body.append(T(r1, yb + 50, "ionic strength (mM), log scale", values, "ax-t", "end"))
    for i, cls in enumerate(c["order"]):
        y = top + i * row
        rows, stated = values[f"lab.{cls}.rows"]["v"], values[f"lab.{cls}.stated"]["v"]
        none = stated == 0
        ym = y + row / 2
        body += [
            T(
                x0 - 14,
                ym + 6,
                MEDIUM_WORDS[cls],
                values,
                "row-l" + (" abs" if none else ""),
                "end",
            ),
            rect(x0, y + 7, bw(stated), row - 14, "seg-i"),
            rect(x0 + bw(stated), y + 7, bw(rows - stated), row - 14, "bar-a"),
            T(
                x0 + bw(rows) + 8,
                ym + 6,
                "{{lab." + cls + ".stated}} / {{lab." + cls + ".rows}}",
                values,
                "val-s",
            ),
        ]
        if none:
            body.append(T(r0, ym + 5, "never stated", values, "band-t"))
            continue
        for mM in c["points"][cls]:
            body.append(f'<circle cx="{sx(mM):.1f}" cy="{ym:.1f}" r="4" class="dot"/>')
        if f"lab.{cls}.at" in values:
            body.append(
                T(
                    sx(values[f"lab.{cls}.at"]["v"]) + 10,
                    ym + 5,
                    "{{lab." + cls + ".at}}",
                    values,
                    "lim",
                )
            )
            continue
        lo, hi = sx(values[f"lab.{cls}.lo"]["v"]), sx(values[f"lab.{cls}.hi"]["v"])
        body += [
            line(lo, ym, hi, ym, "gap"),
            T(lo - 8, ym + 5, "{{lab." + cls + ".lo}}", values, "lim", "end"),
            T(hi + 8, ym + 5, "{{lab." + cls + ".hi}}", values, "lim"),
        ]
    return svg(W, H, body, "Rows per liquid that state their ionic strength, and the range stated")


def chart_curve(values: dict, charts: dict) -> str:
    c = charts["curve"]
    W, H = 760, 340
    x0, x1, y0, y1 = 60, 590, 280, 22
    lx0, lx1 = math.log10(c["x"][0]), math.log10(c["x"][1])
    top = max(abs(m) for m in c["hard"] + [m for s in c["soft"] for m in s["mu"]])
    sx = lambda v: x0 + (math.log10(v) - lx0) / (lx1 - lx0) * (x1 - x0)  # noqa: E731
    sy = lambda m: y0 - abs(m) / top * (y0 - y1)  # noqa: E731
    body = []
    for key in _ticks(values, "curve", "x"):
        x = sx(values[key]["v"])
        body += [
            line(x, y1, x, y0, "grid"),
            line(x, y0, x, y0 + 6, "ax"),
            T(x, y0 + 24, "{{" + key + "}}", values, "tick", "middle"),
        ]
    body.append(line(x0, y0, x1, y0, "ax"))
    salt, mu = c["match"]
    body += [
        line(sx(salt), y1 - 6, sx(salt), y0, "slip"),
        T(sx(salt) + 8, y1 + 4, "reference condition", values, "lab"),
    ]

    def pts(ms: list[float]) -> str:
        return " ".join(f"{sx(g):.1f},{sy(m):.1f}" for g, m in zip(c["grid"], ms, strict=True))

    body.append(f'<polyline points="{pts(c["hard"])}" class="curve"/>')
    for s in c["soft"]:
        body += [
            line(x0, sy(s["plateau"]), x1, sy(s["plateau"]), "plat"),
            f'<polyline points="{pts(s["mu"])}" class="curve-s"/>',
        ]
    ends = sorted(
        [(sy(s["mu"][-1]), "soft: a plateau", "lab-a") for s in c["soft"]]
        + [(sy(c["hard"][-1]), "hard: toward zero", "lab-b")]
    )
    last = -1e9
    for y, text, cls in ends:
        y = max(y + 5, last + 20)
        body.append(T(x1 + 10, y, text, values, cls))
        last = y
    body += [
        f'<circle cx="{sx(salt):.1f}" cy="{sy(mu):.1f}" r="7" class="pt"/>',
        T(
            sx(salt) + 14,
            sy(mu) - 14,
            "one zeta, {{curve.zeta}} mV: three particles",
            values,
            "lab-b",
        ),
        T(x0 - 6, y0 + 4, "zero", values, "note", "end"),
        T(x1, y0 + 50, "ionic strength (mM), log scale", values, "ax-t", "end"),
        f'<text x="18" y="{(y0 + y1) / 2:.1f}" class="ax-t" text-anchor="middle" '
        f'transform="rotate(-90 18 {(y0 + y1) / 2:.1f})">mobility |μ|</text>',
    ]
    return svg(
        W, H, body, "One hard and two soft particles with the same mobility at one salt level"
    )


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


def chart_pol(values: dict, charts: dict) -> str:
    """Slide 13: each polymer's 10th to 90th percentile of zeta, and its median."""
    c = charts["pol"]
    W, x0, x1, top, row = 900, 120, 800, 16, 34
    H = top + row * len(c["rows"]) + 44
    sx = lambda v: x0 + (v - c["x"][0]) / (c["x"][1] - c["x"][0]) * (x1 - x0)  # noqa: E731
    y0 = top + row * len(c["rows"])
    body = []
    for key in _ticks(values, "pol", "x"):
        x = sx(values[key]["v"])
        cls = "ax" if values[key]["v"] == 0 else "grid"
        body += [
            line(x, top, x, y0, cls),
            T(x, y0 + 24, "{{" + key + "}}", values, "tick", "middle"),
        ]
    for i, r in enumerate(c["rows"]):
        y = top + row * i + row / 2
        exc = r["med"] > 0
        body += [
            T(x0 - 14, y + 6, r["g"], values, "row-l abs" if exc else "row-l", "end"),
            rect(sx(r["p10"]), y - 5, sx(r["p90"]) - sx(r["p10"]), 10, "seg-q", 3),
            f'<circle cx="{sx(r["med"]):.1f}" cy="{y:.1f}" r="7" '
            f'class="{"abs" if exc else "pt"}"/>',
            T(x1 + 18, y + 6, "{{p2.pol." + r["g"] + ".med}} mV", values, "val-s"),
        ]
    body.append(
        T(
            x1,
            H - 4,
            "zeta potential, mV: tenth to ninetieth percentile, and the median",
            values,
            "ax-t",
            "end",
        )
    )
    return svg(W, H, body, "Zeta potential by polymer: the spread and the median of each")


def chart_aging(values: dict, charts: dict) -> str:
    """Slide 14: per paper, oxidative pairs aged minus virgin, against the between-paper spread."""
    c = charts["aging"]
    W, x0, x1, top, row = 900, 210, 780, 12, 34
    n = len(c["rows"])
    H = top + row * (n + 1) + 52
    sx = lambda v: x0 + (v - c["x"][0]) / (c["x"][1] - c["x"][0]) * (x1 - x0)  # noqa: E731
    y0 = top + row * (n + 1)
    body = []
    for key in _ticks(values, "aging", "x"):
        x = sx(values[key]["v"])
        cls = "ax" if values[key]["v"] == 0 else "grid"
        body += [
            line(x, top, x, y0, cls),
            T(x, y0 + 24, "{{" + key + "}}", values, "tick", "middle"),
        ]
    for i, r in enumerate(c["rows"]):
        y = top + row * i + row / 2
        body += [
            T(x0 - 14, y + 6, r["label"], values, "row-l", "end"),
            line(sx(r["lo"]), y, sx(r["hi"]), y, "gap"),
            f'<circle cx="{sx(r["med"]):.1f}" cy="{y:.1f}" r="7" class="pt"/>',
            T(x1 + 18, y + 6, "{{ag.paper." + str(i) + "}} mV", values, "val-s"),
        ]
    y = top + row * n + row / 2
    body += [
        T(x0 - 14, y + 6, "paper to paper, virgin PS", values, "row-l abs", "end"),
        rect(sx(-c["iqr"] / 2), y - 7, sx(c["iqr"] / 2) - sx(-c["iqr"] / 2), 14, "seg-q", 3),
        T(x1 + 18, y + 6, "{{ag.iqr.PS}} mV", values, "val-s"),
        T(x1, H - 4, "aged minus virgin, mV: each paper’s pairs and their median; the band’s "
          "width is the spread between papers", values, "ax-t", "end"),
    ]  # fmt: skip
    return svg(W, H, body, "Aged minus virgin zeta per paper, against the spread between papers")


def chart_r2(values: dict, charts: dict) -> str:
    """Slide 17: out-of-paper R² per feature set, and the same model on a leaky split."""
    sets = charts["r2"]["sets"] + ["leak"]
    label = {
        "size": "size",
        "polymer": "polymer",
        "surface": "surface",
        "liquid_pH": "liquid and pH",
        "all": "all of them",
        "leak": "all, rows shuffled",
    }
    W, x0, x1, top, row = 900, 250, 800, 12, 40
    H = top + row * len(sets) + 44
    lo, hi = charts["r2"]["x"]
    sx = lambda v: x0 + (max(lo, min(hi, v)) - lo) / (hi - lo) * (x1 - x0)  # noqa: E731
    y0 = top + row * len(sets)
    body = [line(sx(0), top, sx(0), y0, "ax")]
    for i, k in enumerate(sets):
        y = top + row * i + row / 2
        v = values[f"p4.{k}"]["v"]
        cls = "bar-a" if k == "leak" else "seg-i"
        a, b = sorted((sx(0), sx(v)))
        body += [
            T(x0 - 14, y + 6, label[k], values, "row-l abs" if k == "leak" else "row-l", "end"),
            rect(a, y - 9, max(2, b - a), 18, cls, 3),
            T(x1 + 18, y + 6, "{{p4." + k + "}}", values, "val-s"),
        ]
        ci = charts["r2"]["ci"].get(k)
        if ci:
            body.append(line(sx(ci[0]), y, sx(ci[1]), y, "gap"))
    body += [
        T(sx(0), y0 + 24, "{{r2.x.0}}", values, "tick", "middle"),
        T(x1, H - 4, "R², predicting zeta for papers the model never saw", values, "ax-t", "end"),
    ]
    return svg(W, H, body, "R squared per feature set, grouped by paper, against a shuffled split")


CHARTS = {
    "pol": chart_pol,
    "r2": chart_r2,
    "aging": chart_aging,
    "c14": chart_c14,
    "c02": chart_c02,
    "layer": chart_layer,
    "census": chart_census,
    "fields": chart_fields,
    "henry": chart_henry,
    "arch": chart_arch,
    "lab": chart_lab,
    "curve": chart_curve,
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


def standalone(page: str) -> str:
    """The page as a whole document, to open from a file on a phone or offline. The artifact host
    adds this skeleton itself, so the published page leaves it out."""
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        "</head>\n<body>\n" + page + "\n</body>\n</html>\n"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ref", default="HEAD", help="git ref to read every input from")
    ap.add_argument("--out", default=str(HERE / "slides.html"))
    ap.add_argument("--standalone", action="store_true", help="a whole document, to open as a file")
    args = ap.parse_args()

    deck = build(args.ref)
    out = Path(args.out)
    page = render(deck)
    out.write_text(standalone(page) if args.standalone else page, encoding="utf-8")
    rc = deck["review_checks"]
    print(f"{args.ref} ({deck['commit']}): wrote {out}, {out.stat().st_size:,} bytes")
    print(
        f"{len(deck['values'])} values; build_data's checks against REVIEW.md: {rc['ok']}/{rc['n']}"
    )


if __name__ == "__main__":
    main()
