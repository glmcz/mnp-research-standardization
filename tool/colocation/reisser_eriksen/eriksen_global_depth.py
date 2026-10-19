"""Is NCEI's Eriksen 2014 conversion one constant for all 680 tows? Match NCEI-E rows to the
figshare table by exact position and compute the implied depth (CD1+CD2)/1e6/value.

Usage: python -I eriksen_global_depth.py <rows_R_E.csv> <figshare_eriksen2014.csv>
"""

import sys

import pandas as pd

D = pd.read_csv(sys.argv[1], dtype={"Unique ID": str})
E = D[D["tag"] == "E"].copy()
F = pd.read_csv(sys.argv[2])
F = F[F[["CD1", "CD2", "CD3"]].notna().any(axis=1)].copy()
F["CDmicro"] = F[["CD1", "CD2"]].fillna(0).sum(axis=1)
F["key"] = F["Latitude"].round(4).astype(str) + "," + F["Longitude"].round(4).astype(str)
E["key"] = E["lat"].round(4).astype(str) + "," + E["lon"].round(4).astype(str)
M = E.merge(F[["key", "CDmicro", "Source"]].drop_duplicates("key"), on="key", how="left")
print(f"NCEI-E rows {len(E)}, matched to figshare by exact position {M['CDmicro'].notna().sum()}")
nz = M[(M["value"] > 0) & (M["CDmicro"] > 0)].copy()
nz["depth"] = nz["CDmicro"] / 1e6 / nz["value"]
print(nz.groupby("Source")["depth"].describe().round(4).to_string())
print(f"zero-value rows with CDmicro>0: {((M['value'] == 0) & (M['CDmicro'] > 0)).sum()}")
