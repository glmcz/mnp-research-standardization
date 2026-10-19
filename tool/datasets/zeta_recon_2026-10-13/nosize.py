import sys

import pandas as pd

sys.path.insert(0, "")
exec(
    open(sys.argv[2])
    .read()
    .split("d = pd.read_csv")[0]
    .split("D1 = sys.argv[1]")[1]
    .split("\n", 1)[1]
)  # reuse material_group only
d = pd.read_csv(sys.argv[1])
d["g"] = d.material.fillna("").map(material_group)  # noqa: F821, defined by the exec above
v = d[d.value.notna() & d.quantity.eq("zeta_potential") & d.unit.eq("mV")].copy()
v["size_nm"] = pd.to_numeric(v.size_nominal_nm, errors="coerce").fillna(
    pd.to_numeric(v.size_measured_nm, errors="coerce")
)
ns = v[~v.size_nm.gt(0)]
print(ns.groupby("g").agg(values=("value", "size"), papers=("pmcid", "nunique")).to_string())
print(
    ns[ns.g.isin(["nylon", "PVC", "PLA", "PBAT"])][
        ["pmcid", "g", "material", "particle_name", "value"]
    ].to_string()
)
