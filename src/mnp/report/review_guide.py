"""The text of `out/review/REVIEW.md`, rendered from `review.Facts`.

Every number here is read off the facts `review.gather` computed on this build, or quoted with
the file and section it comes from. Where the guide spells out arithmetic for a worked example it
recomputes the result from the inputs it shows and refuses to render if that disagrees with what
the module produced: a worked example that does not add up is a false sentence in waiting.
"""

from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from mnp.demo import harmonise, resample
from mnp.ek.constants import permittivity, viscosity
from mnp.eval import comparability as comp
from mnp.eval import grid
from mnp.extract.origin import ENVIRONMENTS
from mnp.extract.zeta import OTHER_STEP_TEMPERATURE, STEP_TEMPERATURE, ZERO_IONIC_STRENGTH
from mnp.report import scope
from mnp.report.origin import ROW_COLUMNS
from mnp.report.release import COLUMN_GROUPS
from mnp.report.review import AUDIT_SEED, CASES, COLUMNS, FLAGS, METRICS, RUN_IDS, Facts

HARM = "harmonised_all_rows.csv"
PER_PAPER = "conditions_per_paper.csv"
ICC = "icc_worksheet.csv"
PAIRS = "comparability_worked_pairs.csv"
AUDIT = "audit_sample.csv"
ORIGIN_ROWS = "sample_origin.csv"

#: Griffin and Jurinak (1973): I (mol/L) ≈ 0.013 × EC (mS/cm), which is I (mM) ≈ 0.013 × EC (µS/cm).
GRIFFIN_JURINAK = 0.013
ENV_LABEL = {
    "freshwater": "freshwater",
    "seawater": "seawater",
    "wastewater": "wastewater effluent",
    "soil": "soil",
    "sediment": "sediment",
    "air_dust": "air or dust",
    "biota": "organisms",
    "other": "other",
}
ORIGIN_CONDITIONS = (
    ("medium", "medium"),
    ("ionic_strength", "ionic strength"),
    ("pH", "pH"),
    ("temperature", "temperature"),
    ("instrument", "instrument"),
)


def _int(n: Any) -> str:
    return f"{int(n):,}".replace(",", " ")


def _pct(k: float, n: float, digits: int = 1) -> str:
    return f"{100 * k / n:.{digits}f} %" if n else "—"


def _kn(k: float, n: float) -> str:
    return f"{_int(k)} / {_int(n)} ({_pct(k, n)})"


def _pp(x: float) -> str:
    return f"{100 * x:.1f} %"


def _and(items: list[str]) -> str:
    return " and ".join([", ".join(items[:-1]), items[-1]] if len(items) > 1 else items)


def _cell(value: Any, width: int = 70) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    if isinstance(value, bool):
        return str(value)
    text = f"{value:g}" if isinstance(value, float) else " ".join(str(value).split())
    if len(text) > width:
        text = text[: width - 1].rstrip() + "…"
    return text.replace("|", "\\|")


def _letter(index: int) -> str:
    """Spreadsheet column letter of a 0-based column index."""
    out = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        out = chr(ord("A") + rest) + out
    return out


def _col(sheet: str, column: str) -> str:
    return _letter(list(COLUMNS[sheet]).index(column))


def _check(label: str, shown: float, module: float) -> None:
    if not math.isclose(shown, module, rel_tol=1e-9, abs_tol=1e-12):
        raise ValueError(f"worked example {label}: arithmetic gives {shown}, module gave {module}")


def _complete_rows(f: Facts) -> int:
    return int(f.table["conditions_complete"].sum())


def _with_flag(t: pd.DataFrame, flag: str) -> pd.DataFrame:
    """The rows carrying `flag` as one of their `;`-joined flags."""
    return t[t["flags"].fillna("").astype(str).str.split(";").map(lambda parts: flag in parts)]


def _any_complete(f: Facts) -> int:
    return int((f.papers["conditions_complete_rows"] > 0).sum())


def _every_somewhere(f: Facts) -> int:
    return int((f.papers[[f"{m}_rows" for m in FLAGS]] > 0).all(axis=1).sum())


def _estimate(f: Facts, metric: str) -> resample.MetricEstimate:
    return next(e for e in f.estimates if e.metric == metric)


def _by_verdict(f: Facts, verdict: comp.Comparability) -> list[comp.PairSpec]:
    return [s for s in f.graded if s.verdict.verdict is verdict]


def _zeta_pair(spec: comp.PairSpec) -> bool:
    return spec.a.quantity.value == spec.b.quantity.value == "zeta_potential"


# --- 1 -----------------------------------------------------------------------------------------


def _sheet_table(rows: list[tuple[str, str, str]]) -> list[str]:
    return [
        "| column | what it holds | spreadsheet formula |",
        "|---|---|---|",
        *(f"| `{c}` | {what} | {formula} |" for c, what, formula in rows),
        "",
    ]


def _worksheet_docs(f: Facts) -> list[str]:
    d1 = list(f.table.columns)

    def d(column: str) -> str:
        return _letter(d1.index(column))

    pid = d("pmcid")
    per_paper = [
        ("pmcid", "the paper; one line per paper, sorted", "—"),
        ("n_rows", "its rows in the table", f"`=COUNTIF(d1!{pid}:{pid},A2)`"),
    ]
    for m in METRICS:
        rows_col, share_col = _col(PER_PAPER, f"{m}_rows"), _col(PER_PAPER, f"{m}_share")
        per_paper += [
            (
                f"{m}_rows",
                f"its rows where `{m}` is true",
                f"`=COUNTIFS(d1!{pid}:{pid},A2,d1!{d(m)}:{d(m)},TRUE)`",
            ),
            (f"{m}_share", f"`{m}_rows` / `n_rows`", f"`={rows_col}2/B2`"),
        ]
        _ = share_col
    icc = [
        ("pmcid", "the paper, in the order `resample` clusters in", "—"),
        ("n_i", "its rows (n_i in §5.2)", f"`=COUNTIF(d1!{pid}:{pid},A2)`"),
    ]
    icc += [
        (
            f"{m}_succ",
            f"its rows where `{m}` is true (succ_i in §5.2)",
            f"`=COUNTIFS(d1!{pid}:{pid},A2,d1!{d(m)}:{d(m)},TRUE)`",
        )
        for m in METRICS
    ]
    h = {c: _col(HARM, c) for c in COLUMNS[HARM]}
    harm = [
        (c, "copied from the same row of the table (same order)", f"`=d1!{d(c)}2`")
        for c in ("row_id", "pmcid", "quantity", "value", "unit", *FLAGS)
    ]
    harm += [
        (
            "conditions_complete",
            "all five flags true",
            f"`=AND({h['medium_reported']}2,{h['ionic_strength_reported']}2,{h['pH_reported']}2,"
            f"{h['temperature_reported']}2,{h['instrument_reported']}2)`",
        ),
        (
            "ionic_strength_mM",
            "the ionic strength when it is reported, else blank",
            f'`=IF({h["ionic_strength_reported"]}2,d1!{d("ionic_strength_mM")}2,"")`',
        ),
        ("size_measured_nm", "copied; blank when unreported", f"`=d1!{d('size_measured_nm')}2`"),
        ("temperature_C", "copied; blank when not a number", f"`=d1!{d('temperature_C')}2`"),
        (
            "models_named",
            "conversion models the paper's full text names, `;`-joined "
            "(`harmonise.models_named`, §5.5)",
            "not a formula: a text scan of the XML",
        ),
        (
            "debye_length_nm",
            "κ⁻¹, nm; blank when the ionic strength is unreported or 0 mM (§5.4)",
            f"`=IF(AND(ISNUMBER({h['ionic_strength_mM']}2),{h['ionic_strength_mM']}2>0),"
            f'0.304/SQRT({h["ionic_strength_mM"]}2/1000),"")`',
        ),
        (
            "kappa_a",
            "κa; 0 when the ionic strength is 0 mM; blank when either input is missing",
            f"`=IF(AND(ISNUMBER({h['ionic_strength_mM']}2),ISNUMBER({h['size_measured_nm']}2)),"
            f"IF({h['ionic_strength_mM']}2=0,0,({h['size_measured_nm']}2/2)/"
            f'{h["debye_length_nm"]}2),"")`',
        ),
        (
            "henry_f",
            "f(κa) by Ohshima's approximation; 1 at κa = 0, 1.5 above κa = 700",
            f"`=IF(ISNUMBER({h['kappa_a']}2),IF({h['kappa_a']}2=0,1,1+1/(2*(1+2.5/"
            f'({h["kappa_a"]}2*(1+2*EXP(-{h["kappa_a"]}2))))^3)),"")`',
        ),
        ("case", "the harmonisation case label, §5.5", "read off the result, §5.5"),
        (
            "result",
            "`point`, `interval` or `none`",
            f'`=IF(ISNUMBER({h["point"]}2),"point",IF(ISNUMBER({h["low"]}2),"interval","none"))`',
        ),  # fmt: skip
        ("point", "the harmonised zeta, mV, when fully determined", "by case, §5.5"),
        ("low", "lower bound of the interval, mV", "by case, §5.5"),
        ("high", "upper bound of the interval, mV", "by case, §5.5"),
        ("why", "the module's own one-line reason", "text from `harmonise`"),
    ]
    pairs = [
        ("pair_id", "groups the lines of one pair", "—"),
        ("why_chosen", "the fixed rule that picked the pair", "—"),
        ("verdict", "`comparable`'s grade for the pair", "the three-line rule in §5.6"),
        ("row_id_a", "first row of the pair", "—"),
        ("row_id_b", "second row", "—"),
        ("check", "the code function that runs the check", "—"),
        ("field", "the field checked", "—"),
        ("value_a", "what row a holds", "look it up in `d1_zeta_table.csv`"),
        ("value_b", "what row b holds", "as `value_a`"),
        ("compared_as_a", "what the rule compares: a normalised key, a source, f", "—"),
        ("compared_as_b", "the same for row b", "—"),
        (
            "difference",
            "the numeric gap, relative for ionic strength and f",
            "`=ABS(a-b)/MAX(ABS(a),ABS(b))`, or `=ABS(a-b)` for pH and temperature",
        ),
        ("tolerance", "the rule's limit", "from the §5.6 rule table"),
        ("outcome", "`blocks`, `passes`, or why the check did not run", "compare with `tolerance`"),
        ("blocker_code", "the blocker `comparable` produced on this field", "—"),
        ("blocker_kind", "`unreported`, `undecidable` or `mismatch`", "—"),
    ]
    audit_cols = [
        ("sample_no", "1 to 20", "—"),
        ("stratum", "the condition and state the row was drawn for", "—"),
        ("row_id", "the row", "—"),
        ("pmcid", "the paper", "—"),
        ("doi", "the paper's DOI", "—"),
        ("europepmc_url", "where to read it", "—"),
        ("xml_path", "the vendored XML", "—"),
        ("source_licence", "the paper's licence", "—"),
        ("quote_withheld", "true when no text may be shown", "—"),
    ]
    audit_cols += [
        (c, "copied from the release", "—")
        for c in (
            "quantity",
            "value",
            "value_text",
            "unit",
            "medium_text",
            "medium_class",
            "ionic_strength_mM",
            "ionic_strength_source",
            "pH",
            "pH_text",
            "temperature_C",
            "temperature_qualifier",
            "instrument",
            *FLAGS,
            "conditions_complete",
        )
    ]
    audit_cols += [
        ("evidence_line_ids", "the row's line ids", "—"),
        ("evidence_lines", "the same lines as `PMCID:Lnn`, in the same order", "resolved by code"),
        ("evidence_quote", "the quote; blank when withheld", "—"),
        ("evidence_line_text", "each cited line's text, ` || `-joined; blank when withheld", "—"),
        ("value_ok", "your verdict on value and unit: `yes`, `no`, `unsure`", "you fill it"),
        ("medium_ok", "your verdict on the medium", "you fill it"),
        ("ionic_strength_ok", "your verdict on the ionic strength", "you fill it"),
        ("pH_ok", "your verdict on the pH", "you fill it"),
        ("temperature_ok", "your verdict on the temperature", "you fill it"),
        ("instrument_ok", "your verdict on the instrument", "you fill it"),
        ("note", "anything else", "you fill it"),
    ]
    return [
        "### The worksheets, column by column",
        "",
        "Formulas assume `d1_zeta_table.csv` is imported into the same spreadsheet as a sheet "
        "named `d1`, and that row 2 is the first data row. The letters are the columns of "
        "each file as written.",
        "",
        f"**`{PER_PAPER}`** — {_int(len(f.papers))} lines, one per paper (§5.1).",
        "",
        *_sheet_table(per_paper),
        f"**`{ICC}`** — {_int(len(f.papers))} lines, one per paper (§5.2). The same counts as "
        "the sheet above, laid out for the ANOVA.",
        "",
        *_sheet_table(icc),
        f"**`{HARM}`** — {_int(len(f.harmonised))} lines, every row (§4, §5.4, §5.5).",
        "",
        *_sheet_table(harm),
        f"**`{PAIRS}`** — one line per check, {len(f.pairs)} pairs (§5.6).",
        "",
        *_sheet_table(pairs),
        f"**`{AUDIT}`** — {_int(len(f.audit))} rows to check against the papers (§7).",
        "",
        *_sheet_table(audit_cols),
    ]


def section_1(f: Facts) -> list[str]:
    t, r = f.table, f.release
    extra_cols = [c for c in r.columns if c not in t.columns]
    withheld = int(r["quote_withheld"].sum())
    return [
        "## 1. How to use this guide",
        "",
        "This file is generated by `uv run python -m mnp.report review`. Every number in it was "
        "computed when it was built, from the repo's own code and data, or is quoted with the "
        "file and section it comes from. Rebuild it and a number that has moved moves here too. "
        "Nothing in `out/review/` is edited by hand.",
        "",
        "Read it with the worksheets open. Each section says which worksheet lets you redo its "
        "arithmetic, and section 7 is a one-hour checklist that walks through all of them.",
        "",
        "### The files",
        "",
        "| file | what it is | use it to |",
        "|---|---|---|",
        f"| `out/tables/d1_zeta_table.csv` | the working table: {_int(len(t))} rows × "
        f"{len(t.columns)} columns, every evidence quote included | check any row against its "
        "paper; the one table to open first |",
        f"| `out/release/dataset.parquet`, `dataset.jsonl` | the published form: the same "
        f"{_int(len(r))} rows plus {len(extra_cols)} licence columns ({len(r.columns)} columns), "
        f"with {_int(withheld)} quotes withheld | see exactly what a stranger downloads |",
        f"| `out/review/{PER_PAPER}` | one line per paper: rows, and for each condition how "
        "many rows report it and what share | recompute the per-paper numbers (§5.1) |",
        f"| `out/review/{ICC}` | one line per paper: n_i and the successes for each metric | "
        "recompute ICC, DEFF and n_eff (§5.2) |",
        f"| `out/review/{HARM}` | one line per row: the five flags, the inputs of the zeta "
        "correction, Debye length, κa, f(κa), and the harmonised point or interval | recompute "
        "conditions_complete, κa, f and the correction (§4, §5.4, §5.5) |",
        f"| `out/review/{PAIRS}` | {len(f.pairs)} real pairs, every comparability check field "
        "by field | evaluate a pair by hand (§5.6) |",
        f"| `out/review/{AUDIT}` | {_int(len(f.audit))} rows drawn at random, with the lines "
        "they cite and empty columns for your verdicts | audit rows against the papers (§7) |",
        *(
            [
                f"| `out/tables/{ORIGIN_ROWS}` | one line per row, in the table's order: where its "
                "particle came from, as the reader classified it with the lines it cited, and "
                "`final_origin`, the verdict of a second reading by a Claude agent wherever there "
                "was one (`agent_checked`) | recount C11 (§6) |",
                "| `out/tables/sample_origin_stats.json` | the origin counts before and after the "
                "second reading, the agreement, the environmental rows' conditions and the rows "
                "that are not an own measurement | the numbers of C11, the environmental rows "
                "(§6) and §8 |",
            ]
            if f.extra.get("origin")
            else []
        ),
        "",
        "How they relate:",
        "",
        "```",
        "extractions.jsonl ──extract table──► data/processed/zeta_table.parquet",
        "                                        │ report d1",
        "                                        ▼",
        f"                    out/tables/d1_zeta_table.csv   {_int(len(t))} rows × "
        f"{len(t.columns)} columns",
        "                                        │ report release adds " + ", ".join(extra_cols),
        f"                                        │ and blanks the quote on {_int(withheld)} rows",
        "                                        ▼",
        f"                    out/release/dataset.parquet    {_int(len(r))} rows × "
        f"{len(r.columns)} columns",
        "                                        │ report review reads both",
        "                                        ▼",
        "                    out/review/REVIEW.md and five worksheets",
        "```",
        "",
        "The two tables hold the same rows in the same order; `row_id` joins them and every "
        "worksheet. The only difference is licensing: a quote from a source that is not CC BY "
        "or CC0 is present in `d1_zeta_table.csv` and blank in the release (section 3, "
        "`quote_withheld`). The repository is private, but the audit worksheet keeps the "
        "release's discipline and gives only line numbers for those rows.",
        "",
        "Spreadsheet note: the CSVs write booleans as `True` / `False`. Most spreadsheets read "
        'them as TRUE and FALSE; if yours keeps them as text, compare with `="True"` instead.',
        "",
        *_worksheet_docs(f),
    ]


# --- 2 -----------------------------------------------------------------------------------------


def section_2(f: Facts) -> list[str]:
    c, s, t = f.chain, f.stats, f.table
    avail = s.get("text_availability") or {}
    fails = ", ".join(f"{p} (HTTP {code})" for p, code in c["fetch_failures"]) or "none"
    flagged = t["flags"].fillna("").astype(str).str.strip().ne("")
    counts = Counter(x for v in t["flags"].fillna("") for x in str(v).split(";") if x)
    multi = int(t["evidence_quote"].fillna("").str.contains("||", regex=False).sum())
    models = ", ".join(f"`{m}` {_int(n)} rows" for m, n in c["models_by_row"].items())
    zeroed, stepped = len(_with_flag(t, ZERO_IONIC_STRENGTH)), len(_with_flag(t, STEP_TEMPERATURE))
    other = _with_flag(t, OTHER_STEP_TEMPERATURE)
    return [
        "## 2. Where the dataset comes from",
        "",
        "### The chain, with the count at each step",
        "",
        "```",
        "query  queries/q1.txt, sent to Europe PMC",
        f"  │    Europe PMC reports {_int(c['hits_all'])} hits in all, {_int(c['hits_oa'])} open "
        "access          (data/raw/epmc/search/hit_counts.json)",
        "  ▼",
        f"records  {_int(c['records'])} kept (a PMCID, DOI duplicates dropped), "
        f"{_int(c['records_oa'])} flagged open access   (records.parquet)",
        f"  │    full-text XML fetched for every open-access record; failed: {fails}",
        "  ▼",
        f"XMLs  {_int(c['xml'])} vendored, sha256-pinned       (data/raw/epmc/manifest.sha256)",
        f"  │    {_int(avail.get('with_retrievable_text', 0))} carry retrievable text, "
        f"{_int(avail.get('no_retrievable_text', 0))} carry none        (d1_stats.json)",
        "  ▼",
        f"extraction records  {_int(c['extraction_records'])}, one per paper read   "
        "(data/interim/extractions.jsonl)",
        f"  │    {_int(c['records_with_rows'])} hold at least one measurement, "
        f"{_int(c['records_without_rows'])} hold none",
        "  ▼",
        f"rows  {_int(c['record_rows'])}, from {_int(t['pmcid'].nunique())} papers   "
        "(out/tables/d1_zeta_table.csv)",
        "```",
        "",
        "The query, verbatim:",
        "",
        "```",
        c["query"],
        "```",
        "",
        f"Two gaps in the chain, stated rather than smoothed over. Europe PMC's open-access hit "
        f"count ({_int(c['hits_oa'])}) and the open-access records kept "
        f"({_int(c['records_oa'])}) differ by {_int(c['hits_oa'] - c['records_oa'])}: "
        "`epmc.records_to_frame` drops records with no PMCID and DOI duplicates, and the repo "
        f"does not record which step removed which record. And {_int(c['xml_without_record'])} "
        f"of the {_int(c['xml'])} XMLs have no extraction record at all; "
        f"{_int(c['xml_without_record_or_text'])} of those are among the papers with no "
        "retrievable text.",
        "",
        f"Of the {_int(s['n_papers'])} papers with rows, "
        f"{_int(s['n_papers_with_a_printed_number'])} print at least one number and "
        f"{_int(s['n_papers_measured_but_no_number_printed'])} report a measurement without "
        "printing a number anywhere in the retrievable text (`d1_stats.json`). Those papers are "
        "in the dataset on purpose: a measurement that was made and never printed is one of the "
        "things it counts.",
        "",
        "### How one row is produced",
        "",
        "```",
        "XML ──corpus parse──► extraction text ──a model reads it──► JSON rows",
        "                    (abstract, methods, tables,             │",
        "                     captions, keyword windows)             │ extract ingest",
        "                                                            ▼",
        "     coerce: numbers parsed from the strings the model copied",
        "     verify: every quote passage must be in the article, the value in its quote",
        "     flags:  anything the article does not support is flagged, never fixed",
        "                                                            │ extract retrofit (one-off)",
        "                                                            ▼",
        "     each quote located in the line-addressed document → evidence_line_ids",
        "                                                            │ extract table",
        "                                                            ▼",
        "     two ratified rules clear a value: 0 mM ionic strength, a step temperature",
        "     one table row; the five *_reported flags computed from its fields",
        "```",
        "",
        "1. **Parse.** `corpus parse` turns each XML into the text an extractor reads: abstract, "
        "methods, extra sections, keyword-context windows, tables (caption, TSV, footnotes) and "
        "figure captions (`docs/FINDINGS.md` §E1 lists this block set).",
        f"2. **Read.** A model returns JSON rows for the paper. The rows here came from {models}"
        " (`model` column). The instructions are a brief, `docs/briefs/extraction.md`, but only "
        f"{_int(c['records_with_brief'])} of the {_int(c['extraction_records'])} records carry a "
        f"brief hash, {_int(c['rows_records_with_brief'])} of them among the "
        f'{_int(c["records_with_rows"])} records that hold rows. `README.md` ("The sweep") '
        "says the records without one were produced before briefs were versioned, and that the "
        "brief behind most of them was deleted with a session scratchpad.",
        "3. **Coerce and verify** (`mnp.extract.zeta.verify_row`). Every number is parsed "
        "deterministically from the string the model copied. The quote may join several "
        "passages with ` || `; every passage must be found in the article, after dashes and "
        "whitespace are folded, or the row is marked unverified and excluded from every "
        "number. The value must appear inside its own quote, and the pH, temperature and ionic "
        "strength must each appear both in the article and in the row's own quote (medium and "
        "instrument are not checked this way); a failure adds a flag, never a "
        f"correction. {_int(c['dropped'])} raw rows were dropped at coercion and are not in the "
        f"table. {_kn(int(flagged.sum()), len(t))} rows carry at least one flag; the most "
        "common: " + ", ".join(f"`{k}` {_int(v)}" for k, v in counts.most_common(6)) + ".",
        "4. **Address.** `extract retrofit`, a one-off migration, located every verified quote "
        "in the line-addressed document and stored the ids of the lines it sits in. A line id "
        "is the first 16 hex characters of the sha256 of (section path, ordinal in the "
        "section, line text), deliberately not the line number, so a parser fix that "
        "renumbers the document leaves the citation standing (`docs/PROTOCOL.md`, "
        "`extract retrofit`).",
        "5. **Flag.** `extract table` (`ExtractionRecord.to_rows`) first applies the rules "
        "ratified on 2026-09-28 and 29, each of which keeps the row and clears the value: R1, "
        "an ionic strength of exactly 0 mM becomes unreported and gains the flag "
        f"`{ZERO_IONIC_STRENGTH}` ({_int(zeroed)} rows); R2, a temperature flagged "
        f"`{STEP_TEMPERATURE}` is removed ({_int(stepped)} rows); R2b, a temperature the "
        "row's quote does not state and its source prints only for storage, incubation, "
        f"exposure or culture is removed and flagged `{OTHER_STEP_TEMPERATURE}` "
        f"({_int(len(other))} rows in {_int(other['pmcid'].nunique())} papers, §4.4). R2b is "
        "the one rule that may read the paper, and only for a row whose temperature neither "
        "its quote nor its medium prints. The record in "
        "`extractions.jsonl` keeps what the model read. The five `*_reported` columns and "
        "`conditions_complete` are not read by a model: they are computed from the row's own "
        "fields by the `MeasurementConditions` properties in `src/mnp/schema/models.py` "
        "(section 4 gives each rule).",
        "",
        f"{_kn(multi, len(t))} rows join two or more passages in their quote: the number and "
        "its conditions are routinely sections apart.",
        "",
        '### What "verified" means, and what it does not',
        "",
        f"`evidence_verified` is true on {_kn(int(t['evidence_verified'].sum()), len(t))} rows. "
        "It means the quoted text exists in the paper. It does not mean the value was read "
        "correctly, that the condition in the quote belongs to this measurement rather than to "
        "the experiment next to it, that the paper is right, or that the model found every "
        "measurement the paper reports. Those are what the gold-set scores measure, and those "
        "scores are provisional because the gold set was annotated by a model "
        '(`out/release/DATASET_CARD.md`, "The κ audit has not been done").',
        "",
    ]


# --- 3 -----------------------------------------------------------------------------------------

#: column → (meaning, null means, read by). Values and examples are computed from the release.
COLUMN_DOCS: dict[str, tuple[str, str, str]] = {
    "pmcid": (
        "PubMed Central id of the source paper; the unit every per-paper number groups on",
        "never null",
        "every per-paper computation (`resample`, `d1`); `harmonise.models_named` picks the "
        "XML to scan by it; the release's licence lookup",
    ),
    "doi": ("DOI of the paper, as Europe PMC gave it", "no DOI given", "nothing below"),
    "year": ("publication year", "unknown", "nothing below"),
    "journal": ("journal title", "unknown", "nothing below"),
    "row_id": (
        "`<PMCID>-r<n>`, unique; joins the table, the release and every worksheet",
        "never null",
        "every worksheet; `comparability` names pairs by it",
    ),
    "particle_name": ("the paper's own name for the particle", "not named", "cell D's prompt"),
    "material": (
        "the polymer, as the paper names it",
        "the paper does not name it",
        "`comparability` identity check, through `material_key`",
    ),
    "functionalisation": (
        "surface groups or surface state, as the paper names them",
        "not stated; never read as bare",
        "`comparability` identity check, through `functionalisation_key`",
    ),
    "supplier": ("who sold the particle", "not stated", "nothing below"),
    "size_nominal_nm": (
        "the supplier's nominal size, nm",
        "not stated",
        "deliberately nothing: `ZetaRow` does not carry it, so no rule can use a nominal size",
    ),
    "size_measured_nm": (
        "measured hydrodynamic size, nm (the schema's definition)",
        "not measured or not stated",
        "κa (radius = half of it), the size check in `comparability`, `harmonise`",
    ),
    "quantity": (
        "which quantity the row reports",
        "never null",
        "`comparability` same-measurand check; `harmonise` picks the conversion by it",
    ),
    "value": (
        "the printed number",
        "the paper reports the measurement but prints no single number; `value_text` says what",
        "`harmonise` (its input); `d1` counts papers with a printed number",
    ),
    "value_text": (
        "the value verbatim when it is not one number (`not printed`, a range)",
        "`value` holds the number",
        "nothing below",
    ),
    "unit": (
        "`mV` for zeta; `um_cm_per_Vs` for mobility, i.e. µm·cm/(V·s) = 10⁻⁸ m²/(V·s)",
        "never null",
        "`harmonise` (mobility unit conversion)",
    ),
    "sd": ("standard deviation, as printed", "not printed", "nothing below"),
    "n": ("number of replicates, as printed", "not printed", "nothing below"),
    "medium_text": (
        "the dispersion medium, as the paper composes it",
        "no liquid named",
        "`medium_reported`; `comparability` medium check (normalised text)",
    ),
    "medium_class": (
        "the medium's class",
        "never null; `unreported` when no medium is named",
        "`medium_reported`; `comparability` medium check",
    ),
    "ionic_strength_mM": (
        "total ionic strength, mmol/L",
        "not reported",
        "`ionic_strength_reported`; Debye length and κa; `comparability` 10 % check",
    ),
    "ionic_strength_source": (
        "printed (`reported`), computed from a printed composition "
        "(`inferred_from_named_salt`), or neither (`unreported`)",
        "never null",
        "`ionic_strength_reported` (true only when this is not `unreported`)",
    ),
    "pH": (
        "pH, when the paper prints one number",
        "no single number",
        "`pH_reported`; `comparability` 0.2 check",
    ),
    "pH_text": (
        "pH verbatim when it is not one number (a range, `neutral`)",
        "no such text",
        "`pH_reported` (counts only if it holds a digit); `comparability` (undecidable)",
    ),
    "temperature_C": (
        "measurement temperature, °C",
        "no number",
        "`temperature_reported`; `harmonise` mobility conversion (η and ε at T); "
        "`comparability` 2 °C check",
    ),
    "temperature_qualifier": (
        "temperature verbatim when it is not a number (`room temperature`, `RT`)",
        "no such text",
        "`temperature_reported` (counts, as nominal); `comparability` (undecidable)",
    ),
    "instrument": (
        "the instrument, as named",
        "none named",
        "`instrument_reported`; `comparability` through `instrument_key`",
    ),
    "medium_reported": (
        "computed from `medium_text` and `medium_class` (§4.1)",
        "never null",
        "`conditions_complete`; `resample`; `d1`; the release card; cell D's prompt",
    ),
    "ionic_strength_reported": (
        "computed from `ionic_strength_mM` and `ionic_strength_source` (§4.2)",
        "never null",
        "as `medium_reported`",
    ),
    "pH_reported": (
        "computed from `pH` and `pH_text` (§4.3)",
        "never null",
        "as `medium_reported`",
    ),
    "temperature_reported": (
        "computed from `temperature_C` and `temperature_qualifier` (§4.4)",
        "never null",
        "as `medium_reported`",
    ),
    "instrument_reported": (
        "computed from `instrument` (§4.5)",
        "never null",
        "as `medium_reported`",
    ),
    "conditions_complete": (
        "all five flags true on this row",
        "never null",
        "`resample`; the release card; cell D's prompt",
    ),
    "medium_matches_exposure": (
        "was the zeta measured in the medium the exposure used?",
        "not judged",
        "nothing below",
    ),
    "evidence_quote": (
        "verbatim evidence; several passages are joined with ` || `",
        "in the release, exactly when `quote_withheld` is true; in d1_zeta_table.csv, never",
        "the release's withholding; your audit",
    ),
    "evidence_location": (
        "where the passages sit, as the extractor named it",
        "not given",
        "nothing below",
    ),
    "evidence_verified": (
        "every passage of the quote was found in the article",
        "never null",
        "`d1` drops rows where it is false",
    ),
    "evidence_line_ids": (
        "16-hex line ids, `;`-joined, in passage order (§2 step 4)",
        "the quote was never located",
        "`audit_sample.csv` resolves them to `PMCID:Lnn`; the release addresses withheld "
        "quotes with them",
    ),
    "evidence_quote_sha256": (
        "sha256 of the original quote's UTF-8 bytes, shipped or withheld",
        "no quote",
        "`report rehydrate` checks a restored quote against it",
    ),
    "evidence_quote_spans": (
        "for a withheld quote, a JSON address that rebuilds it from the source's lines",
        "the quote ships",
        "`report rehydrate`",
    ),
    "quote_withheld": (
        "true when the source's licence does not let the quote ship",
        "never null",
        "decides whether `evidence_quote` is blank",
    ),
    "source_licence": (
        "the licence the paper's own JATS states, read by `mnp.corpus.licence`",
        "never null",
        "`quote_withheld`",
    ),
    "flags": (
        "extraction flags, `;`-joined (§2 step 3)",
        "no flag",
        "the demo walk reads `derived_from_composition` and `ionic_strength_from_medium`",
    ),
    "model": ("which extractor produced the row", "never null", "nothing below"),
    "prompt_sha256": ("sha256 of the extraction system prompt", "never null", "nothing below"),
}


def _values(series: pd.Series) -> str:
    s = series.dropna()
    if s.empty:
        return "always empty"
    if pd.api.types.is_bool_dtype(series):
        return f"True {_int(s.sum())}, False {_int(len(s) - s.sum())}"
    if pd.api.types.is_numeric_dtype(series):
        return f"number, {s.min():g} to {s.max():g}"
    distinct = s.astype(str).value_counts()
    if len(distinct) <= 8:
        return ", ".join(f"`{_cell(k, 40)}` {_int(v)}" for k, v in distinct.items())
    return f"text, {_int(len(distinct))} distinct"


def _example_row(r: pd.DataFrame) -> int:
    ok = r["conditions_complete"] & ~r["quote_withheld"]
    richer = ok & r["value"].notna() & r["size_measured_nm"].notna()
    richer &= r["functionalisation"].notna() & r["sd"].notna()
    for mask in (richer, ok):
        hits = mask.to_numpy().nonzero()[0]
        if len(hits):
            return int(hits[0])
    return 0


def section_3(f: Facts) -> list[str]:
    r = f.release
    ex = _example_row(r)
    undocumented = [c for c in r.columns if c not in COLUMN_DOCS]
    if undocumented:
        raise ValueError(f"release columns with no entry in COLUMN_DOCS: {undocumented}")
    lines = [
        "## 3. Every column",
        "",
        f"All {len(r.columns)} columns of `out/release/dataset.parquet`, in the release card's "
        "groups (`release.COLUMN_GROUPS`). *Values* and *null* counts are computed from the "
        f"release on this build. The example is row `{r['row_id'].iloc[ex]}`, the first fully "
        "conditioned row whose quote ships and which prints a value, a measured size, a "
        "functionalisation and an sd; where it is empty, the example is the first non-empty "
        "value in the column, with its row named. *Read by* names the computations in this "
        "guide that use the column. `d1_zeta_table.csv` has the same columns minus the four "
        "the release adds (§1).",
        "",
    ]
    for group, cols in COLUMN_GROUPS:
        cols = tuple(c for c in cols if c in r.columns)
        if not cols:
            continue
        lines += [
            f"**{group}**",
            "",
            "| column | type | meaning | values | null | null means | example | read by |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for c in cols:
            meaning, null_means, read_by = COLUMN_DOCS[c]
            s = r[c]
            value = s.iloc[ex]
            where = ""
            if value is None or (isinstance(value, float) and math.isnan(value)):
                present = s.dropna()
                value = present.iloc[0] if len(present) else None
                where = f" (row `{r['row_id'].loc[present.index[0]]}`)" if len(present) else ""
            lines.append(
                f"| `{c}` | {s.dtype} | {meaning} | {_values(s)} | {_int(s.isna().sum())} | "
                f"{null_means} | `{_cell(value, 60)}`{where} | {read_by} |"
            )
        lines.append("")
    return lines


# --- 4 -----------------------------------------------------------------------------------------

#: `docs/2026-09-21-cile-a-otazky-pro-vedce.md`, Part 1, "Kterých pět podmínek…", translated.
RULES_TABLE = (
    "| condition | why a zeta value means nothing without it | counts as reported | "
    "does not count |",
    "|---|---|---|---|",
    "| **medium** | zeta is a property of the particle **and** its medium | any naming of the "
    'liquid, even "DI water", even "PBS" | the paper never names the liquid |',
    "| **ionic strength** (mM) | sets the Debye length; without it the mobility curve has no "
    'x-axis | "10 mM NaCl"; also a printed composition ("0.137 M NaCl, 0.0027 M KCl"), then '
    'as **derived** | "PBS" or "HEPES" alone; a component whose speciation the paper does not '
    "state; **the nominal value is never looked up** |",
    "| **pH** | sets the dissociation of surface groups, and for a functionalised particle "
    'even changes the sign | a number, also a range ("between 6.8 and 7.2") | "physiological '
    'pH" with no number |',
    '| **temperature** (°C) | enters ε, η and kT in every model | a number; also "room '
    'temperature", but flagged *nominal* | the temperature of incubation, exposure, storage '
    "or cultivation, **even when the paper gives no other** |",
    "| **instrument** | different instruments apply a different conversion of mobility to "
    'zeta | also a family ("Zetasizer"); brand and model is better and is stored verbatim | '
    "nothing stated |",
)


def _param_counts(f: Facts, flag: str) -> str:
    n = len(f.table)
    k = int(f.table[flag].sum())
    any_row = int((f.papers[f"{flag}_rows"] > 0).sum())
    return (
        f"Rows reporting it: **{_kn(k, n)}**. Per paper (mean of each paper's share of rows): "
        f"**{_pp(_estimate(f, flag).per_paper)}**. Papers with at least one row reporting it: "
        f"{_kn(any_row, len(f.papers))}."
    )


def section_4(f: Facts) -> list[str]:
    t = f.table
    n = len(t)
    classes = t["medium_class"].value_counts()
    sources = t.groupby("ionic_strength_source").agg(
        rows=("row_id", "size"), papers=("pmcid", "nunique")
    )
    zero = _with_flag(t, ZERO_IONIC_STRENGTH)
    ph_num = int(t["pH"].notna().sum())
    ph_text = t["pH"].isna() & t["pH_text"].notna()
    ph_digit = ph_text & t["pH_text"].fillna("").str.contains(r"\d")
    ph_nodigit = t.loc[ph_text & ~ph_digit, "pH_text"].value_counts()
    t_num = int(t["temperature_C"].notna().sum())
    t_nom = t["temperature_C"].isna() & t["temperature_qualifier"].notna()
    quals = t.loc[t_nom, "temperature_qualifier"].value_counts()
    step_flag = len(_with_flag(t, STEP_TEMPERATURE))
    other = _with_flag(t, OTHER_STEP_TEMPERATURE)
    labelled = other[other["medium_text"].fillna("").str.contains(r"[°˚º℃]")]
    keys = t["instrument"].dropna().map(comp.instrument_key)
    family = int((keys == "malvern_zetasizer_family").sum())
    literal = int(keys.str.startswith("literal:").sum())
    zero_text = (
        "An ionic strength of exactly 0 mM does not count either (ratified 2026-09-28): "
        '"no added electrolyte" says nothing was added, not that the medium holds no ions. '
        f"{_int(len(zero))} rows from {_int(zero['pmcid'].nunique())} papers printed one "
        f'(for example "{_cell(zero["medium_text"].iloc[0])}"); they keep their row, with '
        "`ionic_strength_mM` empty, `ionic_strength_source` `unreported` and the flag "
        f"`{ZERO_IONIC_STRENGTH}`, and the record still holds the 0."
        if len(zero)
        else "An ionic strength of exactly 0 mM does not count (ratified 2026-09-28); no row "
        "printed one."
    )
    return [
        "## 4. The five parameters",
        "",
        "A zeta potential is interpreted against five conditions: the medium it was measured "
        "in, that medium's ionic strength, its pH, the temperature, and the instrument. What "
        'counts as *reported* for each is written down, as "how it is counted today", in '
        "`docs/2026-09-21-cile-a-otazky-pro-vedce.md`, Part 1, in Czech. Translated:",
        "",
        *RULES_TABLE,
        "",
        "**Fully conditioned** means all five **at the same time, on one row**. That is why the "
        "number is so low.",
        "",
        "Three rules sit above that table (same document, same part):",
        "",
        "1. **Scope.** A condition holds only inside the experiment that states it. It does not "
        "carry to another preparation, even in the same paper. Ratified 13 September.",
        '2. **Absence is never filled in.** "DI water" does not mean ionic strength zero. It '
        "means medium reported, ionic strength unreported.",
        '3. **Every number is an upper bound.** "Reported" is softer than "reported as a '
        'number": a pH range counts, a nominal temperature counts, an instrument family '
        "counts. True completeness is lower still.",
        "",
        "Two layers decide a flag, and they are worth keeping apart. **The judgement** is the "
        "extracting model's: whether it filled `ionic_strength_mM`, or left it empty because "
        'the paper only says "PBS", is a reading of the paper under the brief. **The flag** is '
        "then pure code: given the fields, `MeasurementConditions` computes it the same way "
        "every time. So a spreadsheet can recompute every flag from the fields exactly, but "
        "cannot check the judgement; only the paper can (the audit sample, §7).",
        "",
        "```",
        " medium_text, medium_class ─────────────► medium_reported ─────────┐",
        " ionic_strength_mM, ionic_strength_source ► ionic_strength_reported ┤ AND of five",
        " pH, pH_text ───────────────────────────► pH_reported ─────────────┼──────────►",
        " temperature_C, temperature_qualifier ──► temperature_reported ────┤ conditions_complete",
        " instrument ────────────────────────────► instrument_reported ─────┘",
        "",
        " comparability.comparable(a, b)  rebuilds the five flags from the raw fields of both",
        "                                 rows and checks every one, plus material,",
        "                                 functionalisation, size, and κa for zeta pairs",
        " harmonise.harmonise(row)        ionic_strength_mM + size_measured_nm → κa → f(κa)",
        "                                 temperature_C → η(T), ε(T)   (mobility rows only)",
        "                                 the paper's full text        → conversion model named",
        "                                 never reads medium, pH or instrument",
        "```",
        "",
        "### 4.1 Medium",
        "",
        "Columns: `medium_text` (the value), `medium_class` (its class), `medium_reported`.",
        "",
        "Code rule (`MeasurementConditions.medium_reported`): `medium_text` is not empty **and** "
        "`medium_class` is not `unreported`. Spreadsheet: "
        '`=AND(LEN(medium_text)>0, medium_class<>"unreported")`.',
        "",
        _param_counts(f, "medium_reported"),
        "",
        "Classes: " + ", ".join(f"`{k}` {_int(v)}" for k, v in classes.items()) + ".",
        "",
        "Used by: `conditions_complete`; comparability (`medium_unreported`, "
        "`medium_class_mismatch`, `medium_text_mismatch`). Not used by harmonisation.",
        "",
        "### 4.2 Ionic strength",
        "",
        "Columns: `ionic_strength_mM` (the value), `ionic_strength_source` (how it got there), "
        "`ionic_strength_reported`.",
        "",
        "Code rule (`MeasurementConditions.ionic_strength_reported`): `ionic_strength_mM` is "
        "not empty **and** `ionic_strength_source` is not `unreported`. Spreadsheet: "
        '`=AND(ISNUMBER(ionic_strength_mM), ionic_strength_source<>"unreported")`.',
        "",
        _param_counts(f, "ionic_strength_reported"),
        "",
        "| source | rows | papers |",
        "|---|---|---|",
        *(
            f"| `{src}` | {_int(row['rows'])} | {_int(row['papers'])} |"
            for src, row in sources.sort_values("rows").iterrows()
        ),
        "",
        "`inferred_from_named_salt` means computed from a composition the paper printed; the "
        "nominal composition of a named buffer is never looked up, and a printed conductivity "
        'is never converted (`out/demo/METHOD.md`, "Ionic-strength sources"). ' + zero_text,
        "",
        "Used by: `conditions_complete`; comparability (`ionic_strength_unreported`; "
        f"`ionic_strength_mismatch` beyond {comp.IONIC_STRENGTH_REL_TOL:.0%} relative; and, "
        "through κa, the conversion-regime check); harmonisation (κa, with the size).",
        "",
        "### 4.3 pH",
        "",
        "Columns: `pH` (a single number), `pH_text` (verbatim otherwise), `pH_reported`.",
        "",
        "Code rule (`MeasurementConditions.pH_reported`): `pH` is not empty, **or** `pH_text` "
        "contains at least one digit. Spreadsheet: `=OR(ISNUMBER(pH), "
        "SUMPRODUCT(--ISNUMBER(FIND({0,1,2,3,4,5,6,7,8,9}, pH_text)))>0)`.",
        "",
        _param_counts(f, "pH_reported"),
        "",
        f"{_int(ph_num)} rows print one number; {_int(int(ph_digit.sum()))} count through "
        f"`pH_text` alone (a range, for instance); {_int(int(ph_nodigit.sum()))} carry a "
        "`pH_text` with no digit and so do **not** count ("
        + ", ".join(f'"{_cell(k, 30)}" {_int(v)}' for k, v in ph_nodigit.head(3).items())
        + ").",
        "",
        "Used by: `conditions_complete`; comparability (`pH_unreported`; `pH_not_numeric` when "
        f"a side has only text; `pH_mismatch` beyond ±{comp.PH_TOL:g}). Not used by "
        "harmonisation.",
        "",
        "### 4.4 Temperature",
        "",
        "Columns: `temperature_C` (a number), `temperature_qualifier` (verbatim otherwise), "
        "`temperature_reported`.",
        "",
        "Code rule (`MeasurementConditions.temperature_reported`): `temperature_C` is not "
        "empty, **or** `temperature_qualifier` is not empty. Spreadsheet: "
        "`=OR(ISNUMBER(temperature_C), LEN(temperature_qualifier)>0)`.",
        "",
        _param_counts(f, "temperature_reported"),
        "",
        f"{_int(t_num)} rows give a number; {_int(int(t_nom.sum()))} count only through a "
        "qualifier, i.e. a *nominal* temperature ("
        + ", ".join(f'"{_cell(k, 30)}" {_int(v)}' for k, v in quals.head(3).items())
        + f"). {_int(step_flag)} rows carry the flag `{STEP_TEMPERATURE}`: the number is "
        "attached to an incubation or exposure step in its own piece of the quote. Such a "
        "temperature is not the measurement temperature, even when the paper gives no other "
        "(ratified 2026-09-28), so those rows carry no `temperature_C` and no "
        "`temperature_qualifier` and count as **not** reporting temperature; the flag stays to "
        "say why, and the record still holds the number.",
        "",
        f"R2b (ratified 2026-09-29) clears {_int(len(other))} more, in "
        f"{_int(other['pmcid'].nunique())} papers, flagged `{OTHER_STEP_TEMPERATURE}`. Their "
        "quote does not state the temperature at all, so the verifier's step check never "
        "saw it. The rule asks where the number came from: the row's medium label when the "
        "label prints it, otherwise the paper, and clears it when that source prints it only "
        "in a phrase about storage, incubation, exposure or culture (`coerce.OTHER_STEP_RE`). "
        f"{_int(len(labelled))} rows took it from a label"
        + (f' such as "{_cell(labelled["medium_text"].iloc[0], 60)}"' if len(labelled) else "")
        + f"; {_int(len(other) - len(labelled))} from a paper that prints it only for such a "
        'step. A label that says the sample was measured at once, "(0 h at RT)", is not a '
        "step and stands; so does any temperature the paper prints once outside a step.",
        "",
        "Used by: `conditions_complete`; comparability (`temperature_unreported`; "
        "`temperature_not_numeric` when a side has only a qualifier; `temperature_mismatch` "
        f"beyond ±{comp.TEMPERATURE_TOL_C:g} °C); harmonisation of **mobility** rows only (η and "
        "ε of water at T). The zeta correction does not read it: its Debye length is fixed at "
        "25 °C (§5.4).",
        "",
        "### 4.5 Instrument",
        "",
        "Columns: `instrument`, `instrument_reported`.",
        "",
        "Code rule (`MeasurementConditions.instrument_reported`): `instrument` is not empty. "
        "Spreadsheet: `=LEN(instrument)>0`.",
        "",
        _param_counts(f, "instrument_reported"),
        "",
        f"`comparability.instrument_key` reduces the {_int(t['instrument'].nunique())} distinct "
        f"strings to {_int(keys.nunique())} keys. {_int(family)} rows name only the family "
        '(`malvern_zetasizer_family`, "Zetasizer" with no model), which counts as reported but '
        f"does not match a named model; {_int(literal)} rows name something the key does not "
        "recognise and keep a literal key, which matches only the identical string.",
        "",
        "Used by: `conditions_complete`; comparability (`instrument_unreported`; "
        "`instrument_mismatch`, which is **not** an axis difference: a different instrument "
        "makes the pair not comparable). Not used by harmonisation.",
        "",
        f"All five at once, on one row: {_kn(_complete_rows(f), n)} (section 5.1 has the "
        "per-paper readings).",
        "",
    ]


# --- 5 -----------------------------------------------------------------------------------------


def section_5_1(f: Facts) -> list[str]:
    t, papers = f.table, f.papers
    n, k = len(t), len(papers)
    stats_any = next(m for m in f.stats["missing"] if m["condition"] == "any")
    every = _every_somewhere(f)
    big = papers.sort_values(["n_rows", "pmcid"], ascending=[False, True]).iloc[0]
    small = papers[
        (papers["n_rows"] >= 3)
        & (papers["temperature_reported_share"] > 0)
        & (papers["temperature_reported_share"] < 1)
    ].sort_values(["n_rows", "pmcid"])
    small = small.iloc[0] if len(small) else papers.iloc[0]
    loo = next(
        x for x in resample.leave_one_out(t, big["pmcid"]) if x.metric == "temperature_reported"
    )
    share = _col(PER_PAPER, "temperature_reported_share")
    rows = _col(PER_PAPER, "temperature_reported_rows")
    nr = _col(PER_PAPER, "n_rows")
    ccr = _col(PER_PAPER, "conditions_complete_rows")
    ccs = _col(PER_PAPER, "conditions_complete_share")
    agree = "agrees" if k - every == stats_any["k_missing"] else "does not agree"
    sizes = t.groupby("pmcid").size()
    return [
        "### 5.1 Per-row and per-paper shares",
        "",
        "**What it computes.** How often a condition is reported, counted two ways.",
        "",
        "```",
        "per row   = (rows reporting it) / (all rows)",
        "per paper = average over papers of (that paper's rows reporting it / that paper's rows)",
        "```",
        "",
        "Per row, a paper with 90 rows has 90 votes; per paper, every paper has one. The rows "
        f"cluster by paper (median {sizes.median():g} rows per paper, maximum "
        f"{_int(sizes.max())}), so the two differ, and the per-paper figure is the one a single "
        "large paper cannot move.",
        "",
        "**Columns read.** `pmcid`, the five `*_reported` flags, `conditions_complete`. "
        "**Code.** `mnp.demo.resample.estimates` (`per_row`, `per_paper`). **Worksheet.** "
        f"`{PER_PAPER}`.",
        "",
        f"Spreadsheet: per paper `={rows}2/{nr}2` (that is `temperature_reported_share`); "
        f"per-paper mean `=AVERAGE({share}2:{share}{k + 1})`; per row "
        f"`=SUM({rows}2:{rows}{k + 1})/SUM({nr}2:{nr}{k + 1})`.",
        "",
        f"**Worked example, temperature.** `{big['pmcid']}` has {_int(big['n_rows'])} rows, "
        f"{_int(big['temperature_reported_rows'])} reporting temperature: share "
        f"{big['temperature_reported_share']:.4f}. `{small['pmcid']}` has "
        f"{_int(small['n_rows'])} rows, {_int(small['temperature_reported_rows'])} reporting it: "
        f"share {small['temperature_reported_share']:.4f}. Over all {_int(k)} papers the per-row "
        f"share is {_pp(loo.per_row_full)} and the per-paper mean {_pp(loo.per_paper_full)}. "
        f"Drop `{big['pmcid']}` and they become {_pp(loo.per_row_without)} and "
        f"{_pp(loo.per_paper_without)} (`resample.leave_one_out`): that one paper moves the "
        f"per-row figure by {100 * abs(loo.per_row_full - loo.per_row_without):.1f} points and "
        f"the per-paper one by {100 * abs(loo.per_paper_full - loo.per_paper_without):.1f}.",
        "",
        '**"Fully conditioned per paper" has three readings in this repo, and they are '
        "different numbers.** Keep them apart when quoting:",
        "",
        "| reading | number | where it is used | spreadsheet on the worksheet |",
        "|---|---|---|---|",
        f"| per row | {_kn(_complete_rows(f), n)} | the card's headline | "
        f"`=SUM({ccr}2:{ccr}{k + 1})/SUM({nr}2:{nr}{k + 1})` |",
        f"| per paper, mean of shares | {_pp(_estimate(f, 'conditions_complete').per_paper)} | "
        f"`docs/FINDINGS.md` §E2e | `=AVERAGE({ccs}2:{ccs}{k + 1})` |",
        f"| papers with at least one fully conditioned row | {_kn(_any_complete(f), k)}; "
        f"{_int(k - _any_complete(f))} have none | the Czech question list, Part 1 | "
        f'`=COUNTIF({ccr}2:{ccr}{k + 1},">0")` |',
        f"| papers reporting each condition on *some* row, not necessarily the same one | "
        f"{_kn(every, k)}; its complement, {_int(k - every)}, is `d1_stats.json`'s \"Any "
        f'condition" ({_int(stats_any["k_missing"])}), which it {agree} with | '
        "`d1_stats.json`, the card | the five `*_reported_rows` columns all `>0` |",
        "",
    ]


def section_5_2(f: Facts) -> list[str]:
    k = f.icc[0].anova.k
    last = k + 1
    cc = next(s for s in f.icc if s.metric == "conditions_complete")
    a = cc.anova
    col = _col(ICC, "conditions_complete_succ")
    nc = _col(ICC, "n_i")
    width = len(COLUMNS[ICC])
    p, bt, wt, out = (_letter(width + i) for i in (0, 1, 2, 4))
    rows = [
        ("N = Σ n_i (rows)", lambda s: _int(s.anova.n)),
        ("k (papers)", lambda s: _int(s.anova.k)),
        ("Σ n_i²", lambda s: _int(s.anova.sum_n_squared)),
        ("successes = Σ succ_i", lambda s: _int(s.successes)),
        ("p̄ = successes / N", lambda s: f"{s.anova.grand_mean:.6f}"),
        ("SSB = Σ n_i (p_i − p̄)²", lambda s: f"{s.anova.ss_between:.6f}"),
        ("SSW = Σ n_i p_i (1 − p_i)", lambda s: f"{s.anova.ss_within:.6f}"),
        ("MSB = SSB / (k − 1)", lambda s: f"{s.anova.ms_between:.6f}"),
        ("MSW = SSW / (N − k)", lambda s: f"{s.anova.ms_within:.6f}"),
        ("m0 = (N − Σ n_i² / N) / (k − 1)", lambda s: f"{s.anova.m0:.4f}"),
        ("ICC = (MSB − MSW) / (MSB + (m0 − 1) MSW)", lambda s: f"{s.anova.icc:.4f}"),
        ("DEFF = 1 + (m0 − 1) ICC", lambda s: f"{s.anova.deff:.4f}"),
        ("n_eff = N / DEFF", lambda s: f"{s.n_eff:.1f}"),
    ]
    header = "| quantity | " + " | ".join(f"`{s.metric}`" for s in f.icc) + " |"
    table = [header, "|---|" + "---|" * len(f.icc)]
    table += ["| " + label + " | " + " | ".join(fn(s) for s in f.icc) + " |" for label, fn in rows]
    ionic = next(s for s in f.icc if s.metric == "ionic_strength_reported")
    return [
        "### 5.2 ICC, DEFF and the effective sample size",
        "",
        "**What it computes.** Whether rows of one paper are more alike than rows of different "
        "papers, and what that does to the sample size.",
        "",
        "- **ICC** (intraclass correlation): the share of all variation in a yes/no flag that "
        "lies *between* papers. 0 means a paper's rows are no more alike than random rows; 1 "
        "means every paper is all-yes or all-no.",
        "- **DEFF** (design effect): how many times larger the variance of a share is than it "
        "would be if the rows were independent.",
        "- **n_eff** (effective sample size): how many independent rows the rows are worth.",
        "- **m0**: the average cluster size, adjusted because papers have unequal numbers of rows.",
        "",
        "It is a one-way random-effects ANOVA (analysis of variance: total variation split "
        "into a between-paper and a within-paper part). For a yes/no flag the within-paper sum "
        "of squares has the closed form `n_i · p_i · (1 − p_i)`.",
        "",
        "```",
        " per paper i:  n_i rows, succ_i of them true,  p_i = succ_i / n_i",
        "      │",
        "      ├─► between: SSB = Σ n_i (p_i − p̄)²   ─► MSB = SSB/(k−1) ─┐",
        "      ├─► within:  SSW = Σ n_i p_i(1 − p_i) ─► MSW = SSW/(N−k) ─┼─► ICC ─► DEFF ─► n_eff",
        "      └─► sizes:   m0 = (N − Σn_i²/N)/(k−1) ────────────────────┘",
        "```",
        "",
        "**Columns read.** `pmcid` and the metric. **Code.** `mnp.demo.resample.anova` "
        f"(`estimates` calls the same function). **Worksheet.** `{ICC}`.",
        "",
        "Every intermediate, per metric, computed on this build:",
        "",
        *table,
        "",
        f"**Recompute `conditions_complete` in a spreadsheet.** On `{ICC}` the data sit in "
        f"rows 2 to {last}; `n_i` is column {nc}, `conditions_complete_succ` column {col}. Use "
        f"columns {p}, {bt}, {wt} as helpers and put the results in column {out}:",
        "",
        "```",
        f"{p}2   ={col}2/{nc}2                    p_i                (fill down to row {last})",
        f"{out}1   =SUM({nc}2:{nc}{last})               N      → {_int(a.n)}",
        f"{out}2   =COUNT({nc}2:{nc}{last})             k      → {_int(a.k)}",
        f"{out}3   =SUM({col}2:{col}{last})/{out}1           p̄      → {a.grand_mean:.6f}",
        f"{bt}2   ={nc}2*({p}2-${out}$3)^2             between term       (fill down)",
        f"{wt}2   ={nc}2*{p}2*(1-{p}2)                  within term        (fill down)",
        f"{out}4   =SUM({bt}2:{bt}{last})               SSB    → {a.ss_between:.6f}",
        f"{out}5   =SUM({wt}2:{wt}{last})               SSW    → {a.ss_within:.6f}",
        f"{out}6   ={out}4/({out}2-1)                   MSB    → {a.ms_between:.6f}",
        f"{out}7   ={out}5/({out}1-{out}2)                  MSW    → {a.ms_within:.6f}",
        f"{out}8   =SUMSQ({nc}2:{nc}{last})             Σn²    → {_int(a.sum_n_squared)}",
        f"{out}9   =({out}1-{out}8/{out}1)/({out}2-1)            m0     → {a.m0:.4f}",
        f"{out}10  =({out}6-{out}7)/({out}6+({out}9-1)*{out}7)      ICC    → {a.icc:.4f}",
        f"{out}11  =1+({out}9-1)*{out}10                DEFF   → {a.deff:.4f}",
        f"{out}12  ={out}1/{out}11                      n_eff  → {cc.n_eff:.1f}",
        "```",
        "",
        f"The ionic-strength ICC rebuilds as {ionic.anova.icc:.4f}; `docs/FINDINGS.md` §E2e "
        "printed 0.83 (`out/demo/METHOD.md` reports the difference rather than tuning it "
        "away).",
        "",
    ]


def section_5_3(f: Facts) -> list[str]:
    ratios = [e.row_half_width / e.naive_half_width for e in f.estimates]
    rows = [
        f"| `{e.metric}` | {_pp(e.per_row)} | {_pp(e.row_ci[0])} to {_pp(e.row_ci[1])} | "
        f"±{100 * e.naive_half_width:.1f} | ±{100 * e.row_half_width:.1f} | {_pp(e.per_paper)} | "
        f"{_pp(e.paper_ci[0])} to {_pp(e.paper_ci[1])} |"
        for e in f.estimates
    ]
    temp = _estimate(f, "temperature_reported")
    k = f.icc[0].anova.k
    return [
        "### 5.3 The cluster bootstrap",
        "",
        "**What it computes.** 95 % intervals for each share that respect the clustering. A "
        "**bootstrap** re-draws the sample many times from itself and reads the interval off "
        "the spread of the re-drawn estimates; a **cluster** bootstrap re-draws whole papers, "
        "never single rows.",
        "",
        f"**Procedure** (`mnp.demo.resample._bootstrap_cis`): draw {_int(k)} paper indices with "
        f"replacement, B = {_int(resample.B)} times, from "
        f"`numpy.random.default_rng({resample.SEED})`. For each draw, per row = Σ successes of "
        "the drawn papers / Σ their rows; per paper = mean of the drawn papers' shares. A paper "
        "drawn twice counts twice. The interval is the 2.5th to 97.5th percentile of the B "
        "values. One set of draws is shared by all six metrics.",
        "",
        "**Why papers, not rows.** Rows are not independent (the ICC above), so re-drawing rows "
        "pretends there is more information than there is, and the interval comes out too "
        "narrow.",
        "",
        '**The groupby trap** (`docs/FINDINGS.md` §E2e, "Implementation trap"). An earlier '
        "implementation resampled papers, concatenated their rows and then called "
        '`groupby("pmcid")`. A paper drawn twice was merged back into one group, the '
        "replacement cancelled, and the interval came out too narrow. The rebuild re-draws "
        "*indices* and never groups by the cluster key afterwards.",
        "",
        f"**Not recomputable by hand**: it is {_int(resample.B)} × {_int(k)} random draws. What "
        "you can check is the point estimates (§5.1) and that the intervals below are the ones "
        "the code publishes. The naive half-width is `1.96 · √(p(1−p)/N)`, which ignores the "
        "clustering.",
        "",
        "| metric | per row | 95 % cluster interval | naive ± (pp) | cluster ± (pp) | "
        "per paper | 95 % cluster interval |",
        "|---|---|---|---|---|---|---|",
        *rows,
        "",
        f"Per row, the cluster interval is {min(ratios):.2f}× to {max(ratios):.2f}× the naive "
        f"one. Temperature is the widest: naive ±{100 * temp.naive_half_width:.1f} pp against "
        f"cluster ±{100 * temp.row_half_width:.1f} pp.",
        "",
    ]


def _ka_examples(h: pd.DataFrame) -> list[pd.Series]:
    known = h[h["kappa_a"].notna() & (h["kappa_a"] > 0)].sort_values(["kappa_a", "row_id"])
    if known.empty:
        return []
    picks = dict.fromkeys([0, len(known) // 2, len(known) - 1])
    return [known.iloc[i] for i in picks]


def section_5_4(f: Facts) -> list[str]:
    h = f.harmonised
    ka_known = int(h["kappa_a"].notna().sum())
    zero = h[h["kappa_a"].notna() & (h["kappa_a"] == 0)]
    over = int((h["kappa_a"] > 700).sum())
    ic, sz, db, ka_c = (_col(HARM, c) for c in ("ionic_strength_mM", "size_measured_nm",
                                                 "debye_length_nm", "kappa_a"))  # fmt: skip
    blocks: list[str] = []
    for row in _ka_examples(h):
        ionic, size = row["ionic_strength_mM"], row["size_measured_nm"]
        debye = 0.304 / math.sqrt(ionic / 1000.0)
        radius = size / 2.0
        ka = radius / debye
        e = math.exp(-ka)
        inner = 1.0 + 2.5 / (ka * (1.0 + 2.0 * e))
        formula = 1.0 + 1.0 / (2.0 * inner**3)
        fk = 1.5 if ka > 700 else formula
        _check(f"κa {row['row_id']}", ka, row["kappa_a"])
        _check(f"f {row['row_id']}", fk, row["henry_f"])
        last = (
            [f"formula 1 + 1/(2 · {inner:.6f}³)   = {formula:.6f}",
             "f    = 1.5, because κa > 700: the code's cut-off, not the formula"]
            if ka > 700
            else [f"f    = 1 + 1/(2 · {inner:.6f}³)    = {fk:.4f}"]
        )  # fmt: skip
        blocks += [
            f"`{row['row_id']}`: I = {ionic:g} mM, size = {size:g} nm",
            "",
            "```",
            f"κ⁻¹  = 0.304 / √({ionic:g}/1000)       = {debye:.4f} nm",
            f"a    = {size:g} / 2                    = {radius:.4g} nm",
            f"κa   = {radius:.4g} / {debye:.4f}      = {ka:.4f}",
            f"e^-κa                              = {e:.6g}",
            f"1 + 2.5/(κa·(1 + 2e^-κa))          = {inner:.6f}",
            *last,
            "```",
            "",
        ]
    return [
        "### 5.4 Debye length, κa and Henry's f",
        "",
        "**What it computes.** Which conversion regime a zeta value sits in.",
        "",
        "- The **Debye length** κ⁻¹ is the thickness of the cloud of ions around a charged "
        "particle; more salt makes it thinner.",
        "- **κa** is the particle radius measured in Debye lengths. Small κa: a thick cloud "
        "relative to the particle. Large κa: a thin one.",
        "- **Henry's function f(κa)** links the measured mobility to zeta. It runs from 1.0 "
        "(the **Hückel** limit, κa ≪ 1) to 1.5 (the **Smoluchowski** limit, κa ≫ 1). "
        "**Ohshima's approximation** is a closed formula for it.",
        "",
        "```",
        " ionic_strength_mM ─► κ⁻¹ = 0.304/√(I/1000) nm ─┐",
        " size_measured_nm  ─► a = size/2 ────────────────┴─► κa = a/κ⁻¹ ─► f(κa) in [1, 1.5]",
        "",
        " κ⁻¹  = 0.304 / √(I[M])  nm        1:1 electrolyte, water, 25 °C",
        " κa   = (size_measured / 2) / κ⁻¹",
        " f    = 1 + 1 / (2 · (1 + 2.5 / (κa · (1 + 2·e^(−κa))))³)",
        "```",
        "",
        "**Columns read.** `ionic_strength_mM` (only when reported), `size_measured_nm`. "
        "**Code.** `comparability.debye_length_nm`, `ZetaRow.kappa_a`, `comparability.henry_f`. "
        f"**Worksheet.** `{HARM}`: `debye_length_nm`, `kappa_a`, `henry_f`.",
        "",
        f"Spreadsheet on `{HARM}`: Debye `=0.304/SQRT({ic}2/1000)`; κa `=({sz}2/2)/{db}2`; f "
        f"`=1+1/(2*(1+2.5/({ka_c}2*(1+2*EXP(-{ka_c}2))))^3)` (section 1 gives the full "
        "formulas with the blank and zero cases).",
        "",
        f"κa is known on {_kn(ka_known, len(h))} rows: both the ionic strength and the size must "
        "be reported. Edge cases in the code: an ionic strength of 0 mM gives an infinite Debye "
        "length, which the code turns into κa = 0 and f = 1.0 ("
        + (
            f"{_int(len(zero))} rows here; their `debye_length_nm` is blank"
            if len(zero)
            else "no row here: since 2026-09-28 a 0 mM is not a reported ionic strength, §4.2"
        )
        + "); above κa = 700 the code returns f = 1.5 exactly, "
        f"which the formula approaches but does not reach ({_int(over)} rows here).",
        "",
        "**Worked examples**: the rows with the smallest, the median and the largest non-zero "
        "κa. Every line is recomputed from the two inputs, and the build refuses to render if "
        "it disagrees with the module.",
        "",
        *blocks,
        "**Limitation.** The 0.304 constant assumes a 1:1 electrolyte (NaCl-like) in water at "
        "25 °C (`comparability.debye_length_nm`). A medium with divalent ions (CaCl₂, "
        "phosphate) has a shorter true Debye length, so κa is underestimated for those rows. "
        "The row's own temperature is not used here. κa places a pair in a regime (§5.6) and "
        "also enters the correction of §5.5.",
        "",
    ]


def _harmonise_example(case: str, row: pd.Series) -> list[str]:
    v = row["value"]
    ka, fk = row["kappa_a"], row["henry_f"]
    printed = "prints no single number" if pd.isna(v) else f"reports {v:g} {row['unit']}"
    models = row["models_named"] if isinstance(row["models_named"], str) else ""
    head = (
        f"**{case}**: {CASES[case]}. `{row['row_id']}` {printed}; models named: "
        f"`{models or 'none'}`."
    )
    if case == "H":
        _check(case, v, row["point"])
        body = [f"point = reported value = {v:g} mV"]
    elif case in ("Z1", "Z2"):
        fm = 1.5 if row["why"].startswith("smoluchowski") else 1.0
        if case == "Z1":
            p = v * fm / fk
            _check(case, p, row["point"])
            body = [
                f"f_m = {fm:g}, κa = {ka:.4f}, f = {fk:.4f}",
                f"point = {v:g} × {fm:g} / {fk:.4f} = {p:.4f} mV",
            ]
        else:
            b1, b2 = v * fm / 1.5, v * fm / 1.0
            _check(case, min(b1, b2), row["low"])
            _check(case, max(b1, b2), row["high"])
            body = [
                f"f_m = {fm:g}; κa unknown, so f anywhere in [1, 1.5]",
                f"{v:g} × {fm:g} / 1.5 = {b1:.4f}    {v:g} × {fm:g} / 1 = {b2:.4f}",
                f"interval = [{min(b1, b2):.4f}, {max(b1, b2):.4f}] mV",
            ]
    elif case == "Z3":
        b1, b2 = v * 1.0 / fk, v * 1.5 / fk
        _check(case, min(b1, b2), row["low"])
        _check(case, max(b1, b2), row["high"])
        body = [
            f"κa = {ka:.4f}, f = {fk:.4f}; f_m unknown, 1 or 1.5",
            f"{v:g} × 1 / {fk:.4f} = {b1:.4f}    {v:g} × 1.5 / {fk:.4f} = {b2:.4f}",
            f"interval = [{min(b1, b2):.4f}, {max(b1, b2):.4f}] mV",
        ]
    elif case == "Z4":
        b1, b2 = v / 1.5, v * 1.5
        _check(case, min(b1, b2), row["low"])
        _check(case, max(b1, b2), row["high"])
        body = [
            f"{v:g} / 1.5 = {b1:.4f}    {v:g} × 1.5 = {b2:.4f}",
            f"interval = [{min(b1, b2):.4f}, {max(b1, b2):.4f}] mV",
        ]
    elif case in ("M1", "M2"):
        temp = row["temperature_C"]
        eta, eps = float(viscosity(temp)), float(permittivity(temp))
        mu = v * 1e-8
        head_lines = [
            f"T = {temp:g} °C: η = {eta:.6g} Pa·s, ε = {eps:.6g} F/m (water, `mnp.ek.constants`)",
            f"μ = {v:g} × 10⁻⁸ = {mu:.4g} m²/(V·s)",
        ]
        if case == "M1":
            z = 3 * eta * mu / (2 * eps * fk) * 1000
            _check(case, z, row["point"])
            body = [
                *head_lines,
                f"κa = {ka:.4f}, f = {fk:.4f}",
                f"ζ = 3·η·μ / (2·ε·f) × 1000 = {z:.4f} mV",
            ]
        else:
            z1 = 3 * eta * mu / (2 * eps * 1.0) * 1000
            z15 = 3 * eta * mu / (2 * eps * 1.5) * 1000
            _check(case, min(z1, z15), row["low"])
            _check(case, max(z1, z15), row["high"])
            body = [
                *head_lines,
                "κa unknown, so f in [1, 1.5]",
                f"ζ at f = 1: {z1:.4f} mV    at f = 1.5: {z15:.4f} mV",
            ]
    else:
        body = [f"nothing: {row['why']}"]
    return [head, "", "```", *body, "```", ""]


def section_5_5(f: Facts) -> list[str]:
    h = f.harmonised
    results = h["result"].value_counts()
    cases = h["case"].value_counts()
    released = [c for c in f.release.columns if "harmon" in c]
    examples: list[str] = []
    for case in CASES:
        hit = h[h["case"] == case]
        if len(hit):
            examples += _harmonise_example(case, hit.iloc[0])
    return [
        "### 5.5 Harmonisation: a zeta value corrected for its conversion model",
        "",
        "**The released dataset does not contain harmonised values.** Not one of the "
        f"{len(f.release.columns)} release columns holds one ({len(released)} have 'harmon' in "
        "the name). The correction is computed by code, `mnp.demo.harmonise` (used by the "
        f"demo), and here in `{HARM}`. The reason is the result itself: the correction needs "
        "parameters that are mostly unreported, so most rows get an interval rather than a "
        f"number ({_int(results.get('point', 0))} points, {_int(results.get('interval', 0))} "
        f"intervals, {_int(results.get('none', 0))} with nothing; tables below), and an "
        "interval is not a value a column can carry as if it were one.",
        "",
        "**What it computes.** The instrument measures the electrophoretic **mobility** μ, how "
        "fast the particle moves per unit of electric field. Zeta is converted from it:",
        "",
        "```",
        "μ = (2·ε·ζ / (3·η)) · f(κa)             ε permittivity, η viscosity of the liquid",
        "",
        "a paper that assumed a fixed f_m printed   ζ_rep = 3·η·μ / (2·ε·f_m)",
        "the value the physics gives is            ζ     = 3·η·μ / (2·ε·f(κa))",
        "so                                        ζ     = ζ_rep · f_m / f(κa)",
        "",
        "f_m = 1.5  Smoluchowski        f_m = 1.0  Hückel",
        "```",
        "",
        "Which model a paper applied is read from its full text by `harmonise.models_named`: "
        "a case-insensitive scan for Smoluchowski, Hückel/Huckel, Ohshima, and \"Henry's "
        'function/equation/formula". It records a **mention**, not the model applied.',
        "",
        "```",
        "row ─ quantity ─┬─ zeta ──── value printed? ─ no ───────────────────────► N  nothing",
        "                │                │ yes",
        "                │                ├─ Henry or Ohshima named ─────────────► H  point",
        "                │                ├─ exactly one limit named ─ κa known ─► Z1 point",
        "                │                │                          κa unknown ─► Z2 interval",
        "                │                └─ none, or both limits ─── κa known ─► Z3 interval",
        "                │                                           κa unknown ─► Z4 interval",
        "                └─ mobility ─ value printed? ─ no ──────────────────────► N  nothing",
        "                                  │ yes ─ temperature? ─ no ────────────► M0 nothing",
        "                                           yes ─ κa known ──────────────► M1 point",
        "                                                 κa unknown ────────────► M2 interval",
        "```",
        "",
        "Naming both Smoluchowski and Hückel without Henry is treated as *unknown*: papers "
        'usually write "Smoluchowski rather than Hückel", and a mention cannot say which was '
        'applied (`docs/DESIGN_2026-09-28_demo.md`, "Which model counts as named"). A mobility '
        "row with no measurement temperature gives nothing, never a 25 °C default.",
        "",
        "**Columns read.** `quantity`, `value`, `unit`, `pmcid` (for the text scan), "
        "`ionic_strength_mM` and `ionic_strength_source`, `size_measured_nm`, `temperature_C`. "
        f"**Code.** `mnp.demo.harmonise.harmonise`. **Worksheet.** `{HARM}`: `case`, `result`, "
        "`point`, `low`, `high`, `why`, and `models_named`.",
        "",
        "Counts on this build:",
        "",
        "| result | rows |",
        "|---|---|",
        *(f"| {r} | {int(results.get(r, 0))} |" for r in ("point", "interval", "none")),
        "",
        "| case | meaning | rows |",
        "|---|---|---|",
        *(f"| {c} | {CASES[c]} | {_int(cases.get(c, 0))} |" for c in CASES),
        "",
        f"Most rows are Z4 ({_int(cases.get('Z4', 0))}): no model named and no κa, so the true "
        "value lies anywhere between ζ_rep / 1.5 and ζ_rep × 1.5. Every `none` carries its "
        "reason in `why`.",
        "",
        "**Worked examples**, the first row of each case in table order. Each result is "
        "recomputed from the inputs shown and checked against the worksheet at build time.",
        "",
        *examples,
    ]


RULES: tuple[tuple[str, str, str, str, str, str], ...] = (
    ("1", "quantity_mismatch", "quantity", "mismatch", "the two quantities differ", "identical"),
    ("2", "material_unreported", "material", "unreported", "either material is empty", "—"),
    ("3", "material_mismatch", "material", "mismatch", "`material_key` differs", "identical"),
    (
        "4",
        "functionalisation_unreported",
        "functionalisation",
        "unreported",
        "either is empty",
        "—",
    ),  # fmt: skip
    (
        "5",
        "functionalisation_mismatch",
        "functionalisation",
        "mismatch",
        "`functionalisation_key` differs",
        "identical",
    ),  # fmt: skip
    ("6", "medium_unreported", "medium", "unreported", "either `medium_reported` is false", "—"),
    ("7", "medium_class_mismatch", "medium", "mismatch", "classes differ", "identical"),
    (
        "8",
        "medium_text_mismatch",
        "medium",
        "mismatch",
        "same class, normalised text differs",
        "identical",
    ),  # fmt: skip
    (
        "9",
        "ionic_strength_unreported",
        "ionic_strength",
        "unreported",
        "either not reported",
        "—",
    ),  # fmt: skip
    (
        "10",
        "ionic_strength_mismatch",
        "ionic_strength",
        "mismatch",
        "\\|a−b\\| / max(\\|a\\|,\\|b\\|) above the tolerance",
        f"{comp.IONIC_STRENGTH_REL_TOL:.0%} relative",
    ),  # fmt: skip
    ("11", "pH_unreported", "pH", "unreported", "either not reported", "—"),
    ("12", "pH_not_numeric", "pH", "undecidable", "reported, but one side is text only", "—"),
    (
        "13",
        "pH_mismatch",
        "pH",
        "mismatch",
        "\\|a−b\\| above the tolerance",
        f"±{comp.PH_TOL:g}",
    ),  # fmt: skip
    ("14", "temperature_unreported", "temperature", "unreported", "either not reported", "—"),
    (
        "15",
        "temperature_not_numeric",
        "temperature",
        "undecidable",
        "reported, but one side is a qualifier only",
        "—",
    ),  # fmt: skip
    (
        "16",
        "temperature_mismatch",
        "temperature",
        "mismatch",
        "\\|a−b\\| above the tolerance",
        f"±{comp.TEMPERATURE_TOL_C:g} °C",
    ),  # fmt: skip
    ("17", "instrument_unreported", "instrument", "unreported", "either not named", "—"),
    (
        "18",
        "instrument_mismatch",
        "instrument",
        "mismatch",
        "`instrument_key` differs",
        "identical",
    ),  # fmt: skip
    (
        "19",
        "size_measured_unreported",
        "size_measured_nm",
        "unreported",
        "zeta pair, and either size is empty",
        "—",
    ),  # fmt: skip
    (
        "20",
        "conversion_regime_mismatch",
        "conversion_model",
        "mismatch",
        "zeta pair, both κa known, f differs beyond the tolerance",
        f"{comp.HENRY_REL_TOL:.0%} relative in f",
    ),  # fmt: skip
)


def section_5_6(f: Facts) -> list[str]:
    t = f.table
    n = len(t)
    comparable = _by_verdict(f, comp.Comparability.comparable)
    cond = _by_verdict(f, comp.Comparability.conditionally_comparable)
    comp_zz = [s for s in comparable if _zeta_pair(s)]
    comp_cross = [s for s in comparable if s.a.pmcid != s.b.pmcid]
    zz_cross = [s for s in comp_zz if s.a.pmcid != s.b.pmcid]
    cond_cross = [s for s in cond if s.a.pmcid != s.b.pmcid]
    rows = [comp.ZetaRow.from_mapping(r) for r in t.to_dict("records")]
    candidates = sum(1 for r in rows if comp._fully_reported(r))
    n_zeta = int((t["quantity"] == "zeta_potential").sum())
    key = pd.DataFrame(f.key)
    strata = key.groupby(["stratum", "verdict"]).size().unstack(fill_value=0)
    verdicts = ("comparable", "conditionally_comparable", "not_comparable")
    strata_rows = [
        f"| `{s}` | {_int(comp.STRATUM_SIZES.get(s, 0))} | {_int(strata.loc[s].sum())} | "
        + " | ".join(_int(strata.loc[s].get(v, 0)) for v in verdicts)
        + " |"
        for s in comp.STRATA
        if s in strata.index
    ]
    pairs = []
    for pair in f.pairs:
        v = pair.verdict
        codes = ", ".join(f"`{c}`" for c in v.codes) or "no blockers"
        pairs.append(
            f"- **{pair.pair_id}** `{pair.a['row_id']}` × `{pair.b['row_id']}`, "
            f"{pair.why_chosen}: **{v.verdict.value}**; {codes}."
        )
    return [
        "### 5.6 Comparability",
        "",
        "**What it computes.** For a *pair* of rows: may the two numbers be compared, and if "
        "not, what blocks it. `comparable` means a difference between them is attributable to "
        "the particle. No paper states this, since no paper knows about the other one; it "
        "exists only in the join of two rows, which is why it is computed rather than "
        "extracted. The reported value is never used: `ZetaRow` carries no `value`, so a "
        "similar zeta cannot stand in for a similar particle.",
        "",
        "**Columns read** (through `ZetaRow.from_mapping`): `row_id`, `pmcid`, `quantity`, "
        "`material`, `functionalisation`, `size_measured_nm`, `medium_text`, `medium_class`, "
        "`ionic_strength_mM`, `ionic_strength_source`, `pH`, `pH_text`, `temperature_C`, "
        "`temperature_qualifier`, `instrument`. It does not read the `*_reported` columns; it "
        "rebuilds them with the same `MeasurementConditions` code. **Code.** "
        f"`mnp.eval.comparability.comparable`. **Worksheet.** `{PAIRS}`.",
        "",
        "Every rule, in the order the code runs them. A blocker's **kind** is `unreported` "
        "(the paper never said; nothing may default it), `undecidable` (it said something that "
        "is not a comparable number), or `mismatch` (both said, and they differ).",
        "",
        "| # | blocker code | field | kind | fires when | tolerance |",
        "|---|---|---|---|---|---|",
        *(f"| {a} | `{b}` | `{c}` | {d} | {e} | {g} |" for a, b, c, d, e, g in RULES),
        "",
        "Rules 1, 2–5, 6–18 and 19–20 live in `_measurand_blockers`, `_identity_blockers`, "
        "`_condition_blockers` and `_conversion_blockers`. The size and κa rules apply only "
        "when both rows are zeta potentials: mobility is what is measured, so two mobilities "
        "have no conversion between them. When κa is unknown the κa rule adds nothing, because "
        "the ionic-strength rule has already blocked.",
        "",
        "**Grading** (`comparability._grade`):",
        "",
        "```",
        "no blockers                          → comparable",
        "every blocker is an axis code        → conditionally_comparable",
        "anything else                        → not_comparable",
        "",
        "axis codes: " + ", ".join(sorted(comp._AXIS_CODES)),
        "```",
        "",
        "An axis difference is a stated, quantified difference in a condition: the two rows "
        "sit on a common axis (a titration), not in a comparison. A different instrument, "
        "particle, measurand or conversion regime is not an axis.",
        "",
        "**The census** (`comparability.graded_census`). Every `*_unreported` rule fires when "
        "either row lacks the field, so a row missing any of them can never be half of a "
        f"comparable pair. That turns the search into a row filter: {_int(candidates)} of "
        f"{_int(n)} rows pass it, so {_int(math.comb(candidates, 2))} pairs are checked instead "
        f"of all {_int(math.comb(n, 2))}.",
        "",
        "| | pairs |",
        "|---|---|",
        f"| all unordered pairs of rows | {_int(math.comb(n, 2))} |",
        f"| zeta × zeta pairs ({_int(n_zeta)} zeta rows) | {_int(math.comb(n_zeta, 2))} |",
        f"| **comparable** | **{len(comparable)}** |",
        f"| of which zeta × zeta | {len(comp_zz)} |",
        f"| of which across papers | {len(comp_cross)} |",
        f"| zeta × zeta across papers | {len(zz_cross)} |",
        f"| conditionally comparable | {len(cond)} |",
        f"| of which across papers | {len(cond_cross)} |",
        "",
        "**The kind E answer key** (`queries/kind_e_comparability.csv`) is five seeded strata "
        "plus the whole census unioned in, so a rare positive is never sampled away "
        f"({_int(len(key))} pairs):",
        "",
        "| stratum | sampled | pairs | comparable | conditionally | not comparable |",
        "|---|---|---|---|---|---|",
        *strata_rows,
        "",
        "**The counterfactual**, quoted from `docs/FINDINGS_comparability.md` §4c (no committed "
        "code recomputes it; see §8). Drop every `*_unreported` rule, i.e. let an unreported "
        "condition take a default, and the comparable count rises from 16 to **81 624** pairs, "
        "4.57 % of all pairs. Dropping every agreement, identity, measurand and physics rule "
        "instead raises it only to 51. The count is driven by what papers do not say, not by "
        "strict tolerances.",
        "",
        f"**The worked pairs** (`{PAIRS}`, one line per check):",
        "",
        *pairs,
        "",
    ]


def section_5(f: Facts) -> list[str]:
    return [
        "## 5. Every formula",
        "",
        "Each formula: what it computes, the formula, the columns it reads, the code, a worked "
        "example on real rows, and the worksheet where every row is computed.",
        "",
        *section_5_1(f),
        *section_5_2(f),
        *section_5_3(f),
        *section_5_4(f),
        *section_5_5(f),
        *section_5_6(f),
    ]


# --- 6 -----------------------------------------------------------------------------------------


def _claim(title: str, number: str, computed: str, verify: str, caveats: str) -> list[str]:
    return [
        f"#### {title}",
        "",
        f"- **Number.** {number}",
        f"- **Computed as.** {computed}",
        f"- **Check it.** {verify}",
        f"- **Caveats.** {caveats}",
        "",
    ]


def _acc(run: Any, kind: str) -> str:
    s = run.summaries.get(kind)
    return "—" if s is None else f"{round(s.accuracy * s.n)}/{s.n}"


def section_6(f: Facts) -> list[str]:
    t, papers = f.table, f.papers
    n, k = len(t), len(papers)
    icc = [s.anova.icc for s in f.icc]
    neff = [s.n_eff for s in f.icc]
    ionic_papers = int((papers["ionic_strength_reported_rows"] > 0).sum())
    comparable = _by_verdict(f, comp.Comparability.comparable)
    comp_zz = [s for s in comparable if _zeta_pair(s)]
    cross = [s for s in comparable if s.a.pmcid != s.b.pmcid]
    cond = _by_verdict(f, comp.Comparability.conditionally_comparable)
    results = f.harmonised["result"].value_counts()
    cc_letter = _letter(t.columns.get_loc("conditions_complete"))
    ratios = [e.row_half_width / e.naive_half_width for e in f.estimates]
    sc = f.scan
    res = _col(HARM, "result")
    lines = [
        "## 6. What the dataset proves, and what it does not",
        "",
        "Each claim: the sentence, the number, how it is computed, how to check it yourself, "
        "and what it does not cover. The pandas one-liners assume "
        '`t = pd.read_csv("out/tables/d1_zeta_table.csv")`.',
        "",
    ]
    lines += _claim(
        "C1. Only a small minority of rows are fully conditioned",
        f"{_kn(_complete_rows(f), n)}.",
        "rows where all five flags are true, over all rows (`conditions_complete`).",
        f"in `d1_zeta_table.csv`, `=COUNTIF({cc_letter}:{cc_letter},TRUE)` over "
        "`=COUNTA(A:A)-1`; pandas `t.conditions_complete.sum(), len(t)`.",
        "an upper bound: a range, a nominal temperature and an instrument family all count as "
        "reported (§4). It depends on the extraction being right, which is unaudited.",
    )
    lines += _claim(
        "C2. Per paper it is lower still",
        f"mean of per-paper shares {_pp(_estimate(f, 'conditions_complete').per_paper)}; "
        f"{_kn(_any_complete(f), k)} papers have at least one fully conditioned row.",
        "§5.1; the mean gives each paper one vote.",
        f"`{PER_PAPER}`: `=AVERAGE` of `conditions_complete_share`, and `=COUNTIF` of "
        '`conditions_complete_rows` `">0"`; pandas '
        "`t.groupby('pmcid').conditions_complete.mean().mean()`.",
        "three different per-paper readings exist in the repo (§5.1 table); say which one.",
    )
    ionic_mean = _estimate(f, "ionic_strength_reported").per_paper
    lines += _claim(
        "C3. Ionic strength is the least reported condition",
        f"per row {_kn(int(t['ionic_strength_reported'].sum()), n)}; per-paper mean "
        f"{_pp(ionic_mean)}; papers with any row reporting it {_kn(ionic_papers, k)}.",
        "§4.2 and §5.1.",
        f"`{PER_PAPER}`, the `ionic_strength_reported_*` columns; pandas "
        "`t.groupby('pmcid').ionic_strength_reported.any().sum()`.",
        f'"{_pp(ionic_mean)} of papers report ionic strength" is the mean share, not the share '
        f"of papers that report it on some row ({_pct(ionic_papers, k)}). The rule never "
        "converts conductivity and never looks up a buffer, which lowers it deliberately.",
    )
    lines += _claim(
        "C4. Most papers that report zeta do not name the conversion model",
        f"{sc.zeta_not_named} / {sc.zeta_papers} ({_pct(sc.zeta_not_named, sc.zeta_papers)}) of "
        f"papers with a zeta row name no model; {sc.mobility_named} / {sc.mobility_papers} "
        "papers with a mobility row name one.",
        "`harmonise.scan`: papers with a row of that quantity (value printed or not), whose "
        "vendored full text matches the model scan (§5.5).",
        "`from mnp.demo.harmonise import scan; scan(t)`; for one paper, "
        "roughly, `grep -ciE 'smoluchowski|h(u|ü)ckel|ohshima|henry.?s?[[:space:]]+"
        "(function|equation|formula)' data/raw/epmc/xml/<PMCID>.xml` (the scan runs on the "
        "parsed text, so an XML character entity can make grep miss a Hückel the scan finds).",
        "a mention is not the model applied, so the named count is an upper bound on papers "
        "that name what they used; a spelling the scan does not know would be missed; the "
        f"mobility group is {sc.mobility_papers} papers, too few for a ratio "
        "(`docs/FINDINGS.md` §E2b).",
    )
    lines += _claim(
        "C5. Almost no pair of measurements can be compared, and no zeta across papers",
        f"**{len(comparable)}** comparable pairs of {_int(math.comb(n, 2))}; {len(comp_zz)} are "
        f"zeta × zeta; {len(cross)} cross a paper boundary. {len(cond)} more are conditionally "
        "comparable.",
        "§5.6: `comparability.graded_census` over the rows that report everything.",
        f"evaluate `{PAIRS}` by hand; in Python, "
        "`from mnp.eval.comparability import ZetaRow, graded_census; "
        "graded_census([ZetaRow.from_mapping(r) for r in t.to_dict('records')])`.",
        "the rules and tolerances are this project's own, not a published standard; the κa "
        "rule rests on the 1:1 Debye length; every verdict inherits the extraction; the "
        "counterfactual of 81 624 is quoted, not recomputed.",
    )
    lines += _claim(
        "C6. Reporting behaves like a property of the paper, not of the measurement",
        f"ICC {min(icc):.2f} to {max(icc):.2f} across the six metrics.",
        "§5.2, one-way random-effects ANOVA over papers.",
        f"recompute one metric from `{ICC}` (§5.2 gives every cell).",
        "ICC says rows of one paper agree on whether a condition is reported; it does not say "
        "why. One Methods sentence often covers every row of a paper, which produces the same "
        "pattern with no habit behind it. And a paper is not a lab: two papers from one group "
        "count as independent here, which the Czech question list itself asks about (Part 2, "
        'G2). "A property of the laboratory" (`docs/FINDINGS.md` §E2e) is an interpretation.',
    )
    lines += _claim(
        "C7. The effective sample size is about the number of papers, not of rows",
        f"n_eff {min(neff):.0f} to {max(neff):.0f}, against {_int(n)} rows and {_int(k)} papers.",
        "n_eff = N / DEFF (§5.2).",
        f"`{ICC}`, last step of §5.2.",
        "it differs by metric; the bootstrap intervals (§5.3) are the ones to quote. Naive "
        f"intervals are {min(ratios):.1f}× to {max(ratios):.1f}× too narrow per row.",
    )
    lines += _claim(
        "C8. Most zeta values cannot be put on a common scale",
        f"{_int(results.get('point', 0))} rows get a harmonised point, "
        f"{_int(results.get('interval', 0))} an interval, {_int(results.get('none', 0))} "
        "nothing.",
        "§5.5, `harmonise.harmonise` on every row.",
        f'`{HARM}`: `=COUNTIF({res}:{res},"point")`.',
        "a point is conditional on the mentioned model being the one applied and on a 1:1 "
        "electrolyte; the Henry case takes the paper's value as it stands.",
    )
    d, b = f.grid.get("D"), f.grid.get("B")
    if d and b:
        kinds = sorted(set(d.summaries) | set(b.summaries))
        acc = "; ".join(f"{kind} {_acc(d, kind)} vs {_acc(b, kind)}" for kind in kinds)
        dv = {v: (nn, c, r) for v, nn, c, r in d.verdicts}
        bv = {v: (nn, c, r) for v, nn, c, r in b.verdicts}
        rec = "; ".join(
            f"{v}: D {dv[v][1]}/{dv[v][0]}, B {bv[v][1]}/{bv[v][0]}"
            for v in ("comparable", "conditionally_comparable", "not_comparable")
            if v in dv and v in bv
        )
        said = ", ".join(f"`{name}` {_int(v)}" for name, v in b.said.most_common())
        n_not, n_e = bv["not_comparable"][0], bv["balanced_accuracy"][0]
        missing_cells = [c for c in ("C", "E") if c not in grid.BUILDERS]
        lines += _claim(
            "C9. On the eval grid the structured cell beats the retrieval cell, and kind E "
            "shows why accuracy alone misleads",
            f"accuracy per kind, cell D vs cell B: {acc}. Kind E recall per true verdict: "
            f"{rec}; balanced accuracy D {dv['balanced_accuracy'][2]} vs B "
            f"{bv['balanced_accuracy'][2]}. Cell B's kind E verdicts: {said}.",
            f"the committed runs `data/interim/runs/{RUN_IDS['D']}` and "
            f"`data/interim/runs/{RUN_IDS['B']}` ({d.answered} and {b.answered} answers of "
            f"{d.asked} and {b.asked} asked; {d.refused} and {b.refused} recorded refusals), "
            "re-aggregated here with `scoring.aggregate` and `scoring.verdict_table` from their "
            "`scored.jsonl`. **Balanced accuracy** is the mean of the recall on each true "
            "verdict, so a cell that always answers the majority class cannot score well. The "
            "kinds: A a value with its condition (key from the gold set), B what a paper did "
            "not report (key: the `*_reported` flags), C a numeric filter across papers, D a "
            "mechanism, judged grounded against every passage stating it, E comparability "
            "(key: §5.6).",
            f"`data/interim/runs/{RUN_IDS['B']}/verdicts.tsv` and `scores.tsv`, and the same "
            "for cell D.",
            "Cell B, given only BM25-retrieved lines and no table, answered `not_comparable` to "
            f"{_int(b.said.get('not_comparable', 0))} of {_int(sum(b.said.values()))} pairs; "
            f"its kind E accuracy {_acc(b, 'E')} sits next to the share of `not_comparable` in "
            f"the key ({n_not}/{n_e}), which is why the recall table exists. What it does "
            "**not** mean: that the reader reasons better with the table. Cell D's kind E "
            "prompt contains the computed verdict and its blockers "
            "(`cells.build_d_comparability` prints `comparability_verdict=`), so its perfect "
            "kind E score measures reading the key back. One reader model "
            f"(`{grid.READER_MODEL}`) and one run per cell; cells "
            f"{' and '.join(missing_cells)}, the agentic ones, have not run; the kind A key "
            "comes from the model-annotated gold set.",
        )
    lines += _claim(
        "C10. Every quote exists in its paper",
        f"{_kn(int(t['evidence_verified'].sum()), n)} rows verified.",
        "`verify_row` at ingest (§2).",
        f"`{AUDIT}`, twenty rows against the papers (§7).",
        'it proves the text exists, not that it was read correctly (§2, "What verified means").',
    )
    o = f.extra.get("origin")
    if o:
        lines += _origin_claim(o)
        lines += _environmental_conditions(o)
    g = f.extra.get("gold") or {}
    annot = ", ".join(f"`{a}` {v}" for a, v in (g.get("annotators") or {}).items()) or "unknown"
    lines += [
        "### What the dataset does NOT prove",
        "",
        "- **That the values are physically true.** A row is a reported measurement, not a "
        "verified quantity: the quote is checked against the paper, the paper is not checked "
        "against reality (`out/release/DATASET_CARD.md`, limit 5).",
        f"- **That it represents the literature.** One database, open access only: "
        f"{_int(f.chain['hits_oa'])} open-access hits of {_int(f.chain['hits_all'])} in Europe "
        "PMC, and the card notes OpenAlex indexes roughly three times as much of this "
        "literature. The fractions are fractions of one database's open-access subset (card, "
        "limits 1 and 2).",
        f"- **That the extraction is accurate.** The gold set it is scored against "
        f"({_int(g.get('rows', 0))} rows, {_int(g.get('papers', 0))} papers; annotators: "
        f"{annot}) was annotated by a model; rows re-judged by a human: "
        f"{_int(g.get('human_rows', 0))}. No κ (Cohen's kappa, agreement between two "
        "annotators beyond chance) has been computed.",
        "- **Which conversion model a paper applied.** The scan finds mentions; a mention in a "
        "background paragraph is not the model used. Every harmonised point is conditional on "
        "it.",
        "- **The true Debye length of any medium with divalent ions.** κ⁻¹ assumes a 1:1 "
        "electrolyte at 25 °C.",
        "- **How a reader performs in general.** The grid is one reader model and one run per "
        "cell, on this project's own question sets.",
        "- **Anything about agentic retrieval.** Cells C and E, where the reader chooses what "
        "to fetch, have not been run (`grid.BUILDERS` holds only "
        + ", ".join(sorted(grid.BUILDERS))
        + ").",
        "- **That the comparability verdicts are the field's.** The kind E key is this "
        "project's own rules and tolerances; nobody outside the project has ratified them (the "
        "Czech question list, Part 2 E1–E3, asks scientists exactly this).",
        "- **That two comparable rows hold the same particle.** The key compares the reported "
        "*description*; suppliers, charge densities and ageing that were not printed are "
        "invisible (`docs/FINDINGS_comparability.md` §6).",
        *([_origin_not_proved(o)] if o else []),
        "",
    ]
    return lines


def _origin_claim(o: dict) -> list[str]:
    h, n = o["after_second_reading"], o["rows"]
    rows, where, env = h["origin"]["rows"], h["environment"], h["environmental_rows"]
    hc, reader = o["second_reading"], o["reader"]
    elsewhere = [
        f"{where['rows'][e]} {ENV_LABEL[e]}"
        for e in ENVIRONMENTS
        if e != "wastewater" and where["rows"][e]
    ]
    empty = [ENV_LABEL[e] for e in ENVIRONMENTS if e != "air_dust" and not where["rows"][e]]
    unclear_missed = [d for d in hc["disagreements"] if d["stratum"] == "unclear"]
    stated = sum(d["checked_origin"] != "unclear" for d in unclear_missed)
    whole = env.get("whole_sample_papers") or []
    rnd = hc["random"]
    fo = _letter(ROW_COLUMNS.index("final_origin"))
    return _claim(
        "C11. The particles measured are almost all synthetic",
        f"{_kn(h['synthetic']['rows'], n)} rows measure a synthetic particle: "
        f"{_kn(rows['commercial'], n)} bought ready-made (`commercial`) and "
        f"{_kn(rows['lab_fabricated'], n)} made in a lab (`lab_fabricated`). "
        f"{_kn(rows['environmental'], n)} are real environmental particles, from "
        f"{env['papers']} papers: {where['rows']['wastewater']} of them wastewater effluent, "
        f"from {where['papers']['wastewater']} papers"
        + (f", and {', '.join(elsewhere)}" if elsewhere else "")
        + f". {_kn(rows['unclear'], n)} stay `unclear`"
        + (f", and {_int(rows['unanswered'])} were never answered" if rows["unanswered"] else "")
        + f". Air or dust: {where['rows']['air_dust']} rows; "
        + (", ".join(empty) + ": 0 rows each." if empty else "every other environment has a row."),
        f"one question per paper, asked of all {_int(o['papers'])} papers by the grid's "
        f"isolated reader (`{reader['model']}`, run `{o['run_id']}`) over the lines that speak "
        "to where the particles came from, with a cited line for every particle it classified "
        f"({_int(reader['total']['calls'])} calls with the pilots, "
        f"{reader['total']['input_tokens'] / 1e6:.2f} M input tokens, "
        f"${reader['total']['cost_usd']:.2f}). Bought means received ready-made as particles; "
        "made in a lab covers milling, fragmentation, synthesis or release from a product, even "
        "from a bought or collected bulk plastic; environmental means collected from a real "
        "environment and isolated. The liquid is not the origin: a bought bead dispersed in "
        "lake water is commercial. `report origin` matches each answer to the rows by "
        f"`particle_name` ({_int(o['matching']['rows_exact'])} of {_int(n)} exactly) and takes "
        "the verdict of a second reading wherever there was one: a Claude agent read the "
        "particle again with the paper's full text "
        f"({_int(h['particles_with_a_second_reading'])} particles).",
        f"`out/tables/{ORIGIN_ROWS}`, one line per row in the table's order. `final_origin` "
        "(column " + fo + ") is the second reading's verdict where `agent_checked` is true and "
        "the reader's `origin` everywhere else, and `final_environment` likewise: "
        f'`=COUNTIF({fo}:{fo},"commercial")` and so on over `=COUNTA(A:A)-1`; pandas '
        '`o = pd.read_csv("out/tables/sample_origin.csv"); o.final_origin.value_counts()`, and '
        '`o[o.final_origin == "environmental"].groupby("final_environment").pmcid'
        '.agg(["size", "nunique"])`. `origin_citations` gives the lines the reader cited '
        f"(`PMCID:Lnn`); the second reading's verdicts and notes are "
        f"`data/interim/origin/hand_check-{o['run_id']}.jsonl` (the file name is older than "
        "this wording; the reading in it is Claude's).",
        "the second reading is Claude's judgement, not a person's: no row has been audited by "
        f"a person yet (§7, `{AUDIT}`). Outside it the reader's answer stands. It covered every "
        f"environmental particle ({hc['environmental']['agree']} / {hc['environmental']['n']} "
        f"agree), {hc['unclear']['n']} of the unclear ones ({hc['unclear']['agree']} / "
        f"{hc['unclear']['n']}; "
        + (
            f"each of the {stated} disagreements is"
            if stated == len(unclear_missed)
            else f"{stated} of the {len(unclear_missed)} disagreements are"
        )
        + " an origin the paper states and the reader missed) and a seeded "
        f"{rnd['n']} of the rest ({rnd['agree']} / {rnd['n']}, {_pct(rnd['agree'], rnd['n'])}, "
        f"on the four classes; {rnd['agree_synthetic_split']} / {rnd['n']} on synthetic against "
        "environmental). So `unclear` is an upper bound on what the papers leave unsaid, and the "
        "split between bought and lab-made is the least certain part. "
        + (
            f"In {len(whole)} of the {where['papers']['wastewater']} wastewater papers the zeta "
            "potential is of the collected effluent as a whole, not of isolated plastic, and "
            if whole
            else ""
        )
        + f"{len(o['not_own_measurement'])} rows are not the authors' own measurement of a "
        "plastic particle (§8); all are left in the counts above.",
    )


def _environmental_conditions(o: dict) -> list[str]:
    env = o["after_second_reading"]["environmental_rows"]
    k, reported = env["rows"], env["reported"]
    medium = env["medium_class"]
    whole = env.get("whole_sample_papers") or []
    printed = env.get("conductivity_in_text") or []
    rows = [
        f"| {label} | **{reported[key]['n']} / {k}** |"
        if key == "ionic_strength"
        else f"| {label} | {reported[key]['n']} / {k} |"
        for key, label in ORIGIN_CONDITIONS
    ]
    lines = [
        "### The environmental rows' conditions",
        "",
        f"The {k} rows a Claude agent's second reading confirmed as environmental (C11), from "
        f"{env['papers']} papers, against the five conditions:",
        "",
        "| condition | rows reporting it |",
        "|---|---|",
        *rows,
        f"| all five | {env['conditions_complete']['n']} / {k} |",
        "",
        f"{env['own_sample_liquid']} / {k} were measured in the sample's own liquid ("
        + ", ".join(f"{v} filed `{c}`" for c, v in sorted(medium.items()))
        + f") and {env['lab_liquid']} in a laboratory liquid."
        + (
            f" In {len(whole)} of the {env['papers']} papers ({', '.join(whole)}) the zeta "
            "potential is of the collected effluent as a whole, not of plastic isolated from it."
            if whole
            else ""
        ),
        "",
        "> **Ionic strength: not reported, and not estimable for these rows.** Not one of the "
        f"{k} environmental rows reports an ionic strength ({reported['ionic_strength']['n']} / "
        f"{k}). Where a paper prints the conductivity of the liquid a particle was measured in, an "
        "ionic strength could be estimated from it with Griffin and Jurinak's relation, "
        f"I (mM) ≈ {GRIFFIN_JURINAK} × EC (µS/cm), and it would have to be marked as estimated, "
        "never as reported. **Here that is not possible for any of them:** no conductivity "
        f"reaches a row ({env['conductivity_printed']} / {k} print one in their medium or their "
        "quote), so the dataset holds no ionic strength, reported or estimated, for any "
        "environmental particle.",
    ]
    if printed:
        papers = ", ".join(p["pmcid"] for p in printed)
        lines += [
            ">",
            f"> The full texts print a conductivity in {len(printed)} of the {env['papers']} "
            f"papers ({papers}), and none of it belongs to a row's measurement:",
            ">",
            "> | line | the sentence |",
            "> |---|---|",
            *(
                f"> | `{x['line']}` | "
                + (
                    _cell(x["sentence"], 320)
                    if x["sentence"]
                    else "withheld: the licence allows no quote"
                )
                + " |"
                for p in printed
                for x in p["lines"]
            ),  # fmt: skip
            ">",
            *(f"> {p['pmcid']}: {p['why']}" for p in printed),
        ]
    return [*lines, ""]


def _origin_not_proved(o: dict) -> str:
    h = o["after_second_reading"]
    where = h["environment"]["rows"]
    ambient = ("air_dust", "freshwater", "seawater", "soil", "sediment", "biota")
    syn = h["synthetic"]
    return (
        "- **How environmental micro- and nanoplastics behave.** The particles measured are "
        f"synthetic ({_pct(syn['rows'], o['rows'])} of rows, C11): bought beads and lab-made "
        f"fragments, {_int(syn['medium']['lab_liquid'])} of their {_int(syn['rows'])} rows "
        "measured in a laboratory liquid (deionised water, salt solution, buffer, culture "
        f"medium or biofluid) and {_int(syn['medium']['environmental_water'])} in an "
        "environmental water. "
        "Rows from a real environment: "
        f"{h['environmental_rows']['rows']}, {where['wastewater']} of them wastewater effluent; "
        + ", ".join(f"{ENV_LABEL[e]} {where[e]}" for e in ambient)
        + ". The numbers describe how manufactured particles are reported, not how plastic in "
        "air, water or soil behaves."
    )


# --- 7 -----------------------------------------------------------------------------------------


def section_7(f: Facts) -> list[str]:
    h = f.harmonised
    complete = h[h["conditions_complete"]].head(5)
    one_short = h[~h["conditions_complete"] & (h[list(FLAGS)].sum(axis=1) == 4)].head(5)
    ten = ", ".join(f"`{r}`" for r in [*complete["row_id"], *one_short["row_id"]])
    letters = [_col(HARM, c) for c in (*FLAGS, "conditions_complete")]
    papers = f.papers
    big = papers.sort_values(["n_rows", "pmcid"], ascending=[False, True]).iloc[0]
    small = papers[papers["n_rows"] == 3].iloc[0]
    ka_rows = ", ".join(f"`{r['row_id']}`" for r in _ka_examples(h))
    pair = next((p for p in f.pairs if p.pair_id == "P2"), f.pairs[0])
    withheld = int(f.audit["quote_withheld"].sum())
    example = f.audit.loc[f.audit["quote_withheld"], "pmcid"]
    example = example.iloc[0] if len(example) else f.audit["pmcid"].iloc[0]
    print_cmd = (
        'uv run python -c "import sys; from mnp import config; from mnp.corpus import jats, '
        "lines; p=sys.argv[1]; print(lines.render(lines.build_lines(jats.parse("
        f"(config.EPMC_XML_DIR/f'{{p}}.xml').read_bytes()))))\" {example} | less"
    )
    return [
        "## 7. How to review it yourself, step by step",
        "",
        "About an hour in a spreadsheet, most of it on step 6; the minutes per step are rough "
        "guesses. Open the CSVs from `out/review/` and import `out/tables/d1_zeta_table.csv` "
        "as a sheet named `d1`.",
        "",
        "1. **Recompute `conditions_complete` for ten rows** (5 min). In "
        f"`{HARM}` the five flags are columns {', '.join(letters[:5])} and "
        f"`conditions_complete` is column {letters[5]}. Next to these rows add "
        f"`=AND({letters[0]}2,{letters[1]}2,{letters[2]}2,{letters[3]}2,{letters[4]}2)` "
        f"(row number adjusted) and compare: {ten}. The first five are fully conditioned; the "
        "other five miss exactly one condition. Then recompute one flag from its fields with "
        "the rule in §4, looking the fields up in `d1`.",
        f"2. **Recompute two per-paper shares** (5 min). In `{PER_PAPER}` find "
        f"`{big['pmcid']}` ({_int(big['n_rows'])} rows) and `{small['pmcid']}` "
        f"({_int(small['n_rows'])} rows). Filter `d1` on `pmcid`, count the rows and the rows "
        "reporting temperature yourself, and check `temperature_reported_share`. Then "
        "`=AVERAGE` the whole share column and compare with §5.1.",
        f"3. **Recompute ICC for `conditions_complete`** (15 min). Follow the block in §5.2 on "
        f"`{ICC}`; every intermediate you should reach is printed there.",
        f"4. **Recompute κa and f for three rows** (10 min): {ka_rows}. Use the formulas and "
        f"worked numbers in §5.4 and compare with `kappa_a` and `henry_f` in `{HARM}`. Then "
        "take one of them through its case in §5.5 by hand.",
        f"5. **Evaluate one pair by hand** (10 min). Take pair {pair.pair_id} in `{PAIRS}`. "
        "For each line, read the two rows' fields in `d1`, apply the rule and tolerance from "
        "the §5.6 rule table, and decide blocks or passes before you look at `outcome`. Grade "
        "the pair with the three-line rule in §5.6 and compare with `verdict`.",
        f"6. **Audit twenty rows against the papers** (the rest of the hour, or more). "
        f"`{AUDIT}` holds {_int(len(f.audit))} rows, two drawn at random for each condition "
        "reported and two for each condition unreported (ten strata), from the release in its "
        f"row order with `random.Random({AUDIT_SEED})`, so a rebuild draws the same rows. For "
        "each row:",
        "   - open the paper at `europepmc_url`, or the vendored XML at `xml_path`;",
        "   - find the cited lines. For a row whose quote ships, `evidence_line_text` holds the "
        "text of each cited line (joined with ` || `) and `evidence_quote` the quote: search a "
        f"distinctive phrase of it in the paper. For the {_int(withheld)} rows whose quote is "
        "withheld, only `evidence_lines` (`PMCID:Lnn`, line numbers of the line-addressed "
        "document) and `evidence_line_ids` are given: print that paper's numbered lines with "
        "the command below (run `unset VIRTUAL_ENV` first if a virtualenv is active), or "
        "restore the quotes locally with `uv run python -m mnp.report rehydrate`, which writes "
        "to `data/interim/rehydrated/` and never into `out/`;",
        "   - compare `value`, `value_text` and `unit` with what the paper prints for this "
        "measurement, and each condition with what the paper states for **this** measurement, "
        'by the rules in §4 (an incubation temperature does not count; "PBS" alone is not an '
        "ionic strength);",
        "   - write `yes`, `no` or `unsure` in `value_ok`, `medium_ok`, `ionic_strength_ok`, "
        "`pH_ok`, `temperature_ok` and `instrument_ok`, and anything else in `note`. For a "
        "condition the row calls unreported, `yes` means the paper indeed does not state it "
        "for this measurement.",
        "",
        "```",
        print_cmd,
        "```",
        "",
        "This audit is small and not blind: you see the extracted values while you judge. The "
        "blind worksheet for the κ audit is a different file, "
        "`data/interim/annotation/audit_10.csv`.",
        "",
    ]


# --- 8 -----------------------------------------------------------------------------------------


def section_8(f: Facts) -> list[str]:
    t, papers, x = f.table, f.papers, f.extra
    b = f.grid.get("B")
    k = len(papers)
    zero = _with_flag(t, ZERO_IONIC_STRENGTH)
    stepped = _with_flag(t, STEP_TEMPERATURE)
    other = _with_flag(t, OTHER_STEP_TEMPERATURE)
    kappa = f.harmonised["kappa_a"]
    single = next(
        (r for r in f.key
         if r["verdict"] == "not_comparable" and r["blockers"] == "conversion_regime_mismatch"),
        None,
    )  # fmt: skip
    axis = ", ".join(f"`{c}`" for c in sorted(comp._AXIS_CODES))
    dirty = [cell for cell, run in f.grid.items() if run and run.code_dirty]
    handoff: list[str] = []
    if b:
        handoff.append(
            f"**Cell B, full run** (item 1, then 358/400). The committed run directory "
            f"`{RUN_IDS['B']}` now holds {_int(b.answered)} answers of {_int(b.asked)} asked, "
            f"{_int(b.refused)} of them a recorded refusal (commit `e1b4624`). Closed."
        )
    handoff += [
        "**The LICENSE author** (item 2). `release.AUTHOR` is "
        + (
            "still unset, so `LICENSE` carries a placeholder. Open."
            if not x.get("author")
            else f"set to {x['author']}. Closed."
        ),  # fmt: skip
        "**`uv.lock`** (item 3). "
        + (
            "Still listed in `.gitignore`, so a fresh clone can resolve a newer pandas and "
            "change the `pandas_version` string inside `dataset.parquet`. Open."
            if x.get("lock_ignored")
            else "No longer ignored. Closed."
        ),  # fmt: skip
        "**The repository redistributes non-CC-BY text** (item 4): `xml.tar.gz` holds 244 "
        "full texts that are not CC BY or CC0 (the handoff's count), `d1_zeta_table.csv` and "
        f"`extractions.jsonl` hold the {_int(int(f.release['quote_withheld'].sum()))} "
        "withheld-class quotes, and demo case 12 quotes an NC-ND paper. It matters only if the "
        "repository is or becomes public.",
        '**EHP "public domain unless otherwise noted"** (item 5): 4 papers withheld as '
        "uncertain; they could ship.",
        "**The row-citation bias** (item 6): a `row:X` citation expands to every evidence line "
        "of the row. Fix it before comparing cell D and cell B on citation precision.",
        "**`runs.code_commit` counts untracked files as dirty** (item 7). "
        + (
            f"The grid runs of cell {' and '.join(dirty)} read here record `code_dirty: true`."
            if dirty
            else "The grid runs read here record a clean tree."
        ),
        "**Still open from before** (item 8): the κ audit, rotating the credential the handoff "
        "names, card 2, and vendoring `tiktoken`.",
    ]
    found = [
        "**The axis codes in `docs/FINDINGS_comparability.md` §2 (R5) are wrong.** It says the "
        'four tolerance codes, `conversion_regime_mismatch` among them, "are the '
        f"`_AXIS_CODES`\". The code's `_AXIS_CODES` are {axis}: the conversion-regime code is "
        "not one, and the two medium codes are."
        + (
            f" Pair `{single['row_id_a']}` × `{single['row_id_b']}` is blocked by "
            "`conversion_regime_mismatch` alone and is graded `not_comparable` (worked pair P3)."
            if single
            else ""
        )
        + " The §1 verdict table of the same file agrees with the code; the §2 sentence does "
        "not.",
        *(
            [
                "**`comparability.debye_length_nm`'s docstring is out of date.** It says the "
                'Debye length is "used only to place a row in a regime, never to correct a '
                'reported value". `mnp.demo.harmonise` now corrects values with it (Z1 and M1 '
                "in §5.5)."
            ]
            if "never to correct a reported value" in (comp.debye_length_nm.__doc__ or "")
            else []
        ),
        "**The Czech question list asks about the 1:1 Debye length under an old premise** "
        "(Part 2, E3): that it is used only to place a row in a regime, not to correct a value. "
        "`mnp.demo.harmonise` now corrects values with it (Z1 and M1 in §5.5), so reword E3 "
        "before it is asked.",
        "**A superseded denominator survives.** `docs/FINDINGS_comparability.md` R2 and R7, and "
        "`comparability.instrument_key`'s docstring, still say 5.6 % of papers name a "
        "conversion model (94.4 % do not). `docs/FINDINGS.md` §E2b corrected that to "
        f"{f.scan.zeta_named} / {f.scan.zeta_papers} papers with a zeta row "
        f"({_pct(f.scan.zeta_not_named, f.scan.zeta_papers)} not naming one).",
        '**"Fully conditioned per paper" means three things** (§5.1): '
        f"{_pp(_estimate(f, 'conditions_complete').per_paper)} as a mean of shares, "
        f"{_int(_any_complete(f))} of {_int(k)} papers with a fully conditioned row, and "
        f"{_int(_every_somewhere(f))} papers reporting every condition on some row. "
        "`d1_stats.json` stores the last one as `complete_fraction` "
        f"({f.stats.get('complete_fraction', 0):.4f}), a name that reads like the second. One "
        "name per reading would stop the three being swapped.",
        f'**"{_pp(_estimate(f, "ionic_strength_reported").per_paper)} of papers report ionic '
        'strength"** (the Czech question list, Part 1, prints 8,7 %) is the mean of per-paper '
        "shares. The share of papers that report it on at least one row is "
        f"{_pct(int((papers['ionic_strength_reported_rows'] > 0).sum()), k)}.",
    ]
    if len(zero):
        found.append(
            f"**0 mM, decided.** {_int(len(zero))} rows state an ionic strength of 0 mM "
            f'({", ".join(sorted(zero["pmcid"].unique()))}; "{_cell(zero["medium_text"].iloc[0])}'
            '" and similar). The code used to give them an infinite Debye length, κa = 0 and '
            'f = 1.0, the least defensible κa in the table, since "no added electrolyte" is not '
            "a true zero. Ratified 2026-09-28: 0 mM is not a reported ionic strength. The rows "
            f"stay, with the value cleared and the flag `{ZERO_IONIC_STRENGTH}` (§4.2); κa is now "
            f"known on {_int(int(kappa.notna().sum()))} rows, {_int(int((kappa == 0).sum()))} of "
            f"them 0. The same decision removed the {_int(len(stepped))} step-flagged "
            f"temperatures, and R2b (2026-09-29) {_int(len(other))} storage and incubation "
            "temperatures read from outside the row's quote (§4.4). Closed."
        )
    found.append(
        "**The 81 624 counterfactual is quoted, never recomputed.** No committed code produces "
        "it or the leave-one-rule-out table (`docs/FINDINGS_comparability.md` §4c, §4b), and "
        "`src/mnp/demo/render.py` prints 81 624 as a literal. The all-pairs blocker frequencies "
        "(§4a) could be recomputed with `comparability.blocker_distribution`, but no runner "
        "does."
    )
    if x.get("method_says_no_licence"):
        found.append(
            '**`out/demo/METHOD.md` is stale on the licence.** Its "Limits" section still says '
            '"This dataset has no licence yet", while the release is CC BY 4.0 '
            "(`out/release/DATASET_CARD.md`). The sentence is typed into "
            "`src/mnp/demo/render.py`."
        )
    if "Martin made" in Path(harmonise.__file__).read_text(encoding="utf-8"):
        found.append(
            "**An attribution this guide could not confirm.** `src/mnp/demo/harmonise.py` calls "
            'the both-limits rule (§5.5) "a correction Martin made to the design doc on '
            '2026-09-28". The design doc says only "revised 2026-09-28, after agent B\'s first '
            'pass" and names nobody. If Martin did not make it, the docstring should say who did.'
        )
    found += [
        '**Stale counts in two front documents.** `README.md` ("D1 result on the whole '
        'corpus") still reports 498 papers and 1910 rows, a reading from before the ratified '
        f"rules; the table has {_int(t['pmcid'].nunique())} papers and {_int(len(t))} rows. "
        f"`ideas.md` §12 says the table has 39 columns; it has {len(t.columns)}.",
        "**`docs/FINDINGS.md` §E2e's temperature interval and ratio range** (±8.4 pp; 2.1× to "
        "4.1×) came from an implementation that was never committed; the rebuild in §5.3 is the "
        "one to quote.",
    ]
    if x.get("methods_fix"):
        found.append(_methods_fix(x["methods_fix"]))
    if x.get("origin"):
        found += _origin_open(x["origin"])
    lines = ["## 8. Open issues and decisions", "", "### From `HANDOFF_2026-09-28.md` §4", ""]
    lines += [f"{i}. {item}" for i, item in enumerate(handoff, 1)]
    lines += ["", "### Found while building this guide", ""]
    lines += [f"{i}. {item}" for i, item in enumerate(found, len(handoff) + 1)]
    lines += [
        "",
        "### The corpus",
        "",
        "Not enlarged for now (Martin, 2026-09-30). What the corpus leaves out, why that may "
        "raise the synthetic share, and the cheapest test when it is revisited: "
        f"`{scope.NOTES}`.",
        "",
    ]
    return lines


def _methods_fix(m: dict) -> str:
    """The Methods defect the origin reading found, closed: before the fix against now."""
    b, n = m["before"], m["now"]

    def share(side: dict, key: str) -> float | None:
        k = side["reported"][f"{key}_reported"]
        return round(100 * k / side["rows"], 1) if side["rows"] else None

    moved = [(label, share(b, key), share(n, key)) for key, label in ORIGIN_CONDITIONS]
    shares = "; ".join(
        f"{label} {'—' if then is None else f'{then:.1f} %'} → "
        f"{'—' if now is None else f'{now:.1f} %'}"
        for label, then, now in moved
    )
    known = [(label, then, now) for label, then, now in moved if None not in (then, now)]
    fell = [label for label, then, now in known if now < then]
    rose = [label for label, then, now in known if now > then]
    parts = [f"fell for {_and(fell)}"] * bool(fell) + [f"rose for {_and(rose)}"] * bool(rose)
    direction = f"It {', and '.join(parts)}. " if parts else ""
    bt, nt = b["table"], n["table"]
    return (
        f"**The extraction did not get the Methods of {_int(b['papers'])} of "
        f"{_int(bt['papers'])} papers. Found, fixed, re-extracted.** The origin reading found it "
        "(`d4be112`): `jats._find_methods` took a `supplementary-materials` section for the "
        "Methods, so the section titles were never tried. The parser was fixed in `9b17a6c` "
        "and those papers were re-extracted in `5012fdf` (`docs/DECISIONS.md` CP-07). Share of "
        f"their rows reporting each condition, before the fix → now: {shares} "
        f"({_int(b['rows'])} rows then, {_int(n['rows'])} from {_int(n['papers'])} papers now). "
        f"{direction}The re-extraction also read them under the current brief, and readings "
        "under it differ systematically from the old ones (`docs/DECISIONS.md` EX-09, EX-10), "
        "so every other paper with rows was re-read under it too (`92db4fb`). The whole table: "
        f"{_int(bt['rows'])} rows from {_int(bt['papers'])} papers before the fix, "
        f"{_int(nt['rows'])} from {_int(nt['papers'])} now; fully conditioned rows "
        f"{_int(bt['complete'])} → {_int(nt['complete'])}. Before is what "
        "`tool/methods_fix_impact.py` measured on the table the fix was made against "
        "(`data/interim/methods_fix_impact.json`); now is this table. Closed."
    )


def _origin_open(o: dict) -> list[str]:
    """What checking the particles' origin found that is not about origin, and is still open."""
    out = []
    own = o.get("not_own_measurement") or []
    if own:
        by_why: dict[str, list[str]] = {}
        for r in own:
            by_why.setdefault(r["why"], []).append(f"`{r['row_id']}`")
        out.append(
            f"**{len(own)} rows are not the authors' own measurement of a plastic particle**, "
            "found by a Claude agent's second reading of origin: "
            + "; ".join(f"{', '.join(ids)} ({why})" for why, ids in by_why.items())
            + ". They are rows of the table and counted everywhere, C11 included. Open: drop "
            "them or flag them (`sample_origin_stats.json` → `not_own_measurement`)."
        )
    return out


def render(f: Facts) -> str:
    lines = [
        "# Reviewing the MNP dataset by hand",
        "",
        *scope.block(f.table, f.stats, f.extra.get("origin")),
        "",
        f"A guide to every detail of `MNP-KB v0`: {_int(len(f.table))} surface-charge "
        f"measurements from {_int(f.table['pmcid'].nunique())} papers, with the conditions they "
        "were measured under and an explicit record of every condition a paper did not "
        "report. What it proves, what it does not, and how to check each number yourself.",
        "",
        "Contents: 1 how to use this guide · 2 where the data comes from · 3 every column · "
        "4 the five parameters · 5 every formula · 6 what it proves and does not · 7 a "
        "one-hour review · 8 open issues.",
        "",
        *section_1(f),
        *section_2(f),
        *section_3(f),
        *section_4(f),
        *section_5(f),
        *section_6(f),
        *section_7(f),
        *section_8(f),
    ]
    return "\n".join(lines).rstrip("\n") + "\n"
