# SI census: is the ionic strength in the supplement?

The extraction read main texts only: `src/mnp/corpus/jats.py` drops `<supplementary-material>`.
The 2026-10-10 reviewer said concentrations and buffers often sit in the Supplemental
Information. These scripts check that claim for every paper in `out/tables/d1_zeta_table.csv`.
Findings are in `docs/2026-10-12-si-ionic-strength.md`.

## Re-run

```
unset VIRTUAL_ENV
uv run --no-project python -I tool/si_scan/fetch.py out/tables/d1_zeta_table.csv data/raw/epmc/xml data/raw/pmc_si
uv run --no-project --with xlrd python -I tool/si_scan/to_text.py data/raw/pmc_si data/interim/si_text
uv run python -I tool/si_scan/scan.py out/tables/d1_zeta_table.csv data/raw/pmc_si data/interim/si_text data/interim/si_scan
uv run python -I tool/si_scan/packets.py out/tables/d1_zeta_table.csv data/interim/si_scan data/interim/si_text data/interim/si_scan/packets
# read each packet, write data/interim/si_scan/verdicts.jsonl (one line per row, see verify.py)
uv run python -I tool/si_scan/verify.py out/tables/d1_zeta_table.csv data/interim/si_text data/interim/si_scan/verdicts.jsonl data/interim/si_scan
```

- `fetch.py` pulls from the public PMC Open Access bucket (`pmc-oa-opendata`, S3). The Europe
  PMC `supplementaryFiles` zip works too, but it took minutes per paper. The JATS decides what
  counts as SI. Videos and images are skipped, and every file lands in `manifest.csv` with a
  status.
- `scan.py` imports the extraction's own rules (`mnp.extract.coerce`), so "stated in SI" means
  the same thing as "stated in the main text".
- `verify.py` decides. A reader's verdict counts only if its quote is verbatim in the SI and the
  value passes `zeta._ionic_number_in` / `parse_ionic_strength`, with RC-08 and RC-10 applied.

All outputs under `data/raw/pmc_si/`, `data/interim/si_text/` and `data/interim/si_scan/` are
third-party text and are gitignored. The one committed output is `out/tables/si_rates.json`: counts and the
accepted row ids, no quotes. The deck reads it.
