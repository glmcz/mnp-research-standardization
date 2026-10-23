"""Prompts, the Claude call, and the grounding check for every arm of the experiment.

Every arm answers in the same contract (CONTRACT) through the same pinned reader, so arms differ
only in what they are given and what code does around the model:

- N0  closed-book: the question alone
- N2  naive: the question and the data a person would paste into a chat (`packet`)
- H   hybrid: a planner picks an operation, code runs it, the guard rules, a composer phrases it,
      and code rejects any number the composer did not get from the result
- Hg  hybrid without the guard: the composer sees the result but decides the verdict itself
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tool" / "p2"))
import extension as ext  # noqa: E402
import ops  # noqa: E402

from mnp.eval import grid  # noqa: E402

MODEL = grid.READER_MODEL
#: One system prompt for every arm. grid.SYSTEM_PROMPT says "only the evidence in the user
#: message", which would tie the closed-book arm's hands, so the arms share a neutral one.
SYSTEM = (
    "You answer one question about microplastic survey data or nanoplastic measurements. "
    "Follow the output contract in the user message exactly."
)
CONTRACT = """OUTPUT
Exactly one JSON object, nothing else:
{"value": <number or null>, "verdict": "allow" | "caveat" | "refuse",
 "caveats": [<zero or more of: %s>],
 "answer": "<at most two sentences>"}
- value: the number the question asks for, or null when no number answers it.
- verdict: allow = the number or conclusion holds as asked; caveat = a number can be given, but a
  listed reason limits what it shows; refuse = the data cannot support the comparison or
  conclusion the question asks about.
- caveats: the reasons behind a caveat or a refusal, from the list only.""".replace(
    "%s", ", ".join(ops.CAVEATS)
)

_NUM = re.compile(r"(?<![\w.])[-−]?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?")
#: A DOI's digits are an identifier, never a quantity: they may not ground a number.
_DOI = re.compile(r"10\.\d{4,9}/\S+")


# -- the model ----------------------------------------------------------------------------------


def ask(prompt: str, model: str = MODEL) -> grid.Reply:
    """grid.read with the shared system prompt: same CLI flags, cwd guard, parsing and pin."""
    cmd = grid.reader_command(model)
    cmd[cmd.index("--system-prompt") + 1] = SYSTEM
    cwd = grid.reader_cwd()
    if grid.instruction_files_above(cwd):
        raise grid.ReaderError("instruction files above the reader's cwd")
    try:
        done = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True, cwd=cwd, timeout=grid.TIMEOUT_S
        )
    except subprocess.TimeoutExpired as exc:
        raise grid.ReaderError(f"timed out after {grid.TIMEOUT_S} s") from exc
    if done.returncode != 0 and not done.stdout.strip():
        raise grid.ReaderError(f"exit {done.returncode}: {done.stderr.strip()[-300:]}")
    return grid.parse_cli_output(done.stdout, model)


def parse(text: str) -> dict | None:
    """The first JSON object in a reply, or None. A malformed answer is scored, not repaired."""
    start = text.find("{")
    while start != -1:
        depth = 0
        for i, ch in enumerate(text[start:], start):
            depth += ch == "{"
            depth -= ch == "}"
            if depth == 0:
                try:
                    out = json.loads(text[start : i + 1])
                    return out if isinstance(out, dict) else None
                except json.JSONDecodeError:
                    break
        start = text.find("{", start + 1)
    return None


# -- what each arm is given ---------------------------------------------------------------------


def _csv(df: pd.DataFrame) -> str:
    return df.to_csv(index=False, float_format="%.6g")


def packet(name: str) -> str:
    """The data a naive user would paste: a table that fits in a chat, never the whole database."""
    if name == "none":
        return ""
    if name == "ncei_studies":
        import build as p2

        studies, _, _ = p2.ncei()
        s = studies[studies.setting == "Ocean water"]
        cols = [
            "doi",
            "ref",
            "org",
            "region",
            "methods",
            "n",
            "date_first",
            "date_last",
            "lat",
            "lon",
            "lower_um_min",
            "conc_p10",
            "conc_median",
            "conc_p90",
        ]
        return "NCEI ocean-water studies, one row per study (pieces/m3):\n" + _csv(s[cols])
    if name == "pair_records":
        t = ops.survey()
        g = t[t.study.astype(str).str.contains("0080466|0111913", regex=True)]
        g = g[g.setting == "Ocean water"]
        return "NCEI records of the two studies:\n" + _csv(
            g[["study", "date", "lat", "lon", "method", "value"]]
        )
    if name == "weser":
        w, win = ext.weser()
        return (
            f"Weser stations; small = {win['small_um']} um, large = {win['large_um']} um "
            "(particles/m3):\n" + _csv(w[["station", "date", "small", "large"]])
        )
    if name == "zeta":
        z = ops.zeta()
        cols = ["pmcid", "material_group", "surface", "size_nm", "zeta_mV", "medium_class"]
        return "Zeta potentials from the literature, one row per value:\n" + _csv(z[cols])
    if name == "d1_conditions":
        t = ops.d1()
        flags = [c for c in t.columns if c.endswith("_reported")]
        by = t.groupby("pmcid")[flags].agg(lambda s: (s == "True").any()).reset_index()
        return "Per paper: does any zeta row state each condition?\n" + _csv(by)
    if name == "case14":
        t = ops.d1()
        rows = t[t.row_id.isin(["PMC10260929-r1", "PMC13298883-r1"])]
        cols = [c for c in t.columns if not c.startswith("evidence")][:24]
        return "The two rows:\n" + _csv(rows[cols])
    if name == "datasets_fields":
        t = ops.survey()
        parts = []
        for ds, g in t.groupby("dataset"):
            parts.append(f"{ds}: {len(g)} records; three examples:\n" + _csv(g.head(3)))
        return "\n".join(parts)
    raise KeyError(name)


def naive_prompt(question: str, data: str) -> str:
    body = (
        f"DATA\n{data}"
        if data
        else "No data is attached. Answer from what you know about the published literature."
    )
    return f"QUESTION\n{question}\n\n{body}\n\n{CONTRACT}"


def planner_prompt(question: str) -> str:
    return (
        f"QUESTION\n{question}\n\nOPERATIONS (code runs one of these on the full source data; "
        f"you choose which, and with what arguments)\n{ops.registry_text()}\n\nOUTPUT\n"
        'Exactly one JSON object: {"op": "<name>", "args": {<argument>: <value>, ...}}. '
        "Use a study's DOI when an operation takes a study. Choose the operation whose result "
        "answers the question most directly."
    )


def composer_prompt(
    question: str, result_json: str, verdict: str | None, reasons: list[str]
) -> str:
    rule = (
        f"\n\nGUARD (code, from the result's diagnostics): verdict={verdict}; reasons="
        f"{', '.join(reasons) or 'none'}. Use this verdict and these reasons."
        if verdict is not None
        else ""
    )
    return (
        f"QUESTION\n{question}\n\nRESULT (computed by code over the full source data)\n"
        f"{result_json}{rule}\n\nUse only numbers that appear in RESULT or in the question.\n\n"
        f"{CONTRACT}"
    )


# -- the grounding check ------------------------------------------------------------------------


def numbers_in(text: str) -> list[float]:
    out = []
    for m in _NUM.finditer(_DOI.sub(" ", text or "")):
        s = m.group(0).replace("−", "-").replace(",", ".")
        try:
            out.append(float(s))
        except ValueError:
            continue
    return out


def _matches(x: float, allowed: list[float]) -> bool:
    for a in allowed:
        for cand in (a, a * 100, a / 100):  # a share may be written as a percentage
            if np.isclose(x, cand, rtol=0.02, atol=0.006) or (
                abs(cand) >= 1 and abs(x - round(cand)) < 0.5 and abs(x) >= 1
            ):
                return True
    return False


def ungrounded(answer: dict, allowed: list[float]) -> list[float]:
    """Numbers in the answer that are neither in the result nor in the question."""
    found = numbers_in(str(answer.get("answer", "")))
    if isinstance(answer.get("value"), int | float):
        found.append(float(answer["value"]))
    return [x for x in found if not _matches(x, allowed)]
