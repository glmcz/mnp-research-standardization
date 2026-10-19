"""How DOI, accession, short reference and organization map onto each other.
Usage: python -I study_ids.py <csv>"""

import sys

import pandas as pd

df = pd.read_csv(sys.argv[1], encoding="utf-8-sig", dtype=str, keep_default_na=False)
g = df.groupby("DOI").agg(
    n=("Unique ID", "size"),
    acc=("NCEI Accession Number", lambda s: ";".join(sorted(set(s)))),
    ref=("Short Reference", lambda s: ";".join(sorted(set(s)))),
    org=("Organization", lambda s: ";".join(sorted(set(s)))),
    setting=("Marine Setting", lambda s: ";".join(sorted(set(s)))),
    method=("Sampling Method", lambda s: ";".join(sorted(set(s)))[:60]),
    mesh=("Mesh Size (mm)", lambda s: ";".join(sorted(set(s)))[:40]),
)
pd.set_option("display.width", 250)
pd.set_option("display.max_colwidth", 70)
print(g.sort_values("n", ascending=False).to_string())
print("\naccessions per DOI max", df.groupby("DOI")["NCEI Accession Number"].nunique().max())
print("DOIs per accession max", df.groupby("NCEI Accession Number")["DOI"].nunique().max())
print("DOIs that are NCEI dataset DOIs (10.25921):", sum("10.25921" in d for d in g.index))
print("orgs with >1 DOI:")
print(df.groupby("Organization")["DOI"].nunique().loc[lambda s: s > 1].sort_values(ascending=False).to_string())
print("\nnon-nurdle rows with empty mesh:",
      ((df["Marine Setting"] != "Nurdle Patrol") & (df["Mesh Size (mm)"].str.strip() == "")).sum())
print("mesh by setting (non-empty share):")
print(df.assign(has=df["Mesh Size (mm)"].str.strip() != "").groupby("Marine Setting")["has"].mean().to_string())
