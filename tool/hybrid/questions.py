"""The question set: datasets first, papers second, each with a truth computed apart from ops.py.

A question's truth is computed here with plain pandas over the source files, not through the
operations the hybrid agent calls, so a bug in an operation cannot hide by also writing its own
answer key. The required verdict comes from a domain rule written next to each question (a change
across two sets of studies needs a caveat; the same tows under two studies are not independent).

Each question also names the packet a naive user would paste into a chat: what fits in a prompt.

    uv run --with openpyxl python tool/hybrid/questions.py   # writes queries/hybrid_questions.jsonl
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "tool" / "survey"))
sys.path.insert(0, str(ROOT / "tool" / "p2"))
import build as p2  # noqa: E402
import extension as ext  # noqa: E402

OUT = ROOT / "queries/hybrid_questions.jsonl"
TOWS = ROOT / "tool/colocation/reisser_eriksen/out_2026-10-12/tow_identity_R_E.csv"
REISSER, ERIKSEN = "10.1371/journal.pone.0080466", "10.1371/journal.pone.0111913"
LAW_2010, LAW_2014 = "10.1126/science.1192321", "10.1021/es4053076"


@dataclass(frozen=True)
class Q:
    qid: str
    family: str
    text: str
    ref_plan: dict
    truth: float | None
    tolerance: float  # relative, on the value; 0 means the value is not scored
    verdict: str  # allow | caveat | refuse
    caveat: str | None  # the reason a caveat or refusal must name
    rule: str  # why that verdict
    packet: str  # what a naive user pastes
    adversarial: bool = False
    meta: dict = field(default_factory=dict)


def _ncei_water() -> pd.DataFrame:
    d = pd.read_csv(p2.NCEI, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    d = d[d["Marine Setting"] == "Ocean water"].copy()
    d["year"] = pd.to_datetime(d["Sample Date"], format="%m/%d/%Y %I:%M:%S %p").dt.year
    d["value"] = pd.to_numeric(d["Microplastics Measurement"], errors="coerce")
    d["lat"] = pd.to_numeric(d["Latitude (degree)"])
    d["lon"] = pd.to_numeric(d["Longitude (degree)"])
    return d[d.value.notna()]


def _thirds_ratio(g: pd.DataFrame) -> float:
    years = sorted(g.year.unique())
    k = -(-len(years) // 3)
    return g[g.year.isin(years[-k:])].value.mean() / g[g.year.isin(years[:k])].value.mean()


def build() -> list[Q]:
    w = _ncei_water()
    period = (w.year // 5) * 5
    med = w.groupby(period).value.median()
    law10 = w[w.DOI.str.endswith(LAW_2010)]
    law14 = w[w.DOI.str.endswith(LAW_2014)]
    tows = pd.read_csv(TOWS)
    both = tows[(tows.value_R > 0) & (tows.value_E > 0)]
    weser, win = ext.weser()
    z = pd.read_csv(ROOT / "out/tables/p2_zeta_size.csv")
    amine = z[(z.surface == "amine") & (z.material_group == "PS")]
    nylon = z[z.material_group == "nylon"]
    d1 = pd.read_csv(ROOT / "out/tables/d1_zeta_table.csv", dtype=str, keep_default_na=False)
    is_papers = d1.groupby("pmcid").ionic_strength_reported.agg(lambda s: (s == "True").any())
    mpsed = json.loads(p2.MPSED.read_text(encoding="utf-8"))
    coloc = json.loads((ROOT / "out/tables/survey_colocated.json").read_text())
    rho_size = spearmanr(np.log10(z.size_nm), z.zeta_mV)[0]

    qs = [
        Q(
            "T1",
            "timeline",
            "In the NOAA NCEI marine microplastics database, by what factor did the median "
            "ocean-water concentration (pieces/m3) change from the 2000-2004 samples to the "
            "2020-2024 samples? Does that show microplastic in the ocean rose by that factor?",
            {"op": "period_change", "args": {"period_from": 2000, "period_to": 2020}},
            float(med[2020] / med[2000]),
            0.05,
            "caveat",
            "composition_shift",
            "no study sampled in both periods, so the ratio compares different studies, places "
            "and methods",
            "ncei_studies",
            adversarial=True,
        ),
        Q(
            "T2",
            "timeline",
            "How many different studies contributed NCEI ocean-water samples in 2015-2019, and how "
            "many in 2000-2004? Give the 2015-2019 number.",
            {"op": "study_count", "args": {"period": 2015}},
            float(w[period == 2015].DOI.nunique()),
            0.0001,
            "allow",
            None,
            "a count",
            "ncei_studies",
        ),
        Q(
            "T3",
            "timeline",
            "Law et al. 2010 (doi 10.1126/science.1192321) sampled the western North Atlantic and "
            "Caribbean with neuston nets from 1986 to 2008. In NCEI's copy of their tows, is there "
            "a monotonic trend? Give Spearman's rho of sampling year against concentration.",
            {"op": "series_trend", "args": {"study": LAW_2010, "statistic": "spearman"}},
            float(spearmanr(law10.year, law10.value)[0]),
            0.0,
            "allow",
            None,
            "one study, one method, one area: a within-series trend may be read",
            "ncei_studies",
            meta={"tolerance_abs": 0.05},
        ),
        Q(
            "T4",
            "timeline",
            "Law et al. 2014 (doi 10.1021/es4053076) sampled the eastern Pacific from 2001 to "
            "2012. "
            "By what factor is the mean concentration of its last third of sampled years higher "
            "than its first third? Does that show a rise in Pacific plastic?",
            {"op": "series_trend", "args": {"study": LAW_2014}},
            float(_thirds_ratio(law14)),
            0.05,
            "caveat",
            "sampling_area_shift",
            "the later cruises sampled a different part of the ocean (the tow centre moved about "
            "1 000 km), which the paper itself names as a confounder",
            "ncei_studies",
            adversarial=True,
        ),
        Q(
            "S1",
            "same_place",
            "Two independent studies sampled ocean water within 50 km and one year of each other "
            "with the same kind of net. Across all such pairs in NCEI, what is the median factor "
            "between their values?",
            {"op": "colocated_agreement", "args": {"km": 50, "days": 365, "same_method": True}},
            coloc["same_method_50km_365d"]["median_fold"],
            0.1,
            "allow",
            None,
            "same method, same place and year: a spread may be reported",
            "ncei_studies",
            meta={"truth_source": "out/tables/survey_colocated.json (validators)"},
        ),
        Q(
            "S2",
            "same_place",
            "In the Mediterranean Sea, independent same-method ocean-water samples within 50 km "
            "and "
            "one year: what is the median factor between their values?",
            {
                "op": "colocated_agreement",
                "args": {"km": 50, "days": 365, "same_method": True, "region": "Mediterranean Sea"},
            },
            coloc["mediterranean_same_method_50km_365d"]["median_fold"],
            0.1,
            "allow",
            None,
            "same method, same place and year",
            "ncei_studies",
            meta={"truth_source": "out/tables/survey_colocated.json (validators)"},
        ),
        Q(
            "S3",
            "same_place",
            "Within 50 km and a year, comparing ocean-water samples from any two independent "
            "studies regardless of sampling method: what is the median factor between values?",
            {"op": "colocated_agreement", "args": {"km": 50, "days": 365, "same_method": False}},
            coloc["any_method_50km_365d"]["median_fold"],
            0.1,
            "caveat",
            "method_mix",
            "different methods are compared",
            "ncei_studies",
            meta={"truth_source": "out/tables/survey_colocated.json (validators)"},
        ),
        Q(
            "D1",
            "held_twice",
            "Reisser et al. 2013 (doi 10.1371/journal.pone.0080466) and Eriksen et al. 2014 (doi "
            "10.1371/journal.pone.0111913) both have ocean-water records in NCEI around Australia "
            "and New Zealand. Are they two independent measurements that confirm each other? "
            "Give the median ratio Reisser/Eriksen for samples they share.",
            {"op": "duplicate_check", "args": {"study_a": REISSER, "study_b": ERIKSEN}},
            float((both.value_R / both.value_E).median()),
            0.1,
            "refuse",
            "held_twice",
            "the same 171 tows, held under two studies",
            "pair_records",
            adversarial=True,
        ),
        Q(
            "W1",
            "window",
            "In the Weser estuary (PANGAEA 937685 and 938143), particles of 11-500 um and of "
            "500-5000 um were counted at the same stations. By what median factor do the small "
            "ones outnumber the large ones?",
            {"op": "weser_window_ratio", "args": {}},
            float(weser.ratio.median()),
            0.05,
            "caveat",
            "different_window",
            "two windows: the factor depends on the size distribution, and the textbook slope "
            "(alpha 1.6) predicts about 12",
            "weser",
        ),
        Q(
            "W2",
            "window",
            "One survey counted microplastics with a 0.333 mm net, another with a 0.300 mm net, "
            "both up to 5 mm. Can their counts be compared directly? If a conversion is needed, "
            "give the upper end of the factor from the 0.333 mm count to the 0.300 mm window.",
            {"op": "compare_windows", "args": {"window_a": [333, 5000], "window_b": [300, 5000]}},
            max(ext.window_ratio(a, (300, 5000), (333, 5000)) for a in (1.3, 2.2)),
            0.05,
            "caveat",
            "different_window",
            "different lower limits: a factor, small here",
            "none",
        ),
        Q(
            "W3",
            "window",
            "A pump sample counted 11-500 um particles and a net sample 500-5000 um particles at "
            "the same river station. Can one count be converted into the other's window with the "
            "usual power-law slope?",
            {"op": "compare_windows", "args": {"window_a": [11, 500], "window_b": [500, 5000]}},
            None,
            0.0,
            "refuse",
            "different_window",
            "the windows do not overlap and no single slope in 1.3-2.2 gives a factor within x10",
            "none",
            adversarial=True,
        ),
        Q(
            "U1",
            "units",
            "An MP-SED sediment sample reports 120 microplastic/kg sediment dry wt.; an NCEI "
            "ocean-water sample at the same coast reports 0.5 pieces/m3. Which site is more "
            "polluted?",
            {
                "op": "compare_units",
                "args": {"unit_a": "microplastic/kg sediment dry wt.", "unit_b": "pieces/m3"},
            },
            None,
            0.0,
            "refuse",
            "different_unit",
            "a mass of sediment and a volume of water",
            "none",
            adversarial=True,
        ),
        Q(
            "C1",
            "completeness",
            "What share of MP-SED sediment records lack geographic coordinates? Answer as a "
            "fraction.",
            {"op": "completeness", "args": {"dataset": "mpsed", "field": "lat"}},
            float(not any(k.lower().startswith(("lat", "lon")) for k in mpsed[0])),
            0.01,
            "allow",
            None,
            "MP-SED has no coordinate field at all",
            "datasets_fields",
        ),
        Q(
            "C2",
            "completeness",
            "What share of the soil microplastic records (Wu et al. compilation) lack a sampling "
            "method? Answer as a fraction.",
            {"op": "completeness", "args": {"dataset": "soil", "field": "method"}},
            1.0,
            0.01,
            "allow",
            None,
            "the compilation has no method column",
            "datasets_fields",
        ),
        Q(
            "Z1",
            "zeta",
            "Amine-functionalised polystyrene nanoparticles: how many of the zeta potentials the "
            "literature reports for them are negative? Are these particles positively charged?",
            {
                "op": "zeta_sign_share",
                "args": {"surface": "amine", "sign": "negative", "polymer": "PS"},
            },
            float((amine.zeta_mV < 0).sum()),
            0.02,
            "caveat",
            "liquid_dependent",
            "the sign depends on the liquid the value was measured in",
            "zeta",
            adversarial=True,
        ),
        Q(
            "Z2",
            "zeta",
            "Across the literature, does the zeta potential of micro- and nanoplastics follow "
            "particle size? Give Spearman's rho of log size against zeta.",
            {"op": "zeta_size_correlation", "args": {}},
            float(rho_size),
            0.0,
            "allow",
            None,
            "a correlation over pooled values",
            "zeta",
            meta={"tolerance_abs": 0.05},
        ),
        Q(
            "Z3",
            "zeta",
            "Which polymer group has a positive median zeta potential in the literature, and what "
            "is that median (mV)? How robust is it?",
            {"op": "polymer_median", "args": {"polymer": "nylon"}},
            float(nylon.zeta_mV.median()),
            0.02,
            "caveat",
            "single_paper",
            f"{int(nylon.pmcid.value_counts().iat[0])} of {len(nylon)} values from one paper",
            "zeta",
        ),
        Q(
            "Z4",
            "zeta",
            "What share of papers reporting zeta potentials state the ionic strength for at least "
            "one value? Answer as a fraction.",
            {"op": "reported_share", "args": {"condition": "ionic_strength"}},
            float(is_papers.mean()),
            0.03,
            "allow",
            None,
            "a count",
            "d1_conditions",
        ),
        Q(
            "Z5",
            "zeta",
            "Two papers from one lab report -48.7 mV and -14.7 mV for 100 nm polystyrene in 0.3 mM "
            "NaCl at pH 7.4 and 25 C on the same instrument (rows PMC10260929-r1 and "
            "PMC13298883-r1). May they be compared, and how far apart are they (mV)?",
            {"op": "compare_rows", "args": {"row_a": "PMC10260929-r1", "row_b": "PMC13298883-r1"}},
            34.0,
            0.01,
            "allow",
            None,
            "every comparability rule passes (case 14)",
            "case14",
        ),
    ]
    return qs


def write() -> list[Q]:
    qs = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(asdict(q)) + "\n" for q in qs), encoding="utf-8")
    return qs


def read() -> list[Q]:
    return [Q(**json.loads(x)) for x in OUT.read_text(encoding="utf-8").splitlines() if x.strip()]


if __name__ == "__main__":
    for q in write():
        print(q.qid, q.verdict, q.caveat, q.truth)
    print(f"wrote {OUT}")
