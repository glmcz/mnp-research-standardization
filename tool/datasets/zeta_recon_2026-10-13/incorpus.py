import os
import re
import sys

import pandas as pd

D1 = sys.argv[1]
SI_TEXT = sys.argv[2]


def material_group(text):
    t = text.lower()
    for key, pat in (
        ("PS", r"polystyren"),
        ("PE", r"polyethylene(?! tere)|\bhdpe\b|\bldpe\b|\bpe\b"),
        ("PET", r"terephthal|\bpet\b"),
        ("PP", r"polypropyl|\bpp\b"),
        ("PVC", r"vinyl chlor|\bpvc\b"),
        ("PMMA", r"methacryl|\bpmma\b"),
    ):
        if re.search(pat, t):
            return key
    if re.search(r"hybrid|composite", t):
        return "other"
    for key, pat in (
        ("nylon", r"nylon|polyamide"),
        ("PLA", r"polylactic|\bpla\b"),
        ("PBAT", r"\bpbat\b|butylene adipate"),
    ):
        if re.search(pat, t):
            return key
    # extra split of 'other' for this report only
    for key, pat in (
        ("PU", r"polyurethane|\bpu\b"),
        ("PC", r"polycarbonate"),
        ("tyre", r"tyre|tire|rubber"),
        ("PTFE", r"tetrafluoro|ptfe"),
    ):
        if re.search(pat, t):
            return "other:" + key
    return "other"


d = pd.read_csv(D1, dtype={"value": float}, keep_default_na=True)
d["g"] = d.material.fillna("").map(material_group)
fl = d["flags"].fillna("")
d["vnp"] = fl.str.contains("value_not_printed")
d["missing"] = d.value.isna()
loc = d.evidence_location.fillna("")
d["si_ptr"] = loc.str.contains(
    r"\b(?:Table|Fig(?:ure)?\.?|Supp\w*)\s*S\d|\bS\d+\b|Supporting|Supplement|\bSI\b|\bESI\b",
    regex=True,
    case=False,
)
d["fig_ptr"] = loc.str.contains(r"Fig", case=False) & ~d.si_ptr
d["has_si_text"] = d.pmcid.map(
    lambda p: (
        os.path.isdir(os.path.join(SI_TEXT, p)) or any(f.startswith(p) for f in os.listdir(SI_TEXT))
        if os.path.isdir(SI_TEXT)
        else False
    )
)
mv = d.quantity.eq("zeta_potential") & d.unit.eq("mV")
rows = []
for g, s in d.groupby("g"):
    printed = s[~s.missing & s.quantity.eq("zeta_potential") & s.unit.eq("mV")]
    em = s[~s.missing & s.quantity.eq("electrophoretic_mobility")]
    miss = s[s.missing]
    rows.append(
        dict(
            group=g,
            rows=len(s),
            papers=s.pmcid.nunique(),
            zeta_mV_values=len(printed),
            zeta_papers=printed.pmcid.nunique(),
            mobility_values=len(em),
            empty_value=len(miss),
            vnp_flag=int(s.vnp.sum()),
            empty_papers=miss.pmcid.nunique(),
            empty_si_ptr=int(miss.si_ptr.sum()),
            empty_si_ptr_papers=miss[miss.si_ptr].pmcid.nunique(),
            empty_fig_ptr=int(miss.fig_ptr.sum()),
            empty_fig_papers=miss[miss.fig_ptr].pmcid.nunique(),
            empty_si_text_on_disk=int((miss.si_ptr & miss.has_si_text).sum()),
        )
    )
r = pd.DataFrame(rows).sort_values("rows", ascending=False)
pd.set_option("display.width", 250)
print(r.to_string(index=False))
print(
    "total empty",
    d.missing.sum(),
    "vnp",
    d.vnp.sum(),
    "empty&si",
    (d.missing & d.si_ptr).sum(),
    "papers",
    d[d.missing & d.si_ptr].pmcid.nunique(),
)
print(
    "vnp but value present",
    (d.vnp & ~d.missing).sum(),
    "empty but no vnp",
    (d.missing & ~d.vnp).sum(),
)
thin = d[
    d.g.isin(
        [
            "nylon",
            "PVC",
            "PP",
            "PE",
            "PET",
            "PLA",
            "PBAT",
            "PMMA",
            "other:PU",
            "other:PC",
            "other:tyre",
        ]
    )
    & d.missing
]
print(
    thin[["pmcid", "g", "material", "evidence_location", "has_si_text"]]
    .sort_values(["g", "pmcid"])
    .to_string()
)
print("----- size-filtered (as tool/p2/build.py)")
v = d[d.value.notna() & mv].copy()
v["size_nm"] = pd.to_numeric(v.size_nominal_nm, errors="coerce").fillna(
    pd.to_numeric(v.size_measured_nm, errors="coerce")
)
v = v[v.size_nm.gt(0)]
print(
    v.groupby("g")
    .agg(values=("value", "size"), papers=("pmcid", "nunique"))
    .sort_values("values", ascending=False)
    .to_string()
)
print("----- thin missing grouped")
t = thin.copy()
t["loc"] = t.evidence_location.fillna("").str.slice(0, 70)
print(
    t.groupby(["g", "pmcid"])
    .agg(n=("loc", "size"), si_text=("has_si_text", "first"), loc=("loc", "first"))
    .to_string()
)
