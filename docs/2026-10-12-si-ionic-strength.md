# Does the Supplementary Information hold the missing ionic strength?

Asked by Martin, 2026-10-12, after the review call (`docs/2026-10-10-review-call.md`, item 6). The
reviewer said concentrations and buffers often sit only in the Supplemental Information. The
extraction read main texts only: `src/mnp/corpus/jats.py` drops `<supplementary-material>`. So
every reporting rate so far meant "stated in the main text". This document checks the SI of every
validated paper: all 467 papers and 1 903 rows in `out/tables/d1_zeta_table.csv`, where every row
has `evidence_verified = True`.

## Answer

**The SI adds little.** Ionic strength stays the least-reported condition, now counting the SI too.

| ionic strength reported | main text (as published so far) | main text + SI | upper bound |
|---|---|---|---|
| papers with any row | 38 of 467 (8.1 %) | **43 (9.2 %)** | 47 (10.1 %) |
| rows | 240 of 1 903 (12.6 %) | **262 (13.8 %)** | — |
| mean share of a paper's rows | 7.2 % | 8.2 % | — |

- **The SI supplied an ionic strength for 22 rows in 6 papers**, 5 of which had none before. Of the
  429 papers with no ionic strength in the main text, the SI rescues 5 (1.2 %).
- **The upper bound** adds 4 more papers whose SI states the ionic strength of the zeta liquid. In
  those papers a main-table row lumps several salt levels or media, so no single row can take one
  value (see "Series the main table collapsed").
- **Source:** `out/tables/si_rates.json`, written by `tool/si_scan/verify.py` (counts and the
  accepted row ids; the quotes stay in the gitignored `data/interim/si_scan/`).

The reviewer's point holds for some papers but does not move the headline. Where the SI does help,
it fills rows whose main text names **no liquid at all**: 11 of the 22 rows are `medium_class =
unreported`, 9 are `other`, and 2 are `environmental_water`. No DI-water or salt-solution row
changed.

## How it was checked

```
467 papers ─► JATS lists SI? ── no ─► 77 papers (no SI at all)
                 │ yes (390)
                 ▼
        fetch from PMC OA bucket ─► 548 files, 134 videos/images skipped, 5 unavailable
                 ▼
        text: pdftotext / textutil / xlsx / pptx ─► 553 files with text, 11 scanned PDFs
                 ▼
        scan with the extraction's own rules (code) ─► candidates in 109 papers (112 with mass units)
                 ▼
        read each candidate paper (model: 3 Sonnet readers, 100 packets)
                 ▼
        verify each claim (code): quote verbatim, value printed, RC-08, RC-10
                 ▼
        second reading of every accepted claim + 20 random non-candidates (session)
```

1. **Fetch** (`tool/si_scan/fetch.py`). The paper's own JATS `<supplementary-material>` decides
   what counts as SI. Files come from the public PMC Open Access bucket (`pmc-oa-opendata`), with
   an md5 check against S3. 502 files are verified, and 46 were multipart uploads with no md5 to
   check. 134 media files are skipped and logged: 64 mp4, 32 tif, 15 avi, 14 mov, 2 rar and
   others. Also logged: 3 files over 80 MB, 1 missing from the bucket, 1 publisher link.
2. **Text** (`to_text.py`). Each file is turned into text, or into "no_text" for 11 scanned PDFs.
   11 papers have SI but no readable text (`si_unreadable`).
3. **Scan** (`scan.py`). It imports `mnp.extract.coerce`, so a "statement" means what it means in
   the main text: "ionic strength" or "salinity" next to a concentration, or a molar concentration
   bound to a named salt (RC-02). A buffer's concentration is not one (RC-10). A broad second net
   (salt, electrolyte, buffer and seawater words near a zeta mention) and a detector for salts in
   mass units feed the reading step, because the strict rules miss table layouts.
4. **Read** (`packets.py`, brief `tool/si_scan/READER_BRIEF.md`). Every paper with an open row and
   any hit got a packet: 100 papers. Three Sonnet readers (the extraction's model family) decided
   per row: `is_stated`, `salt_composition`, or a non-claim (`buffer_only`, `di_water_only`,
   `mass_units_composition`, `other_step`, `series_unmapped`, `nothing`). The rule that matters
   most: the liquid must be the one **the zeta potential was measured in**, not an aggregation,
   exposure or transport liquid.
5. **Decide** (`verify.py`). A claim counts only if its quote is verbatim in the SI file and
   prints the value (`zeta._ionic_number_in`, `coerce.parse_ionic_strength`). 0 mM is unreported
   (RC-08), and a buffer's concentration is not an ionic strength (RC-10). All 22 claims passed.
6. **Second reading** (this session). Every accepted claim was re-read against the paper's rows,
   and all 22 stand (notes below). Then 20 random papers the scan did **not** nominate were
   checked:
   - 10 that mention zeta in the SI were read at every zeta mention;
   - 10 whose SI never mentions zeta were searched for salt, recipe and ionic-strength words.

   No missed ionic strength was found. One missed **mass-unit recipe** was found (PMC13185065),
   and the detector for those was added because of it. Its 3 extra papers were checked at
   their recipe hits: 1 recipe is the zeta liquid's (PMC13185065), 2 belong to other steps.

## Where the 429 papers without a main-text ionic strength stand

| SI status (`scan.py` category) | papers |
|---|---|
| no SI listed in the JATS | 70 |
| SI listed, no readable text | 11 |
| SI never mentions zeta, and holds no salt or ionic-strength statement | 166 |
| SI mentions zeta, and nothing salt-like is near it | 88 |
| salt or electrolyte words near zeta (broad net only) | 72 |
| strict statement near a zeta mention | 10 |
| strict statement elsewhere in the SI | 12 |

Reading the last three groups (94 of these papers, plus the 6 that already had a main-text value)
gave the 5 new papers above. The rest record why the SI did not help:

- **The SI names a buffer, not a salt** (9 papers). Examples: "phosphate buffer (10 mM, pH 7)",
  PBS, HEPES, 10 mM Tris-HCl. Under RC-06 and RC-10 these stay unreported.
- **The SI confirms DI or ultrapure water** (6 papers). PMC13432928 adds "a drop of 150 mM NaCl
  to ensure conductivity", which gives the stock and not the final concentration.
- **The SI gives salts in mass units only** (2 papers recorded). One is 0.9 % saline; the other
  is PMC13185065's phagolysosomal simulant fluid in g/L. The readers' notes name two more:
  PMC10458608's digestion juices in mg, and PMC8915914's Instant Ocean in g/L. The extraction
  never converts mass units, so these stay unreported. Each is convertible from the recipe with
  molar masses alone, so it is the cheapest upgrade if Martin wants one.
- **The salt belongs to another step**: aggregation (PMC10624164, "I ≈ 90 mM"), transport,
  sorption, a membrane's zeta (PMC13376387), or a DLVO model.

## The 6 papers the SI rescued

| paper | rows | SI says | second reading |
|---|---|---|---|
| PMC10952355 (Angew. Chem. 2023, CC BY) | r1 | "electrophoretic characterization of the copolymer dispersions diluted to 0.1% w/w using 1 mM KCl as background electrolyte" | the SI's zeta method itself → 1 mM |
| PMC11840474 (Small 2025, CC BY-NC) | r1–r7 | the SI's zeta method dilutes every sample in 10 mM KCl for the pH 3–10 series (paraphrased) | the main text names no liquid; this is the same measurement → 10 mM |
| PMC11990826 (ES&T 2023, CC BY-NC-ND) | r1, r2 | the SI gives the background electrolyte's ionic strength per seawater salinity: 170 mol/m³ at 10 psu and 580 mol/m³ at 34 psu (paraphrased) | the main text orders the values (−10.47 → −5.36 mV with rising salinity), so r1 = 10 psu and r2 = 34 psu; stated in the DLVO section |
| PMC13181784 (J. Phys. Chem. Lett. 2026, CC BY) | r2, r4 | "The pH dependent electrophoretic mobility data determined for the NPLs at 1 mM ionic strength" | main text: "measured in aqueous dispersions (Figure S3)" → 1 mM |
| PMC13298883 (J. Phys. Chem. 2026, CC BY) | r5–r8 | "zeta potential … as a function of pH in 0.3 mM NaCl" (Fig. S1 caption) | r1–r4 already had 0.3 mM from the main text; only the titration rows lacked it |
| PMC9370236 (Nanomaterials 2022, CC BY) | r1–r6 | Table S1: "Ionic strength (I) (mmol·L−1) 8.95 + 9.00 = 17.95 17.72 + 9.00 = 26.72" | columns are Chironomus, then Amphibian; 9 mM of each is tap water, from the Paris water utility's data |

## Series the main table collapsed (the upper bound)

In 6 papers, 4 of them with no main-text ionic strength, the SI states the ionic strength of the
zeta liquid at several levels, but a main-table row stands for the whole series:

- PMC11912305: Table S3 gives PS and PVC zeta at Ca 10, 50, 100, 500 and 1 000 mM.
- PMC7918465: Table S1 gives the ionic strength of BG11 (23.77) and COMBO (5.98).
- Also PMC12069638, PMC13213765, PMC11644253 and PMC9455956.

This is a granularity limit of the table, not absence in the paper. Splitting those rows would
count them properly. It also matters for the curve plan (slide 17, "measured curves run through
it: 0"): **PMC11912305's SI is a measured zeta-versus-salt series for two named plastics.** The
same holds for PMC9455956 and PMC13213765, which give zeta across several electrolyte levels.

## The other thing the SI holds: values

- 569 rows (175 papers) carry `value_not_printed`.
- For 122 of them (30 papers), the row's `evidence_location` names an SI table or figure, for
  example "values in Table S3" (PMC10458608).
- The SI text for those is now on disk. Reading the values is a separate, larger job, not done
  here.

## Limits

- **The corpus is open access**, because the extraction needed the full text. The reviewer's
  "SI is open even when the paper is paywalled" is not tested here. That needs the paywalled
  papers' SI, which this corpus does not have.
- **The SI as PMC holds it.** 77 papers list no SI in their JATS. A publisher page may still
  carry one that PMC never received; that is not checked.
- **Media and scans.** 134 media files and 11 scanned PDFs were not read; OCR was not attempted.
- **The broad net and the hand sample are the recall evidence.** 0 misses in 20 non-candidates
  still allows a miss rate up to 14 % (exact one-sided 95 % bound). Half of that sample was a
  word search, not a full read.
- **The readers are a model.** Sonnet decided all 100 packets, and code checked every claim. The
  "nothing" verdicts were not re-read except through the readers' own uncertainty notes. Those
  notes are where the series cases came from.
- **`d1_zeta_table.csv` is unchanged.** These SI values live in
  `data/interim/si_scan/si_verdicts_checked.jsonl`. Merging them would change the reported rates
  and the pair counts behind the 29 075 pairs lost to absence, and it needs a register entry.
  That decision is Martin's.

## What this changes

- **Slide 8** ("It's a lab. Just assume the water.") still stands: 0 DI-water rows gained an ionic
  strength from the SI. Its "0 of 403 rows whose liquid is not named" becomes "11 of 403" if the
  SI counts. The script's Q&A can say: "We checked the supplements too: 8.1 % of papers becomes
  9.2 %."
- **Review call, item 6**: answered. The reviewer is right that some conditions live only in the
  SI (5 papers here), and wrong that this rescues the comparison.

## Re-run

See `tool/si_scan/README.md`. Inputs and outputs under `data/raw/pmc_si/`, `data/interim/si_text/`
and `data/interim/si_scan/` are third-party text and are gitignored. The reader verdicts are
`data/interim/si_scan/verdicts_{0,1,2}.jsonl`, plus `verdicts_3.jsonl` for the second reading.
