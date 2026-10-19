"""Tow-by-tow reconciliation of four tables for the 171 Australian net tows:

  S1  Reisser 2013 Table S1 (pieces/km2, all sizes, station position)
  FIG Eriksen 2014 figshare (pieces/km2 by size class CD1..CD4, tow position)
  NR  NCEI rows under the Reisser DOI (pieces/m3)
  NE  NCEI rows under the Eriksen DOI (pieces/m3)

Usage: python -I reconcile.py <reisser_S1.txt> <figshare_eriksen2014.csv> <rows_R_E.csv> <out_dir>
"""

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

s1_txt, fig_csv, rows_csv, out = sys.argv[1:5]
out = Path(out)
EARTH_KM = 6371.0088


def hav(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = (
        np.sin((p2 - p1) / 2) ** 2
        + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_KM * np.arcsin(np.sqrt(a))


# --- S1
pat = re.compile(
    r"^\s*(\d+)\s+(\d\d)\.(\d\d)\.(\d\d)\s+(\d+)\s+([\d.]+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s*$"
)
recs = []
for line in open(s1_txt, encoding="utf-8", errors="replace"):
    m = pat.match(line.replace("\xa0", " "))
    if m:
        st, dd, mm, yy, la, lam, lo, lom, cs = m.groups()
        recs.append(
            {
                "station": int(st),
                "date": pd.Timestamp(2000 + int(yy), int(mm), int(dd)),
                "lat": -(int(la) + float(lam) / 60),
                "lon": int(lo) + float(lom) / 60,
                "Cs": float(cs),
            }
        )
S1 = pd.DataFrame(recs)
S1["tow"] = S1.groupby("station").cumcount() + 1
print(
    f"S1 tows parsed: {len(S1)}, stations {S1['station'].nunique()}, "
    f"mean Cs {S1['Cs'].mean():.1f} (paper: 4256.4), median {S1['Cs'].median():.1f} (paper: 1932.1), "
    f"max {S1['Cs'].max():.1f} (paper: 48895.6), zero tows {(S1['Cs'] == 0).sum()} (paper: 35 = 171-136)"
)

# --- FIG (Reisser-sourced trawl rows)
F = pd.read_csv(fig_csv)
F = F[
    F["Source"].astype(str).str.contains("Reisser") & F[["CD1", "CD2", "CD3"]].notna().any(axis=1)
].copy()


def fix_date(v):
    s = str(v)
    if re.match(r"^\d{4}-\d\d-\d\d", s):  # excel parsed dd/mm as mm/dd
        t = pd.Timestamp(s[:10])
        return pd.Timestamp(t.year, t.day, t.month)
    d, m, y = s.split("/")
    y = int(y)
    return pd.Timestamp(y + 2000 if y < 100 else y, int(m), int(d))


F["date"] = F["Date"].map(fix_date)
F["lat"], F["lon"] = F["Latitude"], F["Longitude"]
F["CDall"] = F[["CD1", "CD2", "CD3", "CD4"]].fillna(0).sum(axis=1)
F["CDmicro"] = F[["CD1", "CD2"]].fillna(0).sum(axis=1)
F["CD123"] = F[["CD1", "CD2", "CD3"]].fillna(0).sum(axis=1)
F = F.reset_index(drop=True)
print(
    f"FIG Reisser trawl rows: {len(F)}; extra col: {F['extra'].value_counts(dropna=False).to_dict()}; "
    f"CD4>0 rows: {(F['CD4'].fillna(0) > 0).sum()}"
)

# --- NCEI
D = pd.read_csv(rows_csv, dtype={"Unique ID": str})
D["date"] = pd.to_datetime(D["date"]).dt.normalize()
NR = D[D["tag"] == "R"].copy()
NE = D[
    (D["tag"] == "E")
    & D["lat"].between(-45, -5)
    & D["lon"].between(110, 180)
    & (D["date"].dt.year <= 2012)
].copy()
NR["seq"] = NR["Unique ID"].str[-7:].astype(int)
NE["seq"] = NE["Unique ID"].str[-7:].astype(int)
NR = NR.sort_values("seq").reset_index(drop=True)
NE = NE.sort_values("seq").reset_index(drop=True)
print(
    f"NCEI R rows {len(NR)} (seq {NR['seq'].min()}..{NR['seq'].max()}), "
    f"NCEI E Australian 2011-12 rows {len(NE)} (seq {NE['seq'].min()}..{NE['seq'].max()})"
)


def match_pos(A, B, tag):
    """Each A row -> B row with same date and the exact/nearest position."""
    j = []
    for _, a in A.iterrows():
        c = B[B["date"] == a["date"]]
        if len(c) == 0:
            j.append((np.nan, np.nan))
            continue
        dist = hav(a["lat"], a["lon"], c["lat"].to_numpy(), c["lon"].to_numpy())
        k = int(np.argmin(dist))
        j.append((c.index[k], dist[k]))
    A[f"{tag}_idx"] = [x[0] for x in j]
    A[f"{tag}_km"] = [x[1] for x in j]
    return A


# NCEI E <-> FIG: tow positions should be identical
NE = match_pos(NE, F, "fig")
print(
    f"\nNCEI-E -> FIG matched {NE['fig_idx'].notna().sum()}/{len(NE)}; "
    f"km quantiles {NE['fig_km'].quantile([0, 0.5, 0.9, 1]).round(4).to_dict()}; unique FIG rows {NE['fig_idx'].nunique()}"
)
NE = NE.join(
    F[["CD1", "CD2", "CD3", "CD4", "CDall", "CDmicro", "CD123", "SeaState", "Info"]], on="fig_idx"
)
# NCEI R <-> FIG: tow positions too?
NR = match_pos(NR, F, "fig")
print(
    f"NCEI-R -> FIG matched {NR['fig_idx'].notna().sum()}/{len(NR)}; "
    f"km quantiles {NR['fig_km'].quantile([0, 0.5, 0.9, 1]).round(4).to_dict()}; unique FIG rows {NR['fig_idx'].nunique()}"
)
NR = NR.join(F[["CDall", "CDmicro", "CD123", "SeaState"]].add_prefix("F_"), on="fig_idx")

# NCEI R <-> S1: same date & station, then tow order by NCEI seq
NR["near_station"] = np.nan
for i, a in NR.iterrows():
    c = S1[S1["date"] == a["date"]]
    if len(c):
        dist = hav(a["lat"], a["lon"], c["lat"].to_numpy(), c["lon"].to_numpy())
        NR.loc[i, "near_station"] = c["station"].to_numpy()[int(np.argmin(dist))]
        NR.loc[i, "station_km"] = dist.min()
NR["tow"] = NR.groupby("near_station")["seq"].rank(method="first")
NR = NR.merge(
    S1[["station", "tow", "Cs"]],
    left_on=["near_station", "tow"],
    right_on=["station", "tow"],
    how="left",
)
print(
    f"NCEI-R -> S1 station matched {NR['Cs'].notna().sum()}; station km max {NR['station_km'].max():.2f}"
)

# implied depths: value[m-3] = C[km-2] / 1e6 / depth  -> depth = C/1e6/value
NR["depth_vs_S1"] = NR["Cs"] / 1e6 / NR["value"]
NR["depth_vs_FIGall"] = NR["F_CDall"] / 1e6 / NR["value"]
pd.set_option("display.width", 300)
print("\nNCEI-R implied depth (Cs/1e6/value) by net:")
print(NR[NR["value"] > 0].groupby("Sampling Method")["depth_vs_S1"].describe().round(4).to_string())
print("NCEI-R implied depth vs FIG CDall:")
print(
    NR[NR["value"] > 0]
    .groupby("Sampling Method")["depth_vs_FIGall"]
    .describe()
    .round(4)
    .to_string()
)
print(
    f"NCEI-R zero where S1>0: {((NR['value'] == 0) & (NR['Cs'] > 0)).sum()}, "
    f"NCEI-R >0 where S1=0: {((NR['value'] > 0) & (NR['Cs'] == 0)).sum()}"
)

for col in ["CDall", "CDmicro", "CD123"]:
    NE[f"depth_{col}"] = NE[col] / 1e6 / NE["value"]
print("\nNCEI-E implied depth by numerator (value>0):")
print(
    NE[NE["value"] > 0][["depth_CDall", "depth_CDmicro", "depth_CD123"]]
    .describe()
    .round(4)
    .to_string()
)
print(
    f"NCEI-E zero where CDmicro>0: {((NE['value'] == 0) & (NE['CDmicro'] > 0)).sum()}, "
    f"zero where CDall>0: {((NE['value'] == 0) & (NE['CDall'] > 0)).sum()}, "
    f">0 where CDmicro=0: {((NE['value'] > 0) & (NE['CDmicro'] == 0)).sum()}"
)

NR.to_csv(out / "ncei_R_reconciled.csv", index=False)
NE.to_csv(out / "ncei_E_reconciled.csv", index=False)
S1.to_csv(out / "reisser_S1.csv", index=False)
F.to_csv(out / "figshare_reisser_rows.csv", index=False)
