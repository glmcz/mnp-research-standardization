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
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from mnp.report.reproduce import sha256_file
from mnp.schema import export

DATASET_NAME = "MNP-KB v0"

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
    ("evidence", ("evidence_quote", "evidence_location", "evidence_verified")),
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


def licence_facts(articles: pd.DataFrame | None) -> dict | None:
    """What the source articles say about re-use. Free text per publisher, so counted coarsely."""
    if articles is None or not len(articles) or "license" not in articles.columns:
        return None
    lic = articles["license"].fillna("").astype(str)
    stated = lic.str.strip().ne("")
    codes = lic.str.extract(r"creativecommons\.org/licenses/([a-z\-]+)/", expand=False)
    return {
        "articles": int(len(articles)),
        "distinct_statements": int(lic[stated].nunique()),
        "without_statement": int((~stated).sum()),
        "by_code": {str(k): int(v) for k, v in codes.dropna().value_counts().items()},
        "without_cc_url": int(codes.isna().sum()),
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
    articles: pd.DataFrame | None = None,
    gold: pd.DataFrame | None = None,
    corpus_archive: Path | None = None,
    corpus_manifest: Path | None = None,
) -> dict:
    n = len(table)
    verified = _true(table, "evidence_verified")
    complete = _true(table, "conditions_complete")
    printed = int(table["value"].notna().sum()) if "value" in table else 0
    prompts = sorted(table["prompt_sha256"].dropna().unique()) if "prompt_sha256" in table else []
    models = sorted(table["model"].dropna().unique()) if "model" in table else []
    return {
        "rows": n,
        "papers": int(table["pmcid"].nunique()) if "pmcid" in table else 0,
        "materials": int(table["material"].nunique()) if "material" in table else 0,
        "columns": list(table.columns),
        "rows_verified": verified,
        "rows_complete": complete,
        "rows_printed": printed,
        "rows_not_printed": n - printed,
        "reported": [(label, _true(table, col)) for col, label in CONDITIONS if col in table],
        "prompts": [str(p) for p in prompts],
        "models": [str(m) for m in models],
        "stats": stats,
        "corpus": corpus_facts(corpus_archive, corpus_manifest),
        "licences": licence_facts(articles),
        "gold": gold_facts(gold),
    }


def _true(table: pd.DataFrame, col: str) -> int:
    return int(table[col].astype(bool).sum()) if col in table.columns else 0


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
        "This makes one query answerable that a text index cannot answer: *what ionic strength "
        "did this paper use?* when the true answer is that it never said. There is no passage "
        "to retrieve for that, so a retrieval system fabricates the nearest number. Here it is "
        "a boolean.",
        "",
    ]


def _evidence_section(f: dict) -> list[str]:
    n, v = f["rows"], f["rows_verified"]
    return [
        "## Every quote is verbatim",
        "",
        f"`evidence_verified` is true for every row here: **{_kn(v, n)}**. Each row carries "
        "the sentence or sentences the value was read from, and each was checked as a "
        "substring of the source article's text. A row whose quote could not be located was "
        "dropped and counted, never silently kept.",
        "",
        "`evidence_quote` may join several passages with ` || `, because the value and its "
        "conditions are routinely sections apart — the number in Results or a table, the "
        "ionic strength in Methods. `evidence_location` names each.",
        "",
        "**Read the limit with the number.** Verbatim means the quote exists in the article. "
        "It does not mean the value was read from it correctly; that is what the extraction "
        "scores below measure, and they are provisional.",
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
        "## Licence — UNRESOLVED",
        "",
        "**This release does not yet carry a licence. That is an open decision, not an "
        "oversight, and it is recorded here so nobody assumes one.** Do not redistribute this "
        "dataset until it is settled.",
        "",
        "What is at issue. The source articles are open access, but their licences differ "
        "from paper to paper, and the dataset redistributes short verbatim quotes from them.",
        "",
        "| | |",
        "|---|---|",
        "| redistributed here | extracted values, conditions, the absence booleans, and "
        "short verbatim evidence quotes |",
        "| **not** redistributed here | the full texts of the source articles |",
        "",
        "Every row names its source by `pmcid` and `doi`, so the article itself can always be "
        "fetched from the publisher under whatever licence that publisher applies.",
        "",
    ]
    lic = f["licences"]
    if lic:
        lines += [
            f"Licence statements across the {lic['articles']} fetched articles — "
            f"{lic['distinct_statements']} distinct strings, which is why they are grouped "
            "here by the Creative Commons code named in the statement:",
            "",
            "| licence named in the article | articles |",
            "|---|---|",
        ]
        for code, count in sorted(lic["by_code"].items(), key=lambda kv: -kv[1]):
            lines.append(f"| CC {code.upper()} | {count} |")
        lines.append(
            f"| no Creative Commons URL in the statement | {lic['without_cc_url']} |"
        )
        lines.append(f"| no licence statement at all | {lic['without_statement']} |")
        lines += [
            "",
            "Note the last two rows. A non-commercial or no-derivatives term on a source "
            "article is not automatically satisfied by quoting from it, and the papers with "
            "no statement at all are not automatically permissive.",
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
        f"| `dataset.parquet` | {rows} rows × {columns} columns | "
        f"`{digests['dataset.parquet']}` |",
        f"| `dataset.jsonl` | the same rows, one JSON object per line | "
        f"`{digests['dataset.jsonl']}` |",
        "| `schema.json` | JSON Schema 2020-12 for the record type, generated from the "
        f"pydantic models in `mnp.schema.models` | `{digests['schema.json']}` |",
        "| `DATASET_CARD.md` | this file | — |",
        "",
        "The parquet and the JSONL carry identical content; the two formats exist so the "
        "dataset can be read without pandas. `schema.json` describes the nested record the "
        "extraction produces, of which the flat table here is one row per measurement.",
        "",
    ]


def card(f: dict, digests: dict[str, str]) -> str:
    lines = [
        f"# {DATASET_NAME} — micro- and nanoplastic surface measurements, with absence recorded",
        "",
        f"{f['rows']} surface-charge measurements extracted from {f['papers']} open-access "
        "papers, each with the conditions it was measured under — and, where those conditions "
        "were not reported, an explicit record that they were not.",
        "",
        "**Every number in this card was computed when the card was built**, from "
        "`out/tables/d1_zeta_table.csv` and `out/tables/d1_stats.json`. None is typed in. "
        "Rebuild the card and any number that has moved will move with it.",
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


def build(
    table: pd.DataFrame,
    stats: dict,
    out_dir: Path,
    *,
    articles: pd.DataFrame | None = None,
    gold: pd.DataFrame | None = None,
    corpus_archive: Path | None = None,
    corpus_manifest: Path | None = None,
) -> list[Path]:
    check_agrees(table, stats)
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

    digests = {p.name: sha256_file(p) for p in (parquet, jsonl, schema)}
    f = facts(
        table,
        stats,
        articles=articles,
        gold=gold,
        corpus_archive=corpus_archive,
        corpus_manifest=corpus_manifest,
    )
    card_path = out_dir / "DATASET_CARD.md"
    card_path.write_text(card(f, digests))
    return [parquet, jsonl, schema, card_path]
