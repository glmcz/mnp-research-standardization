import sys
import pandas as pd
df = pd.read_csv(sys.argv[1], low_memory=False)
print(len(df), 'rows')
for c in ['Lat','Lon','Year','km2','Mesh.Size','CutOff','TopLim','CorrectedConcentration','Source']:
    print(c, df[c].notna().sum())
print(df['Source'].value_counts().head(30))
print(df['Mesh.Size'].value_counts().head(8))
print('CutOff', df['CutOff'].value_counts(dropna=False).head(8))
print('TopLim', df['TopLim'].value_counts(dropna=False).head(8))
print('years', df['Year'].min(), df['Year'].max())
print(df['km2'].describe())
