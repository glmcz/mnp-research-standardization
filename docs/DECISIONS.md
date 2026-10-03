# Decision register: the MNP zeta-potential proof of concept

This file lists the choices behind MNP-KB v0 and its evaluation. For each one it records the
question, the options, the choice, who made it, and the evidence. It has two readers. One is a
reviewing colloid scientist or software engineer who asks "why did you do X and not Y?". The
other is Martin, who has to answer that question aloud.

**How to read an entry.** The bold line is the decision. The lines under it are:

- **Question**: what had to be decided.
- **Options**: only the options the record shows were considered. Where none are recorded, the
  entry says so.
- **Decided by**: one of four answers.
  - *Martin*, with his words where they exist.
  - *Proposed by the agent, accepted by Martin*.
  - *Agent default, not reviewed*.
  - *Not recorded*: the record names no one. Usually the choice was already in place at the
    first commit, `1cfc5a5`, so it predates this repository's history.
- **Why**: every number names the file or commit it comes from. Where the record gives no
  reason, the entry says **reason not recorded**, and the entry also appears in the open
  decisions.
- **Limits**, **Built** (commits and files) and **Verified** (tests, `report reproduce`, a hand
  check).

A quote marked *(session)* is Martin's own words from the 2026-09-26 → 30 sessions. No commit
or document holds them, and this file is the first place they are written down.

**What this file does not repeat.** It links to two generated documents instead of copying
them:

- `out/demo/METHOD.md` holds the scientific rules with worked numbers.
- `out/review/REVIEW.md` is the deep review: every column, formula, claim and open issue.

Both are rebuilt by `report reproduce`. Where they disagree with this file on a number, they
are right and this file is wrong.

**Snapshot.** Branch `line-addressed-citations` at `7a0b858` (2026-09-30). The test names under
"Verified" exist in the tree on 2026-10-01. This register did not run them, because another
agent was changing the parser while it was written (see CP-07).

**A naming clash.** Martin's rules R1, R2 and R2b (RC-08, RC-09) keep their names.
`docs/FINDINGS_comparability.md` also numbers its comparability rules R1–R8. Those are
different rules, and this file calls them "comparability rules".

---

## Index

Status:

- **built**: in effect in the code or the data. A cut counts as built.
- **decided-not-built**: decided, but the work has not landed.
- **open**: not decided.

| ID | Decision | Decided by | Status | Commit |
|---|---|---|---|---|
| CP-01 | One Europe PMC query, open access only | Not recorded | built | `1cfc5a5` |
| CP-02 | Vendor the corpus, never re-fetch | Agent | built | `11c0d7d` |
| CP-03 | Readers get line-numbered text, not JATS or JSON | Agent | built | `8771fb1` |
| CP-04 | A line is a paragraph, addressed by a content hash | Agent | built | `f29fe71` |
| CP-05 | Add line addresses to the stored rows, do not re-extract | Agent (acceptance not recorded) | built | `0749420` |
| CP-06 | Do not rebuild the reading path around a selector | Agent | built | `2a96b3e`, `ce49f01` |
| CP-07 | Fix the parser's Methods defect | Martin | built | `9b17a6c`, `5012fdf` |
| EX-01 | Scanner, worker, verifier; only the worker judges | Not recorded | built | `1cfc5a5`, `67d551d` |
| EX-02 | Quotes must be verbatim; unverified rows dropped and counted | Not recorded | built | `1cfc5a5` |
| EX-03 | Extraction by Claude Code subagents, no API key | Not recorded | built | `1cfc5a5` |
| EX-04 | Every record names its brief | Agent | built | `9d040cd` |
| EX-05 | The measurand must be the plastic particle (S8, S21, S23) | Martin | built | `9d040cd`, `fc7960b` |
| EX-06 | Refuse an unreadable unit; step guard reads only the number's piece | Agent | built | `550f8f9` |
| EX-07 | Value checked on the cited line; condition scope stays the quote | Martin | built | `f9249bb` |
| EX-08 | Apply the 2026-09-28 prompt audit | Not recorded (another session) | built | `d3d89c9`, `769b0a4` |
| EX-09 | Measure reading noise with a blind re-read control | Agent | built | `09c11cd` |
| EX-10 | Re-read the 239 papers not read under the current brief | Martin | decided-not-built | (run in progress) |
| EX-11 | Keep each worker's raw JSON in the run directory | Agent | built (from `reread-brief-20261003`) | — |
| RC-01 | Five conditions; fully conditioned = all five on one row | Not recorded | built | `1cfc5a5`, `35d340e` |
| RC-02 | A printed composition counts, flagged derived (Q1) | Martin | built | `1cfc5a5` |
| RC-03 | An incubation temperature is not the measurement temperature (Q2) | Martin | built | `1cfc5a5` |
| RC-04 | A condition holds only inside its own experiment (Q3) | Martin | built | `1cfc5a5` |
| RC-05 | Absence is a value, never imputed | Not recorded (standing rule) | built | `1cfc5a5`, `0858865` |
| RC-06 | No nominal buffer lookup; no conductivity conversion | Not recorded; agent | built | `1cfc5a5`, `c3cbee4` |
| RC-07 | "Reported" is generous; every figure is an upper bound | Not recorded | built | `1cfc5a5`, `35d340e` |
| RC-08 | R1/R2: 0 mM and step temperatures cleared, row kept | Martin | built | `4a3087c` |
| RC-09 | R2b: storage and incubation temperatures cleared | Martin | built | `d538ce5` |
| RC-10 | R3: a buffer's concentration is not a reported ionic strength | Martin | built | `6a93c69` |
| CM-01 | Comparability is a pair predicate in code (kind E) | Agent (acceptance not recorded) | built | `ce49f01`, `0858865` |
| CM-02 | The comparability rules and their tolerances | Agent | built | `0858865` |
| CM-03 | The reported value is never evidence of comparability | Agent | built | `0858865` |
| CM-04 | Missing functionalisation ≠ bare; "unaged" ≠ bare; spellings only | Agent; Martin for "unaged" | built | `0858865`, `4003a11` |
| CM-05 | A third verdict: conditionally comparable | Agent | built | `0858865` |
| CM-06 | Kind E set = full census of positives + five seeded strata | Agent | built | `0858865`, `4003a11` |
| HM-01 | A missing input gives an interval or nothing, never a default | Agent → Martin | built | `220223d` |
| HM-02 | Which conversion model counts as named | Agent (in review) | built | `220223d`, `f78a4f5` |
| HM-03 | Conversion-model denominator = papers reporting a zeta | Agent | built | `9ce15fa`, `220223d` |
| HM-04 | Debye length assumes a 1:1 electrolyte at 25 °C | Agent | built | `0858865` |
| RS-01 | Per-paper figures primary, cluster bootstrap, design effect | Agent (acceptance not recorded) | built | `6e49bd6`, `220223d` |
| RS-02 | Resample paper indices; never regroup by the cluster key | Agent | built | `ff05351`, `220223d` |
| RS-03 | Rebuild uncommitted results; report differences, do not tune | Agent | built | `220223d` |
| GR-01 | Tools are hypotheses: a five-cell grid; the zero is no tool | Martin's reframe; grid by agent | built (B, D) | `761349d`, `189d801` |
| GR-02 | Cut cell A (long context) | Agent (acceptance not recorded) | built | `ce49f01` |
| GR-03 | Cell B is BM25 over line-addressed text | Agent | built | `2a96b3e` |
| GR-04 | Query kinds A–E; kind D so prose retrieval can win | Agent | built | `761349d` |
| GR-05 | Reader is Sonnet, pinned to `claude-sonnet-5` | Martin (model); agent (pin) | built | `189d801` |
| GR-06 | The reader sees the prompt and nothing else | Agent | built | `189d801` |
| GR-07 | The denominator is the plan; failures retried, never scored | Agent | built | `189d801` |
| GR-08 | Pilot ten before a sweep; fix what it finds | Agent → Martin | built | `4003a11`, `e00e85c` |
| GR-09 | A usage-policy refusal is scored wrong, never re-asked | Martin | built | `3fa1da1` |
| GR-10 | A citation written inside the answer counts | Martin | built | `7ba7d35` |
| GR-11 | Kind E reported as recall per verdict and balanced accuracy | Agent | built | `e1b4624` |
| GR-12 | Run cell B in full, all 400 questions | Martin | built | `e1b4624` |
| GR-13 | Kind E set redrawn after R2b; new set accepted | Martin | built | `d538ce5` |
| GR-14 | Never cut cell C | Agent (acceptance not recorded) | decided-not-built | — |
| DM-01 | Thirteen real cases, re-sampled four ways, plus METHOD.md | Agent → Martin | built | `220223d`, `d35f82d` |
| DM-02 | Each case pins a paper and a check that proves its mode | Agent | built | `220223d` |
| DM-03 | Demo answers are read from committed runs, never regenerated | Agent | built | `d35f82d` |
| DM-04 | No demo lookup rests on a value a rule cleared | Agent | built | `4a3087c` |
| RV-01 | A generated review guide with worksheets | Martin (request); agent (form) | built | `78a65ac`, `f78a4f5` |
| RV-02 | An HTML results page, builder kept in the repo | Martin (request); agent (form) | built | `0056e12` |
| RV-03 | Every reader-facing document opens with one generated scope block | Martin | built | `0f3d549` |
| RV-04 | A check done by a Claude agent is called that, never a hand check | Martin's standard (R6) | built | `32fc0d3` |
| LR-01 | v0 = parquet, JSONL, schema, a self-computing card | Martin (date); agent (form) | built | `f29fe71` |
| LR-02 | CC BY 4.0; quotes only from CC BY and CC0 sources | Martin | built | `61aa0a7` |
| LR-03 | Licence read from each article's JATS; unclear means withheld | Agent | built | `61aa0a7` |
| LR-04 | The dataset's author is Martin Durak | Martin | built | `b408c51` |
| OS-01 | Confirm the particles' origin before documenting it | Martin | built | `d4be112`, `0dfc047` |
| OS-02 | Environmental rows: missing ionic strength highlighted; no estimate possible | Martin | built | `0dfc047` |
| OS-03 | Stay with the 491 papers; state the scope first | Martin | built | `0f3d549` |
| OS-04 | Airborne charge: an open direction, not an extension | Martin | open | `7a0b858` |
| PR-01 | Deterministic work first; tokens only where a model must read | Agent | built | `7f7ba5b` |
| PR-02 | `report reproduce`: offline, network refused, diff against HEAD | Agent | built | `11c0d7d` |
| PR-03 | The protocol document is generated from a tested registry | Agent | built | `20e7d4c` |
| PR-04 | Workers claim papers from a leased queue | Agent | built | `1cfc5a5` |
| PR-05 | Gate reviewers: ALLOW or ESCALATE, never REJECT | Agent (offered for reversal) | built | `7f7ba5b` |
| PR-06 | An LLM judge panel routes disputes; Martin decides | Martin | built | `1cfc5a5` |
| PR-07 | Tests are proven red | Agent | built | `220223d` |
| PR-08 | Corrections stay in place | Agent | built | `1fedb71` |
| PR-09 | `ingest --dry-run`: verify a reading without recording it | Agent | built | `0e739d4` |

---

## Corpus and parsing

**CP-01 · The corpus is one Europe PMC query, open access only, read from full JATS text.**
- Question: which literature does the dataset sample?
- Options: none recorded at the time. Later, on 2026-09-13, `docs/ARCHITECTURE_PLAN.md` §8
  considered other sources: OpenAlex for discovery, Unpaywall and PDFs for full text, and
  caNanoLab and eNanoMapper as a structured contrast.
- Decided by: not recorded. The query and the Europe PMC client are already in `1cfc5a5`.
- Why: **reason not recorded.** `ideas.md` §4 says only that JATS XML is what Europe PMC
  serves: "not a choice". OpenAlex was deferred because it "changes every denominator; that is
  a new study" (`docs/PLAN_2026-09-28.md` §7).
- Limits:
  - Counts: 1 115 hits, 862 open access, 858 fetched, 491 papers with a measurement. 253
    paywalled hits were never read (`docs/2026-09-30-corpus-scope-notes.md`, from
    `hit_counts.json` and `d1_stats.json`).
  - OpenAlex held 3 513 works against Europe PMC's 1 117. Of 600 OpenAlex works sampled, 78 %
    were not in the corpus (`ARCHITECTURE_PLAN.md` §8).
  - Dataset card limits 1 and 2.
- Built: `src/mnp/corpus/epmc.py`, `queries/q1.txt`.
- Verified: the counts are in `out/tables/d1_stats.json`, and
  `tests/report/test_scope.py::test_the_block_states_the_corpus` holds them.

**CP-02 · The corpus is vendored and sha256-pinned, and is never re-fetched.**
- Options: re-fetch from Europe PMC when rebuilding, or keep the XMLs in the repo.
- Choice: 858 XMLs in `data/raw/epmc/xml.tar.gz` (27.7 MB), packed in a deterministic archive
  with a `sha256sum` manifest.
- Decided by: agent default, not reviewed (`11c0d7d`).
- Why: "Europe PMC is not an archive, so re-fetching in a year gives a different corpus and
  moves every denominator" (`11c0d7d`).
- Limits: the repo now holds 244 full texts that are not CC BY or CC0
  (`HANDOFF_2026-09-28.md` §4 item 4). That matters only if the repo becomes public (OD-20).
- Verified: `tests/corpus/test_snapshot.py` (`test_one_flipped_byte_is_caught`,
  `test_an_extra_file_is_caught`) and `report reproduce`.

**CP-03 · A reader gets line-numbered text (`md_linenum`). Raw JATS and JSON stay off the
reading path.**
- Options: the seven arms of E1: `xml_raw`, `text_current`, `md_plain`, `md_anchored`,
  `md_linenum`, `md_spanids` and `ir_json`.
- Decided by: the agent, from E1. `ideas.md` §2 lists raw JATS and JSON as rejected (R8, R9)
  with "Measured" as the reason, and names no decider.
- Why: tokens per paper: `xml_raw` 41 127 (7.80×), `md_linenum` 1.02×, `ir_json` 1.45×
  (`docs/FINDINGS.md` E1). A line number gives every line a citable address for about 2 %
  more tokens.
- Limits:
  - The `ir_json` figure depends on a schema E1 never wrote down. It ranges from 1.3× to 1.8×
    (`8771fb1`).
  - Representation moves at most about 13 % of the end-to-end budget (FINDINGS E1, "Ceiling").
- Built: `src/mnp/corpus/represent.py` and `report e1` (`8771fb1`).
- Verified: `report e1` rebuilds `out/tables/e1_representation.csv` offline inside
  `report reproduce`. Six of the seven arms reproduce (`8771fb1`).

**CP-04 · A line is a paragraph, and its id is a content hash, not a line number.**
- Options:
  - Granularity: sentence ids (+12 %), paragraph lines (+2 %) or JSON spans (+45 %)
    (`DESIGN_2026-09-17_tool-value-grid.md` §2, from E1).
  - Address: the position in the document, or a hash of the content.
- Choice: one line per `<p>`, section title or table row. The `line_id` is the first 16 hex
  characters of sha256(section path, ordinal, text).
- Decided by: agent default, not reviewed (`f29fe71`).
- Why: a paragraph is the cheap unit (E1), and a hash still resolves after a parser fix
  renumbers the lines (`f29fe71`).
- Limits: a paragraph can cover several experiments.
  - 44 rows (10 citation sets) have one citation that spans several ionic strengths
    (`docs/GATE_LOG.md`, "On the 44 rows").
  - Of those 44, 36 are cases where "our citation unit [is] too coarse" (`fe51a4b`,
    `docs/FINDINGS_44_shared_citations.md`).
  - This is why condition scope stays on the quote (EX-07).
- Verified: `tests/corpus/test_lines.py` (`test_a_line_id_ignores_the_global_line_number`,
  `test_inserting_a_paragraph_early_does_not_move_ids_in_other_sections`,
  `test_every_stored_quote_in_the_corpus_locates`).

**CP-05 · The existing rows get line addresses by locating their stored quotes. The corpus is
not re-extracted.**
- Options: locate the stored quotes (about 0 tokens), or re-extract the corpus (about 17.5 M
  tokens, which "will not finish by 28.9") (`ideas.md` §10.4).
- Decided by: proposed by the agent ("Claude's recommendation", `ideas.md` §10.4). Martin's
  acceptance is not recorded. The recommendation also included re-extracting a ~100-row sample
  with a second model family. That half was never built.
- Why: every stored quote is verbatim-verified, so every one locates. The cost is zero tokens
  against about 17.5 M (`DESIGN_2026-09-17` §2).
- Limits:
  - The reading judgement is still the original run's.
  - On these rows the change is "monotone-permissive": the line ids were derived from the
    quotes, so a check against the line can only remove flags (GATE_LOG, Card 1, engineer).
- Built: `0749420` (`extract retrofit`). All 1 890 rows carry a citation: 3 899 citations over
  1 449 lines.
- Verified: a second run is byte-identical (`0749420`). The flags `evidence_not_located` and
  `line_document_unavailable` are both 0.

**CP-06 · The reading path is not rebuilt around a query-conditioned selector.**
- Options: five selectors (whole document, the incumbent `extraction_text`, BM25, a structured
  selector, seeded random), measured in E6 (`docs/FINDINGS_selector_bakeoff.md`).
- Decided by: the agent, from E6 (`ce49f01`). `HANDOFF_2026-09-24.md` §4 lists it as settled
  and names no decider.
- Why: the 12 000-token budget binds on only 12–13 of 491 papers, so a perfect selector is
  worth about 1.6 % of end-to-end tokens (`2a96b3e`).
- Limits: E6's ground truth is the incumbent's own citations, so its absolute scores are
  circular. Only the ordering of the selectors is supported (`2a96b3e`).
- Verified: `tests/eval/test_selectors.py`
  (`test_incumbent_reproduces_extraction_text_verbatim_under_its_real_budget`,
  `test_a_value_query_leaks_its_terms_into_the_target_line`).

**CP-07 · Fix the parser's Methods defect.**
- Question: in 208 of 491 papers, `jats._find_methods` matched `supplementary-materials`, so the
  real Methods section never reached the text the extraction read.
- Options: fix the parser and re-extract the 208 papers, or keep the extraction and state the
  bias (`HANDOFF_2026-09-28.md` §8).
- Decided by: Martin, 2026-09-30: "fix" *(session)*.
- Why: those papers report conditions less often. Share of papers with any row reporting each
  condition, the 208 against the rest (`HANDOFF_2026-09-28.md` §8, `REVIEW.md` §8 item 18):
  - medium: 71.2 % against 76.3 %
  - ionic strength: 8.7 % against 11.7 %
  - temperature: 19.2 % against 23.0 %

  So the headline condition-reporting figures may be biased downward.
- Limits:
  - Found in `d4be112`, which repaired it only for the origin reader.
  - Scope settled 2026-10-01 (Martin, from options with measured costs): re-extract only the
    208 papers, through the same pipeline and model family as before; ask every reader question
    again on the new table (cells D and B in full, the demo); drop the 7 rows that are not the
    authors' own measurement.
  - Window rule settled 2026-10-01. Martin first chose an "additive" variant, which kept the
    keyword windows whose only hit now sits inside the recovered Methods. That choice rested on
    the agent's wrong premise that it was a one-line, local change. Measured as a global rule, it
    changes the text of 652 papers, 230 of them untouched by the defect. Martin then chose the fix
    as written: one window rule for all papers, under which the 208 behave like the 283 that were
    parsed correctly. The 77 lines it stops showing are evidence for 0 current rows
    (`tool/methods_fix_impact.py`, `data/interim/methods_fix_impact.json`).
  - `REVIEW.md` §8 item 18 and card limit 8 still say "open". Both must change when the fix
    lands.
- Built: the parser fix `9b17a6c` (branch `methods-fix`), with `tool/methods_fix_impact.py`, which
  measured the fix before any model was called. The re-extraction is `5012fdf`, run
  `methods-fix-20261001`: 208 papers, 224 ingests, 778 rows from 198 papers (769 from 208
  before). Ten papers now hold no row. Their only zeta was cited from another study, came from a
  review, or belonged to a gold-core particle.
- Verified: `tests/corpus/test_jats.py` (two tests, red before the fix). The impact JSON was
  checked independently: the 77 lines the window rule hides are evidence for 0 rows. The 283
  untouched papers rebuild to identical rows. Condition reporting on the 208 moved down, not
  up: medium 81.5 → 76.5 %, pH 20.0 → 15.3 %, temperature 19.5 → 16.2 % per row. EX-09
  explains why.

## Extraction and verification

**EX-01 · Scanner, worker, verifier. Only the worker uses judgement.**
- How it works:
  - A regex scanner finds every printed value and knows nothing about materials.
  - A model worker decides what each value means.
  - A deterministic verifier checks the worker's claim against the article.
  - `extract ingest` is the only thing that writes data (`docs/METHODOLOGY.md` §1–2).
- Decided by: not recorded. The split is in place at `1cfc5a5`.
- Why: "Each caught errors the others could not" (METHODOLOGY §6). The scanner's recall is
  0.98 against 85 gold values (`67d551d`).
- Limits: the verifier checks text, not judgement. Coverage is not recall (README, "What the
  extraction guarantees").
- Verified: `python -m mnp.eval all` scores each stage separately (`67d551d`).
  `tests/eval/test_stages.py::test_verify_must_catch_every_adversarial_row` catches 7 of 7.

**EX-02 · Every quote must be verbatim in the article and the value must sit inside it. An
unverified row is dropped and counted.**
- Decided by: not recorded. The rule is in place at `1cfc5a5`.
- Why: before the guard, seven fabricated quotes each reached production once (`ideas.md`
  §6.5). The guard also caught a unit-conversion bug that had corrupted 25 rows (METHODOLOGY
  §6).
- Limits: "verified" means the text exists. It does not mean the value was read correctly or
  that the quote belongs to this measurement (`REVIEW.md` §2). Today 1 890 of 1 890 rows are
  verified.
- Verified: the fabrication fixture `tests/eval/fixtures/verify_adversarial.json` is caught 7
  of 7 (GATE_LOG, Card 1 outcome).

**EX-03 · Extraction runs as Claude Code subagents through `extract show` and `extract ingest`.
No API key is configured.**
- Options: the API path (`extract run` over an OpenRouter chain) or the subagent path (README,
  "Two extractor paths").
- Decided by: not recorded.
- Why: **reason not recorded.** The record states the fact but not the reason:
  - "There is no OpenRouter key, so extraction runs through the subagent path"
    (`docs/DEMANDING_PROCESSES.md`).
  - "no API key is configured and that is deliberate" (`HANDOFF_2026-09-24.md` §6).
  - Why Sonnet was the worker model is also not recorded. Opus read 30 records "during a
    Sonnet rate-limit window" (METHODOLOGY §2).
  - Rows today: `claude-code:sonnet` 1 806, `claude-code:opus` 84 (`REVIEW.md` §2).
- Limits: the brief behind most records was deleted with a scratchpad (METHODOLOGY §3; EX-04).
- Verified: no live check of the subagent path is recorded. The API path has one: PMC5090179,
  14 of 14 (README, "Model chain").

**EX-04 · Every record must name the brief it was produced under.**
- Options: store a brief hash on each record (proposed in METHODOLOGY §5.3), or nothing.
- Choice: `extract ingest` exits with code 2 without `--brief`. `--no-brief` is the explicit
  opt-out.
- Decided by: agent default, not reviewed (`9d040cd`).
- Why: 833 of 845 records could not be traced to their instructions, which were deleted with a
  scratchpad, and one worker produced six records with no provenance (`9d040cd`).
- Limits: only 134 of 848 records carry a brief hash today (`REVIEW.md` §2). The sweep that
  would trace the rest was cut: it costs about 2.8 M tokens and "buys traceability, not the
  number" (`DESIGN_2026-09-17` §5).
- Verified: `tests/extract/test_extract_cli.py::test_ingest_refuses_a_record_with_no_brief`
  and `::test_ingest_accepts_an_explicit_absence_of_a_brief`.

**EX-05 · The measurand must be the plastic particle itself (S8). S21 and S23 mark its
boundaries.**
- Options for S8: counts, or does not count. S21 covers residual particles in a treated water.
  S23 asks whether the other material is adsorbed onto the plastic or free beside it.
- Decided by: Martin, 2026-09-15: "Ratified by Martin: **does not count**". For S21 the record
  quotes "Plastic of course." (`SESSION_2026-09-15_INDEPENDENCE_AND_SWEEP.md` §5).
- Why:
  - PMC13520016 filtered out its PET at 0.2 µm before every measurement, and its no-plastic
    control returned the same value, −34.0 to −27.4 mV (README; `9d040cd`).
  - That one paper had held read precision at 0.47. With S8 applied it is 0.81 (`93caeca`).
- Limits:
  - The four rulings moved 498 → 491 papers and 1 910 → 1 890 rows. No headline moved by more
    than 0.4 points (SESSION_2026-09-15 §5).
  - `review-measurand` lists candidate papers and never decides.
  - S22 is provisional.
- Built: `9d040cd`, `fc7960b`, `docs/briefs/extraction.md`, `src/mnp/extract/measurand.py`.
- Verified: the S8, S18, S21, S22 and S23 verdicts in `tests/edge/key.yaml`. A test pins the
  false-positive phrase "filtered prior to HPLC analysis" (`9d040cd`).

**EX-06 · An unrecognised unit refuses the row. The step guard reads only the piece of the
quote that carries the number.**
- Decided by: agent default, not reviewed. All three of the wave's fixes were
  mutation-verified (`550f8f9`).
- Why:
  - `normalise_unit → None` had been read as "no unit printed" and filled with the
    conventional unit, under a flag saying nothing was printed.
  - The step guard ran on the whole quote, so it punished fuller evidence. Five workers trimmed
    their quotes to get past it (`550f8f9`).
- Verified: `tests/extract/test_zeta.py::test_the_other_step_test_looks_at_the_clause_carrying_the_temperature`
  and `::test_an_incubation_temperature_in_its_own_clause_is_still_caught`.

**EX-07 · The value is checked against the cited line. A condition's scope stays the sentence
the worker quoted.**
- Options (Card 1): move every check to the cited line, move only the value and
  quote-existence checks, or change nothing.
- Decided by: Martin, 2026-09-18: "a condition's scope is the **sentence the worker quoted**"
  (`docs/GATE_LOG.md`, Card 1 outcome). Both gate reviewers had escalated.
- Why: the wide version (`b6b8976`, GATE_LOG):
  - dropped adversarial detection from 7 of 7 to 5 of 7;
  - grew each row's evidence 3.8× at the median;
  - let a unit-blind digit search match: "a ball mill's 10 mm diameter verifies 10 mM KNO3".
- Limits: exactly 1 row of 1 384 changed, and that change is a false clear: PMC11117817-r32
  (`f9249bb`).
- Verified: 7 of 7 on both paths. `tool/rules_impact.py` gives byte-identical output with and
  without the line document (GATE_LOG). Tests:
  `tests/extract/test_zeta.py::test_the_value_is_checked_against_the_cited_line_not_the_quote`.

**EX-08 · The extraction prompt and the agent files were brought in line with the ratified
brief.**
- Question: a prompt audit found two problems.
  - The API extraction prompt lagged behind the ratified brief.
  - The gate agents cited facts the repo contradicts (`d3d89c9`).
- Decided by: the audit was done in another session and applied in `d3d89c9`. Who approved it
  is not recorded in this repository.
- Limits:
  - The code's `prompt_sha256` no longer matches the hash the committed records were made with.
    `769b0a4` records the new hash; the records themselves are unchanged.
  - In the `d3d89c9` diff, `src/mnp/eval/cells.py` changes only the tool text of cells C and E
    and one docstring. So the prompts of cells B and D did not change.
- Verified: the `code_prompt_sha256` field in `data/processed/extraction_summary.json`, which
  `report reproduce` writes (`769b0a4`).

**EX-09 · Reading noise is measured, not assumed: 30 papers read twice, blind.**
- Question: is a difference between two extractions a property of the paper, or of the reading?
- Choice: a seeded sample of 30 papers the Methods fix did not touch (seed 20261002). Six
  workers read each paper twice, readings A and B, under the current brief. Ingest ran with
  `--dry-run` (PR-09), so nothing was recorded. `tool/reread_control.py` runs every reading
  through the dataset's own pipeline.
- Decided by: the agent, after the 208 re-extraction moved condition reporting *down* and
  nobody could say whether that was noise.
- Result (`data/interim/reread_control/summary.json`):
  - A against B, on rows matched by value: ionic strength, pH, temperature and fully
    conditioned agree 124/124, medium 114/124. The readings differ mostly on which rows exist
    (the same row count in 21 of 30 papers).
  - A against the recorded extraction: instrument 107/137, temperature 117/137. In 3 of the 30
    papers the recorded rows are values cited from other studies.
- Limits: four control agents stopped before reporting, so their last file may be a first pass.
  All 60 files passed a dry-run ingest.
- Built: `09c11cd`, `aa4ffa1`.

**EX-10 · Re-read the 239 papers with rows that were not read under the current brief.**
- Options: re-read the 239; re-read all 594 not read under the current brief (141 of the 355
  without rows print a zeta candidate); or give only the 26 papers a citation regex marks a
  second reading.
- Decided by: Martin, 2026-10-03, "Re-read the 239".
- Why: EX-09. The old readings differ from the current brief in a systematic way, so CP-07's
  premise that "re-reading the untouched papers adds nothing" was wrong. One brief for every
  record with rows is the strongest provenance statement.
- Limits: the 355 records without rows keep their old reading, so a measurement the old run
  missed stays missed. That is a recall limit, to be stated on the card.
- Built: run `reread-brief-20261003`, in progress, with each worker's JSON kept (EX-11).

**EX-11 · Each worker's raw JSON is kept with its run.**
- Why: the 208 re-extraction wrote its JSON to the session scratchpad, which a restart wiped. The
  records keep only the coerced result, so the raw reading (for example, the ionic-strength text
  as the worker typed it) is lost for those papers, and a coercer fix cannot be replayed onto
  them. From `reread-brief-20261003` on, the JSON sits in
  `data/interim/runs/<run>/json/<PMCID>.json`.
- Decided by: the agent.

## The five conditions and what counts as reported

**RC-01 · A zeta value is interpreted against five conditions: medium, ionic strength, pH,
temperature, instrument. "Fully conditioned" means all five on one row.**
- Options: these were raised only later, as questions for scientists (Czech list, F2):
  - adding size measured in the same medium, time since dispersion, and the sonication
    protocol;
  - dropping the instrument, if papers named the conversion model.
- Decided by: not recorded. `MeasurementConditions` already has these five flags at `1cfc5a5`.
- Why:
  - Each field has a reason, given in the per-condition table of `out/demo/METHOD.md` and in
    the schema.
  - The instrument stands in for the conversion model, which 93.2 % of zeta papers do not name
    (`docs/FINDINGS_comparability.md` R2; FINDINGS E2b).
  - Why these five and no others: **reason not recorded**.
- Limits: "that definition sets every percentage here" (`HANDOFF_2026-09-24.md` §7.6). Today
  61 of 1 890 rows (3.2 %) are fully conditioned (`REVIEW.md` C1).
- Verified: `tests/report/test_review.py::test_conditions_complete_is_the_and_of_the_five_flags_on_every_row`,
  and by hand in `REVIEW.md` §7 step 1.

**RC-02 · A printed salt composition counts as a reported ionic strength, flagged derived
(Q1).**
- Options: counts; does not count; counts but flagged derived (`docs/DECISIONS_NEEDED.md` Q1).
- Decided by: Martin, 2026-09-13. It counts "when the calculation follows directly from
  explicitly stated ionic species and concentrations".
- Why: the three judges split on it. 72 rows in 25 papers have PBS as the medium, and 63 of
  them recorded no ionic strength. The rule could move the headline by up to 5 points
  (DECISIONS_NEEDED Q1).
- Limits: `inferred_from_named_salt` does not record what it was derived from. 39 of 141 such
  rows cannot be re-derived by today's parser (FINDINGS E2d).
- Built: `coerce.parse_ionic_strength`, which raises the flag `derived_from_composition`. The
  code is already in `1cfc5a5`, a day after the ruling.
- Verified: `tests/edge/key.yaml` C1, plus a mutation-verified guard (DECISIONS_NEEDED, "What
  the answers changed").

**RC-03 · An incubation, exposure or culture temperature is not the measurement temperature,
even when the paper gives no other (Q2).**
- Options: not the measurement temperature; counts if no other is given; counts but flagged as
  an incubation step.
- Decided by: Martin, 2026-09-13 (DECISIONS_NEEDED Q2).
- Why: ε and η depend on the temperature of the measurement itself. Against the gold set,
  row-level temperature scored P 0.15 / R 0.23 before the rule (DECISIONS_NEEDED Q2) and
  precision 0.76 after it (`fc7960b`).
- Limits: extended by R2 and R2b (RC-08, RC-09).
- Built: `coerce.parse_temperature` and the `verify_row` flag `temperature_step_not_measurement`,
  both in `1cfc5a5`.
- Verified: `tests/edge/key.yaml` C2, plus mutation-verified guards.

**RC-04 · A condition holds only inside the experiment that states it (Q3).**
- Options: it applies to every measurement in the paper; only within its own experiment; it
  carries unless the paper describes a separate preparation; ambiguity is itself the answer.
- Decided by: Martin, 2026-09-13 (DECISIONS_NEEDED Q3).
- Why: 1 016 rows in 264 papers had quotes stitched from several places, more than Q1 and Q2
  together.
- Limits: S5 is still unanswered: does a condition stated in Methods reach a value printed in
  Results? Four workers raised it (SESSION_2026-09-15, "Needs Martin"; OD-17).
- Built: `verify_row` requires each condition in the row's own evidence (`pH_not_in_evidence`
  and its siblings), in `1cfc5a5`.
- Verified: `tests/edge/key.yaml` C5.

**RC-05 · Absence is a value and is never imputed.**
- Options: give a missing condition a default (DI water as 0 mM, 25 °C, pH 7), or record
  `*_reported = false`.
- Decided by: not recorded. It is a standing rule ("Never impute", `ideas.md` §13), attributed
  to no one.
- Why:
  - Imputation has already gone wrong once: a `normalise_unit → None` was filled with the
    conventional default (`ideas.md` §13).
  - Allowing defaults moves the comparable pairs from 16 to 81 624
    (`FINDINGS_comparability.md` §4c).
- Limits: no committed code recomputes the 81 624 (`REVIEW.md` §8 item 15).
- Verified:
  - `tests/eval/test_comparability.py::test_an_unreported_condition_never_acquires_a_default`
    and `::test_di_water_is_a_reported_medium_and_an_unreported_ionic_strength`.
  - Mutation A: 6 tests failed (`FINDINGS_comparability.md` §5).

**RC-06 · A named buffer's nominal composition is never looked up, and a conductivity is never
converted to an ionic strength.**
- Decided by:
  - The buffer rule: not recorded. It is already in the extraction brief and prompt at
    `1cfc5a5` ("never look up a nominal value").
  - The conductivity rule: agent default, first written down in `c3cbee4`.
  - No review by Martin is recorded for either. Both are put to the scientists as questions
    (the Czech list, G1).
- Why: otherwise "unreported" would stop meaning unreported (Czech list, G1, translated). A
  conversion "needs an assumed ionic composition the paper does not give" (`METHOD.md`,
  "Ionic-strength sources").
- Limits: this deliberately lowers the ionic-strength figure (`REVIEW.md` C3). Martin later
  allowed an estimate for environmental rows if it is highlighted (OS-02).
- Verified: case 02 in `METHOD.md` (PMC10141840 rows r1–r3).

**RC-07 · "Reported" is generous: a pH range, "room temperature" (flagged nominal) and an
instrument family all count. So every figure is an upper bound.**
- Decided by: not recorded. At `1cfc5a5`, `coerce.py` already treats "room temperature" as "a
  reported, nominal temperature". The agent wrote the rule down in `35d340e`. Martin's review
  is not recorded, and the choice is put to the scientists (Czech list, F2).
- Why: **reason not recorded**. `35d340e` states only the consequence: every figure is an upper
  bound.
- Limits: the same rows do not count as numeric for comparability (CM-02). Counts
  (`REVIEW.md` §4.3–4.5):
  - 123 rows report temperature only as a phrase;
  - 245 name only the Zetasizer family;
  - 40 report pH only as text.
- Verified: the spreadsheet rules in `REVIEW.md` §4.

**RC-08 · R1 and R2: an ionic strength of exactly 0 mM, and a temperature flagged as an
incubation step, become unreported. The row stays.**
- Options: remove the whole row, or keep the row and clear the value ("A").
- Decided by: Martin, 2026-09-28 (`4a3087c`). He first said "remove it" and "no whole row,
  since it doesn't have one of 5 main indentificators", then chose "A" *(session)*.
- Why:
  - "No added electrolyte" says nothing was added. It does not say the medium holds no ions,
    and absence is never imputed (`4a3087c`).
  - Before the rule, 0 mM gave an infinite Debye length, κa = 0 and f = 1.0 (`REVIEW.md` §8
    item 14).
  - Why the row is kept: Martin's aim is that the five identifiers be filled before resampling
    with the Koelmans formula *(session)*. No commit message records this reason. The commit
    gives a different one: the extraction record keeps what the model read, "so the rule can be
    revisited without re-reading a paper" (`4a3087c`).
- Limits: 14 rows in 3 papers. The comparability census and the harmonised totals do not move
  (`4a3087c`).

  | | before | after |
  |---|---|---|
  | ionic strength reported, per row | 14.2 % | 13.7 % |
  | ionic strength reported, per paper | 8.7 % | 8.6 % |
  | temperature reported, per row | 28.0 % | 27.8 % |
  | temperature reported, per paper | 20.9 % | 20.6 % |
- Built: `4a3087c` (`zeta.row_conditions`). `extractions.jsonl` keeps what the model read.
- Verified: `tests/extract/test_row_rules.py` (`test_zero_ionic_strength_is_unreported_and_flagged`,
  `test_the_record_keeps_what_the_model_read`). 25 questions were re-asked, and no sweep score
  moved.

**RC-09 · R2b: a temperature the row's own quote does not state is cleared when its only source
prints it for storage, incubation, exposure or culture.**
- Options: leave the rows; extend R2 with a regex; or extend R2 after reading every candidate
  row by hand. The handoff said "check each row by hand, not by regex"
  (`HANDOFF_2026-09-28.md` §7).
- Decided by: Martin, 2026-09-29: "okey then change it, if it is common and has also 37"
  *(session)*. `d538ce5` records it as "Martin, 2026-09-29, extending rule R2".
- Why: PMC8719689 labels its media "RPMI (stored at 37 C for 24 h)". 36 rows took that 37 as
  the measurement temperature, which the paper never states (`d538ce5`).
- Limits:
  - 212 candidate rows in 25 papers were read against their papers. 41 were cleared, 170 were
    kept, and 1 was unclear and kept. The record does not say who did the reading.
  - Effect (`d538ce5`):

    | | before | after |
    |---|---|---|
    | temperature reported, per row | 27.8 % | 25.6 % |
    | temperature reported, per paper | 20.6 % | 20.3 % |
    | fully conditioned, per row | 3.3 % | 3.2 % (62 → 61 rows) |
    | fully conditioned, per paper | 2.3 % | 2.1 % |

  - Stale flags: 162 rows carry flags computed once at ingest and never recomputed (OD-09).
- Built: `d538ce5`.
- Verified: `tests/extract/test_row_rules.py`
  (`test_a_storage_temperature_read_off_the_medium_label_is_cleared`,
  `test_room_temperature_at_zero_hours_is_kept`,
  `test_no_committed_temperature_sits_in_a_step_phrase_of_its_own_medium`).

**RC-10 · R3: a buffer's concentration taken as a reported ionic strength becomes unreported.
The row stays.**
- Question: "10 mM phosphate buffer pH 7.0" was stored as a reported ionic strength of 10 mM, in
  44 rows from 8 papers. Extraction worker w18 flagged the coercer path, and the main session
  confirmed it and measured it.
- Options: (a) unreported, strictly; (b) derive the value from the buffer's pKa and the printed
  pH, as an interval; (c) leave it as it is.
- Decided by: Martin, 2026-10-03: "Unreported, strict".
- Why: 10 mM phosphate at pH 7 holds about 18 mM of ions. The brief already says that a
  component whose speciation the paper does not print contributes nothing, and option (b) would
  look up a pKa, which RC-06 refuses.
- Limits: a paper that calls the number an ionic strength keeps it. PMC12598813 states "ionic
  strength 0.010 M (10 mM HEPES)", and the dataset records what is reported, right or wrong.
  The rule fires only when the stored value is printed within 40 characters of a buffer name in
  the same passage and no salt is bound to the number.
- Effect: reported ionic strength 265 → 221 rows (8.4 → 7.0 % per paper); fully conditioned
  57 → 47; comparable pairs **16 → 4**. Case 01 (PMC11099890) loses its pairs.
- Found on the way: `coerce` matched `IS` case-insensitively, so the English "is" counted as the
  abbreviation. It now matches only in capitals.
- Built: `6a93c69` (`zeta.row_conditions`, `coerce.buffer_concentration`).
- Verified: `tests/extract/test_zeta.py` (5 cleared, 6 kept, all real cases) and
  `tests/extract/test_coerce.py::test_the_word_is_is_not_the_abbreviation_IS`. All five guards
  were mutation-checked, and removing any one fails a test.

## Comparability

**CM-01 · Whether two rows can be compared is a deterministic predicate in code, asked as query
kind E.**
- Options: use the knowledge graph as a retrieval selector, or as a representation of relations
  between rows (`DESIGN_2026-09-17` §4b).
- Decided by: proposed by the agent (`ce49f01`). `HANDOFF_2026-09-24.md` §4 lists it as settled
  and names no decider.
- Why:
  - As a selector, the graph only tied BM25 once query leakage was closed (`2a96b3e`).
  - Comparability "is a predicate over a pair of records. No passage states it; it lives in the
    join" (`ce49f01`).
  - The answer key costs zero tokens (`0858865`).
- Limits: the rules are this project's own, and nobody outside it has ratified them
  (`REVIEW.md` §6).
- Built: `src/mnp/eval/comparability.py` (`0858865`).
- Verified:
  - The tests were written first and run against a stub: 38 failed, 14 passed
    (`FINDINGS_comparability.md` §5).
  - The full enumeration of 1 785 105 pairs agrees with the census: 16 comparable and 35
    conditionally comparable.

**CM-02 · The comparability rules and their tolerances.**
- The rules:
  - the same measurand;
  - the same instrument;
  - the particle's identity goes beyond the polymer name;
  - every condition is reported in both rows, and the conditions agree;
  - for zeta pairs, the same conversion regime.
- Options: none recorded beyond the chosen tolerances. The Czech list (E1–E3) puts them to the
  scientists.
- Choice: ionic strength within 10 % relative, pH ±0.2, temperature ±2 °C, Henry's f within
  5 %. The medium is matched by class first, then by text.
- Decided by: agent default, not reviewed (`REVIEW.md` C5, caveat).
- Why: `FINDINGS_comparability.md` §2 argues each number.
  - 10 % in I is 5 % in the Debye length.
  - pH is printed with one decimal.
  - η changes by about 2 % per °C.
  - 5 % is a tenth of f's range from 1.0 to 1.5.
  - On the medium: matching by class alone would merge two growth media whose ionic strengths
    differ 5× (PMC11726606), and matching by text alone would split "PBS" from
    "phosphate-buffered saline".
- Limits:
  - The 5 % Henry tolerance "is the least-defended constant here" (§7).
  - Dropping `medium_text_mismatch` raises 16 to 37 comparable pairs. Dropping the
    conversion-regime rule raises 16 to 29 (§2).
- Verified: `METHOD.md` reads the tolerances from the module's constants
  (`tests/demo/test_render.py::test_method_comparability_reads_tolerances_and_strata_from_constants`).

**CM-03 · The reported value is never evidence of comparability. The row type has no field for
it.**
- Decided by: agent default, not reviewed.
- Why: chemically distinct particles converge to similar zeta values after a corona forms,
  which is the abstract's own point. So "a similar value is not weak evidence of a similar
  particle, it is no evidence" (`FINDINGS_comparability.md` §2, R8).
- Verified: `test_the_row_carries_no_reported_value_at_all` and
  `test_similar_values_never_repair_a_blocked_pair`. Mutation B: 7 tests failed. The second test
  first survived its own mutation and was rewritten (`0858865`).

**CM-04 · A missing functionalisation is unreported, never bare. "Unaged" is a weathering
state, not a bare surface. Canonicalisers merge spellings only.**
- Decided by: the agent, for the first and third parts (`FINDINGS_comparability.md` R3,
  "canonicalisers"). Martin, for "unaged": "Martin's call" (`4003a11`).
- Why:
  - Carboxyl-, amine- and bare-surface polystyrene are different particles.
    `functionalisation_unreported` alone blocks 66.1 % of pairs.
  - "An unrecognised spelling costs a comparable pair; an over-eager merge invents one"
    (`FINDINGS_comparability.md` §2).
- Limits: after the "unaged" change, kind C's functionalisation questions draw from all six
  surface groups. The census stays 16 / 6 / 0 / 35 (`4003a11`).
- Verified: `test_an_unreported_functionalisation_is_not_a_bare_surface`,
  `test_unaged_is_a_weathering_state_not_a_bare_surface` and
  `test_a_surface_state_modifier_is_never_dropped_to_reach_a_match`.

**CM-05 · A third verdict, conditionally comparable: every blocker is a stated, quantified
difference on a condition.**
- Decided by: agent default, not reviewed.
- Why: it tells a titration apart from two rows that share nothing. 35 pairs fall here, 12 of
  them across papers. The category can be deleted without moving the 16
  (`FINDINGS_comparability.md`, headline and §7).
- Limits: `FINDINGS_comparability.md` §2 lists the conditions that count wrongly. The code is
  right (`REVIEW.md` §8 item 9).
- Verified: `test_a_stated_difference_in_one_condition_is_conditionally_comparable` and
  `test_an_unreported_condition_is_never_conditionally_comparable`.

**CM-06 · The kind E query set is the full census of positive pairs plus five seeded strata.**
- Decided by: agent default, not reviewed.
- Why: "a stratified sample of 1.78 M pairs with 16 positives would almost surely contain none"
  (`FINDINGS_comparability.md` §3). The set holds 320 pairs: 16 comparable, 35 conditionally
  comparable, 269 not comparable.
- Verified: `test_the_query_set_on_disk_is_what_the_generator_produces` and
  `test_the_query_set_ground_truth_is_reproducible_from_the_rows`.

## Harmonisation

**HM-01 · A correction with a missing input gives an interval, or no value at all. Never a
default.**
- Question: Martin asked on 2026-09-25 whether lab protocols could be harmonised
  "artificially — tested before it is implemented" (`docs/2026-09-25-rao-harmonization-notes.md`
  §2; that file is untracked, so a fresh clone does not have it). How do zeta values go on a
  common scale when the inputs the correction needs were never reported?
- Options: default the missing input, widen the result to an interval, or refuse.
- Decided by: proposed by the agent (`HANDOFF_2026-09-25.md` §4; "Never harmonise by filling a
  default", Rao notes §11). It is part of the demo design Martin agreed to on 2026-09-28
  (`DESIGN_2026-09-28_demo.md`).
- Why: filling a default moves the comparable pairs from 16 to 81 624
  (`HANDOFF_2026-09-25.md` §4).
- Limits:
  - Of the 1 890 rows, 64 get a point, 1 295 an interval and 531 nothing (`REVIEW.md` C8).
  - The release ships no harmonised values (`78a65ac`).
  - Testing the correction needs measurements of the same sample (`HANDOFF_2026-09-25.md`
    §4).
- Built: `src/mnp/demo/harmonise.py` (`220223d`).
- Verified: `tests/demo/test_harmonise.py::test_no_default_is_ever_used_for_missing_ionic_strength`
  and `::test_mobility_without_temperature_yields_no_value_and_says_why`.

**HM-02 · Which conversion model counts as named.**
- Choice:
  - One textbook limit named: its factor f is known.
  - Henry or Ohshima named: the paper's value stands.
  - Both textbook limits named: the model is unknown.
- Options: the original design treated any named model as known. It was revised after the
  harmonisation agent's first pass (`DESIGN_2026-09-28_demo.md`).
- Decided by: the parent session (agent), in review on 2026-09-28. Not Martin.
  `harmonise.py` first credited the rule to Martin, and `f78a4f5` corrected that.
- Why: papers usually write "Smoluchowski rather than Hückel", and a mention cannot say which
  model was applied (`DESIGN_2026-09-28_demo.md`).
- Limits: a mention is not proof that the model was applied, so every point is conditional
  (`METHOD.md`, limits).
- Verified: `test_both_textbook_limits_named_kappa_unknown_is_an_interval` and
  `test_henry_named_gives_a_point_equal_to_the_reported_value`.

**HM-03 · "Does not name a conversion model" is counted over papers that report a zeta
potential, not over all papers.**
- Options: all 851 readable papers (the first figure, 94.4 %), or the 485 papers that report a
  zeta.
- Decided by: the agent, correcting its own figure in `9ce15fa`.
- Why: "A paper reporting only an electrophoretic mobility needs no conversion and cannot be
  faulted for not naming one" (`9ce15fa`). The result is 452 of 485 papers, 93.2 %.
- Limits:
  - A mention scan is an upper bound.
  - The mobility group (6 of 13 name a model) is too small to give a ratio (FINDINGS E2b).
  - The superseded 5.6 % still appears in two places (`REVIEW.md` §8 item 11).
- Verified: `tests/demo/test_harmonise.py::test_scan_reproduces_findings_e2b`.

**HM-04 · The Debye length assumes a 1:1 electrolyte in water at 25 °C.**
- Decided by: agent default, not reviewed. The question is put to the scientists (Czech list,
  E3).
- Why: **reason not recorded** beyond the textbook formula κ⁻¹ = 0.304/√I nm
  (`FINDINGS_comparability.md` R7).
- Limits:
  - It underestimates κa for divalent media such as CaCl₂ or phosphate.
  - Czech question E3 assumes the Debye length only places a row in a regime. Since
    `harmonise.py`, it also corrects values (`REVIEW.md` §8 item 10).
- Verified: `test_debye_length_matches_the_textbook_one_to_one_electrolyte_value`.

## Resampling and statistics

**RS-01 · Per-paper figures are primary, with cluster-bootstrap intervals and the design effect
stated.**
- Options: per-row figures with naive binomial intervals (every earlier headline), or per-paper
  figures with a cluster bootstrap.
- Decided by: agent (`6e49bd6`). `HANDOFF_2026-09-24.md` §4 lists it as settled and names no
  decider. The Czech list (G2) asks the scientists whether the right unit is the paper or the
  lab.
- Why: rows cluster by paper (`docs/FINDINGS.md` E2e).
  - A median paper has 2 rows, the largest 90, and the top 10 % of papers hold 41.3 % of rows.
  - ICC is 0.78–0.94, and n_eff is 517–588, not 1 890.
  - Naive intervals are 2.1–4.1× too narrow. Today's rebuild gives 2.04–3.33× (`METHOD.md`).
- Limits:
  - A paper is not a lab, and "a property of the laboratory" is an interpretation
    (`REVIEW.md` C6).
  - The ionic-strength ICC is now 0.7688 against the printed 0.83 (`METHOD.md`).
- Built: `src/mnp/demo/resample.py` (`220223d`), with B = 10 000 and seed 20260921.
- Verified: `test_reproduces_published_e2e_table_on_the_table_it_was_measured_on`,
  `test_cluster_interval_wider_than_naive_for_every_metric`, and a hand recompute with
  `icc_worksheet.csv` (`REVIEW.md` §5.2).

**RS-02 · Resample paper indices. Never group by the cluster key after resampling.**
- Decided by: the agent, after running two implementations.
- Why: the two agreed on the point estimates but not on the per-paper intervals. The pandas
  version grouped by `pmcid` after resampling, which merges a paper drawn twice back into one
  and narrows the interval (`ff05351`).
- Verified: `tests/demo/test_resample.py::test_groupby_trap_is_narrower_than_correct_bootstrap`.

**RS-03 · Results that were published but never committed are rebuilt from scratch. A
difference is reported, never tuned away.**
- Decided by: agent rule ("do not tune until it matches", `DESIGN_2026-09-28_demo.md`).
- Why: E2e and E2b were cited but their code was never committed (`HANDOFF_2026-09-28.md` §2).
  A number nobody re-derives is the defect class this repo keeps finding (GATE_LOG).
- Limits: the rebuilds match except for the ionic-strength ICC, 0.8247 against 0.83, a rounding
  difference (HANDOFF §2). The 81 624 and the leave-one-rule-out table still have no committed
  code (`REVIEW.md` §8 item 15).
- Built: `220223d`.

## The reader grid (evaluation)

**GR-01 · Each tool is a hypothesis. Five cells on two axes test them, and the zero is no tool
at all.**
- Options: a ladder T0–T4 (first draft), or a grid of substrate × control
  (`DESIGN_2026-09-17` §1).
- Decided by:
  - The premise is Martin's reframe: "Whether any of them adds value is a measurement, not a
    premise" (`DESIGN_2026-09-17` §0, as the doc records it).
  - The agent proposed the grid.
- Why: "A naive one-shot RAG baseline is a strawman by the field's own 2026 standard" (§0).
  Each delta between two cells moves one variable (§1).
- Limits: only cells B and D exist (`grid.BUILDERS`; `REVIEW.md` §6).
- Built: `761349d`, `189d801`, `src/mnp/eval/{cells,grid}.py`.

**GR-02 · Cell A (the whole corpus in a long context) is cut.**
- Decided by: agent (`ce49f01`). `HANDOFF_2026-09-24.md` §4 lists it as settled and names no
  decider.
- Why: the corpus is 2.64× a 1 M-token window even in its cheapest form (FINDINGS E1b).
  Running the cell would cost about 2.4 M tokens, even cached (`DESIGN_2026-09-17` §5).
- Limits: whether retrieval beats simply reading all 50 gold papers is still unmeasured
  (FINDINGS, "Open questions").

**GR-03 · Cell B is BM25 over the line-addressed text.**
- Options: section-aware chunks with an embedding model and a reranker (`PLAN_2026-09-28.md`
  §4.1); BM25; the structured selector.
- Decided by: the agent, from E6 (`2a96b3e`). `HANDOFF_2026-09-24.md` §4 lists it as settled.
- Why:
  - The structured selector beat BM25 on a leaky query and tied on an honest one.
  - BM25 recall at 10 falls from 0.86 to 0.52 when the query does not leak the answer.
  - BM25 is "thirty lines and couples to no schema" (`2a96b3e`).
- Limits: simpler than the baseline PLAN §4.1 specified, and below the design's own cut line,
  which keeps a plain hybrid (OD-14).
- Verified: `tests/eval/test_cells.py::test_the_corpus_index_reproduces_the_tuned_bm25_ranking_exactly`
  and `::test_cell_b_does_not_top_up_with_the_lines_the_records_were_read_from`.

**GR-04 · Five query kinds, A to E. Kind D is there so that prose retrieval can win.**
- Decided by: agent (`DESIGN_2026-09-17` §3, §4b; `761349d`).
- Why: kind D exists "so the result is not rigged" (§3). Its key is every line in the corpus
  that states the mechanism (`761349d`).
- Limits: kind A's key comes from the gold set, which a model annotated (`REVIEW.md` C9).
- Verified: `tests/eval/test_query_sets.py::test_kind_b_is_not_all_absences_or_always_saying_no_would_score_full_marks`
  and `::test_kind_d_acceptable_evidence_spans_papers_so_one_passage_is_not_the_only_right_answer`.

**GR-05 · The reader is Sonnet, pinned by its full id `claude-sonnet-5`. A reply from any other
model is refused.**
- Options: Martin was offered several models. The pin could be the alias or the full id.
- Decided by: Martin chose "Sonnet (Recommended)" *(session)*. The agent added the pin
  (`189d801`).
- Why:
  - For the pin: on CLI 2.1.92 the alias `sonnet` resolved to claude-sonnet-4-6. With an alias,
    the reader could change between cells run days apart (`189d801`; `HANDOFF_2026-09-28.md`
    §5).
  - Why Sonnet and not another model: **reason not recorded**.
- Verified: `tests/eval/test_grid.py::test_the_reader_is_pinned_by_full_model_id_not_an_alias`
  and `::test_a_reply_from_any_other_model_is_refused`.

**GR-06 · The reader sees the prompt and nothing else.**
- How: it runs with tools off, no settings, strict MCP config and its own system prompt, in a
  temporary directory with no CLAUDE.md above it.
- Decided by: agent default, not reviewed.
- Why: "this repository's instruction files name the headline numbers" (`189d801`).
- Verified: `test_the_reader_has_no_tools_no_settings_and_no_mcp` and
  `test_the_reader_runs_where_no_instruction_file_can_be_discovered`, each mutation-checked
  (`189d801`).

**GR-07 · The denominator is the plan. A reader failure is retried, never scored. An answer
that cannot be parsed counts as wrong.**
- Decided by: agent default, not reviewed.
- Why: `asked.txt` is written before any reading, "so the denominator is the plan, not
  whichever answers came back" (`189d801`).
- Verified: `test_a_reader_failure_is_retried_later_not_scored_as_the_cells_mistake`,
  `test_the_score_names_questions_asked_but_never_answered` and
  `test_an_unparseable_answer_is_never_scored_correct`.

**GR-08 · Ten questions per cell are piloted before any sweep, and what the pilot finds is
fixed.**
- What the first cell D pilot found (`4003a11`):
  - kind E scored answer codes, while its question asked for field names;
  - 15 of 30 kind A questions matched a second gold value in the same paper;
  - kind C asked its questions in internal code words.
- Decided by: the pilot rule is the agent's (`DESIGN_2026-09-17` §3). Martin approved the fixes
  *(session)*, and `4003a11` records "unaged" as his call.
- Why: "A cell that is broken on question three should not be discovered on question eighty"
  (§3).
- Limits: two kind A questions still give away part of their answer (OD-08).
- Verified: the second pilot scored 10 of 10 (`e00e85c`).
  `test_kind_e_blockers_are_fields_not_the_keys_finer_codes` and
  `test_kind_a_names_the_particle_in_the_question_when_it_targets_one`.

**GR-09 · A usage-policy refusal is the cell's answer. It is scored wrong and never asked
again.**
- Options: count it wrong in every cell (the agent's recommendation), or drop the question
  (`HANDOFF_2026-09-28.md` §4 as committed in `3a477d3`).
- Decided by: Martin, 2026-09-28: "refuse it" (`3fa1da1`).
- Why: question D-008 was refused three times on ordinary colloid text. Treated as a timeout,
  it was retried on every resume, so a run could never complete (`3fa1da1`).
- Limits: cell D's kind D score reads 9 of 10.
- Verified: `test_a_refusal_is_the_cells_answer_and_is_scored_wrong` and
  `test_a_refusal_logged_as_a_failure_earlier_is_recorded_without_asking_again`.

**GR-10 · A citation written inside the answer text counts, if it is a full address.**
- Options: score only the `citations` field, or also read citations written in the answer
  (`3a477d3` handoff, §4.2).
- Decided by: Martin: "citation inside text are normal" *(session)*. Built in `7ba7d35`.
- Why: answers D-001 and D-007 wrote "(PMC10830523:L132)" in the text, left the field empty,
  and were scored ungrounded (`7ba7d35`).
- Limits: a bare "L3" is not a citation. Cell D's kind D score went from 7 of 9 to 9 of 9
  grounded.
- Verified: `test_a_citation_written_inside_the_answer_text_counts`, and
  `test_an_unqualified_line_number_in_prose_is_not_a_citation`, whose mutant turned red.

**GR-11 · Kind E is reported as recall per true verdict and as balanced accuracy, not as
accuracy alone.**
- Decided by: agent default, not reviewed (`e1b4624`).
- Why: cell B answered "not comparable" to 319 of 320 pairs and scored an accuracy of 0.838,
  which is exactly the share of "not comparable" in the key (`e1b4624`).
- Result: balanced accuracy 1.000 for cell D and 0.332 for cell B (`REVIEW.md` C9).
- Verified: `test_kind_e_reports_recall_per_true_verdict_so_always_no_cannot_hide`.

**GR-12 · Cell B is run in full: all 400 questions, including all 320 kind E pairs.**
- Options: kinds A–D only (about 0.6 M tokens), or all 320 kind E pairs as well (about 5.6 M)
  (`3a477d3` handoff, §4.3).
- Decided by: Martin: "okey go", "don't care about token" *(session)*.
- Why: cell D is handed the rows, so its score only means something next to cell B's
  (`e00e85c`; `HANDOFF_2026-09-28.md` §6).
- Result, correct answers per kind, cell D against cell B (`REVIEW.md` C9):

  | kind | cell D | cell B |
  |---|---|---|
  | A | 30/30 | 22/30 |
  | B | 30/30 | 27/30 |
  | C | 9/10 | 1/10 |
  | D | 9/10 | 7/10 |
  | E | 320/320 | 268/320 |
- Limits:
  - Cell D's kind E prompt contains the computed verdict, so its score is transcription, not
    judgement (`d3d89c9`; `REVIEW.md` C9).
  - One reader, one run per cell.
- Built: `e1b4624`.

**GR-13 · After R2b the kind E set was redrawn, and Martin accepted the new set.**
- Decided by: Martin: "yes accept new set and commit your changes" *(session)*. `d538ce5`
  records "Martin accepted the new set".
- Why: one fully conditioned row left the pool (`d538ce5`).
- Result: 86 questions were asked again and the old answers kept in `superseded.jsonl`. No score
  moved, and cell B still finds 0 of the 51 comparable pairs (`d538ce5`).

**GR-14 · Cell C (an agent searching the papers, with the knowledge base withheld) is never
cut.**
- Decided by: agent (`DESIGN_2026-09-17` §5; `HANDOFF_2026-09-24.md` §6). Martin's acceptance
  is not recorded.
- Why: it is "the strongest rival to the entire thesis". If cell C matches cell E, the
  knowledge base earns nothing (§5, §6).
- Status: not run. Its corrected cost is about 3.8 M tokens (`HANDOFF_2026-09-28.md` §5).
  See OD-15.

## The demo

**DM-01 · The demo: thirteen real papers, one per failure mode, each re-sampled four ways, plus
a METHOD file.**
- Martin's request *(session)*: "demo should show different cases that were identified across
  pappers so it should show diverzification on at least 10 cases where the dataset shows how it
  would re-sampled so review would see how results are resampled on real … Plus also it should
  provide measurement protocol with detailed explanation in file."
- Options he chose from *(session)*: all four resampling facets; a "How the PoC measures"
  file; scientists as the audience; English; generated Markdown; one case per failure mode.
- Decided by: proposed by the agent, chosen by Martin on 2026-09-28
  (`DESIGN_2026-09-28_demo.md`: "Agreed with Martin the same day").
- Built: `220223d` (the parts) and `d35f82d` (the render, `METHOD.md` and the reader runs), in
  `out/demo/`.
- Verified: `report reproduce` rebuilds `out/demo/` byte for byte.
  `tests/demo/test_render.py::test_rendering_twice_is_byte_identical` and
  `::test_every_case_page_has_all_seven_sections`.

**DM-02 · Each case pins a paper and a check that proves the paper still shows its failure
mode.**
- Decided by: agent (`DESIGN_2026-09-28_demo.md`).
- Why: it caught a bad pin immediately. Case 03's paper failed its own check, because
  PMC13181784 prints no conductivity, so it was replaced by PMC12673110 (`220223d`).
- Verified: `test_every_pinned_case_passes_its_own_check`,
  `test_verify_can_say_no_not_only_yes` and
  `test_no_case_why_claims_uniqueness_unless_only_one_paper_qualifies`.

**DM-03 · Demo answers are read from committed run directories and never regenerated.**
- Decided by: agent (`DESIGN_2026-09-28_demo.md`, "Output").
- Why: it keeps the demo deterministic and inside `report reproduce`.
- Limits: 36 questions per cell. Cell D is handed the rows, so this is an illustration, not an
  estimate. Cell B took case 07's incubation temperatures as the measurement temperature, which
  is exactly that case's failure mode (`d35f82d`).
- Verified: `test_missing_run_directory_renders_not_run`.

**DM-04 · No demo lookup rests on a value that a rule cleared.**
- Decided by: agent (`4a3087c`).
- Why: question X12-A quoted the paper's "ionic strength 0 mM" in its own text. The reader
  repeated it and was scored as fabricating. X12-A now asks about a 1 mM row, and both cells
  answer it correctly (`4a3087c`).
- Verified: `tests/demo/test_questions.py::test_no_lookup_is_built_on_a_value_a_rule_cleared`.

## Review outputs and the results page

**RV-01 · A generated review guide with worksheets, so every number can be checked by hand.**
- Martin's request *(session)*: "i need to know every detail about dataset. What it proof or
  not … where are these 5 main parameters? Write it down into file so i could also check it
  manually from table and do deep review."
- Choice: `report review` writes `out/review/REVIEW.md` and five worksheets. Every formula is
  worked on real rows, claims C1–C11 each say how to check them, and a 20-row audit sample is
  included.
- Decided by: Martin asked; the agent chose the form.
- Limits: building the guide found defects (`78a65ac`).
  - `f78a4f5` and `4a3087c` fixed some of them.
  - The rest are listed in `REVIEW.md` §8.
- Built: `78a65ac`, `src/mnp/report/{review,review_guide}.py`.
- Verified: `report reproduce` rebuilds it byte for byte.
  `tests/report/test_review.py::test_icc_recomputed_from_the_worksheet_alone_matches` and
  `::test_the_key_numbers_are_the_modules_own`.

**RV-02 · An HTML results page for an engineer, with its builder kept in the repo.**
- Martin *(session)*: "CSV is bad", "no excel rather html with excel", "need some graphical
  visualization of the output as engineer".
- Choice:
  - One HTML page, built from a given commit with `git show` and computed with the repo's own
    functions.
  - It checks 105 numbers against `REVIEW.md` and fails loudly on any mismatch.
- Decided by: Martin asked; the agent chose the form.
- Why the builder lives in the repo: the template and the script sat in the session scratchpad
  and were wiped by a restart. They were recovered from the published page and the transcript
  (`0056e12`).
- Limits:
  - The hand-check worksheets are still CSV. The record does not say whether Martin accepted
    that.
  - The page itself is gitignored and published privately (`HANDOFF_2026-09-28.md` §7).
- Verified: `tool/viz/test_reference.py::test_build_data_reproduces_the_reference` rebuilds
  commit `4a3087c` exactly. A z of 1.95996 instead of 1.96 turns it red (`0056e12`).

**RV-03 · Every reader-facing document opens with the same generated scope block.**
- Decided by: Martin, 2026-09-30: "let's reveal such truth in the beggining so the scope would
  be clear" *(session)*. `0f3d549` records "say at the top what they are".
- Choice: `src/mnp/report/scope.py` renders the block from the committed tables for:
  - `REVIEW.md`;
  - the dataset card;
  - the demo README and `METHOD.md`;
  - the results page.
- Why: "so no number in it is typed and the documents cannot drift apart" (`0f3d549`).
- Verified: `tests/report/test_scope.py::test_the_shipped_documents_carry_the_same_block_word_for_word`
  and `::test_the_block_moves_with_the_stats`.

**RV-04 · A check a Claude agent did is called that. Nothing claims a human check that did not
happen.**
- What was wrong: `REVIEW.md` said "the person's verdict", the card said "a gold set of
  hand-checked rows", and the scope block said "Hand-checked". Claude agents did the origin
  check, the R2b read and the gold set. No row has been checked by a person (OD-03).
- Decided by: Martin's own standard (ideas.md R6): a dataset others must validate cannot rest
  on an unstated or false check.
- Choice: "second reading" by a Claude agent, and "agent-checked". The word "hand" is kept for
  the human audit still to come. The column and key names changed too (`hand_checked` →
  `agent_checked`).
- Built: `32fc0d3`. Verified: `tests/report/test_no_claimed_human_check.py`, red before the
  change.

## Licence and release

**LR-01 · Version 0 ships as parquet, JSONL, a JSON Schema and a dataset card that computes its
own numbers.**
- Decided by: Martin set the date: "A vanilla dataset v0 ships by 28.9 regardless" (`ideas.md`
  §3). The agent chose the form (`PLAN_2026-09-28.md` §5 item 1).
- Why: the card refuses to build when its statistics and the table disagree, because "three
  published tables in this repo once stopped following from their data" (`f29fe71`).
- Limits: two gaps in the columns (`HANDOFF_2026-09-25.md` §3; OD-19).
  - No column says whether the paper named its conversion model.
  - The `model` column holds the extraction LLM, which a scientist will read as Smoluchowski or
    Hückel.
- Built: `f29fe71`, `src/mnp/report/release.py`.
- Verified: `test_a_stats_file_that_does_not_describe_this_table_is_refused`,
  `test_running_the_release_twice_is_byte_identical` and
  `test_the_shipped_card_matches_the_committed_stats`.

**LR-02 · The release is licensed CC BY 4.0. Quotes ship only from CC BY and CC0 sources; the
rest are withheld and can be restored locally.**
- Options: the record holds only "option A" (`HANDOFF_2026-09-28.md` §4). The other options
  Martin was shown are not in the repo.
- Decided by: Martin, 2026-09-28: "A" (`61aa0a7`: "Martin's decision"). The repository is
  private (`REVIEW.md` §1).
- Why:
  - Values, conditions and absence flags are facts. A quote is the source's own text.
  - CC BY and CC0 "already permit redistribution with attribution" (`DATASET_CARD.md`,
    Licence).
  - CC BY is "the default expectation for a citable scientific dataset" (PLAN §8.3).
- Result (`61aa0a7`):
  - 1 437 rows ship their quote.
  - 453 rows from 136 papers keep an address and a sha256 instead.
  - `report rehydrate` restores all 453 byte for byte.
  - An independent check found none of 349 withheld passages in any release file.
- Limits: "a licensing decision, not legal advice" (card). The repo itself holds text that is
  not CC BY (OD-20).
- Verified: `tests/corpus/test_licence.py::test_only_cc_by_and_cc0_allow_a_quote`,
  `tests/report/test_quotes.py::test_rehydrate_restores_every_withheld_quote_exactly` and
  `::test_no_withheld_quote_text_appears_in_any_release_file`.

**LR-03 · The licence is read from each article's own JATS permissions. An unclear grant means
the quote is withheld.**
- Decided by: agent default, not reviewed (`61aa0a7`).
- Why: the previous card read the licence from `articles.parquet`, which is gitignored, so a
  fresh clone could not rebuild the decision. Where a URL and its wording disagree, "an unclear
  grant is not a grant" (`61aa0a7`).
- Limits: EHP's "public domain unless otherwise noted" (4 papers) is withheld as uncertain
  (OD-10).
- Verified: `test_the_classifier_reads_nothing_gitignored` and
  `test_a_url_that_contradicts_its_own_wording_is_not_trusted`.

**LR-04 · The dataset's author is Martin Durak.**
- Decided by: Martin, 2026-09-30 (`b408c51`).
- Built: `release.AUTHOR`, `out/release/LICENSE` and the card.
- Verified: `tests/report/test_release.py::test_the_licence_names_its_author`.

## Sample origin and scope

**OS-01 · Where the measured particles came from was confirmed before it was documented.**
- Martin *(session)*: "Oh i see, so even in pappers scientists using synthetic samples not real
  one form environment … Try to confirm it before moving forward." `d4be112` records that he
  "wanted it confirmed before it is documented".
- Options: document the impression as it stood, or confirm it by reading every paper.
- Decided by: Martin required the confirmation. The agent chose the method.
- How (`d4be112`):
  - The isolated `claude-sonnet-5` reader read all 491 papers and classified each particle,
    citing a line for each.
  - Classes: bought, made in a lab, collected from an environment, unclear. The liquid is not
    the origin (`REVIEW.md` C11).
  - Cost: 589 calls, 2.85 M input tokens, $24.
- Result (`REVIEW.md` C11):
  - 94.4 % of rows are synthetic: 68.3 % bought, 26.1 % made in a lab.
  - 1.0 % are environmental: 19 rows in 4 papers, 18 of them wastewater effluent.
  - 0 rows from air, freshwater, seawater, soil or sediment.
- Limits:
  - Hand-check agreement: environmental 18/20, unclear 30/40, random sample 37/40 (40/40 on
    synthetic against environmental).
  - The record does not say who did the hand check. `hand_check-origin-20260929b.jsonl` has no
    field for the checker, yet `REVIEW.md` calls it "the person's verdict" (OD-22).
- Built: `d4be112`; `report origin` rebuilds it (`0dfc047`).
- Verified: `tests/report/test_origin_report.py::test_hand_verdicts_override_the_readers_origin_for_those_rows_only`
  and `::test_agreement_is_counted_per_stratum_and_on_the_synthetic_split`. `report reproduce`
  guards the origin tables.

**OS-02 · The environmental rows' missing ionic strength is highlighted. An estimate from
conductivity would be marked as estimated, but none is possible.**
- Martin *(session)*: "If real particles missing ionic streng than it can be mapped in different
  way but it needs to be highlighted and know."
- Choice: a highlighted statement in `REVIEW.md` C11 and on the card (`0dfc047`).
  - 0 of the 19 environmental rows report an ionic strength.
  - An estimate (Griffin and Jurinak: I in mM ≈ 0.013 × conductivity in µS/cm) would have to be
    marked as estimated.
  - No conductivity reaches any of the 19 rows, so none is made.
- Decided by: Martin.
- Limits: PMC11211448 L26 prints a conductivity and an average zeta for a diluted wastewater.
  That measurement is not a row of the table (OD-02).
- Verified: `tests/report/test_review.py::test_the_environmental_rows_ionic_strength_is_stated_as_not_estimable`.

**OS-03 · The corpus stays at 491 papers, and its scope is stated at the top of every
document.**
- Decided by: Martin, 2026-09-30: "okey let's stay with what we have and don't increase corpus
  for now, but make notes about it" *(session)*. `0f3d549` records "stay with the 491 papers".
- Options: enlarge through OpenAlex discovery, Unpaywall PDFs or publisher text mining, or stay
  (`docs/2026-09-30-corpus-scope-notes.md`, "What is reachable").
- Why: **reason not recorded** for not enlarging now. The notes record what each gap may cost
  and the cheapest test for it.
- Limits: "Part of the 94.4 % is a property of the measurement, not of the sampling" (notes):
  a zeta potential needs a stable dispersion, which bought beads give and environmental samples
  rarely do.
- Verified: `tests/report/test_scope.py::test_the_corpus_notes_exist_and_name_the_query`.

**OS-04 · Telling airborne plastic apart by its charge is recorded as an open direction, not
as an extension of this dataset.**
- Decided by: Martin raised it on 2026-09-30 (`7a0b858`).
- Why it is not an extension: a zeta potential exists only in a liquid. An airborne charge is a
  different measurand, and the sizer's charger sets it (corpus-scope notes, "Open direction").
- Status: open. The cheapest test is recorded in the notes.

## Process

**PR-01 · Deterministic work comes first and is free. Model tokens are spent only where a model
must actually read.**
- Decided by: agent (`DESIGN_2026-09-17` §5, "organising rule"). Martin's real token budget was
  asked for and never recorded (§7 item 1).
- Why: 858 XMLs and 845 records rebuild in 21 s for zero tokens, while one 80-paper extraction
  wave cost 1.4 M (§5).

**PR-02 · `report reproduce` rebuilds every committed artefact offline, refuses the network,
and diffs against HEAD.**
- Decided by: agent default, not reviewed (`11c0d7d`).
- Why: its first run found three published tables that no longer followed from the data, and
  91 stale records (`11c0d7d`).
- Limits:
  - It reproduces from the stored model output, not through the reading (`ideas.md` §5).
  - A fresh clone with no network fails on E1, because of tiktoken (OD-11).
  - `uv.lock` is gitignored (OD-05).
- Verified: `tests/report/test_reproduce.py::test_network_is_refused_not_merely_unused`.

**PR-03 · `docs/PROTOCOL.md` is generated from a registry that the tests hold against the
command line.**
- Decided by: agent (`20e7d4c`).
- Why: "A methodology written by hand describes the pipeline as it was the last time someone
  remembered to edit it" (`20e7d4c`).
- Verified: `tests/test_protocol.py::test_every_command_the_code_offers_has_a_protocol_step`
  and `::test_the_committed_document_is_current`.

**PR-04 · Workers claim papers from a leased queue, and ingest is idempotent per paper.**
- Decided by: agent (METHODOLOGY §5.1; `docs/ARCHITECTURE_PLAN.md` §3).
- Why: the first run went wrong in several ways (METHODOLOGY §4.1–4.6; `ideas.md` §6.5):
  - workers delegated their work instead of doing it;
  - two workers overwrote each other's `/tmp` files;
  - work lists drifted, so two workers read the same papers;
  - ten workers died to a rate limit at once.
- Built: `src/mnp/queue.py`, in `1cfc5a5`. `11c0d7d` gave it its own `MNP_DB_URL`, after a test
  run reached the live application database.
- Verified: `tests/test_queue.py::test_two_workers_never_receive_the_same_paper` and
  `::test_an_expired_lease_returns_the_work_and_counts_the_attempt`. These skip without
  `MNP_DB_URL`.

**PR-05 · Gate reviewers read a card before any token-spending step. They answer ALLOW or
ESCALATE, never REJECT, and Martin picks the branch.**
- Options: let the gates refuse; take a majority vote; or ALLOW/ESCALATE.
- Decided by: the agent, "on the repo's own κ evidence. Reversible in one line if Martin wants"
  (`DESIGN_2026-09-17` §4, §7 item 6). No reversal is recorded.
- Why: the judge panel found the disagreement in 17 of 17 cases and decided at κ = −0.05
  (`docs/DECISIONS_NEEDED.md`).
- Limits: `docs/GATE_LOG.md` holds only Cards 1 and 2. The cell sweeps and the origin run spent
  tokens with no card (OD-21).
- Built: `7f7ba5b`, `.claude/agents/mnp-gate-{engineer,scientist}.md`.

**PR-06 · An LLM judge panel routes rule disputes to Martin and never decides them. A
majority-of-three vote was not relied on.**
- Decided by: Martin: "Martin refused to rely on it" (`ideas.md` §6.5).
- Why: each judge got a whole rule wrong, a different rule each time. The majority was 2–1 on
  every rule, with only 4–6 cases per rule (`DECISIONS_NEEDED.md`, "The judges, scored").
- Built: `mnp.report.judge` and the judge worklists, in `1cfc5a5`.
- Verified: `tests/report/test_judge.py`.

**PR-07 · A test counts only once it has been seen to fail.**
- How: write the test first, or mutate the fix back and watch the test turn red.
- Decided by: agent rule (`DESIGN_2026-09-28_demo.md`, "Rules for every agent").
- Why: tests kept passing for the wrong reason.
  - Three guards were rewritten after a mutation came back green (METHODOLOGY §6).
  - A comparability test survived its own mutation (`0858865`).
  - Two render tests passed after their content was renamed (`d35f82d`).

**PR-08 · Corrections stay in place, and a wrong conclusion is recorded rather than deleted.**
- Decided by: agent (the `docs/FINDINGS.md` header).
- Why: "the process matters more than the tidy version" (FINDINGS E2d, `1fedb71`).

---

**PR-09 · `ingest --dry-run` verifies a reading and prints the usual feedback, but records
nothing.**
- Why: the re-read control (EX-09) needed workers to see exactly what a real worker sees, without
  touching the dataset.
- Built: `0e739d4`. Verified: `tests/extract/test_extract_cli.py`, red before the change.

## Agent actions and how they were checked

**What was delegated.** Agents did the following work, according to the record:

- **Extraction, 2026-09-12/13**: about 114 worker agents (`docs/METHODOLOGY.md` §2). They did
  prompt development, the gold set (5 workers × 10 papers, `mnp-gold-annotator`), re-annotation,
  the corpus sweep (about 65 workers), the papers that print no value (about 37) and repairs.
- **The judge panel**: two blinded Claude judges and one external model judged 17 disputes
  (`docs/DECISIONS_NEEDED.md`).
- **The re-read under a recorded brief**, 2026-09-14/15: a pilot with 2 workers, a slice with
  4, and wave 1 with 8 workers on 10 papers each (`fc7960b`, `550f8f9`).
- **Gate reviews**: `mnp-gate-engineer` and `mnp-gate-scientist` on Cards 1 and 2
  (`docs/GATE_LOG.md`).
- **The demo modules**: agent A (`resample`), agent B (`harmonise`), agent C (`cases`, `walk`,
  `questions`) and agent D (render and reader runs) (`DESIGN_2026-09-28_demo.md`).
- **The 2026-09-28 prompt audit**, done in another session (`d3d89c9`).
- **This register**, written by a subagent on 2026-10-01. The main session checked it and
  committed it (`b3280cd`), and keeps it current.
- **The Methods fix and its impact measurement** (`9b17a6c`), **the re-extraction** (18 workers,
  `5012fdf`), **the re-read control** (6 workers, `09c11cd`), **the wording fix** (`32fc0d3`) and
  **the re-read of the 239** (20 workers, in progress).

The cell readers and the origin reader are not subagents. They are isolated `claude -p` calls
(GR-06, OS-01).

**Subagents never commit.**

- The demo agents were told "Don't commit. The parent session commits"
  (`DESIGN_2026-09-28_demo.md`).
- Extraction workers write only through `extract ingest`, which coerces, verifies and stores
  (METHODOLOGY §2).
- The gate agents have Bash and Read only, and never edit (`DESIGN_2026-09-17` §4).
- The main session commits only when Martin asks for it (`HANDOFF_2026-09-25.md` §0).

**A subagent's report is a claim, not evidence.**

- "Verify against `extractions.jsonl`, never a worker's own prose. Three workers reported
  success having written nothing" (`ideas.md` §13).
- "Verify a reviewer's claim before acting on it, and verify it anyway when it is right"
  (GATE_LOG, Card 2).
- "'working tree clean' is a claim, so run `git status --short`" (`HANDOFF_2026-09-25.md` §0).

**Defects caught in agent output.** All eight below are confirmed in the commit history.

| Defect | What the record says | Commit | Guard now |
|---|---|---|---|
| METHOD.md stated the wrong three rules | "the three rules were the walk's verdicts instead of the ratified ones" | `d35f82d` | `test_method_states_the_ratified_three_rules_not_the_verdict_vocabulary` |
| A false "four strata" | "'four strata' was typed where there are five" | `d35f82d` | `test_method_comparability_reads_tolerances_and_strata_from_constants` |
| A rule credited to Martin | "a rule was attributed to Martin who never saw it"; "harmonise.py credited Martin with the both-limits rule; the parent session made it in review" | `d35f82d`, `f78a4f5` | `test_method_deletes_the_false_martin_review_claim` |
| Case 01 claimed to be unique | "case 01 claimed to be the only fully conditioned paper when ten have more than one such row" | `d35f82d` | `test_no_case_why_claims_uniqueness_unless_only_one_paper_qualifies` |
| Weak tests | "Two of the new render tests passed when their content was renamed … both were mutation-checked"; a comparability test survived its own mutation | `d35f82d`, `0858865` | the rewritten tests |
| `key_not_comparable=1.00` on case pages | the answer key leaked onto every case page; "The demo was not re-rendered after that commit, which is how it went unnoticed" | `f78a4f5` | `test_a_score_line_never_shows_the_answer_key` |
| X12-A quoted "ionic strength 0 mM" from a rule-cleared row | "the reader repeated it and was scored a fabrication" | `4a3087c` | `test_no_lookup_is_built_on_a_value_a_rule_cleared` |
| Kind E stored codes, but the question asked for fields | "Kind E scored blockers on the key's codes while the question and the contract ask for fields" | `4003a11` | `test_kind_e_blockers_are_fields_not_the_keys_finer_codes` |

What the first defect's fix left behind: `METHOD.md` now calls its "three extra rules"
(scope, absence never imputed, every figure an upper bound) "ratified before this demo". It
also calls its per-condition table "the ratified rules". Only the scope rule (RC-04) and the Q1
and Q2 rows of the table (RC-02, RC-03) have a ratification record. The others are RC-05,
RC-06 and RC-07, whose deciders are not recorded (OD-24).

The record holds more defects of the same kind:

- **Workers.** Three workers delegated their work, and batch 025 processed none of its ten
  papers. This was "caught by checking the data, not by reading the report" (METHODOLOGY
  §4.1). Five workers trimmed their quotes to get past a guard (`550f8f9`).
- **Gate cards.** Cards 1 and 2 both named a function's callers from memory and missed some.
  In Card 1 the missed caller was the very measurement the card's failure condition depended on
  (GATE_LOG). A gate called four rows "worker-computed"
  when the paper prints the value; checking that claim found a paper contradicting itself
  (`15efc8a`).
- **The main session.** It declared 14 rows "imputed" from one summary column, and both
  examples were legitimate (`1fedb71`). A commit titled "model-free scorer" did not contain the
  scorer, and the handoff called the tree clean from memory (`b1f4f7e`).
- **Analysis.** The shared-citation investigator's first pass matched "1.5" inside
  "−56.3 ± 1.5" (`fe51a4b`). A pandas bootstrap grouped by `pmcid` after resampling
  (`ff05351`).
- **The re-extraction, 2026-10-01/02.** The main session read every worker report and sent three
  papers back (`5012fdf`):
  - PMC13298883 carried an n the paper never states;
  - PMC8168913 recorded DLVO model inputs as measurements, and on the first correction dropped
    a measurement the paper says it made but does not print, which the brief calls the most
    important case;
  - PMC9643204's medium and temperature were checked against L32, and they stood.

  One worker found its shared scratch file overwritten by another and re-read the paper; from
  then on each worker wrote only to its own paths.
- **The main session, 2026-10-01/03.**
  - It recommended an "additive" window rule on the premise that it was a local, one-line
    change. Measured, it would have changed 652 papers, so Martin reversed the choice (CP-07).
  - It committed a script while ruff was failing, because a `;` chain did not stop on the
    error (`aa4ffa1` fixed it).
  - It wrote "four papers" in a commit message for three, and amended it before anything was
    pushed.

---

## Open decisions

Each item needs Martin. Each gives the options, a recommendation and what the choice would
change. A recommendation marked *(register)* is this file's own, not the record's.

**OD-01 · Seven rows are not the authors' own measurement of a plastic particle.**
- The rows (`report.origin.NOT_OWN_MEASUREMENT`; `REVIEW.md` §8 item 19):
  - PMC12878436 r4–r7: values cited from other papers;
  - PMC12462602-r2: PEG 4000;
  - PMC11644763-r1: a fabric;
  - PMC9645706-r4: a passing remark.
- Options: drop them, or flag them.
- Recommendation *(register)*: drop them. The extraction brief already excludes "a value cited
  from another study", and also fabrics (`docs/briefs/extraction.md`). Record the ruling in
  `tests/edge/key.yaml`.
- What changes: 1 890 → 1 883 rows. Every count and the origin tables rebuild.
- **Decided 2026-10-01 (Martin): drop them.** Not yet built. `NOT_OWN_MEASUREMENT` is keyed by
  row id, and the re-extractions renumber rows: PMC12878436's cited rows are already gone after
  `5012fdf`. The list has to be derived again from the final records before it is applied, or it
  will drop the wrong rows.

**OD-02 · The missing environmental row at PMC11211448 L26.**
- What it is: L26 prints the diluted wastewater's pH 5.8–6.2, its conductivity of
  1000–1050 µS/cm and an average zeta of −49 mV. The table has no row for it (`REVIEW.md` §6).
- Options:
  - Add the row, with an ionic strength estimated from the conductivity and marked as
    estimated, in line with Martin's "highlighted" condition (OS-02).
  - Keep it as a documented finding.
- Recommendation *(register)*: add it only together with a new `ionic_strength_source` value
  for estimates. Today's three values (reported, inferred_from_named_salt, unreported) cannot
  say "estimated".
- What changes: environmental rows go from 19 to 20, with the first environmental ionic
  strength, as an estimate.

**OD-03 · No human has checked any row against its paper.**
- State: `out/review/audit_sample.csv` holds 20 rows, and every `*_ok` column is empty
  (checked 2026-10-01).
- Options: Martin fills it in (about an hour, `REVIEW.md` §7 step 6), someone else does, or it
  stays empty.
- Recommendation *(register)*: Martin fills it in.
- What changes: C10 would gain a measured "read correctly" rate. This is not blind, so it does
  not replace OD-04.

**OD-04 · The κ audit has never run, so the gold standard was annotated only by a model.**
- State: `data/interim/annotation/audit_10.csv` is unfilled. `README.md` still says "10 papers
  are audited by the author", which is stale.
- Options:
  - Martin re-judges 10 gold papers blind (about an hour, `DESIGN_2026-09-17` §5 item 5).
  - Widen to about 30 papers, stratified by flag (`ideas.md` §10.2).
  - Re-extract a sample with a second model family (`ideas.md` §10.4).
- Recommendation *(register)*: the blind 10 first.
- What changes: if κ < 0.6, "the gold set is not ground truth" (`DESIGN_2026-09-17` §6).
- Note the tension in the record.
  - Martin rejected shipping the dataset labelled "annotated by Claude, not yet audited": "not
    acceptable, since even creation of datasets need reliable reproducable way" (`ideas.md` §2,
    R6).
  - The v0 card says "That gold set was annotated by Claude and has not been audited by a
    human" (`out/release/DATASET_CARD.md`, "The κ audit has not been done").

**OD-05 · `uv.lock` is gitignored.**
- Options: commit it, or strip `pandas_version` from the parquet metadata
  (`HANDOFF_2026-09-28.md` §4.3).
- Recommendation: commit it.
- What changes: a fresh clone rebuilds `dataset.parquet` byte for byte.

**OD-06 · `runs.code_commit` counts untracked files as dirty.**
- Options: `git status --porcelain --untracked-files=no` (HANDOFF §4.7), or leave it.
- Recommendation: fix it.
- What changes: future manifests stop reporting `code_dirty: true` because of Martin's research
  documents. The existing manifests keep it.

**OD-07 · Row citations are scored with a bias.**
- What: a `row:X` citation expands to every evidence line of the row, while the key lists only
  the value's lines. This deflated cell D's citation precision to 0.76 in the sweep (`3a477d3`
  handoff, §4.4).
- Options: resolve `row:X` to the value's lines only, or score row citations separately.
- Recommendation: fix it before any D-against-B claim about citation precision.
- What changes: cell D's citation precision.

**OD-08 · The kind A leak (A-012, A-013).**
- What: two kind A questions quote a medium name that contains their own ionic strength. They
  were left as is because the leak "affects both cells equally" (`HANDOFF_2026-09-28.md` §7).
- Options: keep them and disclose it, or replace both and re-ask (4 reader calls).
- Recommendation *(register)*: replace them, because it is cheap.
- What changes: kind A by at most 2 of 30 per cell.

**OD-09 · 162 rows carry stale verifier flags.**
- Source: `d538ce5`. Flags are computed once at ingest and never recomputed, so 162 rows in 34
  older records carry stale ones.
- Options:
  - Recompute now. `d538ce5` says this is "not safe yet": the step pattern would also clear 13
    genuine 25 °C readings.
  - Fix the pattern first, then recompute.
  - Leave them.
- Recommendation: fix the pattern, then recompute, with a per-row account of what changed.
- What changes: the flags on those rows, and any figure that a cleared value feeds.

**OD-10 · EHP's "public domain unless otherwise noted" (4 papers).**
- Options: ship their quotes, or keep them withheld (HANDOFF §4.5).
- Recommendation: this is a licensing question. Keep them withheld until it is answered.
- What changes: the number of shipped quotes. Those papers' row count is not in the record.

**OD-11 · Vendoring tiktoken.**
- Options: vendor the BPE table, sha-pinned, next to `xml.tar.gz` and set `TIKTOKEN_CACHE_DIR`
  (FINDINGS, "Open questions"), or leave it.
- Recommendation: vendor it.
- What changes: `report reproduce` works from a cold clone with no network.

**OD-12 · Card 2.**
- State: the defects are still in the table (`d1_zeta_table.csv`, checked 2026-10-01).
  - PMC13181784-r3/-r4 still store critical coagulation concentrations (56 and 398 mM) as
    ionic strengths.
  - PMC12598813-r13/-r14 still store 10.0 mM from the HEPES term alone.
- Options:
  - Re-issue the card (GATE_LOG) with the second caller named, the real mg/L population (36
    rows), a target that can fail, and a `contradictory` value source (FINDINGS E2c).
  - Retire it.
- Recommendation *(register)*: re-issue it.
- What changes: 4 rows lose an ionic strength. Fully conditioned does not move, because none of
  the 4 rows is complete (GATE_LOG).

**OD-13 · The GitHub PAT in `.git/config`. Rotate it.**
- The token sits in the git remote setting. It was never committed (`HANDOFF_2026-09-24.md`
  §7.1).
- A credential-shaped string was still there on 2026-10-01. This was checked by counting
  matches, without printing it.
- What changes: after rotation, pushing needs the new credential.

**OD-14 · Is BM25 a strong enough baseline for cell B?**
- What the plan said: `PLAN_2026-09-28.md` §4.1 promised section-aware chunking, an embedding
  model, a reranker, and written-down tuning. The design's own cut line keeps at least a plain
  hybrid (`DESIGN_2026-09-17` §5).
- What was measured: E6 found that BM25 ties the structured selector on honest queries.
- Options: keep BM25 and say so beside every result, or build the hybrid with a reranker.
- Recommendation *(register)*: build the hybrid before any public claim that structure beats
  retrieval.
- What changes: the answer to "you strawmanned the baseline" (PLAN §7).

**OD-15 · Cells C and E have not been run.**
- Options: run C (about 3.8 M tokens, `HANDOFF_2026-09-28.md` §5) and then E (about 1.2 M in
  `DESIGN_2026-09-17` §5, which the handoff says is low by about 1.58×), or present only B
  against D and say so.
- Recommendation: run C first ("never cut cell C", GR-14).
- What changes: whether the knowledge base earns anything at all (`DESIGN_2026-09-17` §6).

**OD-16 · What "fix" covers for the Methods defect (CP-07).**
- Options: fix the parser and re-extract the 208 papers (the record has no cost estimate), or
  fix the parser and state the bias for the existing rows.
- Recommendation: measure the impact first. An untracked `tool/methods_fix_impact.py` was in the
  working tree on 2026-10-01. Its name suggests that measurement, but this register did not read
  it.
- What changes: the condition-reporting headline, and `REVIEW.md` §8 item 18 and card limit 8.
- **Resolved 2026-10-01.** See CP-07: re-extract the 208, ask every reader question again, and
  apply one window rule for every paper.

**OD-17 · Edge cases S5, S29 and S31 are unruled.**
- State: `tests/edge/key.yaml` answers 8 of 69 cases.
  - S5: does a condition stated in Methods reach a value printed in Results? It moves the most
    rows.
  - S29: is incineration particulate a plastic particle?
  - S31: are elastomers and silicones in scope? (SESSION_2026-09-15, "Needs Martin")
- Recommendation: S5 first.
- What changes: ionic-strength, pH and temperature reporting across many rows.

**OD-18 · How comparability ships in the release.**
- Options: a precomputed pair table (1 785 105 pairs), the function plus its rules, or
  something else (`HANDOFF_2026-09-25.md` §5.2).
- What changes: what a dataset user can query without the code.

**OD-19 · A `conversion_model_reported` column, and renaming `model` to `extractor_model`.**
- State: proposed in HANDOFF_2026-09-25 §3, and not built (checked: no such column exists).
- What changes: the release schema and the card. The rename breaks any consumer.

**OD-20 · The repository holds text that is not CC BY.**
- What: `xml.tar.gz` holds 244 full texts that are not CC BY or CC0. The table and
  `extractions.jsonl` hold the 453 withheld quotes, and demo case 12 quotes an NC-ND paper
  (`HANDOFF_2026-09-28.md` §4.4).
- This matters only if the repo becomes public. If it does, decide what to remove first.

**OD-21 · Token-spending steps ran without a gate card.**
- What: `docs/GATE_LOG.md` says "every step that spends model tokens gets a card", but it holds
  only Cards 1 and 2. The cell D and cell B sweeps and the origin run ($24) have no card.
- Options: card them after the fact, or drop the rule for work Martin approved directly.

**OD-22 · Who did the hand checks?**
- What: the record never names the person who did the origin hand check (102 particles,
  `d4be112`) or the R2b read of 212 rows (`d538ce5`).
- Recommendation: Martin confirms who did them, and `REVIEW.md` says so. Right now "the
  person's verdict" can be read as a human audit.
- **Resolved 2026-10-02.** The session record shows Claude agents did both checks. RV-04 changed
  the wording.

**OD-23 · Reasons to record.**
- These entries say "reason not recorded":
  - CP-01: why Europe PMC.
  - EX-03: why subagents with no API key, and why Sonnet as the extractor.
  - RC-01: why these five conditions.
  - RC-07: why "reported" is generous.
  - HM-04: why a 1:1 electrolyte and not one computed from the medium's composition.
  - GR-05: why Sonnet as the reader.
  - OS-03: why not enlarge the corpus now.
- Each needs one sentence from Martin, or an honest "default, not chosen".

**OD-24 · `METHOD.md` calls rules "ratified" that Martin never ratified.**
- What: see the note under "Defects caught in agent output". Absence never imputed (RC-05),
  the no-lookup and no-conductivity rules (RC-06) and the generous "reported" (RC-07) appear in
  `METHOD.md` as ratified, with no ratification in the record.
- Options:
  - Martin ratifies them, and `docs/DECISIONS_NEEDED.md` or `tests/edge/key.yaml` records it.
  - `METHOD.md` (`src/mnp/demo/render.py`) stops calling them ratified.
- What changes: the wording of a generated document that scientists will read first.

**OD-25 · PMC13057466 stores a CaCl₂ concentration as its ionic strength.**
- What: "50 mmol L⁻¹ CaCl₂" is stored as a reported 50 mM, where the ratified salt rule (RC-02)
  gives 150 mM, derived. The coercer does not read the superscript unit `L⁻¹`, so the salt rule
  never ran. That is 5 rows in one paper. The table headers show that PMC11899741 and
  PMC11543686 really do state these numbers as ionic strengths ("IS", "Ionic strength (mM)"), so
  their values stand.
- Plan: fix the unit pattern test-first once the 239 re-read has finished, because changing
  `coerce` mid-run would parse half the run one way. Then replay the stored JSON, and send
  PMC13057466, whose JSON was lost (EX-11), back to a reader.

