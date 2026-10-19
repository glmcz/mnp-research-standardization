"""Independent + comparable pairs at 50 km / 365 d and 100 km / none, with and without the
'Unpublished' Oceaneye dataset. Usage: python -I comparable_detail.py <csv> <pairs.csv.gz>"""

import sys

import numpy as np
import pandas as pd

df = pd.read_csv(sys.argv[1], encoding="utf-8-sig", dtype=str, keep_default_na=False)
P = pd.read_csv(sys.argv[2])
grp = df["Organization"].str.split(",").str[0].str.strip().str.lower()
grp = grp.replace({"atlantic technological university": "galway-mayo institute of technology"})
P["indep"] = (grp.to_numpy()[P["i"]] != grp.to_numpy()[P["j"]]) & ~(
    (P["days"] == 0) & (P["km"] < 2)
)
P["comparable"] = P["same_method"] & P["same_mesh"] & P["both_nonzero"]
unpub = df.loc[df["Short Reference"] == "Unpublished", "DOI"].unique()
P["has_unpub"] = P["study_a"].isin(unpub) | P["study_b"].isin(unpub)
P["has_reisser_eriksen"] = P["study_pair"].str.contains("pone.0080466") & P[
    "study_pair"
].str.contains("pone.0111913")
region = df["Region"].replace("", "<none>") + " / " + df["Ocean"].replace("", "<none>")
for label, m in (
    ("50km/365d", (P["km"] <= 50) & (P["days"] <= 365)),
    ("100km/none", P["km"] <= 100),
):
    C = P[m & P["indep"] & P["comparable"]]
    print(label, "comparable independent pairs", len(C), "study pairs", C["study_pair"].nunique())
    D = C[~C["has_unpub"] & ~C["has_reisser_eriksen"]]
    print(
        "  excluding Unpublished and Reisser-Eriksen:",
        len(D),
        "study pairs",
        D["study_pair"].nunique(),
        "records",
        len(set(D["i"]) | set(D["j"])),
    )
    print(
        "  methods:",
        C["same_method"].sum(),
        dict(pd.Series(df.loc[C["i"], "Sampling Method"]).value_counts()),
    )
    print("  region of record a:", dict(region.loc[C["i"]].value_counts().head(6)))
    print(
        "  log10 ratio quantiles (all comparable):",
        C.assign(r=np.log10(np.maximum(C.val_a, C.val_b) / np.minimum(C.val_a, C.val_b)))["r"]
        .quantile([0.25, 0.5, 0.75, 0.9])
        .round(2)
        .to_dict(),
    )
print(
    "unpublished DOIs:",
    list(unpub),
    df[df["DOI"].isin(unpub)].groupby("DOI")["Organization"].first().to_dict(),
)
