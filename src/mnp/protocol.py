"""The protocol: every step of the study, rendered into docs/PROTOCOL.md from this registry.

A methodology written by hand describes the pipeline as it was the last time someone
remembered to edit it. This registry is held against the actual CLI by the test suite, so a
command with no entry — or an entry for a command that no longer exists — fails the build.

Three properties are recorded per step, and they are not the same thing:

deterministic  same input, same output. True of parsing, scanning, verification and every
               aggregate; never true of a model reading a paper.
seeded         random, but pinned by a seed: the same seed reproduces the same numbers.
judgement      a human or a model decides. Not reproducible, so it carries ground truth and
               a brief hash instead — that is the whole design of the extraction stage.
"""

from __future__ import annotations

from dataclasses import dataclass

KINDS = ("deterministic", "seeded", "judgement")


@dataclass(frozen=True)
class Step:
    command: str
    purpose: str
    inputs: str
    outputs: str
    kind: str
    idempotent: bool
    network: bool
    invalidated_by: str
    ground_truth: str = ""
    phase: str = ""


D = "deterministic"
S = "seeded"
J = "judgement"

STEPS: tuple[Step, ...] = (
    # ---------------------------------------------------------------- corpus
    Step(
        command="corpus search",
        purpose=(
            "Crawls Europe PMC for the query in queries/q1.txt and keeps every record that has a "
            "PMCID, deduplicating on DOI. It runs the unrestricted query once and reads the open-"
            "access flag per record, so the OA and the all-hits denominators come from the same "
            "page set rather than from two crawls taken minutes apart. The hit counts are written "
            "down because every fraction in D1 is reported against both."
        ),
        inputs="queries/q1.txt, MNP_CONTACT_EMAIL",
        outputs="data/raw/epmc/search/records.parquet, hit_counts.json",
        kind=D,
        idempotent=True,
        network=True,
        invalidated_by="editing the query, or Europe PMC indexing new records",
        phase="Corpus",
    ),
    Step(
        command="corpus fetch",
        purpose=(
            "Downloads the full-text XML of every open-access hit at five requests a second, with "
            "three retries on 429 and 5xx, and a User-Agent carrying a contact address because "
            "Europe PMC asks for one. A file that exists and is non-empty is never fetched twice, "
            "so an interrupted run resumes for free. Failures go to fetch_log.csv rather than to "
            "silence."
        ),
        inputs="records.parquet",
        outputs="data/raw/epmc/xml/PMC*.xml, fetch_log.csv",
        kind=D,
        idempotent=True,
        network=True,
        invalidated_by="a record being withdrawn or re-versioned upstream",
        phase="Corpus",
    ),
    Step(
        command="corpus snapshot",
        purpose=(
            "Freezes the fetched corpus into one archive and one manifest of sha256 per file. The "
            "archive is built deterministically — sorted names, fixed mode, no ownership, no "
            "timestamps, no gzip filename header — so an unchanged corpus always produces the same "
            "bytes and its hash can be quoted. Run it after a re-fetch and nowhere else."
        ),
        inputs="data/raw/epmc/xml/",
        outputs="xml.tar.gz, manifest.sha256",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="any re-fetch; the archive hash changes and must be re-published",
        phase="Corpus",
    ),
    Step(
        command="corpus verify",
        purpose=(
            "Checks every XML on disk against the manifest and exits non-zero if anything is "
            "missing, changed, or extra. Extra files fail as loudly as missing ones: a corpus with "
            "one more paper in it is a different corpus, even when nothing is corrupt. This is the "
            "check every claim of reproduction starts from."
        ),
        inputs="xml/, manifest.sha256",
        outputs="exit code, named differences",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="nothing — this is the check the others are measured against",
        phase="Corpus",
    ),
    Step(
        command="corpus restore",
        purpose=(
            "Unpacks the vendored archive into data/raw/epmc/xml/ and then verifies what it wrote. "
            "A tar member naming a path outside the target directory is refused rather than "
            "skipped. This is the first command on a fresh clone."
        ),
        inputs="xml.tar.gz",
        outputs="data/raw/epmc/xml/PMC*.xml",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="a corrupt archive; restore verifies and refuses silently-wrong output",
        phase="Corpus",
    ),
    Step(
        command="corpus parse",
        purpose=(
            "Turns each JATS XML into the text an extractor actually reads: the methods sections, "
            "every table flattened with its caption and footnotes, the characterisation sections, "
            "and keyword windows around zeta and mobility mentions. Section selection is by sec-"
            "type with a title-regex fallback, and the result is capped to roughly twelve thousand "
            "tokens, preferring keyword windows. Re-parsing is free and idempotent, but it makes "
            "the scanner counts stored in each record stale — check them with extract recount "
            "--check."
        ),
        inputs="data/raw/epmc/xml/",
        outputs="data/interim/articles.parquet",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="a parser change — re-parse, then `extract recount --check`",
        phase="Corpus",
    ),
    # ------------------------------------------------------------- extraction
    Step(
        command="extract todo",
        purpose=(
            "Lists the PMCIDs that have no record yet, so work can be handed out without two "
            "workers being given the same paper. It reads the live record file rather than a "
            "snapshot, which is what the first corpus run got wrong. With --with-values it narrows "
            "to papers where the scanner found a printed number; with --missing-brief it lists the "
            "opposite set — papers that already have a record but no brief hash, which is exactly "
            "the sweep's work list."
        ),
        inputs="articles.parquet, extractions.jsonl",
        outputs="a list of PMCIDs on stdout",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="new records landing in extractions.jsonl",
        phase="Extraction",
    ),
    Step(
        command="extract show",
        purpose=(
            "Prints exactly what an extractor reads for one paper: the system prompt, then the "
            "article text. It is the same text the API path sends, so a subagent and a model are "
            "reading the identical input. Nothing is written; this is the read half of the two-"
            "path "
            "design."
        ),
        inputs="articles.parquet, the prompt templates",
        outputs="stdout",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="a prompt edit — which changes the brief and therefore the hash",
        phase="Extraction",
    ),
    Step(
        command="extract run",
        purpose=(
            "The API path: an OpenAI-compatible model reads each paper and returns structured "
            "measurements, which then go through the same coercion, verification and coverage "
            "checks as any other path. It walks a model chain on 429 and 5xx, caches every reply "
            "by "
            "sha256 of model, system and user, and never re-bills a paper that already succeeded. "
            "This is judgement, so the record carries the model and the brief hash and is scored "
            "against the gold set."
        ),
        inputs="articles.parquet, a model chain, a brief",
        outputs="extractions.jsonl, zeta_table.parquet",
        kind=J,
        idempotent=True,
        network=True,
        invalidated_by="a brief or model change; both are recorded per record",
        ground_truth="gold_50.csv",
        phase="Extraction",
    ),
    Step(
        command="extract ingest",
        purpose=(
            "The subagent path: an agent supplies the JSON and this applies coercion, the "
            "verbatim-"
            "quote guard, the condition checks and the coverage count exactly as the API path "
            "would. It refuses to record anything without --brief (or an explicit --no-brief), "
            "because 833 existing records cannot be traced to instructions that no longer exist. "
            "Ingesting the same PMCID again replaces its record, so a worker can correct and "
            "resubmit."
        ),
        inputs="a JSON reply, --brief, --model",
        outputs="one record in extractions.jsonl, rebuilt zeta_table.parquet",
        kind=J,
        idempotent=True,
        network=False,
        invalidated_by="a brief change; the record carries its brief hash",
        ground_truth="gold_50.csv",
        phase="Extraction",
    ),
    Step(
        command="extract units",
        purpose=(
            "Prints the units the article itself prints, per table column and per sentence, so a "
            "claimed unit can be checked against the paper rather than assumed. It is the "
            "inspection tool behind the unit cross-check that runs inside every ingest. Read-only."
        ),
        inputs="one PMCID, the parsed article",
        outputs="stdout",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="a change to the unit scanner",
        phase="Extraction",
    ),
    Step(
        command="extract table",
        purpose=(
            "Rebuilds the derived row table and the extraction summary from the records, and "
            "writes "
            "nothing else. It exists because recount also rewrites the record file, and an offline "
            "replay must never write to the thing it is checking. The summary reports the "
            "provenance the records carry — including how many carry no brief — never the prompt "
            "the code happens to hold today."
        ),
        inputs="extractions.jsonl",
        outputs="zeta_table.parquet, extraction_summary.json",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="new or corrected records",
        phase="Extraction",
    ),
    Step(
        command="extract recount",
        purpose=(
            "Recomputes the scanner counts stored in each record after a parser or scanner change, "
            "leaving every measurement exactly as it was. Those counts are a property of the "
            "scanner, not of the extraction, so a fix upstream makes all of them stale at once; 91 "
            "of 845 records were stale when this was last run. With --check it reports the "
            "staleness and exits non-zero without writing anything."
        ),
        inputs="extractions.jsonl, articles.parquet",
        outputs="rewritten extractions.jsonl, zeta_table.parquet",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="a scanner change; `--check` reports staleness without writing",
        phase="Extraction",
    ),
    Step(
        command="extract retrofit",
        purpose=(
            "Gives every stored evidence quote the line address it already implies, without "
            "re-reading a paper or calling a model: each quote was verified verbatim against "
            "the article, so it locates in the line-addressed document by substring, and what "
            "is stored is the line id — the hash of (section path, ordinal, text) — so a later "
            "parser fix that renumbers the document leaves the citation standing. A one-off "
            "migration rather than a replay step, because an offline replay must not write to "
            "the record it is checking; --dry-run reports and writes nothing. The quote guard "
            "searched the whole article while the line document mirrors extraction_text, a "
            "subset of it, so a quote can be genuine and still fail to locate: those rows keep "
            "no ids, gain an evidence_not_located flag and are named in the output. Nothing is "
            "dropped — the count of what did not locate is the measurement."
        ),
        inputs="extractions.jsonl, data/raw/epmc/xml/",
        outputs="evidence.line_ids on each record, rebuilt zeta_table.parquet",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="a parser change that alters section paths, ordinals or line text",
        phase="Extraction",
    ),
    Step(
        command="extract review-measurand",
        purpose=(
            "Lists papers where the thing measured may not have been the plastic — particles "
            "filtered out before the measurement, a supernatant analysed, or the zeta of "
            "another material exposed to plastic (ratified rule S8). It decides nothing: the "
            "rule is a judgement about what a paper measured, and no regex settles that. What "
            "it does is make sure the question is asked, since the rule was found by a worker "
            "reading one paper and most of the corpus has not been read under it."
        ),
        inputs="articles.parquet, extractions.jsonl",
        outputs="a reviewable list on stdout",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="new records, or a change to what counts as the measurand",
        ground_truth="tests/edge/key.yaml S8 and the papers themselves",
        phase="Extraction",
    ),
    Step(
        command="extract review-list",
        purpose=(
            "Writes down every paper the extraction skips, with a link, marking those that discuss "
            "zeta or mobility without printing a number. A skip is a claim about a paper, so it is "
            "reviewable rather than silent. The list is deterministic, which is what lets the 342 "
            "papers with no measurement stand without a model reading them."
        ),
        inputs="articles.parquet",
        outputs="out/tables/d1_papers_without_printed_values.{csv,md}",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="a scanner or parser change",
        phase="Extraction",
    ),
    # ------------------------------------------------------------- evaluation
    Step(
        command="extract sample",
        purpose=(
            "Draws the stratified gold sample by year band from a fixed seed, excluding the papers "
            "used to develop the prompt. The seed and the corpus together decide who gets "
            "annotated, so both are recorded. Changing either draws a different sample and "
            "invalidates the comparison."
        ),
        inputs="articles.parquet, --seed",
        outputs="data/interim/annotation/sample_50.csv",
        kind=S,
        idempotent=True,
        network=False,
        invalidated_by="a different seed or a changed corpus — both change who is annotated",
        phase="Evaluation",
    ),
    Step(
        command="extract gold-merge",
        purpose=(
            "Merges the annotator batches in gold_parts/ into one gold_50.csv with the agreed "
            "column set. Annotation happens in batches so it can be checked in batches; this is "
            "the "
            "only step that assembles them. It performs no judgement of its own."
        ),
        inputs="data/interim/annotation/gold_parts/*.json",
        outputs="gold_50.csv",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="a new or corrected annotation batch",
        phase="Evaluation",
    ),
    Step(
        command="extract audit-sample",
        purpose=(
            "Builds a blind worksheet of gold papers for the author to re-judge, which is what "
            "Cohen's kappa is computed from. Blind means the worksheet carries the papers and the "
            "fields, not the existing annotation. Until it is filled, every slide must say the "
            "gold "
            "set is annotated but not audited."
        ),
        inputs="gold_50.csv, --n",
        outputs="data/interim/annotation/audit_10.csv",
        kind=S,
        idempotent=True,
        network=False,
        invalidated_by="a changed gold set",
        phase="Evaluation",
    ),
    Step(
        command="extract evaluate",
        purpose=(
            "Scores the extraction against the gold set at row level and paper level, matching "
            "rows "
            "on PMCID, fuzzy particle name and medium class, with stated tolerances per field. "
            "Only "
            "the annotated papers are scored: a prediction on an unannotated paper is neither "
            "right "
            "nor wrong, and counting it as a false positive once drove precision to 0.05. The "
            "headline numbers are the accuracy of conditions_complete and of "
            "medium_matches_exposure."
        ),
        inputs="zeta_table.parquet, gold_50.csv",
        outputs="out/tables/d1_precision_recall.csv, data/processed/evaluation.json",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="either side moving — re-run after every re-extraction",
        ground_truth="gold_50.csv",
        phase="Evaluation",
    ),
    Step(
        command="report gate",
        purpose=(
            "Passes or fails an extraction against the gold set on thresholds stated in advance, "
            "optionally on one slice of papers. A field with no ground truth is not scored at all, "
            "because precision 0.00 on zero true positives says nothing. Provenance is part of the "
            "verdict: the gate reports how many records cannot be traced to a brief."
        ),
        inputs="zeta_table.parquet, gold_50.csv, optional --slice",
        outputs="out/tables/gate.{json,md}",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="a threshold change, which is a decision and belongs in the changelog",
        ground_truth="gold_50.csv",
        phase="Evaluation",
    ),
    Step(
        command="report gates",
        purpose=(
            "Runs all four gates in one pass — did the worker do the work and record its brief, "
            "does it agree with the ratified edge cases, does it agree with gold, and what did the "
            "run cost and yield — and reports all four rather than stopping at the first failure. "
            "It is the check that runs before a configuration is trusted on hundreds of papers. "
            "Twelve papers is indicative, not a result."
        ),
        inputs="extractions.jsonl, tests/edge/key.yaml, gold, a slice",
        outputs="out/tables/gates.md",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="answering an edge case, which changes what gate 2 scores",
        ground_truth="tests/edge/key.yaml and gold_50.csv",
        phase="Evaluation",
    ),
    # ------------------------------------------------------------ deliverables
    Step(
        command="report d1",
        purpose=(
            "Builds the missing-conditions statistic: how often a published zeta or mobility "
            "measurement comes without its medium, ionic strength, pH, temperature or instrument, "
            "with Wilson intervals and both denominators. It counts papers that report a "
            "measurement without printing a number anywhere, which is a claim the scanner alone "
            "cannot make. Every figure has its table beside it."
        ),
        inputs="zeta_table.parquet, records.parquet, hit_counts.json",
        outputs="out/tables/d1_*.{csv,md,json}, out/figures/d1_missing_conditions.png",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="any change to the records or the corpus",
        phase="Deliverables",
    ),
    Step(
        command="report d1-gold",
        purpose=(
            "Computes the same statistic on the 50 hand-annotated papers, as an estimate produced "
            "by a different method. Quoting either is defensible; quoting both is the point, "
            "because they agree. It is untouched by re-extraction of the corpus."
        ),
        inputs="gold_50.csv",
        outputs="out/tables/d1_gold_*.{csv,md,json}",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="a changed gold set",
        phase="Deliverables",
    ),
    Step(
        command="report d2",
        purpose=(
            "Renders the JSON Schema, an example instance and the one-page checklist from the same "
            "pydantic models, so the three cannot disagree. Ontology CURIEs travel with the fields "
            "rather than in a separate table. If the schema changes, all three change together or "
            "the build fails."
        ),
        inputs="src/mnp/schema/models.py",
        outputs="out/schema/*.json, out/checklist.md",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="a schema edit",
        phase="Deliverables",
    ),
    Step(
        command="rescale fetch-si",
        purpose=(
            "Downloads the Koelmans 2019 supplement once and extracts mmc1.docx, caching it on "
            "disk. The supplement is fixed, so this is a one-time network step. Nothing downstream "
            "re-reads the network."
        ),
        inputs="MNP_CONTACT_EMAIL, Europe PMC",
        outputs="data/raw/koelmans2019/mmc1.docx",
        kind=D,
        idempotent=True,
        network=True,
        invalidated_by="nothing; the supplement is fixed, and the file is cached",
        phase="Deliverables",
    ),
    Step(
        command="rescale parse",
        purpose=(
            "Parses Table S1 out of the docx programmatically — per-study size range, "
            "concentration, method — with no number transcribed by hand. A fixture test pins the "
            "header mapping, because a silently remapped column is a whole table of wrong numbers. "
            "The output is a CSV that everything downstream reads."
        ),
        inputs="mmc1.docx",
        outputs="data/raw/koelmans2019/table_s1.csv",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="a parser change; the fixture test pins the mapping",
        phase="Deliverables",
    ),
    Step(
        command="rescale run",
        purpose=(
            "Rescales every study's concentration to a common size range using the power-law "
            "correction factor, and reports how much the spread between studies collapses when the "
            "size floors are made comparable. The exponent and the target range are stated in the "
            "caption, and a sensitivity sweep covers the published range of alpha. This is the "
            "whole of D3's argument in one number."
        ),
        inputs="table_s1.csv",
        outputs="out/tables/d3_*.csv, out/figures/d3_before_after.png",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="a change to α or to the target range — both are stated in the caption",
        phase="Deliverables",
    ),
    Step(
        command="report d3",
        purpose=(
            "Renders the D3 tables and figure from the rescaled table. It is the reporting half of "
            "rescale run and produces identical output. Kept separate so report all can rebuild "
            "every deliverable without touching the network."
        ),
        inputs="table_s1.csv",
        outputs="out/tables/d3_*.csv, out/figures/d3_before_after.png",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="the same as `rescale run`, of which this is the reporting half",
        phase="Deliverables",
    ),
    Step(
        command="ek qa",
        purpose=(
            "Recomputes every printed electrokinetic fit on the salt grid the paper itself used, "
            "and gates the residual at two per cent of the axis range. Where a digitised series "
            "exists it is overlaid and scored; where it does not, the recomputed curve stands "
            "alone "
            "and is labelled as such. It also flags rows where the thick-layer assumption does not "
            "hold, rather than fitting them anyway."
        ),
        inputs="data/raw/digitised/printed_params.csv, optional digitised CSVs",
        outputs="out/tables/d4_params.csv, d4_qa_residuals.csv, out/figures/d4_qa_overlay.png",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="a new digitised series, or a correction to the printed parameters",
        ground_truth="the published curves themselves",
        phase="Deliverables",
    ),
    Step(
        command="report d4",
        purpose=(
            "Assembles the D4 tables and figures from the QA output and the saved posteriors: "
            "recovery against the printed fits, the SBC ranks, and the same-zeta-different-"
            "particle "
            "comparison. It reads what inference already wrote rather than re-running it. If the "
            "printed-fit bank is absent it says so and skips, so one missing input cannot kill "
            "report all."
        ),
        inputs="printed_params.csv, data/processed/posteriors/",
        outputs="out/tables/d4_*.csv, out/figures/d4_*.png",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="re-running inference with a different seed or grid",
        phase="Deliverables",
    ),
    Step(
        command="report e1",
        purpose=(
            "Re-runs the E1 representation bake-off: the 50 gold papers serialised seven ways and "
            "counted with cl100k_base. Every markdown and JSON arm is built from one shared block "
            "set, the parse's own lines, so the ratios are a fact about serialisation rather than "
            "about content; md_plain reproducing extraction_text to the token is the check that "
            "says so. The figures published in FINDINGS.md are printed beside the measured ones "
            "and the difference is stated, because the original script lived in a scratchpad and "
            "was lost, which left E1b multiplying constants nobody could regenerate. The tokeniser "
            "downloads its BPE table once into tiktoken's own cache and makes no request after "
            "that; no key is involved at any point."
        ),
        inputs="gold_50.csv, data/raw/epmc/xml/, the cl100k_base BPE table",
        outputs="out/tables/e1_representation.csv, out/tables/e1_representation.md",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by=(
            "any parser fix that moves the block set, or a change to one of the seven serialisers "
            "in mnp.corpus.represent"
        ),
        phase="Deliverables",
    ),
    Step(
        command="report demo",
        purpose=(
            "Renders the 13-case demo: one page per case (why it was picked, its rows, the "
            "standardisation walk, comparability against the paper and the whole corpus, the "
            "harmonised zeta, the resampling headline with and without the paper), a README "
            "with the corpus-wide E2e table and E2b scan, and METHOD.md. It calls no model. Its "
            "reader section reads the recorded judgement runs at "
            "data/interim/runs/demo-cell{d,b}-20260928 rather than asking anything itself, and "
            "renders a missing run as 'not run' and a recorded usage-policy refusal as one."
        ),
        inputs="d1_zeta_table.csv, the vendored corpus, data/interim/runs/demo-cell{d,b}-20260928",
        outputs="out/demo/README.md, out/demo/cases/*.md, out/demo/METHOD.md",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="a change to d1_zeta_table.csv, the demo modules, or a re-run of the cells",
        phase="Deliverables",
    ),
    Step(
        command="report release",
        purpose=(
            "Packages the table D1 wrote as a citable dataset under CC BY 4.0: the same rows as "
            "parquet and as JSONL, the JSON Schema re-exported from the pydantic models rather "
            "than copied, a LICENSE, and a dataset card. Every statistic on the card is computed "
            "during the build from the table and from d1_stats.json, so a rebuild moves the "
            "numbers instead of leaving a stale one behind; the build refuses outright when the "
            "stats file no longer describes the table beside it. Each paper's licence is read "
            "from its vendored XML; a verbatim quote ships only from a CC BY or CC0 source, and "
            "every other quote is replaced by its sha256 and its address in the source lines. "
            "The build refuses when any withheld quote cannot be restored from that address "
            "byte for byte. The card states what has not been established as plainly as what "
            "has — the gold set is unaudited, prompt provenance is coarse, and the corpus is one "
            "database."
        ),
        inputs="out/tables/d1_zeta_table.csv, out/tables/d1_stats.json, gold_50.csv, the "
        "vendored corpus (licences, line addresses) and its manifest",
        outputs="out/release/{dataset.parquet,dataset.jsonl,schema.json,LICENSE,DATASET_CARD.md}",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="any change to the D1 table, the schema models, the gold set, the licence "
        "classifier or the line parser",
        phase="Deliverables",
    ),
    Step(
        command="report review",
        purpose=(
            "Writes out/review/: REVIEW.md, a guide for checking the dataset by hand, and five "
            "CSV worksheets a spreadsheet can recompute (conditions per paper, the ICC inputs, "
            "every row harmonised, four comparability pairs checked field by field, and a "
            "seeded audit sample of twenty rows with empty columns for the reviewer's "
            "verdicts). Every number in the guide is computed during the build by the modules "
            "it describes (resample, harmonise, comparability, scoring) or quoted with its file "
            "and section, and a worked example that does not reproduce the module's result "
            "refuses the build. The audit sample gives line numbers, never text, for a row "
            "whose quote the release withholds."
        ),
        inputs="out/tables/d1_zeta_table.csv, d1_stats.json, out/release/dataset.parquet, the "
        "vendored corpus, queries/kind_e_comparability.csv, the committed grid runs",
        outputs="out/review/{REVIEW.md,conditions_per_paper.csv,icc_worksheet.csv,"
        "harmonised_all_rows.csv,comparability_worked_pairs.csv,audit_sample.csv}",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="a change to the table, the release, the demo or comparability modules, "
        "or a re-run of the grid cells",
        phase="Deliverables",
    ),
    Step(
        command="report rehydrate",
        purpose=(
            "Puts the withheld evidence quotes back into a local copy of the release. For each "
            "withheld row it rebuilds the source article's line-addressed text from the vendored "
            "XML, slices the stored address, and keeps the result only if it matches the stored "
            "sha256; a mismatch is named and left null, never approximated. It writes to "
            "data/interim/rehydrated (gitignored) and refuses any path under out/, because the "
            "restored text carries its sources' licences, not the dataset's. It reaches the "
            "network only with --fetch, for an article missing from the corpus. Not a builder: "
            "report all and report reproduce never run it."
        ),
        inputs="out/release/dataset.parquet, the vendored corpus (or Europe PMC, with --fetch)",
        outputs="data/interim/rehydrated/{dataset.parquet,dataset.jsonl}",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="a new release, or a source re-typeset upstream (its rows then fail the "
        "sha256 check and are reported)",
        phase="Deliverables",
    ),
    Step(
        command="infer mcmc",
        purpose=(
            "Runs a seeded emcee posterior for each complete row of the printed-fit bank, on that "
            "row's own salt grid, from digitised points where they exist and from a synthetic "
            "observation otherwise. It is the reference the amortised posterior is judged against, "
            "not a production tool. Seed, walkers and steps are all recorded."
        ),
        inputs="printed_params.csv, --seed",
        outputs="data/processed/posteriors/mcmc_*.npz, recovery and same-zeta figures",
        kind=S,
        idempotent=True,
        network=False,
        invalidated_by="a change of seed, walkers, steps or noise model",
        phase="Deliverables",
    ),
    Step(
        command="infer npe",
        purpose=(
            "Trains an sbi neural posterior estimator on the reference grid and infers every "
            "complete row from it. It is the only file that imports sbi, so the dependency stays "
            "in "
            "one place. Training is seeded, and the simulation budget is an argument because it is "
            "the main cost."
        ),
        inputs="the simulator, --n-sims, --seed",
        outputs="data/processed/npe_*.pt, sims.npz, npe_*.npz",
        kind=S,
        idempotent=True,
        network=False,
        invalidated_by="a change of seed, simulation budget or prior",
        phase="Deliverables",
    ),
    Step(
        command="infer sbc",
        purpose=(
            "Runs simulation-based calibration on the trained posterior: draw parameters from the "
            "prior, simulate, infer, and check the rank statistics are uniform. It is a property "
            "of "
            "the trained posterior rather than of the data, so it must be re-run after retraining. "
            "A posterior that fails it is overconfident, whatever its recovery plot looks like."
        ),
        inputs="the saved NPE, --n-sbc, --seed",
        outputs="out/tables/d4_sbc.csv, out/figures/d4_sbc_ranks.png",
        kind=S,
        idempotent=True,
        network=False,
        invalidated_by="retraining; SBC is a property of the trained posterior, not the data",
        ground_truth="the simulator's own draws",
        phase="Deliverables",
    ),
    Step(
        command="infer figures",
        purpose=(
            "Regenerates every D4 inference figure from the posteriors already on disk, without "
            "re-"
            "running inference. Useful when only the presentation changes. Deterministic given the "
            "same posteriors."
        ),
        inputs="data/processed/posteriors/",
        outputs="out/figures/d4_*.png",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="new posteriors",
        phase="Deliverables",
    ),
    # ----------------------------------------------------------- verification
    Step(
        command="report all",
        purpose=(
            "Builds every deliverable in order, skipping any whose inputs are absent and saying "
            "which it skipped. It is the command that produces the whole of out/ from what is "
            "already in the repository. It reaches no network and calls no model."
        ),
        inputs="everything above",
        outputs="the whole of out/",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="any upstream change",
        phase="Verification",
    ),
    Step(
        command="report reproduce",
        purpose=(
            "Rebuilds every committed artefact from the vendored corpus and the stored records "
            "into "
            "a scratch directory, with the network refused rather than merely unused, and diffs "
            "the "
            "result against what is published. It hashes the record file before and after to prove "
            "the replay wrote nothing to it, checks the stored scanner counts read-only, and names "
            "any artefact that differs from HEAD. Its first run found three published tables that "
            "no longer followed from the data."
        ),
        inputs="the vendored corpus, extractions.jsonl, the committed out/",
        outputs="a drift report and an exit code",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="nothing — this is the check the published numbers are measured against",
        phase="Verification",
    ),
    Step(
        command="eval all",
        purpose=(
            "Measures each pipeline stage separately against its own ground truth: parse against "
            "hand-located sentences, the scanner against the values a human read out of the gold "
            "papers, the model's reading against the gold set, coercion against a case table "
            "covering every ratified rule, the verifier against fabrications that reached "
            "production, and the aggregate against the committed tables. Before this existed, a "
            "parser or coercion defect could only appear as a worse end-to-end score with nothing "
            "to say which stage caused it. A stage with no ground truth reports not measured — "
            "never 0.00 and never 1.00, because both are claims nobody checked."
        ),
        inputs="fixtures in tests/eval/, gold_50.csv, the parsed corpus",
        outputs="out/tables/eval_stages.md, eval_stages.csv",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="a change to any stage, or a new fixture case",
        ground_truth="one set per stage; a stage with none scores 'not measured', never 0 or 1",
        phase="Verification",
    ),
    Step(
        command="eval cell",
        purpose=(
            "Runs one one-shot cell of the tool-value grid (B or D) over the query set. Each "
            "question's prompt is built deterministically and handed to a headless `claude -p` "
            "reader with every tool, setting source and MCP server switched off, in a directory "
            "with no instruction file above it, so the prompt is the only thing it sees. The "
            "reader is pinned by full model id and a reply from any other model is refused. "
            "Resumes: a question already answered is never asked again, and a reader failure is "
            "retried rather than scored. --pilot asks two per kind first."
        ),
        inputs="queries/kind_*.csv, d1_zeta_table.csv, the vendored corpus",
        outputs="data/interim/runs/<run>/: manifest, asked.txt, answers.jsonl, scores.tsv",
        kind=J,
        idempotent=True,
        network=True,
        invalidated_by="a change to the reader model, the system prompt, or any cell builder",
        ground_truth="the answer keys in queries/kind_*.csv, scored by mnp.eval.scoring",
        phase="Evaluation",
    ),
    Step(
        command="eval score",
        purpose=(
            "Re-scores a run's recorded answers with the model-free scorer, without asking "
            "anything. The denominator is asked.txt, written before any reading, so a question "
            "that never came back is reported as unanswered rather than dropped."
        ),
        inputs="data/interim/runs/<run>/answers.jsonl, asked.txt, queries/kind_*.csv",
        outputs="scored.jsonl, scores.tsv in the run directory",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="a scorer change",
        phase="Evaluation",
    ),
    Step(
        command="report protocol",
        purpose=(
            "Renders this document from the registry in src/mnp/protocol.py, which is the only "
            "writer of docs/PROTOCOL.md. The test suite holds the registry against the actual CLI, "
            "so a command with no entry, or an entry for a command that no longer exists, fails "
            "the "
            "build. Editing the prose by hand is detected and rejected."
        ),
        inputs="src/mnp/protocol.py",
        outputs="docs/PROTOCOL.md",
        kind=D,
        idempotent=True,
        network=False,
        invalidated_by="adding a command, which fails the suite until it is documented here",
        phase="Verification",
    ),
)

PHASES = ("Corpus", "Extraction", "Evaluation", "Deliverables", "Verification")

_HEADER = """# Protocol

**Generated from `src/mnp/protocol.py` — do not edit by hand.** Run
`uv run python -m mnp.report protocol` after changing the registry; a command with no entry
here, or an entry naming a command that no longer exists, fails the test suite.

Every step states what kind of result it produces, because the three are not the same thing:

| Kind | Meaning |
|---|---|
| deterministic | same input, same output |
| seeded | random, but pinned by a seed; the same seed reproduces the numbers |
| judgement | a human or a model decides — not reproducible, so it carries ground truth\
 and a recorded brief instead |

`idem` — running it twice changes nothing the second time. `net` — reaches the network.

Start a fresh checkout with `corpus restore`, and check any claim of reproduction with
`report reproduce`.
"""


def render() -> str:
    """The document, built from STEPS. The only writer of docs/PROTOCOL.md."""
    out = [_HEADER]
    for phase in PHASES:
        steps = [s for s in STEPS if s.phase == phase]
        if not steps:
            continue
        out.append(f"\n## {phase}\n")
        for step in steps:
            out.append(f"\n### `{step.command}`\n")
            out.append(f"\n{step.purpose}\n")
            out.append(f"\n- **in** {step.inputs}")
            out.append(f"\n- **out** {step.outputs}")
            out.append(f"\n- **kind** {step.kind} · idem {'yes' if step.idempotent else 'no'}")
            out.append(f" · net {'yes' if step.network else 'no'}")
            if step.ground_truth:
                out.append(f"\n- **scored against** {step.ground_truth}")
            out.append(f"\n- **stale when** {step.invalidated_by}\n")
    return "".join(out)
