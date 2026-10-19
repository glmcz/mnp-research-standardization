"""Print sheets, headers and the first rows of an xlsx.

Usage: python -I peek_xlsx.py <xlsx> [nrows]
"""

import sys

import pandas as pd

n = int(sys.argv[2]) if len(sys.argv) > 2 else 8
pd.set_option("display.width", 300)
pd.set_option("display.max_columns", 50)
for name, df in pd.read_excel(sys.argv[1], sheet_name=None, header=None).items():
    print(f"=== sheet {name!r} shape {df.shape}")
    print(df.head(n).to_string())
