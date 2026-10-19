import collections
import csv
import json
import os
import re
import sys

XML = sys.argv[1]
D1 = sys.argv[2]
P = {
    "nylon/PA": r"\bnylon|polyamide|\bPA ?6|\bPA\b",
    "PVC": r"\bPVC\b|vinyl chloride",
    "PP": r"polypropylene|\bPP\b",
    "PLA": r"polylactic|poly\(lactic|polylactide|\bPLA\b",
    "PBAT": r"\bPBAT\b|butylene adipate",
    "PU": r"polyurethane|\bPUR?\b",
    "tyre": r"\btyre|\btire wear|\btire particle|\bTWP|\bTRWP|crumb rubber",
    "PET": r"terephthalate|\bPET\b",
    "PMMA": r"methyl methacrylate|methacrylate\)|\bPMMA\b",
    "PC": r"polycarbonate|\bPC\b(?!\d)",
}
Z = re.compile(r"zeta|ζ|electrophoretic mobilit", re.I)
d1 = collections.defaultdict(set)
grp = {
    "nylon/PA": r"nylon|polyamide",
    "PVC": r"vinyl chlor|\bpvc\b",
    "PP": r"polypropyl|\bpp\b",
    "PLA": r"polylactic|\bpla\b",
    "PBAT": r"\bpbat\b|butylene adipate",
    "PU": r"polyurethane",
    "tyre": r"\btyre|\btire|rubber",
    "PET": r"terephthal|\bpet\b",
    "PMMA": r"methacryl|\bpmma\b",
    "PC": r"polycarbonate",
}
for r in csv.DictReader(open(D1)):
    for g, pat in grp.items():
        if re.search(pat, (r["material"] or "").lower()):
            d1[g].add(r["pmcid"])
hits = collections.defaultdict(set)
win_hits = collections.defaultdict(set)
for f in os.listdir(XML):
    if not f.endswith(".xml"):
        continue
    t = open(os.path.join(XML, f), encoding="utf-8", errors="replace").read()
    b = t.find("<body")
    t = t[b:] if b > 0 else t
    t = re.sub(r"<ref-list.*", "", t, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t)
    pm = f[:-4]
    for m in Z.finditer(t):
        w = t[max(0, m.start() - 250) : m.end() + 250]
        for g, pat in P.items():
            if re.search(pat, w, re.I if g not in ("PC", "PP", "PU") else 0):
                win_hits[g].add(pm)
print(f"{'polymer':9} {'xml_zeta±250ch':>15} {'d1_papers':>9} {'both':>5} {'xml_only':>8}")
for g in P:
    a, b = win_hits[g], d1[g]
    print(f"{g:9} {len(a):15} {len(b):9} {len(a & b):5} {len(a - b):8}")

json.dump({g: sorted(win_hits[g] - d1[g]) for g in P}, open(sys.argv[3], "w"), indent=1)
