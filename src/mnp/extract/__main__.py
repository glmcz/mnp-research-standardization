"""python -m mnp.extract run|sample|evaluate"""

from __future__ import annotations

import argparse
import fcntl
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd

from mnp import config, runs
from mnp.corpus import jats, lines
from mnp.extract import evaluate, llm, measurand, prompts, provenance, units, zeta

YEAR_BANDS = (("<=2018", -1, 2018), ("2019-2022", 2019, 2022), ("2023-2026", 2023, 2100))


def _band(year) -> str | None:
    if year is None or pd.isna(year):
        return None
    for name, lo, hi in YEAR_BANDS:
        if lo <= int(year) <= hi:
            return name
    return None


def _jsonl_path() -> Path:
    return config.DATA_INTERIM / "extractions.jsonl"


def _load_records(path: Path) -> dict[str, zeta.ExtractionRecord]:
    if not path.is_file():
        return {}
    out = {}
    for line in path.read_text().splitlines():
        if line.strip():
            rec = zeta.ExtractionRecord.from_json(line)
            out[rec.pmcid] = rec
    return out


def _error_record(pmcid: str, message: str) -> zeta.ExtractionRecord:
    return zeta.ExtractionRecord(
        pmcid=pmcid, doi=None, model=None, prompt_sha256=prompts.prompt_sha256(), error=message
    )


def cmd_run(args: argparse.Namespace) -> int:
    articles = pd.read_parquet(config.DATA_INTERIM / "articles.parquet")
    path = _jsonl_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    done = _load_records(path)
    # A record that failed (no model answered, XML missing) is not an answer: retry it
    # unless asked not to. A successful record is never re-billed.
    todo = [
        p
        for p in articles["pmcid"].tolist()
        if p not in done or (args.retry_errors and done[p].error)
    ]
    if args.limit:
        todo = todo[: args.limit]
    client = llm.from_env(cache_dir=config.LLM_CACHE, model=args.model)
    print(f"{len(done)} done, {len(todo)} to extract, chain={client.chain}", flush=True)
    lock = threading.Lock()

    def one(pmcid: str) -> zeta.ExtractionRecord:
        xml = config.EPMC_XML_DIR / f"{pmcid}.xml"
        if not xml.is_file():
            rec = _error_record(pmcid, f"xml not found: {xml.name}")
        else:
            article = jats.parse(xml.read_bytes())
            article.pmcid = pmcid
            rec = zeta.extract_paper(article, client)
        with lock, _locked(path):
            on_disk = _load_records(path)
            on_disk[pmcid] = rec
            _rewrite(path, on_disk)
            done[pmcid] = rec
            n = len(done)
        if n % 10 == 0 or rec.error:
            print(
                f"[{n}] {pmcid} rows={len(rec.measurements)} cov={rec.coverage} "
                f"model={rec.model} err={rec.error}",
                flush=True,
            )
        return rec

    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        list(pool.map(one, todo))
    # Re-read: a worker's `ingest` may have landed while this run was working, and its
    # record is better than ours — rebuilding from memory would silently drop it.
    with _locked(path):
        _write_table(_load_records(path))
    return 0


def _hash_counts(values) -> dict[str, int]:
    """How many records carry each hash, with the missing ones counted under "none"."""
    counts: dict[str, int] = {}
    for value in values:
        key = value if value else "none"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def _paper_for(rec: zeta.ExtractionRecord) -> str | None:
    """The article's full text when rule R2b must read it, else None — most records never do.

    Missing XML is refused rather than skipped: without the paper the rule would silently keep
    a temperature it clears when the corpus is present, and the table would depend on which
    checkout built it.
    """
    if not any(zeta.needs_paper(m) for m in rec.measurements):
        return None
    article = _article(rec.pmcid)
    if article is None:
        raise SystemExit(
            f"{rec.pmcid}: no XML, and rule R2b needs the paper to build its rows; "
            "run `python -m mnp.corpus restore`"
        )
    return article.full_text


def _write_table(done: dict[str, zeta.ExtractionRecord], quiet: bool = False) -> None:
    rows = [r for rec in done.values() for r in rec.to_rows(_paper_for(rec))]
    table = pd.DataFrame(rows)
    config.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    table.to_parquet(config.DATA_PROCESSED / "zeta_table.parquet", index=False)
    recs = list(done.values())
    covs = [r.coverage for r in recs if r.coverage is not None]
    summary = {
        "papers": len(recs),
        "papers_with_error": sum(1 for r in recs if r.error),
        "papers_with_rows": sum(1 for r in recs if r.measurements),
        "rows": len(rows),
        "rows_verified": int(table["evidence_verified"].sum()) if len(table) else 0,
        "rows_dropped": sum(len(r.dropped) for r in recs),
        "candidates": sum(r.n_candidates for r in recs),
        "candidates_matched": sum(r.n_candidates_matched for r in recs),
        "coverage_mean": float(np.mean(covs)) if covs else None,
        "models": sorted({r.model for r in recs if r.model}),
        # What the records themselves carry. The code's current prompt is reported
        # separately and never as provenance: editing it must not change a summary about
        # records that have not moved.
        "prompt_sha256_in_records": _hash_counts(r.prompt_sha256 for r in recs),
        "brief_sha256_in_records": _hash_counts(r.brief_sha256 for r in recs),
        "code_prompt_sha256": prompts.prompt_sha256(),
    }
    (config.DATA_PROCESSED / "extraction_summary.json").write_text(json.dumps(summary, indent=2))
    if not quiet:
        print(json.dumps(summary, indent=2))


def _article(pmcid: str) -> jats.Article | None:
    xml = config.EPMC_XML_DIR / f"{pmcid}.xml"
    if not xml.is_file():
        return None
    article = jats.parse(xml.read_bytes())
    article.pmcid = pmcid  # the corpus key is the PMCID we fetched, not the XML's claim
    return article


@contextmanager
def _locked(path: Path):
    """Exclusive lock so parallel `ingest` workers never lose each other's records."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(".lock")
    with lock.open("w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _rewrite(path: Path, done: dict[str, zeta.ExtractionRecord]) -> None:
    tmp = path.with_suffix(".jsonl.tmp")
    with tmp.open("w") as fh:
        for rec in done.values():
            fh.write(rec.to_json() + "\n")
    tmp.replace(path)


def cmd_show(args: argparse.Namespace) -> int:
    """What an extractor reads for one paper: the system prompt, then the user prompt."""
    article = _article(args.pmcid)
    if article is None:
        print(f"no XML for {args.pmcid}", file=sys.stderr)
        return 1
    text = jats.extraction_text(article, max_tokens=zeta.MAX_TOKENS)
    if not args.no_system:
        print(prompts.system_prompt())
        print("\n" + "=" * 78 + "\n")
    print(prompts.user_prompt(article.pmcid, text))
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    """Run a supplied JSON reply through coerce → verify → coverage and record it."""
    if not getattr(args, "brief", None) and not getattr(args, "no_brief", False):
        print(
            "refusing to record a judgement with no provenance: pass --brief docs/briefs/"
            "extraction.md, or --no-brief to say deliberately that there was none",
            file=sys.stderr,
        )
        return 2
    article = _article(args.pmcid)
    if article is None:
        print(f"no XML for {args.pmcid}", file=sys.stderr)
        return 1
    try:
        data = json.loads(Path(args.json).read_text())
    except (OSError, json.JSONDecodeError) as e:
        print(f"payload unreadable: {e}", file=sys.stderr)
        return 1
    if not isinstance(data, dict):
        print("payload must be a JSON object with a 'measurements' list", file=sys.stderr)
        return 1
    brief = provenance.load_brief(args.brief) if getattr(args, "brief", None) else None
    rec = zeta.extract_from_payload(article, data, args.model)
    if brief is not None:
        rec.brief_path, rec.brief_sha256 = brief.path, brief.sha256
    if not args.dry_run:
        path = _jsonl_path()
        with _locked(path):
            done = _load_records(path)
            done[rec.pmcid] = rec
            _rewrite(path, done)
            _write_table(done, quiet=True)
    flagged = sum(1 for f in rec.row_flags if f)
    print(
        f"{rec.pmcid}: rows={len(rec.measurements)} flagged={flagged} dropped={len(rec.dropped)} "
        f"candidates={rec.n_candidates} matched={rec.n_candidates_matched} "
        f"coverage={rec.coverage if rec.coverage is None else round(rec.coverage, 2)} "
        # An operator must be able to see from this line whether the judgement was
        # recorded against a brief. Storing it silently is how provenance rots.
        f"brief={rec.brief_sha256[:12] if rec.brief_sha256 else 'none'}"
    )
    for i, (mm, flags) in enumerate(zip(rec.measurements, rec.row_flags, strict=True)):
        if flags:
            print(f"  row {i} ({mm.particle_name!r}, {mm.value} {mm.unit.value}): {flags}")
    for d in rec.dropped:
        print(f"  dropped {d['index']}: {d['flags']}")
    if rec.unmatched_candidates:
        print("  unmatched printed values:")
        for u in rec.unmatched_candidates[:20]:
            print(f"    {u['value']} ({u['quantity']}) in {u['location']}: {u['context'][:70]!r}")
    if args.dry_run:
        print("  dry run: verified and reported, nothing recorded")
        return 0
    if getattr(args, "run_id", None):
        runs.start(
            args.run_id,
            model=args.model,
            brief_sha256=brief.sha256 if brief else None,
        )
        runs.assign(args.run_id, worker=args.worker or args.model, pmcids=[args.pmcid])
    return 0


def cmd_todo(args: argparse.Namespace) -> int:
    articles = pd.read_parquet(config.DATA_INTERIM / "articles.parquet")
    done = _load_records(_jsonl_path())
    if args.with_values:
        keep = articles["extraction_text"].map(lambda t: bool(zeta.find_candidates(t or "")))
        articles = articles[keep]
    if args.missing_brief:
        # Papers that *have* a record but cannot be traced to the instructions that made it.
        todo = [p for p in articles["pmcid"].tolist() if p in done and not done[p].brief_sha256]
    else:
        todo = [p for p in articles["pmcid"].tolist() if p not in done]
    if args.limit:
        todo = todo[: args.limit]
    for p in todo:
        print(p)
    return 0


# What the author re-judges; blanked so the audit is blind to the first annotator.
AUDIT_BLANK = (
    "medium_class",
    "ionic_strength_mM",
    "I_reported",
    "I_inferable_from_named_salt",
    "pH",
    "pH_reported",
    "temperature_C",
    "T_reported",
    "instrument_reported",
    "value",
    "value_text",
    "sd",
    "n",
    "medium_matches_exposure",
    "notes",
)


EPMC_URL = "https://europepmc.org/article/PMC/{}"


def cmd_units(args: argparse.Namespace) -> int:
    """Print the units the article itself prints, per table column and sentence.

    A manual pass over the one field a retyped transcription can corrupt silently.
    """
    article = _article(args.pmcid)
    if article is None:
        print(f"{args.pmcid}: no XML", file=sys.stderr)
        return 1
    text = jats.extraction_text(article, max_tokens=zeta.MAX_TOKENS)
    rows = units.report(text)
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    if not rows:
        print(f"{args.pmcid}: no printed unit found")
        return 0
    print(f"{args.pmcid}: {len(rows)} printed unit(s)")
    print(f"  {'location':22} {'source':8} {'quantity':26} {'unit':22} factor")
    for r in rows:
        print(
            f"  {r['location'][:22]:22} {r['source']:8} {str(r['quantity'])[:26]:26} "
            f"{r['unit'][:22]:22} {r['factor']:g}"
        )
    return 0


def cmd_review_measurand(args: argparse.Namespace) -> int:
    """Papers where the thing measured may not have been the plastic (ratified rule S8).

    Judgement, so this lists rather than decides: each hit is a paper someone has to read.
    Restricted to papers that currently carry rows, since a paper with none cannot be
    contributing a measurement of the wrong thing.
    """
    articles = pd.read_parquet(config.DATA_INTERIM / "articles.parquet").set_index("pmcid")
    done = _load_records(_jsonl_path())
    rows = []
    for pmcid, rec in done.items():
        if not rec.measurements or pmcid not in articles.index:
            continue
        for hit in measurand.suspicions(articles.loc[pmcid, "extraction_text"] or ""):
            rows.append((pmcid, len(rec.measurements), hit.kind, hit.quote))
    rows.sort(key=lambda r: -r[1])
    for pmcid, n, kind, quote in rows:
        print(f"{pmcid}\trows={n}\t{kind}\t{quote}")
    papers = len({r[0] for r in rows})
    print(
        f"\n{papers} papers to review, {sum(dict((r[0], r[1]) for r in rows).values())} rows "
        f"at stake",
        file=sys.stderr,
    )
    return 0


def cmd_table(args: argparse.Namespace) -> int:
    """Rebuild the derived row table from the records, touching nothing else.

    `recount` also rewrites `extractions.jsonl`; an offline replay must not write to the
    scientific record it is checking, so the derived artefact gets its own command.
    """
    path = _jsonl_path()
    done = _load_records(path)
    _write_table(done, quiet=True)
    print(f"rebuilt zeta_table.parquet from {len(done)} records")
    return 0


def cmd_recount(args: argparse.Namespace) -> int:
    """Recompute candidates and coverage for existing records. No model calls.

    `n_candidates` is a property of the value scanner, not of the extraction, so a fix
    to the scanner makes every stored coverage number stale. This refreshes them and
    leaves the measurements exactly as they were.
    """
    path = _jsonl_path()
    with _locked(path):
        done = _load_records(path)
        stale = []
        for pmcid, rec in done.items():
            article = _article(pmcid)
            if article is None:
                continue
            text = jats.extraction_text(article, max_tokens=zeta.MAX_TOKENS)
            candidates = zeta.find_candidates(text)
            matched, unmatched = zeta._match(candidates, rec.measurements)
            if (rec.n_candidates, rec.n_candidates_matched) != (len(candidates), matched):
                stale.append(pmcid)
            if args.check:
                continue
            rec.n_candidates = len(candidates)
            rec.n_candidates_matched = matched
            rec.unmatched_candidates = unmatched
        if not args.check:
            _rewrite(path, done)
            _write_table(done, quiet=True)
    if args.check:
        if stale:
            shown = ", ".join(stale[:5]) + (" …" if len(stale) > 5 else "")
            print(f"STALE: {len(stale)} of {len(done)} records disagree with the scanner: {shown}")
            print("run `extract recount` to refresh them")
            return 1
        print(f"coverage is current: {len(done)} records agree with the scanner")
        return 0
    print(f"recounted {len(done)} records, {len(stale)} coverage numbers changed")
    return 0


def cmd_reverify(args: argparse.Namespace) -> int:
    """Recompute the verifier's flags on every stored row. No model calls.

    The flags R2 reads are stored at ingest, so a verifier fix changes nothing in the table
    until they are recomputed. Only the verifier's own flags move; the coercer's stay as
    recorded, because only the raw reply could reproduce them.
    """
    path = _jsonl_path()
    with _locked(path):
        done = _load_records(path)
        stale = []
        for pmcid, rec in done.items():
            article = _article(pmcid)
            if article is None or not rec.measurements:
                continue
            fresh = zeta.reverify(rec, article)
            if fresh != rec.row_flags:
                stale.append(pmcid)
                if not args.check:
                    rec.row_flags = fresh
        if stale and not args.check:
            _rewrite(path, done)
            _write_table(done, quiet=True)
    if args.check:
        if stale:
            shown = ", ".join(stale[:5]) + (" …" if len(stale) > 5 else "")
            print(
                f"STALE: {len(stale)} of {len(done)} records carry outdated verifier flags: {shown}"
            )
            print("run `extract reverify` to refresh them")
            return 1
        print(f"verifier flags are current: {len(done)} records agree with the verifier")
        return 0
    print(f"reverified {len(done)} records, {len(stale)} changed")
    return 0


# The two ways a stored quote fails to become a citation. Kept apart because they are
# different facts: one says the line document does not contain this quote, the other says
# there was no line document to look in.
NOT_LOCATED = "evidence_not_located"
NO_DOCUMENT = "line_document_unavailable"
_RETROFIT_FLAGS = (NOT_LOCATED, NO_DOCUMENT)


def _cite(doc: lines.LinedDoc | None, quote: str) -> tuple[tuple[str, ...] | None, str | None]:
    """The line ids a stored quote resolves to, or the flag naming why there are none.

    Hashes, not line numbers: a `line_id` keys on (section path, ordinal, text), so a
    parser fix that renumbers the document leaves a stored citation pointing at the same
    line. A quote whose passages do not all resolve gets no ids at all — a partial
    citation is worse than none, because it reads as complete.
    """
    if doc is None or not doc.lines:
        return None, NO_DOCUMENT
    parts = lines.locate_parts(doc, quote)
    if not parts or not all(parts):
        return None, NOT_LOCATED
    return tuple(lines.resolve(doc, n).line_id for n in lines.locate(doc, quote)), None


def cmd_retrofit(args: argparse.Namespace) -> int:
    """Give every stored quote the line address it already implies. No model, no re-read.

    These rows were extracted before line citation existed, but the address is recoverable:
    each quote was verified verbatim against the article, so it locates in the line-addressed
    document by substring. This writes that address onto the record.

    A one-off migration, deliberately outside the replay: `report reproduce` refuses a run
    that writes to the record it is checking. Re-running is safe and changes nothing — the
    ids are a function of the article and the quote, never of the last run, which is why a
    row that now locates also loses a stale flag.

    The gap being measured: the guard that accepted these quotes searched
    `article.full_text`, while the line document mirrors `jats.extraction_text`, a subset of
    it. A quote can therefore be genuine and still fail to locate. Those rows keep no ids,
    gain a flag and are named here; none is dropped, because the whole point of the count is
    to see that difference rather than absorb it.
    """
    path = _jsonl_path()
    with _locked(path):
        done = _load_records(path)
        counts = dict.fromkeys(("located", "not_located", "no_document", "no_quote", "changed"), 0)
        no_xml: list[str] = []
        no_text: list[str] = []
        named: dict[str, list[str]] = {flag: [] for flag in _RETROFIT_FLAGS}
        for pmcid, rec in done.items():
            article = _article(pmcid)
            doc = lines.build_lines(article) if article is not None else None
            if doc is None:
                no_xml.append(f"{pmcid}({len(rec.measurements)})")
            elif not doc.lines:
                no_text.append(f"{pmcid}({len(rec.measurements)})")
            for m, flags in zip(rec.measurements, rec.row_flags, strict=True):
                quote = m.evidence.quote if m.evidence else ""
                if not quote:
                    counts["no_quote"] += 1
                    continue
                ids, flag = _cite(doc, quote)
                keep = [f for f in flags if f not in _RETROFIT_FLAGS]
                if flag:
                    keep.append(flag)
                    counts["not_located" if flag == NOT_LOCATED else "no_document"] += 1
                    named[flag].append(m.row_id or pmcid)
                else:
                    counts["located"] += 1
                if m.evidence.line_ids != ids or keep != flags:
                    counts["changed"] += 1
                if not args.dry_run:
                    m.evidence.line_ids = ids
                    flags[:] = keep
        if not args.dry_run:
            _rewrite(path, done)
            _write_table(done, quiet=True)
    total = sum(counts[k] for k in ("located", "not_located", "no_document", "no_quote"))
    print(f"retrofit{' (DRY RUN — nothing written)' if args.dry_run else ''}: "
          f"{len(done)} records, {total} rows")  # fmt: skip
    print(f"  located: {counts['located']} ({counts['changed']} changed)")
    print(f"  not located: {counts['not_located']}")
    print(f"  no line document: {counts['no_document']}")
    print(f"  no quote: {counts['no_quote']}")
    print(f"  papers: {len(done)} read, {len(no_xml)} with no XML, {len(no_text)} with no text")
    for label, papers in (("no XML", no_xml), ("no retrievable text", no_text)):
        if papers:
            shown = ", ".join(papers[:25]) + (" …" if len(papers) > 25 else "")
            print(f"  papers with {label} (rows carried in brackets): {shown}")
    for flag, rows in named.items():
        for row_id in rows:
            print(f"  {flag}: {row_id}")
    return 0


def cmd_review_list(args: argparse.Namespace) -> int:
    """List the papers the extraction skips, so the skip is reviewable rather than silent.

    A paper with no regex-detectable printed value can only ever contribute "no
    measurement" — but that is a claim about the paper, so it gets written down with a
    link, and papers that discuss zeta without printing a number are marked.
    """
    articles = pd.read_parquet(config.DATA_INTERIM / "articles.parquet")
    has_value = articles["extraction_text"].map(lambda t: bool(zeta.find_candidates(t or "")))
    skipped = articles[~has_value].copy()
    skipped["mentions_zeta"] = (
        skipped["extraction_text"]
        .fillna("")
        .str.contains(r"zeta|ζ|electrophoretic mobilit", case=False, regex=True)
    )
    skipped["url"] = skipped["pmcid"].map(EPMC_URL.format)
    # NaN is truthy, so a missing DOI would otherwise link to "https://doi.org/nan"
    skipped["doi_url"] = skipped["doi"].map(
        lambda d: (
            None if (d is None or pd.isna(d) or not str(d).strip()) else f"https://doi.org/{d}"
        )
    )
    cols = ["pmcid", "url", "doi", "doi_url", "year", "journal", "title", "methods_source",
            "mentions_zeta"]  # fmt: skip
    skipped = skipped.reindex(columns=cols).sort_values(
        ["mentions_zeta", "year"], ascending=[False, False]
    )
    config.OUT_TABLES.mkdir(parents=True, exist_ok=True)
    csv_path = config.OUT_TABLES / "d1_papers_without_printed_values.csv"
    skipped.to_csv(csv_path, index=False)
    md_path = config.OUT_TABLES / "d1_papers_without_printed_values.md"
    n_mentions = int(skipped["mentions_zeta"].sum())
    lines = [
        "# Papers the extraction skips",
        "",
        f"{len(skipped)} of {len(articles)} open-access papers print no zeta potential or "
        "electrophoretic mobility that the value scanner can find. They still count in the "
        "denominator; none is extracted.",
        "",
        f"**{n_mentions}** of them discuss zeta or mobility without printing a number — those "
        "are the ones worth a human glance, and they are listed first.",
        "",
        "| PMCID | year | journal | mentions ζ | title |",
        "|---|---|---|---|---|",
    ]
    for _, r in skipped.iterrows():
        title = str(r["title"] or "").replace("|", "/")[:110]
        journal = str(r["journal"] or "")[:38]
        mark = "yes" if r["mentions_zeta"] else "—"
        lines.append(
            f"| [{r['pmcid']}]({r['url']}) | {r['year'] or ''} | {journal} | {mark} | {title} |"
        )
    md_path.write_text("\n".join(lines) + "\n")
    print(
        f"{len(skipped)} of {len(articles)} papers print no value ({n_mentions} mention zeta) "
        f"-> {csv_path.name}, {md_path.name}"
    )
    return 0


def cmd_audit_sample(args: argparse.Namespace) -> int:
    """A blind worksheet: n gold papers for the author to re-judge, for Cohen's κ."""
    from mnp.schema.models import GOLD_COLUMNS

    gold = pd.read_csv(config.ANNOTATION / "gold_50.csv")
    papers = sorted(gold["pmcid"].unique())
    rng = np.random.RandomState(args.seed)
    chosen = sorted(rng.choice(papers, size=min(args.n, len(papers)), replace=False).tolist())
    sheet = gold[gold["pmcid"].isin(chosen)].copy()
    for col in AUDIT_BLANK:
        if col in sheet.columns:
            sheet[col] = pd.NA
    sheet["annotator"] = "author"
    sheet = sheet.reindex(columns=list(GOLD_COLUMNS))
    out = config.ANNOTATION / "audit_10.csv"
    sheet.to_csv(out, index=False)
    print(
        f"{len(sheet)} rows over {len(chosen)} papers -> {out}\n"
        "Fill in the blanked columns from the article itself, then save it as "
        "gold_parts/gold_audit.json (a JSON list of the same row objects) and re-run "
        "`gold-merge`; `evaluate` then reports Cohen's κ beside precision/recall."
    )
    return 0


def cmd_gold_merge(args: argparse.Namespace) -> int:
    """gold_parts/*.json (one list per annotator batch) → gold_50.csv in the plan's columns."""
    from mnp.schema.models import GOLD_COLUMNS

    parts_dir = config.ANNOTATION / "gold_parts"
    # Later parts supersede earlier ones per paper: a re-annotation (gold_r*.json, which
    # sorts after gold_5.json) replaces that paper's rows rather than doubling them.
    by_paper: dict[str, list[dict]] = {}
    superseded: list[str] = []
    for part in sorted(parts_dir.glob("*.json")):
        fresh: dict[str, list[dict]] = {}
        for r in json.loads(part.read_text()):
            fresh.setdefault(r.get("pmcid"), []).append({c: r.get(c) for c in GOLD_COLUMNS})
        for pmcid, new_rows in fresh.items():
            if pmcid in by_paper:
                superseded.append(pmcid)
            by_paper[pmcid] = new_rows
    rows = [r for paper_rows in by_paper.values() for r in paper_rows]
    if not rows:
        print(f"no parts in {parts_dir}")
        return 1
    df = pd.DataFrame(rows, columns=list(GOLD_COLUMNS))
    articles = pd.read_parquet(config.DATA_INTERIM / "articles.parquet")[["pmcid", "doi"]]
    doi = articles.set_index("pmcid")["doi"]
    df["doi"] = df["doi"].where(df["doi"].notna(), df["pmcid"].map(doi))
    for i, r in df.iterrows():
        if not r["row_id"]:
            df.at[i, "row_id"] = f"{r['pmcid']}-g{i + 1}"
    out = config.ANNOTATION / "gold_50.csv"
    df.to_csv(out, index=False)
    sample_path = config.ANNOTATION / "sample_50.csv"
    missing: list[str] = []
    if sample_path.is_file():
        sampled = set(pd.read_csv(sample_path)["pmcid"])
        missing = sorted(sampled - set(df["pmcid"]))
    with_values = df[df["value"].notna()]["pmcid"].nunique()
    print(
        f"{len(df)} rows over {df['pmcid'].nunique()} papers ({with_values} with values) -> {out}; "
        f"missing: {', '.join(missing) if missing else 'none'}; "
        f"superseded: {', '.join(sorted(set(superseded))) if superseded else 'none'}"
    )
    return 1 if missing else 0


def cmd_sample(args: argparse.Namespace) -> int:
    articles = pd.read_parquet(config.DATA_INTERIM / "articles.parquet")
    df = articles[["pmcid", "doi", "year", "journal", "methods_source"]].copy()
    df["year_band"] = df["year"].map(_band)
    df = df[df["year_band"].notna()].sort_values("pmcid").reset_index(drop=True)
    rng = np.random.RandomState(args.seed)
    bands = [b[0] for b in YEAR_BANDS]

    def take(frame: pd.DataFrame, n: int) -> pd.DataFrame:
        per = n // len(bands)
        extra = n - per * len(bands)
        parts = []
        for i, band in enumerate(bands):
            pool = frame[frame.year_band == band]
            k = min(len(pool), per + (1 if i < extra else 0))
            if k:
                parts.append(pool.sample(n=k, random_state=rng))
        return pd.concat(parts) if parts else frame.iloc[0:0]

    dev = take(df, args.dev)
    rest = df[~df.pmcid.isin(dev.pmcid)]
    sample = take(rest, args.n)
    config.ANNOTATION.mkdir(parents=True, exist_ok=True)
    dev.to_csv(config.ANNOTATION / "dev_20.csv", index=False)
    sample.to_csv(config.ANNOTATION / "sample_50.csv", index=False)
    print(f"dev={len(dev)} sample={len(sample)} bands={sample.year_band.value_counts().to_dict()}")
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    gold = pd.read_csv(args.gold)
    pred_path = Path(args.pred) if args.pred else config.DATA_PROCESSED / "zeta_table.parquet"
    pred = pd.read_parquet(pred_path)
    if "evidence_verified" in pred.columns and not args.include_unverified:
        pred = pred[pred["evidence_verified"].astype(bool)]
    report = evaluate.evaluate(pred, gold)
    config.OUT_TABLES.mkdir(parents=True, exist_ok=True)
    evaluate.write_precision_recall(report, config.OUT_TABLES / "d1_precision_recall.csv")
    config.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    (config.DATA_PROCESSED / "evaluation.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report["headline"], indent=2))
    print(json.dumps(report["audit"], indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m mnp.extract")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--model", default=None)
    r.add_argument("--concurrency", type=int, default=4)
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--no-retry-errors", dest="retry_errors", action="store_false")
    r.set_defaults(fn=cmd_run, retry_errors=True)
    sh = sub.add_parser("show")
    sh.add_argument("--pmcid", required=True)
    sh.add_argument("--no-system", action="store_true")
    sh.set_defaults(fn=cmd_show)
    ing = sub.add_parser("ingest")
    ing.add_argument("--pmcid", required=True)
    ing.add_argument("--json", required=True)
    ing.add_argument("--model", default="claude-code")
    ing.add_argument(
        "--brief",
        default=None,
        help="the brief this judgement was made under; its hash is stored on the record",
    )
    ing.add_argument(
        "--no-brief",
        action="store_true",
        help="record with no brief — for re-ingesting legacy rows, and said out loud",
    )
    ing.add_argument("--run-id", default=None, help="record this ingest in a run manifest")
    ing.add_argument("--worker", default=None, help="who produced it, for the run's assignments")
    ing.add_argument(
        "--dry-run",
        action="store_true",
        help="verify and print the same feedback, record nothing: a re-read control's ingest",
    )
    ing.set_defaults(fn=cmd_ingest)
    td = sub.add_parser("todo")
    td.add_argument("--limit", type=int, default=0)
    td.add_argument(
        "--with-values",
        action="store_true",
        help="only papers where the scanner finds a printed value",
    )
    td.add_argument(
        "--missing-brief",
        action="store_true",
        help="papers whose record carries no brief hash — the sweep's work list",
    )
    td.set_defaults(fn=cmd_todo)
    un = sub.add_parser("units")
    un.add_argument("--pmcid", required=True)
    un.add_argument("--json", action="store_true")
    un.set_defaults(fn=cmd_units)
    rc = sub.add_parser("recount")
    rc.add_argument(
        "--check",
        action="store_true",
        help="report stale coverage numbers and exit 1, without writing to the record",
    )
    rc.set_defaults(fn=cmd_recount)
    rv = sub.add_parser("reverify")
    rv.add_argument("--check", action="store_true", help="report stale flags, write nothing")
    rv.set_defaults(fn=cmd_reverify)
    rf = sub.add_parser("retrofit")
    rf.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change and write nothing",
    )
    rf.set_defaults(fn=cmd_retrofit)
    sub.add_parser("table").set_defaults(fn=cmd_table)
    sub.add_parser("review-measurand").set_defaults(fn=cmd_review_measurand)
    rl = sub.add_parser("review-list")
    rl.set_defaults(fn=cmd_review_list)
    au = sub.add_parser("audit-sample")
    au.add_argument("--n", type=int, default=10)
    au.add_argument("--seed", type=int, default=20260912)
    au.set_defaults(fn=cmd_audit_sample)
    gm = sub.add_parser("gold-merge")
    gm.set_defaults(fn=cmd_gold_merge)
    s = sub.add_parser("sample")
    s.add_argument("--n", type=int, default=50)
    s.add_argument("--dev", type=int, default=20)
    s.add_argument("--seed", type=int, default=20260912)
    s.set_defaults(fn=cmd_sample)
    e = sub.add_parser("evaluate")
    e.add_argument("--gold", required=True)
    e.add_argument("--pred", default=None)
    e.add_argument("--include-unverified", action="store_true")
    e.set_defaults(fn=cmd_evaluate)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
