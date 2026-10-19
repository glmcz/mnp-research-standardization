"""Q2: why does a zeta value contradict its surface label?

An amine group makes a bead positive in clean water; carboxyl and sulfate make it negative. A row
whose sign is the opposite is a candidate. Each paper with candidates is read by two isolated
readers (`claude -p`, tools off), A and B, over the paper's lines about pH, the liquid, salts,
proteins and surface chemistry, plus every line the rows were read from. Each reader gives one
cause per row and cites lines. Then code decides:

- V0 takes reader A's cause as given.
- V1 keeps it only if every citation is a line of this paper and the cited lines carry the kind
  of evidence the cause needs (a pH value for `ph`, a protein or organic matter for `corona` ...).
  `extraction_error` is checked against the row's own quote: the printed sign must differ.
- V2 keeps a cause only where A and B, both passing V1, agree; otherwise the row is abstained.
- V3 hands V2's abstentions to a person (Martin's labels), and is scored once labels exist.

python -m mnp.validate.sign estimate
python -m mnp.validate.sign run --reader A    (then --reader B)
python -m mnp.validate.sign score
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from mnp import config, runs
from mnp.corpus import lines
from mnp.eval import grid, scoring
from mnp.extract import origin

CAUSES = ("ph", "corona", "ions", "label_error", "extraction_error", "other_stated", "unexplained")
#: The sign a surface group gives a particle in clean water near neutral pH.
EXPECTED_SIGN = {"amine": +1, "carboxyl": -1, "sulfate": -1}
# B is a different model and generation from A. claude-opus-5-5 needs Claude Code ≥ 2.1.280;
# the reader CLI here is 2.1.92 (checked 2026-10-19), so B is the newest Opus it can run.
READERS = {"A": grid.READER_MODEL, "B": "claude-opus-4-6"}
RUN_IDS = {"A": "sign-a-20261019", "B": "sign-b-20261019"}
BUDGET_TOKENS = 3000
INPUT_TOKEN_LIMIT = 1_500_000
TABLE = "p2_zeta_size.csv"  # the rows P2 shows; surface groups as P2 assigns them


def answers_dir() -> Path:
    return config.DATA_INTERIM / "validate" / "sign"


def labels_path() -> Path:
    return answers_dir() / "labels.jsonl"


# -- candidates ------------------------------------------------------------------------------------


def candidates(p2: pd.DataFrame | None = None, d1: pd.DataFrame | None = None) -> pd.DataFrame:
    """Rows whose sign opposes their surface group's, with the d1 fields a reader needs."""
    p2 = pd.read_csv(config.OUT_TABLES / TABLE) if p2 is None else p2
    d1 = origin.load_table() if d1 is None else d1
    expected = p2.surface.map(EXPECTED_SIGN)
    c = p2[expected.notna() & (np.sign(p2.zeta_mV) == -expected)]
    keep = [
        "pmcid",
        "row_id",
        "particle_name",
        "medium_text",
        "value_text",
        "evidence_quote",
        "evidence_line_ids",
    ]
    c = c.merge(d1[keep], on=["pmcid", "row_id"], how="left")
    return c.sort_values(["pmcid", "row_id"]).reset_index(drop=True)


# -- which lines speak to the sign -----------------------------------------------------------------

_CUES: dict[str, tuple[int, re.Pattern[str]]] = {
    "ph": (3, re.compile(r"\bpH\b|isoelectric|\bIEP\b|pKa|protonat|deprotonat")),
    "corona": (
        3,
        re.compile(
            r"protein|serum|\bFBS\b|\bBSA\b|albumin|corona|culture medi|DMEM|RPMI|\bMEM\b|humic|"
            r"fulvic|\bNOM\b|\bDOM\b|organic matter|mucin|\bEPS\b|exudate|biofilm|lysozyme|"
            r"saliva|gastric|intestinal|plasma|blood|coat(?:ed|ing|s)?\b|surfactant|adsorb",
            re.I,
        ),
    ),
    "ions": (
        2,
        re.compile(
            r"buffer|\bPBS\b|phosphate|HEPES|\bTris\b|citrate|NaCl|KCl|CaCl|MgCl|Ca\s?2\+|Mg\s?2\+|"
            r"ionic strength|electrolyte|seawater|salinity|\bmM\b|mmol",
            re.I,
        ),
    ),
    "surface": (
        2,
        re.compile(
            r"amin|\bNH2\b|\bNH3\b|carboxyl|COOH|sulfat|sulphat|functionali[sz]|surface charge|"
            r"modif(?:ied|ication)|plain|unmodified|coated|coating",
            re.I,
        ),
    ),
    "zeta": (1, re.compile(r"zeta|ζ|electrophoretic|mobilit", re.I)),
}
CITED_WEIGHT = 4


def cues(text: str) -> dict[str, int]:
    return {family: w for family, (w, rx) in _CUES.items() if rx.search(text)}


def select(
    doc: lines.LinedDoc, cited: Iterable[str], budget: int = BUDGET_TOKENS
) -> origin.Evidence:
    """Every cue line and cited line, highest signal first until the budget, in reading order."""
    cited = frozenset(cited)
    scored = []
    for line in doc.lines:
        score = sum(cues(line.text).values()) + (CITED_WEIGHT if line.line_id in cited else 0)
        if score:
            scored.append((score, line))
    kept, cost = {}, 0
    for _, line in sorted(scored, key=lambda s: (-s[0], s[1].n)):
        c = origin.approx_tokens(line.text) + 1
        if cost + c > budget:
            continue
        kept[line.n] = line
        cost += c
    shown = tuple(kept[n] for n in sorted(kept))
    return origin.Evidence(doc.pmcid or "", doc, shown, tuple(x.text for x in shown), len(scored))


# -- the prompt ------------------------------------------------------------------------------------

_RULES = """RULES
- Each row is a zeta potential whose sign is the opposite of what its surface group gives in \
clean water near neutral pH (amine: positive; carboxyl or sulfate: negative). Say why, choosing \
exactly one cause per row:
  - ph: the lines give a pH at which this group does not carry its usual charge (for example \
an amine above its pKa). Cite the line with the pH.
  - corona: proteins, serum, a culture medium, humic or other organic matter, or another \
coating adsorbed in the measured liquid. Cite the line that names it.
  - ions: salts or buffer ions in the measured liquid (phosphate, citrate, divalent cations, \
high ionic strength) that the lines connect to the measured charge. Cite the line.
  - label_error: the lines show the measured particle is not the one with this surface group \
(it was plain, or the group was on something else).
  - extraction_error: the lines print this value with the other sign, or the value belongs to \
another particle or condition.
  - other_stated: the paper itself states another reason. Cite it.
  - unexplained: the lines do not give a reason. This is a valid answer, not a failure.
- Answer only from the lines above. Background knowledge may only connect a printed pH or a \
named liquid to the group's charge; it may not supply a fact the lines do not print.
- Cite every cause except unexplained: citations lists line addresses exactly as printed at the \
start of each line (PMCID:L<n>).
- Do not explain your reasoning outside the JSON object."""

_CONTRACT = """OUTPUT
Return exactly one JSON object and nothing else, with one entry per row listed above:
{"rows": [{"row_id": "<row id exactly as listed>", "cause": "ph" | "corona" | "ions" | \
"label_error" | "extraction_error" | "other_stated" | "unexplained", \
"citations": ["PMCID:L<n>", ...], "reason": "<one sentence>"}, ...]}"""


def _row_line(r: Mapping[str, Any]) -> str:
    ph = "" if pd.isna(r.get("pH")) else f", pH {r['pH']:g}"
    return (
        json.dumps(
            {
                "row_id": r["row_id"],
                "particle": r["particle_name"],
                "surface_group": r["surface"],
                "zeta_mV": r["zeta_mV"],
                "liquid": r["medium_text"] if pd.notna(r["medium_text"]) else None,
            },
            ensure_ascii=False,
        )
        + ph
    )


def prompt_for(pmcid: str, rows: pd.DataFrame, ev: origin.Evidence) -> str:
    note = (
        f" {ev.dropped} further lines with weaker cues were dropped to fit the length limit; "
        "if what you need is not here, answer unexplained."
        if ev.dropped
        else ""
    )
    listed = "\n".join(_row_line(r) for r in rows.to_dict("records"))
    return "\n\n".join(
        [
            f"You are reading lines from one paper, {pmcid}, to say why some of its zeta-potential "
            "values have the opposite sign to the one their particles' surface group suggests.",
            f"ROWS\n{listed}",
            "LINES\nEach line starts with its citation address. These are the paper's lines "
            "about pH, the measured liquid, salts, proteins and surface chemistry, and the lines "
            f"the rows were read from.{note}\n{origin.render(ev)}",
            _RULES.replace("PMCID", pmcid),
            _CONTRACT.replace("PMCID", pmcid),
        ]
    )


def jobs_for(cands: pd.DataFrame) -> list[origin.Job]:
    out = []
    for pmcid, rows in cands.groupby("pmcid"):
        cited = {i for ids in rows.evidence_line_ids.dropna() for i in str(ids).split(";") if i}
        ev = select(origin.load_doc(pmcid), cited)
        out.append(
            origin.Job(
                pmcid, tuple(rows.row_id), prompt_for(pmcid, rows, ev), len(ev.shown), ev.dropped
            )
        )
    return out


# -- reading the reply back, and the code's decision -----------------------------------------------

#: The kind of line each cause must cite. A cause without such a line is not accepted at V1.
NEEDS = {
    "ph": _CUES["ph"][1],
    "corona": _CUES["corona"][1],
    "ions": _CUES["ions"][1],
    "label_error": _CUES["surface"][1],
}


def parse_reply(text: str) -> dict[str, dict[str, Any]]:
    """row_id -> the reader's entry. Unreadable replies give {}."""
    answer = scoring.parse_answer("sign", "sign", text)
    found = answer.payload.get("rows")
    if answer.unparsed or not isinstance(found, list):
        return {}
    return {str(e.get("row_id")): e for e in found if isinstance(e, dict) and e.get("row_id")}


_NUMBER = r"(?<![\d.])({v})(?![\d])"
_MINUS = "-−–‒"


def printed_sign(quote: str, value: float) -> int | None:
    """The sign the quote prints in front of |value|; None if the number is not in the quote.

    A match right after "±" is a spread, not the value, so the next match is tried.
    """
    v = abs(value)
    for t in dict.fromkeys((f"{v:g}", f"{v:.1f}", f"{v:.2f}")):
        for m in re.finditer(_NUMBER.format(v=re.escape(t)), quote):
            before = quote[: m.start()].rstrip()
            if before.endswith("±"):
                continue
            return -1 if before[-1:] in _MINUS else +1
    return None


@dataclass(frozen=True)
class Decision:
    cause: str  # a CAUSE, "unsupported" (failed V1) or "unparsed"
    raw: str  # what the reader said
    citations_ok: bool
    evidence_ok: bool
    why: str


def decide(
    entry: Mapping[str, Any] | None, doc: lines.LinedDoc, row: Mapping[str, Any]
) -> Decision:
    """V1: accept a cause only if its citations exist and carry the evidence it needs."""
    if not entry or entry.get("cause") not in CAUSES:
        raw = str((entry or {}).get("cause"))
        return Decision("unparsed", raw, False, False, "no valid cause for this row")
    cause = entry["cause"]
    cites = origin.check_citations(doc, entry.get("citations") or [])
    if cause == "unexplained":
        return Decision(cause, cause, True, True, "")
    if not cites.resolved or cites.unresolved:
        return Decision(
            "unsupported", cause, False, False, f"citations {list(cites.unresolved) or 'missing'}"
        )
    cited_text = " ".join(lines.resolve_id(doc, i).text for i in cites.line_ids)
    if cause == "extraction_error":
        s = printed_sign(str(row.get("evidence_quote") or ""), float(row["zeta_mV"]))
        ok = s is not None and s != np.sign(row["zeta_mV"])
        return Decision(
            cause if ok else "unsupported",
            cause,
            True,
            ok,
            "" if ok else "the row's quote prints the same sign as the table",
        )
    need = NEEDS.get(cause)
    ok = need is None or bool(need.search(cited_text))
    return Decision(
        cause if ok else "unsupported",
        cause,
        True,
        ok,
        "" if ok else f"no cited line carries {cause} evidence",
    )


# -- scoring -------------------------------------------------------------------------------------


def load_labels() -> dict[tuple[str, str], str]:
    path = labels_path()
    if not path.is_file():
        return {}
    out = {}
    for text in path.read_text(encoding="utf-8").splitlines():
        if text.strip():
            r = json.loads(text)
            out[(r["pmcid"], r["row_id"])] = r["cause"]
    return out


def kappa(a: Sequence[str], b: Sequence[str]) -> float | None:
    """Cohen's kappa over paired category labels."""
    if not a:
        return None
    cats = sorted(set(a) | set(b))
    n = len(a)
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    pe = sum((list(a).count(c) / n) * (list(b).count(c) / n) for c in cats)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def verdicts(
    cands: pd.DataFrame, answers: Mapping[str, Mapping[str, Mapping[str, Any]]]
) -> pd.DataFrame:
    """One row per candidate: each reader's raw cause and V1 decision, and V0, V1, V2."""
    docs: dict[str, lines.LinedDoc] = {}
    out = []
    for row in cands.to_dict("records"):
        pmcid = row["pmcid"]
        doc = docs.setdefault(pmcid, origin.load_doc(pmcid))
        rec = {
            "pmcid": pmcid,
            "row_id": row["row_id"],
            "zeta_mV": row["zeta_mV"],
            "surface": row["surface"],
            "medium_class": row["medium_class"],
        }
        for r in READERS:
            entry = parse_reply(answers.get(r, {}).get(pmcid, {}).get("text", "")).get(
                row["row_id"]
            )
            d = decide(entry, doc, row)
            rec |= {
                f"raw_{r}": d.raw,
                f"v1_{r}": d.cause,
                f"why_{r}": d.why,
                f"reason_{r}": (entry or {}).get("reason", ""),
                f"cites_{r}": ";".join(map(str, (entry or {}).get("citations") or [])),
            }
        rec["V0"] = rec["raw_A"] if rec["raw_A"] in CAUSES else "unparsed"
        rec["V1"] = rec["v1_A"]
        both = rec["v1_A"] in CAUSES and rec["v1_B"] in CAUSES
        rec["V2"] = rec["v1_A"] if both and rec["v1_A"] == rec["v1_B"] else "abstain"
        out.append(rec)
    return pd.DataFrame(out)


def metrics(
    v: pd.DataFrame,
    answers: Mapping[str, Mapping[str, Mapping[str, Any]]],
    labels: Mapping[tuple[str, str], str],
) -> dict[str, Any]:
    explained = {c for c in CAUSES if c != "unexplained"}
    m: dict[str, Any] = {"candidates": len(v), "papers": int(v.pmcid.nunique())}
    for cfg in ("V0", "V1", "V2"):
        col = v[cfg]
        m[cfg] = {
            "distribution": col.value_counts().to_dict(),
            "abstained": int(col.isin(["abstain", "unsupported", "unparsed"]).sum()),
        }
    m["reader_kappa_raw"] = kappa(list(v.raw_A), list(v.raw_B))
    m["reader_agreement_raw"] = float((v.raw_A == v.raw_B).mean())
    m["v1_rejected"] = {r: int((v[f"v1_{r}"] == "unsupported").sum()) for r in READERS}
    for r in READERS:
        recs = list(answers.get(r, {}).values())
        m[f"cost_{r}"] = {
            "papers": len(recs),
            "input_tokens": int(sum(x.get("input_tokens") or 0 for x in recs)),
            "output_tokens": int(sum(x.get("output_tokens") or 0 for x in recs)),
            "seconds": round(sum(x.get("duration_ms") or 0 for x in recs) / 1000, 1),
            "model": READERS[r],
        }
    keyed = v[[(p, r) in labels for p, r in zip(v.pmcid, v.row_id, strict=True)]]
    m["labelled"] = len(keyed)
    if len(keyed):
        truth = [labels[(p, r)] for p, r in zip(keyed.pmcid, keyed.row_id, strict=True)]
        for cfg in ("V0", "V1", "V2"):
            said = list(keyed[cfg])
            answered = [(s, t) for s, t in zip(said, truth, strict=True) if s in CAUSES]
            wrong_cause = sum(s in explained and s != t for s, t in answered)
            m[cfg] |= {
                "accuracy": round(
                    sum(s == t for s, t in zip(said, truth, strict=True)) / len(truth), 3
                ),
                "accuracy_on_answered": round(sum(s == t for s, t in answered) / len(answered), 3)
                if answered
                else None,
                "false_explanation_rate": round(wrong_cause / len(truth), 3),
                "coverage": round(len(answered) / len(truth), 3),
            }
        v3 = [t if s not in CAUSES else s for s, t in zip(keyed.V2, truth, strict=True)]
        m["V3"] = {
            "accuracy": round(sum(s == t for s, t in zip(v3, truth, strict=True)) / len(truth), 3),
            "human_labels_used": int(sum(s not in CAUSES for s in keyed.V2)),
        }
    return m


# -- the commands ----------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m mnp.validate.sign")
    p.add_argument("what", choices=["estimate", "run", "score"])
    p.add_argument("--reader", choices=sorted(READERS), default="A")
    p.add_argument("--jobs", type=int, default=4)
    args = p.parse_args(argv)
    cands = candidates()
    work = jobs_for(cands)
    directory = answers_dir()
    if args.what in ("estimate", "run"):
        run_id = RUN_IDS[args.reader]
        done = origin.load_answers(directory, run_id)
        todo = [j for j in work if j.pmcid not in done]
        estimate = sum(origin.estimate_billed(j.prompt) for j in todo)
        print(
            f"{len(cands)} candidate rows in {len(work)} papers; reader {args.reader} "
            f"({READERS[args.reader]}): {len(done)} answered, {len(todo)} to ask, "
            f"estimated {estimate:,} input tokens; billed so far {origin.billed(directory):,}"
        )
        if args.what == "estimate":
            return 0
        runs.start(
            run_id,
            task="Q2: why a zeta value contradicts its surface label",
            model=READERS[args.reader],
            reader=f"claude -p, tools off, no setting sources ({grid.cli_version()})",
            system_prompt_sha256=grid.sha256(grid.SYSTEM_PROMPT),
            budget_tokens_per_paper=BUDGET_TOKENS,
            input_token_limit=INPUT_TOKEN_LIMIT,
            answers=str((directory / "answers.jsonl").relative_to(config.ROOT)),
        )
        reader = partial(grid.read, model=READERS[args.reader])
        counts = origin.run(
            work, directory, run_id, reader=reader, jobs=args.jobs, limit=INPUT_TOKEN_LIMIT
        )
        runs.finish(run_id, counts)
        print(json.dumps(counts, indent=2))
        return 0 if not counts["reader_failures"] else 1
    answers = {r: origin.load_answers(directory, RUN_IDS[r]) for r in READERS}
    v = verdicts(cands, answers)
    v.to_csv(config.OUT_TABLES / "validate_sign_verdicts.csv", index=False)
    m = metrics(v, answers, load_labels())
    (config.OUT_TABLES / "validate_sign_metrics.json").write_text(
        json.dumps(m, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(m, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
