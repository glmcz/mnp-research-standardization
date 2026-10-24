"""The gap table, each of its own numbers recomputed another way.

uv run --with openpyxl python -m pytest -q -p no:cacheprovider tool/gaps
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import ladder  # noqa: E402


def _rows():
    return {(r["family"], r["differs"]): r for r in ladder.own()}


def test_case_14_is_the_two_rows_apart() -> None:
    rows = {r["row_id"]: r for r in csv.DictReader(open(ROOT / "out/tables/d1_zeta_table.csv"))}
    a, b = (float(rows[k]["value"]) for k in ladder.CASE14)
    assert _rows()[("charge", "the paper, the batch")]["value"] == abs(a - b) == 34.0


def test_the_amine_range_is_over_named_liquids_with_ten_values() -> None:
    by: dict[str, list[float]] = {}
    for r in csv.DictReader(open(ROOT / "out/tables/p2_zeta_size.csv")):
        if r["surface"] == "amine" and r["material_group"] == "PS":
            by.setdefault(r["medium_class"], []).append(float(r["zeta_mV"]))
    meds = [
        statistics.median(v) for k, v in by.items() if k in ladder.NAMED_LIQUIDS and len(v) >= 10
    ]
    got = _rows()[("charge", "the liquid")]["value"]
    assert abs(got - (max(meds) - min(meds))) < 1e-9


def test_the_window_gap_is_the_river_median() -> None:
    ratios = [float(r["small"]) / float(r["large"])
              for r in csv.DictReader(open(ROOT / "out/tables/p2_weser_pairs.csv"))
              if float(r["large"]) > 0]  # fmt: skip
    got = _rows()[("count", "the size window")]["value"]
    assert abs(got - statistics.median(ratios)) < 1e-9


def test_every_own_row_names_its_source_and_both_sides() -> None:
    aging = json.loads((ROOT / "out/tables/p2_aging.json").read_text())
    rows = ladder.own()
    assert len(rows) == 9
    assert all(r["held_same"] and r["differs"] and r["source"] for r in rows)
    assert _rows()[("charge", "aged or not")]["value"] == abs(aging["P11a"]["median_delta_mV"])


def test_a_quote_counts_only_if_the_page_prints_it(monkeypatch) -> None:
    import scout_check as sc

    page = (
        b"<html><body><p>Zeta potential was \xe2\x88\x9242.0 \xc2\xb1 4.2 mV across 8 "
        b"laboratories</p><script>var x = 'not text';</script></body></html>"
    )
    monkeypatch.setattr(sc.catalog, "get", lambda url: page)
    item = {"family": "A", "name": "t", "url": "u", "material": "latex", "unit": "mV",
            "spread_kind": "sd", "spread": "4.2", "central": "-42.0", "labs": "8",
            "quote": "Zeta potential was -42.0 ± 4.2 mV across 8 laboratories"}  # fmt: skip
    kept = sc.check(item)
    assert kept["kept"] and kept["value"] == 4.2  # a Unicode minus on the page, a hyphen quoted
    assert not sc.check(item | {"quote": "Zeta potential was -40 mV"})["kept"]
    assert not sc.check(item | {"spread": "5.1"})["kept"]  # the number must sit in the quote


def test_spreads_become_gaps_in_their_family_unit() -> None:
    import scout_check as sc

    a = {"family": "A", "unit": "mV"}
    assert (
        sc.gap(a | {"spread_kind": "per_lab", "spread": "Lab1 -30; Lab2 -38(2); Lab3 -41"})[0] == 11
    )
    assert sc.gap(a | {"spread_kind": "cv", "spread": "10 %", "central": "-40"})[0] == 4
    assert (
        sc.gap({"family": "A", "unit": "µm cm/Vs", "spread_kind": "sd", "spread": "0.2"})[0] is None
    )
    b = {"family": "B", "unit": "particles/L"}
    assert sc.gap(b | {"spread_kind": "range", "spread": "20 to 80"})[0] == 4
    assert abs(sc.gap(b | {"spread_kind": "cv", "spread": "50 %"})[0] - 3.0) < 1e-12


def test_percent_spreads_become_folds_only_below_one_hundred() -> None:
    import scout_check as sc

    quote = "The reproducibility, SR, ranged from 62%-117% (for PE) and 45.9%-62% (for PET)."
    item = {"family": "B", "unit": "%", "spread_kind": "other", "spread": "", "quote": quote}
    lo, _, hi = sc.gap(item)
    assert abs(lo - 1.459 / 0.541) < 1e-9 and abs(hi - 1.62 / 0.38) < 1e-9  # 117 % is left out
    # a percentage whose sentence does not say it is a spread is not read as one
    vague = item | {"quote": "Counts varied considerably between laboratories (29-91%)."}
    assert sc.gap(vague)[0] is None


def test_a_recovery_is_not_a_spread_and_layout_does_not_break_a_quote(monkeypatch) -> None:
    import scout_check as sc

    quote = "recoveries of ca. 83 % were obtained, with precisions of ca. 18 %,"
    item = {"family": "B", "unit": "%", "spread_kind": "other", "spread": "", "quote": quote}
    lo, _, hi = sc.gap(item)
    assert abs(lo - 1.18 / 0.82) < 1e-9 and hi == lo  # 83 % is a recovery, not a spread
    # a PDF splits compounds and lines; the letters and digits still have to match in order
    pdf_text = "The reproducibility, SR, in thermo-\nanalytical experiments ranged from 62%−117%"
    quote = "The reproducibility, SR, in thermo-analytical experiments ranged from 62%−117%"
    assert sc.skeleton(quote) in sc.skeleton(pdf_text)
    assert sc.skeleton("ranged from 62%") not in sc.skeleton("ranged from 6.2%")


def test_only_items_whose_quote_code_found_reach_the_table() -> None:
    verified = list(csv.DictReader(open(ROOT / "out/tables/gap_scout_verified.csv")))
    kept = {r["url"] for r in verified if r["kept"] == "True"}
    published = ladder.published()
    assert published and {r["source"] for r in published} <= kept
    assert len(published) == sum(r["kept"] == "True" for r in verified)
