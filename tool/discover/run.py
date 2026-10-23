"""The dataset search agent: catalogue search, a code filter, Claude's triage, code verification.

    unset VIRTUAL_ENV
    uv run --with openpyxl python tool/discover/run.py search   # candidates, filtered (no model)
    uv run --with openpyxl python tool/discover/run.py all      # + triage + verify
    # out/tables/dataset_candidates.csv: every candidate, the stage it reached, and why it stopped

Stages, each recorded per candidate:
  1. found        DataCite datasets for the queries in catalog.QUERIES
  2. on_topic     code: the record is about micro- or nanoplastic
  3. triaged      Claude reads the record (kind, matrix, coordinates, dates, size window, tables)
  4. to_verify    a rule over the triage, not the model, picks what to open
  5. verified     code opens the files: usable | partial | not_usable | no_table | not_verifiable
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tool" / "p2"))
import build as p2  # noqa: E402
import catalog  # noqa: E402
import triage  # noqa: E402
import verify  # noqa: E402

OUT = ROOT / "out/tables/dataset_candidates.csv"
SUMMARY = ROOT / "out/tables/dataset_search.json"


def ncei_dois() -> set[str]:
    d = pd.read_csv(p2.NCEI, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    return {x.lower().removeprefix("https://doi.org/").strip() for x in d["DOI"] if x.strip()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["search", "all"])
    ap.add_argument("--jobs", type=int, default=3)
    a = ap.parse_args()

    found = catalog.search()
    cands = [catalog.to_dict(c) for c in catalog.dedupe(found)]
    on_topic = [c for c in cands if catalog.about_plastic(catalog.Candidate(**c))]
    rows = {c["doi"]: {"doi": c["doi"], "title": c["title"], "publisher": c["publisher"],
                       "year": c["year"], "licence": c["licence"], "stage": "on_topic",
                       "queries": "; ".join(c["queries"])} for c in on_topic}  # fmt: skip
    summary = {"found": len(found), "distinct": len(cands), "on_topic": len(on_topic)}
    if a.what == "all":
        t = triage.classify(on_topic, jobs=a.jobs)
        summary["triaged"] = len(t)
        known = ncei_dois()
        picked = [c for c in on_topic if c["doi"] in t and triage.worth_verifying(t[c["doi"]])]
        summary["to_verify"] = len(picked)
        for doi, item in t.items():
            rows[doi] |= {
                "stage": "triaged",
                "kind": item.get("kind"),
                "matrix": ", ".join(item.get("matrix") or []),
                "claims": " ".join(
                    f"{k}={item.get(k)}"
                    for k in ("coordinates", "dates", "size_window", "tabular", "concentrations")
                ),
                "why": item.get("why"),
            }

        def one(c: dict) -> tuple[str, dict]:
            try:
                return c["doi"], verify.verify(c)
            except Exception as exc:  # noqa: BLE001 - a host that fails is recorded, not fatal
                return c["doi"], {"verdict": "error", "error": f"{type(exc).__name__}: {exc}"[:200]}

        with ThreadPoolExecutor(max_workers=a.jobs) as pool:
            for doi, v in pool.map(one, picked):
                c = next(x for x in picked if x["doi"] == doi)
                rows[doi] |= {
                    "stage": "verified",
                    "verdict": v["verdict"],
                    "host": v.get("host"),
                    "rows": v.get("rows"),
                    "roles": json.dumps(v.get("roles") or {}),
                    "ncei_overlap": verify.ncei_overlap(c, known),
                    "error": v.get("error"),
                }
        verdicts = pd.Series([r.get("verdict") for r in rows.values() if r.get("verdict")])
        summary["verdicts"] = verdicts.value_counts().to_dict()
        summary["usable_independent"] = sum(
            r.get("verdict") == "usable" and not r.get("ncei_overlap") for r in rows.values()
        )
    pd.DataFrame(rows.values()).to_csv(OUT, index=False)
    SUMMARY.write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
