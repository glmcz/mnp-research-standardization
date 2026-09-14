"""LLM-as-judge, scored as an inter-rater reliability problem.

Using a model to adjudicate disagreements is only defensible if the judge itself is
measured, and measured the way human coders are. Three findings from the literature shape
this module:

- **Raw agreement is not evidence.** With a skewed label distribution a judge that always
  answers the majority class scores 90%. Cohen's kappa (Cohen 1960) corrects for chance
  agreement; it is the standard for coded data in the social sciences, and the standard we
  borrow here. An interval comes from bootstrap resampling, because kappa on 20 cases is a
  noisy statistic.
- **Position bias is real.** Judges prefer whichever candidate is shown first
  (Zheng et al. 2023, *Judging LLM-as-a-Judge*). Every case is therefore judged twice with
  the two readings swapped, and a judge that changes its answer is reported as inconsistent
  rather than averaged over.
- **A verdict must be grounded.** Following G-Eval's form-filling discipline
  (Liu et al. 2023), the judge must return the verbatim sentence that settles the case. A
  quote that is not in the article means the verdict is unsupported, and it is excluded from
  the score rather than counted as a hit.

Abstention ("the paper does not say") is a first-class label. A judge that cannot abstain
will manufacture a decision, and the rate of genuine ambiguity in the literature is one of
the things this study wants to know.
"""

from __future__ import annotations

import random
import re
from collections import Counter
from collections.abc import Callable

Verdict = dict  # {"verdict": str, "quote": str, ...}
JudgeFn = Callable[[dict, str], Verdict]  # (case, order) -> verdict


# -- agreement -----------------------------------------------------------------------
def raw_agreement(a: list[str], b: list[str]) -> float:
    if not a:
        return 0.0
    return sum(x == y for x, y in zip(a, b, strict=True)) / len(a)


def cohen_kappa(a: list[str], b: list[str]) -> float | None:
    """Chance-corrected agreement. None when neither rater varies — kappa is undefined
    there, and reporting 1.0 would claim perfect agreement on no information."""
    if not a or len(a) != len(b):
        return None
    labels = sorted(set(a) | set(b))
    if len(labels) < 2:
        return None
    n = len(a)
    po = raw_agreement(a, b)
    ca, cb = Counter(a), Counter(b)
    pe = sum((ca[x] / n) * (cb[x] / n) for x in labels)
    if pe == 1.0:
        return None
    return (po - pe) / (1 - pe)


def bootstrap_ci(
    a: list[str], b: list[str], n: int = 1000, seed: int = 0, alpha: float = 0.05
) -> tuple[float, float]:
    """Percentile bootstrap interval for kappa. Kappa on a few dozen cases is noisy, and a
    point estimate without an interval invites over-reading."""
    rng = random.Random(seed)
    idx = range(len(a))
    samples = []
    for _ in range(n):
        pick = [rng.choice(idx) for _ in idx]
        k = cohen_kappa([a[i] for i in pick], [b[i] for i in pick])
        if k is not None:
            samples.append(k)
    if not samples:
        return (0.0, 0.0)
    samples.sort()
    lo = samples[int(alpha / 2 * len(samples))]
    hi = samples[min(len(samples) - 1, int((1 - alpha / 2) * len(samples)))]
    return (lo, hi)


# -- bias and grounding --------------------------------------------------------------
def order_consistency(forward: dict[str, str], reversed_: dict[str, str]) -> dict:
    """How often the judge gives the same answer when the readings are swapped."""
    shared = sorted(set(forward) & set(reversed_))
    flipped = [c for c in shared if forward[c] != reversed_[c]]
    return {
        "cases": len(shared),
        "consistent": len(shared) - len(flipped),
        "flipped": flipped,
        "consistency": (len(shared) - len(flipped)) / len(shared) if shared else None,
    }


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def grounded(quote: str, article: str) -> bool:
    """Is the quote actually in the article? An unsupported verdict is not a verdict."""
    q = _norm(quote)
    return bool(q) and q in _norm(article)


def filter_grounded(verdicts: dict[str, Verdict], articles: dict[str, str]):
    kept, dropped = {}, []
    for case, v in verdicts.items():
        if grounded(v.get("quote", ""), articles.get(case, "")):
            kept[case] = v
        else:
            dropped.append(case)
    return kept, dropped


# -- the run -------------------------------------------------------------------------
def run(cases: list[dict], judge_fn: JudgeFn, key: dict[str, str] | None = None) -> dict:
    """Judge every case in both orders, then report reliability rather than a bare score.

    `judge_fn(case, order)` returns {"verdict": str, "quote": str}; `order` is "gold_first"
    or "extraction_first" so the caller can present the two readings either way round.
    """
    forward: dict[str, Verdict] = {}
    backward: dict[str, Verdict] = {}
    for case in cases:
        cid = case["case"]
        forward[cid] = judge_fn(case, "gold_first")
        backward[cid] = judge_fn(case, "extraction_first")

    articles = {c["case"]: c.get("article", "") for c in cases}
    kept, ungrounded = filter_grounded(forward, articles)
    consistency = order_consistency(
        {c: v["verdict"] for c, v in forward.items()},
        {c: v["verdict"] for c, v in backward.items()},
    )

    result = {
        "n_cases": len(cases),
        "ungrounded": ungrounded,
        "order_consistency": consistency["consistency"],
        "order_flipped": consistency["flipped"],
        "verdicts": {c: v["verdict"] for c, v in forward.items()},
        "n_scored": 0,
        "agreement": None,
        "kappa": None,
        "kappa_ci": None,
    }
    if not key:
        return result

    # score only cases that are grounded, answered by the key, and order-stable
    scorable = [c for c in kept if c in key and c not in consistency["flipped"]]
    if not scorable:
        return result
    judged = [kept[c]["verdict"] for c in scorable]
    truth = [key[c] for c in scorable]
    result.update(
        n_scored=len(scorable),
        agreement=raw_agreement(truth, judged),
        kappa=cohen_kappa(truth, judged),
        kappa_ci=bootstrap_ci(truth, judged) if len(scorable) > 2 else None,
    )
    return result


def markdown(result: dict) -> str:
    lines = ["# LLM judge — reliability", ""]
    k, ci = result.get("kappa"), result.get("kappa_ci")
    if result["n_scored"]:
        k_txt = "undefined" if k is None else f"{k:.2f}"
        ci_txt = f" (95% CI {ci[0]:.2f}–{ci[1]:.2f})" if ci else ""
        lines += [
            f"Scored on {result['n_scored']} of {result['n_cases']} cases.",
            "",
            f"- raw agreement with the key: **{result['agreement']:.0%}**",
            f"- Cohen's kappa: **{k_txt}**{ci_txt}",
        ]
    else:
        lines += [
            f"**Not scored.** {result['n_cases']} cases judged, but no answer key was "
            "supplied, so there is nothing to measure agreement against.",
        ]
    oc = result.get("order_consistency")
    if oc is not None:
        lines.append(f"- order consistency (position-bias check): **{oc:.0%}**")
        if result["order_flipped"]:
            lines.append(f"  - flipped when swapped: {', '.join(result['order_flipped'])}")
    if result["ungrounded"]:
        lines.append(
            f"- **{len(result['ungrounded'])} verdicts were ungrounded** (quote not found in "
            f"the article) and excluded: {', '.join(result['ungrounded'][:8])}"
        )
    lines += [
        "",
        "Interpretation follows Landis & Koch (1977): kappa below 0.40 is poor, 0.40–0.60 "
        "moderate, 0.60–0.80 substantial, above 0.80 almost perfect. A judge below "
        "substantial should not adjudicate unreviewed.",
    ]
    return "\n".join(lines) + "\n"
