"""Extract Reisser 2013 and Eriksen 2014 rows from the NCEI CSV and profile them.

Usage: python -I extract.py <ncei_csv> <out_dir>
"""

import sys
from pathlib import Path

import pandas as pd

REISSER = "https://doi.org/10.1371/journal.pone.0080466"
ERIKSEN = "https://doi.org/10.1371/journal.pone.0111913"

csv, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
df = pd.read_csv(csv, encoding="utf-8-sig", dtype=str, keep_default_na=False)
df["study"] = df["DOI"].str.strip()
sub = df[df["study"].isin([REISSER, ERIKSEN])].copy()
sub["tag"] = sub["study"].map({REISSER: "R", ERIKSEN: "E"})
sub["lat"] = pd.to_numeric(sub["Latitude (degree)"])
sub["lon"] = pd.to_numeric(sub["Longitude (degree)"])
sub["date"] = pd.to_datetime(sub["Sample Date"], format="%m/%d/%Y %I:%M:%S %p")
sub["value"] = pd.to_numeric(sub["Microplastics Measurement"], errors="coerce")
sub.to_csv(out / "rows_R_E.csv", index=False)

pd.set_option("display.width", 250)
pd.set_option("display.max_colwidth", 120)
for tag, g in sub.groupby("tag"):
    print(f"=== {tag}: {len(g)} rows")
    for c in ["Short Reference", "Long Reference", "Organization", "Sampling Method", "Mesh Size (mm)",
              "Unit", "Water Sample Depth (m)", "Ocean", "Region", "Subregion", "Country",
              "NCEI Accession Number", "Study Type", "Keywords", "Collecting Time (min)"]:
        print(f"  {c}: {g[c].value_counts().to_dict()}")
    print(f"  date range {g['date'].min()} .. {g['date'].max()}")
    print(f"  date hour/minute values: {g['date'].dt.strftime('%H:%M').value_counts().head(10).to_dict()}")
    print(f"  lat {g['lat'].min()} .. {g['lat'].max()}, lon {g['lon'].min()} .. {g['lon'].max()}")
    print(f"  years: {g['date'].dt.year.value_counts().sort_index().to_dict()}")
    print(f"  values: n={g['value'].notna().sum()} zeros={(g['value'] == 0).sum()} "
          f"min={g['value'].min()} median={g['value'].median()} max={g['value'].max()}")
    print(f"  lat/lon decimals: {g['Latitude (degree)'].str.split('.').str[1].str.len().value_counts().to_dict()}")
    print(f"  value strings sample: {g['Microplastics Measurement'].head(8).tolist()}")
