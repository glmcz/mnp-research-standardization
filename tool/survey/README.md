# Survey datasets, validated by code

One table of concentration records from the datasets below (water, sediment, beach, soil), and the checks that decide whether two of
those numbers may be compared. Findings: `docs/2026-10-23-dataset-validation.md`; the
pre-registered timeline test: `docs/PREREG_2026-10.md`, P7.

```
unset VIRTUAL_ENV
uv run --with openpyxl --with pyreadr python tool/survey/table.py    # data/interim/survey/records.csv.gz (gitignored)
uv run --with openpyxl --with pyreadr python tool/survey/report.py   # out/tables/survey_{duplicates,completeness}.csv, survey_colocated.json
uv run --with openpyxl --with pyreadr python tool/survey/p7.py       # out/tables/survey_p7.json
uv run --with openpyxl --with pyreadr python -m pytest -q -p no:cacheprovider tool/survey
```

- `table.py` reads NCEI, MP-SED, the soil compilation (Wu et al.) and the PANGAEA Weser
  fractions through `tool/p2`'s pinned loaders, and pins the datasets added on 2026-10-23:
  - EMODnet's floating micro-litter monitoring nets: 217 Baltic and Kattegat tows, particles/m³,
    300–333 µm mesh. The tow line is binary geometry and is placed at its midpoint.
  - Five PANGAEA sets the search agent (`tool/discover/`) verified (`PANGAEA_FOUND`): each pinned
    by sha256 with its own setting, method, concentration column and lower size limit.
- Martin's datasets, fetched on 2026-10-24 and 2026-10-26 (`docs/2026-10-24-dataset-reference-list.md`,
  `fetch_user.py`): DURUM stormwater, RIVM's Dutch surface waters, and AOMI, the Japanese environment ministry's atlas of
  ocean-surface tows (particles/m³ under 5 mm, the mesh as the lower limit). AOMI holds 93 % of
  Isobe et al. 2021's samples, so it replaced that compilation, and about three in four of NOAA's
  ocean-water records, which the duplicate check finds before any comparison.
- Same place or out (Martin, 2026-10-26): a dataset whose records share no place with another
  study compares nothing, so Valine's Oregon rivers, the California drinking-water portal (a
  country, no place) and two single-cruise PANGAEA sets (941107, 928578) left the table. Two exceptions
  by design: MP-SED places by water body, and the Weser fractions compare two windows at the same
  stations. `test_every_dataset_shares_a_place_with_another_study` holds the rule.
  - Since 2026-10-28 a shared place counts only in a shared unit: `colocated` pairs records of one
    setting and one unit, and a record with no unit pairs with nothing. Two more sets left:
    SFEI's San Francisco Bay (microparticles, plastic or not, per m³ and per g) and PANGAEA
    882220 (beach sediment per litre) met other studies only in units no other study counts in.
    No headline moved: NCEI's own comparisons and the 365-day cross-database ones never mixed
    units.
- EMODnet's pan-European aggregate (2021) is not read: it gives a filtered volume only for 121
  Baltic samples and a tow length for the rest, so a value per m³ would need an assumed net depth.
- GeoPlasticoBR (fetched by Martin 2026-10-27): Brazilian studies on one map. Water, sediment and
  soil rows only (692 of 1,183): a bivalve's count is a body burden. It gives no sampling date and no
  size window, so it enters no 365-day comparison, only the any-year descriptive one. Its DOI
  column was filled down: inside a study the DOI counts up row by row into other papers' (Water
  Research 119707 is the Amazon study, 119708 is on steel corrosion; checked on PubMed), so a study
  is the first DOI its title carries in entry order, and the rest are flagged `doi_filled_down`.
  Rows entered twice are flagged `repeats_row`.
- One paper is one study in every database: a DOI however written (bare, `dx.doi.org`, any case)
  becomes one lower-case link. Before this, AOMI's `10.1088/…abbb4f` and
  `https://doi.org/10.1088/…abbb4f` were two studies. Across databases a pair of records from one
  paper is never a comparison (`report._independent`, `excluded_same_paper`): the duplicate check
  finds shared samples by date and place only, and had missed 1,162 of AOMI's and NOAA's
  same-window pairs, so the AOMI-against-NOAA fold moved from ×2.7 (1,948 pairs) to ×3.25 (786).
- After any change to the table, rerun `report.py` and `p7.py`;
  `test_the_committed_outputs_match_the_table_they_came_from` fails until both are.
- A field a source lacks stays null.
- One value is not as the database has it (`NET_DEPTH`, Martin, 2026-10-27). A surface tow's
  particles/m³ is the paper's particles/km² over a net depth; where the paper states that depth and
  the database's values imply another, the paper's is used and the record is flagged
  `depth_from_paper_…`. NCEI's Reisser 2013 Manta tows imply 0.085 m, which no NCEI field holds;
  Reisser's Methods give 0.17 m. AOMI holds NCEI's values for the same tows, so both copies (129 and
  140 records) are halved; the counts land in `survey_colocated.json`, `net_depth_from_paper`. The
  same tows under Eriksen 2014 imply 0.08 m and are all labelled Neuston net; Eriksen prints no net
  dimensions, so they keep the database's value, and the duplicate check keeps them out of every
  comparison.
- An EMODnet study is its organisation: a monitoring programme's cruises are one series, not
  independent studies, as an NCEI DOI is.
- `validators.py` holds the checks:
  - duplicates: the same day, within 2 km, another study;
  - the size-window factor over α 1.3–2.2, with a refusal when it spans more than ×10;
  - units;
  - co-location: between studies inside NCEI (`colocated_summary`), and between databases
    (`across_datasets`), where every record pair passes the window guard first and a refused pair
    never enters the fold;
  - change within a series, and pooled periods;
  - completeness.
- Each check is tested on a known case or toy data, and four mutations each turn a test red.
- A pandas column named `flags` collides with `DataFrame.flags`. Always use `t["flags"]`.
