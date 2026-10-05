# Case 10 — size-regime


**mode:** 50 nm vs 1 um PS-NH2: +24 vs -34 mV


## 1. Why this case

Two rows, one particle chemistry -- amine-functionalised polystyrene -- in the same medium, and the only thing that changes is size: 50.7 nm carries a positive zeta potential, 955 nm carries a negative one. A roughly nineteen-fold change in size flips the sign of the surface charge, which is exactly the argument that a zeta value without its particle's size attached is not comparable to anything.

- pmcid: PMC10145996
- doi: 10.3390/toxics11040356
- year: 2023
- journal: Toxics

## 2. Rows

| row_id | particle | value | medium | ionic strength | pH | T | instrument |
|---|---|---|---|---|---|---|---|
| PMC10145996-r1 | polystyrene, amine | 24.1 ± 0.66 mV | ultrapure water | unreported | unreported | unreported | Malvern Zetasizer Nano ZS90 |
| PMC10145996-r2 | polystyrene, amine | -34 ± 0.447 mV | ultrapure water | unreported | unreported | unreported | Malvern Zetasizer Nano ZS90 |

**PMC10145996-r1** evidence:
- PMC10145996:L4: “Non-fluorescently labelled PS-NH2 with diameters of 50 nm and 1 μm were characterized using dynamic light scattering (DLS) (Malvern Zetasizer Nano ZS90, Malvern Instruments Ltd., Malvern, UK) and a transmission electron microscope (TEM) (HT7800, Hitachi, Tokyo, Japan). The hydrodynamic diameter (Z-average), polydispersity index (PDI), and zeta potential were measured as key parameters describing PS-NH2 behavior in ultrapure water. Measurements were carried out in triplicate. The primary morphology and particle size of PS-NH2 were identified using TEM at 80 kV.”
- PMC10145996:L17: “The physio-chemical properties of the 50 nm and 1 μm PS-NH2 MNPs are shown in Figure 1. TEM images (Figure 1A,C) revealed that PS-NH2 had a fairly spherical shape, and the size was close with the results obtained by DLS. Their sizes for the 50 nm and 1 μm PS-NH2 MNPs analyzed by DLS were 50.7 ± 0.8 and 955.0 ± 24.194 nm (Figure 1B,D), respectively. The zeta-potential values of 50 nm PS-NH2 and 1 μm PS-NH2 were +24.13 ± 0.660 and -33.97 ± 0.447 mV, respectively.”

**PMC10145996-r2** evidence:
- PMC10145996:L4: “Non-fluorescently labelled PS-NH2 with diameters of 50 nm and 1 μm were characterized using dynamic light scattering (DLS) (Malvern Zetasizer Nano ZS90, Malvern Instruments Ltd., Malvern, UK) and a transmission electron microscope (TEM) (HT7800, Hitachi, Tokyo, Japan). The hydrodynamic diameter (Z-average), polydispersity index (PDI), and zeta potential were measured as key parameters describing PS-NH2 behavior in ultrapure water. Measurements were carried out in triplicate. The primary morphology and particle size of PS-NH2 were identified using TEM at 80 kV.”
- PMC10145996:L17: “The physio-chemical properties of the 50 nm and 1 μm PS-NH2 MNPs are shown in Figure 1. TEM images (Figure 1A,C) revealed that PS-NH2 had a fairly spherical shape, and the size was close with the results obtained by DLS. Their sizes for the 50 nm and 1 μm PS-NH2 MNPs analyzed by DLS were 50.7 ± 0.8 and 955.0 ± 24.194 nm (Figure 1B,D), respectively. The zeta-potential values of 50 nm PS-NH2 and 1 μm PS-NH2 were +24.13 ± 0.660 and -33.97 ± 0.447 mV, respectively.”


## 3. Standardisation walk

| row_id | condition | verdict | reason | citations |
|---|---|---|---|---|
| PMC10145996-r1 | medium | reported | a liquid is named: "ultrapure water" | PMC10145996:L4, PMC10145996:L17 |
| PMC10145996-r1 | ionic_strength | unreported | the medium is named as pure/DI water ("ultrapure water"); DI water does not mean ionic strength zero — absence is never imputed | PMC10145996:L4, PMC10145996:L17 |
| PMC10145996-r1 | pH | unreported | no pH number or range is printed | PMC10145996:L4, PMC10145996:L17 |
| PMC10145996-r1 | temperature | unreported | no measurement temperature is printed; an incubation, exposure or storage temperature never counts as the measurement temperature, even when it is the only one the paper gives | PMC10145996:L4, PMC10145996:L17 |
| PMC10145996-r1 | instrument | reported | an instrument is named: "Malvern Zetasizer Nano ZS90" | PMC10145996:L4, PMC10145996:L17 |
| PMC10145996-r2 | medium | reported | a liquid is named: "ultrapure water" | PMC10145996:L4, PMC10145996:L17 |
| PMC10145996-r2 | ionic_strength | unreported | the medium is named as pure/DI water ("ultrapure water"); DI water does not mean ionic strength zero — absence is never imputed | PMC10145996:L4, PMC10145996:L17 |
| PMC10145996-r2 | pH | unreported | no pH number or range is printed | PMC10145996:L4, PMC10145996:L17 |
| PMC10145996-r2 | temperature | unreported | no measurement temperature is printed; an incubation, exposure or storage temperature never counts as the measurement temperature, even when it is the only one the paper gives | PMC10145996:L4, PMC10145996:L17 |
| PMC10145996-r2 | instrument | reported | an instrument is named: "Malvern Zetasizer Nano ZS90" | PMC10145996:L4, PMC10145996:L17 |

## 4. Comparability

### Pairs inside this paper

| row_id_a | row_id_b | verdict | blockers |
|---|---|---|---|
| PMC10145996-r1 | PMC10145996-r2 | not_comparable | ionic_strength_unreported;pH_unreported;temperature_unreported |

### Each row against the whole corpus

How many corpus rows (in any paper) this row is `comparable` or `conditionally_comparable` with, from the exhaustive corpus-wide census.

| row_id | comparable_with | conditionally_comparable_with |
|---|---|---|
| PMC10145996-r1 | 0 | 0 |
| PMC10145996-r2 | 0 | 0 |

### Blocker fields: this paper versus the kind E query set

The kind E query set (`queries/kind_e_comparability.csv`) is a **274-pair stratified sample**, not the full 1,809,753 possible pairs in the corpus. Share of pairs blocked on each field, side by side.

| field | this paper (of 1 pairs) | kind E sample (of 274 pairs) |
|---|---|---|
| conversion_model | 0.0% | 3.3% |
| functionalisation | 0.0% | 86.5% |
| instrument | 0.0% | 54.7% |
| ionic_strength | 100.0% | 94.5% |
| material | 0.0% | 23.7% |
| medium | 0.0% | 92.0% |
| pH | 100.0% | 86.9% |
| quantity | 0.0% | 5.1% |
| size_measured_nm | 0.0% | 74.8% |
| temperature | 100.0% | 78.8% |

## 5. Harmonised value

| row_id | reported | model | kappa_a | f(kappa_a) | harmonised | why |
|---|---|---|---|---|---|---|
| PMC10145996-r1 | 24.13 mV | not named | unknown | unknown | [16.1, 36.2] mV | no model named and kappa*a unreported: interval over the combined range of f_m / f(kappa*a), [1/1.5, 1.5] |
| PMC10145996-r2 | -33.97 mV | not named | unknown | unknown | [-51, -22.6] mV | no model named and kappa*a unreported: interval over the combined range of f_m / f(kappa*a), [1/1.5, 1.5] |

## 6. Resampling

- rows in this paper: 2
- weight per row (n / 1903): 0.00105
- weight per paper (1 / 467): 0.00214

| metric | per-row (with paper) | per-row (without) | per-paper (with) | per-paper (without) |
|---|---|---|---|---|
| medium_reported | 78.8% | 78.8% | 67.6% | 67.5% |
| ionic_strength_reported | 12.6% | 12.6% | 7.2% | 7.2% |
| pH_reported | 18.5% | 18.5% | 13.6% | 13.6% |
| temperature_reported | 23.0% | 23.0% | 19.0% | 19.0% |
| instrument_reported | 87.2% | 87.2% | 80.9% | 80.9% |
| conditions_complete | 2.4% | 2.4% | 1.6% | 1.6% |

## 7. Reader

### X10-A

In PMC10145996, what zeta potential was reported for polystyrene, amine particles described as "50 nm PS-NH2" in ultrapure water, and at what ionic strength was that measurement made?

**cell D**
- answer: `{"value": 24.13, "unit": "mV", "ionic_strength_reported": false, "ionic_strength_mM": null, "citations": ["row:PMC10145996-r1"]}`
- score: correct=True, fabricated=False, citation_precision=1.00, citation_recall=1.00, value_correct=1.00, condition_correct=1.00
- cited lines:
  - PMC10145996:L4	"Non-fluorescently labelled PS-NH2 with diameters of 50 nm and 1 μm were characterized using dynamic light scattering (DLS) (Malvern Zetasizer Nano ZS90, Malvern Instruments Ltd., Malvern, UK) and a transmission electron microscope (TEM) (HT7800, Hitachi, Tokyo, Japan). The hydrodynamic diameter (Z-average), polydispersity index (PDI), and zeta potential were measured as key parameters describing PS-NH2 behavior in ultrapure water. Measurements were carried out in triplicate. The primary morphology and particle size of PS-NH2 were identified using TEM at 80 kV."
  - PMC10145996:L17	"The physio-chemical properties of the 50 nm and 1 μm PS-NH2 MNPs are shown in Figure 1. TEM images (Figure 1A,C) revealed that PS-NH2 had a fairly spherical shape, and the size was close with the results obtained by DLS. Their sizes for the 50 nm and 1 μm PS-NH2 MNPs analyzed by DLS were 50.7 ± 0.8 and 955.0 ± 24.194 nm (Figure 1B,D), respectively. The zeta-potential values of 50 nm PS-NH2 and 1 μm PS-NH2 were +24.13 ± 0.660 and -33.97 ± 0.447 mV, respectively."

**cell B**
- answer: `{"value": 24.13, "unit": "mV", "ionic_strength_reported": false, "ionic_strength_mM": null, "citations": ["PMC10145996:L17", "PMC10145996:L4"]}`
- score: correct=True, fabricated=False, citation_precision=1.00, citation_recall=1.00, value_correct=1.00, condition_correct=1.00
- cited lines:
  - PMC10145996:L17	"The physio-chemical properties of the 50 nm and 1 μm PS-NH2 MNPs are shown in Figure 1. TEM images (Figure 1A,C) revealed that PS-NH2 had a fairly spherical shape, and the size was close with the results obtained by DLS. Their sizes for the 50 nm and 1 μm PS-NH2 MNPs analyzed by DLS were 50.7 ± 0.8 and 955.0 ± 24.194 nm (Figure 1B,D), respectively. The zeta-potential values of 50 nm PS-NH2 and 1 μm PS-NH2 were +24.13 ± 0.660 and -33.97 ± 0.447 mV, respectively."
  - PMC10145996:L4	"Non-fluorescently labelled PS-NH2 with diameters of 50 nm and 1 μm were characterized using dynamic light scattering (DLS) (Malvern Zetasizer Nano ZS90, Malvern Instruments Ltd., Malvern, UK) and a transmission electron microscope (TEM) (HT7800, Hitachi, Tokyo, Japan). The hydrodynamic diameter (Z-average), polydispersity index (PDI), and zeta potential were measured as key parameters describing PS-NH2 behavior in ultrapure water. Measurements were carried out in triplicate. The primary morphology and particle size of PS-NH2 were identified using TEM at 80 kV."

### X10-B

What ionic strength was used for the zeta-potential and electrophoretic-mobility measurements reported in PMC10145996?

**cell D**
- answer: `{"reported": false, "value": null, "citations": ["row:PMC10145996-r1", "row:PMC10145996-r2"]}`
- score: correct=True, fabricated=False
- cited lines:
  - PMC10145996:L4	"Non-fluorescently labelled PS-NH2 with diameters of 50 nm and 1 μm were characterized using dynamic light scattering (DLS) (Malvern Zetasizer Nano ZS90, Malvern Instruments Ltd., Malvern, UK) and a transmission electron microscope (TEM) (HT7800, Hitachi, Tokyo, Japan). The hydrodynamic diameter (Z-average), polydispersity index (PDI), and zeta potential were measured as key parameters describing PS-NH2 behavior in ultrapure water. Measurements were carried out in triplicate. The primary morphology and particle size of PS-NH2 were identified using TEM at 80 kV."
  - PMC10145996:L17	"The physio-chemical properties of the 50 nm and 1 μm PS-NH2 MNPs are shown in Figure 1. TEM images (Figure 1A,C) revealed that PS-NH2 had a fairly spherical shape, and the size was close with the results obtained by DLS. Their sizes for the 50 nm and 1 μm PS-NH2 MNPs analyzed by DLS were 50.7 ± 0.8 and 955.0 ± 24.194 nm (Figure 1B,D), respectively. The zeta-potential values of 50 nm PS-NH2 and 1 μm PS-NH2 were +24.13 ± 0.660 and -33.97 ± 0.447 mV, respectively."
  - PMC10145996:L4	"Non-fluorescently labelled PS-NH2 with diameters of 50 nm and 1 μm were characterized using dynamic light scattering (DLS) (Malvern Zetasizer Nano ZS90, Malvern Instruments Ltd., Malvern, UK) and a transmission electron microscope (TEM) (HT7800, Hitachi, Tokyo, Japan). The hydrodynamic diameter (Z-average), polydispersity index (PDI), and zeta potential were measured as key parameters describing PS-NH2 behavior in ultrapure water. Measurements were carried out in triplicate. The primary morphology and particle size of PS-NH2 were identified using TEM at 80 kV."
  - PMC10145996:L17	"The physio-chemical properties of the 50 nm and 1 μm PS-NH2 MNPs are shown in Figure 1. TEM images (Figure 1A,C) revealed that PS-NH2 had a fairly spherical shape, and the size was close with the results obtained by DLS. Their sizes for the 50 nm and 1 μm PS-NH2 MNPs analyzed by DLS were 50.7 ± 0.8 and 955.0 ± 24.194 nm (Figure 1B,D), respectively. The zeta-potential values of 50 nm PS-NH2 and 1 μm PS-NH2 were +24.13 ± 0.660 and -33.97 ± 0.447 mV, respectively."

**cell B**
- answer: `{"reported": false, "value": null, "citations": ["PMC10145996:L4", "PMC10145996:L17"]}`
- score: correct=True, fabricated=False
- cited lines:
  - PMC10145996:L17	"The physio-chemical properties of the 50 nm and 1 μm PS-NH2 MNPs are shown in Figure 1. TEM images (Figure 1A,C) revealed that PS-NH2 had a fairly spherical shape, and the size was close with the results obtained by DLS. Their sizes for the 50 nm and 1 μm PS-NH2 MNPs analyzed by DLS were 50.7 ± 0.8 and 955.0 ± 24.194 nm (Figure 1B,D), respectively. The zeta-potential values of 50 nm PS-NH2 and 1 μm PS-NH2 were +24.13 ± 0.660 and -33.97 ± 0.447 mV, respectively."
  - PMC10145996:L4	"Non-fluorescently labelled PS-NH2 with diameters of 50 nm and 1 μm were characterized using dynamic light scattering (DLS) (Malvern Zetasizer Nano ZS90, Malvern Instruments Ltd., Malvern, UK) and a transmission electron microscope (TEM) (HT7800, Hitachi, Tokyo, Japan). The hydrodynamic diameter (Z-average), polydispersity index (PDI), and zeta potential were measured as key parameters describing PS-NH2 behavior in ultrapure water. Measurements were carried out in triplicate. The primary morphology and particle size of PS-NH2 were identified using TEM at 80 kV."

### X10-E

May the zeta_potential reported in PMC10145996 (row PMC10145996-r1) be compared with the zeta_potential reported in PMC10145996 (row PMC10145996-r2)? If not, which fields block the comparison?

**cell D**
- answer: `{"verdict": "not_comparable", "blockers": ["ionic_strength", "pH", "temperature"], "citations": ["row:PMC10145996-r1", "row:PMC10145996-r2"]}`
- score: correct=True, blocker_precision=1.00, blocker_recall=1.00, blockers_exact=1.00
- cited lines:
  - PMC10145996:L4	"Non-fluorescently labelled PS-NH2 with diameters of 50 nm and 1 μm were characterized using dynamic light scattering (DLS) (Malvern Zetasizer Nano ZS90, Malvern Instruments Ltd., Malvern, UK) and a transmission electron microscope (TEM) (HT7800, Hitachi, Tokyo, Japan). The hydrodynamic diameter (Z-average), polydispersity index (PDI), and zeta potential were measured as key parameters describing PS-NH2 behavior in ultrapure water. Measurements were carried out in triplicate. The primary morphology and particle size of PS-NH2 were identified using TEM at 80 kV."
  - PMC10145996:L17	"The physio-chemical properties of the 50 nm and 1 μm PS-NH2 MNPs are shown in Figure 1. TEM images (Figure 1A,C) revealed that PS-NH2 had a fairly spherical shape, and the size was close with the results obtained by DLS. Their sizes for the 50 nm and 1 μm PS-NH2 MNPs analyzed by DLS were 50.7 ± 0.8 and 955.0 ± 24.194 nm (Figure 1B,D), respectively. The zeta-potential values of 50 nm PS-NH2 and 1 μm PS-NH2 were +24.13 ± 0.660 and -33.97 ± 0.447 mV, respectively."
  - PMC10145996:L4	"Non-fluorescently labelled PS-NH2 with diameters of 50 nm and 1 μm were characterized using dynamic light scattering (DLS) (Malvern Zetasizer Nano ZS90, Malvern Instruments Ltd., Malvern, UK) and a transmission electron microscope (TEM) (HT7800, Hitachi, Tokyo, Japan). The hydrodynamic diameter (Z-average), polydispersity index (PDI), and zeta potential were measured as key parameters describing PS-NH2 behavior in ultrapure water. Measurements were carried out in triplicate. The primary morphology and particle size of PS-NH2 were identified using TEM at 80 kV."
  - PMC10145996:L17	"The physio-chemical properties of the 50 nm and 1 μm PS-NH2 MNPs are shown in Figure 1. TEM images (Figure 1A,C) revealed that PS-NH2 had a fairly spherical shape, and the size was close with the results obtained by DLS. Their sizes for the 50 nm and 1 μm PS-NH2 MNPs analyzed by DLS were 50.7 ± 0.8 and 955.0 ± 24.194 nm (Figure 1B,D), respectively. The zeta-potential values of 50 nm PS-NH2 and 1 μm PS-NH2 were +24.13 ± 0.660 and -33.97 ± 0.447 mV, respectively."

**cell B**
- answer: `{"verdict": "not_comparable", "blockers": ["size_measured_nm"], "citations": ["PMC10145996:L17", "PMC10145996:L4"]}`
- score: correct=True, blocker_precision=0.00, blocker_recall=0.00, blockers_exact=0.00
- cited lines:
  - PMC10145996:L17	"The physio-chemical properties of the 50 nm and 1 μm PS-NH2 MNPs are shown in Figure 1. TEM images (Figure 1A,C) revealed that PS-NH2 had a fairly spherical shape, and the size was close with the results obtained by DLS. Their sizes for the 50 nm and 1 μm PS-NH2 MNPs analyzed by DLS were 50.7 ± 0.8 and 955.0 ± 24.194 nm (Figure 1B,D), respectively. The zeta-potential values of 50 nm PS-NH2 and 1 μm PS-NH2 were +24.13 ± 0.660 and -33.97 ± 0.447 mV, respectively."
  - PMC10145996:L4	"Non-fluorescently labelled PS-NH2 with diameters of 50 nm and 1 μm were characterized using dynamic light scattering (DLS) (Malvern Zetasizer Nano ZS90, Malvern Instruments Ltd., Malvern, UK) and a transmission electron microscope (TEM) (HT7800, Hitachi, Tokyo, Japan). The hydrodynamic diameter (Z-average), polydispersity index (PDI), and zeta potential were measured as key parameters describing PS-NH2 behavior in ultrapure water. Measurements were carried out in triplicate. The primary morphology and particle size of PS-NH2 were identified using TEM at 80 kV."
