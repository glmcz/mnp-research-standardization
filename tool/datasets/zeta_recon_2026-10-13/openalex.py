import json
import os
import sys
import time
import urllib.parse
import urllib.request

ROOT = sys.argv[1]
OUT = sys.argv[2]
xml = {f[:-4] for f in os.listdir(os.path.join(ROOT, "data/raw/epmc/xml")) if f.endswith(".xml")}
sdoi = set()
for line in open(os.path.join(ROOT, "data/raw/epmc/search/search.jsonl")):
    r = json.loads(line)
    if r.get("doi"):
        sdoi.add(r["doi"].lower())
ZETA = '("zeta potential" OR "electrophoretic mobility")'
MNP = "(microplastic OR microplastics OR nanoplastic OR nanoplastics)"
POLY = {
    "nylon/PA": "(nylon OR polyamide)",
    "PVC": '("polyvinyl chloride" OR PVC)',
    "PP": "polypropylene",
    "PLA": '("polylactic acid" OR polylactide OR PLA)',
    "PBAT": '(PBAT OR "polybutylene adipate terephthalate")',
    "PU": "polyurethane",
    "tyre": '("tire wear" OR "tyre wear" OR "tire particles" OR "tyre particles" OR "crumb rubber" OR TRWP)',
    "PET": '("polyethylene terephthalate" OR PET)',
    "PMMA": '("polymethyl methacrylate" OR PMMA)',
    "PC": "polycarbonate",
}
FILT = "publication_year:2015-2026,type:article"


def get(params):
    u = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    for k in range(4):
        try:
            j = json.load(urllib.request.urlopen(u, timeout=60))
            time.sleep(0.25)
            return j
        except Exception as e:
            time.sleep(2 + 3 * k)
            last = e
    raise last


rows = []
for p, t in POLY.items():
    q = f"{t} AND {ZETA} AND {MNP}"
    n_all = get(dict(search=q, filter=FILT, per_page=1))["meta"]["count"]
    n_ta = get({"filter": FILT + ",title_and_abstract.search:" + q, "per_page": 1})["meta"]["count"]
    recs, cur = [], "*"
    while cur:
        j = get(
            dict(
                search=q,
                filter=FILT + ",is_oa:true",
                per_page=200,
                cursor=cur,
                select="id,doi,ids,publication_year",
            )
        )
        recs += j["results"]
        cur = j["meta"].get("next_cursor")
        if not j["results"] or len(recs) >= 2000:
            break
    n_oa = j["meta"]["count"]

    def doi(r):
        return (r.get("doi") or "").lower().replace("https://doi.org/", "")

    not_in = [r for r in recs if doi(r) not in sdoi]
    pmc_new = [r for r in not_in if (r.get("ids") or {}).get("pmcid")]
    row = dict(
        source="OpenAlex",
        polymer=p,
        hits_fulltext=n_all,
        hits_title_abstract=n_ta,
        oa=n_oa,
        oa_doi_not_in_1115=len(not_in),
        oa_not_in_1115_with_pmcid=len(pmc_new),
        query=q,
        filter=FILT,
        new_dois=[doi(r) for r in not_in],
    )
    rows.append(row)
    print(json.dumps({k: v for k, v in row.items() if k != "new_dois"}), flush=True)
json.dump(rows, open(OUT, "w"), indent=1)
