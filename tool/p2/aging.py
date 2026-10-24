"""P11: does aging move zeta? The same particle before and after, compared inside one paper.

The reviewer's idea B asked for zeta against size by polymer, "later also by aging". Across papers
a zeta value mostly carries its paper (P4), so this compares a particle with itself: an aged row
against the virgin rows of the same paper, polymer, liquid, pH, nominal size and additives. Both
sides share the lab, the instrument and the liquid, so the five conditions cancel even where they
are unreported. Rules and predictions: docs/PREREG_2026-10.md, P11 (committed before this ran).

    uv run --with openpyxl python tool/p2/aging.py
    # out/tables/p2_aging_pairs.csv, out/tables/p2_aging.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import binomtest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from build import material_group  # noqa: E402

D1 = ROOT / "out/tables/d1_zeta_table.csv"
PAIRS = ROOT / "out/tables/p2_aging_pairs.csv"
OUT = ROOT / "out/tables/p2_aging.json"
PREREG = {"commit": "af3c5ad", "citation_fixed": "00648be"}
SEED, RESAMPLES = 20261024, 2000
OXIDATIVE = ("photo", "chemical")

_VIRGIN = r"non-?uv-?aged|\bun-?aged|unweathered|non-?aged|virgin|pristine|\bno uv\b"
_AGED = (
    r"\baged\b|\bageing\b|\baging\b|weather|\buv|photo-?ag|photo-?oxid|irradiat|ozon|fenton|"
    r"h2o2|persulf|kmno4|\bkoh\b|hypochlor|oxidi[sz]ed"
)
_KINDS = (
    ("photo", r"\buv|photo|irradiat|xenon|sunlight|\blight\b"),
    ("chemical", r"ozon|\bo3\b|h2o2|fenton|persulf|kmno4|\bkoh\b|hypochlor|oxidi[sz]|chemical"),
    ("environmental", r"seawater|sea water|river|freshwater|lake|soil|biofilm|compost|"
                      r"natural|field|outdoor|incubat|landfill|sediment|wastewater"),
)  # fmt: skip
_STRIP = (
    _VIRGIN,
    r"\d+\s*(?:d|days?|h|hours?|weeks?|months?)\b(?:\s*\d+\s*nm)?(?:\s*\buv[abc]?(?:-[abc]\b)?)?",
    r"\buv[abc]?(?:-[abc]\b)?(?:[- ]?(?:aged|oxidi[sz]ed|irradiated|treated))?",
    r"photo-?aged|photo-?oxidi[sz]ed|\baged\b|weathered|irradiated|ozonated|oxidi[sz]ed|"
    r"artificially|\bageing\b|\baging\b",
)


def state(text: str) -> str:
    """Aged or virgin. A negated aging word ("non-UV-aged", "no UV", "unaged") is virgin."""
    t = text.lower()
    if re.search(_VIRGIN, t):
        return "virgin"
    return "aged" if re.search(_AGED, t) else "virgin"


def kind(text: str) -> str:
    """The treatment, first match wins: light before oxidant before an environmental medium."""
    t = text.lower()
    return next((k for k, pat in _KINDS if re.search(pat, t)), "unspecified")


def identity(name: str) -> str:
    """The particle's name with the aging and virgin words removed, and nothing else."""
    t = re.sub(r"\([^)]*\)", " ", name.lower())
    for pat in _STRIP:
        t = re.sub(pat, " ", t)
    return " ".join(re.sub(r"[^\w+.µμ–-]+", " ", t).replace(" - ", " ").split()).strip(" -")


def _additives(functionalisation: str) -> str:
    t = functionalisation.lower()
    found = set(re.findall(r"\+\s*([a-z0-9][\w-]*)", t))
    found |= {w for w in ("adsorbed", "coated", "corona") if w in t}
    return ";".join(sorted(found))


def _frame(rows: pd.DataFrame) -> pd.DataFrame:
    d = rows[rows.quantity.eq("zeta_potential")].copy()
    d["mV"] = pd.to_numeric(d.value, errors="coerce")
    d = d[d.mV.notna()]
    text = d.particle_name.fillna("") + " | " + d.functionalisation.fillna("")
    d["state"] = text.map(state)
    d["kind"] = text.map(kind).where(d.state.eq("aged"))
    d["polymer"] = d.material.fillna("").map(material_group)
    d["identity"] = d.particle_name.fillna("").map(identity)
    d["additives"] = d.functionalisation.fillna("").map(_additives)
    return d


# The liquid is its text and its ionic strength as written: one paper may write "Na +" for a
# whole salt series, and its levels are different liquids.
KEY = ["pmcid", "polymer", "identity", "medium_text", "ionic_strength_mM", "pH",
       "size_nominal_nm", "additives"]  # fmt: skip


def pairs(rows: pd.DataFrame) -> pd.DataFrame:
    """One row per aged measurement that has virgin rows of the same particle in its paper."""
    d = _frame(rows).fillna({k: "" for k in KEY})
    virgin = {k: g for k, g in d[d.state.eq("virgin")].groupby(KEY)}
    out = []
    for _, a in d[d.state.eq("aged")].iterrows():
        v = virgin.get(tuple(a[k] for k in KEY))
        if v is None:
            continue
        ref = float(v.mV.median())
        out.append(
            {
                "pmcid": a.pmcid,
                "aged_row": a.row_id,
                "virgin_row_ids": ";".join(v.row_id),
                "particle": a.particle_name,
                "treatment": a.functionalisation,
                "kind": a.kind,
                "polymer": a.polymer,
                "medium_text": a.medium_text,
                "pH": a.pH,
                "aged_mV": a.mV,
                "virgin_median_mV": ref,
                "virgin_rows": len(v),
                "delta_mV": a.mV - ref,
            }
        )
    return pd.DataFrame(out)


def _ci(rng, groups: list, stat) -> tuple[float, float]:
    draws = [stat([groups[i] for i in rng.integers(0, len(groups), len(groups))])
             for _ in range(RESAMPLES)]  # fmt: skip
    lo, hi = np.nanpercentile(draws, [2.5, 97.5])
    return float(lo), float(hi)


def paired(p: pd.DataFrame, kinds, rng) -> dict:
    per = p[p.kind.isin(kinds)].groupby("pmcid").delta_mV.median()
    if per.empty:
        return {"papers": 0}
    k = int((per < 0).sum())
    nonzero = int((per != 0).sum())
    lo, hi = _ci(rng, list(per), lambda xs: float(np.median(xs)))
    return {
        "papers": int(len(per)),
        "pairs": int(p.kind.isin(kinds).sum()),
        "papers_more_negative": k,
        "papers_less_negative": int((per > 0).sum()),
        "sign_test_p": float(binomtest(k, nonzero, 0.5).pvalue) if nonzero else None,
        "median_delta_mV": float(per.median()),
        "ci95": [lo, hi],
        "ci_width": hi - lo,
    }


def unpaired(d: pd.DataFrame, rng) -> dict:
    """The same question without pairing: aged rows against every virgin row of their polymers."""
    aged = d[d.state.eq("aged") & d.kind.isin(OXIDATIVE)]
    virgin = d[d.state.eq("virgin") & d.polymer.isin(set(aged.polymer))]
    both = pd.concat([aged.assign(side="aged"), virgin.assign(side="virgin")])
    papers = [g for _, g in both.groupby("pmcid")]

    def diff(gs: list) -> float:
        x = pd.concat(gs)
        a, v = x[x.side.eq("aged")].mV, x[x.side.eq("virgin")].mV
        return float(a.median() - v.median()) if len(a) and len(v) else np.nan

    lo, hi = _ci(rng, papers, diff)
    return {
        "aged_rows": int(len(aged)),
        "aged_papers": int(aged.pmcid.nunique()),
        "virgin_rows": int(len(virgin)),
        "virgin_papers": int(virgin.pmcid.nunique()),
        "median_difference_mV": diff(papers),
        "ci95": [lo, hi],
        "ci_width": hi - lo,
    }


def swapped(p: pd.DataFrame) -> list[str]:
    """Papers that print one particle's aged and virgin values the other way round elsewhere."""
    key = set(zip(p.pmcid, p.aged_mV, p.virgin_median_mV, strict=True))
    return sorted({pm for pm, a, v in key if (pm, v, a) in key and a != v})


def between_papers(d: pd.DataFrame, polymers: set[str]) -> dict:
    """How far one virgin plastic's zeta moves between papers: the scale aging is set against."""
    per = d[d.state.eq("virgin") & d.polymer.isin(polymers)].groupby(["polymer", "pmcid"]).mV
    med = per.median().groupby("polymer")
    q = med.quantile([0.25, 0.75]).unstack()
    return {
        k: {"papers": int(med.size()[k]), "iqr_mV": float(q.loc[k, 0.75] - q.loc[k, 0.25])}
        for k in sorted(polymers)
        if med.size().get(k, 0) >= 10
    }


def main() -> None:
    rows = pd.read_csv(D1, dtype=str, keep_default_na=False)
    d = _frame(rows)
    p = pairs(rows)
    p.to_csv(PAIRS, index=False)
    rng = np.random.default_rng(SEED)
    a = paired(p, OXIDATIVE, rng)
    b = unpaired(d, rng)
    share = a["papers_more_negative"] / a["papers"]
    a["verdict"] = "supported" if share >= 2 / 3 else "refuted" if share <= 1 / 2 else "partly"
    ratio = b["ci_width"] / a["ci_width"]
    b["verdict"] = "supported" if ratio >= 2 else "refuted" if ratio < 1 else "partly"
    aged = d[d.state.eq("aged")]
    out = {
        "prereg": PREREG,
        "seed": SEED,
        "resamples": RESAMPLES,
        "aged_rows": int(len(aged)),
        "aged_papers": int(aged.pmcid.nunique()),
        "aged_rows_by_kind": aged.kind.value_counts().to_dict(),
        "pairs": int(len(p)),
        "paired_papers": int(p.pmcid.nunique()),
        "P11a": a,
        "P11b": b | {"width_ratio_unpaired_over_paired": ratio},
        "descriptive": {
            k: paired(p, (k,), rng) for k in ("photo", "chemical", "environmental", "unspecified")
        },
        "chosen_after_the_results": {
            "papers_printing_swapped_values": swapped(p),
            "virgin_between_papers": between_papers(d, set(p.polymer)),
        },
    }
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
