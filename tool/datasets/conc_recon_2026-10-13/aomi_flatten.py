import glob
import json
import os
import sys

import pandas as pd

src, out = sys.argv[1], sys.argv[2]
rows = []
aliases = None
for fn in sorted(glob.glob(os.path.join(src, "p_*.json"))):
    d = json.load(open(fn))
    if "error" in d:
        print("ERR", fn, d["error"])
        continue
    if aliases is None:
        aliases = {f["name"]: f["alias"] for f in d["fields"]}
    print(fn, len(d["features"]), d.get("exceededTransferLimit"))
    rows += [f["attributes"] for f in d["features"]]
df = pd.DataFrame(rows).rename(columns=aliases)
for c in df.columns:
    if "Date" in c and df[c].dtype != object:
        df[c] = pd.to_datetime(df[c], unit="ms", errors="coerce")
df.to_csv(out, index=False)
print(len(df), df["0001:Data ID"].nunique())
