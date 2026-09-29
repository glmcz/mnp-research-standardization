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

The kind E query set (`queries/kind_e_comparability.csv`) is a **320-pair stratified sample**, not the full 1,785,105 possible pairs in the corpus. Share of pairs blocked on each field, side by side.

| field | this paper (of 1 pairs) | kind E sample (of 320 pairs) |
|---|---|---|
| conversion_model | 0.0% | 9.7% |
| functionalisation | 0.0% | 76.2% |
| instrument | 0.0% | 55.0% |
| ionic_strength | 100.0% | 84.1% |
| material | 0.0% | 23.1% |
| medium | 0.0% | 90.9% |
| pH | 100.0% | 76.2% |
| quantity | 0.0% | 5.6% |
| size_measured_nm | 0.0% | 36.2% |
| temperature | 100.0% | 66.2% |

## 5. Harmonised value

| row_id | reported | model | kappa_a | f(kappa_a) | harmonised | why |
|---|---|---|---|---|---|---|
| PMC10145996-r1 | 24.13 mV | not named | unknown | unknown | [16.1, 36.2] mV | no model named and kappa*a unreported: interval over the combined range of f_m / f(kappa*a), [1/1.5, 1.5] |
| PMC10145996-r2 | -33.97 mV | not named | unknown | unknown | [-51, -22.6] mV | no model named and kappa*a unreported: interval over the combined range of f_m / f(kappa*a), [1/1.5, 1.5] |

## 6. Resampling

- rows in this paper: 2
- weight per row (n / 1890): 0.00106
- weight per paper (1 / 491): 0.00204

| metric | per-row (with paper) | per-row (without) | per-paper (with) | per-paper (without) |
|---|---|---|---|---|
| medium_reported | 83.2% | 83.2% | 72.1% | 72.1% |
| ionic_strength_reported | 13.7% | 13.7% | 8.6% | 8.6% |
| pH_reported | 21.3% | 21.3% | 16.8% | 16.8% |
| temperature_reported | 25.6% | 25.6% | 20.3% | 20.3% |
| instrument_reported | 88.8% | 88.8% | 81.0% | 81.0% |
| conditions_complete | 3.2% | 3.2% | 2.1% | 2.1% |

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
- answer: `{"reported": false, "value": null, "citations": ["PMC10145996:L4"]}`
- score: correct=True, fabricated=False
- cited lines:
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
- answer: `{"verdict": "not_comparable", "blockers": ["size_measured_nm"], "citations": ["PMC10145996:L17", "PMC10145996:L18", "row:PMC10145996-r1", "row:PMC10145996-r2"]}`
- score: correct=True, blocker_precision=0.00, blocker_recall=0.00, blockers_exact=0.00
- cited lines:
  - PMC10145996:L17	"The physio-chemical properties of the 50 nm and 1 μm PS-NH2 MNPs are shown in Figure 1. TEM images (Figure 1A,C) revealed that PS-NH2 had a fairly spherical shape, and the size was close with the results obtained by DLS. Their sizes for the 50 nm and 1 μm PS-NH2 MNPs analyzed by DLS were 50.7 ± 0.8 and 955.0 ± 24.194 nm (Figure 1B,D), respectively. The zeta-potential values of 50 nm PS-NH2 and 1 μm PS-NH2 were +24.13 ± 0.660 and -33.97 ± 0.447 mV, respectively."
  - PMC10145996:L18	"Figure 1. TEM images (A,C) and DLS measurements (B,D) of PS-NH2 MNPs in ultrapure water. Dh, PDI, and ζ-potential represent hydrodynamic diameter (nm), polydispersity index (PDI), and zeta potential (mV), respectively."
  - PMC10145996:L4	"Non-fluorescently labelled PS-NH2 with diameters of 50 nm and 1 μm were characterized using dynamic light scattering (DLS) (Malvern Zetasizer Nano ZS90, Malvern Instruments Ltd., Malvern, UK) and a transmission electron microscope (TEM) (HT7800, Hitachi, Tokyo, Japan). The hydrodynamic diameter (Z-average), polydispersity index (PDI), and zeta potential were measured as key parameters describing PS-NH2 behavior in ultrapure water. Measurements were carried out in triplicate. The primary morphology and particle size of PS-NH2 were identified using TEM at 80 kV."
  - PMC10145996:L17	"The physio-chemical properties of the 50 nm and 1 μm PS-NH2 MNPs are shown in Figure 1. TEM images (Figure 1A,C) revealed that PS-NH2 had a fairly spherical shape, and the size was close with the results obtained by DLS. Their sizes for the 50 nm and 1 μm PS-NH2 MNPs analyzed by DLS were 50.7 ± 0.8 and 955.0 ± 24.194 nm (Figure 1B,D), respectively. The zeta-potential values of 50 nm PS-NH2 and 1 μm PS-NH2 were +24.13 ± 0.660 and -33.97 ± 0.447 mV, respectively."
  - PMC10145996:L4	"Non-fluorescently labelled PS-NH2 with diameters of 50 nm and 1 μm were characterized using dynamic light scattering (DLS) (Malvern Zetasizer Nano ZS90, Malvern Instruments Ltd., Malvern, UK) and a transmission electron microscope (TEM) (HT7800, Hitachi, Tokyo, Japan). The hydrodynamic diameter (Z-average), polydispersity index (PDI), and zeta potential were measured as key parameters describing PS-NH2 behavior in ultrapure water. Measurements were carried out in triplicate. The primary morphology and particle size of PS-NH2 were identified using TEM at 80 kV."
  - PMC10145996:L17	"The physio-chemical properties of the 50 nm and 1 μm PS-NH2 MNPs are shown in Figure 1. TEM images (Figure 1A,C) revealed that PS-NH2 had a fairly spherical shape, and the size was close with the results obtained by DLS. Their sizes for the 50 nm and 1 μm PS-NH2 MNPs analyzed by DLS were 50.7 ± 0.8 and 955.0 ± 24.194 nm (Figure 1B,D), respectively. The zeta-potential values of 50 nm PS-NH2 and 1 μm PS-NH2 were +24.13 ± 0.660 and -33.97 ± 0.447 mV, respectively."
