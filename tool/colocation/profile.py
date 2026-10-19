"""Profile the NCEI marine microplastics CSV. Usage: python -I profile.py <csv>"""

import sys

import pandas as pd

df = pd.read_csv(sys.argv[1], encoding="utf-8-sig", dtype=str, keep_default_na=False)
print("rows", len(df))
print("columns", len(df.columns))
for c in df.columns:
    nonempty = (df[c].str.strip() != "").sum()
    print(f"  {c!r}: non-empty {nonempty}, distinct {df[c].nunique()}")

dates = pd.to_datetime(df["Sample Date"], format="%m/%d/%Y %I:%M:%S %p", errors="coerce")
print("unparsed dates", dates.isna().sum(), "min", dates.min(), "max", dates.max())
print(dates.dt.year.value_counts().sort_index().to_string())


def top(col, n=25):
    print(f"\n== {col}")
    print(df[col].replace("", "<empty>").value_counts().head(n).to_string())


for col in [
    "Marine Setting",
    "Unit",
    "Sampling Method",
    "Mesh Size (mm)",
    "Study Type",
    "Ocean",
    "Concentration Class",
]:
    top(col)

print("\n== Marine Setting x Unit")
print(pd.crosstab(df["Marine Setting"], df["Unit"]).to_string())

print("\n== Sampling Method x Marine Setting (top methods)")
m = df["Sampling Method"].value_counts().head(20).index
print(
    pd.crosstab(
        df.loc[df["Sampling Method"].isin(m), "Sampling Method"],
        df.loc[df["Sampling Method"].isin(m), "Marine Setting"],
    ).to_string()
)

meas = pd.to_numeric(df["Microplastics Measurement"], errors="coerce")
print("\nmeasurement non-numeric:", meas.isna().sum(), " zero:", (meas == 0).sum())

for col in ["DOI", "Short Reference", "Long Reference", "Organization", "NCEI Accession Number"]:
    s = df[col].str.strip()
    print(f"{col}: empty {(s == '').sum()}, distinct {s[s != ''].nunique()}")

print("\nrows per accession, top 15")
print(df["NCEI Accession Number"].value_counts().head(15).to_string())
print(
    "\nshort refs per accession (max)",
    df.groupby("NCEI Accession Number")["Short Reference"]
    .nunique()
    .sort_values()
    .tail(10)
    .to_string(),
)
print(
    "\naccessions per short ref (max)",
    df.groupby("Short Reference")["NCEI Accession Number"]
    .nunique()
    .sort_values()
    .tail(10)
    .to_string(),
)
print(
    "\nDOIs per short ref (max)",
    df.groupby("Short Reference")["DOI"].nunique().sort_values().tail(5).to_string(),
)
print(
    "\nshort refs per DOI (max)",
    df[df["DOI"] != ""]
    .groupby("DOI")["Short Reference"]
    .nunique()
    .sort_values()
    .tail(8)
    .to_string(),
)
