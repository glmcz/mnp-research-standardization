"""Independent judges for the validation system: the LLM jury (design §3.4, tier 2).

Three judges from three model families, none Claude (the readers' family) and none Qwen (the base
of Nimble and Microsoft-Decision-1, tier 1). Per paper and reader, a judge sees the lines the
readers saw and each reader's explanation in one fixed format, and answers typed questions per
row: J1 do the cited lines support this cause, J2 which cause do the lines support best, J3 should
a careful reader abstain. Arithmetic is never asked of a judge: code does it.

Probes, run with the same judges:
- order: the list of causes is shuffled per call and then reversed; J2 should not move;
- persuasion: a fluent decoy explanation with a wrong cause and the reader's own citations;
- self-preference: a Claude judge (the readers' family) on Claude-written explanations;
- derivation traps from outside Q2, where the right answer needs arithmetic or a size table.

MNP_ALLOW_SIBLING_ENV=1 uv run python -m mnp.validate.judge run
uv run python -m mnp.validate.judge score
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pandas as pd

from mnp import config
from mnp.eval import grid, scoring
from mnp.extract import llm, origin
from mnp.validate import sign

#: Three families, none Claude (the readers) and none Qwen (tier 1's base). The OpenRouter account
#: had no credit on 2026-10-19: it refused gemini-3.8-flash, mistral-medium-3-5 and then
#: gpt-6-luna with HTTP 402. So the OpenAI-family judge is GPT-OSS-120B on Groq, and the other two
#: are the low-cost models OpenRouter still served.
GROQ = "groq:"
JURY = (
    "groq:openai/gpt-oss-120b",
    "google/gemini-2.5-flash-lite",
    "mistralai/mistral-small-3.2-24b-instruct",
)
CLAUDE_PROBE = grid.READER_MODEL
REASON_CHARS = 300
JUDGE_MAX_TOKENS = 1500
SYSTEM = (
    "You judge explanations written by another reader about a scientific paper, using only the "
    "lines given. Answer in the JSON contract exactly."
)
#: A wrong cause for the decoy: the one least likely to be the reader's.
DECOY_FOR = {c: ("label_error" if c != "label_error" else "corona") for c in sign.CAUSES}
DECOY_REASON = (
    "The methods make it plain that these particles were never actually amine-functionalised as "
    "labelled, so the negative charge simply reflects the true, unmodified surface, exactly as the "
    "cited lines show beyond any reasonable doubt."
)


def items_path() -> Path:
    return sign.answers_dir() / "judge_items.jsonl"


# -- prompts -------------------------------------------------------------------------------------


def _causes_in_order(seed: str, reverse: bool) -> list[str]:
    order = list(sign.CAUSES)
    random.Random(seed).shuffle(order)
    return order[::-1] if reverse else order


def _explanation(row_id: str, cause: str, reason: str, cites: Sequence[str]) -> str:
    """One fixed format for every explanation, so length and style cannot carry it."""
    reason = " ".join(str(reason).split())[:REASON_CHARS]
    return json.dumps(
        {"row_id": row_id, "cause": cause, "reason": reason, "citations": list(cites)},
        ensure_ascii=False,
    )


def judge_prompt(
    pmcid: str,
    rows: pd.DataFrame,
    ev: origin.Evidence,
    explanations: Sequence[str],
    order: Sequence[str],
) -> str:
    listed = "\n".join(sign._row_line(r) for r in rows.to_dict("records"))
    return "\n\n".join(
        [
            f"Lines from one paper, {pmcid}. Each row below is a zeta potential whose sign is the "
            "opposite of what its particle's surface group gives in clean water near neutral pH. "
            "Another reader explained each row. Judge each explanation from the lines only.",
            f"ROWS\n{listed}",
            f"LINES\n{origin.render(ev)}",
            "EXPLANATIONS\n" + "\n".join(explanations),
            "CAUSES, in no particular order: " + ", ".join(order) + ". unexplained means the lines "
            "give no reason; it is a valid answer.",
            "QUESTIONS per row\nJ1: do the cited lines support the stated cause? yes or no.\n"
            "J2: which cause do the lines support best? one of the causes above.\n"
            "J3: should a careful reader abstain, because the lines do not settle it? yes or no.",
            "OUTPUT\nExactly one JSON object: "
            '{"rows": [{"row_id": "<as listed>", "J1": "yes" | "no", '
            '"J2": "<cause>", "J3": "yes" | "no"}, ...]}',
        ]
    )


# -- the derivation traps --------------------------------------------------------------------------

TRAPS = [
    {
        "trap": "reisser_1.9",
        "lines": [
            "PAPER (Reisser et al. 2013, PLoS ONE, Results): When taking into account the effect "
            "of "
            "wind-mixing, net tow plastic concentrations increased by a mean factor of 2.8 (range: "
            "1.04 – 10.0, median = 1.9).",
            "DATA: the same 171 net tows appear twice in a database, once under Reisser 2013 and "
            "once under Eriksen 2014. Paired tow by tow, the Reisser value over the Eriksen value "
            "has a median of 1.9 when tows of the same station are paired with each other.",
            "DATA: in pieces per km², the two papers publish the same value for 168 of the 171 "
            "tows.",
            "DATA: the database divides Reisser's Manta tows by a net depth of 0.085 m and "
            "Eriksen's by 0.08 m, and keeps only particles under 5 mm for Eriksen.",
        ],
        "claim": "The 1.9-fold difference between the two database values is Reisser's wind-mixing "
        "correction, whose median is 1.9.",
        "expected_J1": "no",
    },
    {
        "trap": "clumped_beads",
        "lines": [
            "PAPER (PMC10260929, Table 1): 0.3 mM NaCl: hydrodynamic size 119.50 nm, PDI 0.050, "
            "zeta "
            "−48.70 mV; 30 mM: 133.90 nm, PDI 0.116, −43.10 mV; 100 mM: 160.80 nm, PDI 0.266, "
            "−32.40 mV; 155 mM: 250.50 nm, PDI 0.257, −31.0 mV.",
            "PAPER (PMC10260929, Results): it might be concluded that PS NPs are stable in "
            "distilled water, 0.3 and 30 mM NaCl, while they start to aggregate in NaCl with "
            "concentrations of 100 nM and above.",
        ],
        "claim": "The four zeta values are one particle measured at four salt concentrations, so "
        "together they give that particle's charge-versus-salt curve.",
        "expected_J1": "no",
    },
]


def trap_prompt(trap: Mapping[str, Any]) -> str:
    return "\n\n".join(
        [
            "LINES\n" + "\n".join(trap["lines"]),
            f"CLAIM\n{trap['claim']}",
            "QUESTION\nJ1: do the lines support the claim? yes or no.",
            'OUTPUT\nExactly one JSON object: {"J1": "yes" | "no", "why": "<one sentence>"}',
        ]
    )


# -- running ---------------------------------------------------------------------------------------


def _client(model: str) -> llm.LLMClient:
    if model.startswith(GROQ):
        from openai import OpenAI

        raw = OpenAI(
            api_key=config.require("GROQ_API_KEY"),
            max_retries=0,
            timeout=300.0,
            base_url="https://api.groq.com/openai/v1",
        )
        client = llm.LLMClient(
            raw,
            cache_dir=config.LLM_CACHE,
            chain=[model[len(GROQ) :]],
            extra_body={"reasoning_effort": "low"},
        )
        client.max_tokens = 4000  # a reasoning model spends tokens before it answers
        return client
    client = llm.from_env(chain=[model])
    # Replies are short JSON. OpenRouter reserves credit for max_tokens up front, and the client's
    # default of 16 000 made a judge fail with 402 before it read anything (2026-10-19).
    client.max_tokens = JUDGE_MAX_TOKENS
    return client


def _ask_openrouter(model: str, prompt: str) -> tuple[dict, dict]:
    for attempt in range(6):
        try:
            data, c = _client(model).complete_json(SYSTEM, prompt, temperature=0)
            break
        except llm.ParseError as exc:  # a rate limit (429) is waited out; anything else is not
            if " 429" not in str(exc) or attempt == 5:
                raise
            time.sleep(15 * (attempt + 1))
    return data, {
        "model": c.model,
        "cached": c.cached,
        "prompt_tokens": c.prompt_tokens,
        "completion_tokens": c.completion_tokens,
    }


def _ask_claude(prompt: str) -> tuple[dict, dict]:
    reply = grid.read(prompt, model=CLAUDE_PROBE)
    data = scoring.parse_answer("judge", "judge", reply.text).payload
    return data, {
        "model": reply.model,
        "cached": False,
        "prompt_tokens": reply.input_tokens,
        "completion_tokens": reply.output_tokens,
    }


def tasks(cands: pd.DataFrame, answers: Mapping[str, Mapping[str, Any]]) -> list[dict]:
    """Every judge call: (judge, paper, reader, variant). Variants: order0, order1, decoy."""
    out = []
    for pmcid, rows in cands.groupby("pmcid"):
        cited = {i for ids in rows.evidence_line_ids.dropna() for i in str(ids).split(";") if i}
        ev = sign.select(origin.load_doc(pmcid), cited)
        for reader in sign.READERS:
            parsed = sign.parse_reply(answers.get(reader, {}).get(pmcid, {}).get("text", ""))
            if not parsed:
                continue
            expl = [
                _explanation(r, e.get("cause", ""), e.get("reason", ""), e.get("citations") or [])
                for r, e in parsed.items()
                if r in set(rows.row_id)
            ]
            decoy = [
                _explanation(
                    r,
                    DECOY_FOR.get(e.get("cause"), "label_error"),
                    DECOY_REASON,
                    e.get("citations") or [],
                )
                for r, e in parsed.items()
                if r in set(rows.row_id)
            ]
            for judge in (*JURY, "claude"):
                if judge == "claude" and reader != "A":
                    continue  # the self-preference probe: Claude judging Claude's reader A
                variants = [("order0", expl, False), ("order1", expl, True)]
                if reader == "A" and judge != "claude":
                    variants.append(("decoy", decoy, False))
                for variant, ex, rev in variants:
                    order = _causes_in_order(f"{pmcid}|{reader}|{judge}", rev)
                    out.append(
                        {
                            "judge": judge,
                            "pmcid": pmcid,
                            "reader": reader,
                            "variant": variant,
                            "order": order,
                            "prompt": judge_prompt(pmcid, rows, ev, ex, order),
                        }
                    )
    for trap in TRAPS:
        for judge in (*JURY, "claude"):
            out.append(
                {
                    "judge": judge,
                    "pmcid": trap["trap"],
                    "reader": "-",
                    "variant": "trap",
                    "order": [],
                    "prompt": trap_prompt(trap),
                }
            )
    return out


def run(work: Sequence[dict], jobs: int = 6) -> dict[str, int]:
    path = items_path()
    done = set()
    if path.is_file():
        for text in path.read_text(encoding="utf-8").splitlines():
            r = json.loads(text)
            done.add((r["judge"], r["pmcid"], r["reader"], r["variant"]))
    todo = [t for t in work if (t["judge"], t["pmcid"], t["reader"], t["variant"]) not in done]

    def one(t: dict) -> str:
        try:
            data, meta = (
                _ask_claude(t["prompt"])
                if t["judge"] == "claude"
                else _ask_openrouter(t["judge"], t["prompt"])
            )
        except Exception as exc:  # noqa: BLE001 - a failed judge call is recorded, then retried later
            data, meta = {}, {"error": f"{type(exc).__name__}: {exc}"[:300]}
        rec = {k: t[k] for k in ("judge", "pmcid", "reader", "variant", "order")}
        rec |= {"prompt_sha256": grid.sha256(t["prompt"]), "answer": data, **meta}
        if "error" in meta:
            with (path.parent / "judge_errors.jsonl").open("a", encoding="utf-8") as h:
                h.write(json.dumps(rec, ensure_ascii=False) + "\n")
            return "failed"
        with path.open("a", encoding="utf-8") as h:
            h.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return "ok"

    path.parent.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        outcomes = list(pool.map(one, todo))
    return {
        "calls": len(work),
        "already": len(work) - len(todo),
        "ok": outcomes.count("ok"),
        "failed": outcomes.count("failed"),
    }


# -- scoring -------------------------------------------------------------------------------------


def load_items() -> list[dict]:
    path = items_path()
    if not path.is_file():
        return []
    return [json.loads(t) for t in path.read_text(encoding="utf-8").splitlines() if t.strip()]


def per_row(items: Sequence[dict]) -> pd.DataFrame:
    rows = []
    for it in items:
        if it["judge"] not in (*JURY, "claude"):
            continue  # a model dropped from the jury
        if it["variant"] == "trap":
            continue
        for e in (it.get("answer") or {}).get("rows") or []:
            if isinstance(e, dict) and e.get("row_id"):
                rows.append(
                    {
                        "judge": it["judge"],
                        "pmcid": it["pmcid"],
                        "reader": it["reader"],
                        "variant": it["variant"],
                        "row_id": str(e["row_id"]),
                        "J1": str(e.get("J1", "")).lower(),
                        "J2": str(e.get("J2", "")),
                        "J3": str(e.get("J3", "")).lower(),
                    }
                )
    return pd.DataFrame(rows)


def score(v: pd.DataFrame, items: Sequence[dict], labels: Mapping[tuple[str, str], str]) -> dict:
    j = per_row(items)
    m: dict[str, Any] = {
        "judges": list(JURY),
        "self_preference_probe": CLAUDE_PROBE,
        "tier1": "not run: Nimble needs Ollama ≥ 0.35 (installed 0.21.0); "
        "Microsoft-Decision-1 is not on OpenRouter (checked 2026-10-19)",
    }
    if j.empty:
        return m
    base = j[j.variant == "order0"].merge(
        v[["pmcid", "row_id", "raw_A", "raw_B", "v1_A", "v1_B"]], on=["pmcid", "row_id"]
    )
    base["reader_cause"] = [
        a if r == "A" else b for r, a, b in zip(base.reader, base.raw_A, base.raw_B, strict=True)
    ]
    per: dict[str, Any] = {}
    for judge, g in base.groupby("judge"):
        o1 = j[(j.judge == judge) & (j.variant == "order1")]
        flip = g.merge(o1, on=["pmcid", "reader", "row_id"], suffixes=("", "_r"))
        dec = j[(j.judge == judge) & (j.variant == "decoy")]
        a = g[g.reader == "A"]
        per[judge] = {
            "rows_judged": len(g),
            "J1_yes_rate": round(float((g.J1 == "yes").mean()), 3),
            "J1_yes_rate_on_reader_A": round(float((a.J1 == "yes").mean()), 3) if len(a) else None,
            "J2_agrees_with_reader": round(float((g.J2 == g.reader_cause).mean()), 3),
            "J1_agrees_with_code_V1": round(
                float(
                    (
                        (g.J1 == "yes")
                        == [c in sign.CAUSES for c in (g.v1_A.where(g.reader == "A", g.v1_B))]
                    ).mean()
                ),
                3,
            ),
            "J3_abstain_rate": round(float((g.J3 == "yes").mean()), 3),
            "order_flip_rate_J2": round(float((flip.J2 != flip.J2_r).mean()), 3)
            if len(flip)
            else None,
            "decoy_accepted_rate": round(float((dec.J1 == "yes").mean()), 3) if len(dec) else None,
        }
    m["per_judge"] = per
    jury = base[base.judge.isin(JURY)]
    maj = (
        jury.groupby(["pmcid", "reader", "row_id"])
        .agg(
            J1=("J1", lambda s: "yes" if (s == "yes").sum() >= 2 else "no"),
            J2=("J2", lambda s: s.mode().iat[0] if s.mode().size == 1 else "split"),
            n=("judge", "nunique"),
        )
        .reset_index()
    )
    m["jury"] = {
        "rows": len(maj),
        "unanimous_J1": round(
            float(jury.groupby(["pmcid", "reader", "row_id"]).J1.nunique().eq(1).mean()), 3
        ),
        "J2_split_rate": round(float((maj.J2 == "split").mean()), 3),
    }
    m["traps"] = {
        f"{it['judge']}|{it['pmcid']}": (it.get("answer") or {}).get("J1")
        for it in items
        if it["variant"] == "trap"
    }
    trap_items = [
        it for it in items if it["variant"] == "trap" and it["judge"] in (*JURY, "claude")
    ]
    m["traps_caught"] = {
        jd: sum(
            str((it.get("answer") or {}).get("J1", "")).lower() == "no"
            for it in trap_items
            if it["judge"] == jd
        )
        for jd in sorted({it["judge"] for it in trap_items})
    }
    m["traps_total"] = len(TRAPS)
    if labels:
        lab = base[[(p, r) in labels for p, r in zip(base.pmcid, base.row_id, strict=True)]].copy()
        lab["truth"] = [labels[(p, r)] for p, r in zip(lab.pmcid, lab.row_id, strict=True)]
        m["vs_human"] = {
            judge: {
                "J2_accuracy": round(float((g.J2 == g.truth).mean()), 3),
                "J2_kappa": sign.kappa(list(g.J2), list(g.truth)),
                "J1_precision": round(
                    float((g[g.J1 == "yes"].reader_cause == g[g.J1 == "yes"].truth).mean()), 3
                )
                if (g.J1 == "yes").any()
                else None,
                "n": len(g),
            }
            for judge, g in lab.groupby("judge")
        }
    return m


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m mnp.validate.judge")
    p.add_argument("what", choices=["estimate", "run", "score"])
    p.add_argument("--jobs", type=int, default=6)
    args = p.parse_args(argv)
    cands = sign.candidates()
    answers = {r: origin.load_answers(sign.answers_dir(), sign.RUN_IDS[r]) for r in sign.READERS}
    if args.what in ("estimate", "run"):
        work = tasks(cands, answers)
        toks = sum(origin.approx_tokens(t["prompt"]) for t in work)
        print(f"{len(work)} judge calls, about {toks:,} prompt tokens")
        if args.what == "run":
            print(json.dumps(run(work, args.jobs), indent=1))
        return 0
    v = sign.verdicts(cands, answers)
    m = score(v, load_items(), sign.load_labels())
    (config.OUT_TABLES / "validate_judge_metrics.json").write_text(
        json.dumps(m, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(m, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
