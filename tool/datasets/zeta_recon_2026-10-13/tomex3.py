import json
import sys

import pandas as pd

pd.set_option("display.width", 250)
pd.set_option("display.max_colwidth", 60)
corp = set()
for line in open(sys.argv[1]):
    r = json.loads(line)
    if r.get("doi"):
        corp.add(r["doi"].lower().strip())
for f, zc, mc, pc in (
    (sys.argv[2], "zetapotential.mV", "zetapotential.media", "poly_f"),
    (sys.argv[3], "zetapotential", "zeta.potential.media", "poly_h_f"),
):
    d = pd.read_pickle(f)
    d.columns = [str(c) for c in d.columns]
    print(
        "=====",
        f.split("/")[-1],
        d.shape,
        "dois",
        d["doi"].nunique(),
        "years",
        d["year"].astype(str).value_counts().sort_index().tail(6).to_dict(),
    )
    z = pd.to_numeric(d[zc], errors="coerce")
    h = d[z.notna()].copy()
    h["z"] = z[z.notna()]
    print("rows with numeric zeta", len(h), "dois", h["doi"].nunique())
    h["size_um"] = pd.to_numeric(h["size.length.um.used.for.conversions"], errors="coerce")
    u = h.drop_duplicates(["doi", pc, "z", "size_um"])
    print("distinct (doi, polymer, zeta, size):", len(u))
    print(
        u.groupby(pc, observed=True)
        .agg(values=("z", "size"), studies=("doi", "nunique"))
        .sort_values("values", ascending=False)
        .to_string()
    )
    nonps = u[~u[pc].astype(str).str.contains("Polystyrene|PS", regex=True)]
    print(nonps[["doi", "year", pc, "z", "size_um", mc, "functional.group"]].to_string())
    print("media (distinct doi,z):")
    print(u[mc].astype(str).value_counts().head(12).to_string())
    print(
        "with size:",
        u.size_um.notna().sum(),
        "with functional.group:",
        u["functional.group"].notna().sum(),
    )
    dois = {str(x).lower().strip().replace("https://doi.org/", "") for x in h.doi.dropna()}
    print("zeta dois in our 1115 search set:", len(dois & corp), "of", len(dois))
    print("all polymers in db:", d[pc].astype(str).value_counts().head(25).to_dict())
