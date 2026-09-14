"""python -m mnp.report d1|d2|d3|d4|all [--out DIR]"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

import pandas as pd

from mnp import config


def _out(args: argparse.Namespace) -> tuple[Path, Path, Path, Path]:
    root = Path(args.out) if args.out else config.OUT
    return root, root / "tables", root / "figures", root / "schema"


def run_gates(args: argparse.Namespace) -> list[Path]:
    """All four evaluation gates (ARCHITECTURE_PLAN.md §6) on one slice of papers."""
    from mnp.report import gates

    _, tables, _, _ = _out(args)
    pmcids = Path(args.slice).read_text().split() if args.slice else []
    gold = pred = None
    gold_path = config.ANNOTATION / "gold_50.csv"
    pred_path = config.DATA_PROCESSED / "zeta_table.parquet"
    if gold_path.is_file() and pred_path.is_file():
        gold = pd.read_csv(gold_path)
        pred = pd.read_parquet(pred_path)
        pred = pred[pred["evidence_verified"].astype(bool)]
        if pmcids:
            gold = gold[gold["pmcid"].isin(pmcids)]
            pred = pred[pred["pmcid"].isin(pmcids)]
    key = config.ROOT / "tests" / "edge" / "key.yaml"
    result = gates.run_all(
        pmcids=pmcids, key_path=key if key.is_file() else None, gold=gold, pred=pred
    )
    tables.mkdir(parents=True, exist_ok=True)
    path = tables / "gates.md"
    path.write_text(gates.markdown(result))
    print(gates.markdown(result))
    return [path]


def run_gate(args: argparse.Namespace) -> list[Path]:
    """Score an extraction against the gold set and pass or fail it on stated thresholds."""
    from mnp.report import gate

    _, tables, _, _ = _out(args)
    gold = pd.read_csv(config.ANNOTATION / "gold_50.csv")
    pred = pd.read_parquet(config.DATA_PROCESSED / "zeta_table.parquet")
    pred = pred[pred["evidence_verified"].astype(bool)]
    if args.slice:
        keep = set(Path(args.slice).read_text().split())
        gold = gold[gold["pmcid"].isin(keep)]
        pred = pred[pred["pmcid"].isin(keep)]
    result = gate.run(pred, gold)
    path = gate.write(result, tables)
    print(gate.markdown(result))
    return [path] if result["passed"] else []


def run_d1_gold(args: argparse.Namespace) -> list[Path]:
    """The same statistic on the hand-annotated stratified sample of 50 papers."""
    from mnp.report import d1

    _, tables, figures, _ = _out(args)
    gold_path = config.ANNOTATION / "gold_50.csv"
    if not gold_path.is_file():
        print(f"d1-gold: {gold_path} missing — run `extract gold-merge` first", file=sys.stderr)
        return []
    gold = pd.read_csv(gold_path)
    sampled = gold["pmcid"].nunique()
    prepared = d1.prepare_gold(gold)
    rec_path = config.EPMC_SEARCH_DIR / "records.parquet"
    records = pd.read_parquet(rec_path) if rec_path.is_file() else None
    return d1.build(
        prepared,
        records,
        tables,
        figures,
        hit_counts={"hits_oa": sampled},
        prefix="d1_gold",
        denominator_note=(
            f"the {sampled} papers of the stratified random sample, annotated by hand"
        ),
    )


def run_d1(args: argparse.Namespace) -> list[Path]:
    from mnp.report import d1

    root, tables, figures, _ = _out(args)
    table_path = config.DATA_PROCESSED / "zeta_table.parquet"
    table = pd.read_parquet(table_path) if table_path.is_file() else pd.DataFrame()
    rec_path = config.EPMC_SEARCH_DIR / "records.parquet"
    records = pd.read_parquet(rec_path) if rec_path.is_file() else None
    hits_path = config.EPMC_SEARCH_DIR / "hit_counts.json"
    hits = json.loads(hits_path.read_text()) if hits_path.is_file() else None
    if table.empty:
        print(
            "d1: no zeta_table.parquet yet — run the corpus and extraction first", file=sys.stderr
        )
        return []
    return d1.build(table, records, tables, figures, hit_counts=hits)


def run_d2(args: argparse.Namespace) -> list[Path]:
    from mnp.report import d2

    root, _, _, schema = _out(args)
    return d2.build(schema, root)


def run_d3(args: argparse.Namespace) -> list[Path]:
    from mnp.report import d3

    _, tables, figures, _ = _out(args)
    try:
        return d3.build(tables, figures)
    except FileNotFoundError as e:
        print(f"d3: {e}", file=sys.stderr)
        return []


def run_d4(args: argparse.Namespace) -> list[Path]:
    try:
        d4 = importlib.import_module("mnp.report.d4")
    except ModuleNotFoundError:
        print("d4: report module not built yet", file=sys.stderr)
        return []
    _, tables, figures, _ = _out(args)
    return d4.build(tables, figures)


RUNNERS = {
    "d1": run_d1,
    "d1-gold": run_d1_gold,
    "gate": run_gate,
    "gates": run_gates,
    "d2": run_d2,
    "d3": run_d3,
    "d4": run_d4,
}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m mnp.report")
    p.add_argument("what", choices=[*RUNNERS, "all"])
    p.add_argument("--out", default=None, help="output root (default: out/)")
    p.add_argument(
        "--slice",
        default=None,
        help="gate only: a file of PMCIDs to score, instead of the whole gold set",
    )
    args = p.parse_args(argv)
    # `all` builds the deliverables; the gate is a check, run deliberately.
    targets = (
        [k for k in RUNNERS if k not in ("gate", "gates")] if args.what == "all" else [args.what]
    )
    for name in targets:
        written = RUNNERS[name](args)
        for path in written:
            print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
