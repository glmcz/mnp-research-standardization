# METHOD — how the PoC measures

Every number below is either computed at build time from the repo's own code and data, or quoted with the exact FINDINGS file and section that measured it. None is typed by hand as a bare number.

## Corpus and parsing

1890 rows from 491 papers, one row per printed measurement of a zeta potential or an electrophoretic mobility (`out/tables/d1_zeta_table.csv`, built by `report d1`). Line addresses (`PMCID:Lnn`) come from `mnp.corpus.lines`, and evidence quotes are verified verbatim against the vendored JATS XML before a row is written.

## The five conditions -- what counts as reported

`mnp.demo.walk.walk_row` walks every row through these five conditions, in this order, against the ratified rules of `docs/2026-09-21-cile-a-otazky-pro-vedce.md` Part 1, translated:

| condition | why a zeta value means nothing without it | counts as reported | does not count |
|---|---|---|---|
| medium | zeta is a property of the particle **and** its medium | any liquid named, even "DI water", even "PBS" | the paper never names a liquid at all |
| ionic strength (mM) | sets the Debye length; without it the mobility curve has no x-axis | "10 mM NaCl"; even a printed composition ("0.137 M NaCl, 0.0027 M KCl"), then as **derived** | "PBS" or "HEPES" named alone; a component whose speciation the paper never states; a named buffer's nominal composition is never looked up |
| pH | sets dissociation of surface groups, and can flip the sign on a functionalised particle | a number, even a range ("between 6.8 and 7.2") | "physiological pH" with no number attached |
| temperature (°C) | enters ε, η and kT in every conversion model | a number; even "room temperature", but flagged **nominal** | incubation, exposure, storage or culture temperature -- even when the paper states no other temperature anywhere |
| instrument | different instruments apply a different mobility-to-zeta conversion | even a family name ("Zetasizer"); brand and model is better and is stored verbatim | nothing named at all |

## Verdict vocabulary

`mnp.demo.walk.walk_row` gives each of a row's five conditions one of four verdicts, in the fixed order medium, ionic strength, pH, temperature, instrument:

- **reported** -- the paper states it directly: a number, a range, a name, or (for temperature only) a qualitative phrase.
- **derived** -- computed from a printed composition (`ionic_strength_source == "inferred_from_named_salt"`), never a looked-up nominal value.
- **nominal** -- reported only as a qualitative phrase ("room temperature") rather than a number; a non-null `temperature_qualifier`, flagged rather than treated as a measured value.
- **unreported** -- nothing usable is printed. The reason always names the specific cause the row shows -- see the per-condition table above and the worked example below.

## Three extra rules

Three rules, ratified before this demo and written down in `docs/2026-09-21-cile-a-otazky-pro-vedce.md` Part 1, sit above the per-condition table and the verdict vocabulary -- they are not the same three things as reported/derived/nominal/unreported and should not be conflated with it:

1. **Scope.** A condition holds only inside the experiment that states it. It is never carried to another preparation, not even one in the same paper (ratified 2026-09-13).
2. **Absence is never imputed.** "DI water" is a reported medium; it does not mean ionic strength zero. This is the one rule whose removal moves the numbers by orders of magnitude: the corpus-wide comparable-pair count goes from **16** to **81,624** when every `*_unreported` rule is dropped and absence is allowed a default (`docs/FINDINGS_comparability.md` §4c).
3. **Every figure here is an upper bound.** "Reported" is softer than "reported as a number": a pH range counts, a nominal room temperature counts, an instrument family counts. True completeness is lower than every percentage this project prints.

## Ionic-strength sources

Every row's `ionic_strength_source`, counted at build time from `out/tables/d1_zeta_table.csv`:

| source | rows | papers |
|---|---|---|
| reported | 128 | 17 |
| inferred_from_named_salt | 141 | 36 |
| unreported | 1621 | 458 |

Conductivity is never converted to ionic strength -- the conversion needs an assumed ionic composition the paper does not give -- and a buffer's nominal composition is never looked up even when the field knows it by heart. Both land in `unreported`, never in a value.

**Worked example, case 02 (PMC10141840).** Three rows, one particle, ionic strength unreported on all three -- for three different reasons (`walk.walk_row`):
- `PMC10141840-r1` (H2O (0.55 µS)): conductivity is printed instead of ionic strength ("H2O (0.55 µS)"); converting conductivity to ionic strength needs an assumed ionic composition, which is never assumed here
- `PMC10141840-r2` (PBS): a buffer is named ("PBS") without its printed composition; the nominal ionic strength of a named buffer is never looked up
- `PMC10141840-r3` (RPMI-1640 (fs)): the medium is a culture or biological medium ("RPMI-1640 (fs)"); its composition is not printed as a checkable ionic strength

## Comparability

`mnp.eval.comparability.comparable(a, b)` grades a pair `comparable` (no blockers), `conditionally_comparable` (every blocker is a stated, quantified difference on one of the axis fields below) or `not_comparable` (anything else).

Tolerances, read from the module's own constants, never typed by hand: ionic strength 10% relative, pH ±0.2 units, temperature ±2°C, Henry's f 5% relative -- each argued in `docs/FINDINGS_comparability.md` §2.

A mismatch keeps a pair only *conditionally* comparable when it falls on one of these axis codes -- a stated, quantified difference the reviewer can still place on a common scale:

- `ionic_strength_mismatch`
- `medium_class_mismatch`
- `medium_text_mismatch`
- `pH_mismatch`
- `temperature_mismatch`

Anything else the key can flag is a blocker field, the vocabulary a kind E answer names: `quantity`, `material`, `functionalisation`, `medium`, `ionic_strength`, `pH`, `temperature`, `instrument`, `size_measured_nm`, `conversion_model`.

The κ·a conversion-regime rule (Henry's f within 5%) applies only when **both** rows report a zeta potential -- a mobility row has no assumed f_m to compare, so the rule never fires on it.

On the current table, the exhaustive census over all 1,785,105 unordered pairs finds **16** fully comparable pairs, of which **6** compare two zeta potentials and **0** of those cross a paper boundary; **35** pairs are conditionally comparable.

The kind E query set (`queries/kind_e_comparability.csv`) unions the exhaustive census of comparable and conditionally comparable pairs with **5** uniform seeded strata -- 60 from `same_paper`; 60 from `cross_paper_same_material`; 60 from `cross_paper_different_functionalisation`; 30 from `cross_paper_different_material`; 60 from `both_conditions_complete` -- plus the census itself, so a rare positive is never sampled away. Loaded here it holds 320 pairs.

## Harmonisation

`mnp.demo.harmonise` rebuilds FINDINGS E2b's conversion-model scan (case-insensitive regex over the vendored full text for Smoluchowski, Hückel, Henry's function/equation and Ohshima) and reproduces on this table: **485** papers report a zeta value, **33** name a model, **452** do not; **13** report a mobility, **6** name a model (docs/FINDINGS.md §E2b). Naming a single textbook limit (Smoluchowski or Hückel) gives a known assumed f_m; naming Henry's function or Ohshima's approximation means no single f_m was assumed, so the reported value stands; naming both limits without Henry is treated as unknown, since a mention scan cannot tell which one was applied (harmonise.py's documented deviation from the original design, decided in review on 2026-09-28, recorded in docs/DESIGN_2026-09-28_demo.md). A missing ionic strength or size gives no kappa*a and returns an interval, never a point produced by guessing. Zeta from a reported mobility uses ζ = 3ημ / (2ε f(κa)) at the reported temperature; an unreported temperature returns no value at all rather than defaulting to a water property. The Debye length assumes a 1:1 electrolyte in water at 25°C -- a limitation for any medium with divalent ions, stated here rather than silently applied.

## Resampling

`mnp.demo.resample` rebuilds FINDINGS E2e: reporting completeness computed per row is inflated because rows cluster by paper. ICC comes from a one-way random-effects ANOVA with the unbalanced-cluster adjustment m0; DEFF = 1 + (m0-1)*ICC and n_eff = N/DEFF follow from it. The cluster bootstrap (B=10,000, seed 20260921) resamples **paper indices** with replacement and never regroups by the cluster key afterward -- doing so would silently merge a paper drawn twice back into one group and narrow the interval, the exact defect one of the two original, uncommitted implementations had.

Every metric, rebuilt on the current table, per row and per paper, with both interval styles:

| metric | per row | per paper | ICC | DEFF | n_eff | naive ± (row) | cluster ± (row) | cluster ± (paper) |
|---|---|---|---|---|---|---|---|---|
| medium_reported | 83.2% | 72.1% | 0.84 | 3.38 | 560 | 1.7 pp | 3.8 pp | 3.8 pp |
| ionic_strength_reported | 14.2% | 8.7% | 0.82 | 3.33 | 567 | 1.6 pp | 5.6 pp | 2.3 pp |
| pH_reported | 21.3% | 16.8% | 0.78 | 3.22 | 588 | 1.8 pp | 5.3 pp | 3.1 pp |
| temperature_reported | 28.0% | 20.9% | 0.94 | 3.66 | 517 | 2.0 pp | 8.7 pp | 3.4 pp |
| instrument_reported | 88.8% | 81.0% | 0.94 | 3.66 | 517 | 1.4 pp | 2.9 pp | 3.4 pp |
| conditions_complete | 3.3% | 2.3% | 0.80 | 3.27 | 577 | 0.8 pp | 2.3 pp | 1.3 pp |

**Worked example -- temperature.** The naive binomial half-width is ±2.0 pp; the cluster bootstrap gives ±8.7 pp per row. Any interval this project computed as `sqrt(p(1-p)/1890)` is that far wrong.

**Cluster/naive ratio across the six metrics: 2.04x to 4.28x** -- every metric's cluster interval is at least twice the naive one.

**Ionic strength's ICC.** This rebuild gives **0.8247** (0.82 in the table above), where FINDINGS.md §E2e printed 0.83 -- most likely 0.825 rounded a second time. The difference is reported here, not tuned to match.

**Leave-one-out, PMC8719689 (case 06, 90 rows -- the largest single paper in the corpus).** Dropping it moves the per-row temperature-reported estimate by 3.6 pp (28.0% -> 24.4%) but the per-paper estimate by only 0.2 pp (20.9% -> 20.7%) -- on a real paper, the demonstration of why per-paper is the more conservative unit: one large paper cannot move it much.

## The reader grid

Cells D (structured records first, prose fallback) and B (BM25 top-k lines, no table) of `mnp.eval.cells` answer the demo's kind A/B/E questions through `mnp.eval.grid.read`: `claude -p` with `--tools ""`, `--setting-sources ""`, `--strict-mcp-config`, its own system prompt (replacing the coding-agent one), and a temporary working directory with no CLAUDE.md above it, so nothing but the prompt reaches the model. The model is pinned by full id (`claude-sonnet-5`, `mnp.eval.grid.READER_MODEL`) and a reply is refused if it comes from any other model.

`mnp.eval.scoring` scores every answer without a model: fabrication is counted on kind B (and on the absence half of kind A) whenever an answer states a value the paper never reported; an unparseable reply counts as wrong, never as excluded from the denominator.

A reader failure (timeout, wrong model, no JSON) is not an answer -- it goes to `errors.jsonl` and the question is asked again the next time the run resumes. The harness itself carries no "only once" limit on that resume; the two runs this demo reads happen to have each been resumed at most once. A usage-policy refusal is recorded the same way in `errors.jsonl` and rendered as a refusal rather than a missing answer.

Cell D is handed the matching structured rows for each question, so a high score there is the expected outcome, not a finding on its own -- what the grid actually measures is cell D's *difference* from cell B, which is given only BM25-retrieved lines and no table. Both cells answer the same 36 questions here: an illustration of the grid running on this demo's own cases, not a statistical estimate of either cell's accuracy.

## Limits, stated plainly

- **The kappa audit has not been done.** Extraction accuracy is scored against `gold_50.csv`, which was annotated by Claude and has not been checked by a human; a blind re-judgement worksheet (`audit_10.csv`) exists and is unfilled (`out/release/DATASET_CARD.md`).
- **The gold set itself is model-annotated.** Every accuracy number this demo reports inherits that provenance.
- **`models_named` records mentions, not the model actually applied.** Every harmonised value is conditional on "the named model is the one applied" -- an upper bound in the same sense the E2b scan itself is; a mention in a background paragraph is not evidence of what was used.
- **The Debye length assumes a 1:1 electrolyte.** A medium with divalent ions has a shorter true Debye length than `debye_length_nm` returns.
- **This dataset has no licence yet.** `out/release/DATASET_CARD.md` records that explicitly; do not redistribute it until that is settled.
