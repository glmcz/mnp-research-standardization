import sys, re, pandas as pd
pd.set_option('display.width', 250); pd.set_option('display.max_colwidth', 80)
for f, zc, mc in ((sys.argv[1], 'zetapotential.mV', 'zetapotential.media'), (sys.argv[2], 'zetapotential', 'zeta.potential.media')):
    d = pd.read_csv(f, dtype=str, low_memory=False, encoding='latin-1')
    print('=====', f.split('/')[-1], d.shape)
    cols = list(d.columns)
    print([c for c in cols if re.search(r'poly|size|shape|doi|year|source|authors|media|charge|functional|ph\b|salin|study', c, re.I)])
    z = d[zc].fillna('').str.strip()
    has = d[(z != '') & ~z.str.lower().isin(['n/a','na','not reported','nr','none'])]
    print('rows with zeta:', len(has), 'of', len(d))
    print('distinct zeta strings sample:', has[zc].drop_duplicates().head(25).tolist())
    pc = 'poly' if 'poly' in cols else [c for c in cols if 'poly' in c.lower()][0]
    key = [c for c in ('doi','source','article') if c in cols]
    print('key cols', key, 'polymer col', pc)
    dcol = key[0]
    print('studies total:', d[dcol].nunique(), 'studies with zeta:', has[dcol].nunique())
    u = has.drop_duplicates([dcol, pc, zc])
    print('distinct (study, polymer, zeta) combos:', len(u))
    print(u.groupby(pc).agg(values=(zc,'size'), studies=(dcol,'nunique')).sort_values('values', ascending=False).to_string())
    print('media:', has.drop_duplicates([dcol, zc])[mc].fillna('').value_counts().head(20).to_string())
    print('charge col:', d['charge'].fillna('').value_counts().head(8).to_string())
    print('functional.group:', has['functional.group'].fillna('').value_counts().head(8).to_string())
