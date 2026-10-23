"""The dataset search agent's rules: what is on topic, what is one dataset, what a table holds.

unset VIRTUAL_ENV; uv run --with openpyxl python -m pytest -q -p no:cacheprovider tool/discover
"""

from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import catalog  # noqa: E402
import triage  # noqa: E402
import verify  # noqa: E402

from mnp.eval import grid  # noqa: E402


def _cand(**kw) -> catalog.Candidate:
    base = dict(doi="10.1/x", title="t", publisher="Zenodo", year=2024, description="",
                subjects=[], licence="", formats=[], sizes=[], has_geolocation=False)  # fmt: skip
    return catalog.Candidate(**(base | kw))


def test_the_topic_filter_wants_plastic_in_the_record() -> None:
    assert catalog.about_plastic(_cand(title="Microplastic abundance in the Baltic"))
    assert catalog.about_plastic(_cand(description="nano-plastics in tap water"))
    assert not catalog.about_plastic(_cand(title="Phytoplankton counts in the Baltic"))


def test_versions_of_one_dataset_collapse_to_the_newest() -> None:
    a = _cand(doi="10.5281/zenodo.1", title="Beach MP survey", year=2022, queries=["q1"])
    b = _cand(doi="10.5281/zenodo.2", title="Beach  MP survey", year=2024, queries=["q2"])
    c = _cand(doi="10.6084/m9.figshare.3", title="Beach MP survey", publisher="figshare")
    kept = {x.doi: x for x in catalog.dedupe([a, b, c])}
    assert set(kept) == {"10.5281/zenodo.2", "10.6084/m9.figshare.3"}
    assert kept["10.5281/zenodo.2"].queries == ["q1", "q2"]


def test_column_roles_come_from_the_header() -> None:
    r = verify.roles(["Latitude", "Longitude (degrees_east)", "Date/Time",
                      "Microplastic [#/m**3]", "Mesh size (mm)", "Station"])  # fmt: skip
    assert r["lat"] == ["Latitude"] and r["lon"] == ["Longitude (degrees_east)"]
    assert "Date/Time" in r["date"] and "Mesh size (mm)" in r["size"]
    assert "Microplastic [#/m**3]" in r["conc"]
    assert verify.roles(["Station", "Depth", "Salinity"]) == {}


def test_a_concentration_needs_plastic_and_a_unit_per_volume_mass_or_area() -> None:
    # the first run passed a water-chemistry table and two particle-size tables as concentrations
    conc = [
        "Microplastic [#/m**3]",
        "Plastic particle conc [#/l] (Abundance in sample)",
        "Microplastic [#/kg] (MP kg-1)",
        "abundance_numeric",
        "Microplastics Measurement",
        "items/m3",
    ]
    not_conc = [
        "O2 sat [mg/l] (Multiparameter probe)",
        "Chl a [µg/l]",
        "Microplastic part size [µm] (measurement 1)",
        "Microplastic part [#]",
        "Microplastic part vol [mm**3]",
        "Country",
    ]
    assert verify.roles(conc).get("conc") == conc
    assert verify.roles(not_conc).get("conc") is None


def test_a_table_is_usable_only_with_place_time_and_a_concentration() -> None:
    full = pd.DataFrame({"lat": [1.0] * 25, "lon": [2.0] * 25, "year": [2020] * 25,
                         "particles/m3": [0.1] * 25})  # fmt: skip
    assert verify.judge([full])["verdict"] == "usable"
    assert verify.judge([full.head(5)])["verdict"] == "partial"  # too few rows to be a survey
    assert verify.judge([full.drop(columns=["lat"])])["verdict"] == "partial"
    assert verify.judge([full.drop(columns=["particles/m3"])])["verdict"] == "not_usable"


def test_pangaea_text_files_and_zipped_tables_are_read() -> None:
    tab = "/* DATA DESCRIPTION:\nCitation: x\n*/\nLatitude\tLongitude\tMP [#/m**3]\n1\t2\t3\n"
    assert list(verify.read_table("p.tab", tab.encode())[0].columns) == [
        "Latitude", "Longitude", "MP [#/m**3]"]  # fmt: skip
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("data/survey.csv", "lat,lon,items/kg\n1,2,3\n")
        z.writestr("readme.pdf", "x")
    frames = verify.read_table("bundle.zip", buf.getvalue())
    assert len(frames) == 1 and "items/kg" in frames[0].columns


def test_the_rule_not_the_model_decides_what_is_opened() -> None:
    ok = {"kind": "field_measurements", "matrix": ["ocean_water"], "concentrations": "yes",
          "tabular": "unclear"}  # fmt: skip
    assert triage.worth_verifying(ok)
    assert not triage.worth_verifying(ok | {"kind": "lab_experiment"})
    assert not triage.worth_verifying(ok | {"matrix": ["biota"]})
    assert not triage.worth_verifying(ok | {"concentrations": "no"})


def test_a_malformed_triage_is_left_unclassified(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(triage, "CACHE", tmp_path)
    cands = [catalog.to_dict(_cand(doi=f"10.1/{i}", title=f"MP {i}")) for i in range(3)]

    def short(prompt, system=None):  # answers for only two of three records
        return grid.Reply(text=json.dumps({"items": [{"doi": "10.1/0"}, {"doi": "10.1/1"}]}),
                          model="fake")  # fmt: skip

    assert triage.classify(cands, ask=short) == {}

    def full(prompt, system=None):
        items = [{"doi": c["doi"], "kind": "field_measurements"} for c in cands]
        return grid.Reply(text=json.dumps({"items": items}), model="fake")

    assert set(triage.classify(cands, ask=full)) == {"10.1/0", "10.1/1", "10.1/2"}


def test_a_dataset_ncei_already_holds_is_flagged() -> None:
    c = catalog.to_dict(_cand(doi="10.1/new", related=["IsDerivedFrom:10.1/old"]))
    assert verify.ncei_overlap(c, {"10.1/old"})
    assert verify.ncei_overlap(catalog.to_dict(_cand(description="from NOAA NCEI")), set())
    assert not verify.ncei_overlap(catalog.to_dict(_cand()), {"10.1/old"})
