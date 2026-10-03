"""python -m mnp.report d1|d2|d3|d4|origin|release|review|all|reproduce|rehydrate [--out DIR]"""

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
    """The same statistic on the stratified sample of 50 papers that Claude annotated."""
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
            f"the {sampled} papers of the stratified random sample, annotated by Claude and not "
            "yet audited by a person"
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
    articles_path = config.DATA_INTERIM / "articles.parquet"
    articles = pd.read_parquet(articles_path) if articles_path.is_file() else None
    return d1.build(table, records, tables, figures, hit_counts=hits, articles=articles)


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
    from mnp.ek import qa

    bank = qa.bank_path()
    if not bank.is_file():
        print(f"d4: {bank} missing — no printed-fit bank to recompute", file=sys.stderr)
        return []
    _, tables, figures, _ = _out(args)
    return d4.build(tables, figures)


def run_e1(args: argparse.Namespace) -> list[Path]:
    """E1 — the representation bake-off, re-run from the vendored corpus. No model, no network."""
    from mnp.report import e1

    _, tables, _, _ = _out(args)
    try:
        return e1.build(tables)
    except FileNotFoundError as e:
        print(f"e1: {e}", file=sys.stderr)
        return []


def run_demo(args: argparse.Namespace) -> list[Path]:
    """The 13-case demo: cases/, README.md and METHOD.md, plus the committed reader runs.

    Reads `out/tables/d1_zeta_table.csv` the same way every other runner does, so a replay that
    rebuilds it also moves the demo's numbers. It calls no model: the reader's answers come from
    `data/interim/runs/demo-cell{d,b}-20260928`, read and never regenerated.
    """
    from mnp.demo import render

    root, _, _, _ = _out(args)
    return render.build(root)


def run_origin(args: argparse.Namespace) -> list[Path]:
    """Where every measured particle came from, rebuilt from recorded judgement. Asks nothing.

    The reader's answers and the recorded second reading (a Claude agent's) under
    data/interim/origin are read, never regenerated; they are matched to the D1 table in the
    requested output root, so a replay rebuilds them against the table it rebuilt.
    """
    from mnp.extract import origin as reader
    from mnp.report import origin

    _, tables, _, _ = _out(args)
    table_path = tables / "d1_zeta_table.csv"
    answers = reader.answers_dir() / "answers.jsonl"
    if not table_path.is_file():
        print(f"origin: {table_path} missing — run `report d1` first", file=sys.stderr)
        return []
    if not answers.is_file():
        print(f"origin: {answers} missing — no recorded reader answers to match", file=sys.stderr)
        return []
    pmcids = sorted(pd.read_csv(table_path)["pmcid"].dropna().unique())
    absent = [p for p in pmcids if not (config.EPMC_XML_DIR / f"{p}.xml").is_file()]
    if absent:
        print(f"origin: {len(absent)} of {len(pmcids)} source XMLs are not in "
              f"{config.EPMC_XML_DIR} — run `corpus restore`", file=sys.stderr)  # fmt: skip
        return []
    origin.build(reader.RUN_ID, tables)
    return [tables / "sample_origin.csv", tables / "sample_origin_stats.json"]


def run_release(args: argparse.Namespace) -> list[Path]:
    """The vanilla dataset release: parquet + JSONL + schema + LICENSE + card, from d1's table.

    It reads the table out of the requested output root rather than out of `data/processed`,
    so a replay releases what that replay rebuilt and not what happens to be committed. Each
    paper's licence, and the lines a withheld quote is addressed into, come from the vendored
    XML — the one input a fresh clone restores from a tracked archive.
    """
    from mnp.corpus import jats, licence, lines
    from mnp.report import release

    root, tables, _, _ = _out(args)
    table_path, stats_path = tables / "d1_zeta_table.csv", tables / "d1_stats.json"
    if not (table_path.is_file() and stats_path.is_file()):
        print(f"release: {table_path} or d1_stats.json missing — run `report d1` first",
              file=sys.stderr)  # fmt: skip
        return []
    table = pd.read_csv(table_path)
    xml_dir = config.EPMC_XML_DIR
    pmcids = sorted(table["pmcid"].dropna().unique())
    absent = [p for p in pmcids if not (xml_dir / f"{p}.xml").is_file()]
    if absent:
        print(f"release: {len(absent)} of {len(pmcids)} source XMLs are not in {xml_dir} "
              f"({', '.join(absent[:3])}…) — run `corpus restore`; a licence cannot be read "
              "from an article that is not here", file=sys.stderr)  # fmt: skip
        return []

    def documents(pmcid: str) -> lines.LinedDoc:
        return lines.build_lines(jats.parse((xml_dir / f"{pmcid}.xml").read_bytes()))

    gold_path = config.ANNOTATION / "gold_50.csv"
    origin_path = tables / "sample_origin_stats.json"
    return release.build(
        table,
        json.loads(stats_path.read_text()),
        root / "release",
        licences={p: licence.read(p, xml_dir) for p in pmcids},
        documents=documents,
        gold=pd.read_csv(gold_path) if gold_path.is_file() else None,
        origin=json.loads(origin_path.read_text()) if origin_path.is_file() else None,
        corpus_archive=xml_dir.parent / "xml.tar.gz",
        corpus_manifest=xml_dir.parent / "manifest.sha256",
    )


def run_review(args: argparse.Namespace) -> list[Path]:
    """A guide for checking the dataset by hand, and five worksheets to recompute it with.

    Reads the table, stats and release out of the requested output root, like `release` does, so
    a replay reviews what it rebuilt. Calls no model and reaches no network.
    """
    from mnp.report import review

    root, tables, _, _ = _out(args)
    needed = (tables / "d1_zeta_table.csv", tables / "d1_stats.json",
              root / "release" / "dataset.parquet")  # fmt: skip
    missing = [str(p) for p in needed if not p.is_file()]
    if missing:
        print(f"review: {', '.join(missing)} missing — run `report d1` and `report release` "
              "first", file=sys.stderr)  # fmt: skip
        return []
    return review.build(root)


def run_rehydrate(args: argparse.Namespace) -> int:
    """Put the withheld quotes back, locally, from the source articles. Not a builder.

    It writes outside `out/` and may reach the network, so it is kept out of RUNNERS: neither
    `all` nor `reproduce` can run it by iterating them.
    """
    from mnp.report import quotes

    release_dir = Path(args.release) if args.release else config.OUT / "release"
    target = Path(args.out) if args.out else config.DATA_INTERIM / "rehydrated"
    if target.resolve().is_relative_to(config.OUT.resolve()):
        print(f"rehydrate: refusing to write into {config.OUT}/ — restored quotes carry their "
              "sources' licences, not the dataset's, and must stay out of the published tree",
              file=sys.stderr)  # fmt: skip
        return 2
    if not (release_dir / "dataset.parquet").is_file():
        print(f"rehydrate: no dataset.parquet in {release_dir} — run `report release` first",
              file=sys.stderr)  # fmt: skip
        return 1
    if args.fetch:
        import httpx

        from mnp.corpus import epmc

        with httpx.Client() as client:
            api = epmc.EuropePMC(client, target / "xml", target / "xml")

            def fetch(pmcid: str) -> bytes | None:
                path = api.fetch_full_text(pmcid)
                return path.read_bytes() if path else None

            result = quotes.rehydrate(release_dir, target, xml_dir=config.EPMC_XML_DIR, fetch=fetch)
    else:
        result = quotes.rehydrate(release_dir, target, xml_dir=config.EPMC_XML_DIR)
    print(
        f"rehydrate: {result.restored} / {result.withheld} withheld quotes restored and "
        f"sha256-checked -> {target}"
    )
    if result.missing_xml:
        shown = ", ".join(result.missing_xml[:5])
        print(
            f"  no source for {len(result.missing_xml)} papers ({shown}) — "
            "run `corpus restore`, or pass --fetch"
        )
    if result.failed:
        shown = ", ".join(result.failed[:10])
        print(f"  {len(result.failed)} did not match their sha256 and were left null: {shown}")
    return 1 if result.missing_xml or result.failed else 0


def _tracked_artefacts(root: Path) -> list[str] | None:
    """The committed artefacts, as git knows them. None when this is not a checkout."""
    import subprocess

    try:
        done = subprocess.run(
            ["git", "ls-files", str(root)],
            cwd=config.ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover - no git here
        return None
    # git prints repository-relative paths, so the prefix to strip is the repository-relative
    # form of `root`, not its absolute one.
    prefix = root.relative_to(config.ROOT)
    names = [Path(line).relative_to(prefix).as_posix() for line in done.stdout.split() if line]
    return names or None


# Committed artefacts the offline replay does not rebuild, and why. Named here rather than
# silently missing from the diff: an artefact nobody re-derives is one nobody is checking.
EXCLUDED_FROM_REPLAY = {
    "tables/d4_sbc.csv": "needs `infer sbc` — torch, minutes of CPU; seeded, run deliberately",
    "tables/rules_impact.md": "produced by tool/rules_impact.py, a one-off scoring of the "
    "ratified rules against records extracted before them",
    "tables/slice_20260915.md": "a dated record of one run, not a derived artefact — it "
    "reports what the slice scored on the day it ran and is not meant to move again",
}


def _uncommitted(root: Path) -> list[str]:
    """Artefacts that differ from HEAD, so the published copy is not what this tree rebuilds."""
    import subprocess

    try:
        done = subprocess.run(
            ["git", "status", "--porcelain", "--", str(root)],
            cwd=config.ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover - no git here
        return []
    return [line[3:].strip() for line in done.stdout.splitlines() if line.strip()]


def run_protocol(args: argparse.Namespace) -> int:
    """Render docs/PROTOCOL.md from the registry. The document has no other writer."""
    from mnp import protocol

    path = config.ROOT / "docs" / "PROTOCOL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(protocol.render())
    print(f"{len(protocol.STEPS)} steps -> {path}")
    return 0


def run_reproduce(args: argparse.Namespace) -> int:
    """Rebuild every committed artefact from the vendored corpus, offline, and diff."""
    import tempfile

    from mnp.corpus import __main__ as corpus_cli
    from mnp.eval import __main__ as eval_cli
    from mnp.extract import __main__ as extract_cli
    from mnp.report import reproduce

    records = config.DATA_INTERIM / "extractions.jsonl"
    before_records = reproduce.sha256_file(records) if records.is_file() else None
    stale: list[bool] = []

    def build(out_dir: Path) -> None:
        if corpus_cli.main(["verify"]) != 0:
            raise SystemExit("corpus does not match its manifest; run `corpus restore` first")
        corpus_cli.main(["parse"])
        extract_cli.main(["table"])
        # The scanner numbers stored in each record go stale whenever the scanner changes.
        # Checked read-only here: a replay may not repair the record it is checking.
        if extract_cli.main(["recount", "--check"]) != 0:
            stale.append(True)
        # Several commands write straight to out/tables rather than honouring --out; point
        # that constant at the scratch tree for the duration so the replay writes nothing
        # into the committed one.
        real_tables = config.OUT_TABLES
        config.OUT_TABLES = out_dir / "tables"
        try:
            extract_cli.main(["review-list"])
            # The stage evaluation is a committed artefact, so the replay has to rebuild it
            # too — otherwise it is a published number nobody re-derives. --fast skips only
            # its aggregate row, which is this very replay.
            eval_cli.main(["all", "--fast"])
            extract_cli.main(["evaluate", "--gold", str(config.ANNOTATION / "gold_50.csv")])
            rebuilt = argparse.Namespace(out=str(out_dir), slice=None)
            for name in RUNNERS:
                if name == "gates":
                    continue
                RUNNERS[name](rebuilt)
            slice_path = config.DATA_INTERIM / "worklists" / "gate3_slice.txt"
            if slice_path.is_file():
                RUNNERS["gates"](argparse.Namespace(out=str(out_dir), slice=str(slice_path)))
        finally:
            config.OUT_TABLES = real_tables

    only = _tracked_artefacts(config.OUT)
    if only is not None:
        for name, why in EXCLUDED_FROM_REPLAY.items():
            if name in only:
                only.remove(name)
                print(f"  excluded by design: {name} — {why}")

    with tempfile.TemporaryDirectory(prefix="mnp-reproduce-") as tmp:
        code = reproduce.run(
            committed=config.OUT,
            rebuilt=Path(tmp) / "out",
            build=build,
            only=only,
        )

    after_records = reproduce.sha256_file(records) if records.is_file() else None
    if before_records != after_records:
        print("  changed: data/interim/extractions.jsonl — a replay must not write the record")
        code = 1
    if stale:
        code = 1
    # Rebuilding the working tree is not the claim. The claim is about what is published, so
    # an artefact that differs from HEAD is a published number nobody has re-derived.
    for name in _uncommitted(config.OUT):
        print(f"  uncommitted: {name} — rebuilt here but not committed, so not published")
        code = 1
    return code


# Builders: each writes into the output root, and `all` and `reproduce` iterate them.
RUNNERS = {
    "d1": run_d1,
    "d1-gold": run_d1_gold,
    "gate": run_gate,
    "gates": run_gates,
    "d2": run_d2,
    "d3": run_d3,
    "d4": run_d4,
    "e1": run_e1,
    # After d1, whose table it matches the recorded answers to; before demo, release and review,
    # which read its stats.
    "origin": run_origin,
    # After origin: README.md and METHOD.md open with the scope block, which states the origin.
    # Before review, which reads METHOD.md.
    "demo": run_demo,
    # After d1: it reads the table d1 wrote into the same output root.
    "release": run_release,
    # After release: it reads the released parquet as well as the table.
    "review": run_review,
}

# Everything else the CLI offers. Not builders, so no loop over RUNNERS reaches them.
COMMANDS = ("all", "reproduce", "protocol", "rehydrate")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m mnp.report")
    p.add_argument("what", choices=[*RUNNERS, *COMMANDS])
    p.add_argument(
        "--out",
        default=None,
        help="output root (default: out/); for rehydrate, where the local copy goes "
        "(default: data/interim/rehydrated, never under out/)",
    )
    p.add_argument("--release", default=None, help="rehydrate only: default out/release")
    p.add_argument(
        "--fetch",
        action="store_true",
        help="rehydrate only: download an article missing from the corpus from Europe PMC",
    )
    p.add_argument(
        "--slice",
        default=None,
        help="gate only: a file of PMCIDs to score, instead of the whole gold set",
    )
    args = p.parse_args(argv)
    if args.what == "reproduce":
        return run_reproduce(args)
    if args.what == "protocol":
        return run_protocol(args)
    if args.what == "rehydrate":
        return run_rehydrate(args)
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
