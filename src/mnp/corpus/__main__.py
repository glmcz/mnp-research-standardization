"""python -m mnp.corpus search|fetch|parse|snapshot|verify|restore"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx
import pandas as pd

from mnp import config
from mnp.corpus import epmc, jats, snapshot


def cmd_search(args: argparse.Namespace) -> int:
    query = Path(args.query_file).read_text().strip()
    config.ensure_dirs()
    with httpx.Client() as client:
        api = epmc.EuropePMC(client, config.EPMC_SEARCH_DIR, config.EPMC_XML_DIR)
        all_query = epmc.without_oa_filter(query)
        counts = {
            "query_oa": query,
            "query_all": all_query,
            "hits_oa": epmc.hit_count(client, query),
            "hits_all": epmc.hit_count(client, all_query),
        }
        print(json.dumps(counts, indent=2))
        # One crawl of the unrestricted query carries the OA flag per record, so
        # both denominators come from the same page set.
        records = api.search(all_query)
    (config.EPMC_SEARCH_DIR / "hit_counts.json").write_text(json.dumps(counts, indent=2))
    df = epmc.records_to_frame(records)
    df.to_parquet(config.EPMC_SEARCH_DIR / "records.parquet", index=False)
    print(
        f"{len(records)} records, {len(df)} with a PMCID after DOI dedupe, "
        f"{int(df['is_oa'].sum())} open access"
    )
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    df = pd.read_parquet(config.EPMC_SEARCH_DIR / "records.parquet")
    targets = df.loc[df["is_oa"], "pmcid"].tolist()
    if args.limit:
        targets = targets[: args.limit]
    ok = missing = 0
    with httpx.Client() as client:
        api = epmc.EuropePMC(client, config.EPMC_SEARCH_DIR, config.EPMC_XML_DIR)
        for i, pmcid in enumerate(targets, 1):
            if api.fetch_full_text(pmcid) is None:
                missing += 1
            else:
                ok += 1
            if i % 50 == 0:
                print(f"{i}/{len(targets)} fetched={ok} failed={missing}", flush=True)
    print(f"done: fetched={ok} failed={missing} (see fetch_log.csv)")
    return 0


def cmd_parse(args: argparse.Namespace) -> int:
    rows = []
    for path in sorted(config.EPMC_XML_DIR.glob("PMC*.xml")):
        a = jats.parse(path.read_bytes())
        rows.append(
            {
                "pmcid": a.pmcid or path.stem,
                "doi": a.doi,
                "title": a.title,
                "year": a.year,
                "journal": a.journal,
                "license": a.license,
                "methods_source": a.methods_source,
                "methods_text": a.methods_text,
                "n_tables": len(a.tables),
                "n_extra_sections": len(a.extra_sections),
                "n_keyword_windows": len(a.keyword_windows),
                "extraction_text": jats.extraction_text(a, max_tokens=args.max_tokens),
                "full_text": a.full_text,
            }
        )
    df = pd.DataFrame(rows)
    out = config.DATA_INTERIM / "articles.parquet"
    df.to_parquet(out, index=False)
    src = df["methods_source"].value_counts().to_dict() if len(df) else {}
    print(f"{len(df)} articles -> {out}; methods_source={src}")
    return 0


MANIFEST = config.EPMC_XML_DIR.parent / "manifest.sha256"
ARCHIVE = config.EPMC_XML_DIR.parent / "xml.tar.gz"


def cmd_snapshot(args: argparse.Namespace) -> int:
    """Freeze the fetched corpus: one archive, one manifest, both reproducible."""
    n = snapshot.write_manifest(config.EPMC_XML_DIR, MANIFEST)
    snapshot.write_archive(config.EPMC_XML_DIR, ARCHIVE)
    size = ARCHIVE.stat().st_size / 1e6
    print(f"{n} files -> {MANIFEST.name} and {ARCHIVE.name} ({size:.1f} MB)")
    print(f"archive sha256 {snapshot.sha256_file(ARCHIVE)}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    report = snapshot.verify(config.EPMC_XML_DIR, MANIFEST)
    print(report.summary())
    for label, names in (
        ("missing", report.missing),
        ("extra", report.extra),
        ("changed", report.changed),
    ):
        if names:
            print(f"  {label}: {', '.join(names[:10])}{' …' if len(names) > 10 else ''}")
    return 0 if report.ok else 1


def cmd_restore(args: argparse.Namespace) -> int:
    n = snapshot.restore(ARCHIVE, config.EPMC_XML_DIR)
    print(f"restored {n} files to {config.EPMC_XML_DIR}")
    return cmd_verify(args)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m mnp.corpus")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("--query-file", default=str(config.QUERIES / "q1.txt"))
    s.set_defaults(fn=cmd_search)
    f = sub.add_parser("fetch")
    f.add_argument("--limit", type=int, default=0)
    f.set_defaults(fn=cmd_fetch)
    pa = sub.add_parser("parse")
    pa.add_argument("--max-tokens", type=int, default=12_000)
    pa.set_defaults(fn=cmd_parse)
    sub.add_parser("snapshot").set_defaults(fn=cmd_snapshot)
    sub.add_parser("verify").set_defaults(fn=cmd_verify)
    sub.add_parser("restore").set_defaults(fn=cmd_restore)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
