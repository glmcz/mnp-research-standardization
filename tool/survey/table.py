"""One table of survey records from several datasets, every field as the source has it.

NCEI (marine water, beach, sediment), MP-SED (sediment), the soil compilation of Wu et al. and the
two PANGAEA Weser fractions are read through the pinned loaders of tool/p2. Datasets added after
P2 (EMODnet's European floating-microlitter monitoring, and the PANGAEA sets the dataset search
found) are pinned here. Air is not a survey matrix: an atmospheric compilation of one value per
study was read on 2026-10-23 and removed on 2026-10-24. On 2026-10-26 the Japanese ministry's
atlas (AOMI) replaced Isobe et al. 2021, 93 % of whose samples it holds, and two local datasets
whose records share no place with any other study left (Oregon rivers, California drinking
water); on 2026-10-28 two more left whose shared places hold no shared unit. A field the source
does not give stays null and is never filled. One value is not as the database has it: where a
database divides a tow's count by a net depth the paper contradicts, the paper's depth is used
(NET_DEPTH, flagged);
`flags` says why a field is what it is (NCEI's 5 mm upper bound is the database's rule, MP-SED's
lower limit 99999 means unreported).

    uv run --with openpyxl python tool/survey/table.py   # writes data/interim/survey/records.csv.gz
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import struct
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "tool" / "p2"))
import build as p2  # noqa: E402
import extension as ext  # noqa: E402

OUT = ROOT / "data/interim/survey/records.csv.gz"
CONC = ROOT / "data/raw/datasets_recon/conc"
EMODNET = CONC / "emodnet/mlf_density_nb_m3_monitoring.zip"  # EMODnet Chemistry, CC BY 4.0
PINS = {
    EMODNET: "243dc6c69a2fe70a995bff606680049d6ad6b52645fbf857064f505e2fae50f0",
}
DISCOVERED = ROOT / "data/raw/discover/files"
# Found by the scout agent (.claude/agents/mnp-dataset-scout.md, 2026-10-24) and opened by code
# (tool/discover/scout.py). Isobe et al. 2021, Microplastics and Nanoplastics 1:16: Level 0
# pieces/m3 per pelagic sample. Kiessling et al. 2021, Sci Total Environ 789:147849, supplement S4:
# German rivers sampled by school classes, meso- and microplastics per m3.
KIESSLING = DISCOVERED / "10.5281_zenodo.4600790" / "scout_1.xlsx"
# Fetched by Martin from his reference list on 2026-10-24 (tool/survey/fetch_user.py copies them
# here; RIVM's Git LFS files are fetched from GitHub there).
USER = ROOT / "data/raw/datasets_user"
DURUM = USER / "durum.xlsx"  # Database of Urban RUnoff Microplastics, 2018-2024
RIVM_TOTAL = USER / "rivm/Output/Data/2026-07-07Particle_concentrations_total.rds"
AOMI = USER / "aomi.csv"  # Atlas of Ocean Microplastics, Japan MOE, open-data layer (2026-10-26)
PINS |= {
    DURUM: "fb58bf5556284abd52dda126e5dd861e07b3c1ec47d9ffd10260ab48497aad72",
    RIVM_TOTAL: "c85e10a974515d797d1b91d7daead98217d3fe44ebe60d711b86db119c8a23bb",
    AOMI: "7aac3317b484c7db8bf637154a720d1453492896e1b9a5414862ae9651969d0d",
}
PINS[KIESSLING] = "5dea40db7cd2f90bce7dff97cbf26c647893ba4a0f2eb0bccb22ee1e12c1450a"
#: PANGAEA datasets the search agent found usable (tool/discover, 2026-10-23), each read with its
#: own concentration column. The size window is read from the dataset's own methods text.
PANGAEA_FOUND = {
    941076: {
        "setting": "Ocean water",
        "method": "net",
        "conc": "Microplastic [#/m**3]",
        "unit": "pieces/m3",
        "sha": "d255ac95cc51631545d5162288cccd7d18b13f3622b80a8789ae4017e8b66adf",
    },
    990052: {
        "setting": "Ocean water",
        "method": "pump",
        "conc": "Microplastic [#/m**3] (Fourier-transform infrared",
        "unit": "pieces/m3",
        "sha": "05fa0268ca424653f6c918a12c2c84e199a3e422d6918046710255912a19bad6",
    },
}
# Left out on 2026-10-26: PANGAEA 941107 (subsurface pump) and 928578 (sediment cores) are single
# cruises whose records share no place with any other study, so they compare nothing.
# Left out on 2026-10-28, once a place had to hold one unit too: PANGAEA 882220 (beach
# sediment per litre) and SFEI's San Francisco Bay (microparticles, plastic or not) share a
# place with other studies only in units no other study counts in.
# Left out, though verified usable: PANGAEA 986752 (Eastern Tropical Pacific) holds one row per
# particle, and its per-sample abundance differs within one site and month, so no single value per
# sample can be read without guessing. A lead for its author.
#: A database's pieces/m3 from a surface tow is the paper's pieces/km2 over a net depth the database
#: does not store. Where the paper states that depth and the database's values imply another, the
#: paper's stands. NCEI's Reisser 2013 Manta values equal Table S1's Cs / 1e6 / 0.085 for every
#: tow, yet no NCEI field holds 0.085 (Water Sample Depth is 0, and the submission sheet NCEI keyed
#: from the paper holds only the result); Reisser's Methods give 0.17 m, "full immersion of the net
#: frame". AOMI holds NCEI's values for the same tows. (study, method): (paper's m, implied m).
NET_DEPTH = {
    ("https://doi.org/10.1371/journal.pone.0080466", "Manta net"): (0.17, 0.085),
}
_WINDOW = (r"(\d+)\s*[µμ]m mesh", r"lower microplastic size limit was set to (\d+)\s*[µμ]m")
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


def dbf(raw: bytes) -> pd.DataFrame:
    """A dBase table (a shapefile's attributes) as strings. Field names are cut at 10 characters."""
    n, header, length = struct.unpack("<IHH", raw[4:12])
    fields, o = [], 32
    while raw[o] != 0x0D:
        fields.append((raw[o : o + 11].split(b"\0")[0].decode(), raw[o + 16]))
        o += 32
    rows = []
    for i in range(n):
        rec, p, row = raw[header + i * length + 1 : header + (i + 1) * length], 0, {}
        for name, width in fields:
            row[name] = rec[p : p + width].decode("latin-1").strip()
            p += width
        rows.append(row)
    return pd.DataFrame(rows)


def wkb_midpoint(hexstr: str) -> tuple[float, float]:
    """(lat, lon) halfway along a little-endian (E)WKB line, the tow's track; NaN if unreadable."""
    try:
        b = bytes.fromhex(hexstr)
        kind = struct.unpack("<I", b[1:5])[0]
        o = 9 if kind & 0x20000000 else 5  # an EWKB SRID adds four bytes
        k = struct.unpack("<I", b[o : o + 4])[0]
        pts = [struct.unpack("<2d", b[o + 4 + 16 * i : o + 20 + 16 * i]) for i in range(k)]
        lon, lat = np.mean([p[0] for p in pts]), np.mean([p[1] for p in pts])
        return float(lat), float(lon)
    except (ValueError, struct.error):
        return np.nan, np.nan


def emodnet() -> pd.DataFrame:
    """EMODnet floating micro-litter, monitoring nets, particles per m3 (European seas)."""
    d = dbf(zipfile.ZipFile(EMODNET).read("mlf_density_nb_m3_monitoring.dbf"))
    ll = d["geom_point"].map(wkb_midpoint)
    date = pd.to_datetime(d["date_obs"], errors="coerce")
    return pd.DataFrame(
        {
            "dataset": "emodnet",
            "record_id": "emodnet:" + d["id"],
            # A monitoring programme is one series, like an NCEI DOI: its cruises are not
            # independent studies of each other.
            "study": "EMODnet | " + _blank(d["originator"]),
            "org": _blank(d["originator"]),
            "setting": "Ocean water",
            "method": "net",
            "region": None,
            "lat": [x[0] for x in ll],
            "lon": [x[1] for x in ll],
            "date": date.dt.date.astype(str).where(date.notna()),
            "year": date.dt.year.astype(float),
            "size_min_um": pd.to_numeric(d["mesh_size_"], errors="coerce"),
            "size_max_um": 5000.0,
            "unit": "pieces/m3",
            "value": pd.to_numeric(d["density__2"], errors="coerce"),
            "flags": "upper_by_protocol",
        }
    )


def _pangaea_path(pid: int) -> Path:
    return DISCOVERED / f"10.1594_pangaea.{pid}" / f"pangaea_{pid}.tab"


def pangaea_found() -> pd.DataFrame:
    """The PANGAEA datasets the search agent verified, one record per sample."""
    parts = []
    for pid, spec in PANGAEA_FOUND.items():
        head, body = _pangaea_path(pid).read_text(encoding="utf-8").split("*/\n", 1)
        d = pd.read_csv(io.StringIO(body), sep="\t")
        conc = next(c for c in d.columns if c.startswith(spec["conc"]))
        date_col = next(c for c in d.columns if c.startswith("Date/Time"))
        lower = next((float(m.group(1)) for pat in _WINDOW if (m := re.search(pat, head))), np.nan)
        date = pd.to_datetime(d[date_col].astype(str), errors="coerce")
        parts.append(
            pd.DataFrame(
                {
                    "dataset": f"pangaea_{pid}",
                    "record_id": f"pangaea:{pid}:" + d.index.astype(str),
                    "study": f"10.1594/pangaea.{pid}",
                    "org": None,
                    "setting": spec["setting"],
                    "method": spec["method"],
                    "region": None,
                    "lat": pd.to_numeric(d["Latitude"], errors="coerce"),
                    "lon": pd.to_numeric(d["Longitude"], errors="coerce"),
                    "date": date.dt.date.astype(str).where(date.notna()),
                    "year": date.dt.year.astype(float),
                    "size_min_um": lower,
                    # A study that states only a lower limit counts up to 5 mm, the field's
                    # convention (the review call, 2026-10-10); NCEI applies the same rule.
                    "size_max_um": 5000.0 if np.isfinite(lower) else np.nan,
                    "unit": spec["unit"],
                    "value": pd.to_numeric(d[conc], errors="coerce"),
                    "flags": "found_by_search_agent"
                    + (";upper_by_convention" if np.isfinite(lower) else ";window_unreported"),
                }
            )
        )
    return pd.concat(parts, ignore_index=True)


def kiessling2021() -> pd.DataFrame:
    """Rivers sampled by school classes: meso- and microplastics together, per m3."""
    d = pd.read_excel(KIESSLING, sheet_name="SamplingSites_and_LitterData")
    date = pd.to_datetime(d["Sampling_date"], errors="coerce")
    return pd.DataFrame(
        {
            "dataset": "kiessling2021",
            "record_id": "kiessling2021:" + d["Dataset_number"].astype(str),
            "study": "10.1016/j.scitotenv.2021.147849",
            "org": None,
            "setting": "river water",
            "method": "net",
            "region": d["Sampling_River"].astype(str),
            "lat": pd.to_numeric(d["Coordinates_Latitude_approximate"], errors="coerce"),
            "lon": pd.to_numeric(d["Coordinates_Longitude_approximate"], errors="coerce"),
            "date": date.dt.date.astype(str).where(date.notna()),
            "year": date.dt.year.astype(float),
            "size_min_um": np.nan,
            "size_max_um": np.nan,
            "unit": "pieces/m3",
            "value": pd.to_numeric(d["FloatingMesoplasticsMicroplastics_m-3"], errors="coerce"),
            "flags": "found_by_scout;window_unreported;includes_mesoplastics;"
            "coordinates_approximate",
        }
    )


def _first_year(text) -> float:
    m = re.search(r"(?:19|20)\d\d", str(text))
    return float(m.group(0)) if m else np.nan


def durum() -> pd.DataFrame:
    """Urban stormwater runoff, one row per sampling effort, in the units DURUM standardised."""
    d = pd.read_excel(DURUM)
    date = pd.to_datetime(d["Date"], errors="coerce")
    return pd.DataFrame(
        {
            "dataset": "durum",
            "record_id": "durum:" + d["ID"].astype(str),
            "study": d["DOI"].astype(str),
            "org": None,
            "setting": "stormwater runoff",
            "method": d["Sampling method (standardized)"],
            "region": d["Country"],
            "lat": pd.to_numeric(d["Decimal Latitude"], errors="coerce"),
            "lon": pd.to_numeric(d["Decimal Longitude"], errors="coerce"),
            # "01/19/2023 and 07/14/2023" is two dates; only a single one is a date
            "date": date.dt.date.astype(str).where(date.notna()),
            "year": date.dt.year.where(date.notna(), d["Date"].map(_first_year)).astype(float),
            "size_min_um": pd.to_numeric(d["x1M_um"], errors="coerce"),
            "size_max_um": pd.to_numeric(d["x2M_um"], errors="coerce"),
            "unit": "particles/L",
            "value": pd.to_numeric(d["Standardized Concentration (particles/L)"], errors="coerce"),
            "flags": "provided_by_martin;one_row_per_sampling_effort",
        }
    )


def rivm() -> pd.DataFrame:
    """Dutch surface waters as RIVM harmonised them (report 2026-0069), one row per sample."""
    import pyreadr

    d = pyreadr.read_r(RIVM_TOTAL)[None]
    text = d["sampling_date"].astype(str)
    no_century = text.str.match(r"^00\d\d-")  # "0016-09-20": the century is not printed
    date = pd.to_datetime(text.where(~no_century), errors="coerce")
    return pd.DataFrame(
        {
            "dataset": "rivm",
            "record_id": "rivm:" + d["Sample_ID"].astype(str),
            "study": d["DOI"].fillna(d["Data_source"]).astype(str),
            "org": None,
            "setting": "river water",
            "method": d["Sampling_method"],
            "region": d["River"],
            "lat": pd.to_numeric(d["Latitude"], errors="coerce"),
            "lon": pd.to_numeric(d["Longitude"], errors="coerce"),
            "date": date.dt.date.astype(str).where(date.notna()),
            "year": date.dt.year.astype(float),
            "size_min_um": pd.to_numeric(d["Lower_sampling_size_limit_um"], errors="coerce"),
            "size_max_um": pd.to_numeric(d["Upper_sampling_size_limit_um"], errors="coerce"),
            "unit": "pieces/m3",
            "value": pd.to_numeric(d["concentration"], errors="coerce"),
            "flags": np.where(no_century, "provided_by_martin;date_without_century",
                              "provided_by_martin"),
        }
    )  # fmt: skip


def aomi() -> pd.DataFrame:
    """AOMI, the Japanese environment ministry's atlas: surface tows from many contributors,
    NOAA's among them. Particles per m3 under 5 mm; the net's mesh is the lower limit.

    A study is its DOI, else its reference, else its organisation, prefixed so that the same
    paper held by AOMI and by NCEI counts as two holdings, which the duplicate check then finds.
    """
    d = pd.read_csv(AOMI, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    lat = pd.to_numeric(d["latitude"], errors="coerce")
    lat = lat.where(lat.abs() < 89.9)  # a pole is the atlas's placeholder for a missing position
    date = pd.to_datetime(pd.to_numeric(d["D01_0033"], errors="coerce"), unit="ms")
    study = _blank(d["D01_0016"]).fillna(_blank(d["D01_0014"])).fillna(_blank(d["D01_0009"]))
    mesh_um = pd.to_numeric(d["D01_0070"], errors="coerce") * 1000
    return pd.DataFrame(
        {
            "dataset": "aomi",
            "record_id": "aomi:" + d["D01_0001"],
            "study": "aomi:" + study,
            "org": _blank(d["D01_0009"]),
            "setting": "Ocean water",
            "method": _blank(d["D01_0056"]),
            "region": None,
            "lat": lat,
            "lon": pd.to_numeric(d["longitude"], errors="coerce").where(lat.notna()),
            "date": date.dt.date.astype(str).where(date.notna()),
            "year": date.dt.year.astype(float),
            "size_min_um": mesh_um,
            "size_max_um": 5000.0,
            "unit": "pieces/m3",
            "value": pd.to_numeric(d["D01_0192"], errors="coerce"),
            "flags": "provided_by_martin;upper_by_layer"
            + np.where(mesh_um.isna(), ";window_unreported", ""),
        }
    )


def check_pins() -> None:
    for pid, spec in PANGAEA_FOUND.items():
        got = hashlib.sha256(_pangaea_path(pid).read_bytes()).hexdigest()
        if got != spec["sha"]:
            raise SystemExit(f"PANGAEA {pid}: sha256 {got} != pinned {spec['sha']}")
    for path, want in PINS.items():
        got = hashlib.sha256(path.read_bytes()).hexdigest()
        if got != want:
            raise SystemExit(f"{path}: sha256 {got} != pinned {want}")


def build() -> pd.DataFrame:
    p2.check_pins()
    ext.check_pins()
    check_pins()
    parts = [ncei(), mpsed(), soil(), weser(), emodnet(), pangaea_found(), aomi(),
             kiessling2021(), durum(), rivm()]  # fmt: skip
    t = pd.concat(parts, ignore_index=True)
    return paper_depth(t).loc[:, list(COLUMNS)]


def paper_depth(t: pd.DataFrame) -> pd.DataFrame:
    """Rescale each NET_DEPTH study's tows to the paper's depth, in every database holding them."""
    study = t.study.str.removeprefix("aomi:")
    for (doi, method), (paper, implied) in NET_DEPTH.items():
        m = (study == doi) & (t.method == method)
        t.loc[m, "value"] = t.loc[m, "value"] * implied / paper
        t.loc[m, "flags"] = t.loc[m, "flags"] + f";depth_from_paper_{paper}m_not_{implied}m"
    return t


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
