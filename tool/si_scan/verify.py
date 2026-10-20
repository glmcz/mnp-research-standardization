"""Accept or reject each reader verdict with the main pipeline's own checks, then recount how often
ionic strength is reported once the SI counts.

A verdict is {pmcid, row_id, verdict, mM, file, quote, note}. Only two verdicts are claims:
"is_stated" (the SI calls the number an ionic strength) and "salt_composition" (it names salts at
molar concentrations, RC-02). The rest (buffer_only, di_water_only, mass_units_composition,
other_step, series_unmapped, nothing) are kept as findings and never counted, though a quoted
finding must still be verbatim. series_unmapped marks a paper whose SI states the ionic strength
of its zeta liquid, but where a main-table row lumps several levels or media: it feeds the upper
bound only. A claim is accepted only if
  1. the quote is verbatim in that SI file (folded as scan.flatten folds the SI),
  2. mM > 0 (RC-08: 0 mM is unreported),
  3. the quote prints it: `zeta._ionic_number_in` for a stated value, `parse_ionic_strength`
     for one derived from a named salt (RC-02),
  4. a stated value is not a buffer's concentration (`coerce.buffer_concentration`, RC-10).
The reader proposes; this script decides.

Usage: python -I verify.py <d1_zeta_table.csv> <si_text_dir> <verdicts.jsonl> <out_dir>

The checked verdicts quote the SI and stay in <out_dir> (gitignored). The counts, with the ids of
the accepted rows, go to out/tables/si_rates.json, which the deck reads.
"""

import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from mnp import config
from mnp.extract import coerce, zeta

CLAIMS = {"is_stated", "salt_composition"}
UNIT_DOT = re.compile(r"(mol|g)\s*[·⋅•]\s*(?=L)")


def fold(s: str) -> str:
    """scan.flatten, repeated here because python -I keeps this directory off sys.path."""
    return UNIT_DOT.sub(r"\1 ", re.sub(r"\s+", " ", s)).strip()


def quote_in_si(v: dict, text_dir: Path) -> bool:
    path = text_dir / v["pmcid"] / v["file"]
    quote = fold(v["quote"])
    return bool(v["file"]) and path.is_file() and bool(quote) and quote in fold(path.read_text())


def check(v: dict, text_dir: Path) -> str:
    if not (text_dir / v["pmcid"] / v["file"]).is_file():
        return "rejected:no_such_file"
    if not quote_in_si(v, text_dir):
        return "rejected:quote_not_in_si"
    quote = fold(v["quote"])
    mM = float(v["mM"])
    if mM <= 0:
        return "rejected:zero_is_unreported"
    if v["verdict"] == "salt_composition":
        derived = coerce.parse_ionic_strength(quote)[0]
        if not (
            derived is not None and abs(derived - mM) <= 1e-6 * max(1.0, mM)
        ) and not coerce.ionic_concentration_in(quote, mM):
            return "rejected:not_derivable_from_quote"
        return "accepted"
    if not zeta._ionic_number_in(mM, quote):
        return "rejected:value_not_in_quote"
    if coerce.buffer_concentration(quote, mM):
        return "rejected:buffer_concentration"
    return "accepted"


def main() -> None:
    table, text_dir, verdicts_path, out = map(Path, sys.argv[1:5])
    with table.open() as fh:
        rows = list(csv.DictReader(fh))
    verdicts = [json.loads(line) for line in verdicts_path.read_text().splitlines() if line.strip()]
    known = {r["row_id"]: r for r in rows}
    for v in verdicts:
        if v["verdict"] not in CLAIMS:
            v["outcome"] = "finding"
            if v.get("quote") and not quote_in_si(v, text_dir):
                v["outcome"] = "finding:quote_not_in_si"
        elif v["row_id"] not in known or known[v["row_id"]]["pmcid"] != v["pmcid"]:
            v["outcome"] = "rejected:unknown_row"
        elif known[v["row_id"]]["ionic_strength_reported"] == "True":
            v["outcome"] = "rejected:already_reported_in_main_text"
        else:
            v["outcome"] = check(v, text_dir)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "si_verdicts_checked.jsonl").open("w") as fh:
        for v in verdicts:
            fh.write(json.dumps(v, ensure_ascii=False) + "\n")

    si_rows = {v["row_id"] for v in verdicts if v["outcome"] == "accepted"}
    by_paper = defaultdict(list)
    for r in rows:
        by_paper[r["pmcid"]].append(r)

    def rates(with_si: bool) -> dict:
        def rep(r: dict) -> bool:
            return r["ionic_strength_reported"] == "True" or (with_si and r["row_id"] in si_rows)

        per_row = sum(rep(r) for r in rows)
        any_paper = sum(any(rep(r) for r in rs) for rs in by_paper.values())
        mean_share = sum(sum(rep(r) for r in rs) / len(rs) for rs in by_paper.values()) / len(
            by_paper
        )
        return dict(
            rows=per_row,
            rows_pct=100 * per_row / len(rows),
            papers_any=any_paper,
            papers_any_pct=100 * any_paper / len(by_paper),
            paper_mean_pct=100 * mean_share,
        )

    claimed = {known[r]["pmcid"] for r in si_rows}
    series = {v["pmcid"] for v in verdicts if v["verdict"] == "series_unmapped"}
    main_papers = {
        p for p, rs in by_paper.items() if any(r["ionic_strength_reported"] == "True" for r in rs)
    }
    upper = main_papers | claimed | series
    findings = defaultdict(set)
    for v in verdicts:
        if v["outcome"].startswith("finding") and v["verdict"] not in ("nothing", "done"):
            findings[v["verdict"]].add(v["pmcid"])
    summary = dict(
        n_rows=len(rows),
        n_papers=len(by_paper),
        papers_read=len({v["pmcid"] for v in verdicts}),
        verdicts=len(verdicts),
        accepted=len(si_rows),
        accepted_rows=sorted(si_rows),
        accepted_papers=len(claimed),
        accepted_papers_new=len(claimed - main_papers),
        findings_papers={k: len(v) for k, v in sorted(findings.items())},
        upper_bound_papers_any=len(upper),
        upper_bound_papers_any_pct=100 * len(upper) / len(by_paper),
        outcomes={
            k: sum(v["outcome"] == k for v in verdicts)
            for k in sorted({v["outcome"] for v in verdicts})
        },
        main_text=rates(False),
        main_plus_si=rates(True),
    )
    (config.OUT_TABLES / "si_rates.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
