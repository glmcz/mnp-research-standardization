# MNP-KB v0 — micro- and nanoplastic surface measurements, with absence recorded

**Scope: read this first.**

- **What it is.** The surface charge of micro- and nanoplastic particles as measured in liquids in laboratory studies: 1 903 rows from 467 papers, 1 840 zeta potentials and 63 electrophoretic mobilities (`d1_zeta_table.csv`).
- **Measured in a liquid.** A zeta potential exists only in a liquid, so every value describes the particle in the liquid it was measured in, not in the environment it came from.
- **Where the particles came from.** 95.4 % of rows (1 815 / 1 903) measure a synthetic particle, bought or made in a lab. Only 12 rows, from 3 papers, measure particles collected from a real environment: 11 from wastewater effluent (2 papers) and 1 classed "other" (1 paper). From air or dust, freshwater, seawater, soil or sediment: 0 rows. Agent-checked: a Claude agent gave every environmental particle and samples of the rest a second reading with the paper's full text; no person has checked these counts (`sample_origin_stats.json`, REVIEW.md C11).
- **The measurement liquids.** Rows per `medium_class`: DI water 474, culture medium 317, salt solution 232, buffer 167, environmental water 28, biofluid 20, other 262, unreported 403.
- **The corpus.** The open-access subset of one database (Europe PMC) for one query: 1 115 hits, 862 of them open access, 858 full texts fetched, 467 papers with a measurement (`d1_stats.json`). What that leaves out: `docs/2026-09-30-corpus-scope-notes.md`.
- **What it can be used for.** How laboratory measurements are reported and whether they can be compared. Not how plastics behave in air, water or soil.

1903 surface-charge measurements extracted from 467 open-access papers, each with the conditions it was measured under — and, where those conditions were not reported, an explicit record that they were not.

**Every number in this card was computed when the card was built**, from `out/tables/d1_zeta_table.csv` and `out/tables/d1_stats.json`, and the particles' origin from `out/tables/sample_origin_stats.json`. None is typed in. Rebuild the card and any number that has moved will move with it.

Two things a reader should take from this card before using the data: only a small minority of published measurements are fully conditioned, and the accuracy scores for this extraction have not yet been audited by a human.

## Files

| file | what it is | sha256 |
|---|---|---|
| `dataset.parquet` | 1903 rows × 44 columns | `268b2853f00f40b7b73dba086e20398ea5ba8a4f49f5756ed0769f018d0802ff` |
| `dataset.jsonl` | the same rows, one JSON object per line | `027acd243d241457e61c8da13788595870d8104bb6a2941eb7826e88bc294647` |
| `schema.json` | JSON Schema 2020-12 for the record type, generated from the pydantic models in `mnp.schema.models`; the release's own evidence columns are `$defs/ReleasedEvidence` | `8976dc57ec31847920e727058140f0cb737356452ce4b5c8e28d449dd50edc4d` |
| `LICENSE` | CC BY 4.0, and the attribution line | `e11af74d9ed4f47fc35f3f679bdf4c9e3cd01e2eb69de613847c44fc0adc3667` |
| `DATASET_CARD.md` | this file | — |

The parquet and the JSONL carry identical content; the two formats exist so the dataset can be read without pandas. `schema.json` describes the nested record the extraction produces, of which the flat table here is one row per measurement.

## Scale

| | |
|---|---|
| rows (one surface measurement each) | 1903 |
| papers | 467 |
| distinct `material` values | 95 |
| columns | 44 |
| rows carrying a printed number | 1289 |
| rows reporting a measurement with no retrievable number | 614 |
| **fully conditioned rows** (`conditions_complete`) | **46 / 1903 — 2.4 %** |
| evidence quotes found verbatim in the source | 1903 / 1903 — 100.0 % |

Source corpus: 858 XML files, vendored as one archive of 27747267 bytes (27.7 MB), sha256 `9791cc01550bbd840060e0265dc985644971b2d77a479a223a0fddccb989305b`.

## 2.4 % of rows are fully conditioned

Fully conditioned rows: **46 / 1903 — 2.4 %**. Those are the rows carrying all five of the conditions needed to interpret the number — dispersion medium, ionic strength, pH, temperature and instrument. Every other row is missing at least one of them.

This is the dataset's finding, not a defect in it. A zeta potential without its ionic strength is not a property of the particle; it is a property of one unrecorded experiment. The dataset exists to make that countable.

Row-level reporting of each condition:

| condition | rows reporting it | |
|---|---|---|
| Dispersion medium | 1500 / 1903 | 78.8 % |
| Ionic strength | 240 / 1903 | 12.6 % |
| pH | 352 / 1903 | 18.5 % |
| Temperature | 438 / 1903 | 23.0 % |
| Instrument | 1659 / 1903 | 87.2 % |

## Absence is a value, not a gap

The five `*_reported` booleans are the reason this dataset exists. `ionic_strength_reported = False` is a **positive claim**: this paper did not report the ionic strength of the medium it measured in. It is not a null, not a missing value, and not an encoding of uncertainty. It is deterministically checkable against the source article, which is why it can be used as ground truth.

Nothing is imputed. A condition that was not reported is never filled with a conventional default: **`not measured` is never written as 0.0 and never as 1.0**, because both are claims nobody checked. Where a paper reports a measurement but prints no number, `value` is null and `value_text` says so; where the ionic strength was inferred from a named salt rather than stated, `ionic_strength_source` records that it was inferred.

Some readings are cleared rather than kept, by rules ratified on 2026-09-28 and 29. R1: an ionic strength of exactly 0 mM is not a reported one: "no added electrolyte" says nothing was added, not that the medium holds no ions, so the row reads `ionic_strength_reported = False` and carries `ionic_strength_zero_not_reported` (8 rows). R2: a temperature tied to an incubation or exposure step is not the measurement temperature, even when the paper gives no other, so it is removed and the row carries `temperature_step_not_measurement` (4 rows). R2b: nor is a temperature the row's own quote does not state when its source prints it only for storage, incubation, exposure or culture — a medium label such as "RPMI (stored at 37 ˚C for 24 h)", or, when the row prints it nowhere, a paper that gives it only for such a step; the row carries `temperature_from_other_step` (0 rows). The rows stay; the extraction record keeps the number the model read.

This makes one query answerable that a text index cannot answer: *what ionic strength did this paper use?* when the true answer is that it never said. There is no passage to retrieve for that, so a retrieval system fabricates the nearest number. Here it is a boolean.

## Every quote is verbatim

`evidence_verified` is true for every row here: **1903 / 1903 — 100.0 %**. Each row names the sentence or sentences the value was read from, and each was checked as a substring of the source article's text. A row whose quote could not be located was dropped and counted, never silently kept. Where the source's licence does not allow the quote to ship, the row carries its address and hash instead of its text — see *Licence* below.

`evidence_quote` may join several passages with ` || `, because the value and its conditions are routinely sections apart — the number in Results or a table, the ionic strength in Methods. `evidence_location` names each.

**Read the limit with the number.** Verbatim means the quote exists in the article. It does not mean the value was read from it correctly; that is what the extraction scores below measure, and they are provisional.

## Where each quote sits in the paper

`evidence_line_ids` carries **1903 / 1903 — 100.0 %** of rows, 4221 citations in all. A citation is a 16-character prefix of the SHA-256 of a line's section path, its ordinal within that section, and its normalised text — deliberately not the line number, so that a later fix to the parser which shifts numbering does not invalidate a stored address.

The ids are semicolon-joined, flat, in the order the passages appear in `evidence_quote`. The grouping back onto ` || ` passages is not stored because it is recoverable: the quote is here, and re-running the locator reproduces it — or, for a withheld quote, `evidence_quote_spans` carries it. An empty value means the row carries a flag saying why, and no row is silently left without one.

## Paper-level denominators

Counted over papers rather than rows, and taken from `out/tables/d1_stats.json`, which is the artefact these numbers are published from.

| | |
|---|---|
| papers with at least one verified measurement | 467 |
| **papers omitting at least one of the five conditions** | **456 / 467 — 97.6 %** |
| open-access records the query returned | 862 |
| all hits, including paywalled | 1115 |

Per condition, over papers, with 95 % Wilson intervals:

| missing condition | papers | | 95 % CI |
|---|---|---|---|
| Dispersion medium | 138 / 467 | 29.6 % | 26–34 % |
| Ionic strength | 429 / 467 | 91.9 % | 89–94 % |
| pH | 390 / 467 | 83.5 % | 80–87 % |
| Temperature | 373 / 467 | 79.9 % | 76–83 % |
| Instrument | 82 / 467 | 17.6 % | 14–21 % |
| Any condition | 456 / 467 | 97.6 % | 96–99 % |

Of 858 fetched XMLs, 11 carry no retrievable text at all — conference-abstract volumes and PDF-only deposits. They were not read and found to report nothing, and are counted apart from papers that were.

## The κ audit has not been done

Extraction accuracy for this dataset is scored against a gold set of rows read from the papers, `data/interim/annotation/gold_50.csv`. **That gold set was annotated by Claude and has not been audited by a human.**

Its 153 rows over 50 papers carry these annotators: `claude-opus-gold` 153. Rows re-judged independently by a human: **0**.

A blind worksheet for that re-judgement exists — `data/interim/annotation/audit_10.csv`, ten of the gold papers with every judged column blanked — and it has not been filled in. **No inter-annotator agreement statistic (Cohen's κ) is published with this release, because none has been computed.**

Consequence for anyone using this dataset: **every extraction quality score associated with it is provisional.** The gold set is a second pass by the same family of model that produced the extractions, so it can agree with them for reasons that have nothing to do with the articles. The rows themselves are verbatim-checked against the source and do not depend on the gold set; the *scores* do.

## Provenance, and how coarse it is

Every row carries `pmcid`, `doi`, `model` and `prompt_sha256` — the hash of the extraction prompt that produced it.

**Only 2 distinct `prompt_sha256` values occur across all 1903 rows, so prompt provenance is currently coarse.** A row can be traced to one of a very small number of prompts, not to the exact brief revision it was read under. Do not treat `prompt_sha256` as a fine-grained experimental key.

The hashes present:

- `7b89a830e2b2f0ef3b98adf614521cb254771a04bac2b587580ced642cf8f393`
- `b3790c68b0ed28cb2b3f8ef42d2738438aba1ff45efff89985f1bf003a78edf1`

Models that produced these rows: `claude-code:opus`, `claude-code:sonnet`.

## Licence — CC BY 4.0

This dataset is released under the **Creative Commons Attribution 4.0 International licence (CC BY 4.0)**, <https://creativecommons.org/licenses/by/4.0/>. The notice and the attribution line are in `LICENSE`. The decision was taken on 2026-09-28.

**What is a fact and what is a quote.** The extracted values, units and conditions and the absence booleans are facts about what each paper reports. They ship for every row whatever the source's licence, with the row's source licence code and, where the quote is withheld, its address and hash. The evidence quotes are verbatim text from the source articles. A quote ships only where its source is licensed CC BY (any version) or CC0, which already permit redistribution with attribution. For every other source — non-commercial, no-derivatives, share-alike, a publisher's own terms, a statement that is ambiguous, or no licence statement at all — the quote is withheld: `evidence_quote` is null, `quote_withheld` is true, and the text is in no file of this release.

Per source licence, as each paper's own JATS states it (`source_licence`, read from the vendored XML by `mnp.corpus.licence`: a creativecommons.org URL is preferred, the wording decides where there is none):

| source licence | papers | rows | quotes shipped | quotes withheld |
|---|---|---|---|---|
| `CC-BY` | 335 | 1369 | 1369 | 0 |
| `CC0` | 2 | 91 | 91 | 0 |
| `CC-BY-NC` | 27 | 112 | 0 | 112 |
| `CC-BY-NC-ND` | 84 | 285 | 0 | 285 |
| `other-named` | 10 | 20 | 0 | 20 |
| `none` | 9 | 26 | 0 | 26 |
| **total** | 467 | 1903 | 1460 | 443 |

Quotes withheld: **443 / 1903 — 23.3 %** of rows, from 130 papers. `other-named` is a statement that names no Creative Commons licence, or whose URL and wording disagree — a publisher's own terms, *public domain unless otherwise noted*, a time-limited access grant. `none` is an article with no licence statement at all. Both are withheld: an unclear grant is not a grant.

**Restoring withheld quotes locally.** A withheld row keeps `evidence_quote_sha256`, the hash of the original quote, and `evidence_quote_spans`, its address in the source: a JSON array of `[line_id, start, end]` slices of the article's line-addressed text, joined by glue that holds only separators, whitespace and dashes — never a letter or a digit. With the source articles on your machine:

```
uv run python -m mnp.corpus restore      # the vendored articles
uv run python -m mnp.report rehydrate [--release out/release] [--out <path>]
```

`rehydrate` rebuilds each article's lines, slices them, checks every result against its sha256, and writes a local copy of the dataset with the quotes put back — never into this directory. With `--fetch` it downloads an article missing from the corpus from Europe PMC. A quote that no longer matches its hash is reported and left null, never approximated. That local copy carries text under its sources' licences, not this one; keep it local.

**The source articles keep their own licences.** Nothing here relicenses them, and their full texts are not in this release. Every row names its source by `pmcid` and `doi`: fetch the article from its publisher or from Europe PMC, under the terms its publisher applies. A quote shipped from a CC BY source remains its authors' work, attributed by that row's `pmcid` and `doi`.

This is a licensing decision, not legal advice.

## Limits a citer needs to state

1. **One database.** Every paper here came from Europe PMC: 467 papers with a verified measurement, drawn from 862 open-access records the query returned. OpenAlex indexes roughly three times as much of this literature. Adding it would change every denominator on this card, and would therefore be a different study rather than a larger version of this one. **Do not read these fractions as fractions of the literature.** They are fractions of one database's open-access subset.

2. **Open access only.** Full text was fetched only where Europe PMC serves it. The lower bound against all 1115 hits, paywalled included, is reported in `d1_stats.json` for that reason.

3. **Extraction scores are provisional** until the κ audit above is done.

4. **Prompt provenance is coarse** — see above.

5. **A row is a reported measurement, not a verified physical quantity.** The quote is checked against the article; the article is not checked against reality.

6. **Absence is absence of reporting.** `pH_reported = False` means the paper did not state a pH. It does not mean the experiment had no pH.

7. **The measured particles are synthetic.** 1815 / 1903 — 95.4 % of rows measure a particle bought ready-made or made in a lab. 12 rows, from 3 papers, measure a particle collected from a real environment (wastewater 11, other 1); from air or dust: 0. The values describe manufactured particles in laboratory liquids, not how micro- and nanoplastics behave in the environment. A reader classified every row, and a Claude agent gave every environmental one and a sample of the rest a second reading with the paper's full text; no person has checked them (`out/tables/sample_origin_stats.json`, `out/review/REVIEW.md` C11).

## Columns

| group | columns |
|---|---|
| study | `pmcid`, `doi`, `year`, `journal`, `row_id` |
| measurement | `quantity`, `value`, `value_text`, `unit`, `sd`, `n` |
| particle | `particle_name`, `material`, `functionalisation`, `supplier`, `size_nominal_nm`, `size_measured_nm` |
| conditions | `medium_text`, `medium_class`, `ionic_strength_mM`, `pH`, `pH_text`, `temperature_C`, `temperature_qualifier`, `instrument` |
| absence | `medium_reported`, `ionic_strength_reported`, `pH_reported`, `temperature_reported`, `instrument_reported`, `conditions_complete`, `ionic_strength_source`, `medium_matches_exposure` |
| evidence | `evidence_quote`, `evidence_location`, `evidence_verified`, `evidence_line_ids`, `evidence_quote_sha256`, `evidence_quote_spans` |
| licence | `source_licence`, `quote_withheld` |
| provenance | `model`, `prompt_sha256`, `flags` |

## How to rebuild this

```
uv run python -m mnp.report d1        # the table and d1_stats.json
uv run python -m mnp.report origin    # sample_origin_stats.json
uv run python -m mnp.report release   # this directory
uv run python -m mnp.report reproduce # rebuild everything offline and diff it
```

`reproduce` rebuilds the published artefacts from the vendored corpus with the network refused and compares them byte for byte. The dataset is derived, not hand-curated: nothing in this directory is edited by hand, including this card.
