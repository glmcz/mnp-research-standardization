import json
import os
import random
import re
import sys

XML = sys.argv[1]
cand = json.load(open(sys.argv[2]))
P = {
    "nylon/PA": r"\bnylon|polyamide|\bPA ?6|\bPA\b",
    "PVC": r"\bPVC\b|vinyl chloride",
    "PP": r"polypropylene|\bPP\b",
    "PLA": r"polylactic|poly\(lactic|polylactide|\bPLA\b",
    "PET": r"terephthalate|\bPET\b",
    "PMMA": r"methyl methacrylate|methacrylate\)|\bPMMA\b",
    "PC": r"polycarbonate|\bPC\b(?!\d)",
    "PU": r"polyurethane|\bPUR?\b",
}
LAB = re.compile(
    r"(filter|membrane|syringe|mesh|tube|container|bottle|vial|cuvette|plate|cell|dish|bag|centrifuge|capillar)",
    re.I,
)
Z = re.compile(r"zeta|ζ|electrophoretic mobilit", re.I)
random.seed(0)
for g, ids in cand.items():
    if g not in P:
        continue
    keep = []
    for pm in ids:
        t = open(os.path.join(XML, pm + ".xml"), encoding="utf-8", errors="replace").read()
        b = t.find("<body")
        t = t[b:] if b > 0 else t
        t = re.sub(r"<ref-list.*", "", t, flags=re.S)
        t = re.sub(r"<[^>]+>", " ", t)
        t = re.sub(r"\s+", " ", t)
        good = []
        for m in Z.finditer(t):
            w = t[max(0, m.start() - 250) : m.end() + 250]
            for pm2 in re.finditer(P[g], w, 0 if g in ("PC", "PP", "PU") else re.I):
                after = w[pm2.end() : pm2.end() + 25]
                if not LAB.search(after):
                    good.append(w)
        if good:
            keep.append((pm, good[0]))
    print(f"== {g}: xml_only {len(ids)}, after dropping lab-ware mentions {len(keep)}")
    for pm, w in random.sample(keep, min(3, len(keep))):
        print("  ", pm, "::", w[:300].replace("\n", " "))
