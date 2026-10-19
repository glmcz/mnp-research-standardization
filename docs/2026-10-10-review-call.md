# Review call, 2026-10-10: deck and abstract, plus brainstorming

Martin walked a reviewer (a chemist, unnamed here) through the deck "Reading What Isn't
There" (v3, 18 slides) and the GRC abstract (`docs/Martin - From Detection to Predicting
Micro.md`). Recorded on Martin's phone, in Czech.

| source | length | local only (gitignored) |
|---|---|---|
| `out/review/IMG_1055.MOV` | 4 min, 17:20 | `out/review/IMG_1055.transcript.cs.txt` |
| `out/review/IMG_1056.MOV` | 38 min, 17:25 | `out/review/IMG_1056.transcript.cs.txt` |

The videos and the raw transcripts stay out of git: they hold the reviewer's voice, and
the frames show a private chat. This file is the summary to read and commit.

**Transcription.** Whisper large-v3, Czech, unedited, with no speaker labels. The
Whisper-small version of each file is kept as `*.transcript.small.cs.txt`; it wrote "9,7 %"
where large-v3 and Martin both have 99.7 %. Check any number below against a committed file
before using it, not against the transcript.

## What was said, in order

Timestamps are `[mm:ss]` into each recording.

### IMG_1055: the opening

1. **[00:08–01:41] Add an introduction for the AI audience.** Say what zeta potential is
   and how it is measured: show the instrument. Computer scientists will not know it and
   chemists already do, so keep it shallow. Say why it matters for plastics: surface
   charge shapes how particles behave in the environment and in the body, how biologically
   active they are, and whether they cross physiological barriers.
2. **[01:41–03:22] This is established, not a hypothesis.** Martin asked whether to present
   it as a hypothesis. Reviewer: many experiments use polystyrene beads with modified
   surfaces. Hydroxyl or carboxyl groups make them negative, amine groups positive, and
   sulfate groups negative. The effect on organisms changes with the charge, from bacteria
   to mice. *Needs 1–2 traced review citations before it goes on a slide.*
3. **[03:29–03:57] Put the motivation first.** Then explain how particles behave in liquids.
   Zeta potential comes from colloid chemistry at the end of the 19th century.

### IMG_1056: the curve, the sources, three ideas

4. **[00:00–04:46] The reviewer restates the curve idea correctly.** The x-axis is ionic
   strength and the y-axis is electrophoretic mobility. A hard particle falls toward zero
   at high salt, and a soft particle keeps a plateau.
5. **[04:52–08:12] The objection.** At [04:58] the reviewer summarises Martin's plan: fill in
   the dots from the single measurements in the literature, "so that AI agents can build on
   it" [05:04]. The reviewer's replies:
   - [05:14–05:58] Even with ionic strength, no curve follows, because it depends on how the
     charge is distributed in the particle. If the experiments did not all have the same
     charge, distributed the same way, "you get random dots in the plane of the graph".
   - [06:17–06:37] Even for an ideal hard particle with all its charge on the surface, the
     white curve changes with the amount of charge: "twice the charge, roughly twice as
     fast".
   - [06:47–07:01] "Unless you did the experiments across different ionic strengths with
     identically charged particles, no curve can come out."
   - [07:19–08:00] Martin asked whether it could be unified. The reviewer: that needs another
     parameter, the charge distribution. The curve's shape, and above all its high-salt
     limit, differs between hard and soft. "With measurements that are not comparable, you
     don't know where on the curve you are."
   - [08:12] "Good that we found this now."
   - *Scope (2026-10-12):* the objection rules out building a curve from pooled literature
     dots. It does not rule out reading one particle's curve, which is what slide 17 and D4
     describe ("papers print dots, not curves"). Points 7 and 7a are the reviewer saying
     so himself.
   - *Scope (2026-10-12, under discussion with Martin):* the objection rules out building a
     curve from pooled literature dots. It does not rule out reading one particle's curve,
     which is what slide 17 and D4 describe ("papers print dots, not curves"). Point 7 is
     the reviewer saying the same thing in his own words.
6. **[08:35–12:27] Mobility is what is measured, and the conditions may be in the
   Supplemental Information.** Zeta is derived from mobility. Martin said ionic strength is
   missing (99.7 %: the deck's share of the pairs lost to absence, not a share of papers).
   At [10:52] the reviewer took it as "úplně nic", nothing at all. The per-paper figures
   are 7.2 % (mean share of rows) and 38 of 467 papers (8.1 %) with any row reporting it.
   - [09:51–10:10] The reviewer on framing: maybe say this part worked only halfway, and
     add another topic, "one thing didn't work, so at least this".
   Reviewer: technical details such as concentrations and buffers are often only in the
   Supplemental Information, which is often open even when the paper is paywalled. Martin
   thought the pipeline read main texts only.
   - *Verified 2026-10-12:* it does. `src/mnp/corpus/jats.py` drops `supplementary-material`
     and excludes supplement sections from Methods, so every reporting rate is "stated in
     the main text".
   - *Checked 2026-10-12 (`docs/2026-10-12-si-ionic-strength.md`):* the SI of all 467
     papers was read. Papers with any row reporting ionic strength go from 38 to 43 (8.1 →
     9.2 %), with an upper bound of 47 (10.1 %) where a row lumps a series. The SI helps
     where the main text names no liquid at all, and never for a DI-water row.
7. **[12:52–14:06] Same particle, several salts, or no hard/soft call.** "Unless the
   experimenters themselves measured the same particle at at least a few different ionic
   strengths, you can't tell the hard particle from the soft one … that's quite clear." The
   reviewer recalls a Japanese researcher who measured controlled particles across ionic
   strengths and found they depart from the hard-particle theory, in "two or three papers".
7a. **[14:29–14:37] The reviewer's verdict.** "If it isn't standard [to report], then this
   idea really won't get through." He means extracting curves from the literature. Then:
   "what else could you do with the agents?"
   - *Probably* Kobayashi's group: 2008, 2016 and 2020. In 2020, latexes including 95 nm
     polystyrene in NaCl from 0.1 to 100 mM fit only "hard sphere plus slip 1 to 3.5 nm",
     which is "not the theoretical model". The other candidate is Makino & Ohshima 2011
     (soft, 1–200 mM).
     - All are in `docs/2026-09-08-mobility-curve-datasets.md` and
       `data/raw/digitised/printed_params.csv`, as fitted parameters with no digitised
       points.
     - The reviewer named none of them, so this identification is an inference.
   - *Our own corpus has such series too (checked 2026-10-12, `d1_zeta_table.csv`).*
     27 particles in 8 papers were measured at 2 or more ionic strengths within one paper,
     and 10 particles in 4 papers at 3 or more. Two of those series are clean, with one
     salt and fixed pH:
     - PMC10260929: PS 100 nm, NaCl 0.3, 30, 100 and 155 mM, pH 7.4, 25 °C;
     - PMC13182541: PS 10 µm with humic acid at 10 mg/L, NaCl 0.1, 1, 10 and 100 mM, pH 6.

     The other two mix NaCl with CaCl₂, or the humic acid amount changes along the series.
     The values are zeta, so they must be turned back into mobility with each paper's own
     conversion model. The NPE is trained on a fixed 8-point grid, so these series go
     through `infer/mcmc.py` on their own grid.
8. **[14:28–17:34] Molecular dynamics of protein–plastic binding** (a colleague's earlier
   suggestion). It needs simulation software and a compute cluster. The reviewer's own runs
   were about 20 ns in a box of about 10 nm. **Dropped (Martin, 2026-10-12).**
9. **[17:36–20:02] Idea A: surface charge vs biological effect, summarised across studies.**
   Many studies compare the same particle with positive and negative surfaces. Comparing an
   effect on bacteria with one on mice is apples and pears. The reviewer will think more and
   may ask the team who prepared the abstract. **Parked.**
10. **[20:06–21:30] The original abstract** is vague about the measurement itself.
11. **[22:27–25:51] Idea B: zeta vs size, by polymer type**, later also by aging. Martin's
    corpus is plastics only, with metal and other colloids excluded. It "either shows
    something, or complete chaos". **Before the talk (Martin, 2026-10-12).**
12. **[26:11–36:50] Idea C: environmental concentrations across methods and places.**
    - The problem: methods report different size windows (lower limits of 1, 10, 20 or
      50 µm), so studies disagree.
    - Plot: x is size, y is the concentration span each study reports. That benchmarks
      the studies against each other.
    - Map: where studies sampled and where nobody has, coloured by concentration.
    - Fit: derive relative abundance vs size from studies at the same place with different
      windows, then rescale every study to one window (e.g. 1 µm–5 mm) so they compare.
    - Time: sampling year is a variable, since later samples should be higher.
    - [29:58] Martin mentioned an "army" dataset of microplastic levels in riverbeds and sea
      beds. That is probably **MP-SED** from the US Army ERDC (sediments, by water body); see
      the C1 section below. Nano has almost no data.
    - [32:03] Many studies give only a lower size limit ("from 20 µm"), which implies an
      upper limit of 5 mm.
    - [36:46] Adding time as a variable is more complicated, "and you may not have that
      much time".
    - **Before the talk, focused on cross-validating studies at the same place (Martin,
      2026-10-12).**
13. **[37:00–37:30] Fit to the talk.** The reviewer: idea C belongs to the abstract's first
    paragraph (size ranges and method limits), not to zeta. It is a GRC AI session, so use
    as much AI as possible.

## Decisions, 2026-10-12 (Martin)

- Save the transcript for later AI use: this file plus the two raw transcripts.
- Ideas B and C are done **before** the talk.
- Molecular dynamics: dropped. Idea A: parked.
- Martin departs on **2026-10-30**, so everything for the talk must be done by then.
- Both B and C are to be completed; the order does not matter.
- Open: whether B and C *replace* slide 17 (the curve) or sit next to it (points 5, 7 and 7a).

## What the project already has for B and C

- **B.** `out/tables/d1_zeta_table.csv` (working tree, 2026-10-12):
  - 1 250 zeta rows with a value;
  - 1 046 of them with a size (798 nominal, 696 measured);
  - 892 of them polystyrene;
  - columns `material`, `size_nominal_nm`, `size_measured_nm` and `medium_class`.
  - Prior art: Yang et al. 2026, Environ Pollut 410:128905, PMID 42556690. Its abstract
    (read 2026-10-12) models MNP **toxicity** with PLSR on geometric and experimental
    descriptors and does not mention zeta. The claim in
    `docs/2026-09-07-charge-thesis-reserse.md` that they "modelled zeta directly
    (R² 0.5–0.8)" is not supported by the abstract; the full text was not read.
  - First look (2026-10-12, polystyrene, 815 zeta values from 221 papers):
    - Size shows no association with zeta: Spearman ρ −0.09 (plain), 0.01 (carboxyl),
      −0.15 (amine).
    - Of 118 amine-PS values, which are nominally positive, 67 are reported negative, and
      the median shifts with the liquid: DI water +6.5 mV, salt solution −13.7, buffer −41.8.
    - pH is not controlled for, and no human audit has run (OD-03).
- **C.**
  - D3 already rescales concentrations to a common size window. `src/mnp/rescale/`
    combines Koelmans et al. 2019 (Water Res 155:410) SI Table S1 with the Kooi & Koelmans
    2019 power law (α 1.6). It rescaled 47 studies, written to `out/tables/d3_rescaled.csv`
    and `d3_spread.csv`.
  - Table S1 has no location or date columns.
  - Datasets that do have them, per `docs/2026-09-07-charge-thesis-reserse.md`: NOAA NCEI
    marine microplastics (about 14 000 occurrence records), LITTERBASE, MP-SED and ToMEx.
    None of their fields is checked yet.

## C1 feasibility, 2026-10-12

Scripts, outputs and the re-run command are in `tool/colocation/`. The inputs are
gitignored; their URL and sha256 are in that README.

- **NOAA NCEI** "Global Marine Microplastics Observations" (ArcGIS export):
  - 29 076 rows from 96 DOIs, sampled 1972–2026.
  - NCEI has already converted values to one unit per matrix (pieces/m³ for ocean water and
    beaches). A comparison therefore compares NCEI's conversions, not the published values.
  - The only size field is `Mesh Size (mm)`, a lower bound.
- **Co-located pairs** (different DOI, same setting, within 50 km and 365 days): 2 653 pairs
  from 43 study-pairs.
  - 66 % are the same organisation or the same tow (same day, under 2 km).
  - Requiring the same method, the same mesh and two values above zero leaves 150 pairs from
    10 study-pairs, 86 % of them Mediterranean manta-net tows.
  - Their median disagreement is ×3.6, and the 90th percentile ×21.
- **Verdict:** a broad cross-validation is a no-go. A narrow case study works.
- **Case study, resolved 2026-10-12** (`tool/colocation/reisser_eriksen/README.md`):
  - The 171 Reisser 2013 tows are the same tows as 171 of Eriksen 2014's. Reisser is the
    last author of Eriksen 2014.
  - In pieces/km², the two papers publish the same numbers.
  - NCEI converted them differently. The depth for Reisser's Manta tows is 0.085 m, where
    the paper states 0.17 m; Eriksen's is 0.08 m. The size range is under 5 mm for Eriksen
    and all sizes for Reisser.
  - Each true same-tow pair differs by a median ×1.035 (Manta ×1.13, Neuston ×0.356).
  - The earlier ×1.9 came from also pairing replicate tows. Reisser's own wind-mixing median
    of 1.9 is a coincidence and a trap.
  - Not yet asked of NCEI: why 0.085 m.
- **MP-SED** (US Army ERDC):
  - 1 064 sediment records from 72 DOIs, with no coordinates (location is the water body);
  - one unit throughout;
  - an explicit size window `mp_mdl` (e.g. 63–5000 µm);
  - 13 water bodies with two or more DOIs.
- **LITTERBASE:** no bulk download.
