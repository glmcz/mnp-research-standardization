"""The four gates from ARCHITECTURE_PLAN.md §6, as one runner.

Depth-first: a persona goes through these in order and only widens to the corpus once gate 3
passes. Each gate answers a different question, and the cheap ones come first.

    1 contract — did it honour its contract at all?
    2 edge     — does its judgement match the human answer key?
    3 gold     — how does it score against ground truth?
    4 pilot    — what does it cost at scale?

A gate that cannot be evaluated reports `passed: None`. It never reports success, and it
never blocks on something that was simply not supplied.
"""

from __future__ import annotations

import json
from pathlib import Path

from mnp import config


def _load(store: str | Path) -> dict[str, dict]:
    path = Path(store)
    if not path.is_file():
        return {}
    out = {}
    for line in path.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            out[r["pmcid"]] = r
    return out


def contract(store: str | Path, pmcids: list[str]) -> dict:
    """Gate 1 — did the persona do the work, record its brief, and verify its evidence?

    This is where a worker that delegated and did nothing fails: its papers have no record,
    whatever its report said.
    """
    records = _load(store)
    mine = {p: records[p] for p in pmcids if p in records}
    missing = [p for p in pmcids if p not in records]
    reasons: list[str] = []

    if missing:
        reasons.append(f"{len(missing)} claimed papers have no record: {', '.join(missing[:5])}")
    untraceable = [p for p, r in mine.items() if not r.get("brief_sha256")]
    if untraceable:
        reasons.append(f"{len(untraceable)} records are untraceable (no brief hash)")
    errored = [p for p, r in mine.items() if r.get("error")]
    if errored:
        reasons.append(f"{len(errored)} records carry an error")
    unverified = [
        p
        for p, r in mine.items()
        for m in r.get("measurements", [])
        if not (m.get("evidence") or {}).get("verified")
    ]
    if unverified:
        reasons.append(f"{len(set(unverified))} records contain an unverified row")

    return {
        "gate": "1 contract",
        "passed": not reasons,
        "records": len(mine),
        "missing": missing,
        "untraceable": untraceable,
        "reasons": reasons,
    }


def pilot(store: str | Path, pmcids: list[str]) -> dict:
    """Gate 4 — what the run costs and yields, so a configuration can be compared."""
    records = _load(store)
    mine = [records[p] for p in pmcids if p in records]
    rows = sum(len(r.get("measurements", [])) for r in mine)
    with_rows = sum(1 for r in mine if r.get("measurements"))
    flagged = sum(1 for r in mine for f in r.get("row_flags", []) if f)
    covered = [r["n_candidates_matched"] / r["n_candidates"] for r in mine if r.get("n_candidates")]
    return {
        "gate": "4 pilot",
        "passed": None,  # descriptive: a cost report has no pass mark
        "papers": len(mine),
        "rows": rows,
        "papers_with_rows": with_rows,
        "rows_per_paper": rows / len(mine) if mine else None,
        "flagged_rows": flagged,
        "mean_coverage": sum(covered) / len(covered) if covered else None,
    }


def run_all(
    store: str | Path | None = None,
    pmcids: list[str] | None = None,
    key_path: str | Path | None = None,
    persona_answers: dict[str, str] | None = None,
    gold=None,
    pred=None,
) -> dict:
    """Every gate, in order, reporting all of them rather than stopping at the first failure."""
    from mnp.report import edge
    from mnp.report import gate as gate3

    store = store or config.DATA_INTERIM / "extractions.jsonl"
    pmcids = pmcids or []
    results = [contract(store, pmcids)]

    if key_path and persona_answers is None:
        # Nobody asked the persona. A silent persona is a disagreement (edge.score says so),
        # but a persona that was never questioned has not failed anything — scoring {} here
        # turned three newly answered key cases into a fabricated 0% FAIL.
        key = edge.load_key(key_path)
        answered = sum(1 for v in key.values() if edge.canon((v or {}).get("verdict")))
        results.append({
            "gate": "2 edge", "passed": None, "answered": answered, "scored": False,
            "reason": f"no persona verdicts supplied; the key holds {answered} answered case(s)",
        })  # fmt: skip
    elif key_path:
        e = edge.score(key_path, persona_answers)
        results.append({"gate": "2 edge", "passed": e["scored"] and e["agreement"] == 1.0, **e})
        if not e["scored"]:
            results[-1]["passed"] = None
    else:
        results.append({"gate": "2 edge", "passed": None, "reason": "no answer key given"})

    if gold is not None and pred is not None:
        g = gate3.run(pred, gold, store=store)
        results.append({"gate": "3 gold", "passed": g["passed"], **g})
    else:
        results.append({"gate": "3 gold", "passed": None, "reason": "no gold set given"})

    results.append(pilot(store, pmcids))
    decided = [g["passed"] for g in results if g["passed"] is not None]
    return {"gates": results, "passed": all(decided) if decided else None}


def markdown(result: dict) -> str:
    lines = ["# Evaluation gates", ""]
    for g in result["gates"]:
        mark = {True: "PASS", False: "**FAIL**", None: "not evaluated"}[g["passed"]]
        lines.append(f"## Gate {g['gate']} — {mark}")
        lines.append("")
        for key in ("records", "papers", "rows", "rows_per_paper", "mean_coverage",
                    "answered", "agreement", "reason"):  # fmt: skip
            if key in g and g[key] is not None:
                value = round(g[key], 3) if isinstance(g[key], float) else g[key]
                lines.append(f"- {key.replace('_', ' ')}: {value}")
        for reason in g.get("reasons", []):
            lines.append(f"- **{reason}**")
        lines.append("")
    return "\n".join(lines)
