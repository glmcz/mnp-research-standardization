"""One table of survey records from four concentration datasets, every field as the source has it.

NCEI (marine water, beach, sediment), MP-SED (sediment), the soil compilation of Wu et al. and the
two PANGAEA Weser fractions are read through the pinned loaders of tool/p2, so this file holds no
path or checksum of its own. A field the source does not give stays null and is never filled;
`flags` says why a field is what it is (NCEI's 5 mm upper bound is the database's rule, MP-SED's
lower limit 99999 means unreported).

    uv run --with openpyxl python tool/survey/table.py   # writes data/interim/survey/records.csv.gz
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "tool" / "p2"))
import build as p2  # noqa: E402
import extension as ext  # noqa: E402

OUT = ROOT / "data/interim/survey/records.csv.gz"
COLUMNS = (
    "dataset",
    "record_id",
    "study",
    "org",
    "setting",
    "method",
    "region",
    "lat",
    "lon",
    "date",
    "year",
    "size_min_um",
    "size_max_um",
    "unit",
    "value",
    "flags",
)


def _blank(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().replace({"": None, "nan": None})


def ncei() -> pd.DataFrame:
    """Every NCEI record in the three settings that count particles in a volume or a mass."""
    d = pd.read_csv(p2.NCEI, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    d = d[d["Marine Setting"].isin(p2.NCEI_SETTINGS)]
    date = pd.to_datetime(d["Sample Date"], format="%m/%d/%Y %I:%M:%S %p")
    return pd.DataFrame(
        {
            "dataset": "ncei",
            "record_id": "ncei:" + d["Unique ID"],
            "study": _blank(d["DOI"]),
            "org": _blank(d["Organization"]),
            "setting": d["Marine Setting"],
            "method": _blank(d["Sampling Method"]),
            "region": _blank(d["Region"]),
            "lat": pd.to_numeric(d["Latitude (degree)"]),
            "lon": pd.to_numeric(d["Longitude (degree)"]),
            "date": date.dt.date.astype(str),
            "year": date.dt.year.astype(float),
            "size_min_um": pd.to_numeric(d["Mesh Size (mm)"], errors="coerce") * 1000,
            "size_max_um": p2.NCEI_UPPER_UM,
            "unit": d["Unit"],
            "value": pd.to_numeric(d["Microplastics Measurement"], errors="coerce"),
            "flags": "upper_by_database_rule",
        }
    )


def mpsed() -> pd.DataFrame:
    """MP-SED sediment records. No coordinates; the place is a water body in a country."""
    d = pd.DataFrame(json.loads(p2.MPSED.read_text(encoding="utf-8")))
    lim = d.mp_mdl.str.extract(r"^\s*([\d.]+)\s*-\s*([\d.]+)\s*$").astype(float)
    unknown = lim[0].eq(p2.MPSED_UNKNOWN_LOWER)
    return pd.DataFrame(
        {
            "dataset": "mpsed",
            "record_id": "mpsed:" + d["mpID"].astype(str),
            "study": _blank(d["DOI"]),
            "org": None,
            "setting": "sediment",
            "method": _blank(d["SampleMeth"]),
            "region": _blank(d["waterbody"]) + ", " + _blank(d["CountryName"]),
            "lat": np.nan,
            "lon": np.nan,
            "date": None,
            "year": d["SampleYearTime"].map(ext._year),
            "size_min_um": lim[0].where(~unknown),
            "size_max_um": lim[1],
            "unit": d["measure"],
            "value": pd.to_numeric(d["MP"], errors="coerce"),
            "flags": np.where(unknown, "lower_unreported_code", "") + "summ:" + d["SummStat"],
        }
    )


def soil() -> pd.DataFrame:
    """The soil compilation. A study is a paper title: the dataset has no DOI column."""
    s = ext.soil()
    return pd.DataFrame(
        {
            "dataset": "soil",
            "record_id": "soil:" + s.index.astype(str),
            "study": s["study"],
            "org": None,
            "setting": "soil",
            "method": None,
            "region": s["land_use"],
            "lat": s["lat"],
            "lon": s["lon"],
            "date": None,
            "year": s["year"],
            "size_min_um": s["lower_um"],
            "size_max_um": s["upper_um"],
            "unit": "items/kg",
            "value": s["conc"],
            "flags": "",
        }
    )


def weser() -> pd.DataFrame:
    """The Weser estuary: one study, two complementary size fractions at the same stations."""
    w, win = ext.weser()
    rows = []
    for frac, (lo, hi) in (("small", win["small_um"]), ("large", win["large_um"])):
        rows.append(
            pd.DataFrame(
                {
                    "dataset": "pangaea_weser",
                    "record_id": f"weser:{frac}:" + w["station"].astype(str),
                    "study": "PANGAEA 937685/938143 (Weser estuary)",
                    "org": None,
                    "setting": "river water",
                    "method": "pump" if frac == "small" else "net",
                    "region": w["location"],
                    "lat": np.nan,
                    "lon": np.nan,
                    "date": w["date"],
                    "year": pd.to_datetime(w["date"]).dt.year.astype(float),
                    "size_min_um": lo,
                    "size_max_um": hi,
                    "unit": "pieces/m3",
                    "value": w[frac],
                    "flags": f"fraction:{frac}",
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


def build() -> pd.DataFrame:
    p2.check_pins()
    ext.check_pins()
    t = pd.concat([ncei(), mpsed(), soil(), weser()], ignore_index=True)
    return t.loc[:, list(COLUMNS)]


def load() -> pd.DataFrame:
    """The table as last written; build it first if it is missing."""
    if not OUT.is_file():
        main()
    return pd.read_csv(OUT, dtype={"record_id": str, "study": str})


def main() -> None:
    t = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    t.to_csv(OUT, index=False)
    print(t.groupby(["dataset", "setting"]).size().to_string())
    print(f"wrote {OUT}, {len(t):,} records")


if __name__ == "__main__":
    main()
