import json, sys, time, urllib.parse, urllib.request, collections
rows = json.load(open(sys.argv[1]))
by = collections.defaultdict(set)
for r in rows:
    for p in r['new_pmcids']: by[p].add(r['frame'][:4] + ':' + r['polymer'])
mnp = sorted(p for p, s in by.items() if any(x.startswith('mnp') for x in s))
print('union new OA PMCIDs, mnp frame:', len(mnp), ' particle frame:', sum(1 for s in by.values() if any(x.startswith('part') for x in s)), ' all:', len(by))
for i in range(0, len(mnp), 40):
    q = ' OR '.join(f'PMCID:{p}' for p in mnp[i:i+40])
    u = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search?' + urllib.parse.urlencode(dict(query=q, format='json', pageSize=100, resultType='lite'))
    for r in json.load(urllib.request.urlopen(u, timeout=60))['resultList']['result']:
        print(r.get('pmcid'), r.get('firstPublicationDate'), r.get('pubType','')[:20], '|', ','.join(sorted(by[r['pmcid']])), '|', r.get('title','')[:110])
    time.sleep(0.4)
