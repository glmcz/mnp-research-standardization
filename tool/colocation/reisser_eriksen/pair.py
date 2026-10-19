"""Pair Reisser 2013 rows with Eriksen 2014 rows: same calendar date, nearest position.

Usage: python -I pair.py <rows_R_E.csv> <out_dir>
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

EARTH_KM = 6371.0088


def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * EARTH_KM * np.arcsin(np.sqrt(a))


rows, out = Path(sys.argv[1]), Path(sys.argv[2])
d = pd.read_csv(rows, dtype={"Unique ID": str})
d["date"] = pd.to_datetime(d["date"]).dt.normalize()
R = d[d["tag"] == "R"].reset_index(drop=True)
E = d[d["tag"] == "E"].reset_index(drop=True)
# Australian-region Eriksen rows: bounding box of Reisser +/- 5 deg
box = E["lat"].between(R["lat"].min() - 5, R["lat"].max() + 5) & E["lon"].between(
    R["lon"].min() - 5, R["lon"].max() + 5
)
Eau = E[box].reset_index(drop=True)
print(f"Reisser rows {len(R)}; Eriksen rows {len(E)}; Eriksen in Reisser box(+/-5 deg) {len(Eau)}")
print(f"Eriksen-in-box years {Eau['date'].dt.year.value_counts().sort_index().to_dict()}")
print(f"Eriksen-in-box keywords {Eau['Keywords'].value_counts().to_dict()}")
print(f"Eriksen-in-box date span {Eau['date'].min().date()} .. {Eau['date'].max().date()}")

# all same-date candidate pairs with distance
cand = R.reset_index().merge(Eau.reset_index(), on="date", suffixes=("_r", "_e"))
cand["km"] = haversine(cand["lat_r"], cand["lon_r"], cand["lat_e"], cand["lon_e"])
print(f"\nsame-date R x E candidate pairs: {len(cand)}; within 2 km: {(cand['km'] < 2).sum()}")

# greedy one-to-one matching by distance (nearest first), same date
cand = cand.sort_values("km")
used_r, used_e, m = set(), set(), []
for _, c in cand.iterrows():
    if c["index_r"] in used_r or c["index_e"] in used_e:
        continue
    used_r.add(c["index_r"])
    used_e.add(c["index_e"])
    m.append(c)
M = pd.DataFrame(m).sort_values(["date", "km"]).reset_index(drop=True)
M["ratio_r_over_e"] = M["value_r"] / M["value_e"]
M.to_csv(out / "pairs_1to1.csv", index=False)

print(f"\n1:1 same-date pairs: {len(M)}")
print(
    "distance km quantiles:",
    M["km"].quantile([0, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 1]).round(3).to_dict(),
)
print("pairs with km>2:", (M["km"] > 2).sum())
print(
    M.loc[
        M["km"] > 2, ["date", "lat_r", "lon_r", "lat_e", "lon_e", "km", "value_r", "value_e"]
    ].to_string()
)
unR = R.loc[~R.index.isin(used_r)]
unE = Eau.loc[~Eau.index.isin(used_e)]
print(f"\nunmatched Reisser rows: {len(unR)}")
print(unR[["date", "lat", "lon", "Sampling Method", "value", "Region"]].to_string())
print(f"\nunmatched Eriksen-in-box rows: {len(unE)}")
print(unE[["date", "lat", "lon", "value", "Region", "Keywords"]].to_string())

close = M[M["km"] < 2]
print(f"\nclose pairs (<2 km, same date): {len(close)}")
z_r, z_e = close["value_r"] == 0, close["value_e"] == 0
print(
    f"zero both {int((z_r & z_e).sum())}, zero R only {int((z_r & ~z_e).sum())}, zero E only {int((~z_r & z_e).sum())}"
)
nz = close[~z_r & ~z_e].copy()
print(
    f"identical values: {(close['value_r'] == close['value_e']).sum()} (of which both zero {int((z_r & z_e).sum())})"
)
q = nz["ratio_r_over_e"].quantile([0, 0.05, 0.25, 0.5, 0.75, 0.95, 1])
print(f"nonzero pairs {len(nz)}: ratio R/E quantiles {q.round(3).to_dict()}")
print(
    f"  geometric mean {np.exp(np.log(nz['ratio_r_over_e']).mean()):.3f}; "
    f"sd of log10 {np.log10(nz['ratio_r_over_e']).std():.3f}"
)
print(f"  share R>E {(nz['ratio_r_over_e'] > 1).mean():.3f}")
print("\nratio by method (R row):")
print(nz.groupby("Sampling Method_r")["ratio_r_over_e"].describe().round(3).to_string())
print("\nratio by year/month:")
print(
    nz.groupby(nz["date"].dt.to_period("M"))["ratio_r_over_e"]
    .agg(["size", "median", "min", "max"])
    .round(3)
    .to_string()
)
print("\nratio by R region:")
print(
    nz.groupby(nz["Region_r"].fillna(""))["ratio_r_over_e"]
    .agg(["size", "median", "min", "max"])
    .round(3)
    .to_string()
)
nz["Eq"] = pd.qcut(nz["value_e"], 5)
print("\nratio by E value quintile:")
print(
    nz.groupby("Eq", observed=True)["ratio_r_over_e"]
    .agg(["size", "median", "min", "max"])
    .round(3)
    .to_string()
)
print("\nlog-log regression log10(R) = a + b log10(E):")
b, a = np.polyfit(np.log10(nz["value_e"]), np.log10(nz["value_r"]), 1)
print(f"  a={a:.3f} b={b:.3f}")
print("\nratio by distance bin:")
print(
    nz.groupby(pd.cut(nz["km"], [0, 0.05, 0.2, 0.5, 1, 2]), observed=True)["ratio_r_over_e"]
    .agg(["size", "median"])
    .round(3)
    .to_string()
)
