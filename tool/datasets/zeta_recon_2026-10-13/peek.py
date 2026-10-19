import sys, pandas as pd
df = pd.read_csv(sys.argv[1], dtype=str)
print(len(df))
print(df['material'].value_counts().head(60).to_string())
print(df['quantity'].value_counts().to_string())
print(df['unit'].value_counts().to_string())
fl = df['flags'].fillna('')
import collections
c = collections.Counter(t for f in fl for t in f.replace(';','|').replace(',','|').split('|') if t)
print(c.most_common(30))
print(df['evidence_location'].dropna().sample(30, random_state=1).to_string())
