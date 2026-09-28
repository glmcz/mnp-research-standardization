# The demo: thirteen real cases, each re-sampled four ways

Written 2026-09-28. Agreed with Martin the same day. This file is the one source of truth for
the agents that build it. If code and this file disagree, fix one of them; don't guess.

**Audience:** colloid and micro/nanoplastic scientists reviewing the method. They know zeta
potential and will attack the method. Written in English, at full technical depth.

**What it shows.** Thirteen papers, one per failure mode the corpus actually contains. For each
paper the reviewer sees how its measurements are **re-sampled**, and that word covers four
things:

1. **Standardisation walk.** Each row, and each of the five conditions: is it reported, derived,
   nominal or unreported, and why? Every "why" cites the line of the paper it came from.
2. **Comparability.** The comparability key's verdict on pairs inside the paper, and how many
   rows anywhere in the corpus this paper's rows could be compared with.
3. **Harmonised value.** Each zeta value corrected for the mobility-to-zeta conversion.
   Wherever a parameter the correction needs was never reported, the result is an **interval**,
   never a point.
4. **Paper-level resampling.** What this paper does to the corpus statistics when rows are
   the unit versus when papers are, plus the corpus-wide cluster bootstrap.

Plus the **reader**: cells D and B of the grid answer three questions per case, scored by the
committed scorer.

A second file, `METHOD.md`, explains **how the PoC measures**: every rule behind every number,
with its reason and a worked number computed at build time.

---

## Output

`python -m mnp.report demo` writes `out/demo/`:

| file | content |
|---|---|
| `README.md` | case index; the corpus-wide resampling table (E2e rebuilt); the conversion-model scan; reader results per cell |
| `cases/NN-<slug>.md` | one per case, with sections 1–7 below |
| `METHOD.md` | how the PoC measures |

The output is deterministic, with sorted output and fixed seeds. It joins the artefacts that
`report reproduce` rebuilds byte for byte. Reader answers come from committed run directories
and are **read, never regenerated**. When a run directory is missing, the page says "not run".

---

## The cases

Each case pins a paper **and** a check that proves the paper still shows its mode. A test runs
every check. If a pinned paper fails its check, pick the paper that best satisfies it from
`out/tables/d1_zeta_table.csv`, and say so in your report.

| NN | slug | pmcid | mode | check (on the paper's rows unless stated) |
|---|---|---|---|---|
| 01 | fully-conditioned | PMC11099890 | the rare success | ≥1 pair of its rows is in `comparability.comparable_census` |
| 02 | one-particle-three-media | PMC10141840 | medium alone moves zeta 54 mV | ≥3 rows of one particle, ≥3 distinct `medium_class`, zeta spread ≥ 50 mV |
| 03 | conductivity-not-ionic-strength | PMC12673110 (was PMC13181784, whose rows print no conductivity at all) | a number printed, not the one needed | `medium_text` matches conductivity (µS, mS/cm, "conductiv"), `ionic_strength_reported` False on those rows |
| 04 | derived-from-composition | PMC12312160 | ionic strength derived from a printed composition, never looked up | ≥1 row with `ionic_strength_source == inferred_from_named_salt` |
| 05 | buffer-named-only | PMC6981174 | "PBS" alone is not an ionic strength | `medium_text` names PBS/HEPES/Tris, `ionic_strength_reported` False |
| 06 | biological-medium | PMC8719689 | corona: different particles converge | ≥10 rows with `medium_class == culture_medium` |
| 07 | incubation-not-measurement-temperature | PMC4958399 | 25/37 °C incubation is not the measurement T; one particle printed twice (−20.0, −20.3) | `temperature_reported` False, and a line of the paper mentions incubation at 37 °C |
| 08 | room-temperature | PMC13520334 | "room temperature" counts as reported, flagged nominal | ≥1 row with non-null `temperature_qualifier` |
| 09 | mobility-reported | PMC11117817 | the measured quantity; zeta computable per model | ≥1 row with `quantity == electrophoretic_mobility` |
| 10 | size-regime | PMC10145996 | 50 nm vs 1 µm PS-NH2: +24 vs −34 mV | two rows of one material + functionalisation + medium, sizes ≥10× apart, opposite signs |
| 11 | environmental-matrix | PMC9318256 | effluent before/after treatment | ≥1 row with `medium_class == environmental_water` |
| 12 | weathered | PMC11543686 | aging changes charge and has no field | "aged", "weather" or "UV" in `functionalisation` or `particle_name` |
| 13 | self-contradiction | PMC12598813 | one salt concentration printed twice, ~10³–10⁴× apart (FINDINGS E2c) | the two contradicting lines, pinned by line id, both resolve in the paper |

Each case also carries a 2–3 sentence `why` that tells the reviewer what the case shows. It is
static text written in `cases.py`, and every number in it must be checked against the data.

---

## Per case page, sections

1. **Why this case**: the `why` text, plus pmcid, doi, year and journal.
2. **Rows**: row_id, particle, value ± sd with unit, medium, ionic strength, pH, T, instrument.
   Each row carries the `PMCID:Lnn` citations of its evidence lines, with the line text quoted.
3. **Standardisation walk**: row × condition → verdict and reason, with citations.
4. **Comparability**: verdicts and blockers for pairs inside the paper (all of them if ≤15,
   otherwise the first 15 by row_id); for each row, the number of corpus rows it is
   comparable or conditionally comparable with; and the paper's blocker fields next to the
   corpus-wide blocker distribution.
5. **Harmonised value**: row → reported value, the model named (or not), κa (or why it is
   unknown), f(κa), and `[low, high]` or a point, with the reason.
6. **Resampling**: rows in this paper; its weight per row (n/1890) versus per paper (1/491);
   and for each of the six metrics, the per-row and per-paper headline with and without the
   paper.
7. **Reader**: the three questions; cell D's and cell B's answers verbatim; the score; and each
   cited line resolved to its text.

---

## Modules — `src/mnp/demo/`, tests in `tests/demo/`

Owners are in brackets. **Touch only your own files.**

### `resample.py` [agent A], which rebuilds FINDINGS E2e

Neither implementation of E2e was committed. Rebuild it, and it must reproduce the published
table on the current `d1_zeta_table.csv`:

| metric column | per row | per paper | ICC | DEFF | n_eff |
|---|---|---|---|---|---|
| medium_reported | 83.2 % | 72.1 % | 0.84 | 3.38 | 560 |
| ionic_strength_reported | 14.2 % | 8.7 % | 0.83 | 3.33 | 567 |
| pH_reported | 21.3 % | 16.8 % | 0.78 | 3.22 | 588 |
| temperature_reported | 28.0 % | 20.9 % | 0.94 | 3.66 | 517 |
| instrument_reported | 88.8 % | 81.0 % | 0.94 | 3.66 | 517 |
| conditions_complete | 3.3 % | 2.3 % | 0.80 | 3.27 | 577 |

- **per paper** = the mean over papers of each paper's row proportion (weight 1 per paper).
- ICC comes from a one-way random-effects ANOVA with unbalanced cluster sizes (use the standard
  adjusted m₀); `DEFF = 1 + (m₀ − 1)·ICC` and `n_eff = N / DEFF`.
- **Cluster bootstrap**: B = 10 000, seed 20260921, resampling **paper indices** with
  replacement, for both per-row and per-paper estimates. **Never `groupby` on the cluster key
  after resampling.** That merges a paper drawn twice back into one and narrows the interval.
  Write a test that implements the trap and shows its interval comes out narrower.
- Naive binomial interval, `√(p(1−p)/N)`, reported next to the cluster one. FINDINGS says the
  cluster interval is 2.1–4.1× wider, and for temperature ±2.0 vs ±8.4 pp.
- `leave_one_out(table, pmcid)` → per metric: per-row and per-paper values with and without
  that paper.
- If a published number does not reproduce, **do not tune until it matches**. Report the
  difference and its cause, since the table may have changed since E2e.

### `harmonise.py` [agent B], which rebuilds the E2b conversion-model scan and computes intervals

- `models_named(pmcid)` returns the conversion models the paper's text names: Smoluchowski,
  Hückel/Huckel, Henry (function or equation), Ohshima. It is a case-insensitive scan of the
  vendored XML full text, as in FINDINGS E2b ("Correction — the denominator was wrong"). It
  must reproduce **485 papers reporting a zeta value, 33 name a model, 452 do not**, and
  **13 reporting a mobility, 6 name a model**. If it does not, report the difference; don't
  tune.
- Henry: μ = (2εζ / 3η)·f(κa), with f ∈ [1, 1.5]. Smoluchowski assumes f = 1.5, Hückel f = 1.
  A zeta reported under an assumed f_m gives ζ_true = ζ_rep · f_m / f(κa). Reuse
  `comparability.henry_f`, `debye_length_nm` and `ZetaRow.kappa_a`.
  - model named, κa known → a point;
  - model named, κa unknown (ionic strength or size unreported) → `ζ_rep · f_m · [1/1.5, 1/1]`;
  - model unnamed, κa known → the two points for f_m ∈ {1, 1.5}, as an interval;
  - both unknown → `ζ_rep · [1/1.5, 1.5]`.
  Sort the bounds so low ≤ high whatever the sign.
- **Which model counts as named** (revised 2026-09-28, after agent B's first pass):
  - a single named limit (Smoluchowski *or* Hückel) gives a known f_m;
  - Henry or Ohshima named means the paper applied the general function with its own κa, so
    the point is the reported value, and κa and f are shown as context only;
  - naming **both** limits without Henry means f_m is **unknown**, the same as unnamed. Papers
    usually write "Smoluchowski rather than Hückel", and a mention cannot say which was applied.
  - `models_named` records mentions, not the model actually applied. Every harmonised value is
    therefore conditional on "the named model is the one applied", an upper bound in the same
    sense as the E2b scan.
- Mobility rows: ζ = 3ημ / (2ε f(κa)), using water ε and η at the reported T from
  `mnp.ek.constants`. **If T is unreported, return no value, with the reason "needs the
  measurement temperature". Never default T.** Convert the mobility unit (commonly
  µm·cm/(V·s) = 1e-8 m²/(V·s)); an unknown unit gives no value, with a reason.
- Every result carries a one-line `why`.

### `cases.py`, `walk.py`, `questions.py` [agent C]

- `cases.py`: the `Case` dataclass (nn, slug, pmcid, mode, why, check), the `CASES` tuple from
  the table above, and `verify(case, table, corpus) -> str | None`, which returns None when the
  check passes and a reason when it doesn't.
- `walk.py`: `walk_row(row, doc) -> tuple[Step, ...]`, one Step per condition, in this order:
  medium, ionic_strength, pH, temperature, instrument. `Step(condition, verdict, reason,
  citations)`, where verdict ∈ {reported, derived, nominal, unreported}. The rules are the
  ratified ones in `docs/2026-09-21-cile-a-otazky-pro-vedce.md` Part 1 (translate to English):
  derived = `ionic_strength_source == inferred_from_named_salt`; nominal = a non-null
  `temperature_qualifier`; unreported reasons must name the specific cause the row shows
  (conductivity given, buffer named without composition, culture medium, nothing printed).
  Citations: `PMCID:Lnn` via the row's `evidence_line_ids`, resolved in the corpus.
- `questions.py`: `questions_for(case, table) -> list[tuple[Question, AnswerKey]]`, three per
  case, with qid `X<NN>-A|B|E`, in the exact shapes of `mnp.eval.query_sets` so that
  `cells.build_d`, `cells.build_b` and `scoring.score_one` work unchanged:
  - **A**: a lookup of a row that is unique in its paper by material + functionalisation +
    medium_text + particle_name (always name the particle);
  - **B**: absence or presence of a condition on which every row of the paper agrees;
  - **E**: one pair inside the paper, with its key from `comparability.comparable` (verdict,
    blockers, blocker_fields).
  If a case has no valid question of a kind, return fewer questions and say why in a comment
  on the case. Never force one.

### `render.py`, the runner, protocol, reproduce, and the reader runs [agent D, after A–C]

- Renders all three outputs from A–C plus the recorded runs. `report demo` goes in
  `mnp.report.__main__.RUNNERS`; add a `protocol.py` Step and regenerate `docs/PROTOCOL.md`;
  include `out/demo/` in `reproduce`.
- Reader runs: `grid.run_cell` for cells **D** and **B** over every demo question, into
  `data/interim/runs/demo-celld-20260928` and `demo-cellb-20260928`, with `runs.start` / `finish`
  manifests as `python -m mnp.eval cell` writes them. The reader is `grid.read`, which is
  claude-sonnet-5 with isolation. The spend is ~0.5 M tokens and must not exceed 1 M. A
  usage-policy refusal is recorded in errors.jsonl and shown on the page as "refused by the
  reader's usage-policy filter". It is never retried more than once.
- `METHOD.md` covers: corpus and parsing; line addresses; extraction and verbatim verification;
  the five conditions and what counts as reported (with the three extra rules); ionic-strength
  sources; comparability rules, tolerances and grades, with the census (16 / 6 / 0 / 35) and
  the 81 624 that appear when defaults are allowed; harmonisation (Henry, the 1:1 Debye length
  and its limitation, the interval logic, the conversion-model scan); resampling (per paper as
  primary, ICC, DEFF, n_eff, the cluster bootstrap and the groupby trap); the reader grid (cells,
  isolation, model pin, scorer rules, refusals); and limits (κ audit not done, gold annotated by
  a model, mention scan is an upper bound, 1:1 electrolyte, no licence). Every number is
  computed at build time.

---

## Rules for every agent

- **Absence is never imputed.** No defaults for any condition. A missing parameter gives an
  interval or "not computable", with its reason.
- No model calls, except agent D's reader runs through `grid.read`.
- Deterministic: fixed seeds, sorted output, no clocks in generated files.
- **Tests first, proven red.** Run a new test before the code exists, or mutate the fix back
  and watch the test fail. Green-only tests don't count.
- Touch only your own files. Run `ruff format` and `ruff check` **on your files only**, never
  the whole tree. Always `unset VIRTUAL_ENV` before `uv run`.
- Don't commit. The parent session commits.
- Report back: files written; test counts, including the red run; every published number that
  did or didn't reproduce; every deviation from this file, with its reason.
