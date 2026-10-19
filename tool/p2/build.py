"""P2: zeta against particle size, and microplastic datasets by place, size window and date.

Two questions from the 2026-10-10 review call (docs/2026-10-10-review-call.md, items 11–12):
does zeta follow particle size once 1 000 literature values are pooled, and how do
concentration studies compare when each counts a different size window at a different place
and time?

uv run --with openpyxl python tool/p2/prereg.py   # first: the pre-registered tests
uv run --with openpyxl python tool/p2/build.py    # tool/p2/data.json, p2.html, out/tables/p2_*.csv
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "tool" / "viz"))
sys.path.insert(0, str(HERE))
import extension as ext  # noqa: E402
from build_page import inline  # noqa: E402

D1 = ROOT / "out/tables/d1_zeta_table.csv"
NCEI = ROOT / "data/raw/ncei/ncei_hub_microplastics.csv"
MPSED = ROOT / "data/raw/mpsed/data.json"
LAND = HERE / "land-110m.json"
CASE_TOWS = ROOT / "tool/colocation/reisser_eriksen/out_2026-10-12/tow_identity_R_E.csv"
PINS = {
    NCEI: "31bb1efdc948a4ee4d71c80df4e56d50c26e1b3905c1162139681d2ddc6bb5c5",
    MPSED: "4896ca98df537ab0ed6bf56360dfe3f4235261f241d117e289f8ee4dac706d74",
    LAND: "ead5f68119c49a9250902e7da303bcb209341bbb8fefe7369a439b48b704658a",
}

# NCEI keeps only pieces under 5 mm (Nyadjro et al. 2023, Sci Data, PMC10589325, Methods), so
# 5 mm is every NCEI record's upper bound. It is the database's rule, not a per-study statement.
NCEI_UPPER_UM = 5000.0
NCEI_SETTINGS = (
    "Ocean water",
    "Beach",
    "Ocean sediment",
)  # Nurdle Patrol counts pellets per 10 min
MPSED_UNKNOWN_LOWER = 99999  # MP-SED's code for "lower size limit not reported"
CASE_DOIS = {
    "https://doi.org/10.1371/journal.pone.0080466": "Reisser 2013",
    "https://doi.org/10.1371/journal.pone.0111913": "Eriksen 2014",
}


def check_pins() -> None:
    for path, want in PINS.items():
        got = hashlib.sha256(path.read_bytes()).hexdigest()
        if got != want:
            raise SystemExit(
                f"{path}: sha256 {got} != pinned {want}; refetch per tool/colocation/README.md"
            )


def surface_group(text: str) -> str:
    t = text.lower()
    if re.search(r"amin|nh2|nh3", t):
        return "amine"
    if re.search(r"carbox|cooh", t):
        return "carboxyl"
    if re.search(r"sulf|sulph", t):
        return "sulfate"
    if re.search(r"unmod|pristine|plain|bare|virgin|^none$|non-functional", t):
        return "plain"
    return "unreported"


def material_group(text: str) -> str:
    t = text.lower()
    for key, pat in (
        ("PS", r"polystyren"),
        ("PE", r"polyethylene(?! tere)|\bhdpe\b|\bldpe\b|\bpe\b"),
        ("PET", r"terephthal|\bpet\b"),
        ("PP", r"polypropyl|\bpp\b"),
        ("PVC", r"vinyl chlor|\bpvc\b"),
        ("PMMA", r"methacryl|\bpmma\b"),
    ):
        if re.search(pat, t):
            return key
    if re.search(r"hybrid|composite", t):  # e.g. "polylactic acid / chitosan hybrid"
        return "other"
    for key, pat in (
        ("nylon", r"nylon|polyamide"),
        ("PLA", r"polylactic|\bpla\b"),
        ("PBAT", r"\bpbat\b|butylene adipate"),
    ):
        if re.search(pat, t):
            return key
    return "other"


def spearman(x, y) -> dict:
    r = spearmanr(x, y)
    return {"rho": round(float(r.statistic), 2), "p": float(f"{r.pvalue:.2g}"), "n": int(len(x))}


def zeta_size() -> tuple[pd.DataFrame, dict]:
    d = pd.read_csv(D1)
    d = d[d.value.notna() & d.quantity.eq("zeta_potential") & d.unit.eq("mV")].copy()
    # Nominal size names the particle; measured size can include aggregates (PMC10260929 Table 1
    # grows from 119.5 to 250.5 nm with salt), so it is the fallback, and the kind is kept.
    d["size_nm"] = d.size_nominal_nm.fillna(d.size_measured_nm)
    d["size_kind"] = np.where(d.size_nominal_nm.notna(), "nominal", "measured")
    d = d[d.size_nm.gt(0)]
    d["surface"] = d.functionalisation.fillna("").map(surface_group)
    d["material_group"] = d.material.fillna("").map(material_group)
    t = d[
        [
            "pmcid",
            "row_id",
            "material",
            "material_group",
            "functionalisation",
            "surface",
            "size_nm",
            "size_kind",
            "value",
            "medium_class",
            "pH",
        ]
    ].rename(columns={"value": "zeta_mV"})
    t = t.sort_values(["pmcid", "row_id"]).reset_index(drop=True)

    ps = t[t.material_group.eq("PS")]
    by_surface = {}
    for g, x in ps.groupby("surface"):
        by_surface[g] = {
            "rows": len(x),
            "papers": x.pmcid.nunique(),
            "median_mV": round(float(x.zeta_mV.median()), 1),
            **({"spearman": spearman(np.log10(x.size_nm), x.zeta_mV)} if len(x) >= 15 else {}),
        }
    amine = ps[ps.surface.eq("amine")]
    amine_by_medium = {
        m: {
            "rows": len(x),
            "papers": x.pmcid.nunique(),
            "median_mV": round(float(x.zeta_mV.median()), 1),
            "positive": int((x.zeta_mV > 0).sum()),
            "negative": int((x.zeta_mV < 0).sum()),
        }
        for m, x in amine.groupby("medium_class")
    }
    by_polymer = []
    for g, x in t.groupby("material_group"):
        q = x.zeta_mV.quantile
        by_polymer.append(
            {
                "polymer": g,
                "rows": len(x),
                "papers": x.pmcid.nunique(),
                "zeta_p10": round(float(q(0.1)), 1),
                "zeta_median": round(float(q(0.5)), 1),
                "zeta_p90": round(float(q(0.9)), 1),
                "size_median_nm": round(float(x.size_nm.median())),
                "nano_share": round(float((x.size_nm < 1000).mean()), 2),
                "positive": int((x.zeta_mV > 0).sum()),
                "top_paper_rows": int(x.pmcid.value_counts().iat[0]),
                **({"spearman": spearman(np.log10(x.size_nm), x.zeta_mV)} if len(x) >= 10 else {}),
            }
        )
    by_polymer.sort(key=lambda r: (r["polymer"] == "other", -r["rows"]))
    named = [r["zeta_median"] for r in by_polymer if r["polymer"] != "other"]
    stats = {
        "rows": len(t),
        "papers": t.pmcid.nunique(),
        "by_polymer": by_polymer,
        "named_polymer_median_lo": min(named),
        "named_polymer_median_hi": max(named),
        "ps_rows": len(ps),
        "ps_papers": ps.pmcid.nunique(),
        "size_nm_min": float(t.size_nm.min()),
        "size_nm_max": float(t.size_nm.max()),
        "nominal_rows": int(t.size_kind.eq("nominal").sum()),
        "all_spearman": spearman(np.log10(t.size_nm), t.zeta_mV),
        "ps_by_surface": by_surface,
        "amine_rows": len(amine),
        "amine_negative": int((amine.zeta_mV < 0).sum()),
        "amine_positive": int((amine.zeta_mV > 0).sum()),
        "amine_by_medium": amine_by_medium,
    }
    return t, stats


def ncei() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    df = pd.read_csv(NCEI, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    df = df[df["Marine Setting"].isin(NCEI_SETTINGS)].copy()
    df["lat"] = pd.to_numeric(df["Latitude (degree)"])
    df["lon"] = pd.to_numeric(df["Longitude (degree)"])
    df["date"] = pd.to_datetime(df["Sample Date"], format="%m/%d/%Y %I:%M:%S %p")
    df["value"] = pd.to_numeric(df["Microplastics Measurement"], errors="coerce")
    df["mesh_um"] = pd.to_numeric(df["Mesh Size (mm)"], errors="coerce") * 1000
    df["study"] = df["DOI"].str.strip()

    def mode(s: pd.Series) -> str:
        s = s[s.ne("")]
        return s.mode().iat[0] if len(s) else ""

    rows = []
    for (doi, setting), g in df.groupby(["study", "Marine Setting"]):
        pos = g.value[g.value > 0]
        rows.append(
            {
                "doi": doi,
                "setting": setting,
                "ref": "; ".join(sorted(set(g["Short Reference"]))),
                "case": CASE_DOIS.get(doi, ""),
                "org": mode(g["Organization"]),
                "unit": mode(g["Unit"]),
                "ocean": mode(g["Ocean"]),
                "region": mode(g["Region"]),
                "methods": "; ".join(g["Sampling Method"].value_counts().index[:2]),
                "n": len(g),
                "n_value": int(g.value.notna().sum()),
                "n_zero": int((g.value == 0).sum()),
                "date_first": g.date.min().date().isoformat(),
                "date_last": g.date.max().date().isoformat(),
                "lat": round(float(g.lat.median()), 2),
                "lon": round(float(g.lon.median()), 2),
                "lower_um_min": g.mesh_um.min(),
                "lower_um_max": g.mesh_um.max(),
                "lower_missing": int(g.mesh_um.isna().sum()),
                "upper_um": NCEI_UPPER_UM,
                "conc_min": pos.min() if len(pos) else np.nan,
                "conc_p10": pos.quantile(0.1) if len(pos) else np.nan,
                "conc_median": pos.median() if len(pos) else np.nan,
                "conc_p90": pos.quantile(0.9) if len(pos) else np.nan,
                "conc_max": pos.max() if len(pos) else np.nan,
            }
        )
    studies = (
        pd.DataFrame(rows).sort_values(["setting", "date_first", "ref"]).reset_index(drop=True)
    )

    water = studies[
        studies.setting.eq("Ocean water")
        & studies.conc_median.notna()
        & studies.lower_um_min.notna()
    ]
    stats = {
        "records": len(df),
        "studies": int(studies.doi.nunique()),
        "by_setting": {
            s: {
                "records": int((df["Marine Setting"] == s).sum()),
                "studies": int(studies.setting.eq(s).sum()),
                "unit": mode(df.loc[df["Marine Setting"] == s, "Unit"]),
            }
            for s in NCEI_SETTINGS
        },
        "date_first": df.date.min().date().isoformat(),
        "date_last": df.date.max().date().isoformat(),
        "lower_um_min": float(df.mesh_um.min()),
        "lower_um_max": float(df.mesh_um.max()),
        "lower_distinct": int(df.mesh_um.dropna().nunique()),
        # Across ocean-water studies: does a finer lower size limit go with a higher median count?
        "water_lower_vs_median": spearman(
            np.log10(water.lower_um_min), np.log10(water.conc_median)
        ),
        # Do lower size limits fall over the years? First sampling year against the finest limit.
        "lower_vs_year": spearman(
            pd.to_datetime(studies.dropna(subset=["lower_um_min"]).date_first).dt.year,
            np.log10(studies.lower_um_min.dropna()),
        ),
    }
    pts = df[["lon", "lat", "date", "value", "Marine Setting", "study"]].copy()
    return studies, pts, stats


def mpsed() -> tuple[pd.DataFrame, dict]:
    d = pd.DataFrame(json.loads(MPSED.read_text(encoding="utf-8")))
    lim = d.mp_mdl.str.extract(r"^\s*([\d.]+)\s*-\s*([\d.]+)\s*$").astype(float)
    d["lower_um"], d["upper_um"] = lim[0], lim[1]
    d.loc[d.lower_um.eq(MPSED_UNKNOWN_LOWER), "lower_um"] = np.nan
    d["year"] = pd.to_numeric(
        d.SampleYearTime.astype(str).str.extract(r"((?:19|20)\d\d)")[0], errors="coerce"
    )
    rows = []
    for (doi, lo, hi), g in d.groupby(["DOI", d.lower_um.fillna(-1), "upper_um"], dropna=False):
        rows.append(
            {
                "doi": doi,
                "ref": "; ".join(sorted(set(g.Source.astype(str).str.split(",").str[0])))[:80],
                "countries": "; ".join(sorted(set(g.CountryName))),
                "waterbodies": "; ".join(sorted(set(g.waterbody)))[:120],
                "n": len(g),
                "year_first": g.year.min(),
                "year_last": g.year.max(),
                "year_missing": int(g.year.isna().sum()),
                "lower_um": None if lo == -1 else lo,
                "upper_um": hi,
                "conc_min": g.MP.min(),
                "conc_median": g.MP.median(),
                "conc_max": g.MP.max(),
                "stats": "; ".join(sorted(set(g.SummStat))),
            }
        )
    studies = pd.DataFrame(rows).sort_values(["year_first", "ref"]).reset_index(drop=True)
    pos = studies[studies.lower_um.notna() & studies.conc_median.gt(0)]
    stats = {
        "records": len(d),
        "dois": int(d.DOI.nunique()),
        "waterbodies": int(d.waterbody.nunique()),
        "countries": int(d.CountryName.nunique()),
        "unit": d.measure.iat[0],
        "lower_unknown_records": int(d.lower_um.isna().sum()),
        "year_missing_records": int(d.year.isna().sum()),
        "lower_um_min": float(d.lower_um.min()),
        "lower_um_max": float(d.lower_um.max()),
        "upper_um_values": sorted({float(v) for v in d.upper_um.dropna()}),
        "lower_vs_median": spearman(np.log10(pos.lower_um), np.log10(pos.conc_median)),
        "lower_vs_year": spearman(
            *(lambda x: (x.year_first, np.log10(x.lower_um)))(
                studies.dropna(subset=["lower_um", "year_first"])
            )
        ),
    }
    return studies, stats


def case_stats() -> dict:
    """Reisser 2013 and Eriksen 2014: one row per physical tow, with both NCEI values."""
    t = pd.read_csv(CASE_TOWS)
    both = t[(t.value_R > 0) & (t.value_E > 0)]
    ratio = both.value_R / both.value_E
    by_method = {m: round(float(r.median()), 2) for m, r in ratio.groupby(both["Sampling Method"])}
    return {
        "tows": len(t),
        "both_positive": len(both),
        "median_ratio": round(float(ratio.median()), 2),
        "median_ratio_by_method": by_method,
        "zero_E_positive_R": int(((t.value_E == 0) & (t.value_R > 0)).sum()),
    }


def land_path() -> str:
    """Natural Earth 110m land as one SVG path, equirectangular, 1 unit per degree (x = lon+180)."""
    topo = json.loads(LAND.read_text(encoding="utf-8"))
    (sx, sy), (tx, ty) = topo["transform"]["scale"], topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x, y = x + dx, y + dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)

    def ring(ids: list[int]) -> list[tuple[float, float]]:
        out: list[tuple[float, float]] = []
        for i in ids:
            a = arcs[i] if i >= 0 else arcs[~i][::-1]
            out.extend(a if not out else a[1:])
        return out

    polys = []
    for geom in topo["objects"]["land"]["geometries"]:
        polys += [geom["arcs"]] if geom["type"] == "Polygon" else geom["arcs"]
    parts = []
    for poly in polys:
        for r in poly:
            # A ring that crosses the date line jumps from +180 to -180; unwrap it so it stays
            # continuous, then draw it again shifted by 360 degrees. The page clips to the frame.
            pts = ring(r)
            un = [pts[0]]
            for lon, lat in pts[1:]:
                prev = un[-1][0]
                lon += 360 * round((prev - lon) / 360)
                un.append((lon, lat))
            lons = [p[0] for p in un]
            shifts = [0] + ([360] if min(lons) < -180 else []) + ([-360] if max(lons) > 180 else [])
            for off in shifts:
                parts.append(
                    "M" + "L".join(f"{lon + off + 180:.1f},{90 - lat:.1f}" for lon, lat in un) + "Z"
                )
    return "".join(parts)


def records(t: pd.DataFrame, cols: list[str]) -> list[list]:
    """Rows as lists, NaN as null, for a compact JSON payload."""
    return [
        [None if (isinstance(v, float) and np.isnan(v)) else v for v in row]
        for row in t[cols].itertuples(index=False, name=None)
    ]


PREREG_RESULTS = ROOT / "out/tables/p2_prereg_results.json"


def extension() -> dict:
    """Soil, measured size distributions, the Weser fractions and the pre-registered results."""
    ext.check_pins()
    soil = ext.soil()
    pos = soil[soil.conc > 0]
    q = pos.groupby("study").conc.quantile
    studies = (
        soil.groupby("study")
        .agg(
            lo=("lower_um", "min"),
            hi=("upper_um", "max"),
            n=("conc", "size"),
            lat=("lat", "median"),
            lon=("lon", "median"),
            y0=("year", "min"),
            y1=("year", "max"),
        )
        .join(q(0.1).rename("p10"))
        .join(q(0.5).rename("med"))
        .join(q(0.9).rename("p90"))
        .reset_index()
    )
    studies = studies[studies.med.notna() & studies.lo.gt(0)]
    pts = soil.dropna(subset=["lat", "lon"])
    bins = ext.mpsb_bins()
    raw = ext.fit_alpha(bins)
    lod = ext.fit_alpha(
        bins.assign(
            Geom_mean_size=bins["filtered_geom_mean_size"],
            Normalized_concentration=bins["filtered_normalized_concentration"],
        )
    )
    weser, windows = ext.weser()
    med_ratio = float(weser.ratio.dropna().median())
    # Small derived tables the deck reads with `git show` (the raw inputs are gitignored).
    tables = ROOT / "out/tables"
    weser.assign(
        small_lo_um=windows["small_um"][0],
        small_hi_um=windows["small_um"][1],
        large_lo_um=windows["large_um"][0],
        large_hi_um=windows["large_um"][1],
    ).to_csv(tables / "p2_weser_pairs.csv", index=False)
    pd.concat([raw.assign(bins_used="all"), lod.assign(bins_used="lod_filtered")]).to_csv(
        tables / "p2_alpha_fits.csv", index=False
    )
    return {
        "soil_studies": json.loads(
            studies.assign(study=studies.study.str.slice(0, 120)).to_json(orient="records")
        ),
        "soil_points": [
            [
                round(lo, 2),
                round(la, 2),
                None if np.isnan(y) else int(y),
                None if not c > 0 else round(float(np.log10(c)), 2),
            ]
            for lo, la, y, c in zip(pts.lon, pts.lat, pts.year, pts.conc, strict=True)
        ],
        "soil_records": len(soil),
        "alpha": {
            "raw": raw[["alpha", "sample_type"]].values.tolist(),
            "lod": lod[["alpha", "sample_type"]].values.tolist(),
        },
        "weser": {
            "pairs": json.loads(weser.to_json(orient="records")),
            "windows": windows,
            "median_ratio": round(med_ratio, 1),
            "stations_without_large": int(weser.ratio.isna().sum()),
            "ratio_at_default_alpha": round(
                ext.window_ratio(1.6, windows["small_um"], windows["large_um"]), 1
            ),
            "implied_alpha": round(
                ext.implied_alpha(med_ratio, windows["small_um"], windows["large_um"]), 2
            ),
        },
        "prereg": json.loads(PREREG_RESULTS.read_text(encoding="utf-8")),
    }


def main() -> None:
    check_pins()
    zs, zs_stats = zeta_size()
    nc, pts, nc_stats = ncei()
    ms, ms_stats = mpsed()

    tables = ROOT / "out/tables"
    zs.to_csv(tables / "p2_zeta_size.csv", index=False)
    nc.to_csv(tables / "p2_ncei_studies.csv", index=False)
    ms.to_csv(tables / "p2_mpsed_studies.csv", index=False)

    setting_code = {s: i for i, s in enumerate(NCEI_SETTINGS)}
    study_index = {doi: i for i, doi in enumerate(sorted(pts.study.unique()))}
    pts = pts.assign(
        lon=pts.lon.round(2),
        lat=pts.lat.round(2),
        year=pts.date.dt.year,
        logv=np.where(pts.value > 0, np.log10(pts.value.where(pts.value > 0)).round(2), np.nan),
        zero=(pts.value == 0).astype(int),
        s=pts["Marine Setting"].map(setting_code),
        k=pts.study.map(study_index),
    )
    data = {
        "sources": {
            "d1": "out/tables/d1_zeta_table.csv",
            "ncei": PINS[NCEI],
            "mpsed": PINS[MPSED],
            "ncei_url": "https://hub.arcgis.com/api/download/v1/items/1b56a456ad8c43889652e62aa25a317e/csv?redirect=true&layers=0",
            "mpsed_url": "https://doer.el.erdc.dren.mil/Data/data.json",
        },
        "zeta": {
            "stats": zs_stats,
            "cols": [
                "size_nm",
                "zeta_mV",
                "surface",
                "medium_class",
                "material_group",
                "pmcid",
                "row_id",
                "size_kind",
            ],
            "rows": records(
                zs,
                [
                    "size_nm",
                    "zeta_mV",
                    "surface",
                    "medium_class",
                    "material_group",
                    "pmcid",
                    "row_id",
                    "size_kind",
                ],
            ),
        },
        "case": case_stats(),
        "ncei": {
            "stats": nc_stats,
            "settings": list(NCEI_SETTINGS),
            "study_dois": list(study_index),
            "studies": json.loads(nc.to_json(orient="records")),
            "points_cols": ["lon", "lat", "year", "logv", "zero", "s", "k"],
            "points": records(pts, ["lon", "lat", "year", "logv", "zero", "s", "k"]),
        },
        "mpsed": {"stats": ms_stats, "studies": json.loads(ms.to_json(orient="records"))},
        "land": land_path(),
        "ext": extension(),
    }
    (HERE / "data.json").write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    template = HERE / "template.html"
    if template.exists():
        out = HERE / "p2.html"
        out.write_text(inline(template.read_text(encoding="utf-8"), data), encoding="utf-8")
        print(f"wrote {out}, {out.stat().st_size:,} bytes")
    print(
        json.dumps({"zeta": zs_stats, "ncei": nc_stats, "mpsed": ms_stats}, indent=1, default=str)
    )


if __name__ == "__main__":
    main()
