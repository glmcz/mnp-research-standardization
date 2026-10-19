import json, os, sys, time, urllib.parse, urllib.request
ROOT = sys.argv[1]; OUT = sys.argv[2]
xml = {f[:-4] for f in os.listdir(os.path.join(ROOT, 'data/raw/epmc/xml')) if f.endswith('.xml')}
search_pmc, search_doi = set(), set()
for line in open(os.path.join(ROOT, 'data/raw/epmc/search/search.jsonl')):
    r = json.loads(line)
    if r.get('pmcid'): search_pmc.add(r['pmcid'])
    if r.get('doi'): search_doi.add(r['doi'].lower())

ZETA = '("zeta potential" OR "electrophoretic mobility")'
MNP = '(microplastic* OR nanoplastic* OR "plastic particle*" OR "plastic debris")'
YR = 'PUB_YEAR:[2015 TO 2026] AND NOT PUB_TYPE:"review"'
POLY = {
 'nylon/PA': '(nylon* OR polyamide*)',
 'PVC': '("polyvinyl chloride" OR "poly vinyl chloride" OR PVC)',
 'PP': '(polypropylene)',
 'PLA': '("polylactic acid" OR "poly lactic acid" OR polylactide OR PLA)',
 'PBAT': '(PBAT OR "polybutylene adipate terephthalate" OR "poly butylene adipate co terephthalate")',
 'PU': '(polyurethane*)',
 'tyre': '("tire wear" OR "tyre wear" OR "tire particle*" OR "tyre particle*" OR "tire rubber" OR "tyre rubber" OR "crumb rubber" OR TRWP)',
 'PET': '("polyethylene terephthalate" OR PET)',
 'PMMA': '("polymethyl methacrylate" OR "poly methyl methacrylate" OR PMMA)',
 'PC': '(polycarbonate*)',
}
# particle-framed, no MNP word required: catches papers that call them polymer particles
def ph(names, nouns=('particle*','microparticle*','nanoparticle*','microsphere*','powder')):
    return '(' + ' OR '.join(f'"{n} {x}"' for n in names for x in nouns) + ')'
PART = {
 'nylon/PA': ph(['nylon','polyamide']),
 'PVC': ph(['PVC','polyvinyl chloride']),
 'PP': ph(['polypropylene']),
 'PLA': ph(['PLA','polylactic acid','polylactide']),
 'PBAT': ph(['PBAT']),
 'PU': ph(['polyurethane']),
 'tyre': '("tire wear particle*" OR "tyre wear particle*" OR "tire particle*" OR "tyre particle*" OR "tire rubber particle*" OR "tyre rubber particle*" OR "crumb rubber" OR "tire road wear" OR "tyre road wear")',
}
def epmc(q):
    out, cur = [], '*'
    while True:
        u = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search?' + urllib.parse.urlencode(
            dict(query=q, format='json', pageSize=1000, resultType='lite', cursorMark=cur))
        j = json.load(urllib.request.urlopen(u, timeout=60)); time.sleep(0.4)
        res = j['resultList']['result']; out += res
        nc = j.get('nextCursorMark')
        if not res or nc == cur or len(out) >= j['hitCount']: return j['hitCount'], out
        cur = nc
def summarise(label, poly, q):
    n_all, _ = epmc(q)
    n_oa, recs = epmc(q + ' AND OPEN_ACCESS:y')
    pmc = {r['pmcid'] for r in recs if r.get('pmcid')}
    new_fetch = pmc - xml
    new_search = pmc - search_pmc
    row = dict(source='EPMC', frame=label, polymer=poly, hits=n_all, oa=n_oa, oa_pmcids=len(pmc),
               oa_not_fetched=len(new_fetch), oa_not_in_1115=len(new_search), query=q)
    row['new_pmcids'] = sorted(new_fetch)
    return row
rows = []
for p, t in POLY.items():
    rows.append(summarise('mnp', p, f'{t} AND {ZETA} AND {MNP} AND {YR}')); print(json.dumps({k:v for k,v in rows[-1].items() if k!='new_pmcids'}), flush=True)
for p, t in PART.items():
    rows.append(summarise('particle_no_mnp_word', p, f'{t} AND {ZETA} AND NOT {MNP} AND {YR}')); print(json.dumps({k:v for k,v in rows[-1].items() if k!='new_pmcids'}), flush=True)
json.dump(rows, open(OUT, 'w'), indent=1)
