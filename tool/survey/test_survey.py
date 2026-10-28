"""The survey table and its validators, each checked against its source by another route.

unset VIRTUAL_ENV; uv run --with openpyxl python -m pytest -q -p no:cacheprovider tool/survey
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import table  # noqa: E402


@pytest.fixture(scope="module")
def records():
    return table.build()


def test_every_source_record_arrives_once(records) -> None:
    with open(ROOT / "data/raw/ncei/ncei_hub_microplastics.csv", encoding="utf-8-sig") as f:
        settings = [r["Marine Setting"] for r in csv.DictReader(f)]
    n = records.groupby("dataset").size()
    assert n["ncei"] == sum(s in ("Ocean water", "Beach", "Ocean sediment") for s in settings)
    assert n["mpsed"] == len(json.loads((ROOT / "data/raw/mpsed/data.json").read_text()))
    assert n["pangaea_weser"] == 2 * 23
    assert records.record_id.is_unique


def test_the_datasets_added_after_p2_arrive_whole(records) -> None:
    import struct
    import zipfile

    raw = zipfile.ZipFile(table.EMODNET).read("mlf_density_nb_m3_monitoring.dbf")
    n = records.groupby("dataset").size()
    assert n["emodnet"] == struct.unpack("<I", raw[4:8])[0]
    # air is a different matrix, and a compilation of one value per study is not a survey
    assert not records.setting.str.contains("air", case=False).any()
    e = records[records.dataset == "emodnet"]
    # every EMODnet tow in this file was taken in the Baltic and the Kattegat
    assert e.lat.between(53, 66).all() and e.lon.between(9, 31).all()


def test_a_tow_line_is_placed_at_its_midpoint() -> None:
    import struct

    line = struct.pack("<bII", 1, 2 | 0x20000000, 4326) + struct.pack("<I2d2d", 2, 10, 50, 12, 52)
    assert table.wkb_midpoint(line.hex()) == (51.0, 11.0)
    assert all(map(np.isnan, table.wkb_midpoint("zz")))


def test_a_field_the_source_lacks_stays_empty(records) -> None:
    m = records[records.dataset == "mpsed"]
    assert m.lat.isna().all() and m.lon.isna().all()
    coded = m["flags"].str.contains("lower_unreported_code")
    assert coded.sum() > 0 and m.loc[coded, "size_min_um"].isna().all()
    n = records[records.dataset == "ncei"]
    assert (
        n.size_max_um.eq(5000).all() and n["flags"].str.startswith("upper_by_database_rule").all()
    )
    assert n["flags"].ne("upper_by_database_rule").sum() == 129  # Reisser's Manta tows, below


import pandas as pd  # noqa: E402
import validators as v  # noqa: E402

REISSER = "https://doi.org/10.1371/journal.pone.0080466"
ERIKSEN = "https://doi.org/10.1371/journal.pone.0111913"


def test_the_known_twice_held_tows_are_found_blind(records) -> None:
    # tool/colocation/reisser_eriksen matched 171 tows by station and tow number from the papers'
    # own tables; the detector sees only date and position.
    d = v.duplicates(records)
    pair = d[(d.study_a == REISSER) & (d.study_b == ERIKSEN)]
    assert len(pair) == 1
    known = pd.read_csv(
        ROOT / "tool/colocation/reisser_eriksen/out_2026-10-12" / "tow_identity_R_E.csv"
    )
    assert pair.records_a.iat[0] >= 0.95 * len(known)
    assert pair.median_km.iat[0] < 2


def test_reissers_manta_tows_use_the_net_depth_reisser_states(records) -> None:
    # Martin, 2026-10-27: NCEI's Reisser Manta values are Table S1's pieces/km2 over 0.085 m, a
    # depth no NCEI field holds; Reisser's Methods give 0.17 m, "full immersion of the net frame".
    # The paper's geometry stands until a record shows what 0.085 m means.
    with open(ROOT / "data/raw/ncei/ncei_hub_microplastics.csv", encoding="utf-8-sig") as f:
        raw = [r for r in csv.DictReader(f) if r["DOI"] == REISSER]
    assert {r["Water Sample Depth (m)"] for r in raw} == {"0"}
    tows = pd.read_csv(
        ROOT / "tool/colocation/reisser_eriksen/out_2026-10-12" / "tow_identity_R_E.csv",
        dtype={"Unique ID_R": str},
    )
    n = records[records.study == REISSER].set_index("record_id")
    assert len(n) == len(tows)
    got = n.loc["ncei:" + tows["Unique ID_R"], "value"].to_numpy()
    depth = np.where(tows["Sampling Method"] == "Manta net", 0.17, 0.3)
    assert np.allclose(got, tows["Cs"] / 1e6 / depth, rtol=1e-3)
    # AOMI holds NCEI's values for the same tows, so their depth is put right there too
    a = records[records.study == "aomi:" + REISSER]
    manta = (a.method == "Manta net").to_numpy()
    assert a["flags"].str.contains("depth_from_paper").to_numpy().tolist() == manta.tolist()
    assert manta.sum() > 100
    # nothing else moves: no other study carries the flag
    flagged = records[records["flags"].str.contains("depth_from_paper", na=False)]
    assert set(flagged.study) == {REISSER, "aomi:" + REISSER}


def _toy(rows):
    cols = ["study", "setting", "date", "lat", "lon", "value", "method", "year"]
    return pd.DataFrame(rows, columns=cols).assign(unit="pieces/m3", size_min_um=float("nan"))


def test_records_in_different_units_never_pair() -> None:
    # A pair at one place only compares if the two values count the same thing: plastic pieces
    # per m3 and unconfirmed microparticles per m3 do not, however close they lie.
    rows = [
        ("A", "w", "2020-01-01", 10.0, 10.0, 1.0, "net", 2020),
        ("B", "w", "2020-01-01", 10.0, 10.001, 2.0, "net", 2020),
    ]
    t = _toy(rows)
    assert len(v.colocated(t, km=50, days=None, same_method=False)) == 1
    t["unit"] = ["pieces/m3", "microparticles/m3"]
    assert v.colocated(t, km=50, days=None, same_method=False).empty
    t["unit"] = ["pieces/m3", None]
    assert v.colocated(t, km=50, days=None, same_method=False).empty


def test_duplicates_needs_the_same_day_and_another_study() -> None:
    same = [("A", "w", "2020-01-01", 10.0, 10.0 + i * 0.1, 1.0, "net", 2020) for i in range(12)]
    copy = [(s.replace("A", "B"), *rest) for s, *rest in same]
    later = [("C", "w", "2020-01-02", *r[3:]) for r in same]
    self_ = [("A", "w", "2020-01-01", *r[3:]) for r in same]
    d = v.duplicates(_toy(same + copy + later + self_))
    assert d[["study_a", "study_b"]].values.tolist() == [["A", "B"]]


def test_a_window_conversion_is_bounded_and_refused_when_too_wide() -> None:
    assert v.window_verdict((300, 5000), (300, 5000)).decision == "allow"
    near = v.window_verdict((333, 5000), (300, 5000))
    # a finer lower limit widens the window, so the count can only grow, and only a little
    assert near.decision == "caveat" and 1 < near.detail[0] < near.detail[1] < 1.2
    # The Weser fractions do not overlap; no single slope converts one into the other.
    assert v.window_verdict((11, 500), (500, 5000)).decision == "refuse"
    assert v.window_verdict((100, 5000), (None, 5000)).reason == "window_unreported"


def test_a_window_factor_is_the_power_law_integral_ratio() -> None:
    lo, hi = v.window_factor((100, 5000), (300, 5000))
    for a in (1.3, 2.2):
        f = (300 ** (1 - a) - 5000 ** (1 - a)) / (100 ** (1 - a) - 5000 ** (1 - a))
        assert lo - 1e-12 <= f <= hi + 1e-12


def test_different_units_are_never_compared() -> None:
    assert v.unit_verdict("pieces/m3", "pieces kg-1 d.w.").decision == "refuse"
    assert v.unit_verdict("pieces/m3", "pieces/m3").decision == "allow"
    assert v.unit_verdict(None, "pieces/m3").decision == "refuse"


def test_colocated_pairs_cross_studies_within_distance_and_time() -> None:
    rows = [
        ("A", "w", "2020-01-01", 0.0, 0.0, 1.0, "net", 2020),
        ("B", "w", "2020-03-01", 0.0, 0.2, 4.0, "net", 2020),  # 22 km, 60 days
        ("C", "w", "2023-01-01", 0.0, 0.2, 9.0, "net", 2023),  # three years later
        ("D", "w", "2020-01-01", 0.0, 0.2, 9.0, "pump", 2020),  # another method
        ("A", "w", "2020-01-01", 0.0, 0.1, 2.0, "net", 2020),  # the same study
    ]
    p = v.colocated(_toy(rows), km=50, days=365, same_method=True)
    assert len(p) == 2 and np.allclose(sorted(p.log10_ratio), sorted([np.log10(4), np.log10(2)]))


def test_within_a_study_only_its_own_records_pair() -> None:
    # the patchiness baseline: A against itself, never A against B
    rows = [
        ("A", "w", "2020-01-01", 0.0, 0.0, 1.0, "net", 2020),
        ("A", "w", "2020-02-01", 0.0, 0.2, 3.0, "net", 2020),
        ("B", "w", "2020-01-01", 0.0, 0.1, 9.0, "net", 2020),
    ]
    p = v.colocated(_toy(rows), km=50, days=365, same_method=True, same_study=True)
    assert len(p) == 1 and np.isclose(p.log10_ratio.iat[0], np.log10(3))


def test_series_change_compares_the_first_and_last_third_of_years() -> None:
    flat = [("S", "w", None, 0, 0, 1.0, "net", y) for y in range(2000, 2009)]
    up = [("U", "w", None, 0, 0, 10.0 if y >= 2006 else 1.0, "net", y) for y in range(2000, 2009)]
    s = v.series_change(_toy(flat + up)).set_index("study")
    assert s.loc["S", "ratio_last_over_first"] == 1.0
    assert s.loc["U", "ratio_last_over_first"] == 10.0


def test_pooled_periods_count_each_study_once_in_the_second_median() -> None:
    big = [("big", "w", None, 0, 0, 1.0, "net", 2001)] * 9
    rows = big + [("small", "w", None, 0, 0, 9.0, "net", 2002)]
    p = v.pooled_periods(_toy(rows)).iloc[0]
    assert p.median_per_record == 1.0 and p.median_per_study == 5.0


def test_pooled_periods_say_how_small_a_particle_was_counted() -> None:
    # A rise in counts of net-caught pieces is a rise in microplastics only. The period's median
    # lower size limit says so, and shows whether the window changed between periods.
    rows = [("A", "w", None, 0, 0, 1.0, "net", 2001)] * 2
    rows += [("B", "w", None, 0, 0, 2.0, "pump", 2002)]
    p = v.pooled_periods(_toy(rows).assign(size_min_um=[333.0, 333.0, 0.45])).iloc[0]
    assert p.median_size_min_um == 333.0


def test_completeness_reports_what_a_dataset_never_gives(records) -> None:
    c = v.completeness(records)
    assert c.loc["mpsed", "lat"] == 1.0 and c.loc["soil", "method"] == 1.0
    assert c.loc["ncei", "date"] == 0.0


def test_a_tow_that_caught_nothing_counts_in_a_series() -> None:
    # first third: 0 and 2 (mean 1); last third: 1 and 1 (mean 1). Dropping zeros would halve it.
    rows = [("Z", "w", None, 0, 0, val, "net", y) for y, val in
            [(2000, 0.0), (2000, 2.0), (2001, 5.0), (2002, 1.0), (2002, 1.0)]]  # fmt: skip
    assert v.series_change(_toy(rows)).ratio_last_over_first.iat[0] == 1.0


def test_the_found_pangaea_datasets_arrive_whole_with_their_own_window(records) -> None:
    for pid in table.PANGAEA_FOUND:
        text = table._pangaea_path(pid).read_text(encoding="utf-8")
        rows = text.split("*/\n", 1)[1].strip().count("\n")  # data lines under the header
        assert (records.dataset == f"pangaea_{pid}").sum() == rows, pid
    w = records[records.dataset.str.startswith("pangaea_9")]
    lower = w.groupby("dataset").size_min_um.first()
    # the windows the datasets' own methods state: 300 um meshes, a 10 um counting limit
    assert lower["pangaea_941076"] == 300 and lower["pangaea_990052"] == 10
    # the reviewer's convention (2026-10-10, [32:03]): a stated lower limit implies 5 mm above
    found = records[records["flags"].str.contains("found_by_search_agent", na=False)]
    upper = found.groupby("dataset").size_max_um.agg(lambda s: set(s.dropna()))
    assert upper["pangaea_990052"] == {5000.0} and upper["pangaea_941076"] == {5000.0}
    conv = found[found.size_max_um.notna()]
    assert conv["flags"].str.contains("upper_by_convention").all()


def test_a_cross_dataset_ratio_is_taken_only_where_the_window_guard_allows_it() -> None:
    import report

    rows = [
        ("A", "w", "2020-01-01", 0.0, 0.0, 1.0, "net", 2020),
        ("B", "w", "2021-01-01", 0.0, 0.2, 2.0, "net", 2021),  # dataset y, the same window
        ("C", "w", "2021-01-01", 0.0, 0.3, 5000.0, "pump", 2021),  # dataset z, 10 um and up
    ]
    t = _toy(rows).assign(
        dataset=["x", "y", "z"], size_min_um=[330.0, 330.0, 10.0], size_max_um=5000.0
    )
    none = pd.DataFrame(columns=["study_a", "study_b"])
    out = report.across_datasets(t, km=100, days=None, dup=none)
    assert out["pairs"] == 3 and out["compared"] == 1 and out["refused"] == 2
    assert out["median_fold"] == 2.0  # the ×5000 and ×2500 pairs never enter it
    assert out["unguarded"]["median_fold"] == 2500.0  # what a pooled, unguarded median reports
    by = {(r["datasets"], r["decision"]): r for r in out["by_dataset_pair"]}
    assert by[("x vs z", "refuse")]["reason"] == "window_factor_too_uncertain"
    held = pd.DataFrame({"study_a": ["A"], "study_b": ["B"]})
    assert report.across_datasets(t, km=100, days=None, dup=held)["compared"] == 0


def test_a_caveated_cross_dataset_pair_reports_the_gap_the_window_cannot_explain() -> None:
    import report

    # a 150 um net against a 10 um pump: the window predicts the pump counts lo..hi times more
    lo, hi = v.window_factor((150.0, 5000.0), (10.0, 5000.0))
    rows = [
        ("A", "w", "2020-01-01", 0.0, 0.0, 1.0, "net", 2020),
        ("B", "w", "2021-01-01", 0.0, 0.2, 500.0, "pump", 2021),  # far beyond hi
        ("C", "w", "2021-01-01", 0.0, 0.3, 1.0, "net", 2021),  # dataset z, the same net
    ]
    t = _toy(rows).assign(
        dataset=["x", "y", "z"], size_min_um=[150.0, 10.0, 150.0], size_max_um=5000.0
    )
    none = pd.DataFrame(columns=["study_a", "study_b"])
    out = report.across_datasets(t, km=100, days=None, dup=none)
    by = {r["datasets"]: r for r in out["by_dataset_pair"]}
    assert by["x vs y"]["decision"] == "caveat"
    assert by["x vs y"]["median_fold"] == 500.0
    # what is left after the most generous conversion: 500 / hi, never 500 itself
    assert by["x vs y"]["median_residual_fold"] == round(500.0 / hi, 2)
    # a pair the window fully explains leaves nothing: the same net, the same count
    assert by["x vs z"]["median_residual_fold"] == 1.0


def test_a_study_summary_is_its_records_quantiles_and_its_stated_window(records) -> None:
    import report

    s = report.studies(records)
    one = s[(s.dataset == "pangaea_990052")].iloc[0]
    rows = records[records.dataset == "pangaea_990052"]
    pos = rows.value[rows.value > 0]
    assert one.n == len(rows) and one.n_pos == len(pos)
    assert np.isclose(one.p50, pos.median()) and np.isclose(one.p10, pos.quantile(0.1))
    assert (one.size_min_um, one.size_max_um) == (10.0, 5000.0)
    # a study with no positive value has no span to draw, but it is still counted
    assert s.n.sum() == len(records)


def test_the_scouts_datasets_arrive_whole_and_keep_their_gaps(records) -> None:
    import io

    k = records[records.dataset == "kiessling2021"]
    sheet = pd.read_excel(io.BytesIO(table.KIESSLING.read_bytes()), "SamplingSites_and_LitterData")
    assert len(k) == len(sheet) and k.setting.eq("river water").all()
    # the file does not state the size window it counted; the table does not invent one
    assert k.size_min_um.isna().all() and k["flags"].str.contains("window_unreported").all()


def test_martins_datasets_arrive_whole_with_what_they_state(records) -> None:
    import pyreadr

    durum = pd.read_excel(table.DURUM)
    d = records[records.dataset == "durum"]
    assert len(d) == len(durum) and d.setting.eq("stormwater runoff").all()
    assert (d.size_min_um.to_numpy() == durum.x1M_um.to_numpy()).all()  # the window it states
    rivm = pyreadr.read_r(table.RIVM_TOTAL)[None]
    r = records[records.dataset == "rivm"].reset_index(drop=True)
    assert len(r) == len(rivm) and r.unit.eq("pieces/m3").all()
    # a date printed without its century ("0016-09-20") is not completed by guessing
    broken = rivm.sampling_date.astype(str).str.startswith("00").to_numpy()
    assert r.year[broken].isna().all() and r.date[broken].isna().all()
    assert r["flags"][broken].str.contains("date_without_century").all()


def _held(x: pd.DataFrame, y: pd.DataFrame, km: float = 2.0) -> float:
    """The share of x's placed records with a y record on the same day within km."""
    x, y = x[x.lat.notna() & x.date.notna()], y[y.lat.notna() & y.date.notna()]
    by_day = dict(list(y.groupby("date")))
    hit = 0
    for day, g in x.groupby("date"):
        h = by_day.get(day)
        if h is None:
            continue
        la1, lo1 = np.radians(g.lat.to_numpy())[:, None], np.radians(g.lon.to_numpy())[:, None]
        la2, lo2 = np.radians(h.lat.to_numpy())[None], np.radians(h.lon.to_numpy())[None]
        dlat, dlon = (la2 - la1) / 2, (lo2 - lo1) / 2
        hav = np.sin(dlat) ** 2 + np.cos(la1) * np.cos(la2) * np.sin(dlon) ** 2
        hit += int(((6371 * 2 * np.arcsin(np.sqrt(hav))).min(axis=1) <= km).sum())
    return hit / len(x)


def test_the_atlas_arrives_whole_with_its_mesh_and_without_its_pole_placeholder(records) -> None:
    with open(table.AOMI, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    a = records[records.dataset == "aomi"].reset_index(drop=True)
    assert len(a) == len(rows) and a.study.str.startswith("aomi:").all()
    mesh = [float(r["D01_0070"]) * 1000 if r["D01_0070"] else np.nan for r in rows]
    assert np.allclose(a.size_min_um, mesh, equal_nan=True) and a.size_max_um.eq(5000).all()
    value = np.array([float(r["D01_0192"]) if r["D01_0192"] else np.nan for r in rows])
    depth = a["flags"].str.contains("depth_from_paper").to_numpy()
    assert np.allclose(a.value, np.where(depth, value * 0.085 / 0.17, value), equal_nan=True)
    # a latitude of 90 is the atlas's placeholder for a missing position, not the North Pole
    pole = np.array([abs(float(r["latitude"])) >= 89.9 for r in rows])
    assert pole.any() and a.lat[pole].isna().all() and a.lat[~pole].notna().all()


def test_the_atlas_holds_noaas_own_tows_and_isobes_samples(records) -> None:
    with open(table.AOMI, newline="", encoding="utf-8-sig") as f:
        noaa = {"aomi:" + r["D01_0001"] for r in csv.DictReader(f)
                if r["D01_0004"].startswith("NOAA Marine Microplastics")}  # fmt: skip
    a = records[records.dataset == "aomi"]
    ncei = records[(records.dataset == "ncei") & (records.setting == "Ocean water")]
    # the rows AOMI credits to NOAA's database are NOAA's own records: same day, same place
    assert _held(a[a.record_id.isin(noaa)], ncei) > 0.9
    assert _held(ncei, a) > 0.7


def test_every_dataset_shares_a_place_with_another_study(records) -> None:
    # Martin, 2026-10-26: a dataset whose records share no place with any other study compares
    # nothing. MP-SED places a record by water body, not coordinates; the Weser fractions compare
    # two size windows at the same stations within one study. A shared place counts only in a
    # shared unit (2026-10-28).
    p = v.colocated(records, km=50, days=None, same_method=False)
    seen = set(records.loc[p.i, "dataset"]) | set(records.loc[p.j, "dataset"])
    assert set(records.dataset) - seen == {"mpsed", "pangaea_weser"}


def test_a_doi_is_one_study_however_a_database_writes_it(records) -> None:
    # AOMI writes one paper's DOI bare in some rows and as a link in others; split, the paper
    # looked like two studies holding the same samples
    with open(table.AOMI, newline="", encoding="utf-8-sig") as f:
        ids = {r["D01_0001"]: r["D01_0016"].strip() for r in csv.DictReader(f)}
    forms = [k for k, d in ids.items() if d.lower().endswith("10.1088/1748-9326/abbb4f")]
    assert len({ids[k] for k in forms}) > 1
    a = records[records.dataset == "aomi"].set_index("record_id")
    assert set(a.loc[["aomi:" + k for k in forms], "study"]) == {
        "aomi:https://doi.org/10.1088/1748-9326/abbb4f"
    }
    linked = records.study.dropna().str.extract(r"(https://doi\.org/.*)$", expand=False).dropna()
    assert (linked == linked.str.lower()).all()


def test_the_same_paper_in_two_databases_is_never_compared_with_itself() -> None:
    import report

    base = {"setting": "Ocean water", "date": "2020-01-01", "year": 2020.0, "method": "net",
            "unit": "pieces/m3", "size_min_um": 300.0, "size_max_um": 5000.0,
            "lat": 10.0}  # fmt: skip
    t = pd.DataFrame(
        [
            dict(base, dataset="ncei", study="https://doi.org/10.1/x", lon=10.0, value=1.0),
            dict(base, dataset="aomi", study="aomi:https://doi.org/10.1/x", lon=10.01, value=3.0),
            dict(base, dataset="aomi", study="aomi:https://doi.org/10.1/y", lon=10.02, value=2.0),
        ]
    )
    out = report.across_datasets(t, 50, 365, v.duplicates(t))
    assert out["pairs"] == 1 and out["excluded_same_paper"] == 1


def test_geoplasticobr_arrives_without_its_biota_and_with_one_doi_per_study(records) -> None:
    with open(table.GEOPLASTICO, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    abiotic = [r for r in rows if r["category_type"] == "abiotico"]
    g = records[records.dataset == "geoplasticobr"]
    # a mussel's count is a body burden, not a concentration in the environment
    assert len(g) == len(abiotic) < len(rows)
    # no row gives a sampling date or a size window; its year column is the paper's
    assert g.date.isna().all() and g.year.isna().all() and g.size_min_um.isna().all()
    assert g["flags"].str.contains("sampling_date_unreported").all()
    assert (g.unit == "pieces/m3").sum() == sum(r["unidade"] == "particles_m3" for r in abiotic)
    # the DOI column was filled down: the Amazon study's rows count up from its own DOI into
    # other papers' (...119708 is on steel corrosion), so the study keeps the first
    amazon = [r["id"] for r in abiotic if r["title"].startswith("Large-scale monitoring and risk")]
    a = g.set_index("record_id").loc[["geoplasticobr:" + i for i in amazon]]
    assert set(a.study) == {"geoplasticobr:https://doi.org/10.1016/j.watres.2023.119707"}
    assert a["flags"].str.contains("doi_filled_down").sum() == len(amazon) - 1


def test_the_committed_outputs_match_the_table_they_came_from(records) -> None:
    # 2026-10-28: survey_p7.json was left stale after NET_DEPTH changed Reisser's values, because
    # report.py was rerun and p7.py was not. Any change to the table must rerun both.
    import p7

    import report

    want = json.loads((ROOT / "out/tables/survey_p7.json").read_text())["P7c"]["periods"]
    got = v.pooled_periods(p7.water(records)).round(6).to_dict(orient="records")
    assert got == want
    co = json.loads((ROOT / "out/tables/survey_colocated.json").read_text())
    assert co["records"] == {k: int(n) for k, n in records.groupby("dataset").size().items()}
    water = records[records.setting == "Ocean water"]
    now = report.across_datasets(water, 50, 365, v.duplicates(records))
    assert {k: now[k] for k in ("pairs", "compared", "median_fold")} == {
        k: co["across_datasets"][k] for k in ("pairs", "compared", "median_fold")
    }
