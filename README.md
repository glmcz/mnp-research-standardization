# mnp-research

Evidence for the talk *From Detection to Predicting MNP Behavior*. Four deliverables:

| | Deliverable | Headline |
|---|---|---|
| D1 | Literature stat | fraction of open-access MNP papers reporting a zeta potential **without** medium / ionic strength / pH / temperature / instrument |
| D2 | Schema + checklist | one pydantic model → JSON Schema (2020-12, ontology CURIEs) → one-page reporting checklist |
| D3 | Rescaling demo | Koelmans 2019 concentrations put on a common size range; the spread that survives |
| D4 | Physics demo | Ohshima soft-particle model, parameter recovery by MCMC and NPE, "same zeta, different particle" |

Nothing outside this directory is modified.

## Setup

```bash
uv python pin 3.12 && uv sync --all-groups
export MNP_CONTACT_EMAIL='you@example.org'   # Europe PMC User-Agent; fetch refuses without it
```

Secrets are read from `../nanoSolve-backend/.env` (`OPENROUTER_KEY`, `OPENROUTER_MODEL`,
`OPENROUTER_FALLBACK_MODELS`). Override the location with `MNP_ENV_FILE`.

## Commands

```bash
uv run ruff check src tests && uv run ruff format --check src tests
uv run pytest -q                 # fast
uv run pytest -q -m slow         # NPE smoke + SBC, ~5 min CPU

uv run python -m mnp.corpus search --query-file queries/q1.txt
uv run python -m mnp.corpus fetch && uv run python -m mnp.corpus parse
uv run python -m mnp.extract sample --n 50 --dev 20        # gold + prompt-dev sets
uv run python -m mnp.extract run --model "$OPENROUTER_MODEL" --concurrency 4   # API extractor
uv run python -m mnp.extract show --pmcid PMC5090179        # what an extractor reads
uv run python -m mnp.extract ingest --pmcid PMC5090179 --json reply.json --model claude-code:sonnet
uv run python -m mnp.extract todo --limit 20                # PMCIDs not yet extracted
uv run python -m mnp.extract units --pmcid PMC11117817
uv run python -m mnp.extract evaluate --gold data/interim/annotation/gold_50.csv
uv run python -m mnp.ek qa
uv run python -m mnp.infer mcmc && uv run python -m mnp.infer npe --n-sims 50000
uv run python -m mnp.infer sbc
uv run python -m mnp.report all
```

## Provenance of every oracle number

| Number | Source | Used in |
|---|---|---|
| Correction factors 40.37, 37.36, 17.42, 6.22, 6.63, 8.32 | Koelmans et al. 2020, ES&T 54:12307, Table 1 (α = 1.6, pdf ∝ x^−α) | `tests/rescale/test_powerlaw.py` |
| Default α = 1.6 | Kooi & Koelmans 2019, ES&T Lett 6:551 | `rescale/powerlaw.py` |
| α sensitivity 2.2–3.1 | Kooi et al. 2021, Water Res 202:117429 — **abstract only, paywalled**, labelled as such | `report/d3.py` |
| Per-study size ranges and concentrations | Koelmans et al. 2019, Water Res 155:410, SI `mmc1.docx` Table S1, parsed with python-docx (no hand transcription) | `rescale/koelmans2019.py` |
| Debye length 0.79 nm at 150 mM, 25 °C | κ⁻¹ = sqrt(εε₀kT / (2 N_A e² I)) | `tests/ek/test_hard.py` |
| Henry limits 2/3 (κa → 0) and 1 (κa → ∞) | Henry 1931; Ohshima 1994 approximation for f(κa) | `tests/ek/test_hard.py` |
| σ = −0.07 C/m², a = 1.4 µm, zero free parameters | Kobayashi 2008, Colloid Polym Sci — hard latex | `tests/ek/test_hard.py` |
| zN = −0.0015 M, 1/λ = 1.2 nm, 25 °C | Makino & Ohshima 2011, Fig. 2 caption | `tests/ek/test_soft.py` |
| Ontology CURIEs ENM:0000092, NPO:1315, NPO:1914, ENVO:00003064, ENVO:00002011 | OLS4 lookup 2026-09 | `schema/ontology.py` |

No ionic-strength ontology term exists; that field is deliberately unmapped.

## D1 result on the whole corpus (2026-09-13)

All 858 open-access full texts were parsed and every paper that mentions zeta or
electrophoretic mobility was read by a Claude worker through `show`/`ingest` — including
the 372 that print no number at all, because "measured but never printed" is the category
this study is about. **498 papers** carry at least one plastic-particle measurement whose
evidence quote was found verbatim in the article (1910 rows, every one verified).

| Missing condition | k / 498 | fraction | 95% Wilson |
|---|---|---|---|
| Ionic strength | 447 | 89.8% | 87–92% |
| pH | 399 | 80.1% | 76–83% |
| Temperature | 386 | 77.5% | 74–81% |
| Dispersion medium | 131 | 26.3% | 23–30% |
| Instrument | 91 | 18.3% | 15–22% |
| **Any of the five** | **484** | **97.2%** | **95–98%** |

**144 of the 498** report a zeta measurement without printing a single number anywhere in
the retrievable text — figure, supplement or qualitative statement only.

At row level, across all 1910 rows: instrument on 1695, medium on 1582, temperature on 544,
pH on 397, **ionic strength on 260**.

**This table predates the three judgement rules ratified on 2026-09-13**
(`docs/DECISIONS_NEEDED.md`). Scored against them without re-reading a paper
(`tool/rules_impact.py`): temperature missing → **82.5%**, pH → **83.9%**, ionic strength →
**≥76.7%**. The corpus re-extraction under the recorded brief is what will make this table
current; until then quote it as the pre-rules reading.

**An earlier version of this file reported 341 papers and 1459 rows.** That run extracted
only papers where a regex found a printed value, which silently excluded the papers that
report a measurement without printing one — the worst cases, and the ones most relevant to
the argument. Re-running over all 372 excluded papers moved the headline barely at all
(ionic strength 88.9% → 89.8%, any condition 96.8% → 97.2%) while raising the count of
"no number printed anywhere" from 17 to 144. The fractions were sound; the denominator
was not.

Artefacts: `out/tables/d1_stats.md`, `d1_stats.json`, `d1_zeta_table.csv`, `d1_oa_bias.csv`,
`out/figures/d1_missing_conditions.png` (`python -m mnp.report d1`).

**Which number to quote.** Either. The hand-annotated sample below was read against explicit
rules and its interval covers the corpus value on every condition; the corpus figure adds
precision. The one exception is temperature — see the precision/recall section.

## D1 result on the hand-annotated sample (2026-09-12)

50 papers drawn at random, stratified by year band, from the 859 open-access hits; every one
annotated from its own text (not from any model's output). 24 of the 50 report a zeta
potential or electrophoretic mobility of a synthetic-polymer particle; the rest measure
something else (metal oxides, carbon dots, clay, chitosan, protein) or nothing.

| Missing condition | k / 24 | fraction | 95% Wilson |
|---|---|---|---|
| Ionic strength | 22 | 91.7% | 74–98% |
| pH | 18 | 75.0% | 55–88% |
| Temperature | 18 | 75.0% | 55–88% |
| Dispersion medium | 3 | 12.5% | 4–31% |
| Instrument | 1 | 4.2% | 1–20% |
| **Any of the five** | **24** | **100%** | **86–100%** |

Not one paper of the 24 reported all five. A further **7 of 24** describe a zeta measurement
without printing a single number in the retrievable text (figure, SI or range only).

**Robustness.** The parser fixes below were found *after* the first annotation pass, so all 16
papers whose annotation could have been affected were re-annotated from the corrected text.
Every number in the table above is unchanged; only the "no printed number" count moved (8 → 7),
and exactly one paper (PMC9318256) gained values — its 10 measurements had been sitting in a
table the parser could not see. Seven of the eight papers whose newly visible values belong to
non-plastics (chitosan, carbon dots, MgO, clay, Aβ, micromotors) correctly stayed
`no_measurement`.

**Author audit.** `python -m mnp.extract audit-sample --n 10` writes
`data/interim/annotation/audit_10.csv`: 10 of the 50 papers with every judged column blanked,
for Martin to re-judge blind. Saving the filled sheet as `gold_parts/gold_audit.json` and
re-running `gold-merge` makes `evaluate` report Cohen's κ on the five `*_reported` booleans
beside precision/recall. Until then the slide must say "annotated by Claude, not yet audited".

Artefacts: `out/tables/d1_gold_stats.md`, `d1_gold_stats.json`, `d1_gold_zeta_table.csv`,
`out/figures/d1_gold_missing_conditions.png` (`python -m mnp.report d1-gold`). The
whole-corpus extraction reports the same table under the `d1_` prefix.

## Three rules need a human decision

`docs/DECISIONS_NEEDED.md` — three LLM judges (two Claude, one external and API-only) were
given the same 17 gold-vs-extraction disagreements and agreed with each other no better than
chance (κ between the two Claude judges: **−0.05**). The disagreements are perfectly
systematic and all three are *rule* questions the brief does not settle:

1. does a printed PBS recipe count as a reported ionic strength? — 63 rows, 25 papers, up to
   5 percentage points on the headline;
2. is an incubation temperature the measurement temperature? — 54 at-risk rows, and already
   the largest measured source of extraction error (row temperature P 0.15);
3. does a condition stated once carry to another experiment in the same paper? — 1 016 rows
   across 264 papers.

Each question in that file carries the paper's verbatim text, both readings, what each judge
concluded, and the corpus impact.

## Reproducible runs (2026-09-13)

The first corpus run could not say which instructions produced any row. That is now fixed,
and the machinery is in the repository:

```bash
# a brief is data: hashed by content, versioned in git, stored on every record
uv run python -m mnp.extract ingest --pmcid PMC... --json rows.json \
    --brief docs/briefs/extraction.md --model claude-code:sonnet

# workers claim disjoint work from a Postgres queue rather than being handed lists
./tool/test_db.sh up                      # throwaway database for tests
uv run python -c "from mnp.queue import Queue; ..."   # init / claim / done / reap / status

# score a persona against the gold set and pass or fail it on stated thresholds
uv run python -m mnp.report gate --slice data/interim/worklists/gate3_slice.txt
```

| Piece | What it prevents |
|---|---|
| `docs/briefs/` + `brief_sha256` | a rule change that is invisible in the data |
| `.claude/agents/` personas, none with the Agent tool | workers delegating and reporting success having done nothing |
| `mnp/queue.py`, `FOR UPDATE SKIP LOCKED` | two workers handed the same paper; work lost when a worker dies |
| `mnp/report/gate.py` | shipping a persona nobody measured |
| `tests/edge/` (27 cases) | judgement rules that were never anyone's explicit decision |

The gate reports provenance as part of its verdict, so the 836 pre-2026-09-13 records show up
as untraceable every time it runs rather than being quietly forgotten.

## How this was built

`docs/ARCHITECTURE_PLAN.md` is the plan for a reproducible rebuild: repo-resident state, a
leased work queue, tool-restricted agent personas, evaluation gates before any corpus run, a
24-case edge set for human adjudication, and a measured answer on source coverage (OpenAlex
holds ~3,513 works on this topic against our 858, and 78% of a 600-work sample is not in our
corpus).

`docs/METHODOLOGY.md` maps the agent orchestration that produced the corpus — the phases,
the worker counts, what is reproducible and what is not, seven failure modes with their
evidence, and the architecture that should replace it (a leased work queue, a
tool-restricted worker type, and the brief hash stored beside every record).

The short version: the *pipeline* is sound and reproducible; the *judgement* is not,
because the worker briefs lived in a session scratchpad and one of them is now lost. Every
record carries a `prompt_sha256`, but it has exactly one value — the CLI's system prompt —
so no row can be traced to the instructions that shaped it.

## Units come from the article, not from a transcription

    uv run python -m mnp.extract units --pmcid PMC11117817        # human-readable
    uv run python -m mnp.extract units --pmcid PMC11117817 --json # machine-readable

`mnp.extract.units` reads the printed unit out of the paper itself — a table header, a
row label, a caption, or the sentence carrying the number — and reports what it means
numerically. It exists because the unit is the one field a retyped transcription can
corrupt without leaving any trace in the value: `cm²/Vs` retyped as `m²/Vs` converts
10⁴ times too large and still looks like a plausible number. That is exactly how 25
mobility rows came to be stored as 400 instead of 4.00.

Every ingest now cross-checks the claimed unit against the printed one and raises
`unit_disagrees_with_article` when the two would convert differently. Agreement in
spelling is not required — only in factor — so `cm2/Vs` and `cm² V⁻¹ s⁻¹` agree.

What the whole corpus prints for mobility, found by the tool rather than asserted:

| printed | papers | factor to 1e-8 m²V⁻¹s⁻¹ |
|---|---|---|
| `μm cm V-1 s-1`, `µm cm/Vs`, `µmcm/V` | 5 | 1 |
| `cm 2/Vs` | 2 | 10⁴ |
| `linear electrophoretic mobility × 10 –4 (cm 2 V -1 s -1)` | 1 | 1 |

The last row is why the tool reads the whole header when an exponent sits outside the
brackets: the paper's own ×10⁻⁴ cancels the cm², and reading `(cm 2 V -1 s -1)` alone
would have been wrong by 10⁴ in the other direction.

## Parser bugs the annotation caught

Hand annotation was run against the same `show` output the extractor reads, which turned the
gold set into a test of the parser. Three defects surfaced and are now fixed and covered:

- **Tables outside `<body>`.** 79 of 858 articles (9%) park every table in `<floats-group>`;
  the parser only walked `<body>`, so their data was invisible. One of them (PMC9318256) is
  captioned "Zeta potential of the different effluents" and holds 10 values.
- **Quantity in the caption, unit in the header.** A column headed "Before Treatment (mV)"
  is a zeta potential when the caption says so; header-only matching found nothing.
- **Superscripts in units.** `10⁻⁸ m²V⁻¹s⁻¹` was not recognised as the 10⁻⁸ prefix, so every
  mobility in that paper was multiplied by 10⁸ — `-4.00` stored as `-400`. Superscript digits
  are now normalised before any unit is matched, and a mobility conversion that lands beyond
  |µ| = 100 ×10⁻⁸ is refused outright (`unit_conversion_refused_implausible`) rather than
  stored: no colloid has such a mobility, so a conversion that says so read the unit wrongly.
- **A hyphen, an en-dash or a true minus as the sign.** Eight different dash characters appear
  in front of zeta values in this corpus (U+2010, U+2013, U+2212 among them) and each read as
  a *positive* number. A dash immediately before a digit and not preceded by one is now a sign;
  `2–3%` and `20 – 30` stay ranges, and a tab is a cell separator rather than a range separator.
- **Decimal commas.** A paper printing `-31,63` and `0,026 M` yielded nothing to the scanner.
  Commas inside a single number are now decimals, while `[4,5]` citation lists are not.
- **Citation lists next to a unit.** `[4,5] mV` is a reference, not a measurement.
- **En-dash as a minus sign.** Whole tables print `–13.4 ± 0.8`; the values read as
  *positive*. A dash immediately before a digit and not preceded by one is now a sign, while
  `2–3%` and `20 – 30` stay ranges — and a tab counts as a cell separator, not a range
  separator, which the first version of the fix got wrong.
- **"High mobility group box transcription factor 1."** A gene family whose name contains
  "mobility" turned one gene-expression table into 42 phantom mobility values. A mobility
  header now needs electrophoresis, `EPM`, or a mobility unit.
- **Abstracts were never read.** 8 of 858 papers print a zeta value only in the abstract. It is
  now included; a value the abstract merely restates is counted once, not twice, because an
  abstract restates the body rather than measuring anything.
- **Document order and signs.** A child's tail was emitted before its subtree ("Figure 2 b"
  became "2Figure b"), and a true minus followed by a thin space (Springer's negative numbers)
  parsed as positive — silently turning −43.3 mV into +43.3 mV.

After the fixes: 475 of 858 papers carry at least one regex-detectable printed value
(2172 in total, up from 1988 before the table work). Papers whose gold annotation predated the fixes were re-annotated; gold parts
named `gold_r*.json` supersede earlier ones per paper in `extract gold-merge`.

## Precision and recall against the gold set

`python -m mnp.extract evaluate --gold data/interim/annotation/gold_50.csv`, scored only on
the 50 annotated papers — a prediction on an unannotated paper is neither right nor wrong,
and counting it as a false positive once drove precision to 0.05.

| Level | Field | P | R |
|---|---|---|---|
| paper | instrument reported | 1.00 | 1.00 |
| paper | medium matches exposure | 1.00 | 1.00 |
| paper | pH reported | 1.00 | 0.83 |
| paper | medium reported | 0.95 | 0.95 |
| paper | temperature reported | 0.83 | 0.83 |
| paper | ionic strength reported | 0.50 | 0.50 |
| row | value | 0.68 | 0.74 |
| row | pH | 0.68 | 0.65 |
| row | ionic strength | 0.67 | 0.50 |
| row | **temperature** | **0.15** | **0.23** |

Paper-level precision is 0.83–1.00 on every condition but ionic strength, where the gold
set contains only two papers that report it at all (tp 1, fp 1, fn 1) — too few to score,
not a measured weakness.

**Row-level temperature is the weakest number here** (P = 0.15, R = 0.23; 6 true
positives against 35 false and 20 missed). The extraction records an *incubation*
temperature — particles held at 25 °C or 37 °C before measurement — as the measurement
temperature, which the annotation rules exclude. Every disagreement traced back to that one
distinction, which the papers themselves blur. Quote the gold figure (18 of 24 missing)
rather than the corpus one for temperature alone.

## Two extractor paths (D1)

`run` calls an OpenAI-compatible API. `show` + `ingest` is the same pipeline with the
model call taken out: any agent (here: Claude Code subagents on the author's subscription)
reads what `show` prints, writes the JSON, and `ingest` applies coercion, the verbatim-quote
guard, condition checks and regex coverage exactly as `run` would, recording
`model=claude-code:<name>`. `ingest` replaces an existing record for the PMCID, so a worker
can fix and resubmit; it prints the unmatched printed values so the worker sees what it
missed. The gold set is annotated separately from the raw methods text (not from the
extraction prompt) and 10 papers are audited by the author; the slide must say so.

## Model chain (D1 extraction)

`from_env()` builds the chain as `MNP_MODEL_CHAIN` (comma list) if set, else
`OPENROUTER_MODEL` + `OPENROUTER_FALLBACK_MODELS` from the backend `.env`; `--model`
replaces the head. On OpenRouter every call carries `reasoning: {exclude: true}` —
without it `nemotron-3-super:free` returns its chain-of-thought as untagged content and
never reaches the JSON (live, 2026-09-12: 0 rows in 124 s; with exclusion 14/14 rows,
all quotes verified, in 166 s). `complete_json` gives each model one call and one nudge,
then moves down the chain. Every reply is cached under `data/interim/llm_cache/` keyed by
sha256(model, system, user).

Live check before any batch run: extract `tests/fixtures/PMC5090179.xml` and require
coverage 14/14 with zero flags.

## What the extraction guarantees, and what it does not

- Every numeric field is parsed deterministically from the string the model copied
  (`extract/coerce.py`, 100+ cases in `tests/extract/test_coerce.py`).
- `evidence_quote` must be a verbatim substring of the article; otherwise the row is
  `evidence_unverified` and excluded from every headline number.
- The value must appear inside its own quote (`value_not_in_quote`).
- Reported pH / temperature / ionic strength must appear somewhere in the article. This
  is necessary, not sufficient: a "37 °C" from an incubation step elsewhere in the paper
  passes. The quote check is the one that carries weight.
- Coverage is **not** recall of plastic measurements. The scanner finds every printed
  zeta/mobility number regardless of material, so a paper that reports zeta for a metal
  oxide, a cell, a membrane or a protein alongside its plastic scores low coverage while
  being extracted correctly. Treat coverage as "printed values of any material that the
  extraction claimed"; true recall is the gold-set precision/recall.
- Every printed zeta/mobility number is found independently by regex
  (`find_candidates`); per-paper coverage = extracted rows that claim a printed number,
  one-to-one. Recall is therefore measured on every paper, not only on the gold set.

## Mutation table

Each mutation was applied, the named test went red, the mutation was reverted and the
suite went green again (2026-09-12). Every row below was run this way; none is asserted.

| Mutation | Test that fails |
|---|---|
| flip the sign of ψ_DON | `test_soft.py::test_donnan_potential_sign_follows_sign_of_ZN` (+7) |
| drop the (1 + (ZN/2zn)²)^¼ factor in κ_m | `test_soft.py::test_kappa_m_exceeds_kappa_by_the_quarter_power_factor` |
| `1 − α` → `−α` in `cf_closed` | 23 tests in `tests/rescale/test_powerlaw.py` |
| swap default and measured ranges in the correction factor | `test_closed_form_matches_numerical_integral` |
| swap the ranges in the α = 1 branch | `test_alpha_one_uses_the_log_form` |
| read tables only from `<body>` again | `test_tables_parked_in_floats_group_are_still_parsed` |
| caption never lends its quantity to a unit-only column | `test_table_columns_take_their_quantity_from_the_caption_when_headers_only_carry_units` |
| drop the minus before a thin space | `test_minus_sign_followed_by_a_thin_space_keeps_its_sign` |
| stop expanding colspan/rowspan | `test_colspan_headers_are_expanded_so_columns_line_up` |
| duplicate a spanning data cell into every column it covers | `test_a_spanning_data_cell_is_not_duplicated_into_a_second_value` |
| count an abstract's restated value as a second measurement | `test_a_value_the_abstract_merely_restates_is_not_counted_twice` |
| treat a bare "mobility" header as electrophoretic mobility | `test_a_gene_called_high_mobility_group_is_not_an_electrophoretic_mobility` |
| stop reading a leading en-dash as a minus | `test_en_dash_table_values_are_read_as_negative` |
| stop normalising superscript digits in units | `test_a_superscript_ten_to_the_minus_eight_is_not_multiplied_again` |
| accept an implausible mobility conversion | `test_an_implausible_converted_mobility_is_refused_not_stored` |
| stop reading a decimal comma | `test_comma_decimal_table_values_are_found` |
| make one row claim a value restated elsewhere *and* a repeated table cell | `test_a_value_printed_twice_in_one_table_still_needs_two_rows` |
| read only the header row when looking for a printed unit | `test_units_command_prints_what_the_article_prints` |
| ignore an exponent printed outside the brackets | `test_a_unit_is_read_out_of_a_table_header[linear …]` |
| treat any unit-factor difference as agreement | `test_disagreement_is_detected_between_a_claimed_unit_and_the_printed_one` |
| skip the unit cross-check on ingest | `test_a_claimed_unit_that_contradicts_the_printed_one_is_flagged` |
| emit a child's tail before its subtree | `test_nested_inline_elements_keep_document_order` |
| Henry factor fixed at 1 | `test_hard.py::test_henry_limits_two_thirds_and_one` (+1) |
| select the first `<sec>` instead of the methods section | `test_methods_selected_by_sec_type` |
| count None == None as a true positive | `test_row_level_value_scores_use_field_tolerances` |
| delete the `<think>` strip | `test_strip_think` |
| drop the evidence-substring guard | `test_verify_row_flags_a_quote_that_is_not_in_the_text` |
| value-in-quote check always passes | `test_verify_row_flags_a_value_absent_from_its_own_quote` |
| ionic strength from a named salt ignores the salt | `test_parse_ionic_strength[10 mM CaCl2]` |
| return κ instead of 1/κ | `test_hard.py::test_debye_length_150mM_25C_is_0p79nm` (+3) |

## D4 notes

- Model values (×10⁻⁸ m² V⁻¹ s⁻¹), cross-checked against an independent pure-Python
  recomputation to 4 digits: Makino oracle (zN −0.0015 M, 1/λ 1.2 nm, 25 °C) −0.827 /
  −0.120 / −0.035 at 1 / 10 / 100 mM, plateau −0.023; Kobayashi hard latex
  (σ −0.07 C/m², a 1.4 µm, KCl) −9.39 / −9.46 / −5.56, peak −10.40 at 3.0 mM — matches
  the paper's own Fig. 1 theory curve (≈ −10.3 minimum). Debye 150 mM: 0.7855 nm.
- Printed-fit bank: 25 rows, 12 complete. Incomplete rows carry the missing parameter in
  `notes`; nothing was invented. Kobayashi 2008 Fig. 2 (Na₂SO₄, 1:2) is outside the z:z
  model; Hill & Saville PEO coatings are uncharged layers, outside the fixed-charge model.
- NPE: sbi's z-scoring is dominated by the prior corner (|ZN| ≈ 0.3 M, 1/λ ≈ 30 nm,
  |μ| up to 3000×10⁻⁸); the observation is embedded as arcsinh(μ/10⁻⁸) (bijective).
  Soft SBC passed at 5000 sims only marginally (p = 0.013, 0.016). The final 50 000-sim run
  (5.7 min CPU) passes cleanly: KS p = 0.96 / 0.47 (soft |ZN|, 1/λ), 0.52 / 0.51 (hard σ, a);
  every printed parameter is recovered within |z| ≤ 2.
- No digitised CSVs yet: every D4 figure is labelled "synthetic from printed fits". Drop
  CSVs into `data/raw/digitised/<dataset>.csv` and re-run `python -m mnp.ek qa`.

## D3 data caveat

Koelmans 2019 Table S1 is prose inside cells, not a tidy table. `rescale/koelmans2019.py`
derives size floors from the "Size, shape" cell (falling back to the smallest mesh/sieve
in "Sampling method") and concentrations from "Value" (number units preferred over mass;
mean > median > single > geometric mean of a range). Every derived number carries its
source cell in `notes`. 55 rows parsed, 47 rescaled; 8 excluded (6 no size floor, 2 no
concentration). 28 of 47 report only a lower bound and are rescaled with an assumed
5000 µm upper limit (`upper_assumed`). python-docx drops the Symbol-font µ; the parser
reads the XML directly.
