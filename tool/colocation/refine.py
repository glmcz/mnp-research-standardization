"""Split co-located pairs into same-group / same-tow overlaps vs independent cross-group pairs.

Group = Organization text before the first comma, lowercased; GMIT and its successor ATU
(both Galway) merged. Same-tow = same calendar day and < 2 km apart.

Usage: python -I refine.py <csv> <pairs_100km.csv.gz>
"""

import sys

import numpy as np
import pandas as pd

df = pd.read_csv(sys.argv[1], encoding="utf-8-sig", dtype=str, keep_default_na=False)
P = pd.read_csv(sys.argv[2])
grp = df["Organization"].str.split(",").str[0].str.strip().str.lower()
grp = grp.replace({"atlantic technological university": "galway-mayo institute of technology"})
ref = df.groupby("DOI")["Short Reference"].agg(lambda s: ";".join(sorted(set(s))))
P["same_group"] = grp.to_numpy()[P["i"]] == grp.to_numpy()[P["j"]]
P["same_tow"] = (P["days"] == 0) & (P["km"] < 2)
P["indep"] = ~P["same_group"] & ~P["same_tow"]
P["comparable"] = P["same_method"] & P["same_mesh"] & P["both_nonzero"]
P["log10_ratio"] = np.log10(np.maximum(P["val_a"], P["val_b"]) / np.minimum(P["val_a"], P["val_b"]))

print("same-tow pairs (same day, <2 km) by study pair, any radius:")
st = P[P["same_tow"]]
print(st.groupby("study_pair").agg(n=("i", "size"), same_group=("same_group", "first"),
                                   med_log10_ratio=("log10_ratio", "median"),
                                   share_equal=("exact_dup", "mean")).sort_values("n", ascending=False)
      .rename(index=lambda sp: " || ".join(ref[s] for s in sp.split(" || "))).round(3).to_string())

rows = []
for r in (10, 50, 100):
    for d in (365, None):
        m = P["km"] <= r
        if d is not None:
            m &= P["days"] <= d
        S = P[m]
        I = S[S["indep"]]
        C = I[I["comparable"]]
        rows.append({
            "radius_km": r, "max_days": d or "none", "all_pairs": len(S),
            "same_group": int(S["same_group"].sum()), "same_tow": int(S["same_tow"].sum()),
            "independent": len(I), "indep_study_pairs": I["study_pair"].nunique(),
            "indep_same_method": int(I["same_method"].sum()), "indep_same_mesh": int(I["same_mesh"].sum()),
            "indep_comparable": len(C), "comparable_study_pairs": C["study_pair"].nunique(),
            "comparable_records": len(set(C["i"]) | set(C["j"])),
            "comparable_med_log10_ratio": round(C["log10_ratio"].median(), 2) if len(C) else None,
        })
pd.set_option("display.width", 300)
print("\n", pd.DataFrame(rows).to_string(index=False))

for label, m in (("50 km / 365 d", (P["km"] <= 50) & (P["days"] <= 365)),
                 ("100 km / no date limit", P["km"] <= 100)):
    I = P[m & P["indep"]]
    t = I.groupby("study_pair").agg(
        pairs=("i", "size"), setting=("setting", "first"),
        same_method=("same_method", "mean"), same_mesh=("same_mesh", "mean"),
        comparable=("comparable", "sum"), med_km=("km", "median"), med_days=("days", "median"),
        med_log10_ratio=("log10_ratio", "median"))
    t.index = [" || ".join(ref[s] for s in sp.split(" || ")) for sp in t.index]
    print(f"\nIndependent study pairs, {label}: {len(t)}; with >=1 comparable record pair: {(t['comparable'] > 0).sum()}")
    print(t.sort_values("comparable", ascending=False).head(40).round(2).to_string())
