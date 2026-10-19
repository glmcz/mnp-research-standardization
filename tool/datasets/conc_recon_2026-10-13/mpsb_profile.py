import re
import sys

import pandas as pd


def norm(s):
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", str(s).strip().lower())


x, ncei_fn = sys.argv[1], sys.argv[2]
ncei = pd.read_csv(ncei_fn, low_memory=False, encoding="utf-8-sig")
ncei_dois = set(norm(v) for v in ncei["DOI"].dropna())
for sheet in ["Literature PSD data", "Literature data summary"]:
    df = pd.read_excel(x, sheet_name=sheet, header=2)
    df = df.loc[:, [c for c in df.columns if not str(c).startswith("Unnamed")]]
    df = df[df["PSD_ID"].notna()]
    print("=====", sheet, "rows", len(df), "cols", len(df.columns))
    print(list(df.columns)[55:])
    print(
        "PSD_IDs",
        df["PSD_ID"].nunique(),
        "studies",
        df["Study"].nunique(),
        "links",
        df["Link"].nunique(),
    )
    print(df.groupby("Sample_type")["PSD_ID"].nunique().sort_values(ascending=False))
    g = df.groupby("PSD_ID").agg(
        lo=("Low_size", "min"),
        hi=("High_size", "max"),
        lat=("Lat", "first"),
        lon=("Lon", "first"),
        d=("Sampling_start_date", "first"),
        unit=("MP_Nconc_unit", "first"),
        conc=("MP_Nconc_reported", "first"),
        st=("Sample_type", "first"),
        link=("Link", "first"),
    )
    print(
        "PSD with lo&hi",
        (g.lo.notna() & g.hi.notna()).sum(),
        "lat/lon",
        (g.lat.notna() & g.lon.notna()).sum(),
        "date",
        g.d.notna().sum(),
        "conc",
        g.conc.notna().sum(),
    )
    print(g.unit.value_counts().head(12))
    print(
        "lo quantiles",
        g.lo.quantile([0.1, 0.5, 0.9]).tolist(),
        "hi quantiles",
        g.hi.quantile([0.1, 0.5, 0.9]).tolist(),
    )
    links = set(norm(v) for v in df["Link"].dropna())
    inn = sorted(link for link in links if link in ncei_dois)
    print("distinct links", len(links), "in NCEI", len(inn), inn[:10])
    print("sample links", sorted(links)[:6])
    print(df.groupby("Sample_type")["Link"].nunique().sort_values(ascending=False))
