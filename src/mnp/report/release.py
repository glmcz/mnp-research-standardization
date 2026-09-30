"""The vanilla dataset release: parquet, JSONL, the schema, and a card that reads its own numbers.

Every statistic on the card is computed here, at build time, from the table and from
`d1_stats.json`. Not one is written into the template. This repository has already published
tables that no longer followed from the data behind them, and the defect always has the same
shape: a number was right when it was typed and nobody re-derived it. A dataset card is the
worst place for that, because a card is what a stranger cites without ever seeing the data.

Two consequences in the code below. The card never interpolates a literal it could get wrong —
where a number appears, it came out of the table or the stats file on this run. And the build
*refuses* when the stats file does not describe the table beside it: a silent mismatch between
the two is exactly how a card starts lying.

The schema is not re-written here either. It is generated from the pydantic models by
`mnp.schema.export`, which is the same call `d2` makes, so there is one schema in the repository
and the release ships a byte-identical copy of it.

The licence decision of 2026-09-28 is applied here too. The dataset is CC BY 4.0; a verbatim
quote ships only when its source is CC BY or CC0, read from the vendored XML by
`mnp.corpus.licence`. Every other quote is replaced by its address in the source and the
sha256 of the original — and the build refuses outright if any such address does not give the
quote back exactly, because a quote that is neither shipped nor recoverable is evidence deleted
without anyone deciding to delete it.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path

import numpy as np
import pandas as pd

from mnp.corpus.licence import CODES, QUOTE_ALLOWED, Licence
from mnp.corpus.lines import LinedDoc
from mnp.extract.zeta import OTHER_STEP_TEMPERATURE, STEP_TEMPERATURE, ZERO_IONIC_STRENGTH
from mnp.report import quotes, scope
from mnp.report.reproduce import sha256_file
from mnp.schema import export

DATASET_NAME = "MNP-KB v0"
DATASET_TITLE = (
    f"{DATASET_NAME} — micro- and nanoplastic surface measurements, with absence recorded"
)
LICENCE_NAME = "Creative Commons Attribution 4.0 International"
LICENCE_SHORT = "CC BY 4.0"
LICENCE_URL = "https://creativecommons.org/licenses/by/4.0/"
# Neither this card nor pyproject.toml names an author, and a licence's attribution line is
# not the place to guess one. Set it here and the card and LICENSE follow.
AUTHOR: str | None = None

# Released after `evidence_line_ids`, in this order.
RELEASE_COLUMNS = (
    "evidence_quote_sha256",
    "evidence_quote_spans",
    "quote_withheld",
    "source_licence",
)

# Row-level condition columns, in the order D1 reports them.
CONDITIONS = (
    ("medium_reported", "Dispersion medium"),
    ("ionic_strength_reported", "Ionic strength"),
    ("pH_reported", "pH"),
    ("temperature_reported", "Temperature"),
    ("instrument_reported", "Instrument"),
)

# The grouping of `PLAN_2026-09-28.md` §2. Anything not named here is still listed on the
# card, under "ungrouped" — a column nobody described is a column nobody is checking.
COLUMN_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("study", ("pmcid", "doi", "year", "journal", "row_id")),
    ("measurement", ("quantity", "value", "value_text", "unit", "sd", "n")),
    (
        "particle",
        (
            "particle_name",
            "material",
            "functionalisation",
            "supplier",
            "size_nominal_nm",
            "size_measured_nm",
        ),
    ),
    (
        "conditions",
        (
            "medium_text",
            "medium_class",
            "ionic_strength_mM",
            "pH",
            "pH_text",
            "temperature_C",
            "temperature_qualifier",
            "instrument",
        ),
    ),
    (
        "absence",
        (
            "medium_reported",
            "ionic_strength_reported",
            "pH_reported",
            "temperature_reported",
            "instrument_reported",
            "conditions_complete",
            "ionic_strength_source",
            "medium_matches_exposure",
        ),
    ),
    (
        "evidence",
        (
            "evidence_quote",
            "evidence_location",
            "evidence_verified",
            "evidence_line_ids",
            "evidence_quote_sha256",
            "evidence_quote_spans",
        ),
    ),
    ("licence", ("source_licence", "quote_withheld")),
    ("provenance", ("model", "prompt_sha256", "flags")),
)

ABSENT = "not present in this tree"


def _pct(k: int, n: int) -> float:
    return 100.0 * k / n if n else 0.0


def _kn(k: int, n: int) -> str:
    """The one rendering of a proportion on this card, so a stale one is greppable."""
    return f"{k} / {n} — {_pct(k, n):.1f} %"


def _plain(value):
    """A pandas cell as something `json.dumps` will accept, with NaN as null.

    `not measured` must not survive serialisation as a number, and it must not survive as the
    bare `NaN` literal either: that is invalid JSON everywhere except Python.
    """
    if isinstance(value, np.generic):
        value = value.item()
    try:
        if value is None or pd.isna(value):
            return None
    except (TypeError, ValueError):  # arrays and other non-scalars are not null
        pass
    return value


def records(table: pd.DataFrame) -> list[dict]:
    return [{k: _plain(v) for k, v in row.items()} for row in table.to_dict(orient="records")]


def check_agrees(table: pd.DataFrame, stats: dict) -> None:
    """The stats file must describe the table beside it, or neither number means anything."""
    rows = stats.get("n_rows_total")
    if rows is not None and int(rows) != len(table):
        raise ValueError(
            f"d1_stats.json says n_rows_total={rows} but the table has {len(table)} rows; "
            "one of them is stale — rebuild d1 before releasing"
        )
    papers = stats.get("n_papers")
    if papers is not None and "pmcid" in table.columns and int(papers) != table["pmcid"].nunique():
        raise ValueError(
            f"d1_stats.json says n_papers={papers} but the table has "
            f"{table['pmcid'].nunique()}; one of them is stale — rebuild d1 before releasing"
        )


def corpus_facts(archive: Path | None, manifest: Path | None) -> dict:
    """Size, hash and file count of the vendored corpus, or an explicit absence."""
    out: dict = {"files": None, "bytes": None, "sha256": None}
    if archive is not None and Path(archive).is_file():
        out["bytes"] = Path(archive).stat().st_size
        out["sha256"] = sha256_file(Path(archive))
    if manifest is not None and Path(manifest).is_file():
        out["files"] = sum(1 for line in Path(manifest).read_text().splitlines() if line.strip())
    return out


def withhold(
    table: pd.DataFrame,
    licences: Mapping[str, Licence],
    documents: Callable[[str], LinedDoc | None] | None = None,
) -> pd.DataFrame:
    """The licence decision applied to the table: every quote hashed, the unshippable addressed.

    `documents` gives a paper's line-addressed text; it is called only for papers whose quotes
    are withheld. A paper with no licence decision, or a withheld quote the address cannot give
    back byte for byte, refuses the build — before anything is written.
    """
    undecided = sorted(set(table["pmcid"].dropna()) - set(licences))
    if undecided:
        raise ValueError(
            f"no licence decision for {len(undecided)} papers ({', '.join(undecided[:10])}); "
            "a quote whose source licence is unknown cannot be released or withheld knowingly"
        )
    out = table.copy()
    code = out["pmcid"].map(lambda p: licences[p].code)
    withheld = ~code.isin(QUOTE_ALLOWED)
    quote = out["evidence_quote"] if "evidence_quote" in out else pd.Series(None, index=out.index)
    cited = out["evidence_line_ids"] if "evidence_line_ids" in out else None
    spans: list[str | None] = [None] * len(out)
    docs: dict[str, LinedDoc | None] = {}
    unrestorable: list[str] = []
    for pos in np.flatnonzero(withheld.to_numpy()):
        text = quote.iloc[pos]
        if not isinstance(text, str):
            continue
        pmcid = out["pmcid"].iloc[pos]
        if pmcid not in docs:
            docs[pmcid] = documents(pmcid) if documents is not None else None
        doc = docs[pmcid]
        ids = cited.iloc[pos] if cited is not None else None
        prefer = ids.split(";") if isinstance(ids, str) else ()
        pieces = quotes.address(doc, text, prefer=prefer) if doc is not None else None
        if (
            pieces is None
            or quotes.restore(doc, pieces) != text
            or not quotes.glue_is_clean(pieces)
        ):
            why = "no source document" if doc is None else "not in any line of its source"
            unrestorable.append(f"{out['row_id'].iloc[pos]} ({pmcid}: {why})")
            continue
        spans[pos] = quotes.dumps(pieces)
    if unrestorable:
        raise ValueError(
            f"{len(unrestorable)} withheld quotes cannot be restored from their sources: "
            f"{'; '.join(unrestorable[:10])}. Refusing to release rows whose evidence would be "
            "neither shipped nor recoverable — run `corpus restore`, or re-locate these quotes"
        )
    added = {
        "evidence_quote_sha256": [
            quotes.sha256_text(q) if isinstance(q, str) else None for q in quote
        ],
        "evidence_quote_spans": spans,
        "quote_withheld": withheld.to_numpy(dtype=bool),
        "source_licence": code.to_numpy(),
    }
    if "evidence_quote" in out:
        out["evidence_quote"] = out["evidence_quote"].astype(object)
        out.loc[withheld, "evidence_quote"] = None
    anchor = next(
        (c for c in ("evidence_line_ids", "evidence_quote") if c in out.columns), out.columns[-1]
    )
    at = list(out.columns).index(anchor) + 1
    for offset, name in enumerate(RELEASE_COLUMNS):
        out.insert(at + offset, name, added[name])
    return out


def licence_facts(table: pd.DataFrame) -> dict | None:
    """Papers, rows and quotes per source licence, counted from the released table itself."""
    if "source_licence" not in table.columns:
        return None
    rows = []
    for code in CODES:
        g = table[table["source_licence"] == code]
        if not len(g):
            continue
        withheld = int(g["quote_withheld"].astype(bool).sum())
        rows.append((code, int(g["pmcid"].nunique()), len(g), len(g) - withheld, withheld))
    withheld = int(table["quote_withheld"].astype(bool).sum())
    return {
        "rows": rows,
        "papers": int(table["pmcid"].nunique()),
        "total": len(table),
        "shipped": len(table) - withheld,
        "withheld": withheld,
        "withheld_papers": int(table.loc[table["quote_withheld"].astype(bool), "pmcid"].nunique()),
    }


def gold_facts(gold: pd.DataFrame | None) -> dict | None:
    """Who annotated the set every extraction score is computed against.

    `audit-sample` writes its blind worksheet with `annotator = "author"`, so a gold set that
    carries no such row is a gold set no human has re-judged.
    """
    if gold is None or not len(gold):
        return None
    counts = (
        gold["annotator"].fillna("(unset)").value_counts()
        if "annotator" in gold.columns
        else pd.Series(dtype=int)
    )
    return {
        "rows": int(len(gold)),
        "papers": int(gold["pmcid"].nunique()) if "pmcid" in gold.columns else None,
        "annotators": {str(k): int(v) for k, v in counts.items()},
        "human_rows": int(counts.get("author", 0)),
    }


def facts(
    table: pd.DataFrame,
    stats: dict,
    *,
    gold: pd.DataFrame | None = None,
    corpus_archive: Path | None = None,
    corpus_manifest: Path | None = None,
    origin: dict | None = None,
) -> dict:
    n = len(table)
    verified = _true(table, "evidence_verified")
    complete = _true(table, "conditions_complete")
    printed = int(table["value"].notna().sum()) if "value" in table else 0
    cites = table["evidence_line_ids"].dropna() if "evidence_line_ids" in table else None
    cited = int(len(cites)) if cites is not None else 0
    n_citations = int(cites.str.split(";").map(len).sum()) if cited else 0
    prompts = sorted(table["prompt_sha256"].dropna().unique()) if "prompt_sha256" in table else []
    models = sorted(table["model"].dropna().unique()) if "model" in table else []
    return {
        "rows": n,
        "papers": int(table["pmcid"].nunique()) if "pmcid" in table else 0,
        "materials": int(table["material"].nunique()) if "material" in table else 0,
        "columns": list(table.columns),
        "rows_verified": verified,
        "rows_cited": cited,
        "n_citations": n_citations,
        "rows_complete": complete,
        "rows_printed": printed,
        "rows_not_printed": n - printed,
        "reported": [(label, _true(table, col)) for col, label in CONDITIONS if col in table],
        "cleared": {
            flag: _with_flag(table, flag)
            for flag in (ZERO_IONIC_STRENGTH, STEP_TEMPERATURE, OTHER_STEP_TEMPERATURE)
        },
        "prompts": [str(p) for p in prompts],
        "models": [str(m) for m in models],
        "stats": stats,
        "corpus": corpus_facts(corpus_archive, corpus_manifest),
        "licences": licence_facts(table),
        "gold": gold_facts(gold),
        "origin": origin,
        "scope": scope.block(table, stats, origin),
    }


def _true(table: pd.DataFrame, col: str) -> int:
    return int(table[col].astype(bool).sum()) if col in table.columns else 0


def _with_flag(table: pd.DataFrame, flag: str) -> int:
    if "flags" not in table.columns:
        return 0
    parts = table["flags"].fillna("").astype(str).str.split(";")
    return int(parts.map(lambda p: flag in p).sum())


def _any_missing(stats: dict) -> dict | None:
    for m in stats.get("missing", []):
        if m.get("condition") == "any":
            return m
    return None


def _scale_section(f: dict) -> list[str]:
    n = f["rows"]
    lines = [
        "## Scale",
        "",
        "| | |",
        "|---|---|",
        f"| rows (one surface measurement each) | {n} |",
        f"| papers | {f['papers']} |",
        f"| distinct `material` values | {f['materials']} |",
        f"| columns | {len(f['columns'])} |",
        f"| rows carrying a printed number | {f['rows_printed']} |",
        f"| rows reporting a measurement with no retrievable number | {f['rows_not_printed']} |",
        "| **fully conditioned rows** (`conditions_complete`) | "
        f"**{_kn(f['rows_complete'], n)}** |",
        f"| evidence quotes found verbatim in the source | {_kn(f['rows_verified'], n)} |",
        "",
    ]
    c = f["corpus"]
    if c["sha256"]:
        mb = c["bytes"] / 1e6
        files = f"{c['files']} XML files" if c["files"] else "an unknown number of XML files"
        lines += [
            f"Source corpus: {files}, vendored as one archive of {c['bytes']} bytes "
            f"({mb:.1f} MB), sha256 `{c['sha256']}`.",
            "",
        ]
    else:
        lines += [
            f"Source corpus: the vendored archive `data/raw/epmc/xml.tar.gz` is {ABSENT}, "
            "so its size and sha256 are not stated here rather than guessed.",
            "",
        ]
    return lines


def _headline_section(f: dict) -> list[str]:
    n, k = f["rows"], f["rows_complete"]
    lines = [
        f"## {_pct(k, n):.1f} % of rows are fully conditioned",
        "",
        f"Fully conditioned rows: **{_kn(k, n)}**. Those are the rows carrying all five of "
        "the conditions needed to interpret the number — dispersion medium, ionic strength, "
        "pH, temperature and instrument. Every other row is missing at least one of them.",
        "",
        "This is the dataset's finding, not a defect in it. A zeta potential without its "
        "ionic strength is not a property of the particle; it is a property of one "
        "unrecorded experiment. The dataset exists to make that countable.",
        "",
        "Row-level reporting of each condition:",
        "",
        "| condition | rows reporting it | |",
        "|---|---|---|",
    ]
    for label, k_rep in f["reported"]:
        lines.append(f"| {label} | {k_rep} / {n} | {_pct(k_rep, n):.1f} % |")
    lines.append("")
    return lines


def _paper_section(f: dict) -> list[str]:
    stats = f["stats"]
    den = stats.get("denominators", {})
    any_m = _any_missing(stats)
    lines = [
        "## Paper-level denominators",
        "",
        "Counted over papers rather than rows, and taken from `out/tables/d1_stats.json`, "
        "which is the artefact these numbers are published from.",
        "",
        "| | |",
        "|---|---|",
        f"| papers with at least one verified measurement | {stats.get('n_papers')} |",
    ]
    if any_m:
        lines.append(
            "| **papers omitting at least one of the five conditions** | "
            f"**{_kn(any_m['k_missing'], any_m['n'])}** |"
        )
    if den.get("oa_records"):
        lines.append(f"| open-access records the query returned | {den['oa_records']} |")
    if den.get("all_hits"):
        lines.append(f"| all hits, including paywalled | {den['all_hits']} |")
    lines += ["", "Per condition, over papers, with 95 % Wilson intervals:", ""]
    lines += ["| missing condition | papers | | 95 % CI |", "|---|---|---|---|"]
    for m in stats.get("missing", []):
        lo, hi = m.get("wilson_lo"), m.get("wilson_hi")
        ci = f"{100 * lo:.0f}–{100 * hi:.0f} %" if lo is not None and hi is not None else "—"
        lines.append(
            f"| {m.get('label')} | {m['k_missing']} / {m['n']} | "
            f"{_pct(m['k_missing'], m['n']):.1f} % | {ci} |"
        )
    avail = stats.get("text_availability")
    if avail:
        lines += [
            "",
            f"Of {avail['fetched']} fetched XMLs, {avail['no_retrievable_text']} carry no "
            "retrievable text at all — conference-abstract volumes and PDF-only deposits. "
            "They were not read and found to report nothing, and are counted apart from "
            "papers that were.",
        ]
    lines.append("")
    return lines


def _absence_section(f: dict) -> list[str]:
    return [
        "## Absence is a value, not a gap",
        "",
        "The five `*_reported` booleans are the reason this dataset exists. "
        "`ionic_strength_reported = False` is a **positive claim**: this paper did not report "
        "the ionic strength of the medium it measured in. It is not a null, not a missing "
        "value, and not an encoding of uncertainty. It is deterministically checkable against "
        "the source article, which is why it can be used as ground truth.",
        "",
        "Nothing is imputed. A condition that was not reported is never filled with a "
        "conventional default: **`not measured` is never written as 0.0 and never as 1.0**, "
        "because both are claims nobody checked. Where a paper reports a measurement but "
        "prints no number, `value` is null and `value_text` says so; where the ionic strength "
        "was inferred from a named salt rather than stated, `ionic_strength_source` records "
        "that it was inferred.",
        "",
        "Some readings are cleared rather than kept, by rules ratified on 2026-09-28 and 29. "
        'R1: an ionic strength of exactly 0 mM is not a reported one: "no added electrolyte" '
        "says nothing was added, not that the medium holds no ions, so the row reads "
        f"`ionic_strength_reported = False` and carries `{ZERO_IONIC_STRENGTH}` "
        f"({f['cleared'][ZERO_IONIC_STRENGTH]} rows). R2: a temperature tied to an incubation "
        "or exposure step is not the measurement temperature, even when the paper gives no "
        f"other, so it is removed and the row carries `{STEP_TEMPERATURE}` "
        f"({f['cleared'][STEP_TEMPERATURE]} rows). R2b: nor is a temperature the row's own "
        "quote does not state when its source prints it only for storage, incubation, exposure "
        'or culture — a medium label such as "RPMI (stored at 37 ˚C for 24 h)", or, when the '
        "row prints it nowhere, a paper that gives it only for such a step; the row carries "
        f"`{OTHER_STEP_TEMPERATURE}` ({f['cleared'][OTHER_STEP_TEMPERATURE]} rows). The rows "
        "stay; the extraction record keeps the number the model read.",
        "",
        "This makes one query answerable that a text index cannot answer: *what ionic strength "
        "did this paper use?* when the true answer is that it never said. There is no passage "
        "to retrieve for that, so a retrieval system fabricates the nearest number. Here it is "
        "a boolean.",
        "",
    ]


def _evidence_section(f: dict) -> list[str]:
    n, v = f["rows"], f["rows_verified"]
    cited, ncite = f["rows_cited"], f["n_citations"]
    return [
        "## Every quote is verbatim",
        "",
        f"`evidence_verified` is true for every row here: **{_kn(v, n)}**. Each row names "
        "the sentence or sentences the value was read from, and each was checked as a "
        "substring of the source article's text. A row whose quote could not be located was "
        "dropped and counted, never silently kept. Where the source's licence does not allow "
        "the quote to ship, the row carries its address and hash instead of its text — see "
        "*Licence* below.",
        "",
        "`evidence_quote` may join several passages with ` || `, because the value and its "
        "conditions are routinely sections apart — the number in Results or a table, the "
        "ionic strength in Methods. `evidence_location` names each.",
        "",
        "**Read the limit with the number.** Verbatim means the quote exists in the article. "
        "It does not mean the value was read from it correctly; that is what the extraction "
        "scores below measure, and they are provisional.",
        "",
        "## Where each quote sits in the paper",
        "",
        f"`evidence_line_ids` carries **{_kn(cited, n)}** of rows, {ncite} citations in all. "
        "A citation is a 16-character prefix of the SHA-256 of a line's section path, its "
        "ordinal within that section, and its normalised text — deliberately not the line "
        "number, so that a later fix to the parser which shifts numbering does not "
        "invalidate a stored address.",
        "",
        "The ids are semicolon-joined, flat, in the order the passages appear in "
        "`evidence_quote`. The grouping back onto ` || ` passages is not stored because it "
        "is recoverable: the quote is here, and re-running the locator reproduces it — or, "
        "for a withheld quote, `evidence_quote_spans` carries it. An empty value means the "
        "row carries a flag saying why, and no row is silently left without one.",
        "",
    ]


def _kappa_section(f: dict) -> list[str]:
    lines = [
        "## The κ audit has not been done",
        "",
        "Extraction accuracy for this dataset is scored against a gold set of hand-checked "
        "rows in `data/interim/annotation/gold_50.csv`. **That gold set was annotated by "
        "Claude and has not been audited by a human.**",
        "",
    ]
    g = f["gold"]
    if g:
        who = ", ".join(f"`{k}` {v}" for k, v in g["annotators"].items())
        lines += [
            f"Its {g['rows']} rows over {g['papers']} papers carry these annotators: {who}. "
            f"Rows re-judged independently by a human: **{g['human_rows']}**.",
            "",
        ]
    lines += [
        "A blind worksheet for that re-judgement exists — `data/interim/annotation/"
        "audit_10.csv`, ten of the gold papers with every judged column blanked — and it has "
        "not been filled in. **No inter-annotator agreement statistic (Cohen's κ) is "
        "published with this release, because none has been computed.**",
        "",
        "Consequence for anyone using this dataset: **every extraction quality score "
        "associated with it is provisional.** The gold set is a second pass by the same "
        "family of model that produced the extractions, so it can agree with them for reasons "
        "that have nothing to do with the articles. The rows themselves are verbatim-checked "
        "against the source and do not depend on the gold set; the *scores* do.",
        "",
    ]
    return lines


def _provenance_section(f: dict) -> list[str]:
    prompts, models = f["prompts"], f["models"]
    lines = [
        "## Provenance, and how coarse it is",
        "",
        "Every row carries `pmcid`, `doi`, `model` and `prompt_sha256` — the hash of the "
        "extraction prompt that produced it.",
        "",
        f"**Only {len(prompts)} distinct `prompt_sha256` values occur across all "
        f"{f['rows']} rows, so prompt provenance is currently coarse.** A row can be traced "
        "to one of a very small number of prompts, not to the exact brief revision it was "
        "read under. Do not treat `prompt_sha256` as a fine-grained experimental key.",
        "",
    ]
    if prompts:
        lines += ["The hashes present:", ""]
        lines += [f"- `{p}`" for p in prompts]
        lines.append("")
    if models:
        named = ", ".join(f"`{m}`" for m in models)
        lines += [f"Models that produced these rows: {named}.", ""]
    return lines


def _licence_section(f: dict) -> list[str]:
    lines = [
        f"## Licence — {LICENCE_SHORT}",
        "",
        f"This dataset is released under the **{LICENCE_NAME} licence ({LICENCE_SHORT})**, "
        f"<{LICENCE_URL}>. The notice and the attribution line are in `LICENSE`. The decision "
        "was taken on 2026-09-28.",
        "",
        "**What is a fact and what is a quote.** The extracted values, units and conditions "
        "and the absence booleans are facts about what each paper reports. They ship for every "
        "row whatever the source's licence, with the row's source licence code and, where the "
        "quote is withheld, its address and hash. The evidence quotes are verbatim text from "
        "the source articles. A quote "
        "ships only where its source is licensed CC BY (any version) or CC0, which already "
        "permit redistribution with attribution. For every other source — non-commercial, "
        "no-derivatives, share-alike, a publisher's own terms, a statement that is ambiguous, "
        "or no licence statement at all — the quote is withheld: `evidence_quote` is null, "
        "`quote_withheld` is true, and the text is in no file of this release.",
        "",
    ]
    lic = f["licences"]
    if lic:
        lines += [
            "Per source licence, as each paper's own JATS states it (`source_licence`, read "
            "from the vendored XML by `mnp.corpus.licence`: a creativecommons.org URL is "
            "preferred, the wording decides where there is none):",
            "",
            "| source licence | papers | rows | quotes shipped | quotes withheld |",
            "|---|---|---|---|---|",
        ]
        for code, papers, rows, shipped, withheld in lic["rows"]:
            lines.append(f"| `{code}` | {papers} | {rows} | {shipped} | {withheld} |")
        lines += [
            f"| **total** | {lic['papers']} | {lic['total']} | {lic['shipped']} | "
            f"{lic['withheld']} |",
            "",
            f"Quotes withheld: **{_kn(lic['withheld'], lic['total'])}** of rows, from "
            f"{lic['withheld_papers']} papers. `other-named` is a statement that names no "
            "Creative Commons licence, or whose URL and wording disagree — a publisher's own "
            "terms, *public domain unless otherwise noted*, a time-limited access grant. "
            "`none` is an article with no licence statement at all. Both are withheld: an "
            "unclear grant is not a grant.",
            "",
        ]
    lines += [
        "**Restoring withheld quotes locally.** A withheld row keeps `evidence_quote_sha256`, "
        "the hash of the original quote, and `evidence_quote_spans`, its address in the "
        "source: a JSON array of `[line_id, start, end]` slices of the article's "
        "line-addressed text, joined by glue that holds only separators, whitespace and "
        "dashes — never a letter or a digit. With the source articles on your machine:",
        "",
        "```",
        "uv run python -m mnp.corpus restore      # the vendored articles",
        "uv run python -m mnp.report rehydrate [--release out/release] [--out <path>]",
        "```",
        "",
        "`rehydrate` rebuilds each article's lines, slices them, checks every result against "
        "its sha256, and writes a local copy of the dataset with the quotes put back — never "
        "into this directory. With `--fetch` it downloads an article missing from the corpus "
        "from Europe PMC. A quote that no longer matches its hash is reported and left null, "
        "never approximated. That local copy carries text under its sources' licences, not "
        "this one; keep it local.",
        "",
        "**The source articles keep their own licences.** Nothing here relicenses them, and "
        "their full texts are not in this release. Every row names its source by `pmcid` and "
        "`doi`: fetch the article from its publisher or from Europe PMC, under the terms its "
        "publisher applies. A quote shipped from a CC BY source remains its authors' work, "
        "attributed by that row's `pmcid` and `doi`.",
        "",
        "This is a licensing decision, not legal advice.",
        "",
    ]
    return lines


def _limits_section(f: dict) -> list[str]:
    stats = f["stats"]
    den = stats.get("denominators", {})
    lines = [
        "## Limits a citer needs to state",
        "",
        f"1. **One database.** Every paper here came from Europe PMC: {stats.get('n_papers')} "
        "papers with a verified measurement, drawn from "
        f"{den.get('oa_records', 'an unstated number of')} open-access records the query "
        "returned. OpenAlex indexes roughly three times as much of this literature. Adding it "
        "would change every denominator on this card, and would therefore be a different "
        "study rather than a larger version of this one. **Do not read these fractions as "
        "fractions of the literature.** They are fractions of one database's open-access "
        "subset.",
        "",
        "2. **Open access only.** Full text was fetched only where Europe PMC serves it. "
        f"The lower bound against all {den.get('all_hits', '—')} hits, paywalled included, is "
        "reported in `d1_stats.json` for that reason.",
        "",
        "3. **Extraction scores are provisional** until the κ audit above is done.",
        "",
        "4. **Prompt provenance is coarse** — see above.",
        "",
        "5. **A row is a reported measurement, not a verified physical quantity.** The quote "
        "is checked against the article; the article is not checked against reality.",
        "",
        "6. **Absence is absence of reporting.** `pH_reported = False` means the paper did "
        "not state a pH. It does not mean the experiment had no pH.",
        "",
    ]
    if f.get("origin"):
        lines += _origin_limits(f["origin"])
    return lines


def _origin_limits(o: dict) -> list[str]:
    """Where the particles came from, and the parser defect found while asking."""
    h, n = o["hand_corrected"], o["rows"]
    where, env = h["environment"]["rows"], h["environmental_rows"]
    places = ", ".join(f"{e.replace('_', ' ')} {k}" for e, k in where.items() if k and e != "null")
    lines = [
        f"7. **The measured particles are synthetic.** {_kn(h['synthetic']['rows'], n)} of "
        "rows measure a particle bought ready-made or made in a lab. "
        f"{env['rows']} row{'s' if env['rows'] != 1 else ''}, from {env['papers']} "
        f"paper{'s' if env['papers'] != 1 else ''}, measure a particle collected from a real "
        f"environment ({places}); from air or dust: {where['air_dust']}. The values describe "
        "manufactured particles in laboratory liquids, not how micro- and nanoplastics behave "
        "in the environment. A reader classified every row and a person checked every "
        "environmental one and a sample of the rest (`out/tables/sample_origin_stats.json`, "
        "`out/review/REVIEW.md` C11).",
        "",
    ]
    lm = o.get("lost_methods")
    if not lm:
        return lines
    a, u = lm["affected"], lm["unaffected"]
    shown = (("medium", "medium"), ("ionic_strength", "ionic strength"),
             ("temperature", "temperature"))  # fmt: skip

    def share(block: dict, name: str) -> float:
        return _pct(block["any_row"][name]["n"], block["papers"])

    pairs = "; ".join(
        f"{label} {share(a, k):.1f} % against {share(u, k):.1f} %" for k, label in shown
    )
    lower = all(share(a, k) < share(u, k) for k, _ in shown)
    lines += [
        "8. **The extraction did not read every paper's Methods.** In "
        f"{lm['papers_affected']} of {lm['papers']} papers the parser took a "
        "supplementary-materials section for the Methods, so the Methods reached the text the "
        "extraction read only where a zeta keyword window or a characterisation subsection "
        "covered them. Papers with at least one row reporting the condition, those papers "
        f"against the rest: {pairs}. "
        + (
            "They report conditions less often, so the condition-reporting shares on this card "
            "may be biased downward."
            if lower
            else "The condition-reporting shares on this card may be biased by it."
        )
        + " The parser is not fixed and those papers have not been re-extracted.",
        "",
    ]
    return lines


def _columns_section(f: dict) -> list[str]:
    present = list(f["columns"])
    lines = ["## Columns", "", "| group | columns |", "|---|---|"]
    seen: set[str] = set()
    for group, cols in COLUMN_GROUPS:
        here = [c for c in cols if c in present]
        seen.update(here)
        if here:
            lines.append(f"| {group} | " + ", ".join(f"`{c}`" for c in here) + " |")
    rest = [c for c in present if c not in seen]
    if rest:
        lines.append("| ungrouped | " + ", ".join(f"`{c}`" for c in rest) + " |")
    lines.append("")
    return lines


def _files_section(digests: dict[str, str], rows: int, columns: int) -> list[str]:
    return [
        "## Files",
        "",
        "| file | what it is | sha256 |",
        "|---|---|---|",
        f"| `dataset.parquet` | {rows} rows × {columns} columns | `{digests['dataset.parquet']}` |",
        f"| `dataset.jsonl` | the same rows, one JSON object per line | "
        f"`{digests['dataset.jsonl']}` |",
        "| `schema.json` | JSON Schema 2020-12 for the record type, generated from the "
        "pydantic models in `mnp.schema.models`; the release's own evidence columns are "
        f"`$defs/ReleasedEvidence` | `{digests['schema.json']}` |",
        f"| `LICENSE` | {LICENCE_SHORT}, and the attribution line | `{digests['LICENSE']}` |",
        "| `DATASET_CARD.md` | this file | — |",
        "",
        "The parquet and the JSONL carry identical content; the two formats exist so the "
        "dataset can be read without pandas. `schema.json` describes the nested record the "
        "extraction produces, of which the flat table here is one row per measurement.",
        "",
    ]


def card(f: dict, digests: dict[str, str]) -> str:
    lines = [
        f"# {DATASET_TITLE}",
        "",
        *f["scope"],
        "",
        f"{f['rows']} surface-charge measurements extracted from {f['papers']} open-access "
        "papers, each with the conditions it was measured under — and, where those conditions "
        "were not reported, an explicit record that they were not.",
        "",
        "**Every number in this card was computed when the card was built**, from "
        "`out/tables/d1_zeta_table.csv` and `out/tables/d1_stats.json`"
        + (
            ", and the particles' origin from `out/tables/sample_origin_stats.json`"
            if f.get("origin")
            else ""
        )
        + ". None is typed in. Rebuild the card and any number that has moved will move with it.",
        "",
        "Two things a reader should take from this card before using the data: only a small "
        "minority of published measurements are fully conditioned, and the accuracy scores "
        "for this extraction have not yet been audited by a human.",
        "",
    ]
    lines += _files_section(digests, f["rows"], len(f["columns"]))
    lines += _scale_section(f)
    lines += _headline_section(f)
    lines += _absence_section(f)
    lines += _evidence_section(f)
    lines += _paper_section(f)
    lines += _kappa_section(f)
    lines += _provenance_section(f)
    lines += _licence_section(f)
    lines += _limits_section(f)
    lines += _columns_section(f)
    lines += [
        "## How to rebuild this",
        "",
        "```",
        "uv run python -m mnp.report d1        # the table and d1_stats.json",
        *(
            ["uv run python -m mnp.report origin    # sample_origin_stats.json"]
            if f.get("origin")
            else []
        ),
        "uv run python -m mnp.report release   # this directory",
        "uv run python -m mnp.report reproduce # rebuild everything offline and diff it",
        "```",
        "",
        "`reproduce` rebuilds the published artefacts from the vendored corpus with the "
        "network refused and compares them byte for byte. The dataset is derived, not "
        "hand-curated: nothing in this directory is edited by hand, including this card.",
        "",
    ]
    return "\n".join(lines).rstrip("\n") + "\n"


def licence_notice() -> str:
    author = AUTHOR or (
        "[author not yet named — neither DATASET_CARD.md nor pyproject.toml names one; "
        "set release.AUTHOR before publishing]"
    )
    return "\n".join(
        [
            DATASET_TITLE,
            "",
            f"Licensed under the {LICENCE_NAME} licence ({LICENCE_SHORT}):",
            LICENCE_URL,
            "",
            "You may share and adapt this dataset for any purpose, including commercially, "
            "provided you give appropriate credit, link to the licence, and indicate if "
            "changes were made. The licence is the text at the URL above; this file names it.",
            "",
            f'Attribution: "{DATASET_TITLE}", by {author}. Licensed under {LICENCE_SHORT}, '
            f"{LICENCE_URL}",
            "",
            "Scope: the extracted values, units and conditions, the absence booleans, the "
            "source licence codes, and the quote addresses and hashes. Evidence quotes ship "
            "only from CC BY and CC0 sources; they remain their authors' work, attributed by "
            "each row's pmcid and doi. Quotes from every other source are withheld and are not "
            "part of this release. The source articles keep their own licences.",
            "",
            "This is a licensing decision, not legal advice.",
            "",
        ]
    )


def build(
    table: pd.DataFrame,
    stats: dict,
    out_dir: Path,
    *,
    licences: Mapping[str, Licence],
    documents: Callable[[str], LinedDoc | None] | None = None,
    gold: pd.DataFrame | None = None,
    corpus_archive: Path | None = None,
    corpus_manifest: Path | None = None,
    origin: dict | None = None,
) -> list[Path]:
    check_agrees(table, stats)
    table = withhold(table, licences, documents)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    parquet = out_dir / "dataset.parquet"
    table.to_parquet(parquet, index=False)

    jsonl = out_dir / "dataset.jsonl"
    with jsonl.open("w", encoding="utf-8") as fh:
        for row in records(table):
            fh.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")

    schema = out_dir / "schema.json"
    schema.write_text(json.dumps(export.json_schema(), indent=2) + "\n")

    notice = out_dir / "LICENSE"
    notice.write_text(licence_notice())

    digests = {p.name: sha256_file(p) for p in (parquet, jsonl, schema, notice)}
    f = facts(
        table,
        stats,
        gold=gold,
        corpus_archive=corpus_archive,
        corpus_manifest=corpus_manifest,
        origin=origin,
    )
    card_path = out_dir / "DATASET_CARD.md"
    card_path.write_text(card(f, digests))
    return [parquet, jsonl, schema, notice, card_path]
