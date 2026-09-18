"""E1 — the representation bake-off, over the 50 gold papers.

The table this writes was published in `docs/FINDINGS.md` from a script that lived in a
scratchpad and is gone. Every ratio in E1b multiplies its constants, so until now the whole
chain rested on six numbers nobody could regenerate. This is the experiment, re-run from the
vendored corpus with the tokeniser declared: deterministic, offline, a couple of seconds.

The published figures are carried in `PUBLISHED` and printed beside the measured ones. They
are a historical constant, not a target — nothing here is fitted to them, and where the two
disagree the disagreement is the finding.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from mnp import config
from mnp.corpus import jats, represent

# docs/FINDINGS.md E1, as published: mean tokens per paper, cl100k_base, 50 gold papers.
PUBLISHED: dict[str, int] = {
    "xml_raw": 41127,
    "text_current": 5273,
    "md_plain": 5273,
    "md_anchored": 5309,
    "md_linenum": 5373,
    "md_spanids": 5908,
    "ir_json": 7626,
}


def measure(pmcids: list[str], xml_dir: Path) -> pd.DataFrame:
    """One row per paper, one column per arm. Missing XML is skipped, not guessed at."""
    rows = []
    for pmcid in pmcids:
        path = xml_dir / f"{pmcid}.xml"
        if not path.is_file():
            continue
        raw = path.read_bytes()
        counts = represent.token_counts(jats.parse(raw), raw.decode("utf-8"))
        rows.append({"pmcid": pmcid, **counts})
    return pd.DataFrame(rows, columns=["pmcid", *represent.ARMS])


def composition(pmcids: list[str], xml_dir: Path) -> pd.DataFrame:
    """`md_plain`'s cost split by block kind — the table behind E1's published correction."""
    rows = []
    for pmcid in pmcids:
        path = xml_dir / f"{pmcid}.xml"
        if path.is_file():
            rows.append(represent.block_tokens(jats.parse(path.read_bytes())))
    return pd.DataFrame(rows, columns=list(represent.BLOCK_KINDS))


def markdown(df: pd.DataFrame, blocks: pd.DataFrame) -> str:
    plain = df["md_plain"].mean()
    out = [
        "# E1 — representation bake-off\n",
        f"\n{len(df)} gold papers, `{represent.ENCODING}`, one shared block set "
        "(`mnp.corpus.represent`).\n",
        "\nEvery markdown and JSON arm is built from the same lines of the same parse, so only "
        "the serialisation differs. `md_plain` reproducing `text_current` to the token is the "
        "check that the block set is the parser's own and not a second copy of it.\n",
        "\n| representation | tok/paper | median | × md_plain | addressable to | E1 published |"
        " Δ |\n|---|---|---|---|---|---|---|\n",
    ]
    for arm in represent.ARMS:
        mean, median = df[arm].mean(), df[arm].median()
        was = PUBLISHED[arm]
        out.append(
            f"| `{arm}` | {mean:,.0f} | {median:,.0f} | {mean / plain:.2f} | "
            f"{represent.ADDRESSABLE[arm]} | {was:,} | {(mean - was) / was:+.1%} |\n"
        )
    total = blocks.sum(axis=1).mean()
    out.append(
        "\n## What the tokens are spent on\n"
        "\nBlock kinds of `md_plain`, header and body together. The keyword windows are the "
        "block a first pass of E1 omitted, which is how `md_anchored` came to be reported at "
        "0.72× — cheaper than the document it decorates.\n"
        "\n| block kind | tok/paper | share |\n|---|---|---|\n"
    )
    for kind in represent.BLOCK_KINDS:
        mean = blocks[kind].mean()
        out.append(f"| {kind} | {mean:,.0f} | {mean / total:.1%} |\n")
    out.append(f"| **all blocks** | **{total:,.0f}** | |\n")
    return "".join(out)


def build(tables: Path) -> list[Path]:
    gold_path = config.ANNOTATION / "gold_50.csv"
    if not gold_path.is_file():
        raise FileNotFoundError(f"{gold_path} missing — run `extract gold-merge` first")
    pmcids = sorted(pd.read_csv(gold_path)["pmcid"].dropna().unique())
    df = measure(pmcids, config.EPMC_XML_DIR)
    if df.empty:
        raise FileNotFoundError(
            f"no gold XML under {config.EPMC_XML_DIR} — run `corpus restore` first"
        )
    blocks = composition(pmcids, config.EPMC_XML_DIR)
    tables.mkdir(parents=True, exist_ok=True)
    csv_path, md_path = tables / "e1_representation.csv", tables / "e1_representation.md"
    df.to_csv(csv_path, index=False)
    md_path.write_text(markdown(df, blocks))
    return [csv_path, md_path]
