# Validating the survey datasets, 2026-10-23

Code: `tool/survey/` (table, validators, P7, report). Tests: `tool/survey/test_survey.py`
(12 tests; four mutations each turn one red). Outputs: `out/tables/survey_*.{csv,json}`.

## The table

One table, `data/interim/survey/records.csv.gz` (rebuilt, gitignored), of 25 768 records:

- NCEI: 18 461 (ocean water, beach, ocean sediment);
- MP-SED: 1 064 (sediment);
- soil (Wu et al.): 6 197;
- the PANGAEA Weser fractions: 46.

A field the source does not give stays empty. Completeness (`survey_completeness.csv`):

- **MP-SED:** no record has coordinates or a date; 9 % have no year; 1.5 % code the lower size
  limit as 99999.
- **Soil:** no record names a sampling method; 18 % have no year.
- **NCEI:** complete on these fields, apart from 0.25 % without a mesh size. Its 5 mm upper bound
  is the database's rule, not each study's.

## Findings

1. **The same samples are held twice** (`survey_duplicates.csv`). Run blind, the duplicate check
   flags 5 study pairs: same day, within 2 km, at least 10 records each.
   - It finds the known Reisser/Eriksen tows (171 and 170 records, 0.79 km apart, median ratio
     0.98).
   - The other four pairs, flagged by the check and not yet read:

     | setting | records | median distance | median value ratio |
     |---|---|---|---|
     | ocean water | 36 and 38 | 1.3 km | 1.000001 (identical) |
     | beach | 11 and 29 | 1.1 km | 0.998 |
     | ocean water | 48 and 48 | 0 km | 1.31 |
     | ocean water | 17 and 17 | 0.4 km | 2.19 |

   - "Held twice" is the check's reading. Which paper reports which tow is for the database's
     maintainers to confirm.
2. **The same place, different numbers** (`survey_colocated.json`). Independent studies (the
   duplicate pairs excluded) with the same method, within 50 km and a year:
   - 981 record pairs from 18 study pairs;
   - median ×3.3 apart, ×17.7 at the 90th percentile;
   - with any method allowed, the 90th percentile is ×50;
   - in the Mediterranean: ×3.9 and ×21.4.
3. **The 100× rise that is several things** (PREREG P7).
   - The pooled NCEI ocean-water median rises ×94 from the 2000s to the 2020s.
   - Inside Law et al. 2010's own series it stays flat (ρ −0.02; P7a supported).
   - Two of five long series do rise ×10 or more (P7b refuted). One is the North Pacific gyre,
     where a published increase over four decades exists. The other is Law 2014, whose rise halves
     inside its own accumulation zone, because later cruises sampled the zone more.
4. **The window decides the count.** This exists already (P1, the Weser pair, MPsizeBase).
   - The window check refuses to convert between the Weser fractions: no single slope in α
     1.3–2.2 gives a factor within ×10.
   - It allows a 333 µm count to be compared with a 300 µm count with a factor of 1.06–1.14.
