"""An external judge — a different model family, over an API, with no filesystem access.

Why this exists. Two Claude judges, given the same seventeen disagreements and the same
brief, agreed at **kappa 0.11** (95% CI -0.12 to 0.42) and split systematically on the
contested rule about incubation temperature. Two further problems with an in-family judge:

- **self-preference bias** — models rate their own outputs more favourably, so a Claude judge
  adjudicating a Claude extractor is not a neutral referee;
- **blinding is not enforceable in-repo** — the first judge, while checking how the pipeline
  derived a value, grepped the repository and hit the gold annotations. Eight files contained
  that value.

An API-only judge fixes both structurally: it is a different family, and it has no shell, no
filesystem and no repository. It sees exactly one article and one case.

The prompt follows G-Eval's form-filling discipline (Liu et al. 2023): the task, the two
candidate readings unlabelled, an explicit abstention, and a required verbatim quote that is
checked against the article afterwards.
"""

from __future__ import annotations

import re

VERDICTS = {"A", "B", "neither", "ambiguous"}

SYSTEM = """You adjudicate what a scientific paper reports. You are given one paper and two
candidate readings of a single field, labelled A and B. You are not told where either reading
came from, and you must not speculate about it.

Answer with JSON only:
{"verdict": "A" | "B" | "neither" | "ambiguous", "quote": "<verbatim sentence from the paper
that settles it>", "reasoning": "<one sentence>"}

- "A" or "B": the paper supports that reading.
- "neither": the paper states a different value.
- "ambiguous": the paper genuinely does not determine it. This is a real answer. Do not
  invent a decision to avoid it.

The quote must be copied character for character from the paper. A quote that cannot be found
in the paper invalidates your verdict.

Rules that decide these fields:
- A temperature given for a different step (incubation, exposure, storage) is NOT the
  temperature at which the measurement was made.
- A named salt at a stated concentration gives an ionic strength. "PBS" alone does not,
  unless the paper prints its composition.
- pH is numeric only; a range stays a range."""


def _fmt(value) -> str:
    return "not reported" if value is None else str(value)


def build_user(case: dict, article: str, flip: bool = False) -> str:
    a, b = case["reading_A"], case["reading_B"]
    if flip:
        a, b = b, a
    return (
        f"Field in dispute: {case['field']}\n\n"
        f"Reading A: {_fmt(a)}\n"
        f"Reading B: {_fmt(b)}\n\n"
        f"--- the paper ---\n{article}\n--- end of paper ---\n\n"
        "Which reading does the paper support?"
    )


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def judge_case(client, case: dict, article: str, flip: bool = False) -> dict:
    """One verdict. Never raises: a failure is a recorded outcome, not a gap in the data."""
    user = build_user(case, article, flip)
    try:
        reply = client.complete_json(SYSTEM, user, temperature=0.0)
    except Exception as exc:  # an unreachable judge is a result, not a crash
        return {"case": case["case"], "verdict": "error", "error": str(exc), "flip": flip}
    # LLMClient.complete_json returns (data, completion); a bare dict is also accepted so
    # the harness can be driven by anything that returns parsed JSON.
    if isinstance(reply, tuple):
        reply = reply[0]

    verdict = str(reply.get("verdict", "")).strip()
    quote = str(reply.get("quote", "") or "")
    out = {
        "case": case["case"],
        "verdict": verdict if verdict in VERDICTS else "unparseable",
        "quote": quote,
        "reasoning": str(reply.get("reasoning", "") or "")[:300],
        "grounded": bool(_norm(quote)) and _norm(quote) in _norm(article),
        "flip": flip,
    }
    return out


def run_case_both_orders(client, case: dict, article: str) -> dict:
    """Judge the same case with the readings both ways round, to expose position bias."""
    return {
        "forward": judge_case(client, case, article, flip=False),
        "reversed": judge_case(client, case, article, flip=True),
    }


def to_source(verdict: str, flip: bool) -> str:
    """Translate an A/B verdict into which source it backs.

    Reading A is the first-listed source when not flipped, the second when flipped.
    """
    if verdict in ("ambiguous", "neither", "error", "unparseable"):
        return verdict
    first, second = ("gold", "extraction")
    if verdict == "A":
        return second if flip else first
    return first if flip else second
