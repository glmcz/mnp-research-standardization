# The demo: 14 real cases, each re-sampled four ways

**Scope: read this first.**

- **What it is.** The surface charge of micro- and nanoplastic particles as measured in liquids in laboratory studies: 1 903 rows from 467 papers, 1 840 zeta potentials and 63 electrophoretic mobilities (`d1_zeta_table.csv`).
- **Measured in a liquid.** A zeta potential exists only in a liquid, so every value describes the particle in the liquid it was measured in, not in the environment it came from.
- **Where the particles came from.** 95.4 % of rows (1 815 / 1 903) measure a synthetic particle, bought or made in a lab. Only 12 rows, from 3 papers, measure particles collected from a real environment: 11 from wastewater effluent (2 papers) and 1 classed "other" (1 paper). From air or dust, freshwater, seawater, soil or sediment: 0 rows. Agent-checked: a Claude agent gave every environmental particle and samples of the rest a second reading with the paper's full text; no person has checked these counts (`sample_origin_stats.json`, REVIEW.md C11).
- **The measurement liquids.** Rows per `medium_class`: DI water 474, culture medium 317, salt solution 232, buffer 167, environmental water 28, biofluid 20, other 262, unreported 403.
- **The corpus.** The open-access subset of one database (Europe PMC) for one query: 1 115 hits, 862 of them open access, 858 full texts fetched, 467 papers with a measurement (`d1_stats.json`). What that leaves out: `docs/2026-09-30-corpus-scope-notes.md`.
- **What it can be used for.** How laboratory measurements are reported and whether they can be compared. Not how plastics behave in air, water or soil.

See `docs/DESIGN_2026-09-28_demo.md` for what this shows and `METHOD.md` for how every number below is computed. One page per case is in `cases/`.

## Cases

| nn | slug | pmcid | mode | result |
|---|---|---|---|---|
| 01 | fully-conditioned | PMC12955872 | the rare success | Two PEGylated carboxylate polystyrene particles, nominally 20 and 40 nm, give -2.91 and -2.04 mV in the same 15x diluted PBS (~10 mM NaCl, pH 7.4) at 25 C on the same Zetasizer NanoZS: every condition is printed, and these two rows are one of only two fully comparable pairs in the 1,908-row corpus (`comparability.comparable_census`). |
| 02 | one-particle-three-media | PMC10141840 | medium alone moves zeta 54 mV | One 1.14 micron polystyrene particle, one pH, one temperature, one instrument -- the only thing that changes across these three rows is the medium, and the zeta potential swings from about -68 mV in water to about -14 mV in a culture medium. |
| 03 | conductivity-not-ionic-strength | PMC12673110 | a number printed, not the one needed | Two aqueous media here are named by their conductivity rather than by a stated ionic strength: tap water at 230 uS/cm, a NaCl solution at 4,000 uS/cm. |
| 04 | derived-from-composition | PMC12312160 | ionic strength derived from a printed composition, never looked up | Every zeta row here states its dispersion as 10 mM HEPES plus either 1 mM or 100 mM NaCl -- a printed composition, not a number copied from a lookup table. |
| 05 | buffer-named-only | PMC6981174 | "PBS" alone is not an ionic strength | All seven rows disperse the particle in some form of PBS, one of the best-known buffers in the field, which is exactly why it is dangerous here. |
| 06 | biological-medium | PMC8719689 | corona: different particles converge | Seventy-two of this paper's ninety rows disperse particles in a culture medium, the setting where a protein corona forms around whatever material or functionalisation the particle started with. |
| 07 | incubation-not-measurement-temperature | PMC4958399 | 25/37 C incubation is not the measurement T | None of this paper's fifteen rows reports the temperature the zeta potential was actually measured at, even though the text says particles were incubated with plasma or serum proteins at 25 C and again at 37 C. |
| 08 | room-temperature | PMC13520334 | "room temperature" counts as reported, flagged nominal | Thirty rows in this paper give their temperature only as "room temperature", never as a number. |
| 09 | mobility-reported | PMC11117817 | the measured quantity; zeta computable per model | Sixteen of this paper's thirty-two rows report electrophoretic mobility directly, the quantity an instrument actually measures before any model converts it to a zeta potential. |
| 10 | size-regime | PMC10145996 | 50 nm vs 1 um PS-NH2: +24 vs -34 mV | Two rows, one particle chemistry -- amine-functionalised polystyrene -- in the same medium, and the only thing that changes is size: 50.7 nm carries a positive zeta potential, 955 nm carries a negative one. |
| 11 | environmental-matrix | PMC9318256 | effluent before/after treatment | Ten rows span five industrial effluents -- resin, paint, pharmaceutical, PVC and textile -- each sampled before and after in-house wastewater treatment, so the zeta potential belongs to whatever particles the effluent carried, in a matrix whose ionic strength and pH are never given. |
| 12 | weathered | PMC11543686 | aging changes charge and has no field | Twenty-eight of this paper's forty-two rows carry "aged", "UV" or "weather" somewhere in their functionalisation or particle name, because ageing changes surface charge and this dataset has no field to record it -- not a duration, not a UV dose, nothing. |
| 13 | self-contradiction | PMC12598813 | one salt concentration printed twice, ~1e3-1e4x apart | The Methods section states the salinity series as 5% to 30% weight-by-volume -- 50 to 300 g/L -- while the Results section states the same series as 0 to 30 mg/L, a difference of three to four orders of magnitude. |
| 14 | comparable-yet-apart | PMC13298883, PMC10260929 | comparable on all five conditions, yet 34 mV apart within one lab | Two papers from one laboratory (Bioelectrochemistry, University of Bialystok; every author of the 2026 paper also signs the 2023 one) measure nominally 100 nm plain polystyrene under the same printed conditions -- 0.3 mM NaCl, pH 7.4, 25 C, Zetasizer Nano-ZS -- and report -48.7 +/- 1.4 mV (Sigma-Aldrich 43302, 119.5 nm measured) and -14.7 +/- 0.29 mV (supplier not stated, 158.1 nm measured). |

## Not different, just unreported

Every pair of rows that describe the same particle: the same `quantity`, the same `material_key` (a row whose material is unreported describes no particle) and the same `functionalisation_key`. That is 166,965 pairs among 1,739 rows of 135 particles. `comparability.comparable` grades each one, and the rule in `METHOD.md` ("The same-particle census") puts it in exactly one category:

| category | pairs |
|---|---|
| comparable | 2 |
| conditionally comparable | 3 |
| lost only to absence | 29,075 |
| a stated difference | 137,718 |
| undecidable | 167 |
| all same-particle pairs | 166,965 |

**29,075** pairs of the same particle (17.4%) are blocked only by conditions a paper did not report: no stated value differs and nothing is undecidable. 27,657 of them cross a paper boundary; 1,418 sit inside one paper. **2** pairs are comparable. These are pairs of the same particle blocked only by unreported conditions -- not a claim about what those conditions were, and not a claim about what a default would make comparable. Reported, the conditions could still differ: the pair would become decidable, not necessarily comparable.

Which conditions are missing, ranked over those pairs. A pair usually misses several, so the first column adds up to more than the pairs; the second counts the pairs where the field is the only one missing, where one reported number would make the pair decidable:

| missing field | pairs missing it | pairs missing only it |
|---|---|---|
| `ionic_strength` | 28,984 | 26 |
| `pH` | 28,853 | 0 |
| `temperature` | 28,617 | 2 |
| `medium` | 27,801 | 0 |
| `size_measured_nm` | 24,505 | 25 |
| `functionalisation` | 23,943 | 0 |
| `instrument` | 21,665 | 0 |

23,943 of the pairs lost to absence leave the surface unstated on both rows. They are grouped as one particle only because nothing printed tells them apart; the unstated surface is itself one of their absences, so none of them can be comparable.

## Corpus-wide resampling (E2e, rebuilt)

| metric | per row | per paper | ICC | DEFF | n_eff | naive ± (row) | cluster ± (row) | cluster ± (paper) |
|---|---|---|---|---|---|---|---|---|
| medium_reported | 78.8% | 67.6% | 0.81 | 3.48 | 546 | 1.8 pp | 4.4 pp | 4.1 pp |
| ionic_strength_reported | 12.6% | 7.2% | 0.87 | 3.67 | 519 | 1.5 pp | 5.2 pp | 2.2 pp |
| pH_reported | 18.5% | 13.6% | 0.84 | 3.57 | 533 | 1.7 pp | 5.2 pp | 2.9 pp |
| temperature_reported | 23.0% | 19.0% | 0.86 | 3.62 | 525 | 1.9 pp | 6.3 pp | 3.5 pp |
| instrument_reported | 87.2% | 80.9% | 0.89 | 3.72 | 512 | 1.5 pp | 3.4 pp | 3.4 pp |
| conditions_complete | 2.4% | 1.6% | 0.79 | 3.43 | 555 | 0.7 pp | 1.9 pp | 1.0 pp |

## Conversion-model scan (E2b, rebuilt)

| quantity | papers | name a model | do not |
|---|---|---|---|
| zeta_potential | 462 | 32 | 430 |
| electrophoretic_mobility | 15 | 6 | 9 |

## Reader results

Cell D is handed the matching structured rows for each question, so a high score there is the expected outcome, not a finding on its own -- what the grid actually measures is cell D's *difference* from cell B, which is given only BM25-retrieved lines and no table. Both cells answer the same 37 questions here: an illustration of the grid running on this demo's own cases, not a statistical estimate of either cell's accuracy.

cell D: 37 answered, 0 refused, 0 not answered
cell	kind	n	accuracy	fabrication	cite_p	cite_r	tokens	calls
D	A	12	1.000	0.000	1.000	1.000	1560	0.0
D	B	11	1.000	0.000	1.000	0.750	3979	0.0
D	E	14	1.000	-	-	-	713	0.0

cell B: 37 answered, 0 refused, 0 not answered
cell	kind	n	accuracy	fabrication	cite_p	cite_r	tokens	calls
B	A	12	0.917	0.000	0.917	0.617	5408	0.0
B	B	11	0.818	0.091	0.500	0.125	5957	0.0
B	E	14	0.857	-	-	-	6001	0.0

### Cell B fabrications

- [`X12-B`](cases/12-weathered.md): answered pH reported=true, value 4.2 -- the paper never reports pH on any row of this case

### Cell D wrong answers

(none recorded in this run)
