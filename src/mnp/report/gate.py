"""Score an extraction against the gold set and decide pass/fail.

`ARCHITECTURE_PLAN.md` §6 defines gates that must pass before a corpus run. A gate that has
to be assembled by hand each time is a gate that quietly stops being run, so it is a command.

Two rules matter more than the thresholds:

- a field the gold set never exercises is **not scored**, and cannot fail the gate. The first
  gate run reported precision 0.00 for ionic strength on zero true positives, which says
  nothing about the persona and everything about the slice;
- provenance is part of the verdict. An extraction that cannot be traced to its brief is not
  a passing extraction, however well it scores.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from mnp import config
from mnp.extract import evaluate, provenance

# From ARCHITECTURE_PLAN.md §6, gate 3.
DEFAULT_THRESHOLDS = {
    "paper:medium_reported": 0.90,
    "paper:instrument_reported": 0.90,
    "row:value": 0.75,
}


def run(
    pred: pd.DataFrame,
    gold: pd.DataFrame,
    thresholds: dict[str, float] | None = None,
    store: str | Path | None = None,
) -> dict:
    """Score `pred` against `gold`; every threshold is on precision."""
    thresholds = DEFAULT_THRESHOLDS if thresholds is None else thresholds
    report = evaluate.evaluate(pred, gold)
    by_field = {f"{r['level']}:{r['field']}": r for r in report["row"] + report["paper"]}

    checks = []
    for field, floor in thresholds.items():
        row = by_field.get(field)
        if row is None:
            checks.append({"field": field, "passed": None, "reason": "field not scored"})
            continue
        scored = row["tp"] + row["fn"] > 0
        observed = row["precision"]
        if not scored or observed != observed:  # no ground truth, or precision is NaN
            checks.append(
                {"field": field, "passed": None, "reason": "no ground truth",
                 "tp": row["tp"], "fp": row["fp"], "fn": row["fn"]}
            )  # fmt: skip
            continue
        checks.append(
            {"field": field, "passed": bool(observed >= floor), "threshold": floor,
             "observed": round(observed, 3), "tp": row["tp"], "fp": row["fp"], "fn": row["fn"]}
        )  # fmt: skip

    store = Path(store) if store else config.DATA_INTERIM / "extractions.jsonl"
    prov = provenance.audit(store)
    return {
        "passed": all(c["passed"] is not False for c in checks),
        "checks": checks,
        "papers": report["papers"],
        "provenance": prov,
        "evaluation": report,
    }


def markdown(result: dict) -> str:
    verdict = "PASS" if result["passed"] else "FAIL"
    lines = [
        f"# Gate result: **{verdict}**",
        "",
        f"Scored on {result['papers']['gold']} annotated papers "
        f"({result['papers'].get('pred_outside_gold', 0)} predictions outside the gold set "
        "were not scored).",
        "",
        "| Field | threshold | observed | tp | fp | fn | verdict |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in result["checks"]:
        if c["passed"] is None:
            lines.append(
                f"| `{c['field']}` | — | — | {c.get('tp', 0)} | {c.get('fp', 0)} "
                f"| {c.get('fn', 0)} | not scored ({c['reason']}) |"
            )
        else:
            mark = "pass" if c["passed"] else "**fail**"
            lines.append(
                f"| `{c['field']}` | {c['threshold']:.2f} | {c['observed']:.3f} | {c['tp']} "
                f"| {c['fp']} | {c['fn']} | {mark} |"
            )
    p = result["provenance"]
    lines += [
        "",
        f"Provenance: {p['records'] - p['untraceable']} of {p['records']} records carry a "
        f"brief hash.",
    ]
    if p["untraceable"]:
        shown = ", ".join(p["untraceable_pmcids"][:10])
        lines.append(f"**{p['untraceable']} records cannot be traced to their brief**: {shown}")
    return "\n".join(lines) + "\n"


def write(result: dict, out_dir: str | Path) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "gate.json").write_text(json.dumps(result["checks"], indent=2) + "\n")
    path = out / "gate.md"
    path.write_text(markdown(result))
    return path
