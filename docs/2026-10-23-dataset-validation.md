# Validating the survey datasets, 2026-10-23

Code: `tool/survey/` (table, validators, P7, report). Tests: `tool/survey/test_survey.py`
(16 tests; four mutations each turn one red). Outputs: `out/tables/survey_*.{csv,json}`.

## The table

One table, `data/interim/survey/records.csv.gz` (rebuilt, gitignored), of 26 552 records from 11
datasets:

- NCEI: 18 461 (ocean water, beach, ocean sediment);
- MP-SED: 1 064 (sediment);
- soil (Wu et al.): 6 197;
- the PANGAEA Weser fractions: 46.
- Found and verified by the search agent (below):
  - EMODnet Baltic and Kattegat trawls: 217;
  - the Fu 2023 atmospheric compilation: 62;
  - five PANGAEA sets: 343 beach cores (882220), 79 subsurface pumps (941107), 34 net tows
    (941076), 29 sediment cores (928578), and 20 ship-pump FTIR samples from the eastern Pacific
    shelf (990052).

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

5. **Across databases, the window decides first** (`survey_colocated.json`, `across_datasets`).
   - Within 50 km and a year, only 3 record pairs exist across databases: EMODnet against NCEI,
     ×1.18 apart.
   - Within 100 km in any year (the place held, the time not), there are 70 pairs:
     - 57 EMODnet–NCEI pairs, nets of 330 µm against 333 µm, median ×1.5 (×7.2 at the 90th
       percentile), a median 2 years apart. These are caveated, not refused.
     - 13 NCEI–990052 pairs: nets against a 10 µm ship pump. 990052 states only its lower
       limit, so (from 2026-10-24) its upper limit is 5 mm by the field's convention, as the
       reviewer said and as NCEI applies.
       - 9 pairs are refused, with a median gap of ×68 000. Seven are against 300–335 µm nets
         (the conversion spans ×4–70) and two against grab samples filtered at 0.45 µm. In
         each case the conversion's range is wider than ×10.
       - 4 pairs, against a 150 µm plankton net, are caveated. The window predicts the pump
         counts ×2.9–26 more; it counts ×492–4 091 more. After the most generous conversion
         ×22 is left (the median residual), so the window is not the explanation.
   - A refused pair is counted and shown, but never enters the summary fold. A caveated pair is
     never dropped for disagreeing (that would bias toward agreement); it reports its residual,
     the fold left after the window conversion. The raw 90th percentile of all 70 pairs is
     ×29 000.
   - The between-study summaries in findings 2 and 3 stay inside NCEI, as the hybrid's questions
     ask.

## Finding more datasets: the search agent

`tool/discover/` (README there). One DataCite search reaches Zenodo, figshare, Dryad, PANGAEA,
Mendeley and university Dataverse repositories.

| stage | how | count |
|---|---|---|
| found | 15 queries, DataCite datasets | 1 132 |
| distinct | one record per title and publisher (versions collapse) | 711 |
| on topic | code: the record names micro- or nanoplastic | 700 |
| to open | Claude reads the record; a code rule over its answer picks what to open | 272 |
| usable | code opens the files: concentration, coordinates, date, 20+ rows | 12 |

- **Of the 12 usable:** two are flagged as overlapping NCEI (986752, and a Zenodo ASV set). Of
  the other ten:
  - five PANGAEA sets are new in the table;
  - three were in it already (the soil compilation, the two Weser fractions);
  - one is macro-litter (923730);
  - the global mangrove Dataverse set (154 rows) is not ingested yet.
- **Partial (16):** a concentration without coordinates or a date, e.g. the Seine (6 322 rows) and
  the Colombian Caribbean. These are leads, not data.
- **Not verifiable (136):** no public file API (the publisher's site, a journal supplement, a
  login).
- **The first run overcounted.** It passed a water-chemistry table (`O2 sat [mg/l]`) and two
  particle-size tables as concentrations. A concentration column now has to name plastic and a
  per-volume, mass or area unit (`verify.is_concentration`, test-first).
- **Left out:** PANGAEA 986752 (eastern tropical Pacific), whose per-sample abundance column is
  ambiguous (`table.py`).

## Aging, the same particle before and after (PREREG P11, idea B)

`tool/p2/aging.py`, `out/tables/p2_aging_pairs.csv`, `out/tables/p2_aging.json`.

- **Coverage.** There are 77 aged zeta values in 20 papers. Only 9 papers measure the same
  particle before and after in the same liquid (46 pairs), and 7 of those use light or an oxidant.
- **P11a: partly.** In 4 of 7 papers the aged particle is more negative, in 2 less, and in 1 the
  same. The median is −4.7 mV (95 % interval −11.7 to +0.4).
- **P11b: partly.** Unpaired, the interval is ×1.6 as wide; ×2 was predicted.
- **Scale, chosen after the results.** Between papers, virgin polystyrene's per-paper median has
  an interquartile range of 25 mV. Aging's ~5 mV is visible only paired.
- **PMC12475273 prints its aged and virgin values swapped.** Its Methods and its Discussion give
  the two values the other way round.
- **Two coding defects** were found by reading the pairs and fixed test-first: O3 was not read as
  ozone, and one salt series was pooled across its levels. The verdicts did not change, and the
  first run's numbers are kept in the PREREG.

## The hybrid agent against naive Claude (PREREG P8–P10)

The same 19 questions, two runs each, claude-sonnet-5 throughout (`tool/hybrid/`):

| arm | correct |
|---|---|
| Claude from memory | 11 % |
| Claude with the data pasted in | 32 % |
| the hybrid | 100 % |

- **Paired:** the hybrid is right where pasted-data Claude is wrong 26 times; the reverse never
  happens.
- **Without the guard:** Claude flags every question that needs a flag. But it also flags most
  that do not, and answers only 17 % of the plain questions correctly. The pre-registered
  expectation (that it would miss flags) was wrong in direction.
- **Without the grounding check:** 0.13 numbers per answer that the computation never produced.
- **Limit:** the questions were written with the operations in mind, so the planner's choice is
  easy. This measures the guard, the arithmetic and the grounding, not open-ended planning.
