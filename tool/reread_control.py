"""How reproducible is one reading of a paper? Score the 2026-10-02 re-read control.

30 papers the Methods fix did not touch (seed 20261002, `data/interim/worklists/
reread_control_20261002.txt`) were each read twice, blind, by claude-code:sonnet under the
current brief: readings A and B in `data/interim/reread_control/`. Neither was recorded; ingest
ran with --dry-run. This compares A with B (the noise of reading), and each with the recorded
extraction of the same paper (the noise plus whatever changed since: brief, model, parser).

Every reading goes through the pipeline the dataset uses: coerce, verify, then
`ExtractionRecord.to_rows`, so the rules R1–R3 apply to all three alike.

Rows are matched within a paper by (quantity, value to 0.1): a printed number identifies a
measurement. Rows with no printed value cannot be matched that way and are counted, not paired.

    uv run python tool/reread_control.py

Writes data/interim/reread_control/summary.json and prints the tables. Calls no model.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from mnp import config
from mnp.corpus import jats
from mnp.extract import zeta

CONTROL = config.DATA_INTERIM / "reread_control"
WORKLIST = config.DATA_INTERIM / "worklists" / "reread_control_20261002.txt"
CONDITIONS = (
    "medium_reported",
    "ionic_strength_reported",
    "pH_reported",
    "temperature_reported",
    "instrument_reported",
    "conditions_complete",
)


def _article(pmcid: str) -> jats.Article:
    article = jats.parse((config.EPMC_XML_DIR / f"{pmcid}.xml").read_bytes())
    article.pmcid = pmcid
    return article


def _rows(rec: zeta.ExtractionRecord, article: jats.Article) -> list[dict]:
    paper = article.full_text if any(zeta.needs_paper(m) for m in rec.measurements) else None
    return rec.to_rows(paper)


def _reading(pmcid: str, label: str, article: jats.Article) -> list[dict]:
    data = json.loads((CONTROL / f"{label}-{pmcid}.json").read_text())
    return _rows(zeta.extract_from_payload(article, data, "claude-code:sonnet"), article)


def _recorded() -> dict[str, zeta.ExtractionRecord]:
    path = config.DATA_INTERIM / "extractions.jsonl"
    return {
        rec.pmcid: rec
        for rec in (zeta.ExtractionRecord.from_json(x) for x in path.read_text().splitlines())
    }


def _key(row: dict) -> tuple[str, float] | None:
    return None if row["value"] is None else (row["quantity"], round(float(row["value"]), 1))


def _pairs(a: list[dict], b: list[dict]) -> list[tuple[dict, dict]]:
    """Rows of a and b with the same (quantity, value), each used once, in table order."""
    pool: dict[tuple, list[dict]] = {}
    for row in b:
        if (k := _key(row)) is not None:
            pool.setdefault(k, []).append(row)
    out = []
    for row in a:
        if (k := _key(row)) is not None and pool.get(k):
            out.append((row, pool[k].pop(0)))
    return out


def _share(rows: list[dict], c: str) -> float | None:
    return sum(bool(r[c]) for r in rows) / len(rows) if rows else None


def compare(x: dict[str, list[dict]], y: dict[str, list[dict]]) -> dict:
    papers = sorted(x)
    pairs = [p for pmcid in papers for p in _pairs(x[pmcid], y[pmcid])]
    valued = sum(1 for pmcid in papers for r in x[pmcid] if _key(r) is not None)
    per_condition = {}
    for c in CONDITIONS:
        diffs = [
            abs(_share(x[p], c) - _share(y[p], c))
            for p in papers
            if x[p] and y[p]
        ]
        any_same = sum(
            1 for p in papers if any(r[c] for r in x[p]) == any(r[c] for r in y[p])
        )
        per_condition[c] = {
            "row_pairs_agreeing": sum(1 for a, b in pairs if bool(a[c]) == bool(b[c])),
            "paper_mean_abs_share_difference": sum(diffs) / len(diffs) if diffs else None,
            "papers_agreeing_on_any_row": any_same,
        }
    return {
        "papers": len(papers),
        "papers_same_row_count": sum(1 for p in papers if len(x[p]) == len(y[p])),
        "papers_both_with_rows_or_both_without": sum(
            1 for p in papers if bool(x[p]) == bool(y[p])
        ),
        "rows": [sum(len(x[p]) for p in papers), sum(len(y[p]) for p in papers)],
        "valued_rows_in_first": valued,
        "row_pairs_matched_by_value": len(pairs),
        "per_condition": per_condition,
    }


def rates(readings: dict[str, list[dict]]) -> dict:
    rows = [r for rs in readings.values() for r in rs]
    with_rows = [rs for rs in readings.values() if rs]
    return {
        c: {
            "per_row": _share(rows, c),
            "per_paper": sum(_share(rs, c) for rs in with_rows) / len(with_rows),
        }
        for c in CONDITIONS
    } | {"rows": len(rows), "papers_with_rows": len(with_rows)}


def main() -> int:
    pmcids = [
        line.split()[0]
        for line in WORKLIST.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    recorded = _recorded()
    a, b, r = {}, {}, {}
    for pmcid in pmcids:
        article = _article(pmcid)
        a[pmcid] = _reading(pmcid, "A", article)
        b[pmcid] = _reading(pmcid, "B", article)
        r[pmcid] = _rows(recorded[pmcid], article)
    summary = {
        "papers": pmcids,
        "recorded_models": dict(Counter(recorded[p].model for p in pmcids)),
        "recorded_briefs": dict(
            Counter((recorded[p].brief_sha256 or "none")[:12] for p in pmcids)
        ),
        "rates": {"A": rates(a), "B": rates(b), "recorded": rates(r)},
        "A_vs_B": compare(a, b),
        "A_vs_recorded": compare(a, r),
        "B_vs_recorded": compare(b, r),
    }
    (CONTROL / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    print("| condition | A per row / per paper | B | recorded |")
    print("|---|---|---|---|")
    for c in CONDITIONS:
        cells = [
            f"{100 * summary['rates'][k][c]['per_row']:.1f} / "
            f"{100 * summary['rates'][k][c]['per_paper']:.1f}"
            for k in ("A", "B", "recorded")
        ]
        print(f"| {c} | " + " | ".join(cells) + " |")
    print(
        "| rows (papers with rows) | "
        + " | ".join(
            f"{summary['rates'][k]['rows']} ({summary['rates'][k]['papers_with_rows']})"
            for k in ("A", "B", "recorded")
        )
        + " |"
    )
    for name in ("A_vs_B", "A_vs_recorded", "B_vs_recorded"):
        s = summary[name]
        n = s["row_pairs_matched_by_value"]
        print(
            f"\n{name}: same row count in {s['papers_same_row_count']}/{s['papers']} papers, "
            f"rows {s['rows'][0]} vs {s['rows'][1]}, {n} of {s['valued_rows_in_first']} "
            "valued rows matched by value"
        )
        for c, v in s["per_condition"].items():
            d = v["paper_mean_abs_share_difference"]
            print(
                f"  {c:26s} matched rows agree {v['row_pairs_agreeing']}/{n}; "
                f"papers agree on 'any row' {v['papers_agreeing_on_any_row']}/{s['papers']}; "
                f"mean |share difference| per paper {100 * d:.1f} pp"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
