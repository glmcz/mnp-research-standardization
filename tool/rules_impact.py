"""What the three ratified rules (2026-09-13) do to the stored corpus, without re-extracting.

Read-only. Re-runs `verify_row` over every stored measurement under the current rules and
counts how many papers would lose a condition. It writes `out/tables/rules_impact.md`.

Two things it is not:
- a re-extraction. Q2 (an incubation temperature is not the measurement temperature) can
  only be applied properly by a worker reading the paper again; here it is approximated by
  the flags `temperature_step_not_measurement` and `temperature_not_in_evidence`.
- a result for Q1. A paper whose full text holds two or more salt+concentration terms
  *might* yield an ionic strength; whether those salts describe the measurement medium is a
  judgement, so that column is an upper bound on the gain, not the gain.

    uv run python tool/rules_impact.py
"""

from __future__ import annotations

import copy

from mnp import config
from mnp.corpus import lines
from mnp.extract import __main__ as cli
from mnp.extract import coerce, zeta

SCOPE_T = {"temperature_step_not_measurement", "temperature_not_in_evidence"}


def collect() -> dict[str, dict]:
    papers: dict[str, dict] = {}
    for pmcid, rec in cli._load_records(cli._jsonl_path()).items():
        if not rec.measurements:
            continue
        article = cli._article(pmcid)
        text = article.full_text if article else ""
        doc = lines.build_lines(article) if article is not None else None
        s = dict(
            T_now=False,
            T_kept=False,
            pH_now=False,
            pH_kept=False,
            I_now=False,
            composition=len(coerce._salt_terms(text)) >= 2,
        )
        for m in rec.measurements:
            flags = set(zeta.verify_row(copy.deepcopy(m), text, doc))
            c = m.conditions
            if c.temperature_C is not None or c.temperature_qualifier is not None:
                s["T_now"] = True
                # a nominal "room temperature" names no step, so the scope rule cannot move it
                if c.temperature_qualifier is not None or not (SCOPE_T & flags):
                    s["T_kept"] = True
            if c.pH is not None or (c.pH_text and any(ch.isdigit() for ch in c.pH_text)):
                s["pH_now"] = True
                if "pH_not_in_evidence" not in flags:
                    s["pH_kept"] = True
            if c.ionic_strength_mM is not None:
                s["I_now"] = True
        papers[pmcid] = s
    return papers


def markdown(papers: dict[str, dict]) -> str:
    n = len(papers)
    miss = lambda k: sum(1 for s in papers.values() if not s[k])  # noqa: E731
    line = lambda k: f"{k} / {n} = {k / n:.1%}"  # noqa: E731
    i_best = sum(1 for s in papers.values() if not s["I_now"] and not s["composition"])
    return "\n".join(
        [
            "# What the three rules do to the corpus",
            "",
            f"{n} papers with a verified measurement, re-verified under the rules ratified",
            "on 2026-09-13 (`docs/DECISIONS_NEEDED.md`). No paper was re-read; this is the",
            "stored extraction scored against the new rules.",
            "",
            "| Condition | missing now | missing under the rules | rule |",
            "|---|---|---|---|",
            f"| Temperature | {line(miss('T_now'))} | {line(miss('T_kept'))} | Q2 + Q3 |",
            f"| pH | {line(miss('pH_now'))} | {line(miss('pH_kept'))} | Q3 |",
            f"| Ionic strength | {line(miss('I_now'))} | ≥ {line(i_best)} | Q1, upper bound |",
            "",
            "Q1 moves the other way: a printed composition now counts, so the ionic-strength",
            "figure can only fall. The number given is the best case — every paper whose text",
            "holds two or more salt+concentration terms yielding one. Only a re-extraction",
            "settles it.",
            "",
        ]
    )


def main() -> int:
    papers = collect()
    out = config.OUT_TABLES
    out.mkdir(parents=True, exist_ok=True)
    path = out / "rules_impact.md"
    path.write_text(markdown(papers))
    print(markdown(papers))
    print(f"written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
