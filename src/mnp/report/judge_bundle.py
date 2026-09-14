"""Self-contained case bundles, so an adjudicating judge cannot look up the answer.

The first judge run was blind by construction — two readings labelled A and B, order flipped
between judges, the mapping stored separately — and it leaked anyway. The judge grepped the
repository for a value while checking how the pipeline derived it, and hit the gold
annotations and the counterpart order file. Eight files contained that value.

The lesson is that blinding by naming does not survive a grep. A judge that can read the
repository can find the gold set, whether or not it means to. So the judge is given a
directory containing the article text and the case, and nothing else; the mapping between
readings and their sources is written somewhere the judge has no reason to look.

This is necessary but not sufficient: an agent with shell access can still reach the repo if
it is told where it is. Run judges with worktree isolation, or on a machine that has only the
bundle, when the verdict has to be defensible.
"""

from __future__ import annotations

import json
from pathlib import Path

from mnp import config

README = """# Adjudication bundle

Everything you need is here. Do not look anywhere else — not at the repository, not at any
other directory. If you cannot answer from `articles/` and `cases.json`, the answer is
`ambiguous`, and that is a real answer.

- `cases.json` — each case gives a paper, a field, and two candidate readings, **A** and
  **B**. You are not told where either came from. Do not try to work it out.
- `articles/<PMCID>.txt` — the text of each paper, exactly as the pipeline sees it.

For each case decide which reading the paper supports: `A`, `B`, `neither` (the paper
supports some third value), or `ambiguous` (the paper does not determine it). Quote the
verbatim sentence that settles it; the quote is checked against the article, and a verdict
whose quote cannot be found is discarded rather than counted.
"""


def write(
    cases: list[dict],
    articles: dict[str, str],
    out_dir: str | Path,
    judge: str,
    mapping_dir: str | Path | None = None,
) -> Path:
    """Write one judge's bundle. `judge="b"` presents the readings in the opposite order."""
    out = Path(out_dir)
    interim = Path(config.DATA_INTERIM).resolve()
    try:
        out.resolve().relative_to(interim)
        raise ValueError(
            f"refusing to write a judge bundle inside {interim}: the judge must not be able "
            "to reach the gold annotations"
        )
    except ValueError as exc:
        if "refusing" in str(exc):
            raise

    flip = judge.lower().endswith("b")
    public, mapping = [], {}
    for c in cases:
        a, b = c["reading_A"], c["reading_B"]
        if flip:
            a, b = b, a
        public.append(
            {
                "case": c["case"],
                "pmcid": c["pmcid"],
                "field": c["field"],
                "reading_A": a,
                "reading_B": b,
            }
        )
        mapping[c["case"]] = "A_is_extraction" if flip else "A_is_gold"

    out.mkdir(parents=True, exist_ok=True)
    (out / "cases.json").write_text(json.dumps(public, indent=2) + "\n")
    (out / "README.md").write_text(README)
    art = out / "articles"
    art.mkdir(exist_ok=True)
    for pmcid in sorted({c["pmcid"] for c in cases}):
        (art / f"{pmcid}.txt").write_text(articles.get(pmcid, ""))

    keys = Path(mapping_dir) if mapping_dir else Path(out).parent / "_keys"
    keys.mkdir(parents=True, exist_ok=True)
    (keys / f"{judge}.mapping.json").write_text(json.dumps(mapping, indent=2) + "\n")
    return out
