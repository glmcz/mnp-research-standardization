# The demo: thirteen real cases, each re-sampled four ways

See `docs/DESIGN_2026-09-28_demo.md` for what this shows and `METHOD.md` for how every number below is computed. One page per case is in `cases/`.

## Cases

| nn | slug | pmcid | mode | result |
|---|---|---|---|---|
| 01 | fully-conditioned | PMC11099890 | the rare success | This paper's rows are among the rare ones the comparability key can place in the same regime: twelve of the sixteen fully comparable pairs in the entire 1,890-row corpus come from inside this single paper (`comparability.comparable_census`). |
| 02 | one-particle-three-media | PMC10141840 | medium alone moves zeta 54 mV | One 1.14 micron polystyrene particle, one pH, one temperature, one instrument -- the only thing that changes across these three rows is the medium, and the zeta potential swings from about -68 mV in water to about -14 mV in a culture medium. |
| 03 | conductivity-not-ionic-strength | PMC12673110 | a number printed, not the one needed | Two aqueous media here are named by their conductivity rather than by a stated ionic strength: tap water at 230 uS/cm, a NaCl solution at 4,000 uS/cm. |
| 04 | derived-from-composition | PMC12312160 | ionic strength derived from a printed composition, never looked up | Every zeta row here states its dispersion as 10 mM HEPES plus either 1 mM or 100 mM NaCl -- a printed composition, not a number copied from a lookup table. |
| 05 | buffer-named-only | PMC6981174 | "PBS" alone is not an ionic strength | All seven rows disperse the particle in some form of PBS, one of the best-known buffers in the field, which is exactly why it is dangerous here. |
| 06 | biological-medium | PMC8719689 | corona: different particles converge | Seventy-two of this paper's ninety rows disperse particles in a culture medium, the setting where a protein corona forms around whatever material or functionalisation the particle started with. |
| 07 | incubation-not-measurement-temperature | PMC4958399 | 25/37 C incubation is not the measurement T | None of this paper's fifteen rows reports the temperature the zeta potential was actually measured at, even though the text says particles were incubated with plasma or serum proteins at 25 C and again at 37 C. |
| 08 | room-temperature | PMC13520334 | "room temperature" counts as reported, flagged nominal | Thirty rows in this paper give their temperature only as "room temperature", never as a number. |
| 09 | mobility-reported | PMC11117817 | the measured quantity; zeta computable per model | Sixteen of this paper's thirty-two rows report electrophoretic mobility directly, the quantity an instrument actually measures before any model converts it to a zeta potential. |
| 10 | size-regime | PMC10145996 | 50 nm vs 1 um PS-NH2: +24 vs -34 mV | Two rows, one particle chemistry -- amine-functionalised polystyrene -- in the same medium, and the only thing that changes is size: 50.7 nm carries a positive zeta potential, 955 nm carries a negative one. |
| 11 | environmental-matrix | PMC9318256 | effluent before/after treatment | Ten rows span five industrial effluents -- resin, paint, pharmaceutical, PVC and textile -- each measured before and after in-house wastewater treatment. |
| 12 | weathered | PMC11543686 | aging changes charge and has no field | Twenty-eight of this paper's forty-two rows carry "aged", "UV" or "weather" somewhere in their functionalisation or particle name, because ageing changes surface charge and this dataset has no field to record it -- not a duration, not a UV dose, nothing. |
| 13 | self-contradiction | PMC12598813 | one salt concentration printed twice, ~1e3-1e4x apart | The Methods section states the salinity series as 5% to 30% weight-by-volume -- 50 to 300 g/L -- while the Results section states the same series as 0 to 30 mg/L, a difference of three to four orders of magnitude. |

## Corpus-wide resampling (E2e, rebuilt)

| metric | per row | per paper | ICC | DEFF | n_eff | naive ± (row) | cluster ± (row) | cluster ± (paper) |
|---|---|---|---|---|---|---|---|---|
| medium_reported | 83.2% | 72.1% | 0.84 | 3.38 | 560 | 1.7 pp | 3.8 pp | 3.8 pp |
| ionic_strength_reported | 14.2% | 8.7% | 0.82 | 3.33 | 567 | 1.6 pp | 5.6 pp | 2.3 pp |
| pH_reported | 21.3% | 16.8% | 0.78 | 3.22 | 588 | 1.8 pp | 5.3 pp | 3.1 pp |
| temperature_reported | 28.0% | 20.9% | 0.94 | 3.66 | 517 | 2.0 pp | 8.7 pp | 3.4 pp |
| instrument_reported | 88.8% | 81.0% | 0.94 | 3.66 | 517 | 1.4 pp | 2.9 pp | 3.4 pp |
| conditions_complete | 3.3% | 2.3% | 0.80 | 3.27 | 577 | 0.8 pp | 2.3 pp | 1.3 pp |

## Conversion-model scan (E2b, rebuilt)

| quantity | papers | name a model | do not |
|---|---|---|---|
| zeta_potential | 485 | 33 | 452 |
| electrophoretic_mobility | 13 | 6 | 7 |

## Reader results

Cell D is handed the matching structured rows for each question, so a high score there is the expected outcome, not a finding on its own -- what the grid actually measures is cell D's *difference* from cell B, which is given only BM25-retrieved lines and no table. Both cells answer the same 36 questions here: an illustration of the grid running on this demo's own cases, not a statistical estimate of either cell's accuracy.

cell D: 36 answered, 0 refused, 0 not answered
cell	kind	n	accuracy	fabrication	cite_p	cite_r	tokens	calls
D	A	12	1.000	0.000	1.000	1.000	2252	0.0
D	B	11	1.000	0.000	1.000	1.000	4204	0.0
D	E	13	0.923	-	-	-	723	0.0

cell B: 36 answered, 0 refused, 0 not answered
cell	kind	n	accuracy	fabrication	cite_p	cite_r	tokens	calls
B	A	12	0.833	0.000	0.778	0.646	5788	0.0
B	B	11	0.818	0.182	1.000	0.071	5759	0.0
B	E	13	0.846	-	-	-	5974	0.0

### Cell B fabrications

- [`X03-B`](cases/03-conductivity-not-ionic-strength.md): answered ionic_strength reported=true, value None -- the paper never reports ionic_strength on any row of this case
- [`X07-B`](cases/07-incubation-not-measurement-temperature.md): answered temperature reported=true, value [25, 37] -- the paper never reports temperature on any row of this case

### Cell D wrong answers

- [`X01-E`](cases/01-fully-conditioned.md): answered conditionally_comparable (blockers: size_measured_nm) -- gold is comparable (blockers: none)
