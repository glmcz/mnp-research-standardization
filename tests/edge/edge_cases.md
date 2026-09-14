# Edge cases for human adjudication

24 real papers from the corpus. Each is a decision the pipeline got wrong, got right by
luck, or where two careful readers could differ. Your answers become `key.yaml`, the
standard every future persona and prompt change is scored against
(`docs/ARCHITECTURE_PLAN.md` §6, gate 2).

Read each paper with:

```bash
uv run python -m mnp.extract show --pmcid <PMCID> --no-system
```

Answer in `key.yaml` — a verdict plus one line of reasoning. Where you think the paper is
genuinely ambiguous, say so: that is a legitimate answer, and the pipeline should learn to
report ambiguity rather than guess at it.

## Material boundary — what is a plastic particle?

### M1 · [PMC3990004](https://europepmc.org/article/PMC/PMC3990004)

PLG-PEMA biodegradable nanoparticles carry a zeta potential. PLGA/PLG is a synthetic
polyester used as a drug carrier, not an environmental pollutant. Does it count as a plastic
particle for this study?

*Why it matters:* Decides whether the drug-delivery literature enters the corpus at all — hundreds of papers.

### M2 · [PMC9735624](https://europepmc.org/article/PMC/PMC9735624)

Lignin nanoparticles with a printed zeta potential. Lignin is a natural polymer being
developed as a plastic replacement. Count it?

### M3 · [PMC12883708](https://europepmc.org/article/PMC/PMC12883708)

BiVO4 micromotors with a ~0.6 wt% poly(o-phenylenediamine) shell; five zeta values printed.
Polymer surface, inorganic core. Count it?

*Why it matters:* Sets the rule for every core-shell particle.

### M4 · [PMC9811439](https://europepmc.org/article/PMC/PMC9811439)

Cellulose nanocrystals, printed zeta, presented as a biodegradable packaging material. Count
it?

### M5 · [PMC9315505](https://europepmc.org/article/PMC/PMC9315505)

Polymer-coated iron-oxide particles used to capture plastics from water. Their zeta is
printed; the plastics' is not. Count the capture agent?

### M6 · [PMC5876619](https://europepmc.org/article/PMC/PMC5876619)

A PIB-PEG polymersome — a vesicle self-assembled from a polyisobutylene-PEG block
copolymer. Structurally it is a drug-delivery vesicle like a liposome, but it is built
entirely from a synthetic polymer. Count it as a plastic particle?

*Why it matters:* Raised independently by a gate-3 worker, which said it could read this
either way. The persona's list neither includes nor excludes polymersomes.

### M7 · [PMC12883708](https://europepmc.org/article/PMC/PMC12883708)

The rule says "a polymer coating on an inorganic core is not a plastic particle". Here the
poly(o-phenylenediamine) shell is a molecularly-imprinted recognition layer doing the
paper's actual work, not a passive coating. Does the rule still exclude it?

*Why it matters:* A gate-3 worker applied the rule as written but flagged that the shell is
functional rather than incidental. Decides the boundary for every functionalised core-shell
particle.

## Attribution — whose measurement is it?

### A1 · [PMC12105431](https://europepmc.org/article/PMC/PMC12105431)

Zeta values appear in the discussion, attributed to Zhou et al. rather than measured here.
Count them?

*Why it matters:* If cited values count, the corpus double-counts the literature.

### A2 · [PMC10458608](https://europepmc.org/article/PMC/PMC10458608)

The paper states the general 'plus/minus 30 mV' colloidal-stability threshold. Is that a
measurement?

### A3 · [PMC11026464](https://europepmc.org/article/PMC/PMC11026464)

Polystyrene beads appear only as an instrument calibration standard, with no zeta reported
for them. Does the paper report a plastic zeta?

### A4 · [PMC9318256](https://europepmc.org/article/PMC/PMC9318256)

Zeta is measured on whole industrial effluent containing microplastics, not on isolated
particles. Is that a microplastic measurement?

*Why it matters:* 10 rows hang on this one call.

### A5 · [PMC13520016](https://europepmc.org/article/PMC/PMC13520016)

Table 1 holds 80 fully-conditioned zeta values, but samples were 0.2 um filtered first,
removing 83-97% of the PET particles; the authors attribute the signal to the Abeta peptide.
Count them?

*Why it matters:* The largest single block of conditioned data in the corpus.

## The value — is a measurement reported?

### V1 · [PMC10978833](https://europepmc.org/article/PMC/PMC10978833)

The zeta is given as 'approximately -5 to -14 mV'. Is that a reported value, a reported
range, or no value?

### V2 · [PMC9974068](https://europepmc.org/article/PMC/PMC9974068)

The measurement is described in the text; the numbers exist only in Figure 1. Reported?

*Why it matters:* This class is 144 papers — the study's headline.

### V3 · [PMC12038248](https://europepmc.org/article/PMC/PMC12038248)

Values exist only in supplementary Table S2. Reported?

### V4 · [PMC11204973](https://europepmc.org/article/PMC/PMC11204973)

The text says the zeta potential was 'maintained' with no number anywhere. Is a measurement
reported?

### V5 · [PMC10479899](https://europepmc.org/article/PMC/PMC10479899)

Five zeta values are printed in prose with no unit stated anywhere in the paper. Record
them, and with what unit?

### V6 · [PMC10819112](https://europepmc.org/article/PMC/PMC10819112)

'the zeta potentials of PS and PVC MPs were plus/minus 45 and plus/minus 20'. Magnitude
given, sign not. What is the value?

### V7 · [PMC5876619](https://europepmc.org/article/PMC/PMC5876619)

Methods say "see Table S1 for all lipid compositions, size, and zeta potentials of
nanoparticles used in this study". The supplement is not available to the reader of the
main text, and the table's heading mentions lipids, though a carboxylated polystyrene bead
is among the particles studied. Does that pointer make the PS bead's zeta a reported
measurement (a `value: null` row), or is it too weak an inference to record?

*Why it matters:* The gold set recorded a row here; a gate-3 worker declined to, reasoning
that inferring coverage from a table heading was riskier than omitting. Both readings are
defensible, and the answer sets the rule for every "see Table SX" pointer in the corpus.

## Conditions — was a condition stated?

### C1 · [PMC4958399](https://europepmc.org/article/PMC/PMC4958399)

PBS is used and its tablet composition is printed (0.137 M NaCl, 0.0027 M KCl, 0.01 M
phosphate). Is the ionic strength reported?

*Why it matters:* Changes I-reported for every PBS paper in the corpus.

### C2 · [PMC4958399](https://europepmc.org/article/PMC/PMC4958399)

Particles were incubated at 25 C and 37 C before measurement; the measurement temperature is
never stated. Is temperature reported?

*Why it matters:* This single distinction drives row-level temperature precision to 0.15.

### C3 · [PMC9218121](https://europepmc.org/article/PMC/PMC9218121)

pH is given as a range across a titration rather than a single value. Is pH reported, and
what is recorded?

### C4 · [PMC9230722](https://europepmc.org/article/PMC/PMC9230722)

The medium is named only as 'the experimental medium'. Is the medium reported?

### C5 · [PMC4861966](https://europepmc.org/article/PMC/PMC4861966)

Methods state the medium and pH for the PEGylated particles only; the stock particles are
measured too. Do the conditions carry over to the stock rows?

*Why it matters:* Governs how far a once-stated condition propagates.

### C6 · [PMC10081693](https://europepmc.org/article/PMC/PMC10081693)

The instrument is named as 'Zetasizer (Nano ZS90; Malvern)'. If a paper instead said only
'Zetasizer', is the instrument reported?

### C7 · [PMC12250668](https://europepmc.org/article/PMC/PMC12250668)

The unit is printed as 'mvolt', and elsewhere in the corpus as 'MV' where millivolts are
meant. Should an obviously mistyped unit be taken at face value?

### C8 · [PMC11099890](https://europepmc.org/article/PMC/PMC11099890)

Mobility is printed as 'x 10-4 (cm2 V-1 s-1)' — the paper's own prefactor cancels the cm2.
Should the recorded unit be the bracket, or the whole header?

*Why it matters:* A wrong answer here is a 10^4 error.

