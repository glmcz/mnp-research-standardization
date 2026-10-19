import sys

import pandas as pd

df = pd.read_excel(sys.argv[1], sheet_name="information")
df = df[df["ID"].notna()]
print("rows", len(df), "studies(titles)", df["Title"].nunique())
for c in [
    "Size min(μm)",
    "Size max(μm)",
    "Latitude",
    "Longitude",
    "Sampling date",
    "abundance_numeric",
    "abundance_corrected",
    "Identification and Quantification of MPs",
]:
    print(c, df[c].notna().sum())
both = df["Size min(μm)"].notna() & df["Size max(μm)"].notna()
print("size min&max", both.sum())
print("size min", df["Size min(μm)"].value_counts().head(8).to_dict())
print("size max", df["Size max(μm)"].value_counts().head(8).to_dict())
print("Sampling date sample", df["Sampling date"].astype(str).value_counts().head(10).to_dict())
print("Land use", df["Land use"].value_counts().head(10).to_dict())
print("Location top", df["Location"].value_counts().head(5).to_dict())
r = df.assign(la=df["Latitude"].round(1), lo=df["Longitude"].round(1))
g = r.groupby(["la", "lo"])["Title"].nunique()
print("0.1deg cells", len(g), "cells with >=2 studies", (g >= 2).sum())
print(df[["abundance_numeric", "abundance_corrected", "CF"]].describe().to_string())
