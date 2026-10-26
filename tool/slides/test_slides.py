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
import html
import importlib.util
import inspect
import io
import json
import math
import re
import statistics
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest
from scipy.stats import binomtest

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

    # the liquids of slide 36, counted from the table's own rows rather than through pandas
    liquids: dict = {}
    for r in d1.values():
        c = liquids.setdefault(r["medium_class"], {"rows": 0, "mM": []})
        c["rows"] += 1
        if r["ionic_strength_reported"] == "True":
            c["mM"].append(float(r["ionic_strength_mM"]))
    for cls, c in liquids.items():
        E[f"lab.{cls}.rows"], E[f"lab.{cls}.stated"] = c["rows"], len(c["mM"])
        if c["mM"] and min(c["mM"]) != max(c["mM"]):
            E[f"lab.{cls}.lo"], E[f"lab.{cls}.hi"] = min(c["mM"]), max(c["mM"])
        elif c["mM"]:
            E[f"lab.{cls}.at"] = c["mM"][0]
    every = [x for c in liquids.values() for x in c["mM"]]
    E["lab.lo"], E["lab.hi"] = min(every), max(every)
    salt = liquids["salt_solution"]
    E["lab.salt.share"] = len(salt["mM"]) / salt["rows"]

    # slide 32 (backup): the physics demo's figure defaults
    from mnp.ek import constants as ek_constants
    from mnp.ek import hard as ek_hard
    from mnp.infer import figures

    fig = inspect.signature(figures.same_zeta_figure).parameters
    salt, T = fig["I_match_mM"].default, fig["T_C"].default
    E["curve.I"], E["curve.T"] = salt, T
    radius = fig["hard_radius_nm"].default * 1e-9
    mu = float(ek_hard.mobility_hard(fig["hard_sigma_C_m2"].default, radius, salt, T_C=T))
    E["curve.zeta"] = Near(1e3 * ek_constants.viscosity(T) * mu / ek_constants.permittivity(T), 0.5)

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
    E.update(expected_findings(get))
    return E


def _ranks(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=xs.__getitem__)
    out = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def _quantile(xs: list[float], q: float) -> float:
    """Linear interpolation between order statistics, the definition pandas uses by default."""
    s = sorted(xs)
    pos = (len(s) - 1) * q
    lo = math.floor(pos)
    return s[lo] + (s[min(lo + 1, len(s) - 1)] - s[lo]) * (pos - lo)


def expected_findings(get=show) -> dict:
    """The 2026-10-19 slides, each source read again with csv, statistics and plain regex."""
    E: dict = {}
    # slide 4: the two review abstracts, as the sources note quotes them
    src = get("docs/2026-10-19-motivation-sources.md")
    quotes = [ln[2:] for ln in src.splitlines() if ln.startswith("> ")]
    shen = next(q for q in quotes if q.startswith("Positively charged"))
    E["mot.shen"] = shen[: shen.index(", and smaller")]
    xu = next(q for q in quotes if "not benchmarked" in q)
    E["mot.xu"] = xu[xu.index("identified several") : xu.rindex(".")]
    heads = dict(re.findall(r"^## (\w+) et al\. (\d{4})", src, re.M))
    journals = dict(
        re.findall(r"^(?:Shen|Xu) .*?\n.*?(Environ Pollut|Sci Total Environ) (\d+)", src, re.M)
    )
    E["mot.shen.ref"] = f"Shen et al. {heads['Shen']}, Environ Pollut {journals['Environ Pollut']}"
    E["mot.xu.ref"] = f"Xu et al. {heads['Xu']}, Sci Total Environ {journals['Sci Total Environ']}"

    # slides 1, 3 and 23: the standardisation note, its quoted lines split by hand
    std = get("docs/2026-10-25-standardisation-sources.md")
    said = [ln[2:] for ln in std.splitlines() if ln.startswith("> ")]

    def line(start: str) -> str:
        return next(q for q in said if q.startswith(start))

    E["ab.title"] = flat(std).split("Martin's abstract, \"", 1)[1].split('" (', 1)[0]
    led = line("Accordingly, we led").split(" participating laboratories")[0]
    E["mp.dfr.labs"] = int(led.rsplit(" ", 1)[1])
    E["mp.dfr.floor"] = int(line("Participants demonstrated").split("greater than ")[1].split()[0])
    E["mp.cow.n"] = int(line("This diverse group of").split()[4])
    k19 = line("However, only").split()
    E["mp.k19.pass"], E["mp.k19.n"] = k19[2], int(k19[5])
    E["np.fda"] = line("While studies on microplastics").split("lack of ", 1)[1].rstrip(".")
    E["np.fda2"] = line("This is particularly")[:-1]
    E["np.gig"] = line("The term").split("debate, and ", 1)[1].rstrip(".")
    for key, head, journal in (
        ("mp.dfr.ref", "De Frond et al. 2022", "Chemosphere"),
        ("mp.k20.ref", "Koelmans et al. 2020", "Environ Sci Technol"),
        ("mp.cow.ref", "Cowger et al. 2020", "Appl Spectrosc"),
        ("mp.k19.ref", "Koelmans et al. 2019", "Water Res"),
        ("np.fda.ref", "Duncan et al. 2024", "Anal Chem"),
        ("np.gig.ref", "Gigault et al. 2018", "Environ Pollut"),
    ):
        citation = flat(std.split(f"### {head}\n\n", 1)[1].split("\n\n", 1)[0])
        E[key] = f"{head}, {journal} {citation.split(journal + ' ', 1)[1].split(':')[0]}"
        E[key.replace(".ref", ".year")] = int(head.rsplit(" ", 1)[1])

    # slide 18: each paper's reporting habit, recounted with csv and plain sets
    per = list(csv.DictReader(io.StringIO(get("out/review/conditions_per_paper.csv"))))
    conds = {
        "medium": "medium",
        "ionic_strength": "ionic strength",
        "pH": "pH",
        "temperature": "temperature",
        "instrument": "instrument",
    }
    habit = [frozenset(c for c in conds if int(r[c + "_reported_rows"])) for r in per]
    sizes: dict[frozenset, int] = {}
    for h in habit:
        sizes[h] = sizes.get(h, 0) + 1
    counts = sorted(sizes.values(), reverse=True)
    E["pp.n"] = len(per)
    for c in conds:
        E[f"pp.any.{c}_reported"] = sum(c in h for h in habit)
    for i, k in enumerate(counts[:9]):
        E[f"pp.h.{i}"] = k
    E["pp.rest.k"], E["pp.rest.n"] = len(counts[9:]), sum(counts[9:])
    top = max(sizes, key=sizes.get)
    said = [f"the {w}" for c, w in conds.items() if c in top]
    E["pp.top"] = said[0] if len(said) == 1 else ", ".join(said[:-1]) + " and " + said[-1]
    E["pp.none"], E["pp.all"] = sizes.get(frozenset(), 0), sizes.get(frozenset(conds), 0)
    E["pp.mixed"] = sum(
        any(float(r[c + "_reported_share"]) not in (0.0, 1.0) for c in conds) for r in per
    )

    # slide 5: the quantity and instrument columns of the table
    d1 = list(csv.DictReader(io.StringIO(get("out/tables/d1_zeta_table.csv"))))
    E["zb.zeta_rows"] = sum(r["quantity"] == "zeta_potential" for r in d1)
    E["zb.mob_rows"] = sum(r["quantity"] == "electrophoretic_mobility" for r in d1)
    named = [r["instrument"] for r in d1 if r["instrument"].strip()]
    E["zb.zetasizer"] = [sum("zetasizer" in s.lower() for s in named), len(named)]

    # slide 17: ionic strength with the supplements, recounted from the table and the accepted rows
    si_rows = set(json.loads(get("out/tables/si_rates.json"))["accepted_rows"])
    papers: dict[str, list[dict]] = {}
    for r in d1:
        papers.setdefault(r["pmcid"], []).append(r)

    def stated(r: dict, with_si: bool) -> bool:
        return r["ionic_strength_reported"] == "True" or (with_si and r["row_id"] in si_rows)

    E["si.mean"] = Near(
        statistics.fmean(sum(stated(r, True) for r in rs) / len(rs) for rs in papers.values()),
        1e-9,
    )
    E["si.new"] = sum(
        any(stated(r, True) for r in rs) and not any(stated(r, False) for r in rs)
        for rs in papers.values()
    )

    # slide 10: the commit at which the predictions were written
    prereg = json.loads(get("out/tables/p2_prereg_results.json"))
    E["pr.commit"] = prereg["prereg_commit"]

    # slide 19: the P2 table with csv and statistics
    p2 = list(csv.DictReader(io.StringIO(get("out/tables/p2_zeta_size.csv"))))
    E["p2.rows"], E["p2.papers"] = len(p2), len({r["pmcid"] for r in p2})
    size = [math.log10(float(r["size_nm"])) for r in p2]
    zeta = [float(r["zeta_mV"]) for r in p2]
    E["p2.rho"] = Near(statistics.correlation(_ranks(size), _ranks(zeta)), 0.005)
    groups: dict = {}
    for r in p2:
        groups.setdefault(r["material_group"], []).append(r)
    named_groups = {g: rs for g, rs in groups.items() if g != "other" and len(rs) >= 10}
    meds = {g: _quantile([float(r["zeta_mV"]) for r in rs], 0.5) for g, rs in named_groups.items()}
    for g, m in meds.items():
        E[f"p2.pol.{g}.med"] = Near(m, 1e-9)
    neg = [m for m in meds.values() if m < 0]
    E["p2.neg_n"], E["p2.named_n"] = len(neg), len(meds)
    E["p2.neg_lo"], E["p2.neg_hi"] = Near(min(neg), 1e-9), Near(max(neg), 1e-9)
    exc = next(g for g, m in meds.items() if m > 0)
    E["p2.exc"] = exc
    papers_of = [r["pmcid"] for r in named_groups[exc]]
    E["p2.exc_papers"] = len(set(papers_of))
    E["p2.exc_top"] = max(papers_of.count(p) for p in set(papers_of))
    E["p2.exc_n"] = len(papers_of)
    amine = [float(r["zeta_mV"]) for r in groups["PS"] if r["surface"] == "amine"]
    E["p2.amine_neg"], E["p2.amine_n"] = sum(z < 0 for z in amine), len(amine)

    # slide 15: the Weser fractions with csv, the power law solved by bisection on its own formula
    w = list(csv.DictReader(io.StringIO(get("out/tables/p2_weser_pairs.csv"))))
    small = (float(w[0]["small_lo_um"]), float(w[0]["small_hi_um"]))
    large = (float(w[0]["large_lo_um"]), float(w[0]["large_hi_um"]))
    ratios = [float(r["small"]) / float(r["large"]) for r in w if float(r["large"]) > 0]
    E["w.stations"] = len(ratios)
    E["w.small.lo"], E["w.small.hi"] = int(small[0]), int(small[1])
    E["w.large.lo"], E["w.large.hi"] = int(large[0]), int(large[1])
    med = statistics.median(ratios)
    E["w.ratio"] = round(med)

    def count(a: float, b: float, alpha: float) -> float:  # ∫ d^−α from a to b, up to a constant
        return (b ** (1 - alpha) - a ** (1 - alpha)) / (1 - alpha)

    E["w.alpha0"] = prereg["alpha_default"]
    E["w.pred"] = Near(
        count(*small, prereg["alpha_default"]) / count(*large, prereg["alpha_default"]), 1e-6
    )
    a, b = 1.05, 6.0
    while b - a > 1e-9:
        m = (a + b) / 2
        a, b = (m, b) if count(*small, m) / count(*large, m) < med else (a, m)
    E["w.alpha"] = Near(a, 1e-6)
    p1, p2t, p3 = prereg["P1"], prereg["P2"], prereg["P3"]
    E["p1.studies"], E["p1.rho"], E["p1.slope"], E["p1.verdict"] = (
        p1["studies"],
        p1["rho"],
        p1["slope"],
        p1["verdict"],
    )
    E["p2t.cells"], E["p2t.reduction"], E["p2t.verdict"] = (
        p2t["cells"],
        p2t["median_reduction"],
        p2t["verdict"],
    )
    sec = prereg["secondary"]
    diff = sec["P2_cells_with_different_windows"]
    E["p2t.diff_cells"], E["p2t.wider"] = diff["cells"], diff["share_wider_after"]
    E["p3.n"], E["p3.median"], E["p3.verdict"] = (
        p3["distributions"],
        p3["median_alpha"],
        p3["verdict"],
    )
    E["p3.outside"] = Near(1 - p3["share_within_1.6pm0.3"], 1e-12)
    E["p3.lod_median"] = sec["P3_lod_filtered"]["median_alpha"]
    E["p3.band_lo"], E["p3.band_hi"] = prereg["alpha_band"]

    # slide 38 (backup): the tow table with csv, the README's own sentences
    tows = list(
        csv.DictReader(
            io.StringIO(get("tool/colocation/reisser_eriksen/out_2026-10-12/tow_identity_R_E.csv"))
        )
    )
    E["re.tows"] = len(tows)
    by: dict = {}
    for t in tows:
        r, e = float(t["value_R"]), float(t["value_E"])
        if r > 0 and e > 0:
            by.setdefault(t["Sampling Method"], []).append(r / e)
    E["re.manta"] = Near(statistics.median(by["Manta net"]), 1e-9)
    E["re.neuston"] = Near(statistics.median(by["Neuston net"]), 1e-9)
    E["re.zero"] = sum(float(t["value_E"]) == 0 and float(t["value_R"]) > 0 for t in tows)
    readme = flat(get("tool/colocation/reisser_eriksen/README.md"))
    E["re.trap"] = float(one(readme, r"own wind-mixing median of ([\d.]+) is a coincidence")[0])
    E["re.same"] = int(one(readme, r"within 0\.1 % for (\d+) of the")[0])

    # slide 40 (backup): the validation metrics, the labelling page's sample size, the results note
    vm = json.loads(get("out/tables/validate_sign_metrics.json"))
    E["v.cands"], E["v.papers"] = vm["candidates"], vm["papers"]
    E["v.v0"] = vm["candidates"] - vm["V0"]["abstained"]
    E["v.v1_rej"] = vm["v1_rejected"]["A"]
    E["v.v2_kept"] = vm["candidates"] - vm["V2"]["abstained"]
    E["v.v2_abst"] = vm["V2"]["abstained"]
    E["v.kappa"], E["v.agree"] = vm["reader_kappa_raw"], vm["reader_agreement_raw"]
    E["v.modelA"], E["v.modelB"] = vm["cost_A"]["model"], vm["cost_B"]["model"]
    E["v.tokA"], E["v.secA"] = vm["cost_A"]["input_tokens"], round(vm["cost_A"]["seconds"])
    E["v.labelled"] = vm["labelled"]
    E["v.label_target"] = int(one(get("tool/validate/build_labels.py"), r"\nN = (\d+)\n")[0])
    notes = flat(get("docs/2026-10-19-validation-results.md"))
    E["v.first_rej"] = int(one(notes, r"rejected (\d+) reader answers")[0])
    E["v.guard"] = int(one(notes, r"(\d+) of them were \"corona\" answers")[0])

    # slide 41 (backup): the judges, recounted from the raw judge records, not the metrics file
    jm = json.loads(get("out/tables/validate_judge_metrics.json"))
    last = {}
    for text in get("data/interim/validate/sign/judge_items.jsonl").splitlines():
        it = json.loads(text)
        last[(it["judge"], it["pmcid"], it["reader"], it["variant"])] = it

    def judged(jd: str, variant: str, reader: str | None = None) -> dict:
        return {
            (p, r, str(e["row_id"])): e
            for (j, p, r, v), it in last.items()
            if j == jd and v == variant and reader in (None, r)
            for e in (it["answer"] or {}).get("rows") or []
            if isinstance(e, dict) and e.get("row_id")
        }

    def share(entries, test) -> Near:
        return Near(sum(map(test, entries)) / len(entries), 5e-4)

    def name(jd: str) -> str:
        return re.sub(r"-instruct$", "", re.sub(r"^.*[:/]", "", jd))

    for i, jd in enumerate([*jm["judges"], "claude"], start=1):
        o0, o1 = judged(jd, "order0"), judged(jd, "order1")
        E[f"j.{i}.name"] = jm["self_preference_probe"] if jd == "claude" else name(jd)
        E[f"j.{i}.rows"] = [len(judged(jd, "order0", "A")), vm["candidates"]]
        E[f"j.{i}.yes"] = share(
            judged(jd, "order0", "A").values(), lambda e: str(e.get("J1")).lower() == "yes"
        )
        both = o0.keys() & o1.keys()
        E[f"j.{i}.flip"] = share([str(o0[k].get("J2")) != str(o1[k].get("J2")) for k in both], bool)
        decoy = judged(jd, "decoy").values()
        E[f"j.{i}.decoy"] = (
            share(decoy, lambda e: str(e.get("J1")).lower() == "yes") if decoy else "not asked"
        )
        traps = [it for (j, _, _, v), it in last.items() if j == jd and v == "trap"]
        E[f"j.{i}.traps"] = [
            sum(str((t["answer"] or {}).get("J1", "")).lower() == "no" for t in traps),
            len(traps),
        ]
    rates = {
        jd: sum(str(e.get("J1")).lower() == "yes" for e in judged(jd, "decoy").values())
        / len(judged(jd, "decoy"))
        for jd in jm["judges"]
    }
    top = max(rates, key=rates.get)
    E["j.decoy_top.name"], E["j.decoy_top"] = name(top), Near(rates[top], 5e-4)

    # slides 11 to 15: the survey outputs, the counts redone from their rows where they have any
    co = json.loads(get("out/tables/survey_colocated.json"))
    names = {"ncei": "ncei", "mpsed": "mpsed", "soil": "soil", "pangaea_weser": "weser",
             "emodnet": "emodnet", "kiessling2021": "kiessling", "durum": "durum",
             "rivm": "rivm", "sfbay": "sfbay", "aomi": "aomi"}  # fmt: skip
    user = ("durum", "rivm", "sfbay", "aomi")
    scout = ("kiessling2021",)
    found = [k for k in co["records"] if k not in names]
    assert all(k.startswith("pangaea_") and k[8:].isdigit() for k in found), found
    for ds, n_ in co["records"].items():
        if ds in names:
            E[f"sv.n.{names[ds]}"] = n_
    E["sv.n.found"] = sum(co["records"][k] for k in found)
    E["sv.n.datasets"], E["ds.joined"] = len(co["records"]), len(found)
    E["found.total"] = len(found) + sum(k in co["records"] for k in scout)
    # the scout: candidates and claims recounted from the verified rows
    sc = list(csv.DictReader(io.StringIO(get("out/tables/dataset_scout_verified.csv"))))
    E["sc.cands"], E["sc.usable"] = len(sc), sum(r["verdict"] == "usable" for r in sc)
    E["sc.opened"] = sum(int(r["files_opened"]) > 0 for r in sc)
    E["sc.joined"] = sum(k in co["records"] for k in scout)
    cells = [r[k] for r in sc for k in r if k.startswith("agree_")]
    E["sc.tested"] = sum(c in ("True", "False") for c in cells)
    E["sc.held"] = cells.count("True")
    E["sv.total"] = sum(co["records"].values())
    # the search funnel, recounted from the per-candidate rows where the rows hold the stage
    cands = list(csv.DictReader(io.StringIO(get("out/tables/dataset_candidates.csv"))))
    search = json.loads(get("out/tables/dataset_search.json"))
    E["ds.found"], E["ds.distinct"] = search["found"], search["distinct"]
    E["ds.on_topic"] = len(cands)
    E["ds.to_verify"] = sum(r["stage"] == "verified" for r in cands)
    for key in ("usable", "partial", "not_verifiable"):
        E[f"ds.{key}"] = sum(r["verdict"] == key for r in cands)
    miss = {
        r["dataset"]: r
        for r in csv.DictReader(io.StringIO(get("out/tables/survey_completeness.csv")))
    }
    E["sv.miss.emodnet.mesh"] = float(miss["emodnet"]["size_min_um"])
    E["sv.miss.kiessling.window"] = float(miss["kiessling2021"]["size_min_um"])
    E["sv.miss.durum.date"] = float(miss["durum"]["date"])
    E["sv.miss.rivm.date"] = float(miss["rivm"]["date"])
    E["sv.miss.aomi.mesh"] = float(miss["aomi"]["size_min_um"])
    E["sv.n.user"] = sum(k in co["records"] for k in user)
    E["sv.found_nolower"] = sum(float(miss[k]["size_min_um"]) == 1.0 for k in found)
    E["sv.miss.mpsed.lat"] = float(miss["mpsed"]["lat"])
    E["sv.miss.mpsed.year"] = float(miss["mpsed"]["year"])
    E["sv.miss.soil.method"] = float(miss["soil"]["method"])
    E["sv.miss.soil.year"] = float(miss["soil"]["year"])
    E["sv.miss.ncei.mesh"] = float(miss["ncei"]["size_min_um"])
    p7 = json.loads(get("out/tables/survey_p7.json"))
    per = {int(x["period"]): x for x in p7["P7c"]["periods"]}
    E["sv.pooled"] = Near(per[2020]["median_per_record"] / per[2000]["median_per_record"], 0.06)
    for key, start in (("from", 2000), ("to", 2020), ("peak", 2015)):
        assert start in per, start
        E[f"sv.y_{key}"], E[f"sv.y_{key}_end"] = start, start + 4
    E["sv.studies_from"], E["sv.studies_to"] = per[2000]["studies"], per[2020]["studies"]
    E["sv.studies_peak"] = per[2015]["studies"]
    E["sv.law_rho"], E["sv.law_tows"] = p7["P7a"]["spearman_rho"], p7["P7a"]["tows"]
    E["sv.law_y0"], E["sv.law_y1"] = p7["P7a"]["years"]
    E["sv.p7a"], E["sv.p7b"] = p7["P7a"]["verdict"], p7["P7b"]["verdict"]
    ser = {x["series"]: x for x in p7["P7b"]["series"]}
    E["sv.goldstein"] = ser["Goldstein et al. 2013"]["ratio_last_over_first"]
    E["sv.law14"] = ser["Law et al. 2014"]["ratio_last_over_first"]
    for i, x in enumerate(p7["P7c"]["periods"]):
        E[f"rise.p.{i}"], E[f"rise.n.{i}"] = int(x["period"]), x["studies"]
    zone = p7["P7_secondary_law2014_zone"]
    E["sv.law14_zone"] = zone["ratio_inside_zone"]
    E["sv.zone_first"] = zone["share_in_zone_first_third"]
    E["sv.zone_last"] = zone["share_in_zone_last_third"]
    same, anym = co["same_method_50km_365d"], co["any_method_50km_365d"]
    med = co["mediterranean_same_method_50km_365d"]
    E["sv.co.km"], E["sv.co.days"] = same["km"], same["days"]
    E["sv.co.median"], E["sv.co.p90"] = same["median_fold"], same["p90_fold"]
    E["sv.co.pairs"], E["sv.co.studypairs"] = same["pairs"], same["study_pairs"]
    E["sv.co.excluded"] = same["excluded_held_twice"]
    E["sv.co.any_median"], E["sv.co.any_p90"] = anym["median_fold"], anym["p90_fold"]
    E["sv.co.med_median"], E["sv.co.med_studypairs"] = med["median_fold"], med["study_pairs"]
    within = co["within_study_50km_365d"]
    E["sv.co.within"], E["sv.co.within_p90"] = within["median_fold"], within["p90_fold"]
    E["sv.co.within_pairs"], E["sv.co.within_studies"] = within["pairs"], within["studies"]
    # the floor must sit below the gap it is a floor for
    assert within["median_fold"] < same["median_fold"]
    # across databases: the groups add up to the totals; AOMI against NOAA with one window is the
    # same-place check, after the pairs whose studies hold the same samples are gone
    x = co["across_datasets"]
    groups = {(g["datasets"], g["decision"]): g for g in x["by_dataset_pair"]}
    kept = sum(g["pairs"] for (_, dec), g in groups.items() if dec != "refuse")
    assert kept == x["compared"] and kept + x["refused"] == x["pairs"]
    same, wider = groups[("aomi vs ncei", "allow")], groups[("aomi vs ncei", "caveat")]
    E["sv.x.km"], E["sv.x.days"], E["sv.x.held"] = x["km"], x["days"], x["excluded_held_twice"]
    E["sv.x.compared"], E["sv.x.cav"] = same["pairs"], wider["pairs"]
    E["sv.x.refused"] = x["refused"]
    E["sv.x.median"], E["sv.x.p90"] = same["median_fold"], same["p90_fold"]
    E["sv.x.residual"] = wider["median_residual_fold"]
    dup = list(csv.DictReader(io.StringIO(get("out/tables/survey_duplicates.csv"))))
    E["sv.dup.n"] = len(dup)
    # a pair with a zero on one side has no ratio, so it cannot be identical
    E["sv.dup.identical"] = sum(
        r["median_ratio_a_over_b"] != "" and abs(float(r["median_ratio_a_over_b"]) - 1) < 0.01
        for r in dup
    )
    side = [(r["study_a"].startswith("aomi:"), r["study_b"].startswith("aomi:")) for r in dup]
    E["sv.dup.ncei"] = sum(not a and not b for a, b in side)
    E["sv.dup.aomi"] = sum(a != b for a, b in side)
    E["sv.dup.aomi_self"] = sum(a and b for a, b in side)
    shared: dict[str, int] = {}
    for r, (a, b) in zip(dup, side, strict=True):
        if a != b:
            st, n = (r["study_b"], r["records_b"]) if b else (r["study_a"], r["records_a"])
            shared[st] = max(shared.get(st, 0), int(n))
    E["sv.dup.aomi_records"] = sum(shared.values())
    # NOAA's own pair, not AOMI's copies of the same two studies
    E["sv.dup.re_found"] = next(
        int(r["records_a"])
        for r in dup
        if (r["study_a"], r["study_b"])
        == (
            "https://doi.org/10.1371/journal.pone.0080466",
            "https://doi.org/10.1371/journal.pone.0111913",
        )
    )

    # slides 29 and 30: every arm recounted from the per-question rows, not the summary fields
    hy = json.loads(get("out/tables/hybrid_results.json"))
    hq = [json.loads(x) for x in get("queries/hybrid_questions.jsonl").splitlines() if x.strip()]
    E["hy.q"], E["hy.adv"] = len(hq), sum(q["adversarial"] for q in hq)
    E["hy.flagq"] = sum(q["verdict"] != "allow" for q in hq)
    rows = hy["per_question"]
    E["hy.reps"] = len({r["rep"] for r in rows if r["arm"] == "H"})

    def share(arm, keep=lambda r: True, field="correct"):
        xs = [r[field] for r in rows if r["arm"] == arm and keep(r) and r[field] is not None]
        return Near(sum(xs) / len(xs), 6e-4)

    for arm in ("N0", "N2", "H", "Hg", "Hng"):
        E[f"hy.{arm}.correct"] = share(arm)
        E[f"hy.{arm}.adv"] = share(arm, lambda r: r["adversarial"])
        E[f"hy.{arm}.flag"] = share(arm, lambda r: r["flag_required"])
        E[f"hy.{arm}.noflag"] = share(arm, lambda r: not r["flag_required"])
        ung = [r["ungrounded"] for r in rows if r["arm"] == arm and r["ungrounded"] is not None]
        E[f"hy.{arm}.ungrounded"] = Near(sum(ung) / len(ung), 6e-3) if ung else "not scored"
        if arm in ("N0", "N2", "H"):
            sel = [r for r in rows if r["arm"] == arm]
            E[f"hy.{arm}.tokens"] = round(sum(r["input_tokens"] for r in sel) / len(sel))
            E[f"hy.{arm}.sec"] = Near(sum(r["seconds"] for r in sel) / len(sel), 6e-3)
    hmap = {(r["qid"], r["rep"]): r["correct"] for r in rows if r["arm"] == "H"}
    n2 = [(r["correct"], hmap[(r["qid"], r["rep"])]) for r in rows if r["arm"] == "N2"]
    E["hy.paired"] = len(n2)
    E["hy.only_H"] = sum(h and not a for a, h in n2)
    E["hy.only_N2"] = sum(a and not h for a, h in n2)
    pv = binomtest(E["hy.only_N2"], E["hy.only_N2"] + E["hy.only_H"], 0.5).pvalue
    E["hy.p"] = "< 0.001" if pv < 0.001 else Near(pv, 6e-4)
    E["hy.H.plan"] = share("H", field="plan_matches_ref")
    prereg = flat(get("docs/PREREG_2026-10.md"))
    E["hy.p9_min"] = float(one(prereg, r"flag-required questions by at least (\d+(?:\.\d+)?)")[0])
    E["hy.code"] = one(prereg, r"Code at `([0-9a-f]{7})`")[0]
    h, a2 = hy["arms"]["H"], hy["arms"]["N2"]
    E["hy.p8"] = ("refuted" if a2["correct"] >= h["correct"]
                  else ("supported" if a2["vs_H"]["p"] < 0.05 else "not significant"))  # fmt: skip
    drop = h["correct_flag_required"] - hy["arms"]["Hg"]["correct_flag_required"]
    E["hy.p9"] = ("supported" if drop >= E["hy.p9_min"]
                  else ("refuted" if drop < 0.1 else "partly"))  # fmt: skip

    # slide 20: P11 recounted from the pairs, the sign test from the binomial by hand
    ag = json.loads(get("out/tables/p2_aging.json"))
    pairs = list(csv.DictReader(io.StringIO(get("out/tables/p2_aging_pairs.csv"))))
    per: dict[str, list[float]] = {}
    for r in pairs:
        if r["kind"] in ("photo", "chemical"):
            per.setdefault(r["pmcid"], []).append(float(r["delta_mV"]))
    meds = sorted(statistics.median(v) for v in per.values())
    neg, pos = sum(m < 0 for m in meds), sum(m > 0 for m in meds)
    E["ag.a.papers"], E["ag.a.neg"], E["ag.a.pos"] = len(meds), neg, pos
    E["ag.a.median"] = statistics.median(meds)
    n = neg + pos
    tail = sum(math.comb(n, k) for k in range(0, min(neg, pos) + 1)) / 2**n
    E["ag.a.p"] = min(1.0, 2 * tail)
    for i, m in enumerate(meds):
        E[f"ag.paper.{i}"] = m
    E["ag.pairs"], E["ag.paired_papers"] = len(pairs), len({r["pmcid"] for r in pairs})
    E["ag.aged_rows"], E["ag.aged_papers"] = ag["aged_rows"], ag["aged_papers"]
    E["ag.a.lo"], E["ag.a.hi"] = ag["P11a"]["ci95"]
    b = ag["P11b"]
    E["ag.b.median"], (E["ag.b.lo"], E["ag.b.hi"]) = b["median_difference_mV"], b["ci95"]
    paired = ag["P11a"]["ci95"]
    E["ag.b.ratio"] = (b["ci95"][1] - b["ci95"][0]) / (paired[1] - paired[0])
    share = neg / len(meds)
    E["ag.a.verdict"] = "supported" if share >= 2 / 3 else "refuted" if share <= 1 / 2 else "partly"
    r_ = E["ag.b.ratio"]
    E["ag.b.verdict"] = "supported" if r_ >= 2 else "refuted" if r_ < 1 else "partly"
    iqr = ag["chosen_after_the_results"]["virgin_between_papers"]["PS"]["iqr_mV"]
    E["ag.iqr.PS"], E["ag.scale"] = iqr, iqr / abs(E["ag.a.median"])
    seen = {(r["pmcid"], r["aged_mV"], r["virgin_median_mV"]) for r in pairs}
    E["ag.swap"] = next(pm for pm, a, v in seen if a != v and (pm, v, a) in seen)

    # slide 7: the flags and sources recounted with csv, the scanner's coverage with json
    rows = list(csv.DictReader(io.StringIO(get("out/tables/d1_zeta_table.csv"))))
    fl = [{x.strip() for x in r["flags"].split(";")} for r in rows]

    def count(*names):
        return sum(bool(f & set(names)) for f in fl)

    E["fl.unit_assumed"] = count("unit_assumed_mV", "unit_assumed_um_cm_per_Vs")
    E["fl.not_printed"], E["fl.range"] = count("value_not_printed"), count("value_is_range")
    E["fl.converted"] = count("unit_converted", "kelvin_converted")
    E["fl.not_in_quote"] = count("value_not_in_quote")
    src_ = [r["ionic_strength_source"] for r in rows]
    E["is.reported"], E["is.salt"] = src_.count("reported"), src_.count("inferred_from_named_salt")
    E["is.unreported"] = src_.count("unreported")
    assert E["is.reported"] + E["is.salt"] + E["is.unreported"] == len(rows)
    last = {}
    for ln in get("data/interim/extractions.jsonl").splitlines():
        if ln.strip():
            r = json.loads(ln)
            last[r["pmcid"]] = r
    E["cov.cand"] = sum(r.get("n_candidates") or 0 for r in last.values())
    E["cov.matched"] = sum(r.get("n_candidates_matched") or 0 for r in last.values())
    assert E["cov.matched"] <= E["cov.cand"]

    # slide 12 and backup slide 31: the per-study table, counted with csv
    st = list(csv.DictReader(io.StringIO(get("out/tables/survey_studies.csv"))))

    def num(x):
        return float(x) if x not in ("", None) else math.nan

    def windowed(r):
        return not math.isnan(num(r["size_min_um"])) and not math.isnan(num(r["size_max_um"]))

    drawn = [r for r in st if int(r["n_pos"]) > 0 and num(r["p10"]) > 0 and windowed(r)]
    ocean = [r for r in drawn if r["setting"] == "Ocean water" and r["unit"] == "pieces/m3"]
    E["win.ncei.n"] = sum(r["dataset"] == "ncei" for r in ocean)
    E["win.emodnet.n"] = sum(r["dataset"] == "emodnet" for r in ocean)
    # the agents' ocean finds are the PANGAEA sets; AOMI came from the reference list
    E["win.found.n"] = sum(r["dataset"].startswith("pangaea_") for r in ocean)
    panels = {"ocean": (("Ocean water",), "pieces/m3"), "river": (("river water",), "pieces/m3"),
              "storm": (("stormwater runoff",), "particles/L"),
              "sed": (("sediment",), "microplastic/kg sediment dry wt."),
              "soil": (("soil",), "items/kg")}  # fmt: skip
    for k, (settings, unit) in panels.items():
        E[f"win.{k}.n"] = sum(r["setting"] in settings and r["unit"] == unit for r in drawn)
    fresh = ("river water", "lake water", "stormwater runoff")
    E["map.fresh.n"] = sum(r["setting"] in fresh and not math.isnan(num(r["lat"])) for r in st)
    E["map.ocean.n"] = sum(
        r["setting"] == "Ocean water" and r["unit"] == "pieces/m3"
        and not math.isnan(num(r["lat"])) and num(r["p50"]) > 0 for r in st
    )  # fmt: skip
    E["map.soil.n"] = sum(r["setting"] == "soil" and not math.isnan(num(r["lat"])) for r in st)

    # slide 23: the gap table read with csv; case 14's row must be the case 14 the deck shows
    for r in csv.DictReader(io.StringIO(get("out/tables/gap_ladder.csv"))):
        E[f"gap.{r['key']}"] = float(r["value"])
        if r["high"]:
            E[f"gap.{r['key']}.high"] = float(r["high"])
        E[f"gap.{r['key']}.label"], E[f"gap.{r['key']}.tag"] = r["label"], r["tag"]
    zeta = {
        r["row_id"]: r for r in csv.DictReader(io.StringIO(get("out/tables/d1_zeta_table.csv")))
    }
    pair = [float(zeta[k]["value"]) for k in ("PMC10260929-r1", "PMC13298883-r1")]
    assert abs(E["gap.case14"] - abs(pair[0] - pair[1])) < 1e-9
    verified = list(csv.DictReader(io.StringIO(get("out/tables/gap_scout_verified.csv"))))
    nano = next(r for r in verified if r["name"].startswith("NanoValid") and r["kept"] == "True")
    said = "the zeta potential method is not recommended as reference"
    assert said in json.loads(nano["extra_found"])[0]
    E["gap.nanovalid.said"] = said

    # slide 24: every verdict, read from its own results file
    pre = json.loads(get("out/tables/p2_prereg_results.json"))
    verdicts = [pre[k]["verdict"] for k in ("P1", "P2", "P3", "P4")]
    verdicts += [E["sv.p7a"], E["sv.p7b"], E["hy.p8"], E["hy.p9"]]
    verdicts += [E["ag.a.verdict"], E["ag.b.verdict"]]
    E["pv.n"] = len(verdicts)
    for v in ("supported", "partly", "refuted"):
        E[f"pv.{v}"] = verdicts.count(v)
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

    printed = one(review, r"Rows per `medium_class`: ([^.]+)\.")[0]
    per_liquid = {
        name.strip(): int(k) for name, k in re.findall(r"([a-zA-Z ]+?) (\d+)(?:,|$)", printed)
    }
    words = {"DI_water": "DI water", "unreported": "unreported"}
    for key in (k for k in V if k.startswith("lab.") and k.endswith(".rows")):
        cls = key.split(".")[1]
        assert per_liquid[words.get(cls, cls.replace("_", " "))] == V[key], key

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
    assert {t["chart"] for t in ticks} == {
        "c14",
        "c02",
        "fields",
        "henry",
        "lab",
        "curve",
        "pol",
        "rise",
        "aging",
        "win_ocean",
        "win_river",
        "win_storm",
        "win_sed",
        "win_soil",
        "map",
        "gaps_c",
        "gaps_n",
    }
    for t in ticks:
        lo, hi = charts[t["chart"]][t["axis"]]
        assert lo - 1e-9 <= t["v"] <= hi + 1e-9, t
    for name in ("c14", "c02", "fields", "lab"):
        lo, hi = charts[name]["x"]
        assert all(lo <= m <= hi for m in charts[name]["marks"]), name
    c = charts["curve"]
    at = min(range(len(c["grid"])), key=lambda i: abs(c["grid"][i] - c["match"][0]))
    assert math.isclose(c["grid"][at], c["match"][0], rel_tol=1e-9)
    for s in c["soft"]:
        assert math.isclose(s["mu"][at], c["hard"][at], rel_tol=1e-6)
        assert abs(c["hard"][-1]) < abs(s["plateau"]) <= min(abs(m) for m in s["mu"]) + 1e-12
    lo, hi = charts["pol"]["x"]
    assert all(lo <= r["p10"] <= r["med"] <= r["p90"] <= hi for r in charts["pol"]["rows"])
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
    (r"\bV[0-3]\b", None, "rung"),
    (r"\bP(?:1[01]|[1-9])\b", None, "prediction"),
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
    design = show("docs/DESIGN_2026-10-18_hypotheses-method-evaluation.md")
    prereg = show("docs/PREREG_2026-10.md")
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
        elif kind == "rung":
            assert f"| **{token}** |" in design, token
        elif kind == "prediction":
            covered = {
                n
                for lo, hi in re.findall(r"\n## P(\d+)(?:–P(\d+))? · ", prereg)
                for n in range(int(lo), int(hi or lo) + 1)
            }
            assert int(token[1:]) in covered, token


def test_the_data_is_inlined_whole(deck, page) -> None:
    m = re.search(r'<script type="application/json" id="deck-data">(.*?)</script>', page, re.S)
    assert m and json.loads(m.group(1)) == json.loads(json.dumps(deck))


def test_every_slide_has_a_title_a_message_and_notes(page) -> None:
    slides = re.findall(
        r'<section class="slide[^"]*" id="(s\d+)"(.*?)</section>'
        r'\s*(?=<section class="slide|</main>)',
        page,
        re.S,
    )
    assert [s for s, _ in slides] == [f"s{i}" for i in range(1, 45)]
    backup = re.findall(r'<section class="slide backup" id="(s\d+)"', page)
    assert backup == [f"s{i}" for i in range(27, 45)]
    for sid, body in slides:
        assert re.search(r"<h[12]>", body), sid
        assert sid == "s1" or 'class="msg"' in body, sid
        notes = re.findall(r'<aside class="notes"[^>]*>(.*?)</aside>', body, re.S)
        assert len(notes) == 1, sid
        prose = re.sub(r"<[^>]+>", "", re.sub(r'<span class="label">[^<]*</span>', "", notes[0]))
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", prose.strip()) if s]
        assert 2 <= len(sentences) <= 4, (sid, len(sentences))


def test_no_di_water_row_gained_an_ionic_strength_from_the_supplements() -> None:
    # The script says so; the SI rescued rows whose liquid the main text left unnamed.
    si_rows = set(json.loads(show("out/tables/si_rates.json"))["accepted_rows"])
    d1 = rows_by_id(show("out/tables/d1_zeta_table.csv"))
    assert si_rows <= set(d1)
    assert not [r for r in si_rows if d1[r]["medium_class"] == "DI_water"]


def test_the_standalone_page_opens_from_a_file(bs, page) -> None:
    doc = bs.standalone(page)
    assert doc.startswith("<!doctype html>") and doc.rstrip().endswith("</html>")
    assert 'name="viewport" content="width=device-width' in doc
    assert page in doc


def test_the_hybrid_slides_say_what_the_runs_did(deck) -> None:
    # slide 29's notes: pasted-data Claude misses traps; slide 30: unguarded Claude over-flags,
    # it never misses a needed flag, and loses on the questions that need a plain answer.
    V = {k: v["v"] for k, v in deck["values"].items()}
    assert V["hy.N2.adv"] < V["hy.H.adv"] and V["hy.N0.correct"] < V["hy.N2.correct"]
    assert V["hy.Hg.flag"] == 1.0  # "the model alone never missed a needed caveat"
    assert V["hy.Hg.noflag"] < V["hy.H.noflag"] - 0.3


def test_the_judges_slide_says_what_the_judges_did(deck) -> None:
    # "Claude was no softer on its own family, but its pick moved with the order of the list."
    V = {k: v["v"] for k, v in deck["values"].items()}
    jury = (1, 2, 3)
    assert V["j.4.yes"] <= min(V[f"j.{i}.yes"] for i in jury)
    assert V["j.4.flip"] > max(V[f"j.{i}.flip"] for i in jury)


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


# ---- the talk script (build_script.py) ----------------------------------------------------------


@pytest.fixture(scope="module")
def sc():
    spec = importlib.util.spec_from_file_location("build_script", HERE / "build_script.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script_page(sc, deck, page):
    return sc.render(deck, page)


@pytest.fixture(scope="module")
def script_scan(script_page):
    s = Scan()
    s.feed(script_page)
    s.close()
    return s


def test_the_time_plan_fills_twenty_minutes_over_five_acts(sc) -> None:
    # The order of 2026-10-25: why standardise, the engineering, the datasets, the papers, the way
    # forward. Twenty minutes; the backup slides untimed.
    assert [s for _, _, slides in sc.ACTS for s in slides] == list(sc.PLAN)
    assert list(sc.PLAN) == [f"s{i}" for i in range(1, 27)]
    assert sc.BACKUP == tuple(f"s{i}" for i in range(27, 45))
    acts = {name: sum(sc.PLAN[s] for s in slides) for name, _, slides in sc.ACTS}
    assert acts == {"I": 160, "II": 235, "III": 295, "IV": 305, "V": 205}
    assert sc.timing_values()["at.s26"]["text"] == "20:00"


def test_no_card_asks_for_more_than_130_words_a_minute(sc, script_page) -> None:
    # A rehearsal at a speaking pace a second-language speaker can hold, pauses included.
    for sid, seconds in sc.PLAN.items():
        card = re.search(rf'<section class="card" id="{sid}">(.*?)</section>', script_page, re.S)
        say = re.search(r'<div class="say">(.*?)</div>', card.group(1), re.S).group(1)
        say = re.sub(r'<span class="pause">pause</span>', "", say)
        words = len(html.unescape(re.sub(r"<[^>]+>", " ", say)).split())
        assert words / seconds * 60 <= 130, (sid, words, seconds)


def test_the_script_has_one_card_per_slide_under_the_decks_title(script_page, page) -> None:
    cards = re.findall(r'<section class="card" id="(s\d+)">(.*?)</section>', script_page, re.S)
    assert [sid for sid, _ in cards] == [f"s{i}" for i in range(1, 45)]
    titles = {
        sid: re.search(r"<h([12])[^>]*>(.*?)</h\1>", body, re.S).group(2)
        for sid, body in re.findall(
            r'<section class="slide[^"]*" id="(s\d+)"(.*?)</section>'
            r'\s*(?=<section class="slide|</main>)',
            page,
            re.S,
        )
    }
    for sid, body in cards:
        assert f"<h3>{titles[sid]}</h3>" in body, sid
        assert 'class="say"' in body, sid


def test_the_script_markup_nests_and_has_no_open_slot(script_scan, script_page) -> None:
    assert not script_scan.errors, script_scan.errors[:5]
    assert not script_scan.stack, [t for t, _, _ in script_scan.stack]
    assert "{{" not in script_page and "__DATA__" not in script_page


def test_every_script_slot_shows_its_value(sc, deck, script_scan) -> None:
    values = {**deck["values"], **sc.timing_values()}
    wrong = [
        (k, t, values[k]["text"])
        for k, t in script_scan.owned
        if k in values and t != values[k]["text"]
    ]
    unknown = [k for k, _ in script_scan.owned if k not in values and k != "build.commit"]
    assert not wrong and not unknown, (wrong[:5], unknown[:5])


def test_no_digit_in_the_script_is_untraced(script_scan) -> None:
    _, stray = _allowed_tokens(script_scan)
    assert not stray, stray[:10]


def test_every_identifier_in_the_script_exists_in_its_source(script_scan) -> None:
    test_every_identifier_shown_exists_in_its_source(script_scan)


def test_the_script_follows_the_artifact_contract(script_page) -> None:
    title = one(script_page, r"<title>([^<]+)</title>")[0]
    assert 2 <= len(title.split()) <= 4 and ":" not in title
    assert not re.search(r"<!doctype|<(?:html|head|body)[\s>]", script_page, re.I)
    hosts = set(re.findall(r"https?://([^/\"' )]+)", script_page))
    assert hosts <= {"fonts.googleapis.com", "fonts.gstatic.com"}, hosts
    style = script_page.split("<style>", 1)[1].split("</style>", 1)[0]
    root = set(re.findall(r"(--[\w-]+):", one(style, r"(?s):root \{(.*?)\}")[0]))
    for block in (
        one(style, r"(?s):root:not\(\[data-theme=\"light\"\]\) \{(.*?)\}")[0],
        one(style, r"(?s):root\[data-theme=\"dark\"\] \{(.*?)\}")[0],
    ):
        assert "color-scheme: dark" in block
        assert set(re.findall(r"(--[\w-]+):", block)) == root - {"--display", "--text", "--mono"}
    assert re.search(r"body \{[^}]*background: var\(--paper\)", style)
    assert "prefers-reduced-motion" in style
