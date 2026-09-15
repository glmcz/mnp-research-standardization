"""D1: how often is a zeta potential reported without its conditions?

Headline numbers count papers, not rows, and only papers with at least one
row whose evidence quote was found verbatim in the article. Two extra
denominators are reported alongside: all open-access records the query
returned (papers where nothing was extracted count as "not missing", so this
is conservative) and all hits including paywalled ones (a lower bound).
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import pandas as pd

from mnp.extract.evaluate import wilson_ci

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

CONDITIONS = (
    ("medium", "medium_reported", "Dispersion medium"),
    ("ionic_strength", "ionic_strength_reported", "Ionic strength"),
    ("pH", "pH_reported", "pH"),
    ("temperature", "temperature_reported", "Temperature"),
    ("instrument", "instrument_reported", "Instrument"),
)
YEAR_BANDS = (("<=2018", -1, 2018), ("2019-2022", 2019, 2022), ("2023-2026", 2023, 2100))


def _band(year) -> str:
    if year is None or pd.isna(year):
        return "unknown"
    for name, lo, hi in YEAR_BANDS:
        if lo <= int(year) <= hi:
            return name
    return "unknown"


def prepare_gold(gold: pd.DataFrame) -> pd.DataFrame:
    """Hand-annotated gold rows → the columns paper_stats expects.

    Gold rows are annotated from the article itself, so every one of them is evidence
    by definition; `evidence_verified` exists only to filter LLM output.
    """
    from mnp.extract.evaluate import _measurement_rows, derive_booleans

    rows = derive_booleans(_measurement_rows(gold)).reset_index(drop=True)
    rows["evidence_verified"] = True
    return rows


def text_availability(articles: pd.DataFrame) -> dict:
    """How many fetched papers actually carry text an extractor could read.

    Eleven of the 858 fetched XMLs have an empty body: conference-abstract volumes and
    "this content is available as a PDF" stubs. In the record an empty extraction of one of
    those is indistinguishable from a paper that was read and genuinely reported nothing, so
    the two are counted apart. Both slice workers who hit one raised it unprompted.
    """
    text = articles["extraction_text"].fillna("").astype(str).str.strip()
    empty = articles.loc[text.eq(""), "pmcid"].tolist()
    return {
        "fetched": int(len(articles)),
        "with_retrievable_text": int(len(articles) - len(empty)),
        "no_retrievable_text": len(empty),
        "pmcids_without_text": sorted(empty),
    }


def paper_stats(
    table: pd.DataFrame, n_oa_records: int | None = None, n_all_hits: int | None = None
) -> dict:
    verified = table[table["evidence_verified"].astype(bool)] if len(table) else table
    unverified_only = set(table["pmcid"]) - set(verified["pmcid"]) if len(table) else set()
    per_paper = (
        verified.groupby("pmcid")[[col for _, col, _ in CONDITIONS]].any()
        if len(verified)
        else pd.DataFrame(columns=[col for _, col, _ in CONDITIONS])
    )
    n = len(per_paper)
    missing = []
    any_missing = pd.Series(False, index=per_paper.index)
    for key, col, label in CONDITIONS:
        miss = ~per_paper[col].astype(bool) if n else pd.Series(dtype=bool)
        any_missing |= miss.reindex(per_paper.index, fill_value=False) if n else False
        k = int(miss.sum())
        missing.append(_missing_entry(key, label, k, n, n_oa_records, n_all_hits))
    k_any = int(any_missing.sum()) if n else 0
    missing.append(_missing_entry("any", "Any condition", k_any, n, n_oa_records, n_all_hits))
    numeric = (
        int(verified[verified["value"].notna()]["pmcid"].nunique())
        if len(verified) and "value" in verified.columns
        else n
    )
    return {
        "n_papers": n,
        "n_papers_with_a_printed_number": numeric,
        "n_papers_measured_but_no_number_printed": n - numeric,
        "n_rows_verified": int(len(verified)),
        "n_rows_total": int(len(table)),
        "n_papers_with_unverified_only": len(unverified_only),
        "denominators": {
            "papers_with_verified_zeta": n,
            "oa_records": n_oa_records,
            "all_hits": n_all_hits,
        },
        "missing": missing,
        "complete_fraction": (1 - k_any / n) if n else None,
    }


def _missing_entry(key, label, k, n, n_oa, n_all) -> dict:
    lo, hi = wilson_ci(k, n)
    return {
        "condition": key,
        "label": label,
        "k_missing": k,
        "n": n,
        "fraction": (k / n) if n else None,
        "wilson_lo": lo,
        "wilson_hi": hi,
        "fraction_of_oa_records": (k / n_oa) if n_oa else None,
        "fraction_of_all_hits_lower_bound": (k / n_all) if n_all else None,
    }


def oa_bias(records: pd.DataFrame) -> pd.DataFrame:
    """OA vs non-OA counts by year band and by journal (top 15 + other)."""
    df = records.copy()
    df["year_band"] = df["year"].map(_band)
    df["journal"] = df["journal"].fillna("unknown")
    top = df["journal"].value_counts().head(15).index
    df["journal_level"] = df["journal"].where(df["journal"].isin(top), "other")
    rows = []
    for dim, col in (("year_band", "year_band"), ("journal", "journal_level")):
        for level, grp in df.groupby(col):
            oa = int(grp["is_oa"].sum())
            non = int((~grp["is_oa"].astype(bool)).sum())
            rows.append(
                {
                    "dimension": dim,
                    "level": level,
                    "oa": oa,
                    "non_oa": non,
                    "oa_share": oa / (oa + non) if oa + non else None,
                }
            )
    return pd.DataFrame(rows, columns=["dimension", "level", "oa", "non_oa", "oa_share"])


DEFAULT_DENOMINATOR = "all open-access records the query returned"


def _markdown(stats: dict) -> str:
    n = stats["n_papers"]
    lines = [
        "# D1 — zeta potentials reported without their conditions",
        "",
        f"Papers with at least one verified zeta/mobility row: **{n}** "
        f"(rows: {stats['n_rows_verified']} verified of {stats['n_rows_total']}; "
        f"{stats['n_papers_with_unverified_only']} papers had only unverifiable rows "
        "and are excluded).",
        "",
        f"Of these, **{stats['n_papers_measured_but_no_number_printed']}** report a zeta "
        "measurement without printing a single number in the main text (range, figure or "
        "SI only).",
        "",
        "Denominators: (1) papers with a verified measurement, with 95% Wilson intervals; "
        f"(2) {stats.get('denominator_note') or DEFAULT_DENOMINATOR} — conservative, papers "
        "where nothing was extracted count as not missing; (3) all hits incl. paywalled — "
        "a lower bound.",
        "",
        "| Missing | k / n | fraction | 95% CI | of OA records | of all hits (≥) |",
        "|---|---|---|---|---|---|",
    ]
    if (avail := stats.get("text_availability")) and avail["no_retrievable_text"]:
        lines[6:6] = [
            f"Of {avail['fetched']} fetched XMLs, **{avail['no_retrievable_text']} carry no "
            "retrievable text at all** — conference-abstract volumes and PDF-only deposits. "
            "They are not papers that were read and found to report nothing, and are counted "
            "apart from those that were: " + ", ".join(avail["pmcids_without_text"][:12]) + ".",
            "",
        ]
    for m in stats["missing"]:
        frac = f"{100 * m['fraction']:.1f}%" if m["fraction"] is not None else "—"
        ci = (
            f"{100 * m['wilson_lo']:.0f}–{100 * m['wilson_hi']:.0f}%"
            if m["fraction"] is not None
            else "—"
        )
        oa = f"{100 * m['fraction_of_oa_records']:.1f}%" if m["fraction_of_oa_records"] else "—"
        al = (
            f"{100 * m['fraction_of_all_hits_lower_bound']:.1f}%"
            if m["fraction_of_all_hits_lower_bound"]
            else "—"
        )
        lines.append(
            f"| {m['label']} | {m['k_missing']} / {m['n']} | {frac} | {ci} | {oa} | {al} |"
        )
    lines += [
        "",
        "Rows whose evidence quote was not found verbatim in the article are excluded from "
        "every number above (see `flags` in d1_zeta_table.csv).",
    ]
    return "\n".join(lines) + "\n"


def figure(stats: dict, path: Path) -> Path:
    entries = [m for m in stats["missing"]]
    labels = [m["label"] for m in entries]
    fracs = [100 * (m["fraction"] or 0) for m in entries]
    lo = [100 * ((m["fraction"] or 0) - (m["wilson_lo"] or 0)) for m in entries]
    hi = [100 * ((m["wilson_hi"] or 0) - (m["fraction"] or 0)) for m in entries]
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.barh(labels, fracs, xerr=[lo, hi], color="#4c72b0", capsize=3)
    ax.set_xlim(0, 100)
    ax.set_xlabel("papers reporting a zeta potential without this condition (%)")
    ax.set_title(f"n = {stats['n_papers']} open-access papers, 95% Wilson intervals", fontsize=10)
    ax.invert_yaxis()
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def build(
    table: pd.DataFrame,
    records: pd.DataFrame | None,
    out_tables: Path,
    out_figures: Path,
    hit_counts: dict | None = None,
    prefix: str = "d1",
    denominator_note: str | None = None,
    articles: pd.DataFrame | None = None,
) -> list[Path]:
    out_tables, out_figures = Path(out_tables), Path(out_figures)
    out_tables.mkdir(parents=True, exist_ok=True)
    out_figures.mkdir(parents=True, exist_ok=True)
    n_oa = None
    if records is not None and len(records):
        n_oa = int(records["is_oa"].astype(bool).sum())
    if hit_counts and hit_counts.get("hits_oa"):
        n_oa = int(hit_counts["hits_oa"])
    n_all = int(hit_counts["hits_all"]) if hit_counts and hit_counts.get("hits_all") else None
    stats = paper_stats(table, n_oa_records=n_oa, n_all_hits=n_all)
    stats["denominator_note"] = denominator_note
    if articles is not None and len(articles):
        stats["text_availability"] = text_availability(articles)
    written = []
    p = out_tables / f"{prefix}_zeta_table.csv"
    table.to_csv(p, index=False)
    written.append(p)
    p = out_tables / f"{prefix}_stats.json"
    p.write_text(json.dumps(stats, indent=2))
    written.append(p)
    p = out_tables / f"{prefix}_stats.md"
    p.write_text(_markdown(stats))
    written.append(p)
    p = out_tables / f"{prefix}_oa_bias.csv"
    bias = (
        oa_bias(records)
        if records is not None and len(records)
        else pd.DataFrame(columns=["dimension", "level", "oa", "non_oa", "oa_share"])
    )
    bias.to_csv(p, index=False)
    written.append(p)
    written.append(figure(stats, out_figures / f"{prefix}_missing_conditions.png"))
    return written
