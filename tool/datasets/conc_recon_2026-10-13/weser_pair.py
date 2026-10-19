import io
import sys

import pandas as pd


def load(fn):
    t = open(fn, encoding="utf-8").read().split("*/\n", 1)[1]
    return pd.read_csv(io.StringIO(t), sep="\t")


small, large = load(sys.argv[1]), load(sys.argv[2])
small["st"] = small["Event"].str.split("_").str[-1]
large["st"] = large["Event"].str.split("_").str[-1]
m = small.merge(large, on="st", suffixes=("_s", "_l"))
m["ratio"] = m["Microplastic [#/m**3]_s"] / m["Microplastic [#/m**3]_l"]
print(len(small), len(large), "paired", len(m))
print(
    m[
        [
            "st",
            "Location_s",
            "Date/Time_s",
            "Date/Time_l",
            "Microplastic [#/m**3]_s",
            "Microplastic [#/m**3]_l",
            "ratio",
        ]
    ]
    .head(5)
    .to_string()
)
print("ratio median", m["ratio"].median(), "min", m["ratio"].min(), "max", m["ratio"].max())
