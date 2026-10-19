"""Join the four tables on true tow identity and decompose the NCEI Reisser/Eriksen ratio.

Inputs are the outputs of reconcile.py.
Usage: python -I tow_identity.py <out_dir> <refine_pairs_csv.gz or ->
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

out = Path(sys.argv[1])
EARTH_KM = 6371.0088


def hav(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = (
        np.sin((p2 - p1) / 2) ** 2
        + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_KM * np.arcsin(np.sqrt(a))


S1 = pd.read_csv(out / "reisser_S1.csv", parse_dates=["date"])
F = pd.read_csv(out / "figshare_reisser_rows.csv", parse_dates=["date"])
NR = pd.read_csv(out / "ncei_R_reconciled.csv", parse_dates=["date"], dtype={"Unique ID": str})
NE = pd.read_csv(out / "ncei_E_reconciled.csv", parse_dates=["date"], dtype={"Unique ID": str})
pd.set_option("display.width", 300)
pd.set_option("display.max_columns", 30)

# FIG -> S1 station (same date, nearest station position), tow = order in the figshare file
F = F[F["date"].dt.year <= 2012].copy()
F["row"] = np.arange(len(F))
st, km = [], []
for _, r in F.iterrows():
    c = S1[S1["date"] == r["date"]].drop_duplicates("station")
    d = hav(r["lat"], r["lon"], c["lat"].to_numpy(), c["lon"].to_numpy())
    st.append(c["station"].to_numpy()[np.argmin(d)])
    km.append(d.min())
F["station"], F["station_km"] = st, km
F["tow"] = F.groupby("station")["row"].rank(method="first").astype(int)
print(
    f"FIG 2011-12 Reisser rows {len(F)}; station km max {max(km):.2f}; tows per station "
    f"{F.groupby('station').size().value_counts().to_dict()}"
)
J = S1.merge(
    F[["station", "tow", "CD1", "CD2", "CD3", "CD4", "CDall", "CDmicro", "lat", "lon", "SeaState"]],
    on=["station", "tow"],
    suffixes=("_s1", "_fig"),
)
J["rel_diff"] = (J["CDall"] - J["Cs"]) / J["Cs"].where(J["Cs"] > 0)
print(f"S1 x FIG joined {len(J)}")
print(
    f"  both zero {((J['Cs'] == 0) & (J['CDall'] == 0)).sum()}, S1 zero & FIG>0 {((J['Cs'] == 0) & (J['CDall'] > 0)).sum()}, "
    f"S1>0 & FIG zero {((J['Cs'] > 0) & (J['CDall'] == 0)).sum()}"
)
print(
    "  |FIG-S1|/S1 quantiles:",
    J["rel_diff"].abs().quantile([0.5, 0.75, 0.9, 0.95, 0.99, 1]).round(4).to_dict(),
)
big = J[J["rel_diff"].abs() > 0.02]
print(f"  tows differing by >2%: {len(big)}")
print(big[["station", "tow", "date", "Cs", "CD1", "CD2", "CD3", "CDall", "rel_diff"]].to_string())
print(
    f"  share of FIG count density in >4.75 mm (CD3) over all tows: {J['CD3'].sum() / J['CDall'].sum():.3f}; "
    f"CD1 (0.33-1 mm) share {J['CD1'].sum() / J['CDall'].sum():.3f}"
)
print(
    f"  mean CDall {J['CDall'].mean():.1f} vs mean Cs {J['Cs'].mean():.1f}; mean CDmicro {J['CDmicro'].mean():.1f}"
)

# NCEI R row <-> S1 (station, tow) already in NR; NCEI E row <-> FIG row via fig_idx -> need FIG station/tow
Fall = pd.read_csv(out / "figshare_reisser_rows.csv", parse_dates=["date"])
Fall = Fall.join(F[["station", "tow"]])  # same index as F (F is a filtered copy of Fall)
NE = NE.join(Fall[["station", "tow"]].add_prefix("fig_"), on="fig_idx")
T = NR[
    ["Unique ID", "date", "station", "tow", "Sampling Method", "value", "Cs", "lat", "lon"]
].merge(
    NE[["Unique ID", "fig_station", "fig_tow", "value", "CDall", "CDmicro", "CD3", "lat", "lon"]],
    left_on=["station", "tow"],
    right_on=["fig_station", "fig_tow"],
    suffixes=("_R", "_E"),
)
T["km_RE"] = hav(T["lat_R"], T["lon_R"], T["lat_E"], T["lon_E"])
print(f"\nNCEI R x NCEI E joined on true tow identity: {len(T)}")
T["d_R"] = np.where(T["Sampling Method"] == "Manta net", 0.085, 0.300)
T["pred_R"] = T["Cs"] / 1e6 / T["d_R"]
T["pred_E"] = T["CDmicro"] / 1e6 / 0.08
print(
    f"  max |NCEI_R - Cs/1e6/d_R| = {np.abs(T['value_R'] - T['pred_R']).max():.2e}; "
    f"max |NCEI_E - CDmicro/1e6/0.08| = {np.abs(T['value_E'] - T['pred_E']).max():.2e}"
)
print(
    f"  identical values: {(T['value_R'] == T['value_E']).sum()} (both zero: {((T['value_R'] == 0) & (T['value_E'] == 0)).sum()})"
)
print(
    f"  R>0 & E=0: {((T['value_R'] > 0) & (T['value_E'] == 0)).sum()}  R=0 & E>0: {((T['value_R'] == 0) & (T['value_E'] > 0)).sum()}"
)
print(
    "  km between NCEI R and NCEI E position of the same tow:",
    T["km_RE"].quantile([0, 0.5, 0.9, 1]).round(3).to_dict(),
)
nz = T[(T["value_R"] > 0) & (T["value_E"] > 0)].copy()
nz["ratio"] = nz["value_R"] / nz["value_E"]
nz["depth_factor"] = 0.08 / nz["d_R"]
nz["size_factor"] = nz["Cs"] / nz["CDmicro"]
print(
    f"  nonzero both: {len(nz)}; ratio R/E median {nz['ratio'].median():.3f}, IQR "
    f"{nz['ratio'].quantile(0.25):.3f}-{nz['ratio'].quantile(0.75):.3f}, min {nz['ratio'].min():.3f} max {nz['ratio'].max():.3f}"
)
print(
    f"  check ratio == depth_factor*size_factor: max rel err "
    f"{(nz['ratio'] / (nz['depth_factor'] * nz['size_factor']) - 1).abs().max():.2e}"
)
print(
    nz.groupby("Sampling Method")
    .agg(
        n=("ratio", "size"),
        ratio_med=("ratio", "median"),
        ratio_q25=("ratio", lambda s: s.quantile(0.25)),
        ratio_q75=("ratio", lambda s: s.quantile(0.75)),
        depth_factor=("depth_factor", "first"),
        size_factor_med=("size_factor", "median"),
        share_size1=("size_factor", lambda s: (np.abs(s - 1) < 0.01).mean()),
    )
    .round(3)
    .to_string()
)
print("  ratio by Sampling Method x voyage month:")
print(
    nz.groupby([nz["date"].dt.to_period("M"), "Sampling Method"])["ratio"]
    .agg(["size", "median", "min", "max"])
    .round(3)
    .to_string()
)
T.to_csv(out / "tow_identity_R_E.csv", index=False)

# per-tow ratio including what the 'nearest same-day row' rule matched vs truth
P = pd.read_csv(out / "pairs_1to1.csv", dtype={"Unique ID_r": str, "Unique ID_e": str})
truth = dict(zip(T["Unique ID_R"], T["Unique ID_E"], strict=True))
P["true_partner"] = P["Unique ID_r"].map(truth) == P["Unique ID_e"]
print(
    f"\nnearest-position 1:1 rule picked the true partner in {P['true_partner'].sum()}/{len(P)} tows"
)

# many-to-many: all same-day <2 km R x E pairs (the refine.py 'same tow' rule)
R = NR.set_index("Unique ID")
E = NE.set_index("Unique ID")
mm = R.reset_index()[["Unique ID", "date", "lat", "lon", "value"]].merge(
    E.reset_index()[["Unique ID", "date", "lat", "lon", "value"]], on="date", suffixes=("_R", "_E")
)
mm["km"] = hav(mm["lat_R"], mm["lon_R"], mm["lat_E"], mm["lon_E"])
mm = mm[mm["km"] < 2].copy()
mm["true"] = mm["Unique ID_R"].map(truth) == mm["Unique ID_E"]
with np.errstate(divide="ignore", invalid="ignore"):
    mm["l10"] = np.log10(
        np.maximum(mm["value_R"], mm["value_E"]) / np.minimum(mm["value_R"], mm["value_E"])
    )
print(
    f"many-to-many same-day <2 km pairs: {len(mm)} (true-tow pairs among them {mm['true'].sum()})"
)
print(
    f"  median |log10 ratio| incl. inf/NaN as pandas does: {mm['l10'].median():.3f} -> x{10 ** mm['l10'].median():.2f}"
)
for lab, s in (("true-tow pairs", mm[mm["true"]]), ("wrong-tow pairs", mm[~mm["true"]])):
    print(
        f"  {lab}: n={len(s)}, median |log10 ratio| {s['l10'].median():.3f} -> x{10 ** s['l10'].median():.2f}"
    )
