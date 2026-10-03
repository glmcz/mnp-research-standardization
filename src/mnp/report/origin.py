"""Where the measured particles came from, per zeta row — a confirmation, not a release table.

The reader answered once per paper and per distinct `particle_name`; this matches each answer
back to the rows carrying that name, counts rows and papers per origin and environment, and asks
of the environmental rows alone how completely they report their conditions. Two things are
checked deterministically rather than trusted: every citation must address a line of that paper
(and one the reader was shown), and every row whose `supplier` is filled but whose particle is
not called commercial is listed for a human to look at.

`report origin` runs `build`: it reads the recorded answers and the recorded verdicts of the
second reading, and asks nothing, so the rebuild is deterministic though both readings were
judgement. The second reading (2026-09-29) was done by a Claude agent with each paper's full
text, not by a person; its files under data/interim/origin/ keep their `hand_check` names, which
are history. REVIEW.md (C11) and the dataset card read the stats it writes. It also counts the
papers whose methods the parser lost (`extract.origin.methods_lost`), because the origin reading
is where that defect was found.

python -m mnp.report.origin build [--run RUN_ID]
python -m mnp.report.origin sample [--run RUN_ID]
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from mnp import config, runs
from mnp.corpus import licence, lines
from mnp.eval import grid
from mnp.extract import origin
from mnp.report.d1 import CONDITIONS

UNANSWERED = "unanswered"
ROW_ORIGINS = (*origin.ORIGINS, UNANSWERED)
SYNTHETIC = frozenset({"commercial", "lab_fabricated"})
SEED = 20260929
SAMPLE_N = 40
#: A lab liquid, as opposed to the particle's own environmental water. `unreported` is neither,
#: and so is `other`: both environmental rows filed there were measured in their own sample liquid.
LAB_LIQUIDS = frozenset({"DI_water", "salt_solution", "buffer", "culture_medium", "biofluid"})

#: Found by a Claude agent during the second reading of origin, 2026-09-29: D1 rows that are not
#: the authors' own measurement of a plastic particle. Row ids, so a re-extraction that drops one
#: fails the build.
NOT_OWN_MEASUREMENT = {
    "PMC11644763-r1": "a polyester fabric, not a particle",
    "PMC12462602-r2": "PEG 4000, a water-soluble polymer the authors use in place of polystyrene",
    "PMC12878436-r4": "a value cited from Arenas et al. 2022, not measured in this paper",
    "PMC12878436-r5": "a value cited from Arenas et al. 2022, not measured in this paper",
    "PMC12878436-r6": "a value cited from Na et al. 2021, not measured in this paper",
    "PMC12878436-r7": "a value cited from Na et al. 2021, not measured in this paper",
    "PMC9645706-r4": "a passing remark about naturally fragmented plastics; nothing was collected "
    "or measured",
}

#: Read by a Claude agent, 2026-09-29, for every environmental paper whose text prints a
#: conductivity: why none of it gives that paper's environmental rows an ionic strength. Martin's
#: rule allows an ionic strength estimated from a printed conductivity only when it is marked as
#: estimated.
CONDUCTIVITY_NOT_THE_ROWS = {
    "PMC11211448": (
        "The sentence about the liquid of its environmental row, the industrial wastewater as "
        "diluted for the experiments, gives that dispersion's pH, conductivity and an average "
        "zeta potential, and that average is not a row of the table. The row the table holds is "
        "the zeta potential followed down a pH series and shown only in a figure; acid changes "
        "the conductivity along the series, so the printed one does not describe it. The other "
        "sentences are about the model dispersions, water made to simulate one, and other "
        "wastewaters that have no zeta row."
    ),
}

#: The words the second reading used for a zeta potential of the collected sample, not the plastic.
WHOLE_SAMPLE_NOTE = "as a whole"

#: sample_origin.csv, in order. The reader's `origin` and the agent-checked `final_origin` sit
#: side by side, so the counts after the second reading can be recounted from this one file.
ROW_COLUMNS = (
    "pmcid",
    "row_id",
    "particle_name",
    "material",
    "supplier",
    "medium_text",
    "medium_class",
    "origin",
    "environment",
    "aged_in_lab",
    "origin_citations",
    "origin_reason",
    "matched_by",
    "agent_checked",
    "final_origin",
    "final_environment",
)

_CONDUCTIVITY = re.compile(
    r"(?i:conductiv)|(?<![A-Za-z])[µμumd]?S\s*(?:/|·|\s)\s*c?m(?:-1|−1|⁻¹)?(?![A-Za-z])"
)
#: A number with a conductivity unit after it: printed, not just the word "conductive".
_CONDUCTIVITY_VALUE = re.compile(r"\d\s*[µμumd]?S\s*(?:/|·|\s)\s*c?m(?:-1|−1|⁻¹)?(?![A-Za-z])")


def prints_conductivity(medium_text: Any, quote: Any) -> bool:
    return any(_CONDUCTIVITY.search(str(t)) for t in (medium_text, quote) if _text(t))


def conductivity_sentences(doc: lines.LinedDoc) -> list[tuple[str, str]]:
    """Every sentence of the paper that prints a conductivity value, with its line address."""
    return [
        (f"{doc.pmcid}:L{line.n}", sentence)
        for line in doc.lines
        for sentence in origin._SENTENCE.split(line.text)
        if _CONDUCTIVITY_VALUE.search(sentence)
    ]


def conductivity_in_text(
    found: Mapping[str, list[tuple[str, str]]],
    reasons: Mapping[str, str] = CONDUCTIVITY_NOT_THE_ROWS,
    quotable: set[str] | frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """The conductivities the environmental papers print, each paper with the recorded reason it
    gives its rows no ionic strength. A paper nobody has read for that refuses the build; a
    sentence ships only from a source whose licence allows a quote."""
    unread = sorted(p for p, hits in found.items() if hits and p not in reasons)
    if unread:
        raise ValueError(
            f"environmental papers print a conductivity that nobody has read against their rows: "
            f"{unread} — add a reason to CONDUCTIVITY_NOT_THE_ROWS"
        )
    return [
        {
            "pmcid": pmcid,
            "why": reasons[pmcid],
            "lines": [
                {"line": line, "sentence": sentence if pmcid in quotable else None}
                for line, sentence in hits
            ],
        }
        for pmcid, hits in sorted(found.items())
        if hits
    ]


def _text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _fold(name: str) -> str:
    return lines.fold(name).casefold()


# -- answers to rows -----------------------------------------------------------------------------


def classifications(answers: Mapping[str, Mapping[str, Any]]) -> pd.DataFrame:
    """One row per particle the reader classified, plus one status row per paper it did not.

    A refused or unreadable paper keeps a row with no particle, so its absence is counted
    rather than silently shrinking the denominator.
    """
    out: list[dict[str, Any]] = []
    for pmcid, record in sorted(answers.items()):
        if record.get("refused"):
            out.append({"pmcid": pmcid, "status": "refused"})
            continue
        parsed = origin.parse_reply(record.get("text") or "")
        if parsed.unparsed:
            out.append({"pmcid": pmcid, "status": "unparsed"})
            continue
        for item in parsed.particles:
            cites = item.get("citations")
            out.append(
                {
                    "pmcid": pmcid,
                    "status": "ok",
                    "particle_name": item["particle_name"],
                    "origin": item.get("origin"),
                    "environment": item.get("environment"),
                    "aged_in_lab": item.get("aged_in_lab"),
                    "citations": [str(c) for c in cites] if isinstance(cites, list) else [],
                    "reason": str(item.get("reason") or ""),
                    "problems": [
                        p for p in parsed.problems if p.startswith(f"{item['particle_name']}:")
                    ],
                }
            )
    columns = [
        "pmcid",
        "status",
        "particle_name",
        "origin",
        "environment",
        "aged_in_lab",
        "citations",
        "reason",
        "problems",
    ]
    return pd.DataFrame(out).reindex(columns=columns)


def attach(table: pd.DataFrame, classes: pd.DataFrame) -> pd.DataFrame:
    """Every zeta row with its particle's origin. Exact name first, then case- and space-folded."""
    ok = classes[classes["status"] == "ok"]
    exact: dict[tuple[str, str], Mapping[str, Any]] = {}
    folded: dict[tuple[str, str], Mapping[str, Any]] = {}
    for rec in ok.to_dict(orient="records"):
        exact.setdefault((rec["pmcid"], rec["particle_name"]), rec)
        folded.setdefault((rec["pmcid"], _fold(rec["particle_name"])), rec)
    extra: list[dict[str, Any]] = []
    for row in table.to_dict(orient="records"):
        name = _text(row.get("particle_name"))
        rec, how = exact.get((row["pmcid"], name)), "exact"
        if rec is None:
            rec, how = folded.get((row["pmcid"], _fold(name))), "folded"
        if rec is None:
            extra.append({"origin": UNANSWERED, "matched_by": "none"})
            continue
        extra.append(
            {
                "origin": rec["origin"],
                "environment": rec["environment"],
                "aged_in_lab": rec["aged_in_lab"],
                "origin_citations": ";".join(rec["citations"]),
                "origin_reason": rec["reason"],
                "matched_by": how,
            }
        )
    added = pd.DataFrame(extra, index=table.index).reindex(
        columns=[
            "origin",
            "environment",
            "aged_in_lab",
            "origin_citations",
            "origin_reason",
            "matched_by",
        ]
    )
    return pd.concat([table, added], axis=1)


# -- deterministic checks -----------------------------------------------------------------------


def supplier_disagreements(rows: pd.DataFrame) -> list[dict[str, Any]]:
    """Rows whose `supplier` is filled but whose particle the reader did not call commercial.

    Not all are errors: a bought pellet milled in the lab names a supplier and is lab-made.
    That is exactly why they are listed rather than counted as agreement or disagreement.
    """
    named = rows[rows["supplier"].map(_text) != ""]
    odd = named[named["origin"] != "commercial"].sort_values("row_id")
    return [
        {
            "row_id": r["row_id"],
            "particle_name": r["particle_name"],
            "supplier": r["supplier"],
            "origin": r["origin"],
            "reason": _text(r.get("origin_reason")),
        }
        for r in odd.to_dict(orient="records")
    ]


def citation_checks(
    classes: pd.DataFrame, docs: Mapping[str, lines.LinedDoc], shown: Mapping[str, set[int]]
) -> dict[str, Any]:
    total = resolved = repaired = 0
    unresolved: list[list[str]] = []
    not_shown: list[list[str]] = []
    uncited = 0
    for rec in classes[classes["status"] == "ok"].to_dict(orient="records"):
        cites = rec["citations"]
        if not cites:
            uncited += 1
        got = origin.check_citations(docs[rec["pmcid"]], cites)
        total += len(cites)
        resolved += len(got.resolved)
        unresolved += [[rec["pmcid"], rec["particle_name"], t] for t in got.unresolved]
        for token, line_id in zip(got.resolved, got.line_ids, strict=True):
            line = lines.resolve_id(docs[rec["pmcid"]], line_id)
            if line.section_path.startswith("body:"):
                repaired += 1
            if line.n not in shown.get(rec["pmcid"], set()):
                not_shown.append([rec["pmcid"], rec["particle_name"], token])
    return {
        "citations": total,
        "resolve_to_a_line_of_that_paper": resolved,
        "resolve_to_a_repaired_methods_line": repaired,
        "unresolved": unresolved,
        "resolve_but_were_not_shown": not_shown,
        "particles_without_citations": uncited,
    }


# -- counting ------------------------------------------------------------------------------------


def _share(k: int, n: int) -> float:
    return round(k / n, 4) if n else 0.0


def _n_share(mask: pd.Series) -> dict[str, float]:
    k = int(mask.sum())
    return {"n": k, "share": _share(k, len(mask))}


def stats(rows: pd.DataFrame, classes: pd.DataFrame) -> dict[str, Any]:
    papers = rows.groupby("pmcid")["origin"]
    status = classes.drop_duplicates("pmcid").set_index("pmcid")["status"]
    ok = classes[classes["status"] == "ok"]
    row_names = {
        (p, _fold(_text(n))) for p, n in zip(rows["pmcid"], rows["particle_name"], strict=True)
    }
    labels = list(ROW_ORIGINS) + sorted(set(rows["origin"]) - set(ROW_ORIGINS))

    env = rows[rows["origin"] == "environmental"]
    env_medium = env["medium_class"].fillna("unreported")
    conductivity = [
        prints_conductivity(m, q)
        for m, q in zip(env["medium_text"], env["evidence_quote"], strict=True)
    ]
    conductivity = pd.Series(conductivity, index=env.index, dtype=bool)
    answered = rows[rows["origin"] != UNANSWERED]
    syn_medium = rows.loc[rows["origin"].isin(SYNTHETIC), "medium_class"].fillna("unreported")

    return {
        "papers": int(rows["pmcid"].nunique()),
        "rows": int(len(rows)),
        "particles_classified": int(len(ok)),
        "answers": {
            "papers_answered": int((status == "ok").sum()),
            "refused": int((status == "refused").sum()),
            "unparsed": int((status == "unparsed").sum()),
            "missing": int(len(set(rows["pmcid"]) - set(status.index))),
            "particles_with_problems": int(ok["problems"].map(bool).sum()),
        },
        "matching": {
            "rows_exact": int((rows["matched_by"] == "exact").sum()),
            "rows_folded": int((rows["matched_by"] == "folded").sum()),
            "rows_unmatched": int((rows["matched_by"] == "none").sum()),
            "names_not_in_rows": sorted(
                [p, n]
                for p, n in zip(ok["pmcid"], ok["particle_name"], strict=True)
                if (p, _fold(n)) not in row_names
            ),
        },
        "origin": {
            "rows": {o: int((rows["origin"] == o).sum()) for o in labels},
            "row_share": {o: _share(int((rows["origin"] == o).sum()), len(rows)) for o in labels},
            "papers_any": {
                o: int(papers.apply(lambda s, o=o: (s == o).any()).sum()) for o in labels
            },
            "papers_only": {
                o: int(papers.apply(lambda s, o=o: (s == o).all()).sum()) for o in labels
            },
        },
        "synthetic": {
            "rows": int(rows["origin"].isin(SYNTHETIC).sum()),
            "row_share": _share(int(rows["origin"].isin(SYNTHETIC).sum()), len(rows)),
            "papers_any": int(papers.apply(lambda s: s.isin(SYNTHETIC).any()).sum()),
            "papers_only": int(papers.apply(lambda s: s.isin(SYNTHETIC).all()).sum()),
            "medium": {
                "lab_liquid": int(syn_medium.isin(LAB_LIQUIDS).sum()),
                "environmental_water": int((syn_medium == "environmental_water").sum()),
                "other": int((syn_medium == "other").sum()),
                "unreported": int((syn_medium == "unreported").sum()),
            },
        },
        "environment": {
            "rows": {e: int((env["environment"] == e).sum()) for e in origin.ENVIRONMENTS}
            | {"null": int(env["environment"].isna().sum())},
            "papers": {
                e: int(env.loc[env["environment"] == e, "pmcid"].nunique())
                for e in origin.ENVIRONMENTS
            },
        },
        "aged_in_lab": {
            "rows_true": int((answered["aged_in_lab"] == True).sum()),  # noqa: E712
            "rows_false": int((answered["aged_in_lab"] == False).sum()),  # noqa: E712
            "rows_null": int(answered["aged_in_lab"].isna().sum()),
            "share_true_of_answered_rows": _share(
                int((answered["aged_in_lab"] == True).sum()),  # noqa: E712
                len(answered),
            ),
            "rows_true_by_origin": {
                o: int(((rows["origin"] == o) & (rows["aged_in_lab"] == True)).sum())  # noqa: E712
                for o in origin.ORIGINS
            },
            "papers_true": int(rows.loc[rows["aged_in_lab"] == True, "pmcid"].nunique()),  # noqa: E712
        },
        "supplier_vs_origin": {
            "rows_naming_a_supplier": int((rows["supplier"].map(_text) != "").sum()),
            "of_which": {
                o: int(((rows["supplier"].map(_text) != "") & (rows["origin"] == o)).sum())
                for o in labels
            },
        },
        "environmental_rows": {
            "rows": int(len(env)),
            "papers": int(env["pmcid"].nunique()),
            "reported": {name: _n_share(env[col].astype(bool)) for name, col, _ in CONDITIONS},
            "conditions_complete": _n_share(env["conditions_complete"].astype(bool)),
            "ionic_strength_reported": int(env["ionic_strength_reported"].astype(bool).sum()),
            "conductivity_printed": int(conductivity.sum()),
            "conductivity_printed_without_ionic_strength": int(
                (conductivity & ~env["ionic_strength_reported"].astype(bool)).sum()
            ),
            "medium_class": env_medium.value_counts().sort_index().astype(int).to_dict(),
            "own_environmental_water": int((env_medium == "environmental_water").sum()),
            "own_sample_liquid": int(
                (~env_medium.isin(LAB_LIQUIDS) & (env_medium != "unreported")).sum()
            ),
            "lab_liquid": int(env_medium.isin(LAB_LIQUIDS).sum()),
            "medium_unreported": int((env_medium == "unreported").sum()),
            "medium_other": int((env_medium == "other").sum()),
            "list": [
                {
                    "row_id": r["row_id"],
                    "particle_name": r["particle_name"],
                    "environment": r["environment"],
                    "medium_text": _text(r["medium_text"]),
                    "medium_class": _text(r["medium_class"]) or "unreported",
                    "ionic_strength_reported": bool(r["ionic_strength_reported"]),
                    "conductivity_printed": bool(conductivity[i]),
                }
                for i, r in env.iterrows()
            ],
        },
        "reporting_by_origin": _reporting_by_origin(rows, labels),
    }


def _reporting_by_origin(rows: pd.DataFrame, labels: list[str]) -> dict[str, dict[str, float]]:
    """The same five shares for every origin, so the environmental ones have a comparison."""
    out = {}
    for o in labels:
        g = rows[rows["origin"] == o]
        if len(g):
            out[o] = {"rows": int(len(g))} | {
                name: _share(int(g[col].astype(bool).sum()), len(g))
                for name, col, _ in (*CONDITIONS, ("complete", "conditions_complete", ""))
            }
    return out


# -- the second reading --------------------------------------------------------------------------


def hand_check_sample(classes: pd.DataFrame, seed: int = SEED, n: int = SAMPLE_N) -> pd.DataFrame:
    """Every environmental particle; every unclear one up to `n`, else `n` of them; `n` others."""
    ok = classes[classes["origin"].notna()].sort_values(["pmcid", "particle_name"])
    ok = ok.reset_index(drop=True)
    rng = random.Random(seed)

    def take(frame: pd.DataFrame, k: int | None) -> pd.DataFrame:
        if k is None or len(frame) <= k:
            return frame
        return frame.loc[sorted(rng.sample(list(frame.index), k))]

    parts = [
        take(ok[ok["origin"] == "environmental"], None).assign(stratum="environmental"),
        take(ok[ok["origin"] == "unclear"], n).assign(stratum="unclear"),
        take(ok[ok["origin"].isin(SYNTHETIC)], n).assign(stratum="random"),
    ]
    return pd.concat(parts, ignore_index=True)


def apply_hand(rows: pd.DataFrame, hand: pd.DataFrame) -> pd.DataFrame:
    """Rows with the second reading's origin and environment wherever it read the particle.

    `hand` is the recorded file of the second reading by a Claude agent; its `hand_origin` and
    `hand_environment` fields keep the names they were recorded under."""
    verdict = {(r["pmcid"], r["particle_name"]): r for r in hand.to_dict(orient="records")}
    fixed = rows.copy()
    for i, row in rows.iterrows():
        v = verdict.get((row["pmcid"], _text(row["particle_name"])))
        if v is not None:
            fixed.at[i, "origin"] = v["hand_origin"]
            fixed.at[i, "environment"] = v.get("hand_environment")
    return fixed


def with_final(rows: pd.DataFrame, hand: pd.DataFrame | None) -> pd.DataFrame:
    """The rows with the second reading beside the reader's answer: `final_origin` is the second
    reading's verdict where `agent_checked` is true and the reader's answer everywhere else."""
    out = rows.copy()
    if hand is None or hand.empty:
        out["agent_checked"] = False
        out["final_origin"], out["final_environment"] = rows["origin"], rows["environment"]
        return out
    read = {(p, n) for p, n in zip(hand["pmcid"], hand["particle_name"], strict=True)}
    fixed = apply_hand(rows, hand)
    out["agent_checked"] = [
        (p, _text(n)) in read for p, n in zip(rows["pmcid"], rows["particle_name"], strict=True)
    ]
    out["final_origin"], out["final_environment"] = fixed["origin"], fixed["environment"]
    return out


def whole_sample_papers(hand: pd.DataFrame) -> list[str]:
    """Environmental papers whose zeta potential the second reading found to be of the collected
    sample as a whole rather than of isolated plastic."""
    env = hand[hand["hand_origin"] == "environmental"]
    return sorted(set(env.loc[env["note"].fillna("").str.contains(WHOLE_SAMPLE_NOTE), "pmcid"]))


def not_own_rows(
    table: pd.DataFrame, listing: Mapping[str, str] = NOT_OWN_MEASUREMENT
) -> list[dict[str, str]]:
    by_id = table.set_index("row_id")
    stale = sorted(set(listing) - set(by_id.index))
    if stale:
        raise ValueError(f"rows listed as not an own measurement are not in the table: {stale}")
    return [
        {
            "row_id": row_id,
            "pmcid": str(by_id.at[row_id, "pmcid"]),
            "particle_name": _text(by_id.at[row_id, "particle_name"]),
            "why": why,
        }
        for row_id, why in sorted(listing.items())
    ]


def lost_methods(table: pd.DataFrame, lost: set[str] | frozenset[str]) -> dict[str, Any]:
    """Papers whose methods the parser lost against the rest: the share of papers with at least
    one row reporting each condition, which is where an unread Methods section would show."""
    cols = {name: col for name, col, _ in CONDITIONS} | {"complete": "conditions_complete"}
    per_paper = table[list(cols.values())].astype(bool).groupby(table["pmcid"]).any()
    hit = per_paper.index.isin(sorted(lost))

    def block(mask: Any) -> dict[str, Any]:
        g = per_paper[mask]
        return {
            "papers": int(len(g)),
            "rows": int(table["pmcid"].isin(g.index).sum()),
            "any_row": {name: _n_share(g[col]) for name, col in cols.items()},
        }

    return {
        "papers": int(len(per_paper)),
        "papers_affected": int(hit.sum()),
        "affected": block(hit),
        "unaffected": block(~hit),
        "pmcids": sorted(set(per_paper.index[hit])),
    }


def agreement(sample: pd.DataFrame, hand: pd.DataFrame) -> dict[str, Any]:
    verdicts = hand.drop(columns=[c for c in ("stratum",) if c in hand.columns])
    merged = sample.merge(verdicts, on=["pmcid", "particle_name"], how="inner")

    def split(o: Any) -> str:
        return "synthetic" if o in SYNTHETIC else str(o)

    merged["agree"] = merged["origin"] == merged["hand_origin"]
    merged["agree_split"] = merged["origin"].map(split) == merged["hand_origin"].map(split)
    out: dict[str, Any] = {}
    for stratum, g in merged.groupby("stratum", sort=False):
        out[stratum] = {
            "n": int(len(g)),
            "agree": int(g["agree"].sum()),
            "share": _share(int(g["agree"].sum()), len(g)),
            "agree_synthetic_split": int(g["agree_split"].sum()),
        }
    out["checked"] = int(len(merged))
    out["not_checked"] = int(len(sample) - len(merged))
    out["disagreements"] = [
        {
            "pmcid": r["pmcid"],
            "particle_name": r["particle_name"],
            "stratum": r["stratum"],
            "origin": r["origin"],
            "checked_origin": r["hand_origin"],
            "note": r.get("note"),
        }
        for r in merged[~merged["agree"]].to_dict(orient="records")
    ]
    return out


# -- files ---------------------------------------------------------------------------------------


def _paths(run_id: str, tables: Path | None = None) -> dict[str, Path]:
    base, tables = origin.answers_dir(), tables or config.OUT_TABLES
    # The recorded second reading is named `hand_check-*`; the names are history, and the
    # reading was a Claude agent's, not a person's.
    return {
        "rows": tables / "sample_origin.csv",
        "stats": tables / "sample_origin_stats.json",
        "sample": base / f"hand_check_sample-{run_id}.jsonl",
        "packet": base / f"hand_check_packet-{run_id}.txt",
        "hand": base / f"hand_check-{run_id}.jsonl",
    }


def _read_jsonl(path: Path) -> pd.DataFrame:
    return pd.DataFrame(
        [json.loads(t) for t in path.read_text(encoding="utf-8").splitlines() if t.strip()]
    )


def reader_spend(directory: Path) -> dict[str, Any]:
    """What every run in the answers file was billed, pilots included; reused copies cost 0."""
    path = directory / "answers.jsonl"
    per_run: dict[str, dict[str, float]] = {}
    for record in map(json.loads, filter(str.strip, path.read_text("utf-8").splitlines())):
        if record.get("reused_from"):
            continue
        run = per_run.setdefault(
            record["run_id"], {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
        )
        run["calls"] += 1
        run["input_tokens"] += int(record.get("input_tokens") or 0)
        run["output_tokens"] += int(record.get("output_tokens") or 0)
        run["cost_usd"] = round(run["cost_usd"] + float(record.get("cost_usd") or 0.0), 4)
    total = {
        k: sum(r[k] for r in per_run.values()) for k in ("calls", "input_tokens", "output_tokens")
    }
    total["cost_usd"] = round(sum(r["cost_usd"] for r in per_run.values()), 2)
    return {"per_run": per_run, "total": total, "input_token_limit": origin.INPUT_TOKEN_LIMIT}


def build(run_id: str, tables: Path | None = None) -> dict[str, Any]:
    """Rebuild `sample_origin.csv` and `sample_origin_stats.json` in `tables` (default
    out/tables) from the D1 table beside them, the recorded answers and the recorded second
    reading."""
    paths = _paths(run_id, tables)
    table = pd.read_csv(paths["rows"].parent / "d1_zeta_table.csv")
    answers = origin.load_answers(origin.answers_dir(), run_id)
    classes = classifications(answers)
    rows = attach(table, classes)

    docs, shown, stale, lost = {}, {}, [], set()
    for pmcid, group in table.groupby("pmcid"):
        doc = origin.load_doc(pmcid)
        names = origin.particle_names(group)
        ev = origin.select(doc, origin.cited_ids(group), names)
        docs[pmcid], shown[pmcid] = doc, {x.n for x in ev.shown}
        record = answers.get(pmcid)
        if record and record["prompt_sha256"] != grid.sha256(origin.prompt_for(pmcid, names, ev)):
            stale.append(pmcid)
        if origin.methods_lost((config.EPMC_XML_DIR / f"{pmcid}.xml").read_bytes()):
            lost.add(pmcid)

    result = stats(rows, classes)
    result["run_id"] = run_id
    result["reader"] = reader_spend(origin.answers_dir()) | {"model": runs.load(run_id)["model"]}
    result["checks"] = citation_checks(classes, docs, shown) | {
        "answers_whose_prompt_no_longer_rebuilds": stale,
        "supplier_named_but_not_commercial": supplier_disagreements(rows),
    }
    hand = None
    if paths["hand"].is_file() and paths["sample"].is_file():
        # The second reading, by a Claude agent with the full text; no person has checked it.
        hand = _read_jsonl(paths["hand"])
        result["second_reading"] = agreement(_read_jsonl(paths["sample"]), hand)
        # The second reading took every environmental particle, so these are the counts it
        # confirms; outside its sample the reader's answer stands.
        fixed = apply_hand(rows, hand)
        confirmed = stats(fixed, classes)
        env = confirmed["environmental_rows"]
        env_papers = sorted(set(fixed.loc[fixed["origin"] == "environmental", "pmcid"]))
        env["whole_sample_papers"] = whole_sample_papers(hand)
        env["conductivity_in_text"] = conductivity_in_text(
            {p: conductivity_sentences(docs[p]) for p in env_papers},
            quotable={p for p in env_papers if licence.read(p).code in licence.QUOTE_ALLOWED},
        )
        result["after_second_reading"] = {
            k: confirmed[k] for k in ("origin", "synthetic", "environment", "environmental_rows")
        } | {"particles_with_a_second_reading": int(len(hand))}
    result["not_own_measurement"] = not_own_rows(table)
    result["lost_methods"] = lost_methods(table, lost)

    paths["rows"].parent.mkdir(parents=True, exist_ok=True)
    with_final(rows, hand)[list(ROW_COLUMNS)].to_csv(paths["rows"], index=False)
    paths["stats"].write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    return result


def _origin_sentences(doc: lines.LinedDoc, cited: origin.Citations, cap: int = 12):
    """Sentences outside the cited lines that name particles next to an origin cue: what a second
    reader needs to catch an origin the reader missed or an "unclear" the paper does answer."""
    skip = set(cited.line_ids)
    found = []
    for line in doc.lines:
        if line.line_id in skip:
            continue
        for sentence in origin._SENTENCE.split(line.text):
            if origin._about_particles(sentence, ()) and origin.cues(sentence).keys() & {
                "supplier",
                "fabrication",
                "collection",
                "ageing",
            }:
                found.append((line.n, sentence))
    return found[:cap]


def write_sample(run_id: str) -> Path:
    """The sample for a second reading, and a packet of every cited line in full to read it from."""
    table = origin.load_table()
    answers = origin.load_answers(origin.answers_dir(), run_id)
    sample = hand_check_sample(classifications(answers))
    paths = _paths(run_id)
    cols = ["pmcid", "particle_name", "stratum", "origin", "environment", "aged_in_lab"]
    with paths["sample"].open("w", encoding="utf-8") as handle:
        for rec in sample[cols + ["citations", "reason"]].to_dict(orient="records"):
            handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
    blocks = []
    for rec in sample.to_dict(orient="records"):
        doc = origin.load_doc(rec["pmcid"])
        rows = table[
            (table["pmcid"] == rec["pmcid"])
            & (table["particle_name"].map(_text) == rec["particle_name"])
        ]
        head = (
            f"### [{rec['stratum']}] {rec['pmcid']} :: {rec['particle_name']}\n"
            f"reader: origin={rec['origin']} environment={rec['environment']} "
            f"aged={rec['aged_in_lab']}\nreason: {rec['reason']}\n"
            f"table supplier: {sorted(set(rows['supplier'].map(_text)))} "
            f"medium: {sorted(set(rows['medium_text'].map(_text)))[:4]}"
        )
        cited = origin.check_citations(doc, rec["citations"])
        body = ["cited:"]
        for token, line_id in zip(cited.resolved, cited.line_ids, strict=True):
            text = lines.resolve_id(doc, line_id).text
            body.append(f"  {token}\t{text if len(text) < 1500 else origin.excerpt(text)}")
        body.append("other origin sentences in the paper:")
        body += [f"  L{n}\t{sentence[:400]}" for n, sentence in _origin_sentences(doc, cited)]
        blocks.append("\n".join([head, *body]))
    paths["packet"].write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    return paths["sample"]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m mnp.report.origin")
    p.add_argument("what", choices=["build", "sample"])
    p.add_argument("--run", default=origin.RUN_ID)
    args = p.parse_args(argv)
    if args.what == "sample":
        print(f"-> {write_sample(args.run)}")
        return 0
    result = build(args.run)
    summary = {k: result[k] for k in ("papers", "rows", "answers", "origin", "synthetic")}
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
