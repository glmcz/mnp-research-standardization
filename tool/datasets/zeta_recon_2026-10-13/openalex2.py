import json, os, sys, time, urllib.parse, urllib.request
ROOT = sys.argv[1]; OUT = sys.argv[2]
sdoi = set()
for line in open(os.path.join(ROOT, 'data/raw/epmc/search/search.jsonl')):
    r = json.loads(line)
    if r.get('doi'): sdoi.add(r['doi'].lower())
MNP = '(microplastic OR microplastics OR nanoplastic OR nanoplastics OR "plastic particles")'
POLY = {
 'nylon/PA': '(nylon OR polyamide)', 'PVC': '("polyvinyl chloride" OR PVC)', 'PP': 'polypropylene',
 'PLA': '("polylactic acid" OR polylactide OR PLA)', 'PBAT': '(PBAT OR "polybutylene adipate terephthalate")',
 'PU': 'polyurethane', 'tyre': '("tire wear" OR "tyre wear" OR "tire particles" OR "tyre particles" OR "crumb rubber" OR TRWP)',
 'PET': '("polyethylene terephthalate" OR PET)', 'PMMA': '("polymethyl methacrylate" OR PMMA)', 'PC': 'polycarbonate',
}
FT = '("zeta potential" OR "electrophoretic mobility")'
def get(params):
    u = 'https://api.openalex.org/works?' + urllib.parse.urlencode(params, safe=':,')
    for k in range(4):
        try:
            j = json.load(urllib.request.urlopen(u, timeout=60)); time.sleep(0.25); return j
        except Exception as e:
            time.sleep(2 + 3 * k); last = e
    raise last
def epmc_oa_pmc(dois):
    found = {}
    for i in range(0, len(dois), 25):
        q = ' OR '.join(f'DOI:"{d}"' for d in dois[i:i+25])
        u = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search?' + urllib.parse.urlencode(dict(query=q, format='json', pageSize=100, resultType='lite'))
        for r in json.load(urllib.request.urlopen(u, timeout=60))['resultList']['result']:
            if r.get('doi'): found[r['doi'].lower()] = (r.get('pmcid'), r.get('isOpenAccess'))
        time.sleep(0.4)
    return found
rows = []
for p, t in POLY.items():
    base = f'publication_year:2015-2026,type:article,title_and_abstract.search:{t} AND {MNP},fulltext.search:{FT}'
    recs, cur = [], '*'
    while cur:
        j = get(dict(filter=base, per_page=200, cursor=cur, select='id,doi,publication_year,open_access'))
        recs += j['results']; cur = j['meta'].get('next_cursor')
        if not j['results']: break
    n = j['meta']['count']
    def doi(r): return (r.get('doi') or '').lower().replace('https://doi.org/', '')
    oa = [r for r in recs if (r.get('open_access') or {}).get('is_oa')]
    new = [doi(r) for r in recs if doi(r) and doi(r) not in sdoi]
    new_oa = [doi(r) for r in oa if doi(r) and doi(r) not in sdoi]
    m = epmc_oa_pmc(new_oa)
    in_pmc_oa = [d for d in new_oa if m.get(d, (None, None))[0] and m[d][1] == 'Y']
    row = dict(polymer=p, hits=n, oa=len(oa), not_in_1115=len(new), oa_not_in_1115=len(new_oa), oa_not_in_1115_pmc_oa=len(in_pmc_oa),
               filter=base, new_oa_dois=new_oa, pmc_oa=[m[d][0] for d in in_pmc_oa])
    rows.append(row); print(json.dumps({k: v for k, v in row.items() if k not in ('new_oa_dois',)}), flush=True)
json.dump(rows, open(OUT, 'w'), indent=1)
