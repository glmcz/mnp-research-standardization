import sys, json, pandas as pd
corp = set()
for line in open(sys.argv[3]):
    r = json.loads(line)
    if r.get('doi'): corp.add(r['doi'].lower().strip())
for f, zc in ((sys.argv[1], 'zetapotential.mV'), (sys.argv[2], 'zetapotential')):
    d = pd.read_csv(f, dtype=str, low_memory=False, encoding='latin-1')
    d.columns = [c.replace('ï»¿','') for c in d.columns]
    print('=====', f.split('/')[-1], 'sources', d['source'].nunique(), 'dois', d['doi'].nunique())
    print('polymers overall:', d.polymer.value_counts().head(25).to_dict())
    z = d[zc].fillna('').str.strip(); h = d[z != '']
    print('zeta by source:', h['source'].nunique())
    u = h.drop_duplicates(['source','polymer',zc])
    print(u[u.polymer!='PS'][['source','doi','polymer',zc]].to_string())
    dois = {x.lower().strip().replace('https://doi.org/','') for x in h.doi.dropna()}
    print('zeta studies (doi) in our 1115 search set:', len(dois & corp), 'of', len(dois))
