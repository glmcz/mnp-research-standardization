"""Measure every stage of the pipeline separately, each against its own ground truth.

Only two stages were ever scored: the model's reading, against the gold set, and the
aggregate, against the published tables. Everything between them — the parser, the value
scanner, the coercion of strings into numbers, the verifier — could only show up as a worse
end-to-end score, with nothing to say which stage caused it.

One rule outranks every threshold here: **a stage with no ground truth is not measured.**
Not 0.00, not 1.00. Both are claims about a thing nobody checked.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from mnp import config

FIXTURES = config.ROOT / "tests" / "eval" / "fixtures"


@dataclass
class Stage:
    name: str
    what: str
    ground_truth: str
    metric: str
    threshold: float | None


STAGES: tuple[Stage, ...] = (
    Stage(
        name="parse",
        what="JATS to methods text, tables and keyword windows",
        ground_truth="tests/eval/fixtures/parse_spans.json — sentences located in a fixture "
        "article when it was written; who located them is not recorded",
        metric="span recall",
        threshold=1.0,
    ),
    Stage(
        name="scan",
        what="find every printed zeta/mobility value in an article",
        ground_truth="values in gold_50.csv, which Claude read from the papers; not yet "
        "audited by a person",
        metric="recall of gold values",
        threshold=None,
    ),
    Stage(
        name="read",
        what="a model or agent turns the article into rows",
        ground_truth="gold_50.csv",
        metric="row value precision",
        threshold=None,
    ),
    Stage(
        name="coerce",
        what="strings to numbers, under the ratified rules",
        ground_truth="tests/eval/fixtures/coerce_cases.json",
        metric="exact-match accuracy",
        threshold=1.0,
    ),
    Stage(
        name="verify",
        what="reject what the article does not support",
        ground_truth="tests/eval/fixtures/verify_adversarial.json — production defects",
        metric="detection rate",
        threshold=1.0,
    ),
    Stage(
        name="aggregate",
        what="verified rows into the published tables",
        ground_truth="the committed out/ tree",
        metric="artefacts reproduced",
        threshold=1.0,
    ),
)

BY_NAME = {s.name: s for s in STAGES}


@dataclass
class Result:
    stage: str
    metric: str
    value: float | None
    n: int
    threshold: float | None
    detail: str = ""

    @property
    def status(self) -> str:
        if self.value is None or self.n == 0:
            return "not measured"
        if self.threshold is None:
            return "reported"
        return "pass" if self.value >= self.threshold else "fail"

    def line(self) -> str:
        shown = "—" if self.value is None or self.n == 0 else f"{self.value:.2f}"
        gate = "—" if self.threshold is None else f"{self.threshold:.2f}"
        return f"| {self.stage} | {self.metric} | {shown} | {self.n} | {gate} | {self.status} |"


def _load(name: str) -> list[dict]:
    path = FIXTURES / name
    return json.loads(path.read_text()) if path.is_file() else []


def coerce_cases() -> list[dict]:
    return _load("coerce_cases.json")


def measure_parse() -> Result:
    """Every sentence located in a fixture article must survive parsing."""
    from mnp.corpus import jats

    cases = _load("parse_spans.json")
    hits = 0
    misses: list[str] = []
    for case in cases:
        xml = config.ROOT / "tests" / "fixtures" / case["xml"]
        if not xml.is_file():
            continue
        article = jats.parse(xml.read_bytes())
        # Only what the extractor is actually given. Searching full_text as well would pass a
        # parser that had quietly dropped the tables from the extraction text.
        normalised = " ".join(jats.extraction_text(article).split())
        needle = " ".join(case["sentence"].split())
        if needle in normalised:
            hits += 1
        else:
            misses.append(f"{case['xml']}: {needle[:60]}…")
    n = len([c for c in cases if (config.ROOT / "tests" / "fixtures" / c["xml"]).is_file()])
    value = hits / n if n else None
    return Result("parse", "span recall", value, n, 1.0, "; ".join(misses))


def measure_scan() -> Result:
    """Of the values Claude read out of the gold papers, how many does the scanner find?

    Precision is not reported and never will be: the scanner finds printed values of any
    material, so a paper reporting a metal oxide alongside its plastic scores badly while
    behaving exactly as designed.
    """
    import pandas as pd

    gold_path = config.ANNOTATION / "gold_50.csv"
    articles_path = config.DATA_INTERIM / "articles.parquet"
    if not gold_path.is_file() or not articles_path.is_file():
        return Result("scan", "recall of gold values", None, 0, None, "no corpus parsed here")

    from mnp.extract import zeta

    gold = pd.read_csv(gold_path)
    articles = pd.read_parquet(articles_path).set_index("pmcid")
    found = total = 0
    missed: list[str] = []
    for pmcid, rows in gold.groupby("pmcid"):
        if pmcid not in articles.index:
            continue
        text = articles.loc[pmcid, "extraction_text"] or ""
        candidates = {round(float(c.value), 2) for c in zeta.find_candidates(text)}
        for value in pd.to_numeric(rows["value"], errors="coerce").dropna():
            total += 1
            if any(abs(round(float(value), 2) - c) <= 0.05 for c in candidates):
                found += 1
            elif len(missed) < 8:
                missed.append(f"{pmcid}:{value:g}")
    value = found / total if total else None
    return Result(
        "scan", "recall of gold values", value, total, None, "missed " + ", ".join(missed)
    )


def measure_read() -> Result:
    """The one stage that is judgement: scored against the gold set Claude annotated."""
    import pandas as pd

    gold_path = config.ANNOTATION / "gold_50.csv"
    pred_path = config.DATA_PROCESSED / "zeta_table.parquet"
    if not gold_path.is_file() or not pred_path.is_file():
        return Result("read", "row value precision", None, 0, None, "nothing extracted here")
    from mnp.extract import evaluate

    pred = pd.read_parquet(pred_path)
    pred = pred[pred["evidence_verified"].astype(bool)]
    report = evaluate.evaluate(pred, pd.read_csv(gold_path))
    for score in report.get("row", []):
        if score["field"] == "value":
            return Result(
                "read",
                "row value precision",
                score["precision"],
                score["n"],
                None,
                f"recall {score['recall']:.2f}",
            )
    return Result("read", "row value precision", None, 0, None, "no row scores")


def measure_coerce() -> Result:
    """Every ratified rule has at least one case, and every case must hold."""
    from mnp.extract import coerce

    cases = coerce_cases()
    ok = 0
    wrong: list[str] = []
    for case in cases:
        kind, raw, expected = case["parser"], case["input"], case["expected"]
        qualifier: str | None = None
        flags: list[str] = []
        if kind == "ionic_strength":
            got, source, flags = coerce.parse_ionic_strength(
                raw, from_medium=case.get("from_medium", False)
            )
            qualifier = getattr(source, "value", None)
        elif kind == "temperature":
            got, qualifier, flags = coerce.parse_temperature(raw)
        elif kind == "number":
            got, _, flags = coerce.parse_number(raw)
        else:  # pragma: no cover - a typo in a fixture, not a code path
            wrong.append(f"unknown parser {kind!r}")
            continue
        if expected is None:
            good = got is None
        else:
            good = got is not None and abs(got - expected) <= case.get("tol", 0.05)
        # "room temperature" and "37 °C incubation" both yield no number; only the qualifier
        # and the flag tell them apart, so a case that cares must say which it expects.
        if good and (want := case.get("expect_qualifier")) is not None:
            good = qualifier == want
            if not good:
                wrong.append(f"{case['rule']}: {raw!r} qualifier {qualifier!r}, wanted {want!r}")
                continue
        if good and (want_flag := case.get("expect_flag")):
            good = want_flag in flags
            if not good:
                wrong.append(f"{case['rule']}: {raw!r} flags {flags}, wanted {want_flag!r}")
                continue
        if good:
            ok += 1
        else:
            wrong.append(f"{case['rule']}: {raw!r} -> {got!r}, wanted {expected!r}")
    value = ok / len(cases) if cases else None
    return Result("coerce", "exact-match accuracy", value, len(cases), 1.0, "; ".join(wrong))


def measure_verify() -> Result:
    """Each case is a fabrication the verifier must refuse. The gate is all of them."""
    from mnp.extract import zeta
    from mnp.schema import models

    cases = _load("verify_adversarial.json")
    caught = 0
    escaped: list[str] = []
    for case in cases:
        conditions = models.MeasurementConditions(**case.get("conditions", {}))
        m = models.SurfaceMeasurement(
            quantity=models.Quantity.zeta_potential,
            value=case.get("value"),
            unit=models.Unit.mV,
            conditions=conditions,
            evidence=models.Evidence(quote=case["quote"]),
        )
        flags = zeta.verify_row(m, case["article_text"])
        expected = case["expect_flag"]
        if expected in flags or (expected == "evidence_unverified" and not m.evidence.verified):
            caught += 1
        else:
            escaped.append(f"{case['name']}: got {flags or 'no flags'}")
    value = caught / len(cases) if cases else None
    return Result("verify", "detection rate", value, len(cases), 1.0, "; ".join(escaped))


def measure_aggregate(fast: bool = False) -> Result:
    """Do the published tables still follow from the records? The offline replay answers it."""
    if fast:
        return Result("aggregate", "artefacts reproduced", None, 0, 1.0, "skipped (fast)")
    import argparse

    from mnp.report import __main__ as report_cli

    code = report_cli.run_reproduce(argparse.Namespace(out=None, slice=None))
    return Result(
        "aggregate",
        "artefacts reproduced",
        1.0 if code == 0 else 0.0,
        1,
        1.0,
        "see `report reproduce` output",
    )


def run_all(fast: bool = False) -> list[Result]:
    return [
        measure_parse(),
        measure_scan(),
        measure_read(),
        measure_coerce(),
        measure_verify(),
        measure_aggregate(fast=fast),
    ]


def summary(results: list[Result]) -> str:
    lines = [
        "# Stage evaluation",
        "",
        "Each stage against its own ground truth. A stage with no ground truth reads",
        "**not measured** — never 0.00 and never 1.00, because both are claims nobody checked.",
        "",
        "| stage | metric | value | n | gate | status |",
        "|---|---|---|---|---|---|",
    ]
    lines += [r.line() for r in results]
    lines += ["", "## What each stage is scored against", ""]
    for stage in STAGES:
        lines.append(f"- **{stage.name}** — {stage.what}. Ground truth: {stage.ground_truth}.")
    detail = [r for r in results if r.detail and r.status in ("fail", "reported")]
    if detail:
        lines += ["", "## Detail", ""]
        lines += [f"- **{r.stage}**: {r.detail}" for r in detail]
    return "\n".join(lines) + "\n"


def write(results: list[Result], tables_dir: Path | None = None) -> Path:
    tables = Path(tables_dir or config.OUT_TABLES)
    tables.mkdir(parents=True, exist_ok=True)
    path = tables / "eval_stages.md"
    path.write_text(summary(results))
    with (tables / "eval_stages.csv").open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["stage", "metric", "value", "n", "threshold", "status"])
        for r in results:
            writer.writerow([r.stage, r.metric, r.value, r.n, r.threshold, r.status])
    return path
