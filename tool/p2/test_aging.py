"""P11's rules: what counts as aged, which rows are the same particle, and the numbers by hand.

uv run --with openpyxl python -m pytest -q -p no:cacheprovider tool/p2/test_aging.py
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import aging  # noqa: E402


def test_a_negated_aging_word_is_virgin_and_the_treatment_is_named() -> None:
    assert aging.state("non-UV-aged plain HDPE MPs") == "virgin"
    assert aging.state("PMMA MPs, no UV") == "virgin"
    assert aging.state("PE MPs, unaged, 22–37 μm") == "virgin"
    assert aging.state("PS MPs") == "virgin"
    assert aging.state("PS MPs, 5 days 254 nm UV") == "aged"
    assert aging.kind("UVB/H2O2 oxidized") == "photo"
    assert aging.kind("Aged PVC (ozonated)") == "chemical"
    assert aging.kind("PS(O3) | O3-aged") == "chemical"  # O3 is ozone; the first run missed it
    assert aging.kind("weathered PET COO- groups introduced by KOH weathering") == "chemical"
    assert aging.kind("aged 14 days in standard seawater") == "environmental"
    assert aging.kind("UV-aged 30 days in river water") == "photo"  # light wins over the water
    assert aging.kind("artificially aged PE") == "unspecified"


def test_the_aging_words_are_stripped_and_nothing_else() -> None:
    same = aging.identity
    assert same("PMMA MPs, no UV") == same("PMMA MPs, 5 days 254 nm UV")
    assert same("virgin PS") == same("aged PS")
    assert same("UV-oxidized PS 50 nm") == same("PS 50 nm") != same("PS 200 nm")
    assert same("UV-aged plain HDPE MPs + Cd") == same("non-UV-aged plain HDPE MPs + Cd")
    assert same("UV-aged plain HDPE MPs + Cd") != same("UV-aged plain HDPE MPs")


def _row(pmcid, name, value, medium="NaCl 10 mM", ph="7", functionalisation="", size="", i=""):
    return {
        "pmcid": pmcid, "row_id": f"{pmcid}-{name}-{value}", "particle_name": name,
        "functionalisation": functionalisation, "material": "polystyrene", "quantity":
        "zeta_potential", "value": value, "medium_text": medium, "pH": ph,
        "size_nominal_nm": size, "ionic_strength_mM": i,
    }  # fmt: skip


def test_a_pair_needs_the_same_paper_liquid_ph_size_and_additives() -> None:
    rows = pd.DataFrame(
        [
            _row("P1", "PS MPs", "-20"),
            _row("P1", "PS MPs", "-22"),
            _row("P1", "UV-aged PS MPs", "-35"),
            _row("P1", "UV-aged PS MPs", "-40", medium="seawater"),  # another liquid: no pair
            _row("P1", "UV-aged PS MPs + Cd", "-30"),  # an additive the virgin rows lack
            _row("P2", "UV-aged PS MPs", "-50"),  # another paper's virgin is not its own
        ]
    )
    p = aging.pairs(rows)
    assert len(p) == 1
    assert p.delta_mV.iat[0] == -35 - statistics.median([-20, -22])
    assert p.kind.iat[0] == "photo" and p.virgin_rows.iat[0] == 2


def test_the_committed_pairs_match_the_zeta_table_by_hand() -> None:
    table = {r["row_id"]: r for r in csv.DictReader(open(aging.D1, encoding="utf-8"))}
    pairs = list(csv.DictReader(open(aging.PAIRS, encoding="utf-8")))
    assert pairs, "run tool/p2/aging.py first"
    for p in pairs:
        aged = table[p["aged_row"]]
        virgins = [table[r] for r in p["virgin_row_ids"].split(";")]
        assert all(v["pmcid"] == aged["pmcid"] for v in virgins)
        assert all(v["medium_text"] == aged["medium_text"] for v in virgins)
        assert all(v["pH"] == aged["pH"] for v in virgins)
        assert all(v["ionic_strength_mM"] == aged["ionic_strength_mM"] for v in virgins)
        want = float(aged["value"]) - statistics.median(float(v["value"]) for v in virgins)
        assert abs(float(p["delta_mV"]) - want) < 1e-9, p["aged_row"]


def test_the_verdicts_follow_the_rules_committed_before_the_run() -> None:
    out = json.loads(aging.OUT.read_text())
    a, b = out["P11a"], out["P11b"]
    share = a["papers_more_negative"] / a["papers"]
    want_a = "supported" if share >= 2 / 3 else "refuted" if share <= 1 / 2 else "partly"
    assert a["verdict"] == want_a
    ratio = b["ci_width"] / a["ci_width"]
    want_b = "supported" if ratio >= 2 else "refuted" if ratio < 1 else "partly"
    assert b["verdict"] == want_b


def test_a_salt_series_pairs_level_by_level() -> None:
    # PMC11543686 writes "Na +" for three concentrations; the first run pooled the three levels
    rows = pd.DataFrame(
        [_row("P1", "PS", v, medium="Na +", i=i) for v, i in (("-40", "1"), ("-30", "10"))]
        + [_row("P1", "PS(UV)", v, medium="Na +", i=i) for v, i in (("-45", "1"), ("-33", "10"))]
    )
    p = aging.pairs(rows).sort_values("aged_mV")
    assert list(p.delta_mV) == [-5.0, -3.0] and list(p.virgin_rows) == [1, 1]
