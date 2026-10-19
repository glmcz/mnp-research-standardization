"""Co-located record pairs from different studies in the NCEI marine microplastics CSV.

Study = DOI column. Pair = two records, different DOI, same Marine Setting, haversine
distance <= R km, optionally |date difference| <= D days.

Usage: python -I colocate.py <csv> <out_dir>
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

EARTH_KM = 6371.0088
RADII = (10, 50, 100)
DATE_LIMITS = (365, None)

csv, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
out_dir.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(csv, encoding="utf-8-sig", dtype=str, keep_default_na=False)
df["lat"] = pd.to_numeric(df["Latitude (degree)"])
df["lon"] = pd.to_numeric(df["Longitude (degree)"])
df["date"] = pd.to_datetime(df["Sample Date"], format="%m/%d/%Y %I:%M:%S %p")
df["value"] = pd.to_numeric(df["Microplastics Measurement"], errors="coerce")
df["mesh"] = pd.to_numeric(df["Mesh Size (mm)"], errors="coerce")
df["study"] = df["DOI"].str.strip()
df = df.reset_index(drop=True)


def unit_xyz(lat, lon):
    la, lo = np.radians(lat), np.radians(lon)
    return np.column_stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])


def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * EARTH_KM * np.arcsin(np.sqrt(a))


rmax = max(RADII)
chord = 2 * np.sin(rmax / (2 * EARTH_KM)) * 1.0001
parts = []
for setting, sub in df.groupby("Marine Setting"):
    idx = sub.index.to_numpy()
    tree = cKDTree(unit_xyz(sub["lat"].to_numpy(), sub["lon"].to_numpy()))
    p = tree.query_pairs(chord, output_type="ndarray")
    if len(p) == 0:
        continue
    i, j = idx[p[:, 0]], idx[p[:, 1]]
    keep = df["study"].to_numpy()[i] != df["study"].to_numpy()[j]
    parts.append(np.column_stack([i[keep], j[keep]]))
    print(f"{setting}: candidate pairs within {rmax} km {len(p)}, different study {keep.sum()}")

pairs = np.vstack(parts)
i, j = pairs[:, 0], pairs[:, 1]
a, b = df.loc[i].reset_index(drop=True), df.loc[j].reset_index(drop=True)
P = pd.DataFrame(
    {
        "i": i,
        "j": j,
        "setting": a["Marine Setting"],
        "km": haversine(
            a["lat"].to_numpy(), a["lon"].to_numpy(), b["lat"].to_numpy(), b["lon"].to_numpy()
        ),
        "days": (a["date"] - b["date"]).abs().dt.days.to_numpy(),
        "study_a": a["study"],
        "study_b": b["study"],
        "same_unit": (a["Unit"] == b["Unit"]).to_numpy(),
        "same_method": (a["Sampling Method"] == b["Sampling Method"]).to_numpy(),
        "same_org": (a["Organization"] == b["Organization"]).to_numpy(),
        "mesh_a": a["mesh"],
        "mesh_b": b["mesh"],
        "val_a": a["value"],
        "val_b": b["value"],
    }
)
P = P[P["km"] <= rmax].reset_index(drop=True)
lo, hi = np.minimum(P["mesh_a"], P["mesh_b"]), np.maximum(P["mesh_a"], P["mesh_b"])
P["mesh_known"] = P["mesh_a"].notna() & P["mesh_b"].notna()
P["mesh_ratio"] = hi / lo
P["same_mesh"] = P["mesh_known"] & (P["mesh_ratio"] <= 1.1)  # 0.33/0.333/0.335 count as same
P["both_nonzero"] = (P["val_a"] > 0) & (P["val_b"] > 0)
P["exact_dup"] = (P["km"] < 0.01) & (P["days"] == 0) & (P["val_a"] == P["val_b"])
key = np.where(
    P["study_a"] < P["study_b"],
    P["study_a"] + " || " + P["study_b"],
    P["study_b"] + " || " + P["study_a"],
)
P["study_pair"] = key
P.to_csv(out_dir / "pairs_100km.csv.gz", index=False)

rows = []
for r in RADII:
    for d in DATE_LIMITS:
        m = P["km"] <= r
        if d is not None:
            m &= P["days"] <= d
        S = P[m]
        recs = np.unique(np.concatenate([S["i"], S["j"]])) if len(S) else np.array([], int)
        cells = set(
            zip(
                np.floor(df.loc[recs, "lat"]).astype(int),
                np.floor(df.loc[recs, "lon"]).astype(int),
                strict=True,
            )
        )
        if len(S):
            n = len(df)
            g = coo_matrix((np.ones(len(S)), (S["i"], S["j"])), shape=(n, n))
            ncomp, lab = connected_components(g, directed=False)
            clusters = len(set(lab[recs]))
        else:
            clusters = 0
        rows.append(
            {
                "radius_km": r,
                "max_days": d if d is not None else "none",
                "record_pairs": len(S),
                "same_unit": int(S["same_unit"].sum()),
                "diff_unit": int((~S["same_unit"]).sum()),
                "same_method": int(S["same_method"].sum()),
                "diff_method": int((~S["same_method"]).sum()),
                "same_mesh(<=1.1x)": int(S["same_mesh"].sum()),
                "mesh_ratio>10": int((S["mesh_ratio"] > 10).sum()),
                "mesh_missing": int((~S["mesh_known"]).sum()),
                "same_method&mesh": int((S["same_method"] & S["same_mesh"]).sum()),
                "both_nonzero": int(S["both_nonzero"].sum()),
                "same_org": int(S["same_org"].sum()),
                "exact_dup": int(S["exact_dup"].sum()),
                "study_pairs": S["study_pair"].nunique(),
                "study_pairs_same_method&mesh": S.loc[
                    S["same_method"] & S["same_mesh"], "study_pair"
                ].nunique(),
                "studies": len(set(S["study_a"]) | set(S["study_b"])),
                "records": len(recs),
                "cells_1deg": len(cells),
                "clusters": clusters,
            }
        )
        if r == 50 and d == 365:
            S50 = S

summary = pd.DataFrame(rows)
pd.set_option("display.width", 300)
print(summary.to_string(index=False))
summary.to_csv(out_dir / "summary.csv", index=False)

print("\nby setting, 50 km / 365 d")
print(
    S50.groupby("setting")
    .agg(
        pairs=("i", "size"),
        study_pairs=("study_pair", "nunique"),
        same_method=("same_method", "sum"),
        same_mesh=("same_mesh", "sum"),
    )
    .to_string()
)

meta = df.groupby("study").agg(
    ref=("Short Reference", lambda s: ";".join(sorted(set(s)))),
    org=("Organization", "first"),
)


def describe(sp, S):
    sa, sb = sp.split(" || ")
    sel = S[S["study_pair"] == sp]
    recs = np.unique(np.concatenate([sel["i"], sel["j"]]))
    out = {}
    for tag, s in (("A", sa), ("B", sb)):
        rr = df.loc[recs][df.loc[recs, "study"] == s]
        out[tag] = (
            f"{meta.loc[s, 'ref']} | n={len(rr)} | {';'.join(sorted(set(rr['Sampling Method'])))} "
            f"| mesh {';'.join(sorted(set(rr['Mesh Size (mm)'])))} mm | {';'.join(sorted(set(rr['Unit'])))} "
            f"| {rr['date'].dt.year.min()}-{rr['date'].dt.year.max()} "
            f"| median {rr['value'].median():.4g}"
        )
    reg = df.loc[recs, ["Ocean", "Region", "Country"]].replace("", np.nan)
    region = "; ".join(f"{c}={reg[c].mode().iat[0]}" for c in reg if reg[c].notna().any())
    lat, lon = df.loc[recs, "lat"].median(), df.loc[recs, "lon"].median()
    return (
        f"{len(sel)} pairs | {sel['setting'].iat[0]} | {region} | ~({lat:.1f},{lon:.1f}) "
        f"| median km {sel['km'].median():.0f}, median days {sel['days'].median():.0f}"
        f"\n      A: {out['A']}\n      B: {out['B']}"
    )


for label, S in (("50 km / 365 d", S50), ("50 km / no date limit", P[P["km"] <= 50])):
    print(f"\nTop 10 study-pairs, {label}")
    for k, sp in enumerate(S["study_pair"].value_counts().head(10).index, 1):
        print(f"{k:2d}. {describe(sp, S)}")

print("\nAll study pairs 50 km / 365 d with record-pair counts and comparability")
t = S50.groupby("study_pair").agg(
    pairs=("i", "size"),
    same_method=("same_method", "mean"),
    same_mesh=("same_mesh", "mean"),
    nonzero=("both_nonzero", "mean"),
    setting=("setting", "first"),
)
t.index = [" || ".join(meta.loc[s, "ref"] for s in sp.split(" || ")) for sp in t.index]
print(t.sort_values("pairs", ascending=False).round(2).to_string())
