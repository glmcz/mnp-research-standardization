"""Was the plastic particle the thing measured?

Ratified rule S8 (2026-09-15): a zeta potential or mobility measured on something else — a
supernatant, a treated water, a protein, a cell — is not a plastic measurement, however
clearly the paper attributes the shift to the plastic. The case it was written from filtered
its PET particles out at 0.2 µm before every measurement and reported "Zeta Potential of Aβ
When Exposed to MNP"; its own no-plastic control returned the same value.

This module decides nothing. It produces a reviewable list, because the rule is a judgement
about what a paper measured and no regex can settle that. What it can do is make sure the
question is *asked* — a worker reading one paper found this, and the sweep has 443 papers
nobody has read.

The hard part is not finding the shape but not drowning in it: "filtered prior to HPLC
analysis" says nothing about the zeta, and in the first scan 16 of 25 hits were that. So a
removal only counts when the thing it precedes is the measurement itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# What a removal has to precede before it is interesting: the measurement, not some other assay.
_MEASUREMENT = (
    r"(?:zeta|ζ|electrophoretic|electrokinetic|optical measurement|DLS|"
    r"light scattering|size measurement)"
)
_REMOVAL = r"(?:removed?|separated|filtered|centrifuged|discarded|settled out)"

PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    (
        "removed_before_measurement",
        re.compile(
            rf"\b{_REMOVAL}\b[^.]{{0,140}}?\b(?:before|prior to|preceding)\b[^.]{{0,80}}?"
            rf"{_MEASUREMENT}",
            re.IGNORECASE,
        ),
    ),
    (
        "other_material_exposed",
        re.compile(
            rf"{_MEASUREMENT}[- ]?potentials?\s+of\s+(?!(?:the\s+)?(?:PS|PE|PP|PET|PVC|PMMA|"
            rf"plastic|microplastic|nanoplastic|polystyrene|polyethylene|particles?|beads?|MPs?|"
            rf"NPs?|MNPs?))[^.]{{0,40}}?\b(?:when\s+)?(?:exposed|incubated|treated)\b\s*"
            rf"(?:to|with)",
            re.IGNORECASE,
        ),
    ),
    (
        "supernatant_measured",
        re.compile(
            rf"(?:supernatant[^.]{{0,120}}{_MEASUREMENT}|{_MEASUREMENT}[^.]{{0,120}}supernatant)",
            re.IGNORECASE,
        ),
    ),
)


@dataclass(frozen=True)
class Suspicion:
    kind: str
    quote: str


def suspicions(text: str) -> list[Suspicion]:
    """Every reason to ask whether this paper measured its plastic. Never a verdict."""
    if not text:
        return []
    found: list[Suspicion] = []
    for kind, pattern in PATTERNS:
        if m := pattern.search(text):
            found.append(Suspicion(kind, " ".join(m.group(0).split())[:180]))
    return found
