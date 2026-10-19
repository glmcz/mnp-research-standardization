"""Pair counts per Marine Setting for each radius/date window. Usage: python -I by_setting.py <pairs.csv.gz>"""

import sys

import pandas as pd

P = pd.read_csv(sys.argv[1])
rows = []
for r in (10, 50, 100):
    for d in (365, None):
        m = P["km"] <= r
        if d is not None:
            m &= P["days"] <= d
        g = P[m].groupby("setting").agg(pairs=("i", "size"), study_pairs=("study_pair", "nunique"))
        for s, x in g.iterrows():
            rows.append({"radius": r, "days": d or "none", "setting": s, **x.to_dict()})
print(
    pd.DataFrame(rows)
    .pivot_table(index=["radius", "days"], columns="setting", values=["pairs", "study_pairs"])
    .fillna(0)
    .astype(int)
    .to_string()
)
