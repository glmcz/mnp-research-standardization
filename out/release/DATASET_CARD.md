# MNP-KB v0 — micro- and nanoplastic surface measurements, with absence recorded

1890 surface-charge measurements extracted from 491 open-access papers, each with the conditions it was measured under — and, where those conditions were not reported, an explicit record that they were not.

**Every number in this card was computed when the card was built**, from `out/tables/d1_zeta_table.csv` and `out/tables/d1_stats.json`. None is typed in. Rebuild the card and any number that has moved will move with it.

Two things a reader should take from this card before using the data: only a small minority of published measurements are fully conditioned, and the accuracy scores for this extraction have not yet been audited by a human.

## Files

| file | what it is | sha256 |
|---|---|---|
| `dataset.parquet` | 1890 rows × 40 columns | `ffa54c448f4de7c480cc6674edb35773520920cb65c9e7eb69d0d0113fb7a71c` |
| `dataset.jsonl` | the same rows, one JSON object per line | `a3c5c4abed5e583e5a5342fb66efa5a8dff1214ef5c3d20be24c952fd25fc0c0` |
| `schema.json` | JSON Schema 2020-12 for the record type, generated from the pydantic models in `mnp.schema.models` | `bb28b3a5029452a5649ad6e574daa9daf6ca7daded71a4d7d7cb5f2490278cc3` |
| `DATASET_CARD.md` | this file | — |

The parquet and the JSONL carry identical content; the two formats exist so the dataset can be read without pandas. `schema.json` describes the nested record the extraction produces, of which the flat table here is one row per measurement.

## Scale

| | |
|---|---|
| rows (one surface measurement each) | 1890 |
| papers | 491 |
| distinct `material` values | 151 |
| columns | 40 |
| rows carrying a printed number | 1384 |
| rows reporting a measurement with no retrievable number | 506 |
| **fully conditioned rows** (`conditions_complete`) | **62 / 1890 — 3.3 %** |
| evidence quotes found verbatim in the source | 1890 / 1890 — 100.0 % |

Source corpus: 858 XML files, vendored as one archive of 27747267 bytes (27.7 MB), sha256 `9791cc01550bbd840060e0265dc985644971b2d77a479a223a0fddccb989305b`.

## 3.3 % of rows are fully conditioned

Fully conditioned rows: **62 / 1890 — 3.3 %**. Those are the rows carrying all five of the conditions needed to interpret the number — dispersion medium, ionic strength, pH, temperature and instrument. Every other row is missing at least one of them.

This is the dataset's finding, not a defect in it. A zeta potential without its ionic strength is not a property of the particle; it is a property of one unrecorded experiment. The dataset exists to make that countable.

Row-level reporting of each condition:

| condition | rows reporting it | |
|---|---|---|
| Dispersion medium | 1572 / 1890 | 83.2 % |
| Ionic strength | 269 / 1890 | 14.2 % |
| pH | 402 / 1890 | 21.3 % |
| Temperature | 529 / 1890 | 28.0 % |
| Instrument | 1679 / 1890 | 88.8 % |

## Absence is a value, not a gap

The five `*_reported` booleans are the reason this dataset exists. `ionic_strength_reported = False` is a **positive claim**: this paper did not report the ionic strength of the medium it measured in. It is not a null, not a missing value, and not an encoding of uncertainty. It is deterministically checkable against the source article, which is why it can be used as ground truth.

Nothing is imputed. A condition that was not reported is never filled with a conventional default: **`not measured` is never written as 0.0 and never as 1.0**, because both are claims nobody checked. Where a paper reports a measurement but prints no number, `value` is null and `value_text` says so; where the ionic strength was inferred from a named salt rather than stated, `ionic_strength_source` records that it was inferred.

This makes one query answerable that a text index cannot answer: *what ionic strength did this paper use?* when the true answer is that it never said. There is no passage to retrieve for that, so a retrieval system fabricates the nearest number. Here it is a boolean.

## Every quote is verbatim

`evidence_verified` is true for every row here: **1890 / 1890 — 100.0 %**. Each row carries the sentence or sentences the value was read from, and each was checked as a substring of the source article's text. A row whose quote could not be located was dropped and counted, never silently kept.

`evidence_quote` may join several passages with ` || `, because the value and its conditions are routinely sections apart — the number in Results or a table, the ionic strength in Methods. `evidence_location` names each.

**Read the limit with the number.** Verbatim means the quote exists in the article. It does not mean the value was read from it correctly; that is what the extraction scores below measure, and they are provisional.

## Where each quote sits in the paper

`evidence_line_ids` carries **1890 / 1890 — 100.0 %** of rows, 3899 citations in all. A citation is a 16-character prefix of the SHA-256 of a line's section path, its ordinal within that section, and its normalised text — deliberately not the line number, so that a later fix to the parser which shifts numbering does not invalidate a stored address.

The ids are semicolon-joined, flat, in the order the passages appear in `evidence_quote`. The grouping back onto ` || ` passages is not stored because it is recoverable: the quote is here, and re-running the locator reproduces it. An empty value means the row carries a flag saying why, and no row is silently left without one.

## Paper-level denominators

Counted over papers rather than rows, and taken from `out/tables/d1_stats.json`, which is the artefact these numbers are published from.

| | |
|---|---|
| papers with at least one verified measurement | 491 |
| **papers omitting at least one of the five conditions** | **477 / 491 — 97.1 %** |
| open-access records the query returned | 862 |
| all hits, including paywalled | 1115 |

Per condition, over papers, with 95 % Wilson intervals:

| missing condition | papers | | 95 % CI |
|---|---|---|---|
| Dispersion medium | 127 / 491 | 25.9 % | 22–30 % |
| Ionic strength | 440 / 491 | 89.6 % | 87–92 % |
| pH | 392 / 491 | 79.8 % | 76–83 % |
| Temperature | 383 / 491 | 78.0 % | 74–81 % |
| Instrument | 90 / 491 | 18.3 % | 15–22 % |
| Any condition | 477 / 491 | 97.1 % | 95–98 % |

Of 858 fetched XMLs, 11 carry no retrievable text at all — conference-abstract volumes and PDF-only deposits. They were not read and found to report nothing, and are counted apart from papers that were.

## The κ audit has not been done

Extraction accuracy for this dataset is scored against a gold set of hand-checked rows in `data/interim/annotation/gold_50.csv`. **That gold set was annotated by Claude and has not been audited by a human.**

Its 153 rows over 50 papers carry these annotators: `claude-opus-gold` 153. Rows re-judged independently by a human: **0**.

A blind worksheet for that re-judgement exists — `data/interim/annotation/audit_10.csv`, ten of the gold papers with every judged column blanked — and it has not been filled in. **No inter-annotator agreement statistic (Cohen's κ) is published with this release, because none has been computed.**

Consequence for anyone using this dataset: **every extraction quality score associated with it is provisional.** The gold set is a second pass by the same family of model that produced the extractions, so it can agree with them for reasons that have nothing to do with the articles. The rows themselves are verbatim-checked against the source and do not depend on the gold set; the *scores* do.

## Provenance, and how coarse it is

Every row carries `pmcid`, `doi`, `model` and `prompt_sha256` — the hash of the extraction prompt that produced it.

**Only 2 distinct `prompt_sha256` values occur across all 1890 rows, so prompt provenance is currently coarse.** A row can be traced to one of a very small number of prompts, not to the exact brief revision it was read under. Do not treat `prompt_sha256` as a fine-grained experimental key.

The hashes present:

- `3a50d97a5880d5acae5db0911acbca7376446e8050c08843e38c6c6f924efd1d`
- `b3790c68b0ed28cb2b3f8ef42d2738438aba1ff45efff89985f1bf003a78edf1`

Models that produced these rows: `claude-code:opus`, `claude-code:sonnet`.

## Licence — UNRESOLVED

**This release does not yet carry a licence. That is an open decision, not an oversight, and it is recorded here so nobody assumes one.** Do not redistribute this dataset until it is settled.

What is at issue. The source articles are open access, but their licences differ from paper to paper, and the dataset redistributes short verbatim quotes from them.

| | |
|---|---|
| redistributed here | extracted values, conditions, the absence booleans, and short verbatim evidence quotes |
| **not** redistributed here | the full texts of the source articles |

Every row names its source by `pmcid` and `doi`, so the article itself can always be fetched from the publisher under whatever licence that publisher applies.

Licence statements across the 858 fetched articles — 109 distinct strings, which is why they are grouped here by the Creative Commons code named in the statement:

| licence named in the article | articles |
|---|---|
| CC BY | 534 |
| CC BY-NC-ND | 139 |
| CC BY-NC | 41 |
| CC BY-ND | 2 |
| no Creative Commons URL in the statement | 142 |
| no licence statement at all | 16 |

Note the last two rows. A non-commercial or no-derivatives term on a source article is not automatically satisfied by quoting from it, and the papers with no statement at all are not automatically permissive.

## Limits a citer needs to state

1. **One database.** Every paper here came from Europe PMC: 491 papers with a verified measurement, drawn from 862 open-access records the query returned. OpenAlex indexes roughly three times as much of this literature. Adding it would change every denominator on this card, and would therefore be a different study rather than a larger version of this one. **Do not read these fractions as fractions of the literature.** They are fractions of one database's open-access subset.

2. **Open access only.** Full text was fetched only where Europe PMC serves it. The lower bound against all 1115 hits, paywalled included, is reported in `d1_stats.json` for that reason.

3. **Extraction scores are provisional** until the κ audit above is done.

4. **Prompt provenance is coarse** — see above.

5. **A row is a reported measurement, not a verified physical quantity.** The quote is checked against the article; the article is not checked against reality.

6. **Absence is absence of reporting.** `pH_reported = False` means the paper did not state a pH. It does not mean the experiment had no pH.

## Columns

| group | columns |
|---|---|
| study | `pmcid`, `doi`, `year`, `journal`, `row_id` |
| measurement | `quantity`, `value`, `value_text`, `unit`, `sd`, `n` |
| particle | `particle_name`, `material`, `functionalisation`, `supplier`, `size_nominal_nm`, `size_measured_nm` |
| conditions | `medium_text`, `medium_class`, `ionic_strength_mM`, `pH`, `pH_text`, `temperature_C`, `temperature_qualifier`, `instrument` |
| absence | `medium_reported`, `ionic_strength_reported`, `pH_reported`, `temperature_reported`, `instrument_reported`, `conditions_complete`, `ionic_strength_source`, `medium_matches_exposure` |
| evidence | `evidence_quote`, `evidence_location`, `evidence_verified`, `evidence_line_ids` |
| provenance | `model`, `prompt_sha256`, `flags` |

## How to rebuild this

```
uv run python -m mnp.report d1        # the table and d1_stats.json
uv run python -m mnp.report release   # this directory
uv run python -m mnp.report reproduce # rebuild everything offline and diff it
```

`reproduce` rebuilds the published artefacts from the vendored corpus with the network refused and compares them byte for byte. The dataset is derived, not hand-curated: nothing in this directory is edited by hand, including this card.
