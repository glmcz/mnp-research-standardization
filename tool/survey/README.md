# Survey datasets, validated by code

One table of concentration records from four datasets, and the checks that decide whether two of
those numbers may be compared. Findings: `docs/2026-10-23-dataset-validation.md`; the
pre-registered timeline test: `docs/PREREG_2026-10.md`, P7.

```
unset VIRTUAL_ENV
uv run --with openpyxl python tool/survey/table.py    # data/interim/survey/records.csv.gz (gitignored)
uv run --with openpyxl python tool/survey/report.py   # out/tables/survey_{duplicates,completeness}.csv, survey_colocated.json
uv run --with openpyxl python tool/survey/p7.py       # out/tables/survey_p7.json
uv run --with openpyxl python -m pytest -q -p no:cacheprovider tool/survey
```

- `table.py` reads NCEI, MP-SED, the soil compilation (Wu et al.) and the PANGAEA Weser
  fractions through `tool/p2`'s pinned loaders. It holds no path or checksum of its own. A field
  a source lacks stays null.
- `validators.py` holds the checks:
  - duplicates: the same day, within 2 km, another study;
  - the size-window factor over α 1.3–2.2, with a refusal when it spans more than ×10;
  - units;
  - co-location;
  - change within a series, and pooled periods;
  - completeness.
- Each check is tested on a known case or toy data, and four mutations each turn a test red.
- A pandas column named `flags` collides with `DataFrame.flags`. Always use `t["flags"]`.
