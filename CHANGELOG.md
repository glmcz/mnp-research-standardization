# Changelog — mnp-research

Process log for the evidence build behind *From Detection to Predicting MNP Behavior*.
Written so it can be picked up cold. Work began 2026-09-12; this entry was first written
2026-09-13 mid-wave, then rewritten the same day once the review wave (Log below) finished
and every artefact was regenerated.

## 0. 2026-09-14/15 — independence, protocol, per-stage evaluation, and a recorded re-read

Three things the study could not previously claim: that the repository stands alone, that its
steps are written down as a repeatable protocol, and that each stage is measured rather than
only the end of the pipeline.

**Independence.** The work queue fell back to `DATABASE_URL`, which `config.load_env()` reads
out of the Rust service's `.env` — so `pytest` with no `MNP_DB_URL` pointed the queue's
integration tests at the live `nanoplastics` application database and tried to create schemas
in it. A permission error was the only thing that stopped it (11 errors where the README
promised 11 skips). The queue now has one variable of its own and no fall-back; this service
reads its own `.env`, with the sibling's available only via `MNP_ALLOW_SIBLING_ENV=1`; and
`.env.example` is held against the source by an ast-based test.

**The corpus is vendored.** 858 XMLs, 27.7 MB, sha256 `9791cc01…`, with a `sha256sum`-format
manifest. The archive is byte-reproducible (sorted, no mtime, no ownership, no gzip filename
header), `verify` reports extra files as loudly as missing ones, and `restore` refuses a tar
member that resolves outside the target.

**Offline replay** (`report reproduce`) rebuilds every committed artefact from the vendored
corpus with the network *refused* rather than merely unused, hashes the record file before and
after to prove it wrote nothing, checks stored scanner counts read-only, and names any artefact
that differs from HEAD. Its first run found: `d1_precision_recall.csv` no longer followed from
the data (row value P 0.685 → 0.733; paper pH recall 0.833 → 1.000),
`d1_papers_without_printed_values` was stale by 53 papers (405 → 352), and 91 of 845 records
carried scanner counts from before the last scanner fix (mean coverage 0.533 → 0.563). No
measurement moved; `d1_stats` rebuilt byte for byte.

**A provenance field that lied.** `extraction_summary.json` reported `prompt_sha256` as the
hash of whatever prompt the *code* held at rebuild time, in a file describing 845 stored
records. Editing the prompt changed the artefact without a single record changing. It now
reports what the records carry — 833 with no brief, 12 with `0266af56…` — and the code's
current prompt separately, under its own name.

**Paths resolved late.** `ek/qa.py` and `rescale/koelmans2019.py` froze `config.DATA_RAW` at
import, so redirecting the data root depended on which test imported first; one report test
passed only by accident. `report d4` now skips cleanly when its bank is absent instead of
killing `report all`.

**The protocol** (`docs/PROTOCOL.md`) is generated from a 37-step registry that the test suite
holds against the actual CLI, each step 2–3 sentences: purpose, the non-obvious constraint,
and what makes it stale. A command with no entry, an entry for a dead command, or a hand-edited
document all fail the build.

**Provenance is now enforced.** `extract ingest` exits 2 without `--brief`; `--no-brief` is the
explicit opt-out. `--run-id` writes `data/interim/runs/<id>/manifest.json` — commit, dirty flag,
brief hash, corpus manifest hash, and the *names* (never values) of environment keys — plus one
append-only line per worker claim.

**Per-stage evaluation** (`python -m mnp.eval all`) measures parse, scan, read, coerce, verify
and aggregate separately, each against its own ground truth, and reports **not measured** —
never 0.00 or 1.00 — where there is none. First run: parse 1.00 (5 spans; dropping tables from
the extraction text scores 0.60), scanner recall **0.98** against 85 hand-read gold values,
coerce 1.00 over 12 cases covering every ratified rule, verify **1.00** over 7 fabrications
that each reached production once.

**Rule S8 ratified and applied (2026-09-15).** The measurand must be the plastic particle
itself: a zeta measured on a supernatant, a treated water, a protein or a cell is not a plastic
measurement, however clearly the paper attributes the shift to plastic. The case it came from
filtered its PET out at 0.2 µm before every measurement and tabulated "Zeta Potential of Aβ When
Exposed to MNP"; its own no-plastic control returned the same value. The rule is in
`docs/briefs/extraction.md` (hash `21f2ad53` → `25082cec`), and `extract review-measurand` lists
the papers that need the same question asked — 10 papers after the detector was tightened, down
from 25 when "filtered prior to HPLC analysis" still counted.

Fourteen papers were then read against it: **five emptied or reduced** (60, 21, 4, 4 and 3 rows),
**nine left untouched**. The corpus moved 498 → 493 papers and 1910 → 1876 rows, and **no
headline fraction moved by more than 0.3 points** — ionic strength 89.8% → 89.7%, temperature
77.5% → 77.7%, any condition 97.2% → 97.4%. One paper nearly became a false negative: stripping
its supernatant rows left `PMC12105431` at zero when it also measures its particles directly
against pH (Figure 4, value in the figure only); that row was recorded rather than lost. Three
places where S8 does not settle the question went to the key unanswered rather than being
decided quietly (`S21`–`S23`), including the case the rule's own test cannot resolve: two mixed
particle populations, where "would there still be something in the cuvette?" is true of both.

**Four more rulings, 2026-09-15**, and the rule that needed them. S8 as first written was too
blunt, and applying it exposed three boundaries:

- **S21 — residual particles in a treated water are still particles** ("plastic of course").
  S8 removes a measurement when the plastic is *gone* from the cuvette or was never the
  analyte; it does not remove one because the water around the particles was treated. Four
  rows restored to `PMC12105431`. The brief now carries this boundary explicitly, so the next
  worker cannot over-apply the rule the way this pass did.
- **S22 — provisional, not counted.** `PMC11857315` gives one laundry-wastewater number rather
  than a value per polymer, with 20–1000 µm granules largely outside the instrument's range.
  One sentence does attribute the figure to "the MPs", so it is recorded as provisional and
  reverses if a per-polymer value ever surfaces.
- **S23 — the tiebreaker for two colloid populations.** S8's own test ("would there still be
  something in the cuvette with a zeta potential?") answers yes either way when both species
  are particles, so it decides nothing. The rule is now: **is the other material adsorbed onto
  the plastic?** Adsorbed → a coated plastic particle, record it. Free in suspension → a
  mixture, record nothing.
- **S18 follows from S23**: a protein corona is the textbook adsorbed case, so corona
  measurements count. Recorded by implication and labelled as such.

Final after the pass: **493 papers, 1880 rows**; ionic strength missing 89.7%, pH 79.9%,
temperature 77.7%, instrument 18.1%, any condition 97.4% — every fraction within 0.4 points of
where it was before the rule existed.

**Re-reading under a recorded brief** began. Pilot (10 gold papers, 2 workers): 3 min 37 s,
~21 k agent tokens per paper, row value P/R **1.00 / 1.00**, zero rows dropped. Slice (28 more
gold papers, 4 workers) followed. The workers raised **14 rule gaps** (`P1`–`P7`, `S1`–`S7` in
`tests/edge/key.yaml`), several found independently by two workers — including eleven corpus
papers that carry **no retrievable text at all**, where an empty extraction had been
indistinguishable from a paper read and found to report nothing. `report d1` now counts those
apart.

## 1. Status

Session handoff for the rules wave: `SESSION_2026-09-13_RULES.md`.

As of 2026-09-13 (post-rules), `data/interim/extractions.jsonl` and every regenerated D1
table agree exactly — no drift between the live file and the reports. The paper count moved
499 → 498 and rows 1915 → 1910 when the gate run re-extracted twelve gold papers under a
recorded brief; the paper that left is PMC5876619, and it left on an **unratified** rule
(edge case V7: does "see Table S1 for ... zeta potentials" make a measurement reported?).
The gold annotator said yes, the gate worker said no. Answer V7 and one of them changes.

| | Count | Source |
|---|---|---|
| OA search hits | 862 (1115 incl. paywalled) | `data/raw/epmc/search/hit_counts.json` |
| Fetched + parsed | 858 full-text XMLs | `data/raw/epmc/xml/` (858 `.xml` files), `data/interim/articles.parquet` (858 rows) |
| Extraction records | 845, 0 with a non-null `error` | `data/interim/extractions.jsonl`, counted live |
| Papers with ≥1 measurement | **498** | jsonl live and `out/tables/d1_stats.md`/`.json` agree |
| — of which no printed number anywhere | **144** | jsonl live and `d1_stats.json`'s `n_papers_measured_but_no_number_printed` agree |
| Measurement rows | **1910** | jsonl live and `out/tables/d1_stats.md` agree |
| Tests | **737 passed, 2 deselected** | `uv run pytest -q` |
| Ruff | **clean** — "All checks passed!" | `uv run ruff check src tests` |

The gold-set figures (`out/tables/d1_gold_stats.md`, 24 papers, 127 rows) are untouched by
this wave and are current. See the Log below for what changed and why the previous entry's
warning against quoting D1 numbers mid-wave no longer applies.

## 2. Pipeline

The D1 pipeline runs these stages in order; D2/D3/D4 are separate, narrower pipelines described
under Deliverables.

1. **Corpus fetch** — query Europe PMC, download OA full-text XML — `mnp.corpus.epmc` —
   `uv run python -m mnp.corpus search --query-file queries/q1.txt` then
   `uv run python -m mnp.corpus fetch`
2. **Parse** — JATS XML to flattened per-article text and TSV tables (captions, footnotes,
   `<floats-group>`, colspan/rowspan expansion, sign and superscript normalisation) —
   `mnp.corpus.jats` — `uv run python -m mnp.corpus parse`
3. **Scan** — regex-find every printed zeta/mobility number in an article independent of what
   gets extracted, used both as an extraction candidate list and as the coverage denominator —
   `mnp.extract.zeta` (`find_candidates`) — inspectable directly via
   `uv run python -m mnp.extract units --pmcid <id>`
4. **Extract** — an LLM reads the methods/results text and returns structured measurements,
   two interchangeable paths into the same pipeline — `mnp.extract.llm` / `.prompts` / `.coerce` —
   API path: `uv run python -m mnp.extract run --model "$OPENROUTER_MODEL" --concurrency 4`;
   subagent path: `uv run python -m mnp.extract show --pmcid <id>` then
   `uv run python -m mnp.extract ingest --pmcid <id> --json reply.json --model claude-code:sonnet`
5. **Verify** — evidence-quote and value-in-quote guards, condition-reported checks, printed-unit
   cross-check — `mnp.extract.zeta` (`verify_row`) / `mnp.extract.units` — runs inside every
   `ingest`/`run`; scored against the gold set with
   `uv run python -m mnp.extract evaluate --gold data/interim/annotation/gold_50.csv`
6. **Report** — verified rows into the D1–D4 tables and figures — `mnp.report.d1/d2/d3/d4` —
   `uv run python -m mnp.report all`

## 3. Deliverables

**D1 — literature stat.** All 858 open-access full texts were parsed, and every paper that
mentions zeta or electrophoretic mobility was read via `show`/`ingest` — not only the ones
where a regex found a printed value, but also the 372 that print no number at all, because
"measured but never printed" is exactly the category this study is about. **499 papers**
carry at least one verified plastic-particle zeta/mobility measurement (1915 rows, every one
evidence-verified). Headline: **97.2%** (485/499, 95% CI 95–98%) omit at least one of
medium/ionic strength/pH/temperature/instrument. The defensible number for the talk is still
the hand-annotated sample, not the corpus figure: 24 of 50 stratified-random papers report a
zeta/mobility value, and **100%** (24/24, 95% CI 86–100%) omit at least one condition; not one
of the 24 reports all five. Row-level temperature is known-bad against gold — P 0.15 / R 0.23
(exact: 0.1463/0.2308 per `d1_precision_recall.csv`; it captures incubation temperature, not
measurement temperature) — so the gold figure (18/24 missing temperature) is the one to use,
not the corpus figure (388/499). **144 of the 499** report a measurement without printing a
single number anywhere in the retrievable text, up from 17 in the previous, biased-denominator
run (see Log). Artefacts: `out/tables/d1_stats.md`/`.json`, `d1_gold_stats.md`/`.json`,
`d1_zeta_table.csv`, `d1_gold_zeta_table.csv`, `d1_oa_bias.csv`, `d1_gold_oa_bias.csv`,
`d1_precision_recall.csv`, `data/processed/evaluation.json`,
`out/figures/d1_missing_conditions.png`, `d1_gold_missing_conditions.png`. Unlike the previous
entry, there is no drift to warn about: the whole-corpus numbers above match the live jsonl
exactly — see Status.

**D2 — schema + checklist.** One pydantic model (`mnp.schema.models`) renders to a JSON Schema
(2020-12, with ontology CURIEs from `mnp.schema.ontology`) and a one-page reporting checklist,
via `mnp.schema.export`; editing the checklist by hand is not possible by design. Headline: a
17-row checklist (`out/checklist.md`) backed by a schema with 14 `$defs`
(`out/schema/mnp_characterisation.schema.json`, 827 lines) and one worked example
(`out/schema/example_instance.json`). Ionic strength is deliberately left unmapped — no ENM/NPO/
CHMO/ENVO term exists for it.

**D3 — rescaling demo.** Koelmans et al. 2019 (Water Res 155:410) Table S1 is prose inside SI
cells, not a tidy table; `mnp.rescale.koelmans2019` reads the SI docx XML directly (python-docx
drops the Symbol-font µ) and derives a size floor and a concentration per row, recording the
source cell in `notes` for every derived number. Headline, quoted from the README: **55 rows
parsed, 47 rescaled; 8 excluded (6 no size floor, 2 no concentration). 28 of 47 report only a
lower bound** and are rescaled against an assumed 5000 µm upper limit. Rescaling itself uses the
Kooi & Koelmans 2019 power-law correction factors (default α = 1.6) from `mnp.rescale.powerlaw`.
Artefacts: `out/tables/d3_rescaled.csv` (660 rows), `d3_spread.csv` (26 rows),
`out/figures/d3_before_after.png`.

**D4 — physics demo.** The Ohshima soft-particle and hard-sphere electrokinetic models
(`mnp.ek.soft`/`.hard`), fit against a bank of printed literature curves and validated against an
independent pure-Python recomputation (Makino oracle to 4 digits; Kobayashi hard-latex peak
matches the paper's own Fig. 1 theory curve). Headline: a 25-row printed-fit bank, 12 rows
complete (`out/tables/d4_params.csv`); parameter recovery by MCMC (`emcee`, per-row posteriors
under `data/processed/posteriors/`) and by NPE (`sbi`, trained at 50,000 simulations, 5.7 min
CPU), simulation-based calibration passing cleanly: KS p = 0.96 / 0.47 (soft |ZN|, 1/λ), 0.52 /
0.51 (hard σ, a) — every printed parameter recovered within |z| ≤ 2. No digitised curves exist yet
(`data/raw/digitised/` is empty of real data), so every D4 figure is labelled "synthetic from
printed fits." Artefacts: `out/tables/d4_params.csv`, `d4_qa_residuals.csv`, `d4_sbc.csv`;
`out/figures/d4_qa_overlay.png`, `d4_recovery.png`, `d4_same_zeta.png`, `d4_sbc_ranks.png`.
Untouched by today's wave.

## 4. Defects found and fixed

The first nine were caught the same way: the 50-paper hand annotation was read against the same
`mnp.extract show` output the LLM extractor reads, which made the gold set a test of the parser
rather than only of the model. Each is pinned by a named test in `tests/`.

| Defect | Scale | Surfaced by | Pinning test(s) |
|---|---|---|---|
| Tables parked in `<floats-group>`, outside `<body>`, were invisible to the parser | 79 of 858 articles (9%); one, PMC9318256, held 10 zeta values in a table captioned "Zeta potential of the different effluents" | Annotator saw the caption in the article but nothing in `show` output for PMC9318256 | `test_tables_parked_in_floats_group_are_still_parsed` |
| A column headed only with a unit ("Before Treatment (mV)") wasn't matched to its quantity, named only in the caption | not quantified in README | Header-only matching returned nothing during table review | `test_table_columns_take_their_quantity_from_the_caption_when_headers_only_carry_units` |
| Superscript unit exponents (`10⁻⁸ m²V⁻¹s⁻¹`) weren't normalised before matching, inflating every mobility in the affected paper ×10⁸ | 25 mobility rows stored as 400 instead of 4.00 | Built while writing the `mnp.extract.units` cross-check tool, which compares the claimed unit against the one the article prints | `test_a_superscript_ten_to_the_minus_eight_is_not_multiplied_again`, `test_an_implausible_converted_mobility_is_refused_not_stored` |
| Hyphen, en-dash and true-minus characters in front of a value read as positive; a true minus before a thin space (Springer's typesetting) did too | 8 distinct dash characters found acting as a sign in this corpus (incl. U+2010, U+2013, U+2212); whole tables of `–13.4 ± 0.8` read as positive | Annotator found negative values in the article stored as positive numbers in `show` output | `test_en_dash_table_values_are_read_as_negative`, `test_a_hyphen_used_as_a_minus_is_read_as_negative`, `test_minus_sign_followed_by_a_thin_space_keeps_its_sign`, `test_every_dash_character_used_as_a_sign_becomes_an_ascii_minus` |
| Decimal commas (`-31,63`, `0,026 M`) weren't read as decimals | one paper yielded zero candidates where the article printed values | Annotator found a paper with printed values and an empty `show` output | `test_a_decimal_comma_is_read_as_a_decimal_point`, `test_comma_decimal_table_values_are_found` |
| A citation list next to a unit (`[4,5] mV`) was read as a value | not quantified in README | Found alongside the decimal-comma review, same comma-parsing pass | `test_a_citation_list_is_not_a_decimal`, `test_a_citation_list_next_to_a_unit_is_not_a_zeta_value` |
| A gene name containing "mobility" ("high mobility group box transcription factor 1") was read as electrophoretic mobility | 42 phantom mobility values from one gene-expression table | Coverage for one paper was implausibly high; traced to a gene-expression table | `test_a_gene_called_high_mobility_group_is_not_an_electrophoretic_mobility` |
| Abstracts were never scanned; a value printed only there was missed, and a value the abstract merely restates was at risk of being counted twice once abstracts were added | 8 of 858 papers print a zeta value only in the abstract | Annotator found a printed value in the abstract with nothing in `show` output | `test_the_abstract_is_captured_and_reaches_the_extraction_text`, `test_a_value_printed_only_in_the_abstract_is_still_counted`, `test_a_value_the_abstract_merely_restates_is_not_counted_twice` |
| Document order: a child element's tail text was emitted before its own subtree (`"Figure 2 b"` became `"2Figure b"`) | one example given in README | Text order looked scrambled next to numbers during annotation review | `test_nested_inline_elements_keep_document_order` |

### New defects, 2026-09-13 — surfaced by the no-printed-value review wave

Reading the 372 papers that discuss zeta/mobility without a scanner-detectable printed value
(see Log) found one systemic gap and seven scanner recall gaps, all now fixed and pinned.

| Defect | Scale | Surfaced by | Pinning test(s) |
|---|---|---|---|
| A claimed unit was never checked against the one printed in the article — a retyped unit (`cm²/Vs` as `m²/Vs`) converts 10⁴× too large and still looks plausible, with no trace of the error in the value itself | the same 25 mobility rows as the superscript-exponent defect above | Built `mnp.extract.units` (new `units` CLI subcommand) to read the printed unit directly out of the article; every `ingest` now cross-checks and flags `unit_disagrees_with_article` on a mismatch | `test_units_command_prints_what_the_article_prints`, `test_disagreement_is_detected_between_a_claimed_unit_and_the_printed_one`, `test_a_claimed_unit_that_contradicts_the_printed_one_is_flagged` |
| A zeta value printed with no unit anywhere near it ("a zeta potential of -32.0") was not a candidate | not quantified | PMC10766629, found working the review list | `test_a_zeta_printed_without_any_unit_is_still_a_printed_value` |
| A magnitude given only as "± 45" (sign unknown, no unit printed) was not a candidate | not quantified | PMC10819112 | `test_a_unitless_zeta_written_with_a_leading_plus_minus_keeps_its_magnitude`, `test_a_sign_unknown_candidate_is_claimed_by_a_row_of_either_sign` |
| "ZP" was not recognised as an abbreviation for zeta potential | not quantified | PMC10610651 | `test_zp_is_recognised_as_the_zeta_potential_abbreviation`, `test_zp_needs_its_unit_and_does_not_fire_on_unrelated_words` |
| A value with its unit inside a trailing bracket, or the unit spelled out as "millivolts"/"millivolt", was not matched | not quantified | PMC11288365 (bracket), PMC11293132 (spelled out), PMC11312894 (bracket) | `test_values_printed_in_brackets_or_with_a_spelled_out_unit_are_found`, `test_the_deviation_inside_the_bracket_is_kept` |
| A table column headed with a typo ("MPS-zate(mv)") — no "zeta", no "potential" — was not matched to the quantity | 42 values in one paper | PMC11543686 | `test_a_column_measured_in_millivolts_is_a_zeta_column` |
| A millivolt column naming no quantity at all was dropped outright, on the theory that "mV" alone was too weak a signal | same paper/values as above | PMC11543686 | `test_a_millivolt_column_is_claimed_even_when_nothing_names_the_quantity` |

## 5. Open items

- **Blind audit, not yet done.** `data/interim/annotation/audit_10.csv` holds 10 of the 50 gold
  papers (41 rows) with every judged column (`medium_class`, `ionic_strength_mM`, `pH`,
  `temperature_C`, `instrument_reported`, `value`, …) blanked, for Martin to re-judge blind against
  the article. `data/processed/evaluation.json`'s `audit` block confirms this is still untouched:
  `n_audited_rows: 0`, every κ is `NaN`. Once the filled sheet is saved as
  `data/interim/annotation/gold_parts/gold_audit.json` and `extract gold-merge` is re-run,
  `evaluate` will report Cohen's κ on the five `*_reported` booleans. Until then the slide must say
  "annotated by Claude, not yet audited," per the README.
- **Review list, regenerated post-wave.** All 372 papers the previous review list flagged have now
  been read via `show`/`ingest` — that is the wave recorded in the Log below. Regenerated against
  the fixed parser/scanner, `out/tables/d1_papers_without_printed_values.md`/`.csv` now lists
  **405** open-access papers with no regex-detectable printed value, of which **392** discuss zeta
  or mobility without printing a number — up from 383/370 before this wave. That is not a
  before/after comparison of the same list: some of the 372 papers that got folded into the
  extraction should have dropped off it, while the new precision guards added today (membrane
  potential, applied voltage, redox potential no longer matching as zeta) mean some papers that
  used to register a "printed value" no longer do. The two effects haven't been separated, and
  none of these 405/392 has had a second read yet.
- **Report/jsonl drift — resolved.** The previous entry's warning against quoting D1 numbers
  mid-wave no longer applies: `extractions.jsonl` (845 records) and every regenerated D1 table now
  agree exactly (499 papers, 1915 rows, 144 with no printed number — see Status).
- **README's own precision/recall table has drifted from its source file, again.** README prints
  row-level `value` P/R as 0.69/0.74 — close enough to the source (0.6847826086956522 /
  0.7411764705882353), just rounded generously — but `temperature_C` as **0.05/0.08**. The current
  `out/tables/d1_precision_recall.csv` (same 2026-09-13 regeneration as `d1_stats.md`) says
  `temperature_C` P **0.14634146341463414** / R **0.23076923076923078** (tp 6, fp 35, fn 20, n 61)
  — not a rounding difference. That 0.05 doesn't come from the CSV at all; it matches the
  unrelated anecdote two paragraphs above the table ("counting it as a false positive once drove
  precision to 0.05"), which suggests that number got typed into the wrong cell. The CSV also
  still carries two row-level fields (`ionic_strength_mM`, `pH`) that README's table omits
  entirely. Row-level temperature was already flagged as the number not to trust for the talk;
  0.05/0.08 understates even that — worth fixing in README before anyone quotes it.
- **D4 has no real digitised data yet.** Every D4 figure is synthetic from printed fits; dropping
  CSVs into `data/raw/digitised/<dataset>.csv` and re-running `python -m mnp.ek qa` is what the
  README asks for next, whenever that data is available.

## 6. Log

### 2026-09-13 (latest) — three judgement rules ratified, and what they cost

Martin answered the three rule questions in `docs/DECISIONS_NEEDED.md`:

1. **A printed composition is an ionic strength**, flagged derived — "0.0027 M potassium
   chloride, 0.137 M sodium chloride" is 139.7 mM. A component whose speciation the paper
   never states (phosphate at an unstated pH) contributes nothing.
2. **An incubation temperature is not the measurement temperature** — and stays that way
   when the paper gives no other temperature, and when temperature is its own variable.
3. **A condition applies only within the experiment that states it** — no propagation across
   preparations unless the paper says so.

Recorded in `tests/edge/key.yaml` (C1, C2, C5), in `docs/briefs/extraction.md` — whose hash
moved `0266af56…` → `21f2ad53…`, so every record produced from here on is traceable to these
rules — in the worker system prompt, and in the extractor and gold-annotator personas.

Code, each guard mutation-verified:

| Rule | Change | Flag |
|---|---|---|
| Q1 | `coerce.parse_ionic_strength` reads spelled-out salt names and sums a printed composition | `derived_from_composition` |
| Q2 | `coerce.parse_temperature` returns null for another step's temperature | `temperature_not_measurement` |
| Q2 | `zeta.verify_row` catches a temperature quoted inside an incubation sentence | `temperature_step_not_measurement` |
| Q3 | `zeta.verify_row` requires each condition in the row's **own** evidence, not merely in the article | `pH_not_in_evidence`, `temperature_not_in_evidence`, `ionic_strength_not_in_evidence` |

`tool/rules_impact.py` scores the stored corpus against the new rules without re-reading a
paper (`out/tables/rules_impact.md`): temperature missing 77.5% → **82.5%**, pH 80.1% →
**83.9%**, ionic strength 89.8% → **≥76.7%** (Q1 is an upper bound on the gain; only a
re-extraction settles it). **The published D1 numbers predate the rules** — they are the old
reading, and the re-extraction under the recorded brief is what makes them current.

Scored the three LLM judges against Martin's answers rather than against each other:
claude-1 κ **+1.00** (16 cases, 100%), external nemotron **+0.34** (64%), claude-2 **+0.22**
(57%). Each judge got one whole rule entirely wrong, a different one each — so no single
judge runs unsupervised. Majority-of-three would have been right on all three rules here, on
2–1 margins across 4–6 cases each: worth noting, not worth relying on.

Also fixed: with the key's first three answers in place, gate 2 scored the CLI's empty
persona dict as 0% agreement and printed **FAIL** — a failure nobody's work caused. Not
being asked and disagreeing are now different outcomes (`passed: None`, with the reason).

737 tests pass, ruff clean.

### 2026-09-13 (later) — reproducibility machinery, and a gate that found six defects

Built steps 1–4 of `docs/ARCHITECTURE_PLAN.md`:

- **Provenance.** `mnp/extract/provenance.py` identifies a brief by the hash of its content;
  `ingest --brief` stores `brief_path` and `brief_sha256` on every record. `audit()` names the
  records that cannot be traced — currently 836 of 845, all predating today.
- **Work queue.** `mnp/queue.py` on PostgreSQL with `FOR UPDATE SKIP LOCKED`. Eight parallel
  processes claiming at once partition the corpus with zero overlap (tested). Expired leases
  return their work; three failed attempts retire a paper for a human to look at.
- **Personas.** Four agent definitions in `.claude/agents/`, none holding the Agent tool, so
  the delegation failure of the first run is structurally impossible.
- **Edge set.** `tests/edge/` — 27 real papers whose adjudication is Martin's to make, not the
  pipeline's. Three were added by gate-3 workers who found rules the brief does not state.
- **Gate.** `mnp/report/gate.py` and `python -m mnp.report gate`. A field with no ground truth
  is reported, not scored: precision 0.00 on zero true positives says nothing about a persona.
  Provenance is part of the verdict.

**The gate was then run for real, and found six defects — three of them mine, introduced the
same day:**

1. `--brief` was documented in the persona but never wired into the CLI, so a compliant worker
   produced six records with no provenance at all.
2. An unrelated concentration in a medium string ("FSW + BPA (10 µM)") was recorded as a
   *reported* ionic strength — inflating the study's headline metric.
3. `<0 mV` parsed as `0.0`: a fabricated measurement with the wrong sign.
4. A not-zeta phrase anywhere in a paragraph suppressed real values 400 characters away.
5. `accelerat` matched the ordinary verb "accelerates".
6. Polymersomes and functional core-shell coatings are undefined in the brief; two workers
   flagged this independently, which is the signal that the rule is missing rather than the
   worker confused.

All six are fixed and mutation-verified. Three of the mutations first came back green, meaning
the test proved nothing until it was rewritten to discriminate.

Scores on the 12-paper gate slice after the fixes: row value P 0.88 / R 0.88 (corpus run:
0.68 / 0.74); row temperature 0.57 / 0.57 (corpus run: 0.15 / 0.23); paper-level instrument,
pH and temperature 1.00 / 1.00. Twelve papers is a small slice — indicative, not a result.



### 2026-09-13 — units extractor; review wave over the no-printed-value papers (complete)

The first corpus pass extracted only papers where a regex found a printed value — 341 papers,
1459 rows. That silently excluded 372 papers that discuss a zeta potential without printing one
anywhere in the retrievable text: exactly the papers "measured but never printed" is about, and
the ones most relevant to the argument — a selection bias against the study's own subject. Every
one of the 372 was read via `show`/`ingest`. The corpus moved from 341 papers / 1459 rows to
**499 papers / 1915 rows**, and the count of papers reporting a measurement with no printed
number anywhere from **17 to 144**. The headline fractions barely moved (ionic strength 88.9% →
89.8%, any condition 96.8% → 97.2%) — worth stating plainly: the fractions were sound, the
denominator was not.

Built `mnp.extract.units` (new `units` CLI subcommand) to read the printed unit directly out of
an article — a table header, row label, caption, or the sentence carrying the number — instead of
trusting a transcription. Every `ingest` now cross-checks the claimed unit against the printed one
and flags `unit_disagrees_with_article` on a mismatch; this is what caught the superscript-exponent
bug in the Defects table above (25 mobility rows that had been stored as 400 instead of 4.00).

Reading the 372 also surfaced seven scanner recall gaps: a zeta printed with no unit nearby, a
magnitude given only as "± 45", the "ZP" abbreviation, a value with its unit inside a trailing
bracket, a spelled-out "millivolts", a column headed with a typo ("MPS-zate(mv)"), and a millivolt
column naming no quantity at all. Each is now fixed and pinned by a named test — see Defects.

`out/tables/d1_papers_without_printed_values.md`/`.csv` has been regenerated against the fixed
scanner: 405 of 858 papers now have no regex-detectable printed value (392 discussing zeta or
mobility), against 383/370 before this wave — see Open items for why that moved the way it did.

Finished the session at 630 passing tests (2 deselected, `uv run pytest -q`) and a clean
`uv run ruff check src tests` ("All checks passed!").

### 2026-09-12 — build

Built the D1–D4 pipeline end to end. Europe PMC corpus fetch/parse (862 OA hits, 858 full texts
fetched and parsed); the zeta/mobility regex scanner and the two-path extractor (OpenAI-compatible
API via `extract run`, and a Claude Code subagent path via `extract show`/`ingest` reading the same
prompt with the model call taken out); the pydantic schema, JSON Schema and checklist (D2); the
Koelmans 2019 rescaling demo (D3, SI docx parsed from its XML directly); the Ohshima electrokinetic
model with MCMC and NPE parameter recovery (D4, culminating in a 50,000-simulation NPE run with
clean simulation-based calibration). Model chain built from the backend `.env`
(`OPENROUTER_MODEL`/`OPENROUTER_FALLBACK_MODELS`), each call passing `reasoning: {exclude: true}`
after a live check showed `nemotron-3-super:free` returning 0 rows in 124 s without it and 14/14
rows in 166 s with it.

Ran the 50-paper stratified hand annotation (`gold_50.csv`) directly against `show` output, which
surfaced and fixed the nine parser/extraction defects listed above, each pinned by a new test.
Re-annotated all 16 gold papers whose text changed under the fixes; every headline number held,
only the "no printed number" count moved (8 → 7) and one paper (PMC9318256) gained 10 values that
correctly stayed out of the plastics count. Wrote the 10-paper blind audit sheet (`audit_10.csv`,
still unfilled — see Open items). Finished the session at 601 passing tests and a clean `ruff
check`.
