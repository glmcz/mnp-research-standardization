# Dataset search agent

Finds open microplastic datasets beyond NCEI, and decides from the files themselves whether one
can join the survey table (`tool/survey/`). Results and what was ingested:
`docs/2026-10-23-dataset-validation.md`, "Finding more datasets".

```
unset VIRTUAL_ENV
uv run --with openpyxl python tool/discover/run.py search   # candidates, filtered (no model)
uv run --with openpyxl python tool/discover/run.py all      # + Claude triage + verification
uv run --with openpyxl python -m pytest -q -p no:cacheprovider tool/discover
```

Writes `out/tables/dataset_candidates.csv` (every candidate, the stage it reached, and why it
stopped) and `out/tables/dataset_search.json` (the funnel).

## Models read, code decides

1. **`catalog.py` (search).** It queries the DataCite API for the 15 queries in `QUERIES`.
   - DataCite indexes Zenodo, figshare, Dryad, PANGAEA, Mendeley and most university
     repositories.
   - Versions of one dataset collapse to the newest (same title and publisher).
   - A code filter (`about_plastic`) keeps records that name micro- or nanoplastic.
2. **`triage.py` (Claude).** Claude (`claude-sonnet-5`, through `tool/hybrid/agents.ask`) reads
   the metadata only, in batches of 12, and answers in a fixed JSON contract: kind, matrix,
   coordinates, dates, size window, tabular, concentrations.
   - A malformed batch is retried once, then left unclassified, never guessed.
   - `worth_verifying` is a rule over the answer; the model does not choose what is opened.
3. **`verify.py` (code).** It lists the files through the host's API (Zenodo, figshare, PANGAEA,
   Mendeley, Dryad, Dataverse) and opens the tables (csv, xlsx, PANGAEA tab, zip).
   - Each column gets a role from its header: lat, lon, date, size, concentration.
   - `is_concentration` requires plastic and a per-volume, mass or area unit.
   - **usable:** concentration, coordinates, date and at least 20 rows.
   - **partial:** a concentration without one of the others.
   - **not_usable, no_table, not_verifiable, error.**
   - A record that cites or derives from an NCEI DOI is flagged (`ncei_overlap`).

"Usable" means the table has the columns. It is not ingested until `tool/survey/table.py` pins
it by sha256 with its setting, method, unit and lower size limit, read from the dataset's own
description.

## Caching

Every HTTP response is cached under `data/raw/discover/http/` and every triage answer under
`data/raw/discover/triage/`, keyed by the request (both gitignored). A rerun reads the same answers.
The User-Agent names the project only.
