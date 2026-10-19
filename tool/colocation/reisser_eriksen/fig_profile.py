"""Profile the Eriksen 2014 figshare table (tow-level, pieces/km2 by size class).

Usage: python -I fig_profile.py <xlsx> <out_dir>
"""

import sys
from pathlib import Path

import pandas as pd

x = pd.read_excel(sys.argv[1], header=None, skiprows=2)
x.columns = [
    "Date",
    "Latitude",
    "Longitude",
    "CD1",
    "CD2",
    "CD3",
    "CD4",
    "WD1",
    "WD2",
    "WD3",
    "WD4",
    "SeaState",
    "Source",
    "Info",
    "Comments",
    "extra",
][: x.shape[1]]
out = Path(sys.argv[2])
x.to_csv(out / "figshare_eriksen2014.csv", index=False)
pd.set_option("display.width", 300)
pd.set_option("display.max_columns", 30)
print("rows", len(x))
print("Source counts:\n", x["Source"].value_counts(dropna=False).to_string())
print("\nDate dtype", x["Date"].dtype, "sample", x["Date"].head(3).tolist())
x["has_cd"] = x[["CD1", "CD2", "CD3", "CD4"]].notna().any(axis=1)
print("rows with any CD:", x["has_cd"].sum())
print("rows with CD1 or CD2 (net tows?):", x[["CD1", "CD2"]].notna().any(axis=1).sum())
print(
    "rows with only CD4 (visual?):",
    (x["CD4"].notna() & x[["CD1", "CD2", "CD3"]].isna().all(axis=1)).sum(),
)
au = x[x["Source"].astype(str).str.contains("Reisser", case=False)]
print(f"\nReisser-sourced rows: {len(au)}")
print(au.head(30).to_string())
print("\nInfo values sample:", au["Info"].astype(str).head(20).tolist())
print("Comments:", au["Comments"].value_counts(dropna=False).head(10).to_dict())
print("Sea state:", au["SeaState"].value_counts(dropna=False).sort_index().to_dict())
print("date values:", au["Date"].astype(str).value_counts().sort_index().to_dict())
