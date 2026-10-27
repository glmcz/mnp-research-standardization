# Reading list for the talk: what to know cold, and what to re-read

Written on 2026-10-26 from an independent review of the deck (a reviewer agent reading the slides
as a colloid and monitoring researcher who also builds agents). "Checked" means the reference was
found on PubMed on 2026-10-26 (PMID given); "not checked" means it is a standard reference the
reviewer named but that was not looked up here, so verify it before quoting it.

## Already in the talk material

| What | Where it is used |
|---|---|
| Henry's function: f(κa) from 1.0 (Hückel) to 1.5 (Smoluchowski), so ±20 % without ionic strength and ±38 % when the conversion model is unknown too; κ⁻¹ = 0.304/√I nm for a 1:1 electrolyte at 25 °C | slides on zeta and absence (backup) |
| Hard against soft particles; why a curve cannot be pieced together from different papers' dots | backup curve slide, the review call |
| Missing not at random; confounding by composition (a Simpson-like effect); sign test; exact McNemar; Spearman ρ; power-law slope α; IQR; coverage factor k = 2 | throughout |
| De Frond et al. 2022, Chemosphere 298:134282 (good recovery and identification above 50 µm only) | slide 3 |
| Koelmans et al. 2020, Environ Sci Technol 54:12307 (rescaling to one size window) | slides 3, 15 |
| Cowger et al. 2020, Appl Spectrosc 74:1066; Koelmans et al. 2019, Water Res 155:410 | slide 3 |
| Duncan et al. 2024, Anal Chem 96:4343; Gigault et al. 2018, Environ Pollut 235:1030; Faria et al. 2018, Nat Nanotechnol 13:777 | slides 3, 24 and the Q&A |
| Shen et al. 2019, Environ Pollut 252; Xu et al. 2022, Sci Total Environ 851 | slide 4 |
| Reisser 2013 and Eriksen 2014: the shared tows, and the net depth NOAA's values imply (0.085 m, held in no field) against the paper's 0.17 m | slides 14, 38 |
| Case 14 and case 02 numbers; the certified silica and the eight-laboratory silica study behind the gap ladder (`out/tables/gap_scout_verified.csv`) | slides 22, 23 |

## Background to re-read (not in the material)

**Electrokinetics, and what to report for zeta (read these two first: they already say what a
zeta measurement must report, so expect "what is new?")**
- Delgado AV, González-Caballero F, Hunter RJ, Koopal LK, Lyklema J (2007). Measurement and
  interpretation of electrokinetic phenomena (IUPAC). J Colloid Interface Sci 309:194–224.
  Checked, PMID 17368660.
- Lowry GV, Hill RJ, Harper S, et al. (2016). Guidance to improve the scientific value of
  zeta-potential measurements in nanoEHS. Environ Sci: Nano 3:953–965. Not checked.
- Doane TL, Chuang C-H, Hill RJ, Burda C (2012). Nanoparticle ζ-potentials. Acc Chem Res
  45:317–326. Checked, PMID 22074988.
- Bhattacharjee S (2016). DLS and zeta potential: what they are and what they are not? J Control
  Release 235:337–351. Checked, PMID 27297779.
- Henry DC (1931), Proc R Soc Lond A 133:106 (the conversion); O'Brien RW, White LR (1978),
  J Chem Soc Faraday Trans 2 74:1607 (relaxation at high zeta, which Henry ignores); Ohshima H
  (1995), Adv Colloid Interface Sci 62:189 (soft particles); Hunter RJ (1981), Zeta Potential in
  Colloid Science. Not checked.
- Monopoli MP, Åberg C, Salvati A, Dawson KA (2012). Biomolecular coronas provide the biological
  identity of nanosized materials. Nat Nanotechnol 7:779–786. Checked, PMID 23212421.

**Nanoplastics: definitions, behaviour**
- Gigault J, et al. (2021). Nanoplastics are neither microplastics nor engineered nanoparticles.
  Nat Nanotechnol 16:501–507. Checked, PMID 33927364.
- Alimi OS, Farner Budarz J, Hernandez LM, Tufenkji N (2018). Microplastics and nanoplastics in
  aquatic environments: aggregation, deposition, and enhanced contaminant transport. Environ Sci
  Technol 52:1704–1724. Checked, PMID 29265806. This is the "behaviour" the abstract promises.
- Hartmann NB, et al. (2019). Are we speaking the same language? Recommendations for a definition
  and categorization framework for plastic debris. Environ Sci Technol 53:1039–1047. Checked,
  PMID 30608663.
- Mitrano DM, Wick P, Nowack B (2021), Nat Nanotechnol 16:491. Not checked.

**Counts, windows and the ocean series**
- Kooi M, Primpke S, Mintenig SM, Lorenz C, Gerdts G, Koelmans AA (2021). Characterizing the
  multidimensionality of microplastics across environmental compartments. Water Res 202:117429.
  Checked, PMID 34304075. Power-law slopes are compartment-specific: median 2.2 in marine surface
  water up to 3.1 in biota. The answer to "did you use compartment-specific α?": the
  pre-registered test used the single slope the rescaling literature defaults to.
- Law KL, et al. (2010). Plastic accumulation in the North Atlantic subtropical gyre. Science
  329:1185–1188. Checked, PMID 20724586 (no trend over 22 years).
- Law KL, et al. (2014). Distribution of surface plastic debris in the eastern Pacific Ocean from
  an 11-year data set. Environ Sci Technol 48:4732–4738. Checked, PMID 24708264. The authors were
  "unable to detect a robust temporal trend … perhaps because of confounded spatial and temporal
  variability": the same reading as slide 12's "part of its rise is where the ship sailed".
- Goldstein MC, Rosenberg M, Cheng L (2012). Increased oceanic microplastic debris enhances
  oviposition in an endemic pelagic insect. Biol Lett 8:817–820. Checked, PMID 22573831: "increased
  by two orders of magnitude in the past four decades" in the North Pacific gyre. NOAA's series
  in slide 12 is listed under a Goldstein et al. 2013 DOI; know which is which.
- Kukulka T, et al. (2012), Geophys Res Lett 39:L07601 (wind mixing); Isobe A, et al. (2021),
  Microplastics and Nanoplastics 1:16 (the compilation AOMI now holds). Not checked.

**Agents, evaluation, data**
- Dagdelen J, et al. (2024). Structured information extraction from scientific text with large
  language models. Nat Commun 15:1418. Checked, PMID 38360817.
- Rubin DB (1976), Inference and missing data, Biometrika 63:581 (missing not at random);
  Zheng L, et al. (2023), Judging LLM-as-a-judge (NeurIPS Datasets and Benchmarks); Amodei D,
  et al. (2016), Concrete problems in AI safety, arXiv:1606.06565 (reward hacking: slide 8);
  Wilkinson MD, et al. (2016), FAIR principles, Sci Data 3:160018. Not checked.

## Prepare before the talk (questions the material cannot answer yet)

- The zeta tolerances behind slide 21's "two pairs comparable" (pH, temperature, ionic strength).
  They apply to zeta rows only. No tolerance touches the tows: the net-depth gap below is a
  metadata question.
- What the printed zeta values the scanner found but no row covers are: cited values, model
  inputs or real misses.
- The total cost of the extraction, not only the evaluation runs.
- NOAA, as a metadata question and not a tolerance: no NCEI field holds the 0.085 m its Reisser
  Manta values imply. `Water Sample Depth (m)` is 0; the submission sheet NCEI keyed from the paper
  holds only the result; the ISO record calls it "measured". Reisser's Methods give a 1 × 0.17 m
  mouth, 333 µm mesh, and d = 0.17 m, "full immersion of the net frame". The survey uses 0.17 m in
  NCEI and in AOMI (`tool/survey/table.py`, `NET_DEPTH`) until a record defines 0.085 m. Ask
  which field holds it and what it means, and why the same tows under Eriksen 2014 are all
  "Neuston net", 0.33 mm, implying 0.08 m. Evidence: `tool/colocation/reisser_eriksen/README.md`.
- A public timestamp for the pre-registration (Zenodo or OSF): a private repository's commits
  cannot show they came first.
- Whether "on request" stands for the code (OD-20), and one sentence on affiliation and funding.
