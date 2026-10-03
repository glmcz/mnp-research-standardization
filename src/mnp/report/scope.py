"""The scope block every reader-facing document opens with.

Martin, 2026-09-30: "reveal the truth at the beginning so the scope is clear". REVIEW.md, the
dataset card, the demo's README and METHOD, and the results page each open with the same short
statement of what the dataset is, what a zeta potential can describe, where the particles came
from, which liquids they were measured in, which corpus they were read from, and what the data
can and cannot be used for.

One function renders it for all of them, from the committed tables, so the documents cannot
drift apart and no number in it is typed. The sentences are plain text with backticks for file
names: Markdown takes them as they are, and the page turns the backticks into code spans.
"""

from __future__ import annotations

import pandas as pd

TITLE = "Scope: read this first."
NOTES = "docs/2026-09-30-corpus-scope-notes.md"

# `medium_class` values in the order the block lists them; a class not named here is appended.
LIQUIDS = (
    ("DI_water", "DI water"),
    ("culture_medium", "culture medium"),
    ("salt_solution", "salt solution"),
    ("buffer", "buffer"),
    ("environmental_water", "environmental water"),
    ("biofluid", "biofluid"),
    ("other", "other"),
    ("unreported", "unreported"),
)
# Where a collected particle came from, as the sentence names it. Wastewater leads because it is
# where almost every collected particle in this corpus came from.
PLACES = (
    ("wastewater", "from wastewater effluent"),
    ("freshwater", "from freshwater"),
    ("seawater", "from seawater"),
    ("soil", "from soil"),
    ("sediment", "from sediment"),
    ("air_dust", "from air or dust"),
    ("biota", "from organisms"),
    ("other", 'classed "other"'),
)
# The environments a reader would expect such particles from, said out loud when they are empty.
AMBIENT = (
    ("air_dust", "air or dust"),
    ("freshwater", "freshwater"),
    ("seawater", "seawater"),
    ("soil", "soil"),
    ("sediment", "sediment"),
)


def _int(n: int) -> str:
    return f"{int(n):,}".replace(",", " ")


def _papers(n: int) -> str:
    return f"{n} paper" if n == 1 else f"{n} papers"


def _either(words: list[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " or " + words[-1]


def _both(words: list[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def gather(table: pd.DataFrame, stats: dict, origin: dict | None) -> dict:
    """The counts the block states: the D1 table, `d1_stats.json`, `sample_origin_stats.json`."""
    quantity = table["quantity"].value_counts() if "quantity" in table else pd.Series(dtype=int)
    media = (
        table["medium_class"].fillna("unreported").value_counts()
        if "medium_class" in table
        else None
    )
    den = stats.get("denominators") or {}
    return {
        "rows": len(table),
        "papers": int(table["pmcid"].nunique()),
        "zeta": int(quantity.get("zeta_potential", 0)),
        "mobility": int(quantity.get("electrophoretic_mobility", 0)),
        "media": None if media is None else {str(k): int(v) for k, v in media.items()},
        "hits_all": den.get("all_hits"),
        "hits_oa": den.get("oa_records"),
        "fetched": (stats.get("text_availability") or {}).get("fetched"),
        "with_measurement": stats.get("n_papers"),
        "origin": None if origin is None else _origin_facts(origin),
    }


def _origin_facts(origin: dict) -> dict:
    h = origin["after_second_reading"]
    where = h["environment"]
    return {
        "rows": origin["rows"],
        "synthetic": h["synthetic"]["rows"],
        "env_rows": h["environmental_rows"]["rows"],
        "env_papers": h["environmental_rows"]["papers"],
        "place_rows": {k: int(v) for k, v in where["rows"].items() if k != "null"},
        "place_papers": {k: int(v) for k, v in where["papers"].items()},
    }


def items(f: dict) -> list[tuple[str, str]]:
    """The block as (lead, sentence) pairs, in the order every document shows them."""
    what = f"{_int(f['zeta'])} zeta potentials" + (
        f" and {_int(f['mobility'])} electrophoretic mobilities" if f["mobility"] else ""
    )
    out = [
        (
            "What it is.",
            "The surface charge of micro- and nanoplastic particles as measured in liquids in "
            f"laboratory studies: {_int(f['rows'])} rows from {_int(f['papers'])} papers, "
            f"{what} (`d1_zeta_table.csv`).",
        ),
        (
            "Measured in a liquid.",
            "A zeta potential exists only in a liquid, so every value describes the particle in "
            "the liquid it was measured in, not in the environment it came from.",
        ),
    ]
    if f["origin"]:
        out.append(("Where the particles came from.", _origin_sentence(f["origin"])))
    if f["media"]:
        known = dict(LIQUIDS)
        order = [k for k, _ in LIQUIDS] + sorted(k for k in f["media"] if k not in known)
        shown = [f"{known.get(k, k)} {_int(f['media'].get(k, 0))}" for k in order]
        out.append(("The measurement liquids.", f"Rows per `medium_class`: {', '.join(shown)}."))
    chain = [
        (f["hits_all"], "hits"),
        (f["hits_oa"], "of them open access"),
        (f["fetched"], "full texts fetched"),
        (f["with_measurement"], "papers with a measurement"),
    ]
    steps = ", ".join(f"{_int(n)} {label}" for n, label in chain if n is not None)
    out += [
        (
            "The corpus.",
            "The open-access subset of one database (Europe PMC) for one query: "
            f"{steps} (`d1_stats.json`). What that leaves out: `{NOTES}`.",
        ),
        (
            "What it can be used for.",
            "How laboratory measurements are reported and whether they can be compared. Not how "
            "plastics behave in air, water or soil.",
        ),
    ]
    return out


def _origin_sentence(o: dict) -> str:
    n, syn, k = o["rows"], o["synthetic"], o["env_rows"]
    rows, papers = o["place_rows"], o["place_papers"]
    found = [
        f"{rows[key]} {label} ({_papers(papers.get(key, 0))})"
        for key, label in PLACES
        if rows.get(key)
    ]
    empty = [label for key, label in AMBIENT if not rows.get(key)]
    text = (
        f"{100 * syn / n:.1f} % of rows ({_int(syn)} / {_int(n)}) measure a synthetic particle, "
        "bought or made in a lab. "
    )
    if k:
        verb = "measure particles" if k != 1 else "measures a particle"
        text += (
            f"Only {_int(k)} {'rows' if k != 1 else 'row'}, from {_papers(o['env_papers'])}, "
            f"{verb} collected from a real environment: {_both(found)}. "
        )
    else:
        text += "No row measures a particle collected from a real environment. "
    if empty:
        text += f"From {_either(empty)}: 0 rows. "
    return text + (
        "Agent-checked: a Claude agent gave every environmental particle and samples of the rest "
        "a second reading with the paper's full text; no person has checked these counts "
        "(`sample_origin_stats.json`, REVIEW.md C11)."
    )


def markdown(pairs: list[tuple[str, str]] | list[list[str]]) -> list[str]:
    """The block's lines, with no blank line after it: the caller places it."""
    return [f"**{TITLE}**", "", *(f"- **{lead}** {text}" for lead, text in pairs)]


def block(table: pd.DataFrame, stats: dict, origin: dict | None) -> list[str]:
    return markdown(items(gather(table, stats, origin)))


def extract(text: str) -> str | None:
    """The block as it stands in a rendered document, or None when the document has none."""
    lines = text.splitlines()
    head = f"**{TITLE}**"
    if head not in lines:
        return None
    start = lines.index(head)
    end = start + 2
    while end < len(lines) and lines[end].startswith("- **"):
        end += 1
    return "\n".join(lines[start:end])
