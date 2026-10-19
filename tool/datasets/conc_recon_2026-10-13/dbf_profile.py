import sys
from dbfread import DBF
import pandas as pd
for fn in sys.argv[1:]:
    df = pd.DataFrame(iter(DBF(fn, encoding='latin-1')))
    print('=====', fn, len(df), list(df.columns))
    print(df.head(3).to_string()[:1500])
    for c in df.columns:
        if df[c].nunique() < 15: print(c, df[c].value_counts().to_dict())
