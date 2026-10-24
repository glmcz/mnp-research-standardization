"""How far apart two numbers are, and what was held the same: every gap in one table.

Each row is one comparison: what the two measurements share, what differs, and how far apart
they are, read from a committed output of this project or, for the published interlaboratory
gaps, from a page whose quote code found (`scout_check.py`). Charge gaps are in mV, count gaps
are folds.

    uv run --with openpyxl python tool/gaps/ladder.py   # out/tables/gap_ladder.csv
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
T = ROOT / "out/tables"
OUT = T / "gap_ladder.csv"
SCOUT = T / "gap_scout_verified.csv"
CASE14 = ("PMC10260929-r1", "PMC13298883-r1")
NAMED_LIQUIDS = ("DI_water", "salt_solution", "buffer", "culture_medium")
#: What differs, then what stays the same: how a row reads on the slide.
LABELS = {
    "aged or not": "aged or not · same bead, paper, liquid",
    "the paper, the batch": "another batch · same label, five conditions",
    "the paper": "another paper · virgin polystyrene",
    "the liquid": "another liquid · amine polystyrene",
    "the conversion, in one database": "converted twice · the same tows",
    "the database, the year": "another database and year · same net, sea",
    "the study": "another study · same net, sea, year",
    "the method: a net or a pump": "net or pump · after converting the window",
    "the size window": "another size window · same river, day",
}
#: The published rows' labels, by a word of the scout's item name; the metric's short tag.
PUBLISHED_LABELS = {
    "SRM 1992": "another laboratory · a certified silica, the best case",
    "NanoValid": "another laboratory · one batch of silica",
    "Ciornii": "another laboratory · PET particles in one tablet",
    "Erasmus": "another participant · spiked water, one protocol",
    "pellet": "another laboratory · weighing the same pellets",
}
SHORT = {
    "median of papers": "median",
    "one pair": "one pair",
    "interquartile range": "IQR",
    "range of liquid medians": "range",
    "median": "median",
    "median residual": "after conversion",
    "certified expanded uncertainty, k = 2": "certified ±",
    "plus over minus one reproducibility SD, as a fold": "±1 SD",
    "plus over minus one CV, as a fold": "±1 SD",
}


def own() -> list[dict]:
    """The gaps this project measured, each from the output that holds it."""
    rows = []

    def add(family, held, differs, value, metric, source, high=None):
        rows.append({"family": family, "label": LABELS[differs], "held_same": held,
                     "differs": differs, "value": value,
                     "high": high, "metric": metric, "source": source,
                     "origin": "this project"})  # fmt: skip

    aging = json.loads((T / "p2_aging.json").read_text())
    add(
        "charge",
        "the bead, the paper, the liquid",
        "aged or not",
        abs(aging["P11a"]["median_delta_mV"]),
        "median of papers",
        "out/tables/p2_aging.json: P11a",
    )
    d1 = pd.read_csv(T / "d1_zeta_table.csv", dtype=str, keep_default_na=False)
    a, b = (d1[d1.row_id == r].iloc[0] for r in CASE14)
    gap = abs(float(a.value) - float(b.value))
    add(
        "charge",
        "the 100 nm label and all five conditions",
        "the paper, the batch",
        gap,
        "one pair",
        "out/tables/d1_zeta_table.csv: case 14",
    )
    ps = aging["chosen_after_the_results"]["virgin_between_papers"]["PS"]
    add(
        "charge",
        "virgin polystyrene",
        "the paper",
        ps["iqr_mV"],
        "interquartile range",
        "out/tables/p2_aging.json: virgin PS between papers",
    )
    z = pd.read_csv(T / "p2_zeta_size.csv")
    amine = z[(z.surface == "amine") & (z.material_group == "PS")]
    med = amine.groupby("medium_class").zeta_mV.agg(["size", "median"])
    med = med.loc[[m for m in NAMED_LIQUIDS if med.loc[m, "size"] >= 10], "median"]
    add(
        "charge",
        "amine polystyrene",
        "the liquid",
        med.max() - med.min(),
        "range of liquid medians",
        "out/tables/p2_zeta_size.csv: amine PS by liquid",
    )

    tows = pd.read_csv(ROOT / "tool/colocation/reisser_eriksen/out_2026-10-12/tow_identity_R_E.csv")
    both = tows[(tows.value_R > 0) & (tows.value_E > 0)]
    manta = (both.value_R / both.value_E)[both["Sampling Method"] == "Manta net"].median()
    add(
        "count",
        "the same tows",
        "the conversion, in one database",
        manta,
        "median",
        "tool/colocation/reisser_eriksen: Manta tows",
    )
    co = json.loads((T / "survey_colocated.json").read_text())
    groups = {(g["datasets"], g["decision"]): g
              for g in co["across_datasets_100km_any_year"]["by_dataset_pair"]}  # fmt: skip
    nets = groups[("emodnet vs ncei", "caveat")]
    add(
        "count",
        "the net's window, the sea",
        "the database, the year",
        nets["median_fold"],
        "median",
        "out/tables/survey_colocated.json: EMODnet vs NCEI",
        high=nets["p90_fold"],
    )
    same = co["same_method_50km_365d"]
    add(
        "count",
        "the net, the sea, the year",
        "the study",
        same["median_fold"],
        "median",
        "out/tables/survey_colocated.json: same method",
        high=same["p90_fold"],
    )
    pump = groups[("ncei vs pangaea_990052", "caveat")]
    add(
        "count",
        "the sea, after converting the window",
        "the method: a net or a pump",
        pump["median_residual_fold"],
        "median residual",
        "out/tables/survey_colocated.json: NCEI vs PANGAEA 990052",
    )
    w = pd.read_csv(T / "p2_weser_pairs.csv")
    w = w[w.large > 0]
    add("count", "the river, the station, the day", "the size window",
        float((w.small / w.large).median()), "median", "out/tables/p2_weser_pairs.csv")  # fmt: skip
    return rows


def published() -> list[dict]:
    """Interlaboratory gaps the gap scout found, kept only where code found the quote."""
    if not SCOUT.is_file():
        return []
    s = pd.read_csv(SCOUT)
    s = s[s.kept]
    rows = []
    for r in s.itertuples():
        label = next(v for k, v in PUBLISHED_LABELS.items() if k in r.name)
        metric = "range of laboratory means" if r.metric.startswith("range of") else r.metric
        rows.append(
            {"family": "charge" if r.family == "A" else "count", "label": label,
             "held_same": r.material, "differs": "the laboratory", "value": r.value,
             "high": None if pd.isna(r.high) or r.high == r.value else r.high,
             "metric": metric, "source": r.url, "origin": "published"}
        )  # fmt: skip
    return rows


def main() -> None:
    t = pd.DataFrame(own() + published())
    t["tag"] = t.metric.map({**SHORT, "range of laboratory means": "range of labs"})
    t.to_csv(OUT, index=False)
    print(t[["family", "held_same", "differs", "value", "metric", "origin"]].to_string())


if __name__ == "__main__":
    main()
