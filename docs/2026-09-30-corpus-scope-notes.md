# Corpus scope notes — 2026-09-30

**Decision (Martin, 2026-09-30): stay with the corpus we have. Do not enlarge it now, but write
down what it leaves out.** This file is that record, for a later session and for Martin. The
scope block that now opens REVIEW.md, the dataset card, the demo and the results page states the
consequence to every reader; this file gives the reasons and the cheapest way to test them.

Numbers are as of commit `d3d89c9` (branch `line-addressed-citations`). Each one names the file
it comes from. They are typed here because this is a dated note; the generated documents compute
theirs.

## What the 491 papers are

One query, sent to one database, Europe PMC, on 2026-09-11 (`README.md`, "The corpus is
vendored"). The query, verbatim from `data/raw/epmc/search/hit_counts.json` (`query_all`):

```
(nanoplastic* OR microplastic* OR "plastic nanoparticle*" OR "polystyrene nanoparticle*") AND (METHODS:"zeta potential" OR METHODS:"electrophoretic mobility" OR METHODS:"zetasizer" OR "zeta potential" OR "electrophoretic mobility") AND NOT PUB_TYPE:"review"
```

`query_oa` in the same file, and `queries/q1.txt`, add `AND OPEN_ACCESS:y`.

| step | count | from |
|---|---|---|
| hits, open access or not | 1 115 | `hit_counts.json` → `hits_all` |
| open-access hits | 862 | `hit_counts.json` → `hits_oa` |
| full texts fetched | 858 | `out/tables/d1_stats.json` → `text_availability.fetched`; `data/raw/epmc/manifest.sha256` |
| papers with a measurement | 491 | `d1_stats.json` → `n_papers` |
| rows | 1 890 | `out/tables/d1_zeta_table.csv` |

Between 862 and 858 sit three records dropped by `epmc.records_to_frame` (no PMCID or a DOI
duplicate) and one fetch that failed with HTTP 404 (PMC9027246). Of the 858 XMLs, 848 reached
the extraction as a record; 11 carry no retrievable text (`out/review/REVIEW.md` §2).

What the 491 hold, after the hand check (`out/tables/sample_origin_stats.json` →
`hand_corrected`): 1 784 of 1 890 rows (94.4 %) measure a synthetic particle, bought (1 290) or
made in a lab (494). 19 rows (1.0 %), from 4 of 491 papers (0.8 %), measure particles collected
from a real environment: 18 from wastewater effluent in 3 papers, and 1 classed `other` in 1
paper, the borderline filtrate of a PP-bottle injection solution (`hand_check.disagreements`,
PMC12474203). From air or dust, freshwater, seawater, soil or sediment: 0 rows.

## What the corpus leaves out, and why each gap may raise the synthetic share

Each "why" below is a hypothesis. None has been tested.

1. **253 paywalled hits were never read** (1 115 − 862, `hit_counts.json`). Full text was
   fetched only where Europe PMC serves it. *Why it may bias:* deposit in PMC is driven most
   strongly by biomedical funders, and biomedical work on plastic particles (uptake, toxicity,
   corona) is where bought polystyrene beads are the standard material. Environmental-science and
   wastewater-engineering papers, where collected particles would appear, are more often in
   subscription or hybrid journals. If so, the unread 253 hold a larger environmental share than
   the 491 we read.

2. **One database.** Europe PMC indexes the life-science literature and leans biomedical. The
   card's limit 1 says OpenAlex indexes roughly three times as much of this literature (a
   sentence typed in `src/mnp/report/release.py`, `_limits_section`). Its basis is
   `docs/ARCHITECTURE_PLAN.md` §8, measured 2026-09-13: OpenAlex held 3 513 works on the topic
   against Europe PMC's 1 117 at the time, 77 % of them open access, and of 600 OpenAlex works
   sampled, 22 % were already in the corpus and 78 % were not. The query behind the 3 513 is not
   recorded in the repo. *Why it may bias:* the same as gap 1, one step earlier. The journals
   Europe PMC does not index are disproportionately environmental and engineering journals.

3. **The query term `"polystyrene nanoparticle*"`.** The other three terms name plastic as a
   pollutant. This one names the model particle of nanotoxicology and drug-delivery work, which
   is almost always bought. A paper that measures polystyrene nanoparticles and never says
   nanoplastic or microplastic enters through this term alone, and there is no matching term that
   admits collected samples the pollutant terms would miss. *Why it may bias:* it adds papers
   that are synthetic by construction.

4. **Non-English literature (e.g. CNKI, Wanfang).** Europe PMC holds 4 Chinese-language works on
   the topic (`LANG:"chi"`), CNKI and Wanfang are subscription databases with no open API, and
   China-affiliated groups, about 29 % of the field in OpenAlex (1 002 works), mostly publish in
   English-language journals (`docs/ARCHITECTURE_PLAN.md` §8). *Why it may bias:* national
   monitoring surveys of rivers and treatment plants may be published domestically, in Chinese.
   The direction is the least certain of the four, and the measured numbers suggest a small
   return.

**What a larger corpus would not change.** A zeta potential needs a stable dispersion with
enough particles to measure. Bought beads give that; plastic isolated from an environmental
sample rarely does. Part of the 94.4 % is a property of the measurement, not of the sampling, and
no corpus choice removes it. The gaps above can move the share; they cannot make it
representative of plastic in the environment.

## What is reachable

From `../nanoSolve-backend/docs/sources.md` (measured 2026-09-27):

- **Discovery is mostly solved.** OpenAlex searches title and abstract with boolean queries.
  After the OpenAlex and PubMed fixes, every further source added 0–3 MNP papers a month
  ("Discovery is saturated"). Finding the papers is not the limit.
- **Full text is the limit.**
  - Europe PMC JATS covers the open-access subset only, which is the corpus we already have.
  - Unpaywall is a full-text locator, not a discovery source: 20 of 40 sampled MNP DOIs had an
    open-access copy, mostly on Wiley, doi.org, PMC and Springer. Most of those are PDFs, so
    they need PDF parsing through `papertext` (S1b), which no consumer uses yet.
  - OpenAlex content (GROBID TEI) needs `OPENALEX_API_KEY`: of 50 fresh MNP works, 10 were
    flagged `has_content`, and 2 of the 6 tried downloaded. GROBID scored 2.10/10 on scientific
    tables (arXiv 2603.18652), so a charge value read from TEI needs a second rendering before it
    is believed.
  - Hermes' `pdf_fetch` (pypdf) is live but weak: tables, columns and minus signs are
    unreliable. A dropped minus sign turns −32 mV into 32 mV.
- **Publisher text and data mining** (Elsevier, Wiley, Springer Nature) needs an institutional
  licence. This is part of the 2026-09-30 decision, not a measurement, and `sources.md` does not
  cover it. `sources.md` records only that the proprietary Wiley Scholar Gateway is unreachable
  by decision (2026-09-27).

A PDF-derived row would also be a different tier from a JATS-derived one: the line addresses,
the quote check and the licence reading in this repo all assume JATS XML.

## The cheapest test, when this is revisited

The question is whether the environmental share here, 1.0 % of rows and 0.8 % of papers, is a
property of the field or of this corpus.

1. **OpenAlex count for the same query.** OpenAlex has no `METHODS:` field, so send the same
   terms once through `title_and_abstract.search` and once through `fulltext.search`, and record
   both counts, the date and the exact query strings. Minutes, no model.
2. **Abstract-level origin classification of what we could not read.** Europe PMC returns the
   abstracts of the 253 paywalled hits (`query_all` minus `query_oa`). Ask the origin question
   the reader already asks (bought, made in a lab, collected, unclear) of each abstract, and do
   the same for a seeded sample of OpenAlex works not in the corpus. An abstract describes a
   paper, not rows, so compare with the paper share: 4 of 491 papers with an environmental row
   (0.8 %, `sample_origin_stats.json` → `hand_corrected.origin.papers_any`), not the 1.0 % row
   share. Classify a sample of our own 491 from their abstracts too, to measure how often an
   abstract leaves the origin unsaid; without that the comparison has no baseline.
3. **The polystyrene term, locally.** Count the papers among the 491 whose full text matches
   only through `"polystyrene nanoparticle*"`, and their synthetic share. A regex over the
   vendored XMLs approximates Europe PMC's match; it needs no network.

If the unread papers' environmental share is several times ours, the synthetic share is a
property of this corpus, and the scope statement already says the numbers are this corpus's. If
it is about the same, the finding stands for the field's open and closed literature alike.

## Decision

Not now (Martin, 2026-09-30). The corpus stays at 491 papers. Every reader-facing document opens
with the scope block instead (`src/mnp/report/scope.py`), which states the origin numbers, the
single database and the single query, and points here.
