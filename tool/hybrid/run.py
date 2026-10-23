"""Run the arms of the naive-vs-hybrid experiment and score them.

    unset VIRTUAL_ENV
    uv run --with openpyxl python tool/hybrid/run.py run --arm N0 --rep 1 [--only T1,Z1] [--jobs 3]
    uv run --with openpyxl python tool/hybrid/run.py score     # out/tables/hybrid_results.json

Each answer is one JSON file under data/interim/runs/hy-<arm>-r<rep>/<qid>.json, written once and
skipped on a re-run, so a run resumes where it stopped. Hg (no guard) and Hng (no grounding check)
reuse the hybrid run's plan and result, so each ablation removes one stage and nothing else.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from scipy.stats import binomtest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import agents  # noqa: E402
import ops  # noqa: E402
import questions  # noqa: E402

from mnp.eval import grid  # noqa: E402

RUNS = ROOT / "data/interim/runs"
OUT = ROOT / "out/tables/hybrid_results.json"
ARMS = ("N0", "N2", "H", "Hg", "Hng")


def _reply(r: grid.Reply) -> dict:
    return {
        "text": r.text,
        "model": r.model,
        "input_tokens": r.input_tokens,
        "output_tokens": r.output_tokens,
        "cost_usd": r.cost_usd,
        "ms": r.duration_ms,
    }


def _scalar(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, list) and value and all(isinstance(x, int | float) for x in value):
        return float(max(value))
    return None


def naive(q: questions.Q, closed: bool, ask=agents.ask) -> dict:
    data = "" if closed else agents.packet(q.packet)
    r = ask(agents.naive_prompt(q.text, data))
    allowed = agents.numbers_in(q.text) + agents.numbers_in(data)
    ans = agents.parse(r.text)
    grounded = None if closed or ans is None else agents.ungrounded(ans, allowed)
    return {"calls": [_reply(r)], "answer": ans, "ungrounded": grounded}


def hybrid(q: questions.Q, ask=agents.ask) -> dict:
    """Plan, validate, execute, guard, compose, check grounding. Code sets value and verdict."""
    calls, rec = [], {}
    r = ask(agents.planner_prompt(q.text))
    calls.append(_reply(r))
    raw = agents.parse(r.text) or {}
    plan = ops.Plan(str(raw.get("op", "")), dict(raw.get("args") or {}))
    problems = plan.validate()
    if problems:
        r = ask(
            agents.planner_prompt(q.text) + "\n\nYour plan was rejected: " + "; ".join(problems)
        )
        calls.append(_reply(r))
        raw = agents.parse(r.text) or {}
        plan = ops.Plan(str(raw.get("op", "")), dict(raw.get("args") or {}))
        problems = plan.validate()
    rec["plan"] = {
        "op": plan.op,
        "args": plan.args,
        "problems": problems,
        "matches_ref": plan.op == q.ref_plan["op"],
    }
    if problems:
        return rec | {"calls": calls, "abstained": "invalid plan", "answer": None}
    try:
        result = ops.execute(plan)
    except Exception as exc:  # noqa: BLE001 - an operation that fails is an abstention, counted
        return rec | {
            "calls": calls,
            "abstained": f"{type(exc).__name__}: {exc}"[:200],
            "answer": None,
        }
    verdict, reasons = ops.guard(plan, result)
    rj = ops.to_json(result)
    allowed = result.numbers() + agents.numbers_in(q.text)
    rec |= {"result": json.loads(rj), "guard": {"verdict": verdict, "reasons": reasons}}

    for variant, given in (("H", verdict), ("Hg", None)):
        r = ask(agents.composer_prompt(q.text, rj, given, reasons if given else []))
        calls.append(_reply(r))
        draft = agents.parse(r.text)
        bad = agents.ungrounded(draft, allowed) if draft else ["unparsed"]
        final = draft
        if draft is None or bad:
            retry = f"\n\nThese numbers are not in RESULT or the question: {bad}. Rewrite."
            r = ask(agents.composer_prompt(q.text, rj, given, reasons if given else []) + retry)
            calls.append(_reply(r))
            final = agents.parse(r.text)
            if final is None or agents.ungrounded(final, allowed):
                final = {  # only the text is replaced; the composer's verdict still stands
                    "value": None,
                    "verdict": (draft or {}).get("verdict"),
                    "caveats": (draft or {}).get("caveats") or [],
                    "answer": "(templated: the composer's text was not grounded)",
                }
        value = _scalar(final.get("value"))
        if value is None or agents.ungrounded({"value": value}, allowed):
            value = _scalar(result.value)
        if variant == "H":  # code decides the verdict; the model only phrases it
            final = final | {"value": value, "verdict": verdict, "caveats": reasons}
        else:
            final = final | {"value": value}
        rec[variant] = {"draft": draft, "draft_ungrounded": bad if draft else None, "final": final}
    rec["calls"] = calls
    rec["answer"] = rec["H"]["final"]
    return rec


def derive(rec: dict, arm: str) -> dict:
    """Hg and Hng from a hybrid record: the same plan and result, one stage removed."""
    if rec.get("answer") is None:
        return {"answer": None, "abstained": rec.get("abstained"), "calls": []}
    if arm == "Hg":
        return {"answer": rec["Hg"]["final"], "calls": [], "ungrounded": []}
    draft = rec["H"]["draft"] or {}
    guard = rec["guard"]
    return {
        "answer": draft | {"verdict": guard["verdict"], "caveats": guard["reasons"]},
        "calls": [],
        "ungrounded": rec["H"]["draft_ungrounded"] or [],
    }


def path(arm: str, rep: int, qid: str) -> Path:
    return RUNS / f"hy-{arm}-r{rep}" / f"{qid}.json"


def run(arm: str, rep: int, only: set[str] | None, jobs: int) -> None:
    qs = [q for q in questions.read() if not only or q.qid in only]

    def one(q: questions.Q) -> str:
        p = path(arm, rep, q.qid)
        if p.is_file():
            return "kept"
        try:
            if arm in ("N0", "N2"):
                rec = naive(q, closed=arm == "N0")
            elif arm == "H":
                rec = hybrid(q)
            else:
                src = path("H", rep, q.qid)
                if not src.is_file():
                    return "needs H"
                rec = derive(json.loads(src.read_text()), arm)
        except grid.ReaderError as exc:
            return f"error {exc}"[:120]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(rec | {"qid": q.qid, "arm": arm, "rep": rep}, indent=1, default=float),
            encoding="utf-8",
        )
        return "ok"

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        for q, status in zip(qs, pool.map(one, qs), strict=True):
            print(arm, rep, q.qid, status, flush=True)


# -- scoring -----------------------------------------------------------------------------------


def score_one(q: questions.Q, rec: dict) -> dict:
    a = rec.get("answer") or {}
    value = _scalar(a.get("value"))
    tol_abs = q.meta.get("tolerance_abs")
    if q.truth is None or (q.tolerance == 0 and tol_abs is None):
        value_ok = None
    elif value is None:
        value_ok = False
    elif tol_abs is not None:
        value_ok = abs(value - q.truth) <= tol_abs
    else:
        value_ok = abs(value - q.truth) <= q.tolerance * abs(q.truth)
    verdict = a.get("verdict")
    flagged_ok = (verdict in ("caveat", "refuse")) == (q.verdict != "allow") if verdict else False
    caveat_ok = (q.caveat in (a.get("caveats") or [])) if q.caveat else None
    correct = bool(flagged_ok and value_ok is not False and caveat_ok is not False)
    calls = rec.get("calls") or []
    return {
        "qid": q.qid,
        "family": q.family,
        "adversarial": q.adversarial,
        "flag_required": q.verdict != "allow",
        "parsed": bool(a),
        "value_ok": value_ok,
        "verdict_exact": verdict == q.verdict,
        "flagged_ok": flagged_ok,
        "caveat_ok": caveat_ok,
        "correct": correct,
        "ungrounded": len(rec["ungrounded"]) if isinstance(rec.get("ungrounded"), list) else None,
        "input_tokens": sum(c["input_tokens"] for c in calls),
        "output_tokens": sum(c["output_tokens"] for c in calls),
        "seconds": sum(c["ms"] for c in calls) / 1000,
        "plan_matches_ref": (rec.get("plan") or {}).get("matches_ref"),
    }


def _mean(xs) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(float(np.mean(xs)), 3) if xs else None


def mcnemar(a: list[bool], b: list[bool]) -> dict:
    """Exact McNemar on paired outcomes: how often one arm is right where the other is wrong."""
    only_a = sum(x and not y for x, y in zip(a, b, strict=True))
    only_b = sum(y and not x for x, y in zip(a, b, strict=True))
    n = only_a + only_b
    p = binomtest(only_a, n, 0.5).pvalue if n else 1.0
    return {"only_this_right": only_a, "only_H_right": only_b, "p": round(float(p), 4)}


def _numbers(x) -> list[float]:
    if isinstance(x, bool):
        return []
    if isinstance(x, int | float):
        return [float(x)]
    if isinstance(x, dict):
        return [n for y in x.values() for n in _numbers(y)]
    if isinstance(x, list):
        return [n for y in x for n in _numbers(y)]
    return []


def _final_ungrounded(q: questions.Q, arm: str, rep: int) -> list[float]:
    """Numbers in a hybrid answer's final text that the stored result does not hold."""
    h = json.loads(path("H", rep, q.qid).read_text())
    res = h["result"]
    allowed = _numbers({k: v for k, v in res.items() if k != "provenance"})
    allowed += agents.numbers_in(q.text)
    return agents.ungrounded(h[arm]["final"], allowed)


def score() -> dict:
    qs = {q.qid: q for q in questions.read()}
    rows = []
    for d in sorted(RUNS.glob("hy-*-r*")):
        arm, rep = d.name.split("-")[1], int(d.name.split("-r")[-1])
        if rep == 0:  # the pilot: seen while building, never scored
            continue
        for f in sorted(d.glob("*.json")):
            rec = json.loads(f.read_text())
            if rec["qid"] not in qs:
                continue
            if arm in ("H", "Hg") and rec.get("answer"):
                rec = rec | {"ungrounded": _final_ungrounded(qs[rec["qid"]], arm, rep)}
            rows.append({"arm": arm, "rep": rep} | score_one(qs[rec["qid"]], rec))
    out = {"questions": len(qs), "adversarial": sum(q.adversarial for q in qs.values()), "arms": {}}
    for arm in ARMS:
        r = [x for x in rows if x["arm"] == arm]
        if not r:
            continue
        adv = [x for x in r if x["adversarial"]]
        out["arms"][arm] = {
            "answers": len(r),
            "reps": sorted({x["rep"] for x in r}),
            "correct": _mean(x["correct"] for x in r),
            "correct_adversarial": _mean(x["correct"] for x in adv),
            "correct_flag_required": _mean(x["correct"] for x in r if x["flag_required"]),
            "correct_no_flag": _mean(x["correct"] for x in r if not x["flag_required"]),
            "value_ok": _mean(x["value_ok"] for x in r),
            "flagged_ok": _mean(x["flagged_ok"] for x in r),
            "caveat_named": _mean(x["caveat_ok"] for x in r),
            "ungrounded_numbers_per_answer": _mean(x["ungrounded"] for x in r),
            "input_tokens_per_q": _mean(x["input_tokens"] for x in r),
            "seconds_per_q": _mean(x["seconds"] for x in r),
            "plan_matches_ref": _mean(x["plan_matches_ref"] for x in r),
        }
    h = {(x["qid"], x["rep"]): x["correct"] for x in rows if x["arm"] == "H"}
    for arm in out["arms"]:
        if arm == "H":
            continue
        paired = [
            (x["correct"], h[(x["qid"], x["rep"])])
            for x in rows
            if x["arm"] == arm and (x["qid"], x["rep"]) in h
        ]
        if paired:
            out["arms"][arm]["vs_H"] = mcnemar([p[0] for p in paired], [p[1] for p in paired])
    stab = {}
    for arm in ARMS:
        by_q: dict[str, list[bool]] = {}
        for x in rows:
            if x["arm"] == arm:
                by_q.setdefault(x["qid"], []).append(x["correct"])
        multi = [v for v in by_q.values() if len(v) > 1]
        if multi:
            stab[arm] = round(sum(len(set(v)) == 1 for v in multi) / len(multi), 3)
    out["stability_same_outcome_across_reps"] = stab
    out["per_question"] = rows
    OUT.write_text(json.dumps(out, indent=1, default=float) + "\n", encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["run", "score"])
    ap.add_argument("--arm", choices=ARMS)
    ap.add_argument("--rep", type=int, default=1)
    ap.add_argument("--only")
    ap.add_argument("--jobs", type=int, default=3)
    a = ap.parse_args()
    if a.what == "run":
        run(a.arm, a.rep, set(a.only.split(",")) if a.only else None, a.jobs)
    else:
        s = score()
        print(json.dumps({k: v for k, v in s.items() if k != "per_question"}, indent=1))


if __name__ == "__main__":
    main()
