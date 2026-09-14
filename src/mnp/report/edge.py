"""Gate 2 — score a persona's judgement against the human answer key.

`tests/edge/key.yaml` holds Martin's decisions on 27 real papers where the pipeline was
wrong, right by luck, or where two careful readers could differ. Those decisions are his to
make: the personas currently encode one reading of the material boundary, of whether a cited
value counts, of whether an incubation temperature counts, and that reading has never been
ratified by anyone.

Until a case is answered it is **not scored**. An empty key must never read as agreement.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

# Verdicts are free text so a human can write naturally; these fold the spellings that mean
# the same thing, so "does_not_count" and "does not count" are not a disagreement.
_CANON = [
    (r"ambig|cannot say|does not say|unclear", "ambiguous"),
    (r"not[\s_-]*report|unreport", "not reported"),
    (r"report", "reported"),
    (r"(does|do)[\s_-]*not[\s_-]*count|exclude|no\b", "does not count"),
    (r"count|include|yes\b", "counts"),
]


def canon(verdict: str | None) -> str | None:
    """Fold a written verdict onto its meaning, or return it lowercased if it is neither."""
    if verdict is None:
        return None
    v = verdict.strip().lower()
    if not v:
        return None
    for pattern, name in _CANON:
        if re.search(pattern, v):
            return name
    return v


def load_key(path: str | Path) -> dict[str, dict]:
    return yaml.safe_load(Path(path).read_text()) or {}


def score(key_path: str | Path, persona: dict[str, str]) -> dict:
    """Compare persona verdicts with the key. Unanswered cases are excluded, not assumed."""
    key = load_key(key_path)
    answered = {c: v for c, v in key.items() if canon((v or {}).get("verdict"))}
    agree, disagreements = 0, []
    for case, entry in answered.items():
        want = canon(entry["verdict"])
        got = canon(persona.get(case))
        if want == got:
            agree += 1
        else:
            disagreements.append(
                {"case": case, "key": entry["verdict"], "persona": persona.get(case)}
            )
    return {
        "cases": len(key),
        "answered": len(answered),
        "agree": agree,
        "agreement": agree / len(answered) if answered else None,
        "scored": bool(answered),
        "disagreements": disagreements,
    }


def markdown(result: dict) -> str:
    if not result["scored"]:
        return (
            f"# Gate 2 — edge cases\n\n"
            f"**Not scored.** {result['cases']} cases exist and none is answered yet: "
            "`tests/edge/key.yaml` is the human's decisions, and an empty key is not "
            "agreement — the cases are **not yet answered**. Answer them and re-run.\n"
        )
    lines = [
        "# Gate 2 — edge cases",
        "",
        f"Agreement with the answer key: **{result['agreement']:.0%}** "
        f"({result['agree']} of {result['answered']} answered; "
        f"{result['cases'] - result['answered']} not yet answered).",
        "",
    ]
    if result["disagreements"]:
        lines += ["| Case | key says | persona said |", "|---|---|---|"]
        lines += [
            f"| {d['case']} | {d['key']} | {d['persona'] or '—'} |" for d in result["disagreements"]
        ]
    return "\n".join(lines) + "\n"
