"""Build data.json for the MNP-KB results page (template.html) from one committed snapshot.

Every input is read with `git show <ref>:<path>`, never from the working tree, so a table that
is being rebuilt cannot leak into the page. What has to be computed is computed by the repo's
own code - `resample`, `comparability`, `harmonise`, `scoring`, `release` - fed that snapshot.
The only values typed in here are the row ids of REVIEW.md's worked examples and the 1.96 of
its naive interval (REVIEW.md §5.3).

The run ends by checking the headline numbers against REVIEW.md at the same ref, writes the
result into `checks`, and exits 1 if any disagree.

    unset VIRTUAL_ENV
    uv run python tool/viz/build_data.py [--ref HEAD] [--out tool/viz/data.json]
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from mnp.demo import harmonise, resample
from mnp.eval import comparability, scoring
from mnp.eval.query_sets import QueryKind
from mnp.report import release, review, scope

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

FLAGS = [
    "medium_reported",
    "ionic_strength_reported",
    "pH_reported",
    "temperature_reported",
    "instrument_reported",
]
METRICS = [*FLAGS, "conditions_complete"]
assert tuple(METRICS) == resample.METRICS

# REVIEW.md §5.3 prints the naive half-width as 1.96 * sqrt(p(1-p)/N). resample carries
# norm.ppf(0.975) = 1.95996 instead; the two agree to 0.001 pp, so both round to what REVIEW prints.
NAIVE_Z = 1.96

# REVIEW.md §5.5 worked examples: the calculator's presets, one per case it can reproduce.
WORKED_ROWS = {
    "H": "PMC11099890-r1",
    "Z1": "PMC12955872-r1",
    "Z2": "PMC10213243-r1",
    "Z3": "PMC10045319-r1",
    "Z4": "PMC10340104-r3",
}

ORIGIN_STATS = "out/tables/sample_origin_stats.json"
ORIGINS = ("commercial", "lab_fabricated", "environmental", "unclear")
ENVIRONMENTS = ("freshwater", "seawater", "wastewater", "soil", "sediment", "air_dust", "biota",
                "other")  # fmt: skip
ORIGIN_CONDITIONS = ("medium", "ionic_strength", "pH", "temperature", "instrument")

TARGET_WINDOW = "1-5000 \N{MICRO SIGN}m"
OTHER_WINDOW = "0.1-5000 \N{MICRO SIGN}m"


def show(ref: str, path: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{ref}:{path}"], capture_output=True, check=True
    )
    return out.stdout.decode("utf-8")


def exists(ref: str, path: str) -> bool:
    done = subprocess.run(["git", "-C", str(REPO), "cat-file", "-e", f"{ref}:{path}"])
    return done.returncode == 0


def read_csv(ref: str, path: str, delimiter: str = ",") -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(show(ref, path)), delimiter=delimiter))


def read_jsonl(ref: str, path: str) -> list[dict]:
    return [json.loads(line) for line in show(ref, path).splitlines() if line.strip()]


def truthy(s: str) -> bool:
    return s == "True"


def blank(s: str | None) -> bool:
    return s is None or not s.strip() or s.strip().lower() == "nan"


def fnum(s: str | None) -> float | None:
    return None if blank(s) else float(s)


def pairs(n: int) -> int:
    return n * (n - 1) // 2


def funnel_and_census(ref: str, d1: list[dict], table: pd.DataFrame) -> dict:
    hits = json.loads(show(ref, "data/raw/epmc/search/hit_counts.json"))
    manifest = show(ref, "data/raw/epmc/manifest.sha256").splitlines()
    xml_fetched = sum(1 for ln in manifest if ln.rstrip().endswith(".xml"))

    n_rows = len(d1)
    n_zeta = sum(1 for r in d1 if r["quantity"] == "zeta_potential")
    complete = sum(truthy(r["conditions_complete"]) for r in d1)

    # REVIEW.md §5.6: the census is `graded_census` over the rows that pass its row filter.
    rows = [comparability.ZetaRow.from_mapping(r) for r in table.to_dict(orient="records")]
    passing = sum(1 for r in rows if comparability._fully_reported(r))
    graded = comparability.graded_census(rows)
    comparable = [s for s in graded if s.verdict.verdict is comparability.Comparability.comparable]
    conditional = [
        s
        for s in graded
        if s.verdict.verdict is comparability.Comparability.conditionally_comparable
    ]

    def zz(s: comparability.PairSpec) -> bool:
        return s.a.quantity.value == "zeta_potential" == s.b.quantity.value

    def cross(s: comparability.PairSpec) -> bool:
        return s.a.pmcid != s.b.pmcid

    census = {
        "all_pairs": pairs(n_rows),
        "zeta_rows": n_zeta,
        "zeta_pairs": pairs(n_zeta),
        "rows_passing": passing,
        "pairs_checked": pairs(passing),
        "comparable": len(comparable),
        "comparable_zeta": sum(zz(s) for s in comparable),
        "comparable_cross": sum(cross(s) for s in comparable),
        "comparable_zeta_cross": sum(zz(s) and cross(s) for s in comparable),
        "conditional": len(conditional),
        "conditional_cross": sum(cross(s) for s in conditional),
    }
    census["not_comparable_checked"] = (
        census["pairs_checked"] - census["comparable"] - census["conditional"]
    )

    def step(label: str, unit: str, n: int, note: str) -> dict:
        return {"label": label, "unit": unit, "n": n, "note": note}

    funnel = [
        step(
            "Europe PMC search hits", "articles", hits["hits_all"], "the query, open access or not"
        ),
        step("open-access hits", "articles", hits["hits_oa"], "full text may be read and quoted"),
        step("full texts fetched", "articles", xml_fetched, "XML files vendored, sha256-pinned"),
        step(
            "papers with a measurement",
            "papers",
            len({r["pmcid"] for r in d1}),
            "at least one zeta or mobility value",
        ),
        step("measurement rows", "rows", n_rows, "one row per reported measurement"),
        step("fully conditioned rows", "rows", complete, "all five conditions on the same row"),
        step("comparable pairs", "pairs", census["comparable"], "of every possible pair of rows"),
        step(
            "comparable zeta pairs across papers",
            "pairs",
            census["comparable_zeta_cross"],
            "two zeta values from two different papers",
        ),
    ]
    return {"funnel": funnel, "census": census}


def five_parameters(d1: list[dict], per_paper: list[dict]) -> dict:
    hist = Counter(sum(truthy(r[f]) for f in FLAGS) for r in d1)
    n = len(d1)

    def split(flag: str, strong, soft) -> dict:
        rep = [r for r in d1 if truthy(r[flag])]
        s = sum(1 for r in rep if strong(r))
        w = sum(1 for r in rep if soft(r))
        assert s + w == len(rep), flag
        return {"strong": s, "soft": w, "unreported": n - len(rep)}

    rows = {
        "medium_reported": split("medium_reported", lambda r: True, lambda r: False),
        "ionic_strength_reported": split(
            "ionic_strength_reported",
            lambda r: r["ionic_strength_source"] == "reported",
            lambda r: r["ionic_strength_source"] == "inferred_from_named_salt",
        ),
        "pH_reported": split("pH_reported", lambda r: not blank(r["pH"]), lambda r: blank(r["pH"])),
        "temperature_reported": split(
            "temperature_reported",
            lambda r: not blank(r["temperature_C"]),
            lambda r: blank(r["temperature_C"]),
        ),
        "instrument_reported": split("instrument_reported", lambda r: True, lambda r: False),
    }
    labels = {
        "medium_reported": ("Medium", "liquid named", None),
        "ionic_strength_reported": (
            "Ionic strength",
            "printed in mM",
            "computed from a printed salt recipe",
        ),
        "pH_reported": ("pH", "one number", "a range or text with a digit"),
        "temperature_reported": (
            "Temperature",
            "a number in \N{DEGREE SIGN}C",
            "nominal: \N{LEFT DOUBLE QUOTATION MARK}room temperature\N{RIGHT DOUBLE QUOTATION MARK}"
            ", \N{LEFT DOUBLE QUOTATION MARK}RT\N{RIGHT DOUBLE QUOTATION MARK}",
        ),
        "instrument_reported": ("Instrument", "named", None),
    }
    k = len(per_paper)
    params = []
    for flag in FLAGS:
        # The mean of conditions_per_paper.csv's printed shares, as REVIEW.md §5.1's
        # spreadsheet takes it; `clustering` holds resample's own per-paper mean.
        shares = [float(p[flag + "_share"]) for p in per_paper]
        name, strong_label, soft_label = labels[flag]
        params.append(
            {
                "key": flag,
                "name": name,
                "strong_label": strong_label,
                "soft_label": soft_label,
                **rows[flag],
                "rows_share": (rows[flag]["strong"] + rows[flag]["soft"]) / n,
                "paper_mean_share": sum(shares) / k,
                "papers_any": sum(1 for p in per_paper if int(p[flag + "_rows"]) > 0),
            }
        )
    complete_shares = [float(p["conditions_complete_share"]) for p in per_paper]
    return {
        "n_rows": n,
        "n_papers": k,
        "histogram": [hist.get(i, 0) for i in range(6)],
        "params": params,
        "complete_rows": sum(truthy(r["conditions_complete"]) for r in d1),
        "complete_paper_mean": sum(complete_shares) / k,
        "complete_papers_any": sum(1 for p in per_paper if int(p["conditions_complete_rows"]) > 0),
    }


def clustering(table: pd.DataFrame, per_paper: list[dict]) -> dict:
    """resample.estimates on the snapshot's table: papers sorted by pmcid, B draws, one seed."""
    estimates = resample.estimates(table)
    metrics = []
    for e in estimates:
        naive = NAIVE_Z * math.sqrt(e.per_row * (1 - e.per_row) / e.n)
        metrics.append(
            {
                "key": e.metric,
                "per_row": float(e.per_row),
                "per_paper": float(e.per_paper),
                "naive_lo": float(e.per_row - naive),
                "naive_hi": float(e.per_row + naive),
                "naive_hw": naive,
                "row_lo": e.row_ci[0],
                "row_hi": e.row_ci[1],
                "paper_lo": e.paper_ci[0],
                "paper_hi": e.paper_ci[1],
                "icc": float(e.icc),
                "deff": float(e.deff),
                "n_eff": float(e.n_eff),
            }
        )
    # one line per paper for the bubble chart: its rows, then its six shares
    papers = [
        [int(p["n_rows"])] + [round(float(p[m + "_share"]), 4) for m in METRICS] for p in per_paper
    ]
    return {
        "N": estimates[0].n,
        "k": estimates[0].k,
        "B": resample.B,
        "seed": resample.SEED,
        "metrics": metrics,
        "papers": papers,
    }


def calculator_model(row: dict) -> str:
    """The calculator's model for a worksheet row, decided by `harmonise`'s own zeta rule, which
    must also give back the worksheet's result."""
    models = frozenset(m for m in row["models_named"].split(";") if m and m != "none")
    model, *_, low, high, point, _why = harmonise._zeta_case(
        float(row["value"]), fnum(row["kappa_a"]), models
    )
    for ours, sheet in ((point, row["point"]), (low, row["low"]), (high, row["high"])):
        assert (ours is None) == blank(sheet), (row["row_id"], ours, sheet)
        assert ours is None or math.isclose(ours, float(sheet), rel_tol=1e-6), (row["row_id"], ours)
    return model or "none"


def harmonise_section(harm: list[dict]) -> dict:
    case_order = ["H", "Z1", "Z2", "Z3", "Z4", "M1", "M2", "M0", "U", "N"]
    cases = Counter(r["case"] for r in harm)
    results = Counter(r["result"] for r in harm)
    # every zeta row with a printed value: [value, case, point, low, high, row_id]
    zeta = [
        [
            float(r["value"]),
            r["case"],
            fnum(r["point"]),
            fnum(r["low"]),
            fnum(r["high"]),
            r["row_id"],
        ]
        for r in harm
        if r["quantity"] == "zeta_potential" and not blank(r["value"])
    ]
    zeta.sort(key=lambda z: (z[0], z[5]))
    by_id = {r["row_id"]: r for r in harm}
    examples = {}
    for case, rid in WORKED_ROWS.items():
        r = by_id[rid]
        assert r["case"] == case, (rid, r["case"])
        examples[case] = {
            "row_id": rid,
            "value": float(r["value"]),
            "ionic_strength_mM": fnum(r["ionic_strength_mM"]),
            "size_nm": fnum(r["size_measured_nm"]),
            "models_named": r["models_named"] or "none",
            "model": calculator_model(r),
            "point": fnum(r["point"]),
            "low": fnum(r["low"]),
            "high": fnum(r["high"]),
        }
    return {
        "case_order": case_order,
        "cases": {c: cases.get(c, 0) for c in case_order},
        "results": {k: results.get(k, 0) for k in ("point", "interval", "none")},
        "zeta": zeta,
        "examples": examples,
        "kappa_known": sum(1 for r in harm if not blank(r["kappa_a"])),
        "mobility_rows": sum(1 for r in harm if r["quantity"] == "electrophoretic_mobility"),
    }


FIELD_OF_CODE = {
    "quantity_mismatch": "quantity",
    "conversion_regime_mismatch": "conversion_model",
    "size_measured_unreported": "size_measured_nm",
}


def code_field(code: str) -> str:
    if code in FIELD_OF_CODE:
        return FIELD_OF_CODE[code]
    for suffix in ("_class_mismatch", "_text_mismatch", "_not_numeric", "_unreported", "_mismatch"):
        if code.endswith(suffix):
            return code[: -len(suffix)]
    raise ValueError(code)


def comparability_section(kind_e: list[dict]) -> dict:
    """What blocks the pairs of the kind E key: per field, pairs where at least one row never
    stated it, and pairs where both stated it and differ."""
    field_total: Counter[str] = Counter()
    field_unreported: Counter[str] = Counter()
    for p in kind_e:
        fields = [f for f in p["blocker_fields"].split(";") if f]
        codes = [c for c in p["blockers"].split(";") if c]
        kinds = [k for k in p["blocker_kinds"].split(";") if k]
        assert len(codes) == len(kinds)
        assert sorted({code_field(c) for c in codes}) == sorted(fields), p
        for f in fields:
            field_total[f] += 1
            if any(
                code_field(c) == f and k == "unreported" for c, k in zip(codes, kinds, strict=True)
            ):
                field_unreported[f] += 1
    strata: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for p in kind_e:
        strata[p["stratum"]][p["verdict"]] += 1
    return {
        "n_pairs": len(kind_e),
        "fields": [
            {
                "field": f,
                "pairs": n,
                "unreported": field_unreported[f],
                "stated": n - field_unreported[f],
            }
            for f, n in field_total.most_common()
        ],
        "strata": {s: dict(c) for s, c in strata.items()},
        "verdicts": dict(Counter(p["verdict"] for p in kind_e)),
        "no_blocker_pairs": sum(1 for p in kind_e if not p["blocker_fields"]),
    }


def d3_section(ref: str) -> dict:
    rows = read_csv(ref, "out/tables/d3_spread.csv")
    units: defaultdict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r["target"] not in ("measured", TARGET_WINDOW):
            continue
        units[r["unit"]].append(
            {
                "target": r["target"],
                "alpha": fnum(r["alpha"]),
                "source": r["alpha_source"],
                "n": int(r["n"]),
                "log_min": math.log10(float(r["min"])),
                "log_max": math.log10(float(r["max"])),
                "range": float(r["log10_range"]),
            }
        )
    # the other target window gives the same spreads, shifted: say so rather than plot it twice
    other = {
        (r["unit"], r["alpha"]): float(r["log10_range"])
        for r in rows
        if r["target"] == OTHER_WINDOW
    }
    same = all(
        abs(other[(u, str(x["alpha"]))] - x["range"]) < 1e-9
        for u, xs in units.items()
        for x in xs
        if x["alpha"] is not None
    )
    return {"units": dict(units), "windows_same_spread": same}


def load_scored(text: str) -> list[scoring.Scored]:
    """The snapshot's scored.jsonl through the loader REVIEW.md aggregates with."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "scored.jsonl"
        path.write_text(text, encoding="utf-8")
        return review._load_scored(path)


def grid_section(ref: str) -> dict:
    """review.grid_run, on the snapshot's copy of each run directory."""
    out = {}
    for cell, run in review.RUN_IDS.items():
        base = f"data/interim/runs/{run}"
        scored = load_scored(show(ref, f"{base}/scored.jsonl"))
        kinds: defaultdict[str, list[int]] = defaultdict(lambda: [0, 0])
        for item in scored:
            kinds[item.kind.value][0] += bool(item.correct)
            kinds[item.kind.value][1] += 1
        recall = {}
        for line in scoring.verdict_table(scored).splitlines()[1:]:
            _, verdict, n, correct, value = line.split("\t")
            recall[verdict] = {
                "n": int(n),
                "correct": None if correct == "-" else int(correct),
                "recall": float(value),
            }
        answers = read_jsonl(ref, f"{base}/answers.jsonl")
        said: Counter[str] = Counter()
        for a in answers:
            if a.get("kind") != QueryKind.e.value:
                continue
            parsed = scoring.parse_answer(a["qid"], a["cell"], a.get("text") or "")
            said[
                "unreadable"
                if parsed.unparsed
                else str(parsed.payload.get("verdict", "none given"))
            ] += 1
        asked = [t for t in show(ref, f"{base}/asked.txt").splitlines() if t.strip()]
        manifest = json.loads(show(ref, f"{base}/manifest.json"))
        out[cell] = {
            "run": run,
            "model": manifest["model"],
            "kinds": {k: {"correct": c, "n": n} for k, (c, n) in sorted(kinds.items())},
            "recall": recall,
            "kind_e_said": dict(said),
            "asked": len(asked),
            "refused": sum(1 for a in answers if a.get("refused")),
        }
    return out


def explorer(d1: list[dict], harm: list[dict]) -> dict:
    assert [r["row_id"] for r in d1] == [h["row_id"] for h in harm]
    cols = [
        "pmcid", "row", "particle", "material", "qty", "value", "unit",
        "medium", "medium_ok", "ionic_mM", "ionic_ok", "pH", "pH_ok",
        "temp", "temp_ok", "instrument", "instr_ok", "complete", "size_nm",
        "case", "harmonised", "h_lo", "h_hi",
    ]  # fmt: skip
    rows = []
    for r, h in zip(d1, harm, strict=True):
        value = fnum(r["value"])
        ph = r["pH"] if not blank(r["pH"]) else (r["pH_text"] or "")
        temp = (
            r["temperature_C"]
            if not blank(r["temperature_C"])
            else (r["temperature_qualifier"] or "")
        )
        if h["result"] == "point":
            lo = hi = float(h["point"])
            shown = f"{lo:.2f}"
        elif h["result"] == "interval":
            lo, hi = float(h["low"]), float(h["high"])
            shown = f"[{lo:.2f}, {hi:.2f}]"
        else:
            shown, lo, hi = "", None, None
        zeta = r["quantity"] == "zeta_potential"
        rows.append(
            [
                r["pmcid"],
                r["row_id"].split("-")[-1],
                r["particle_name"],
                r["material"],
                "\N{GREEK SMALL LETTER ZETA}" if zeta else "\N{GREEK SMALL LETTER MU}",
                value if value is not None else (r["value_text"] or ""),
                "mV" if r["unit"] == "mV" else "\N{MICRO SIGN}m\N{MIDDLE DOT}cm/(V\N{MIDDLE DOT}s)",
                r["medium_text"] or "",
                int(truthy(r["medium_reported"])),
                fnum(r["ionic_strength_mM"]) if truthy(r["ionic_strength_reported"]) else "",
                int(truthy(r["ionic_strength_reported"])),
                ph,
                int(truthy(r["pH_reported"])),
                temp,
                int(truthy(r["temperature_reported"])),
                r["instrument"] or "",
                int(truthy(r["instrument_reported"])),
                int(truthy(r["conditions_complete"])),
                fnum(r["size_measured_nm"]) if not blank(r["size_measured_nm"]) else "",
                h["case"],
                shown,
                lo,
                hi,
            ]
        )
    return {"cols": cols, "rows": rows}


def gold_section(ref: str) -> dict:
    facts = release.gold_facts(
        pd.read_csv(io.StringIO(show(ref, "data/interim/annotation/gold_50.csv")))
    )
    return {"rows": facts["rows"], "papers": facts["papers"], "human": facts["human_rows"]}


def origin_section(ref: str) -> dict | None:
    """The hand-corrected origin counts, or None at a ref that predates `report origin`."""
    if not exists(ref, ORIGIN_STATS):
        return None
    stats = json.loads(show(ref, ORIGIN_STATS))
    h, hc = stats["hand_corrected"], stats["hand_check"]
    env = h["environmental_rows"]
    return {
        "rows": stats["rows"],
        "papers": stats["papers"],
        "synthetic_rows": h["synthetic"]["rows"],
        "synthetic_papers": h["synthetic"]["papers_any"],
        "classes": [
            {"key": k, "rows": h["origin"]["rows"][k], "papers": h["origin"]["papers_any"][k]}
            for k in ORIGINS
        ],
        "environments": [
            {"key": e, "rows": h["environment"]["rows"][e], "papers": h["environment"]["papers"][e]}
            for e in ENVIRONMENTS
        ],
        "env_rows": env["rows"],
        "env_papers": env["papers"],
        "env_conditions": [{"key": k, "n": env["reported"][k]["n"]} for k in ORIGIN_CONDITIONS],
        "env_complete": env["conditions_complete"]["n"],
        "env_conductivity": env["conductivity_printed"],
        "hand": {
            s: {"n": hc[s]["n"], "agree": hc[s]["agree"], "split": hc[s]["agree_synthetic_split"]}
            for s in ("environmental", "unclear", "random")
        },
    }


def scope_section(ref: str, table: pd.DataFrame) -> dict | None:
    """The block every generated document opens with, rendered from this ref's tables by the
    same function; None at a ref that predates `report origin`, so the page hides the box."""
    if not exists(ref, ORIGIN_STATS):
        return None
    facts = scope.gather(
        table,
        json.loads(show(ref, "out/tables/d1_stats.json")),
        json.loads(show(ref, ORIGIN_STATS)),
    )
    return {
        "title": scope.TITLE,
        "items": [list(item) for item in scope.items(facts)],
        # The documents gained the block after the origin table was committed; at such a ref the
        # page shows the box and says it is not cross-checked, rather than failing.
        "cross_checked": scope.extract(show(ref, "out/review/REVIEW.md")) is not None,
    }


# ---- cross-check against REVIEW.md ----------------------------------------------------------


def n(s: str) -> float:
    return float(re.sub(r"\s", "", s))


def review_checks(ref: str, data: dict) -> list[dict]:
    text = show(ref, "out/review/REVIEW.md")
    checks: list[dict] = []

    def check(name: str, ours, theirs) -> None:
        ok = ours == theirs if not isinstance(ours, float) else abs(ours - theirs) < 1e-9
        checks.append({"name": name, "ours": ours, "review": theirs, "ok": ok})

    def one(pattern: str, flags: int = 0) -> tuple[str, ...]:
        m = re.search(pattern, text, flags)
        if not m:
            raise SystemExit(f"REVIEW.md no longer matches: {pattern}")
        return m.groups()

    def many(pattern: str, expected: int, flags: int = 0) -> list:
        # A table REVIEW.md reshaped must fail here, not quietly drop its checks.
        found = re.findall(pattern, text, flags)
        if len(found) != expected:
            raise SystemExit(f"REVIEW.md: {len(found)} matches, expected {expected}: {pattern}")
        return found

    f = {s["label"]: s["n"] for s in data["funnel"]}
    hits_all, hits_oa = one(r"reports ([\d ]+) hits in all, ([\d ]+) open access")
    check("search hits", f["Europe PMC search hits"], int(n(hits_all)))
    check("open-access hits", f["open-access hits"], int(n(hits_oa)))
    check("XMLs vendored", f["full texts fetched"], int(n(one(r"XMLs\s+([\d ]+) vendored")[0])))
    rows, papers = one(r"rows\s+([\d ]+), from ([\d ]+) papers")
    check("rows", f["measurement rows"], int(n(rows)))
    check("papers", f["papers with a measurement"], int(n(papers)))
    check(
        "fully conditioned rows",
        f["fully conditioned rows"],
        int(n(one(r"All five at once, on one row: ([\d ]+) /")[0])),
    )

    c = data["census"]
    passing, _, checked, allp = one(
        r"([\d ]+) of ([\d ]+) rows pass it, so ([\d ]+) pairs are checked "
        r"instead of all ([\d ]+)\."
    )
    check("rows passing census filter", c["rows_passing"], int(n(passing)))
    check("pairs checked", c["pairs_checked"], int(n(checked)))
    check("all pairs", c["all_pairs"], int(n(allp)))
    _, zp = one(r"\| zeta \N{MULTIPLICATION SIGN} zeta pairs \(([\d ]+) zeta rows\) \| ([\d ]+) \|")
    check("zeta pairs", c["zeta_pairs"], int(n(zp)))
    check(
        "comparable",
        c["comparable"],
        int(n(one(r"\| \*\*comparable\*\* \| \*\*([\d ]+)\*\* \|")[0])),
    )
    check(
        "comparable zeta\N{MULTIPLICATION SIGN}zeta",
        c["comparable_zeta"],
        int(one(r"\| of which zeta \N{MULTIPLICATION SIGN} zeta \| (\d+) \|")[0]),
    )
    across = many(r"\| of which across papers \| (\d+) \|", 2)
    check("comparable across papers", c["comparable_cross"], int(across[0]))
    check("conditionally across papers", c["conditional_cross"], int(across[1]))
    check(
        "comparable zeta across papers",
        c["comparable_zeta_cross"],
        int(one(r"\| zeta \N{MULTIPLICATION SIGN} zeta across papers \| (\d+) \|")[0]),
    )
    check(
        "conditionally comparable",
        c["conditional"],
        int(one(r"\| conditionally comparable \| (\d+) \|")[0]),
    )

    fp = data["five"]
    reported = many(r"Rows reporting it: \*\*([\d ]+) / ([\d ]+)", len(FLAGS))
    means = many(
        r"Per paper \(mean of each paper's share of rows\): \*\*([\d.]+) %\*\*", len(FLAGS)
    )
    anyp = many(r"Papers with at least one row reporting it: (\d+) / (\d+)", len(FLAGS))
    for p, rep, mean, a in zip(fp["params"], reported, means, anyp, strict=True):
        check(f"{p['name']} rows reporting", p["strong"] + p["soft"], int(n(rep[0])))
        check(f"{p['name']} per-paper mean %", round(p["paper_mean_share"] * 100, 1), float(mean))
        check(f"{p['name']} papers with any row", p["papers_any"], int(a[0]))
    src = dict(many(r"^\| `(reported|inferred_from_named_salt)` \| ([\d ]+) \|", 2, re.M))
    ion = fp["params"][1]
    check("ionic strength printed", ion["strong"], int(n(src["reported"])))
    check("ionic strength from salt recipe", ion["soft"], int(n(src["inferred_from_named_salt"])))
    ph = fp["params"][2]
    one_num, via_text = one(r"([\d ]+) rows print one number; (\d+) count through `pH_text` alone")
    check("pH one number", ph["strong"], int(n(one_num)))
    check("pH text only", ph["soft"], int(via_text))
    t = fp["params"][3]
    num, qual = one(r"([\d ]+) rows give a number; ([\d ]+) count only through a qualifier")
    check("temperature number", t["strong"], int(n(num)))
    check("temperature nominal", t["soft"], int(n(qual)))
    check(
        "papers with a fully conditioned row",
        fp["complete_papers_any"],
        int(one(r"papers with at least one fully conditioned row \| (\d+) / [\d ]+")[0]),
    )
    check(
        "fully conditioned per-paper mean %",
        round(fp["complete_paper_mean"] * 100, 1),
        float(one(r"\| per paper, mean of shares \| ([\d.]+) %")[0]),
    )

    metrics = data["clustering"]["metrics"]
    icc_cells = one(r"^\| ICC = [^|]+\|(.+)\|$", re.M)[0].split("|")
    for m, v in zip(metrics, icc_cells, strict=True):
        check(f"ICC {m['key']}", round(m["icc"], 4), float(v))
    boot = many(
        r"^\| `(\w+)` \| ([\d.]+) % \| ([\d.]+) % to ([\d.]+) % \| \N{PLUS-MINUS SIGN}([\d.]+) \| "
        r"\N{PLUS-MINUS SIGN}([\d.]+) \| ([\d.]+) % \| ([\d.]+) % to ([\d.]+) % \|$",
        len(metrics),
        re.M,
    )
    by_key = {m["key"]: m for m in metrics}

    def pp(x: float) -> float:
        return round(x * 100, 1)

    for key, _pr, rlo, rhi, nh, _ch, _pp, plo, phi in boot:
        m = by_key[key]
        check(
            f"bootstrap {key} per-row interval",
            (pp(m["row_lo"]), pp(m["row_hi"])),
            (float(rlo), float(rhi)),
        )
        check(
            f"bootstrap {key} per-paper interval",
            (pp(m["paper_lo"]), pp(m["paper_hi"])),
            (float(plo), float(phi)),
        )
        check(f"naive {key} half-width pp", pp(m["naive_hw"]), float(nh))

    h = data["harmonise"]
    for res, cnt in many(r"^\| (point|interval|none) \| ([\d ]+) \|$", 3, re.M):
        check(f"harmonise {res}", h["results"][res], int(n(cnt)))
    case_rows = many(
        r"^\| (H|Z1|Z2|Z3|Z4|M0|M1|M2|U|N) \| [^|]+ \| ([\d ]+) \|$", len(h["case_order"]), re.M
    )
    for case, cnt in case_rows:
        check(f"case {case}", h["cases"][case], int(n(cnt)))
    check(
        "kappa-a known rows",
        h["kappa_known"],
        int(n(one(r"\N{GREEK SMALL LETTER KAPPA}a is known on ([\d ]+) /")[0])),
    )

    g = data["grid"]

    def cell(c: str, section: str, key: str) -> tuple[int, int]:
        return (g[c][section][key]["correct"], g[c][section][key]["n"])

    c9 = one(r"accuracy per kind, cell D vs cell B: (.+?)\. Kind E recall")[0]
    kinds = re.findall(r"([A-E]) (\d+)/(\d+) vs (\d+)/(\d+)", c9)
    if len(kinds) != len(g["D"]["kinds"]):
        raise SystemExit(f"REVIEW.md C9 lists {len(kinds)} kinds: {c9}")
    for kind, dc, dn, bc, bn in kinds:
        check(f"grid kind {kind} cell D", cell("D", "kinds", kind), (int(dc), int(dn)))
        check(f"grid kind {kind} cell B", cell("B", "kinds", kind), (int(bc), int(bn)))
    recalls = many(
        r"(comparable|conditionally_comparable|not_comparable): D (\d+)/(\d+), B (\d+)/(\d+)", 3
    )
    for verdict, dc, dn, bc, bn in recalls:
        check(f"recall {verdict} D", cell("D", "recall", verdict), (int(dc), int(dn)))
        check(f"recall {verdict} B", cell("B", "recall", verdict), (int(bc), int(bn)))
    bd, bb = one(r"balanced accuracy D (\d\.\d+) vs B (\d\.\d+)")
    check("balanced accuracy D", g["D"]["recall"]["balanced_accuracy"]["recall"], float(bd))
    check("balanced accuracy B", g["B"]["recall"]["balanced_accuracy"]["recall"], float(bb))
    said_not, said_cond = one(
        r"Cell B's kind E verdicts: `not_comparable` (\d+), `conditionally_comparable` (\d+)"
    )
    said = g["B"]["kind_e_said"]
    check("cell B said not_comparable", said.get("not_comparable", 0), int(said_not))
    check("cell B said conditionally", said.get("conditionally_comparable", 0), int(said_cond))

    gr, gp = one(r"The gold set it is scored against \((\d+) rows, (\d+) papers")
    check("gold set rows", data["gold"]["rows"], int(gr))
    check("gold set papers", data["gold"]["papers"], int(gp))
    check(
        "gold rows re-judged by a human",
        data["gold"]["human"],
        int(one(r"rows re-judged by a human: (\d+)")[0]),
    )

    strata = data["comparability"]["strata"]
    table = many(r"^\| `(\w+)` \| (\d+) \| (\d+) \| (\d+) \| (\d+) \| (\d+) \|$", len(strata), re.M)
    for s, _sampled, total, comp, cond, notc in table:
        got = strata[s]
        check(
            f"kind E stratum {s}",
            (
                sum(got.values()),
                got.get("comparable", 0),
                got.get("conditionally_comparable", 0),
                got.get("not_comparable", 0),
            ),
            (int(total), int(comp), int(cond), int(notc)),
        )

    sc = data.get("scope")
    if sc and sc["cross_checked"]:
        check("scope block, word for word", "\n".join(scope.markdown(sc["items"])),
              scope.extract(text))  # fmt: skip

    o = data.get("origin")
    if not (o and o["cross_checked"]):
        return checks
    by = {c["key"]: c for c in o["classes"]}
    where = {e["key"]: e for e in o["environments"]}
    syn, total = one(
        r"- \*\*Number\.\*\* ([\d ]+) / ([\d ]+) \([\d.]+ %\) rows measure a synthetic"
    )
    check("origin rows", o["rows"], int(n(total)))
    check("origin synthetic rows", o["synthetic_rows"], int(n(syn)))
    for key, words in (("commercial", "bought ready-made"), ("lab_fabricated", "made in a lab"),
                       ("unclear", "stay")):  # fmt: skip
        got = one(rf"([\d ]+) / [\d ]+ \([\d.]+ %\) {words} \(?`{key}`")[0]
        check(f"origin {key} rows", by[key]["rows"], int(n(got)))
    env_rows, env_papers, ww_rows, ww_papers = one(
        r"([\d ]+) / [\d ]+ \([\d.]+ %\) are real environmental particles, from (\d+) papers: "
        r"(\d+) of them wastewater effluent, from (\d+) papers"
    )
    check("origin environmental rows", by["environmental"]["rows"], int(n(env_rows)))
    check("origin environmental papers", o["env_papers"], int(env_papers))
    check("origin wastewater rows", where["wastewater"]["rows"], int(ww_rows))
    check("origin wastewater papers", where["wastewater"]["papers"], int(ww_papers))
    check(
        "origin air or dust rows",
        where["air_dust"]["rows"],
        int(one(r"Air or dust: (\d+) rows")[0]),
    )
    hand = o["hand"]
    agree, k = one(r"every environmental particle \((\d+) / (\d+) agree\)")
    check("origin hand check environmental", (hand["environmental"]["agree"],
          hand["environmental"]["n"]), (int(agree), int(k)))  # fmt: skip
    _, agree, k = one(r"(\d+) of the unclear ones \((\d+) / (\d+);")
    check("origin hand check unclear", (hand["unclear"]["agree"], hand["unclear"]["n"]),
          (int(agree), int(k)))  # fmt: skip
    agree, k, split, k2 = one(
        r"a seeded \d+ of the rest \((\d+) / (\d+), [\d.]+ %, on the four classes; "
        r"(\d+) / (\d+) on synthetic against environmental\)"
    )
    r = hand["random"]
    check("origin hand check random", (r["agree"], r["n"]), (int(agree), int(k)))
    check("origin hand check synthetic split", (r["split"], r["n"]), (int(split), int(k2)))
    part = text.split("### The environmental rows' conditions", 1)[-1].split("\n### ", 1)[0]
    table = dict(
        (label, (int(a), int(b)))
        for label, a, b in re.findall(
            r"^\| (medium|ionic strength|pH|temperature|instrument) \| \**(\d+) / (\d+)\** \|$",
            part,
            re.M,
        )
    )
    if len(table) != len(o["env_conditions"]):
        raise SystemExit(f"REVIEW.md: environmental conditions table has {len(table)} rows")
    for c in o["env_conditions"]:
        check(f"origin environmental {c['key']}", (c["n"], o["env_rows"]),
              table[c["key"].replace("_", " ")])  # fmt: skip
    printed, k = one(r"no conductivity reaches a row \((\d+) / (\d+) print one")
    check("origin environmental conductivity", (o["env_conductivity"], o["env_rows"]),
          (int(printed), int(k)))  # fmt: skip
    return checks


def build(ref: str) -> dict:
    commit = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "--short", ref],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    d1_text = show(ref, "out/tables/d1_zeta_table.csv")
    d1 = list(csv.DictReader(io.StringIO(d1_text)))
    table = pd.read_csv(io.StringIO(d1_text))
    harm = read_csv(ref, "out/review/harmonised_all_rows.csv")
    per_paper = read_csv(ref, "out/review/conditions_per_paper.csv")
    kind_e = read_csv(ref, "queries/kind_e_comparability.csv")

    data: dict = {"ref": ref, "commit": commit}
    data.update(funnel_and_census(ref, d1, table))
    data["five"] = five_parameters(d1, per_paper)
    data["clustering"] = clustering(table, per_paper)
    data["harmonise"] = harmonise_section(harm)
    data["comparability"] = comparability_section(kind_e)
    data["d3"] = d3_section(ref)
    data["grid"] = grid_section(ref)
    data["explorer"] = explorer(d1, harm)
    data["gold"] = gold_section(ref)
    origin = origin_section(ref)
    if origin is not None:
        # REVIEW.md gained C11 after the origin table was first committed; at such a ref the
        # page shows the section and says it is not cross-checked, rather than failing.
        origin["cross_checked"] = "#### C11." in show(ref, "out/review/REVIEW.md")
        data["origin"] = origin
    box = scope_section(ref, table)
    if box is not None:
        data["scope"] = box
    data["checks"] = review_checks(ref, data)
    return data


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ref", default="HEAD", help="git ref to read every input from")
    ap.add_argument("--out", default=str(HERE / "data.json"))
    args = ap.parse_args()

    data = build(args.ref)
    out = Path(args.out)
    out.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    bad = [c for c in data["checks"] if not c["ok"]]
    print(f"{args.ref} ({data['commit']}): wrote {out}, {out.stat().st_size:,} bytes")
    print(f"{len(data['checks'])} checks against REVIEW.md, {len(bad)} disagree")
    for c in bad:
        print(f"  DIFF {c['name']}: ours {c['ours']} / REVIEW {c['review']}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
