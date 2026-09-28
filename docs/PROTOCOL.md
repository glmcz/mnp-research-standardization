# Protocol

**Generated from `src/mnp/protocol.py` — do not edit by hand.** Run
`uv run python -m mnp.report protocol` after changing the registry; a command with no entry
here, or an entry naming a command that no longer exists, fails the test suite.

Every step states what kind of result it produces, because the three are not the same thing:

| Kind | Meaning |
|---|---|
| deterministic | same input, same output |
| seeded | random, but pinned by a seed; the same seed reproduces the numbers |
| judgement | a human or a model decides — not reproducible, so it carries ground truth and a recorded brief instead |

`idem` — running it twice changes nothing the second time. `net` — reaches the network.

Start a fresh checkout with `corpus restore`, and check any claim of reproduction with
`report reproduce`.

## Corpus

### `corpus search`

Crawls Europe PMC for the query in queries/q1.txt and keeps every record that has a PMCID, deduplicating on DOI. It runs the unrestricted query once and reads the open-access flag per record, so the OA and the all-hits denominators come from the same page set rather than from two crawls taken minutes apart. The hit counts are written down because every fraction in D1 is reported against both.

- **in** queries/q1.txt, MNP_CONTACT_EMAIL
- **out** data/raw/epmc/search/records.parquet, hit_counts.json
- **kind** deterministic · idem yes · net yes
- **stale when** editing the query, or Europe PMC indexing new records

### `corpus fetch`

Downloads the full-text XML of every open-access hit at five requests a second, with three retries on 429 and 5xx, and a User-Agent carrying a contact address because Europe PMC asks for one. A file that exists and is non-empty is never fetched twice, so an interrupted run resumes for free. Failures go to fetch_log.csv rather than to silence.

- **in** records.parquet
- **out** data/raw/epmc/xml/PMC*.xml, fetch_log.csv
- **kind** deterministic · idem yes · net yes
- **stale when** a record being withdrawn or re-versioned upstream

### `corpus snapshot`

Freezes the fetched corpus into one archive and one manifest of sha256 per file. The archive is built deterministically — sorted names, fixed mode, no ownership, no timestamps, no gzip filename header — so an unchanged corpus always produces the same bytes and its hash can be quoted. Run it after a re-fetch and nowhere else.

- **in** data/raw/epmc/xml/
- **out** xml.tar.gz, manifest.sha256
- **kind** deterministic · idem yes · net no
- **stale when** any re-fetch; the archive hash changes and must be re-published

### `corpus verify`

Checks every XML on disk against the manifest and exits non-zero if anything is missing, changed, or extra. Extra files fail as loudly as missing ones: a corpus with one more paper in it is a different corpus, even when nothing is corrupt. This is the check every claim of reproduction starts from.

- **in** xml/, manifest.sha256
- **out** exit code, named differences
- **kind** deterministic · idem yes · net no
- **stale when** nothing — this is the check the others are measured against

### `corpus restore`

Unpacks the vendored archive into data/raw/epmc/xml/ and then verifies what it wrote. A tar member naming a path outside the target directory is refused rather than skipped. This is the first command on a fresh clone.

- **in** xml.tar.gz
- **out** data/raw/epmc/xml/PMC*.xml
- **kind** deterministic · idem yes · net no
- **stale when** a corrupt archive; restore verifies and refuses silently-wrong output

### `corpus parse`

Turns each JATS XML into the text an extractor actually reads: the methods sections, every table flattened with its caption and footnotes, the characterisation sections, and keyword windows around zeta and mobility mentions. Section selection is by sec-type with a title-regex fallback, and the result is capped to roughly twelve thousand tokens, preferring keyword windows. Re-parsing is free and idempotent, but it makes the scanner counts stored in each record stale — check them with extract recount --check.

- **in** data/raw/epmc/xml/
- **out** data/interim/articles.parquet
- **kind** deterministic · idem yes · net no
- **stale when** a parser change — re-parse, then `extract recount --check`

## Extraction

### `extract todo`

Lists the PMCIDs that have no record yet, so work can be handed out without two workers being given the same paper. It reads the live record file rather than a snapshot, which is what the first corpus run got wrong. With --with-values it narrows to papers where the scanner found a printed number; with --missing-brief it lists the opposite set — papers that already have a record but no brief hash, which is exactly the sweep's work list.

- **in** articles.parquet, extractions.jsonl
- **out** a list of PMCIDs on stdout
- **kind** deterministic · idem yes · net no
- **stale when** new records landing in extractions.jsonl

### `extract show`

Prints exactly what an extractor reads for one paper: the system prompt, then the article text. It is the same text the API path sends, so a subagent and a model are reading the identical input. Nothing is written; this is the read half of the two-path design.

- **in** articles.parquet, the prompt templates
- **out** stdout
- **kind** deterministic · idem yes · net no
- **stale when** a prompt edit — which changes the brief and therefore the hash

### `extract run`

The API path: an OpenAI-compatible model reads each paper and returns structured measurements, which then go through the same coercion, verification and coverage checks as any other path. It walks a model chain on 429 and 5xx, caches every reply by sha256 of model, system and user, and never re-bills a paper that already succeeded. This is judgement, so the record carries the model and the brief hash and is scored against the gold set.

- **in** articles.parquet, a model chain, a brief
- **out** extractions.jsonl, zeta_table.parquet
- **kind** judgement · idem yes · net yes
- **scored against** gold_50.csv
- **stale when** a brief or model change; both are recorded per record

### `extract ingest`

The subagent path: an agent supplies the JSON and this applies coercion, the verbatim-quote guard, the condition checks and the coverage count exactly as the API path would. It refuses to record anything without --brief (or an explicit --no-brief), because 833 existing records cannot be traced to instructions that no longer exist. Ingesting the same PMCID again replaces its record, so a worker can correct and resubmit.

- **in** a JSON reply, --brief, --model
- **out** one record in extractions.jsonl, rebuilt zeta_table.parquet
- **kind** judgement · idem yes · net no
- **scored against** gold_50.csv
- **stale when** a brief change; the record carries its brief hash

### `extract units`

Prints the units the article itself prints, per table column and per sentence, so a claimed unit can be checked against the paper rather than assumed. It is the inspection tool behind the unit cross-check that runs inside every ingest. Read-only.

- **in** one PMCID, the parsed article
- **out** stdout
- **kind** deterministic · idem yes · net no
- **stale when** a change to the unit scanner

### `extract table`

Rebuilds the derived row table and the extraction summary from the records, and writes nothing else. It exists because recount also rewrites the record file, and an offline replay must never write to the thing it is checking. The summary reports the provenance the records carry — including how many carry no brief — never the prompt the code happens to hold today.

- **in** extractions.jsonl
- **out** zeta_table.parquet, extraction_summary.json
- **kind** deterministic · idem yes · net no
- **stale when** new or corrected records

### `extract recount`

Recomputes the scanner counts stored in each record after a parser or scanner change, leaving every measurement exactly as it was. Those counts are a property of the scanner, not of the extraction, so a fix upstream makes all of them stale at once; 91 of 845 records were stale when this was last run. With --check it reports the staleness and exits non-zero without writing anything.

- **in** extractions.jsonl, articles.parquet
- **out** rewritten extractions.jsonl, zeta_table.parquet
- **kind** deterministic · idem yes · net no
- **stale when** a scanner change; `--check` reports staleness without writing

### `extract retrofit`

Gives every stored evidence quote the line address it already implies, without re-reading a paper or calling a model: each quote was verified verbatim against the article, so it locates in the line-addressed document by substring, and what is stored is the line id — the hash of (section path, ordinal, text) — so a later parser fix that renumbers the document leaves the citation standing. A one-off migration rather than a replay step, because an offline replay must not write to the record it is checking; --dry-run reports and writes nothing. The quote guard searched the whole article while the line document mirrors extraction_text, a subset of it, so a quote can be genuine and still fail to locate: those rows keep no ids, gain an evidence_not_located flag and are named in the output. Nothing is dropped — the count of what did not locate is the measurement.

- **in** extractions.jsonl, data/raw/epmc/xml/
- **out** evidence.line_ids on each record, rebuilt zeta_table.parquet
- **kind** deterministic · idem yes · net no
- **stale when** a parser change that alters section paths, ordinals or line text

### `extract review-measurand`

Lists papers where the thing measured may not have been the plastic — particles filtered out before the measurement, a supernatant analysed, or the zeta of another material exposed to plastic (ratified rule S8). It decides nothing: the rule is a judgement about what a paper measured, and no regex settles that. What it does is make sure the question is asked, since the rule was found by a worker reading one paper and most of the corpus has not been read under it.

- **in** articles.parquet, extractions.jsonl
- **out** a reviewable list on stdout
- **kind** deterministic · idem yes · net no
- **scored against** tests/edge/key.yaml S8 and the papers themselves
- **stale when** new records, or a change to what counts as the measurand

### `extract review-list`

Writes down every paper the extraction skips, with a link, marking those that discuss zeta or mobility without printing a number. A skip is a claim about a paper, so it is reviewable rather than silent. The list is deterministic, which is what lets the 342 papers with no measurement stand without a model reading them.

- **in** articles.parquet
- **out** out/tables/d1_papers_without_printed_values.{csv,md}
- **kind** deterministic · idem yes · net no
- **stale when** a scanner or parser change

## Evaluation

### `extract sample`

Draws the stratified gold sample by year band from a fixed seed, excluding the papers used to develop the prompt. The seed and the corpus together decide who gets annotated, so both are recorded. Changing either draws a different sample and invalidates the comparison.

- **in** articles.parquet, --seed
- **out** data/interim/annotation/sample_50.csv
- **kind** seeded · idem yes · net no
- **stale when** a different seed or a changed corpus — both change who is annotated

### `extract gold-merge`

Merges the annotator batches in gold_parts/ into one gold_50.csv with the agreed column set. Annotation happens in batches so it can be checked in batches; this is the only step that assembles them. It performs no judgement of its own.

- **in** data/interim/annotation/gold_parts/*.json
- **out** gold_50.csv
- **kind** deterministic · idem yes · net no
- **stale when** a new or corrected annotation batch

### `extract audit-sample`

Builds a blind worksheet of gold papers for the author to re-judge, which is what Cohen's kappa is computed from. Blind means the worksheet carries the papers and the fields, not the existing annotation. Until it is filled, every slide must say the gold set is annotated but not audited.

- **in** gold_50.csv, --n
- **out** data/interim/annotation/audit_10.csv
- **kind** seeded · idem yes · net no
- **stale when** a changed gold set

### `extract evaluate`

Scores the extraction against the gold set at row level and paper level, matching rows on PMCID, fuzzy particle name and medium class, with stated tolerances per field. Only the annotated papers are scored: a prediction on an unannotated paper is neither right nor wrong, and counting it as a false positive once drove precision to 0.05. The headline numbers are the accuracy of conditions_complete and of medium_matches_exposure.

- **in** zeta_table.parquet, gold_50.csv
- **out** out/tables/d1_precision_recall.csv, data/processed/evaluation.json
- **kind** deterministic · idem yes · net no
- **scored against** gold_50.csv
- **stale when** either side moving — re-run after every re-extraction

### `report gate`

Passes or fails an extraction against the gold set on thresholds stated in advance, optionally on one slice of papers. A field with no ground truth is not scored at all, because precision 0.00 on zero true positives says nothing. Provenance is part of the verdict: the gate reports how many records cannot be traced to a brief.

- **in** zeta_table.parquet, gold_50.csv, optional --slice
- **out** out/tables/gate.{json,md}
- **kind** deterministic · idem yes · net no
- **scored against** gold_50.csv
- **stale when** a threshold change, which is a decision and belongs in the changelog

### `report gates`

Runs all four gates in one pass — did the worker do the work and record its brief, does it agree with the ratified edge cases, does it agree with gold, and what did the run cost and yield — and reports all four rather than stopping at the first failure. It is the check that runs before a configuration is trusted on hundreds of papers. Twelve papers is indicative, not a result.

- **in** extractions.jsonl, tests/edge/key.yaml, gold, a slice
- **out** out/tables/gates.md
- **kind** deterministic · idem yes · net no
- **scored against** tests/edge/key.yaml and gold_50.csv
- **stale when** answering an edge case, which changes what gate 2 scores

### `eval cell`

Runs one one-shot cell of the tool-value grid (B or D) over the query set. Each question's prompt is built deterministically and handed to a headless `claude -p` reader with every tool, setting source and MCP server switched off, in a directory with no instruction file above it, so the prompt is the only thing it sees. The reader is pinned by full model id and a reply from any other model is refused. Resumes: a question already answered is never asked again, and a reader failure is retried rather than scored. --pilot asks two per kind first.

- **in** queries/kind_*.csv, d1_zeta_table.csv, the vendored corpus
- **out** data/interim/runs/<run>/: manifest, asked.txt, answers.jsonl, scores.tsv
- **kind** judgement · idem yes · net yes
- **scored against** the answer keys in queries/kind_*.csv, scored by mnp.eval.scoring
- **stale when** a change to the reader model, the system prompt, or any cell builder

### `eval score`

Re-scores a run's recorded answers with the model-free scorer, without asking anything. The denominator is asked.txt, written before any reading, so a question that never came back is reported as unanswered rather than dropped.

- **in** data/interim/runs/<run>/answers.jsonl, asked.txt, queries/kind_*.csv
- **out** scored.jsonl, scores.tsv in the run directory
- **kind** deterministic · idem yes · net no
- **stale when** a scorer change

## Deliverables

### `report d1`

Builds the missing-conditions statistic: how often a published zeta or mobility measurement comes without its medium, ionic strength, pH, temperature or instrument, with Wilson intervals and both denominators. It counts papers that report a measurement without printing a number anywhere, which is a claim the scanner alone cannot make. Every figure has its table beside it.

- **in** zeta_table.parquet, records.parquet, hit_counts.json
- **out** out/tables/d1_*.{csv,md,json}, out/figures/d1_missing_conditions.png
- **kind** deterministic · idem yes · net no
- **stale when** any change to the records or the corpus

### `report d1-gold`

Computes the same statistic on the 50 hand-annotated papers, as an estimate produced by a different method. Quoting either is defensible; quoting both is the point, because they agree. It is untouched by re-extraction of the corpus.

- **in** gold_50.csv
- **out** out/tables/d1_gold_*.{csv,md,json}
- **kind** deterministic · idem yes · net no
- **stale when** a changed gold set

### `report d2`

Renders the JSON Schema, an example instance and the one-page checklist from the same pydantic models, so the three cannot disagree. Ontology CURIEs travel with the fields rather than in a separate table. If the schema changes, all three change together or the build fails.

- **in** src/mnp/schema/models.py
- **out** out/schema/*.json, out/checklist.md
- **kind** deterministic · idem yes · net no
- **stale when** a schema edit

### `rescale fetch-si`

Downloads the Koelmans 2019 supplement once and extracts mmc1.docx, caching it on disk. The supplement is fixed, so this is a one-time network step. Nothing downstream re-reads the network.

- **in** MNP_CONTACT_EMAIL, Europe PMC
- **out** data/raw/koelmans2019/mmc1.docx
- **kind** deterministic · idem yes · net yes
- **stale when** nothing; the supplement is fixed, and the file is cached

### `rescale parse`

Parses Table S1 out of the docx programmatically — per-study size range, concentration, method — with no number transcribed by hand. A fixture test pins the header mapping, because a silently remapped column is a whole table of wrong numbers. The output is a CSV that everything downstream reads.

- **in** mmc1.docx
- **out** data/raw/koelmans2019/table_s1.csv
- **kind** deterministic · idem yes · net no
- **stale when** a parser change; the fixture test pins the mapping

### `rescale run`

Rescales every study's concentration to a common size range using the power-law correction factor, and reports how much the spread between studies collapses when the size floors are made comparable. The exponent and the target range are stated in the caption, and a sensitivity sweep covers the published range of alpha. This is the whole of D3's argument in one number.

- **in** table_s1.csv
- **out** out/tables/d3_*.csv, out/figures/d3_before_after.png
- **kind** deterministic · idem yes · net no
- **stale when** a change to α or to the target range — both are stated in the caption

### `report d3`

Renders the D3 tables and figure from the rescaled table. It is the reporting half of rescale run and produces identical output. Kept separate so report all can rebuild every deliverable without touching the network.

- **in** table_s1.csv
- **out** out/tables/d3_*.csv, out/figures/d3_before_after.png
- **kind** deterministic · idem yes · net no
- **stale when** the same as `rescale run`, of which this is the reporting half

### `ek qa`

Recomputes every printed electrokinetic fit on the salt grid the paper itself used, and gates the residual at two per cent of the axis range. Where a digitised series exists it is overlaid and scored; where it does not, the recomputed curve stands alone and is labelled as such. It also flags rows where the thick-layer assumption does not hold, rather than fitting them anyway.

- **in** data/raw/digitised/printed_params.csv, optional digitised CSVs
- **out** out/tables/d4_params.csv, d4_qa_residuals.csv, out/figures/d4_qa_overlay.png
- **kind** deterministic · idem yes · net no
- **scored against** the published curves themselves
- **stale when** a new digitised series, or a correction to the printed parameters

### `report d4`

Assembles the D4 tables and figures from the QA output and the saved posteriors: recovery against the printed fits, the SBC ranks, and the same-zeta-different-particle comparison. It reads what inference already wrote rather than re-running it. If the printed-fit bank is absent it says so and skips, so one missing input cannot kill report all.

- **in** printed_params.csv, data/processed/posteriors/
- **out** out/tables/d4_*.csv, out/figures/d4_*.png
- **kind** deterministic · idem yes · net no
- **stale when** re-running inference with a different seed or grid

### `report e1`

Re-runs the E1 representation bake-off: the 50 gold papers serialised seven ways and counted with cl100k_base. Every markdown and JSON arm is built from one shared block set, the parse's own lines, so the ratios are a fact about serialisation rather than about content; md_plain reproducing extraction_text to the token is the check that says so. The figures published in FINDINGS.md are printed beside the measured ones and the difference is stated, because the original script lived in a scratchpad and was lost, which left E1b multiplying constants nobody could regenerate. The tokeniser downloads its BPE table once into tiktoken's own cache and makes no request after that; no key is involved at any point.

- **in** gold_50.csv, data/raw/epmc/xml/, the cl100k_base BPE table
- **out** out/tables/e1_representation.csv, out/tables/e1_representation.md
- **kind** deterministic · idem yes · net no
- **stale when** any parser fix that moves the block set, or a change to one of the seven serialisers in mnp.corpus.represent

### `report demo`

Renders the 13-case demo: one page per case (why it was picked, its rows, the standardisation walk, comparability against the paper and the whole corpus, the harmonised zeta, the resampling headline with and without the paper), a README with the corpus-wide E2e table and E2b scan, and METHOD.md. It calls no model. Its reader section reads the recorded judgement runs at data/interim/runs/demo-cell{d,b}-20260928 rather than asking anything itself, and renders a missing run as 'not run' and a recorded usage-policy refusal as one.

- **in** d1_zeta_table.csv, the vendored corpus, data/interim/runs/demo-cell{d,b}-20260928
- **out** out/demo/README.md, out/demo/cases/*.md, out/demo/METHOD.md
- **kind** deterministic · idem yes · net no
- **stale when** a change to d1_zeta_table.csv, the demo modules, or a re-run of the cells

### `report release`

Packages the table D1 wrote as a citable dataset: the same rows as parquet and as JSONL, the JSON Schema re-exported from the pydantic models rather than copied, and a dataset card. Every statistic on the card is computed during the build from the table and from d1_stats.json, so a rebuild moves the numbers instead of leaving a stale one behind; the build refuses outright when the stats file no longer describes the table beside it. The card states what has not been established as plainly as what has — the gold set is unaudited, the licence is undecided, prompt provenance is coarse, and the corpus is one database.

- **in** out/tables/d1_zeta_table.csv, out/tables/d1_stats.json, articles.parquet, gold_50.csv, the vendored corpus manifest
- **out** out/release/{dataset.parquet,dataset.jsonl,schema.json,DATASET_CARD.md}
- **kind** deterministic · idem yes · net no
- **stale when** any change to the D1 table, the schema models or the gold set

### `infer mcmc`

Runs a seeded emcee posterior for each complete row of the printed-fit bank, on that row's own salt grid, from digitised points where they exist and from a synthetic observation otherwise. It is the reference the amortised posterior is judged against, not a production tool. Seed, walkers and steps are all recorded.

- **in** printed_params.csv, --seed
- **out** data/processed/posteriors/mcmc_*.npz, recovery and same-zeta figures
- **kind** seeded · idem yes · net no
- **stale when** a change of seed, walkers, steps or noise model

### `infer npe`

Trains an sbi neural posterior estimator on the reference grid and infers every complete row from it. It is the only file that imports sbi, so the dependency stays in one place. Training is seeded, and the simulation budget is an argument because it is the main cost.

- **in** the simulator, --n-sims, --seed
- **out** data/processed/npe_*.pt, sims.npz, npe_*.npz
- **kind** seeded · idem yes · net no
- **stale when** a change of seed, simulation budget or prior

### `infer sbc`

Runs simulation-based calibration on the trained posterior: draw parameters from the prior, simulate, infer, and check the rank statistics are uniform. It is a property of the trained posterior rather than of the data, so it must be re-run after retraining. A posterior that fails it is overconfident, whatever its recovery plot looks like.

- **in** the saved NPE, --n-sbc, --seed
- **out** out/tables/d4_sbc.csv, out/figures/d4_sbc_ranks.png
- **kind** seeded · idem yes · net no
- **scored against** the simulator's own draws
- **stale when** retraining; SBC is a property of the trained posterior, not the data

### `infer figures`

Regenerates every D4 inference figure from the posteriors already on disk, without re-running inference. Useful when only the presentation changes. Deterministic given the same posteriors.

- **in** data/processed/posteriors/
- **out** out/figures/d4_*.png
- **kind** deterministic · idem yes · net no
- **stale when** new posteriors

## Verification

### `report all`

Builds every deliverable in order, skipping any whose inputs are absent and saying which it skipped. It is the command that produces the whole of out/ from what is already in the repository. It reaches no network and calls no model.

- **in** everything above
- **out** the whole of out/
- **kind** deterministic · idem yes · net no
- **stale when** any upstream change

### `report reproduce`

Rebuilds every committed artefact from the vendored corpus and the stored records into a scratch directory, with the network refused rather than merely unused, and diffs the result against what is published. It hashes the record file before and after to prove the replay wrote nothing to it, checks the stored scanner counts read-only, and names any artefact that differs from HEAD. Its first run found three published tables that no longer followed from the data.

- **in** the vendored corpus, extractions.jsonl, the committed out/
- **out** a drift report and an exit code
- **kind** deterministic · idem yes · net no
- **stale when** nothing — this is the check the published numbers are measured against

### `eval all`

Measures each pipeline stage separately against its own ground truth: parse against hand-located sentences, the scanner against the values a human read out of the gold papers, the model's reading against the gold set, coercion against a case table covering every ratified rule, the verifier against fabrications that reached production, and the aggregate against the committed tables. Before this existed, a parser or coercion defect could only appear as a worse end-to-end score with nothing to say which stage caused it. A stage with no ground truth reports not measured — never 0.00 and never 1.00, because both are claims nobody checked.

- **in** fixtures in tests/eval/, gold_50.csv, the parsed corpus
- **out** out/tables/eval_stages.md, eval_stages.csv
- **kind** deterministic · idem yes · net no
- **scored against** one set per stage; a stage with none scores 'not measured', never 0 or 1
- **stale when** a change to any stage, or a new fixture case

### `report protocol`

Renders this document from the registry in src/mnp/protocol.py, which is the only writer of docs/PROTOCOL.md. The test suite holds the registry against the actual CLI, so a command with no entry, or an entry for a command that no longer exists, fails the build. Editing the prose by hand is detected and rejected.

- **in** src/mnp/protocol.py
- **out** docs/PROTOCOL.md
- **kind** deterministic · idem yes · net no
- **stale when** adding a command, which fails the suite until it is documented here
