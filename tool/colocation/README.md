# Co-located microplastic concentrations (idea C, feasibility)

Can concentration measurements from different studies at the same place check each other?
Recon run 2026-10-12. Outputs are in `recon_2026-10-12/`, and the summary is in
`docs/2026-10-10-review-call.md`.

## Inputs (gitignored; refetch and check the sha256)

| file | source | sha256 |
|---|---|---|
| `data/raw/ncei/ncei_hub_microplastics.csv` | NOAA NCEI "Global Marine Microplastics Observations", ArcGIS item `1b56a456ad8c43889652e62aa25a317e`: `https://hub.arcgis.com/api/download/v1/items/1b56a456ad8c43889652e62aa25a317e/csv?redirect=true&layers=0`. 29 076 rows, server Last-Modified 2026-07-19, citation doi:10.25921/v8gj-k896 | `31bb1efdc948a4ee4d71c80df4e56d50c26e1b3905c1162139681d2ddc6bb5c5` |
| `data/raw/mpsed/data.json` | MP-SED (US ERDC), `https://doer.el.erdc.dren.mil/Data/data.json`. 1 064 records, 72 DOIs | `4896ca98df537ab0ed6bf56360dfe3f4235261f241d117e289f8ee4dac706d74` |

## Re-run

```
unset VIRTUAL_ENV
R="uv run --no-project --with pandas --with scipy python -I"
CSV=../../data/raw/ncei/ncei_hub_microplastics.csv
OUT=/tmp/colocation_out    # pairs_100km.csv.gz (~0.9 MB) is rebuilt, not kept
cd tool/colocation
$R profile.py $CSV; $R study_ids.py $CSV
$R colocate.py $CSV $OUT
for s in refine comparable_detail; do $R $s.py $CSV $OUT/pairs_100km.csv.gz; done
$R by_setting.py $OUT/pairs_100km.csv.gz
```

Pair rule: two records with different `DOI`, the same `Marine Setting`, a haversine distance
of 10, 50 or 100 km, and dates within 365 days or no limit. NCEI has already converted every
value to one unit per matrix, so a comparison here compares NCEI's conversions, not the
published numbers.
