"""A blinded sheet for Martin: for each question, two answers in random order, no truth shown.

The experiment's answer key is computed by code. This sheet is the human check of that key: for
each question Martin marks which answer is right (A, B, both, neither, or unsure). The key that
says which answer came from which arm is written apart, so the sheet can be filled blind.

    uv run --with openpyxl python tool/hybrid/adjudication.py
    # out/review/hybrid_adjudication.md (the sheet), data/interim/runs/hy-adjudication-key.json
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import questions  # noqa: E402
import run  # noqa: E402

SHEET = ROOT / "out/review/hybrid_adjudication.md"
KEY = ROOT / "data/interim/runs/hy-adjudication-key.json"
SEED = 20261023
ARMS = ("H", "N2")


def _show(a: dict | None) -> str:
    if not a:
        return "_no answer (the arm abstained)_"
    caveats = ", ".join(a.get("caveats") or []) or "none"
    return (
        f"- value: `{a.get('value')}`\n- verdict: **{a.get('verdict')}**, reasons: {caveats}\n"
        f"- says: {a.get('answer', '')}"
    )


def main() -> None:
    rng = random.Random(SEED)
    intro = (
        "For each question, mark **A**, **B**, **both** or **neither** after `Your call:`. "
        "Judge the number and the verdict: should the comparison be allowed, caveated, or "
        "refused? If you cannot tell, write **unsure** and, if you like, why: never guess, "
        "because a guess is counted as a judgement and an unsure is not. "
        "Do not open `data/interim/runs/hy-adjudication-key.json` until you are done.\n"
    )
    key: dict = {}
    parts = ["# Which answer is right? (blind)\n", intro]
    for q in questions.read():
        recs = {arm: json.loads(run.path(arm, 1, q.qid).read_text()) for arm in ARMS}
        order = list(ARMS)
        rng.shuffle(order)
        key[q.qid] = {"A": order[0], "B": order[1]}
        parts += [
            f"## {q.qid}. {q.text}\n",
            f"**Answer A**\n{_show(recs[order[0]].get('answer'))}\n",
            f"**Answer B**\n{_show(recs[order[1]].get('answer'))}\n",
            "Your call: \n",
        ]
    SHEET.parent.mkdir(parents=True, exist_ok=True)
    SHEET.write_text("\n".join(parts), encoding="utf-8")
    KEY.write_text(json.dumps(key, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {SHEET} ({len(key)} questions) and {KEY}")


if __name__ == "__main__":
    main()
