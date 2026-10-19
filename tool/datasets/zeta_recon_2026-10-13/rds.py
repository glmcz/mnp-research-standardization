import sys, rdata, pandas as pd
pd.set_option('display.width', 250)
for f in sys.argv[1:]:
    try:
        obj = rdata.read_rds(f, default_encoding='utf8')
    except Exception as e:
        print('FAIL', f, repr(e)[:300]); continue
    print('=====', f.split('/')[-1], type(obj))
    if isinstance(obj, pd.DataFrame):
        cols = list(obj.columns)
        print(obj.shape)
        print([c for c in cols if any(k in c.lower() for k in ('zeta','charge','functional','poly','doi','size.length','media','source','year','authors'))])
        obj.to_pickle(f + '.pkl')
