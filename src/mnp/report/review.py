"""`report review`: a guide for checking the dataset by hand, and the worksheets to do it with.

Writes `out/review/REVIEW.md` and five CSV files a spreadsheet can recompute. Every number in the
guide is computed here at build time from the repo's own code and data, or quoted from a named
file and section. Nothing is re-derived a second way: ICC comes from `mnp.demo.resample.anova`,
the harmonised values from `mnp.demo.harmonise.harmonise`, the pair verdicts from
`mnp.eval.comparability.comparable`, the grid scores from `mnp.eval.scoring`. The worksheets only
lay those results out beside their inputs so a reader can redo the arithmetic.

The audit sample keeps the release's licence discipline even though the repository is private:
for a row whose quote is withheld it gives line numbers, never text.
"""

from __future__ import annotations

import json
import math
import random
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from mnp import config, runs
from mnp.corpus import jats, lines
from mnp.corpus.lines import LinedDoc
from mnp.demo import harmonise, resample
from mnp.eval import comparability as comp
from mnp.eval import scoring
from mnp.eval.query_sets import QueryKind
from mnp.report import release as release_mod
from mnp.schema.models import Quantity

FLAGS: tuple[str, ...] = (
    "medium_reported",
    "ionic_strength_reported",
    "pH_reported",
    "temperature_reported",
    "instrument_reported",
)
METRICS: tuple[str, ...] = resample.METRICS

AUDIT_SEED = 20260928
AUDIT_PER_STRATUM = 2
AUDIT_CHECK_COLUMNS = (
    "value_ok",
    "medium_ok",
    "ionic_strength_ok",
    "pH_ok",
    "temperature_ok",
    "instrument_ok",
    "note",
)

RUN_IDS = {"D": "celld-sweep-20260927", "B": "cellb-sweep-20260928"}

EUROPEPMC_URL = "https://europepmc.org/article/PMC/{pmcid}"

COLUMNS: dict[str, tuple[str, ...]] = {
    "conditions_per_paper.csv": (
        "pmcid",
        "n_rows",
        *(f"{m}_{part}" for m in METRICS for part in ("rows", "share")),
    ),
    "icc_worksheet.csv": ("pmcid", "n_i", *(f"{m}_succ" for m in METRICS)),
    "harmonised_all_rows.csv": (
        "row_id",
        "pmcid",
        "quantity",
        "value",
        "unit",
        *FLAGS,
        "conditions_complete",
        "ionic_strength_mM",
        "size_measured_nm",
        "temperature_C",
        "models_named",
        "debye_length_nm",
        "kappa_a",
        "henry_f",
        "case",
        "result",
        "point",
        "low",
        "high",
        "why",
    ),
    "comparability_worked_pairs.csv": (
        "pair_id",
        "why_chosen",
        "verdict",
        "row_id_a",
        "row_id_b",
        "check",
        "field",
        "value_a",
        "value_b",
        "compared_as_a",
        "compared_as_b",
        "difference",
        "tolerance",
        "outcome",
        "blocker_code",
        "blocker_kind",
    ),
    "audit_sample.csv": (
        "sample_no",
        "stratum",
        "row_id",
        "pmcid",
        "doi",
        "europepmc_url",
        "xml_path",
        "source_licence",
        "quote_withheld",
        "quantity",
        "value",
        "value_text",
        "unit",
        "medium_text",
        "medium_class",
        "ionic_strength_mM",
        "ionic_strength_source",
        "pH",
        "pH_text",
        "temperature_C",
        "temperature_qualifier",
        "instrument",
        *FLAGS,
        "conditions_complete",
        "evidence_line_ids",
        "evidence_lines",
        "evidence_quote",
        "evidence_line_text",
        *AUDIT_CHECK_COLUMNS,
    ),
}

#: The harmonisation cases, as labelled in `harmonised_all_rows.csv`. The label is read off what
#: `harmonise.harmonise` returned; it never decides anything itself.
CASES: dict[str, str] = {
    "H": "zeta; Henry's function or Ohshima's approximation named: taken as reported",
    "Z1": "zeta; one textbook limit named, κa known: corrected to a point",
    "Z2": "zeta; one textbook limit named, κa unknown: an interval",
    "Z3": "zeta; conversion model unknown, κa known: an interval",
    "Z4": "zeta; conversion model unknown, κa unknown: an interval",
    "M1": "mobility; temperature and κa known: converted to a point",
    "M2": "mobility; temperature known, κa unknown: an interval",
    "M0": "mobility; temperature unreported: nothing",
    "U": "mobility in a unit the conversion does not know: nothing",
    "N": "no printed value: nothing",
}


def _blank(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


# --- conditions and ICC ------------------------------------------------------------------------


def conditions_per_paper(table: pd.DataFrame) -> pd.DataFrame:
    """Per paper: its rows, and for each metric the rows that report it and their share."""
    grouped = table.groupby("pmcid")
    out = pd.DataFrame({"n_rows": grouped.size()})
    for metric in METRICS:
        out[f"{metric}_rows"] = grouped[metric].sum().astype(int)
        out[f"{metric}_share"] = out[f"{metric}_rows"] / out["n_rows"]
    out = out.sort_index().reset_index()
    return out[list(COLUMNS["conditions_per_paper.csv"])]


def icc_worksheet(table: pd.DataFrame) -> pd.DataFrame:
    """Per paper the n_i and successes, in the pmcid order `resample` clusters in."""
    grouped = table.groupby("pmcid")
    out = pd.DataFrame({"n_i": grouped.size()})
    for metric in METRICS:
        out[f"{metric}_succ"] = grouped[metric].sum().astype(int)
    out = out.sort_index().reset_index()
    return out[list(COLUMNS["icc_worksheet.csv"])]


@dataclass(frozen=True)
class IccSummary:
    metric: str
    successes: int
    anova: resample.Anova

    @property
    def n_eff(self) -> float:
        return self.anova.n / self.anova.deff


def icc_summary(table: pd.DataFrame) -> list[IccSummary]:
    return [
        IccSummary(metric, int(table[metric].sum()), resample.anova_for(table, metric))
        for metric in METRICS
    ]


# --- harmonisation -----------------------------------------------------------------------------


def case_of(result: harmonise.Harmonised) -> str:
    """The case label of one harmonised row, read off what `harmonise` returned."""
    if result.reported_value is None:
        return "N"
    if result.quantity is Quantity.zeta_potential:
        if result.model == "henry":
            return "H"
        if result.model in ("smoluchowski", "huckel"):
            return "Z1" if result.point is not None else "Z2"
        return "Z3" if result.kappa_a is not None else "Z4"
    if result.point is not None:
        return "M1"
    if result.low is not None:
        return "M2"
    if result.why == "needs the measurement temperature":
        return "M0"
    return "U"


def result_of(result: harmonise.Harmonised) -> str:
    if result.point is not None:
        return "point"
    if result.low is not None and result.high is not None:
        return "interval"
    return "none"


def harmonised_rows(table: pd.DataFrame) -> pd.DataFrame:
    """Every row: its five flags, the inputs the correction needs, and what `harmonise` gave."""
    out = []
    for record in table.to_dict(orient="records"):
        models = harmonise.models_named(str(record["pmcid"]))
        result = harmonise.harmonise(record, models)
        row = comp.ZetaRow.from_mapping(record)
        reported = row.conditions.ionic_strength_reported
        ionic = row.conditions.ionic_strength_mM if reported else None
        debye = comp.debye_length_nm(ionic) if ionic is not None else None
        kappa_a = result.kappa_a
        out.append(
            {
                "row_id": record["row_id"],
                "pmcid": record["pmcid"],
                "quantity": record["quantity"],
                "value": _blank(record["value"]),
                "unit": record["unit"],
                **{flag: bool(record[flag]) for flag in FLAGS},
                "conditions_complete": bool(record["conditions_complete"]),
                "ionic_strength_mM": ionic,
                "size_measured_nm": row.size_measured_nm,
                "temperature_C": row.conditions.temperature_C,
                "models_named": ";".join(sorted(models)),
                "debye_length_nm": None if debye is None or math.isinf(debye) else debye,
                "kappa_a": kappa_a,
                "henry_f": comp.henry_f(kappa_a) if kappa_a is not None else None,
                "case": case_of(result),
                "result": result_of(result),
                "point": result.point,
                "low": result.low,
                "high": result.high,
                "why": result.why,
            }
        )
    return pd.DataFrame(out, columns=list(COLUMNS["harmonised_all_rows.csv"]))


# --- comparability -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Pair:
    pair_id: str
    why_chosen: str
    a: dict[str, Any]
    b: dict[str, Any]

    @property
    def rows(self) -> tuple[comp.ZetaRow, comp.ZetaRow]:
        return comp.ZetaRow.from_mapping(self.a), comp.ZetaRow.from_mapping(self.b)

    @property
    def verdict(self) -> comp.Verdict:
        return comp.comparable(*self.rows)


def census(table: pd.DataFrame) -> list[comp.PairSpec]:
    return comp.graded_census([comp.ZetaRow.from_mapping(r) for r in table.to_dict("records")])


def pick_pairs(
    table: pd.DataFrame, graded: list[comp.PairSpec], key: list[dict[str, str]]
) -> list[Pair]:
    """Four real pairs, chosen by a fixed rule so a rebuild picks the same ones.

    Comparable and conditionally comparable come from the exhaustive census; the two not
    comparable ones from the kind E answer key: one blocked by a single rule that is not an
    axis, and one ordinary pair from a uniform stratum.
    """
    records = {r["row_id"]: r for r in table.to_dict(orient="records")}
    zeta = Quantity.zeta_potential

    def first(specs, predicate):
        return next((s for s in specs if predicate(s)), None)

    comparable = first(
        graded,
        lambda s: (
            s.verdict.verdict is comp.Comparability.comparable
            and s.a.quantity is zeta
            and s.b.quantity is zeta
        ),
    ) or first(graded, lambda s: s.verdict.verdict is comp.Comparability.comparable)
    conditional = first(
        graded,
        lambda s: (
            s.verdict.verdict is comp.Comparability.conditionally_comparable
            and s.a.pmcid != s.b.pmcid
        ),
    ) or first(graded, lambda s: s.verdict.verdict is comp.Comparability.conditionally_comparable)
    single = next(
        (
            r
            for r in key
            if r["verdict"] == "not_comparable" and r["blockers"] == "conversion_regime_mismatch"
        ),
        None,
    ) or next(
        r
        for r in key
        if r["verdict"] == "not_comparable" and r["stratum"] == "both_conditions_complete"
    )
    ordinary = next(
        r
        for r in key
        if r["stratum"] == "cross_paper_same_material" and r["verdict"] == "not_comparable"
    )
    pairs = []
    if comparable is not None:
        pairs.append(
            Pair(
                "P1",
                "the first comparable zeta–zeta pair of the census",
                records[comparable.a.row_id],
                records[comparable.b.row_id],
            )
        )
    if conditional is not None:
        pairs.append(
            Pair(
                "P2",
                "the first conditionally comparable pair of the census that crosses papers",
                records[conditional.a.row_id],
                records[conditional.b.row_id],
            )
        )
    pairs.append(
        Pair(
            "P3",
            "the first not-comparable pair of the kind E key blocked by one rule alone, "
            "which is not an axis rule",
            records[single["row_id_a"]],
            records[single["row_id_b"]],
        )
    )
    pairs.append(
        Pair(
            "P4",
            "the first pair of the kind E key's cross_paper_same_material stratum",
            records[ordinary["row_id_a"]],
            records[ordinary["row_id_b"]],
        )
    )
    return pairs


def _show(value: Any) -> str:
    value = _blank(value)
    if value is None:
        return "unreported"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _num(value: float | None) -> str:
    return "" if value is None else f"{value:.6g}"


def _rel(a: float, b: float) -> float:
    scale = max(abs(a), abs(b))
    return 0.0 if scale == 0 else abs(a - b) / scale


def pair_checks(pair: Pair) -> list[dict[str, Any]]:
    """Every check `comparable` runs on this pair, field by field, beside the values it read.

    The outcome of a check is whether `comparable` produced a blocker on that field; nothing
    here re-decides it. The difference and compared-as columns are shown so a reader can see
    why, not to vote.
    """
    a, b = pair.rows
    verdict = pair.verdict
    by_field = {blocker.field: blocker for blocker in verdict.blockers}
    ca, cb = a.conditions, b.conditions
    zeta_pair = a.quantity is Quantity.zeta_potential and b.quantity is Quantity.zeta_potential
    ka, kb = a.kappa_a, b.kappa_a
    fa = comp.henry_f(ka) if ka is not None else None
    fb = comp.henry_f(kb) if kb is not None else None

    def numeric_diff(x, y, relative=False):
        if x is None or y is None:
            return ""
        return _num(_rel(x, y) if relative else abs(x - y))

    rows = [
        (
            "_measurand_blockers",
            "quantity",
            a.quantity.value,
            b.quantity.value,
            a.quantity.value,
            b.quantity.value,
            "",
            "must be identical",
        ),
        (
            "_identity_blockers",
            "material",
            _show(a.material),
            _show(b.material),
            _show(comp.material_key(a.material)),
            _show(comp.material_key(b.material)),
            "",
            "both stated; material_key identical",
        ),
        (
            "_identity_blockers",
            "functionalisation",
            _show(a.functionalisation),
            _show(b.functionalisation),
            _show(comp.functionalisation_key(a.functionalisation)),
            _show(comp.functionalisation_key(b.functionalisation)),
            "",
            "both stated; functionalisation_key identical",
        ),
        (
            "_condition_blockers",
            "medium",
            f"{ca.medium_class.value} / {_show(ca.medium_text)}",
            f"{cb.medium_class.value} / {_show(cb.medium_text)}",
            f"{ca.medium_class.value} / {_show(comp._norm(ca.medium_text))}",
            f"{cb.medium_class.value} / {_show(comp._norm(cb.medium_text))}",
            "",
            "both reported; class identical, then normalised text identical",
        ),
        (
            "_condition_blockers",
            "ionic_strength",
            _show(ca.ionic_strength_mM) if ca.ionic_strength_reported else "unreported",
            _show(cb.ionic_strength_mM) if cb.ionic_strength_reported else "unreported",
            ca.ionic_strength_source.value,
            cb.ionic_strength_source.value,
            numeric_diff(
                ca.ionic_strength_mM if ca.ionic_strength_reported else None,
                cb.ionic_strength_mM if cb.ionic_strength_reported else None,
                relative=True,
            ),
            f"both reported; |a-b| / max(|a|,|b|) <= {comp.IONIC_STRENGTH_REL_TOL:g}",
        ),
        (
            "_condition_blockers",
            "pH",
            _show(ca.pH if ca.pH is not None else ca.pH_text),
            _show(cb.pH if cb.pH is not None else cb.pH_text),
            "number" if ca.pH is not None else ("text" if ca.pH_reported else "unreported"),
            "number" if cb.pH is not None else ("text" if cb.pH_reported else "unreported"),
            numeric_diff(ca.pH, cb.pH),
            f"both reported as numbers; |a-b| <= {comp.PH_TOL:g}",
        ),
        (
            "_condition_blockers",
            "temperature",
            _show(ca.temperature_C if ca.temperature_C is not None else ca.temperature_qualifier),
            _show(cb.temperature_C if cb.temperature_C is not None else cb.temperature_qualifier),
            "number" if ca.temperature_C is not None else "qualifier or unreported",
            "number" if cb.temperature_C is not None else "qualifier or unreported",
            numeric_diff(ca.temperature_C, cb.temperature_C),
            f"both reported as numbers; |a-b| <= {comp.TEMPERATURE_TOL_C:g} °C",
        ),
        (
            "_condition_blockers",
            "instrument",
            _show(ca.instrument),
            _show(cb.instrument),
            _show(comp.instrument_key(ca.instrument)),
            _show(comp.instrument_key(cb.instrument)),
            "",
            "both named; instrument_key identical",
        ),
        (
            "_conversion_blockers",
            "size_measured_nm",
            _show(a.size_measured_nm),
            _show(b.size_measured_nm),
            "",
            "",
            "",
            "zeta pairs only: both sizes reported",
        ),
        (
            "_conversion_blockers",
            "conversion_model",
            _num(ka) or "κa unknown",
            _num(kb) or "κa unknown",
            f"f={fa:.4f}" if fa is not None else "",
            f"f={fb:.4f}" if fb is not None else "",
            numeric_diff(fa, fb, relative=True),
            f"zeta pairs only: |f_a-f_b| / max(f_a,f_b) <= {comp.HENRY_REL_TOL:g}",
        ),
    ]
    out = []
    for check, name, va, vb, as_a, as_b, diff, tol in rows:
        blocker = by_field.get(name)
        if blocker is not None:
            outcome = "blocks"
        elif name in ("size_measured_nm", "conversion_model") and not zeta_pair:
            outcome = "not applicable: not a zeta-zeta pair"
        elif name == "conversion_model" and (
            a.size_measured_nm is None or b.size_measured_nm is None
        ):
            outcome = "not evaluated: a size is unreported"
        elif name == "conversion_model" and (ka is None or kb is None):
            outcome = "not evaluated: κa unknown, the ionic strength check already blocks"
        else:
            outcome = "passes"
        out.append(
            {
                "pair_id": pair.pair_id,
                "why_chosen": pair.why_chosen,
                "verdict": verdict.verdict.value,
                "row_id_a": a.row_id,
                "row_id_b": b.row_id,
                "check": check,
                "field": name,
                "value_a": va,
                "value_b": vb,
                "compared_as_a": as_a,
                "compared_as_b": as_b,
                "difference": diff,
                "tolerance": tol,
                "outcome": outcome,
                "blocker_code": blocker.code if blocker else "",
                "blocker_kind": blocker.kind.value if blocker else "",
            }
        )
    return out


def worked_pairs(pairs: list[Pair]) -> pd.DataFrame:
    rows = [check for pair in pairs for check in pair_checks(pair)]
    return pd.DataFrame(rows, columns=list(COLUMNS["comparability_worked_pairs.csv"]))


# --- the audit sample --------------------------------------------------------------------------


def _document(pmcid: str) -> LinedDoc | None:
    path = config.EPMC_XML_DIR / f"{pmcid}.xml"
    if not path.is_file():
        return None
    return lines.build_lines(jats.parse(path.read_bytes()))


def audit_sample(
    release: pd.DataFrame,
    seed: int = AUDIT_SEED,
    documents: Callable[[str], LinedDoc | None] = _document,
) -> pd.DataFrame:
    """Twenty rows: two drawn per (condition, reported or not) stratum, ten strata, no repeats.

    Drawn from the released table in its own row order with `random.Random(seed)`, so the same
    seed gives the same rows. A row's quote text and line text are given only when its source
    licence lets the quote ship; a withheld row gets its line numbers and nothing else.
    """
    rng = random.Random(seed)
    chosen: list[tuple[str, int]] = []
    taken: set[int] = set()
    for flag in FLAGS:
        for state in (True, False):
            pool = [
                i
                for i, v in enumerate(release[flag].astype(bool))
                if bool(v) is state and i not in taken
            ]
            for i in rng.sample(pool, AUDIT_PER_STRATUM):
                taken.add(i)
                chosen.append((f"{flag}={state}", i))
    docs: dict[str, LinedDoc | None] = {}
    out = []
    for number, (stratum, i) in enumerate(chosen, 1):
        row = release.iloc[i]
        pmcid = str(row["pmcid"])
        if pmcid not in docs:
            docs[pmcid] = documents(pmcid)
        doc = docs[pmcid]
        ids = [x for x in str(_blank(row["evidence_line_ids"]) or "").split(";") if x]
        found = [lines.resolve_id(doc, x) if doc is not None else None for x in ids]
        withheld = bool(row["quote_withheld"])
        out.append(
            {
                "sample_no": number,
                "stratum": stratum,
                "row_id": row["row_id"],
                "pmcid": pmcid,
                "doi": row["doi"],
                "europepmc_url": EUROPEPMC_URL.format(pmcid=pmcid),
                "xml_path": f"data/raw/epmc/xml/{pmcid}.xml",
                "source_licence": row["source_licence"],
                "quote_withheld": withheld,
                **{
                    col: _blank(row[col])
                    for col in (
                        "quantity",
                        "value",
                        "value_text",
                        "unit",
                        "medium_text",
                        "medium_class",
                        "ionic_strength_mM",
                        "ionic_strength_source",
                        "pH",
                        "pH_text",
                        "temperature_C",
                        "temperature_qualifier",
                        "instrument",
                    )
                },
                **{flag: bool(row[flag]) for flag in FLAGS},
                "conditions_complete": bool(row["conditions_complete"]),
                "evidence_line_ids": ";".join(ids),
                "evidence_lines": ";".join(
                    f"{pmcid}:L{line.n}" if line is not None else f"{pmcid}:L?" for line in found
                ),
                "evidence_quote": None if withheld else _blank(row["evidence_quote"]),
                "evidence_line_text": None
                if withheld
                else " || ".join(line.text for line in found if line is not None),
                **dict.fromkeys(AUDIT_CHECK_COLUMNS, None),
            }
        )
    return pd.DataFrame(out, columns=list(COLUMNS["audit_sample.csv"]))


# --- the reader grid ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GridRun:
    cell: str
    run_id: str
    asked: int
    answered: int
    refused: int
    summaries: dict[str, scoring.Summary]
    verdicts: list[tuple[str, int, str, str]]
    said: Counter[str]
    code_dirty: bool | None


def _load_scored(path: Path) -> list[scoring.Scored]:
    out = []
    for text in path.read_text(encoding="utf-8").splitlines():
        if not text.strip():
            continue
        d = json.loads(text)
        out.append(
            scoring.Scored(
                qid=d["qid"],
                kind=QueryKind(d["kind"]),
                cell=d["cell"],
                correct=bool(d["correct"]),
                fabricated=d.get("fabricated"),
                citation_precision=d.get("citation_precision"),
                citation_recall=d.get("citation_recall"),
                tokens_delivered=int(d.get("tokens_delivered") or 0),
                retrieval_calls=int(d.get("retrieval_calls") or 0),
                extra=tuple((str(k), float(v)) for k, v in d.get("extra") or ()),
                detail=d.get("detail") or "",
            )
        )
    return out


def grid_run(cell: str) -> GridRun | None:
    run_id = RUN_IDS[cell]
    directory = runs.run_dir(run_id)
    if not (directory / "scored.jsonl").is_file():
        return None
    scored = _load_scored(directory / "scored.jsonl")
    summaries = {kind.value: s for (_, kind), s in scoring.aggregate(scored).items()}
    verdicts = []
    for text in scoring.verdict_table(scored).splitlines()[1:]:
        _, verdict, n, correct, recall = text.split("\t")
        verdicts.append((verdict, int(n), correct, recall))
    said: Counter[str] = Counter()
    answers = [
        json.loads(t) for t in (directory / "answers.jsonl").read_text().splitlines() if t.strip()
    ]
    for record in answers:
        if record.get("kind") != QueryKind.e.value:
            continue
        parsed = scoring.parse_answer(record["qid"], record["cell"], record.get("text") or "")
        said[
            "unreadable" if parsed.unparsed else str(parsed.payload.get("verdict", "none given"))
        ] += 1
    asked = [t for t in (directory / "asked.txt").read_text().splitlines() if t.strip()]
    manifest = json.loads((directory / "manifest.json").read_text())
    return GridRun(
        cell=cell,
        run_id=run_id,
        asked=len(asked),
        answered=len(answers),
        refused=sum(1 for r in answers if r.get("refused")),
        summaries=summaries,
        verdicts=verdicts,
        said=said,
        code_dirty=manifest.get("code_dirty"),
    )


# --- everything the guide states ---------------------------------------------------------------


@dataclass
class Facts:
    table: pd.DataFrame
    release: pd.DataFrame
    stats: dict
    papers: pd.DataFrame
    icc: list[IccSummary]
    estimates: list[resample.MetricEstimate]
    harmonised: pd.DataFrame
    scan: harmonise.ScanResult
    graded: list[comp.PairSpec]
    key: list[dict[str, str]]
    pairs: list[Pair]
    pair_sheet: pd.DataFrame
    audit: pd.DataFrame
    grid: dict[str, GridRun | None]
    chain: dict[str, Any]
    extra: dict[str, Any] = field(default_factory=dict)


def corpus_chain(table: pd.DataFrame, stats: dict) -> dict[str, Any]:
    """The counts at each step from the query to the rows, each read from the file that holds it."""
    search = config.EPMC_SEARCH_DIR
    hits = json.loads((search / "hit_counts.json").read_text())
    records = pd.read_parquet(search / "records.parquet")
    fetch_log = pd.read_csv(config.EPMC_XML_DIR / "fetch_log.csv")
    manifest = config.EPMC_XML_DIR.parent / "manifest.sha256"
    n_xml = sum(1 for t in manifest.read_text().splitlines() if t.strip())
    extractions = [
        json.loads(t)
        for t in (config.DATA_INTERIM / "extractions.jsonl").read_text().splitlines()
        if t.strip()
    ]
    with_rows = [r for r in extractions if r.get("measurements")]
    xml_names = {
        t.split()[-1].removesuffix(".xml") for t in manifest.read_text().splitlines() if t.strip()
    }
    recorded = {r["pmcid"] for r in extractions}
    no_text = set((stats.get("text_availability") or {}).get("pmcids_without_text") or ())
    return {
        "query": (config.QUERIES / "q1.txt").read_text().strip(),
        "hits_all": int(hits["hits_all"]),
        "hits_oa": int(hits["hits_oa"]),
        "records": len(records),
        "records_oa": int(records["is_oa"].astype(bool).sum()),
        "fetch_failures": [(str(r.pmcid), str(r.status)) for r in fetch_log.itertuples()],
        "xml": n_xml,
        "xml_without_record": len(xml_names - recorded),
        "xml_without_record_or_text": len((xml_names - recorded) & no_text),
        "extraction_records": len(extractions),
        "records_with_rows": len(with_rows),
        "records_without_rows": len(extractions) - len(with_rows),
        "record_rows": sum(len(r["measurements"]) for r in extractions),
        "dropped": sum(len(r.get("dropped") or []) for r in extractions),
        "records_with_brief": sum(1 for r in extractions if r.get("brief_sha256")),
        "rows_records_with_brief": sum(1 for r in with_rows if r.get("brief_sha256")),
        "models_by_row": table["model"].value_counts().sort_index().to_dict(),
        "prompts": int(table["prompt_sha256"].nunique()),
    }


def gather(root: Path) -> Facts:
    table = pd.read_csv(root / "tables" / "d1_zeta_table.csv")
    stats = json.loads((root / "tables" / "d1_stats.json").read_text())
    release = pd.read_parquet(root / "release" / "dataset.parquet")
    graded = census(table)
    key = comp.read_query_set()
    pairs = pick_pairs(table, graded, key)
    method = root / "demo" / "METHOD.md"
    gold = config.ANNOTATION / "gold_50.csv"
    extra = {
        "method_says_no_licence": method.is_file()
        and "This dataset has no licence yet" in method.read_text(encoding="utf-8"),
        "lock_ignored": "uv.lock"
        in {t.strip() for t in (config.ROOT / ".gitignore").read_text().splitlines()},
        "author": release_mod.AUTHOR,
        "gold": release_mod.gold_facts(pd.read_csv(gold)) if gold.is_file() else None,
    }
    return Facts(
        table=table,
        release=release,
        stats=stats,
        papers=conditions_per_paper(table),
        icc=icc_summary(table),
        estimates=resample.estimates(table),
        harmonised=harmonised_rows(table),
        scan=harmonise.scan(table),
        graded=graded,
        key=key,
        pairs=pairs,
        pair_sheet=worked_pairs(pairs),
        audit=audit_sample(release),
        grid={cell: grid_run(cell) for cell in RUN_IDS},
        chain=corpus_chain(table, stats),
        extra=extra,
    )


def _write_csv(frame: pd.DataFrame, path: Path) -> Path:
    frame.to_csv(path, index=False, float_format="%.10g", lineterminator="\n")
    return path


def build(root: Path) -> list[Path]:
    """Write `REVIEW.md` and the five worksheets under `root/review/`."""
    from mnp.report import review_guide

    facts = gather(Path(root))
    out_dir = Path(root) / "review"
    out_dir.mkdir(parents=True, exist_ok=True)
    sheets = {
        "conditions_per_paper.csv": facts.papers,
        "icc_worksheet.csv": icc_worksheet(facts.table),
        "harmonised_all_rows.csv": facts.harmonised,
        "comparability_worked_pairs.csv": facts.pair_sheet,
        "audit_sample.csv": facts.audit,
    }
    written = [_write_csv(frame, out_dir / name) for name, frame in sheets.items()]
    guide = out_dir / "REVIEW.md"
    guide.write_text(review_guide.render(facts), encoding="utf-8")
    written.append(guide)
    return sorted(written)
