# METHOD — how the PoC measures

**Scope: read this first.**

- **What it is.** The surface charge of micro- and nanoplastic particles as measured in liquids in laboratory studies: 1 903 rows from 467 papers, 1 840 zeta potentials and 63 electrophoretic mobilities (`d1_zeta_table.csv`).
- **Measured in a liquid.** A zeta potential exists only in a liquid, so every value describes the particle in the liquid it was measured in, not in the environment it came from.
- **Where the particles came from.** 95.4 % of rows (1 815 / 1 903) measure a synthetic particle, bought or made in a lab. Only 12 rows, from 3 papers, measure particles collected from a real environment: 11 from wastewater effluent (2 papers) and 1 classed "other" (1 paper). From air or dust, freshwater, seawater, soil or sediment: 0 rows. Agent-checked: a Claude agent gave every environmental particle and samples of the rest a second reading with the paper's full text; no person has checked these counts (`sample_origin_stats.json`, REVIEW.md C11).
- **The measurement liquids.** Rows per `medium_class`: DI water 474, culture medium 317, salt solution 232, buffer 167, environmental water 28, biofluid 20, other 262, unreported 403.
- **The corpus.** The open-access subset of one database (Europe PMC) for one query: 1 115 hits, 862 of them open access, 858 full texts fetched, 467 papers with a measurement (`d1_stats.json`). What that leaves out: `docs/2026-09-30-corpus-scope-notes.md`.
- **What it can be used for.** How laboratory measurements are reported and whether they can be compared. Not how plastics behave in air, water or soil.

Every number below is either computed at build time from the repo's own code and data, or quoted with the exact FINDINGS file and section that measured it. None is typed by hand as a bare number.

## Corpus and parsing

1903 rows from 467 papers, one row per printed measurement of a zeta potential or an electrophoretic mobility (`out/tables/d1_zeta_table.csv`, built by `report d1`). Line addresses (`PMCID:Lnn`) come from `mnp.corpus.lines`, and evidence quotes are verified verbatim against the vendored JATS XML before a row is written.

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
2. **Absence is never imputed.** "DI water" is a reported medium; it does not mean ionic strength zero. What absence costs is measured, not imagined: of the 166,965 pairs of rows that describe the same particle, **29,075** are blocked only by conditions one row or both did not report, and **2** are comparable (the same-particle census below; every category in `README.md`). These are pairs blocked only by absence -- not a count of what any default would make comparable.
3. **Every figure here is an upper bound.** "Reported" is softer than "reported as a number": a pH range counts, a nominal room temperature counts, an instrument family counts. True completeness is lower than every percentage this project prints.

## Ionic-strength sources

Every row's `ionic_strength_source`, counted at build time from `out/tables/d1_zeta_table.csv`:

| source | rows | papers |
|---|---|---|
| reported | 68 | 9 |
| inferred_from_named_salt | 172 | 31 |
| unreported | 1663 | 441 |

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

On the current table, the exhaustive census over all 1,809,753 unordered pairs finds **2** fully comparable pairs, of which **2** compare two zeta potentials and **1** of those cross a paper boundary; **3** pairs are conditionally comparable.

The kind E query set (`queries/kind_e_comparability.csv`) unions the exhaustive census of comparable and conditionally comparable pairs with **5** uniform seeded strata -- 60 from `same_paper`; 60 from `cross_paper_same_material`; 60 from `cross_paper_different_functionalisation`; 30 from `cross_paper_different_material`; 60 from `both_conditions_complete` -- plus the census itself, so a rare positive is never sampled away. Loaded here it holds 274 pairs.

## The same-particle census

`mnp.eval.comparability.same_particle_census` takes every pair of rows that measure the same particle -- the same `quantity`, the same `material_key(material)` (a row whose material is unreported is left out) and the same `functionalisation_key(functionalisation)` -- and grades it with `comparable(a, b)`. Each pair falls in exactly one category, decided in this order:

- **comparable** -- verdict `comparable`;
- **conditionally comparable** -- verdict `conditionally_comparable`;
- **lost only to absence** -- verdict `not_comparable` and **every** blocker has kind `unreported`;
- **a stated difference** -- verdict `not_comparable` and at least one blocker has kind `mismatch`;
- **undecidable** -- the rest: no mismatch, and at least one blocker `undecidable`.

Within lost only to absence it counts, per blocker field, the pairs where that field is among the missing ones; per field, the pairs where it is the only one missing; and the pairs that cross a paper boundary. A surface unreported on both rows keys to no surface, so those rows group together, but `comparable` still raises `functionalisation_unreported` on every such pair: an unstated surface is counted as absence, never as sameness. The census counts what blocks a pair. It imputes nothing and says nothing about what a default would do. The numbers are in `README.md`.

## Harmonisation

`mnp.demo.harmonise` rebuilds FINDINGS E2b's conversion-model scan (case-insensitive regex over the vendored full text for Smoluchowski, Hückel, Henry's function/equation and Ohshima) and reproduces on this table: **462** papers report a zeta value, **32** name a model, **430** do not; **15** report a mobility, **6** name a model (docs/FINDINGS.md §E2b). Naming a single textbook limit (Smoluchowski or Hückel) gives a known assumed f_m; naming Henry's function or Ohshima's approximation means no single f_m was assumed, so the reported value stands; naming both limits without Henry is treated as unknown, since a mention scan cannot tell which one was applied (harmonise.py's documented deviation from the original design, decided in review on 2026-09-28, recorded in docs/DESIGN_2026-09-28_demo.md). A missing ionic strength or size gives no kappa*a and returns an interval, never a point produced by guessing. Zeta from a reported mobility uses ζ = 3ημ / (2ε f(κa)) at the reported temperature; an unreported temperature returns no value at all rather than defaulting to a water property. The Debye length assumes a 1:1 electrolyte in water at 25°C -- a limitation for any medium with divalent ions, stated here rather than silently applied.

## Resampling

`mnp.demo.resample` rebuilds FINDINGS E2e: reporting completeness computed per row is inflated because rows cluster by paper. ICC comes from a one-way random-effects ANOVA with the unbalanced-cluster adjustment m0; DEFF = 1 + (m0-1)*ICC and n_eff = N/DEFF follow from it. The cluster bootstrap (B=10,000, seed 20260921) resamples **paper indices** with replacement and never regroups by the cluster key afterward -- doing so would silently merge a paper drawn twice back into one group and narrow the interval, the exact defect one of the two original, uncommitted implementations had.

Every metric, rebuilt on the current table, per row and per paper, with both interval styles:

| metric | per row | per paper | ICC | DEFF | n_eff | naive ± (row) | cluster ± (row) | cluster ± (paper) |
|---|---|---|---|---|---|---|---|---|
| medium_reported | 78.8% | 67.6% | 0.81 | 3.48 | 546 | 1.8 pp | 4.4 pp | 4.1 pp |
| ionic_strength_reported | 12.6% | 7.2% | 0.87 | 3.67 | 519 | 1.5 pp | 5.2 pp | 2.2 pp |
| pH_reported | 18.5% | 13.6% | 0.84 | 3.57 | 533 | 1.7 pp | 5.2 pp | 2.9 pp |
| temperature_reported | 23.0% | 19.0% | 0.86 | 3.62 | 525 | 1.9 pp | 6.3 pp | 3.5 pp |
| instrument_reported | 87.2% | 80.9% | 0.89 | 3.72 | 512 | 1.5 pp | 3.4 pp | 3.4 pp |
| conditions_complete | 2.4% | 1.6% | 0.79 | 3.43 | 555 | 0.7 pp | 1.9 pp | 1.0 pp |

**Worked example -- temperature.** The naive binomial half-width is ±1.9 pp; the cluster bootstrap gives ±6.3 pp per row. Any interval this project computed as `sqrt(p(1-p)/1890)` is that far wrong.

**Cluster/naive ratio across the six metrics: 2.24x to 3.49x** -- every metric's cluster interval is at least twice the naive one.

**Ionic strength's ICC.** This rebuild gives **0.8737** (0.87 in the table above), where FINDINGS.md §E2e printed 0.83. FINDINGS predates the rule of 2026-09-28 that a printed 0 mM is not a reported ionic strength; on the table before it, this code gave 0.8247 (commit f78a4f5), which the printed 0.83 most likely rounds twice (0.8247 -> 0.825 -> 0.83). The 8 rows that rule cleared account for the rest. The difference is reported here, not tuned to match.

**Leave-one-out, PMC8719689 (case 06, 90 rows -- the largest single paper in the corpus).** Dropping it moves the per-row temperature-reported estimate by 1.8 pp (23.0% -> 21.2%) but the per-paper estimate by only 0.1 pp (19.0% -> 18.9%) -- on a real paper, the demonstration of why per-paper is the more conservative unit: one large paper cannot move it much.

## The reader grid

Cells D (structured records first, prose fallback) and B (BM25 top-k lines, no table) of `mnp.eval.cells` answer the demo's kind A/B/E questions through `mnp.eval.grid.read`: `claude -p` with `--tools ""`, `--setting-sources ""`, `--strict-mcp-config`, its own system prompt (replacing the coding-agent one), and a temporary working directory with no CLAUDE.md above it, so nothing but the prompt reaches the model. The model is pinned by full id (`claude-sonnet-5`, `mnp.eval.grid.READER_MODEL`) and a reply is refused if it comes from any other model.

`mnp.eval.scoring` scores every answer without a model: fabrication is counted on kind B (and on the absence half of kind A) whenever an answer states a value the paper never reported; an unparseable reply counts as wrong, never as excluded from the denominator. A citation counts whether it is listed in the `citations` field or written inside the answer's own text, as a scientist would write it -- but only as a full address (`PMCID:Lnn` or `row:ID`); a bare `L3` in a sentence is not one.

A reader failure (timeout, wrong model, no JSON) is not an answer -- it goes to `errors.jsonl` and the question is asked again the next time the run resumes. The harness itself carries no "only once" limit on that resume; the two runs this demo reads happen to have each been resumed at most once. A usage-policy refusal is different: it is deterministic (D-008 was refused three times on ordinary colloid text), so it is recorded as the cell's answer, scored wrong, kept in the denominator and never asked again (Martin, 2026-09-28).

Cell D is handed the matching structured rows for each question, so a high score there is the expected outcome, not a finding on its own -- what the grid actually measures is cell D's *difference* from cell B, which is given only BM25-retrieved lines and no table. Both cells answer the same 37 questions here: an illustration of the grid running on this demo's own cases, not a statistical estimate of either cell's accuracy.

## Limits, stated plainly

- **The kappa audit has not been done.** Extraction accuracy is scored against `gold_50.csv`, which was annotated by Claude and has not been checked by a human; a blind re-judgement worksheet (`audit_10.csv`) exists and is unfilled (`out/release/DATASET_CARD.md`).
- **The gold set itself is model-annotated.** Every accuracy number this demo reports inherits that provenance.
- **`models_named` records mentions, not the model actually applied.** Every harmonised value is conditional on "the named model is the one applied" -- an upper bound in the same sense the E2b scan itself is; a mention in a background paragraph is not evidence of what was used.
- **The Debye length assumes a 1:1 electrolyte.** A medium with divalent ions has a shorter true Debye length than `debye_length_nm` returns.
- **Quotes ship only from CC BY and CC0 sources.** The release is licensed CC BY 4.0; a quote from any other source is withheld and can be restored locally (`out/release/DATASET_CARD.md`, Licence).
