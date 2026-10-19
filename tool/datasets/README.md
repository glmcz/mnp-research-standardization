# Dataset recon, 2026-10-13

Where more data could come from, asked after P2 (`tool/p2/`) showed thin polymers: nylon 25
values from 3 papers, PBAT 11 from 3. The scripts are as an agent wrote them, kept so the
counts can be re-run. Downloads are in `data/raw/datasets_recon/` (gitignored).

## Zeta (`zeta_recon_2026-10-13/`)

- **ToMEx 2.0 does have zeta** (`zetapotential.mV`, `zetapotential.media`). This corrects
  `docs/2026-09-07-charge-thesis-reserse.md`, which says it was absent. The files are the
  GitHub `.RDS` in SCCWRP/ToMEx_AquaticOrganisms and SCCWRP/ToMEx_HumanHealth. They hold mostly
  polystyrene, and only about 4 new values for the thin polymers.
- **eNanoMapper**: 1 polystyrene value. **Zenodo and figshare**: no compiled MNP zeta dataset.
  **Yang 2026**: ranges only, no data released.
- **Inside the corpus:** about 23 values have their size only as a bin in `particle_name`
  (for example "PA 1–5 μm"), so P2 drops them. About 31 thin-polymer rows point at an SI table
  or a main-text figure.
- **New since the 2026-09-11 snapshot:** 26 open-access PMCIDs match the corpus query plus the
  thin-polymer terms. 22 of them were published from 2026-08-25 on.
- **PDF route** (OpenAlex): 98 open-access DOIs for nylon, PVC, PLA, PBAT, PU, tyre and PC that
  are not among the 1 115 hits. About half are Elsevier. This is a lower evidence tier than
  JATS.

## Concentrations (`conc_recon_2026-10-13/`)

Profiled from downloaded files. The sha256 of every file is in
`data/raw/datasets_recon/conc/SHA256SUMS`.

| dataset | what | why |
|---|---|---|
| Soil MP 2005–2026 (Wu et al., Zenodo 20806151, CC BY 4.0) | 6 197 rows from 297 studies, all with coordinates, year, min and max particle size, items/kg | 201 grid cells of 0.1° contain two or more studies |
| MPsizeBase v19-5-2026 (CNRS, Zenodo 20832480, CC BY 4.0) | 203 measured particle size distributions (atmosphere 104, ocean 99), per-bin bounds | tests the α = 1.6 that D3's rescaling assumes |
| PANGAEA 937685 + 938143 (Weser estuary, CC BY 4.0) | one study, 23 stations, two complementary size fractions: S-MP 11–500 µm (pump, µFTIR) and L-MP 500–5000 µm (net, ATR-FTIR). *Corrected 2026-10-19: the recon called them "a 10 µm filter vs a 300 µm net"* | small outnumber large by a median of 5 237 over 22 stations (one found no large particles), which implies α ≈ 3.24 against the assumed 1.6. The recon's 5 340 counted that station's infinite ratio |
| DURUM stormwater (OSF 9cgu4) | 180 rows from 28 DOIs, size bounds, coordinates | small, urban runoff |

**Rejected:**

- **AOMI:** the open REST layer overlaps NCEI by about 84 %, and the processed levels sit behind
  a form.
- **Eriksen 2023:** mostly SEA data that NCEI already holds, no DOI per row.
- **MP-GERE:** extracted by a model (GLM-5.3); a review repeats a primary study's values, so they
  are counted twice. Use it for leads only.
