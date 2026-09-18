# Findings — the 44 rows where one citation spans several ionic strengths

A single investigation, in the style of `FINDINGS.md`: what was measured, on what, and what it
changes. Every number below was computed against `out/tables/d1_zeta_table.csv` as of
2026-09-18 (1 890 rows, 491 papers, `evidence_line_ids` present on all 1 890). Where a figure
here disagrees with the brief that commissioned the work, **the computed figure stands and the
disagreement is named.**

Nothing was rebuilt and no source file was edited. Read-only throughout.

---

## The question

`docs/GATE_LOG.md` records the gate scientist's decisive example: **44 rows corpus-wide where
one citation spans several ionic strengths.** A "line" in the line-addressed document is a
paragraph, a table caption, one TSV row, a footnote or a figure caption (`src/mnp/corpus/lines.py`).
So the claim is that 44 rows point at a piece of text that does not distinguish experiments the
paper itself distinguishes.

If that is what it is, it is the talk's own thesis measured inside our own data. The thesis
(`Martin - From Detection to Predicting Micro.md`) is that

> "To ensure comparability across studies, it is necessary to account for particle size ranges
> and analytical method limits, surface properties, measurement conditions, and environmental
> parameters."

The question this document answers: **is the 44 a fact about the literature, or a fact about
our representation of it?**

The answer is **our representation**, 36 rows of 44, with **zero** rows of genuine
literature-side ambiguity about ionic strength. The detail below is what makes that defensible,
including the parts that are unflattering to the brief and to this document's own first pass.

---

## Method, so a stranger can redo it

Group the published table by `(pmcid, evidence_line_ids)` — the citation string exactly as
stored — and count distinct values of the condition within each group. A group with more than
one distinct value is a *shared citation*; its rows are the population.

```python
import pandas as pd
df = pd.read_csv("out/tables/d1_zeta_table.csv", dtype=str,
                 keep_default_na=False, na_values=[""])
d  = df[df.evidence_line_ids.notna() & df["ionic_strength_mM"].notna()]
g  = d.groupby(["pmcid", "evidence_line_ids"])["ionic_strength_mM"].nunique()
keys = set(g[g > 1].index)
rows = d[[(p, l) in keys for p, l in zip(d.pmcid, d.evidence_line_ids)]]
len(rows), len(keys), rows.pmcid.nunique()      # -> 44, 10, 6
```

Adjudication resolves each cited `line_id` back to its text with
`mnp.corpus.lines.resolve_id(lines.build_lines(article), ident)`, and reads the surrounding
article with `uv run python -m mnp.extract show --pmcid <PMCID> --no-system`. Every verdict
below quotes the text that settles it.

**Reproducibility caveat, stated rather than discovered.** The analysis scripts were written to
the session scratchpad and are not committed. The eight lines above regenerate the population;
the adjudication is manual and is preserved here only as the quotes themselves. This is the
same defect `FINDINGS.md` flags for E1, and it is not fixed by this document.

---

## 1. The population, per condition

Do not add these up. Each is its own denominator and its own question.

| condition | rows carrying it | distinct citations | citations spanning >1 value | **rows** | papers |
|---|---|---|---|---|---|
| **ionic strength** | 269 | 193 | 10 | **44** | **6** |
| **pH** | 362 | 222 | 11 | **45** | **10** |
| **temperature** | 406 | 222 | 4 | **8** | **2** |
| **medium** (verbatim `medium_text`) | 1 572 | 829 | 149 | **535** | **86** |
| **medium** (coerced `medium_class`) | 1 890 | 1 022 | 102 | **395** | **60** |

The gate log's **44 reproduces exactly**, as do 6 papers and 10 citations.

Medium is an order of magnitude larger than the other three and is a different phenomenon: a
medium is usually a phrase rather than a number, and one paragraph legitimately describes
several media. It is listed for completeness, not adjudicated here.

### Ionic strength — the spread inside a shared citation

Ratio of largest to smallest ionic strength within each of the 10 citations:

| pmcid | rows | distinct IS (mM) | spread |
|---|---|---|---|
| PMC10450312 | 4 | 0.1 / 1 / 10 / 100 | **1000x** |
| PMC12312160 | 8 | 1 / 100 | 100x |
| PMC12312160 | 4 | 1 / 100 | 100x |
| PMC12312160 | 4 | 1 / 100 | 100x |
| PMC6187999 | 2 | 1.5 / 150 | 100x |
| PMC6187999 | 2 | 1.5 / 150 | 100x |
| PMC6187999 | 2 | 1.5 / 150 | 100x |
| PMC13181784 | 2 | 56 / 398 | 7.11x |
| PMC13057466 | 6 | 150 / 500 | 3.33x |
| PMC12598813 | 10 | 10 / 10.5 | 1.05x |

Median spread **100x**. Seven of ten citations are at or above 100x, covering **26 of the 44
rows**. At 25 °C in a 1:1 electrolyte the Debye length is `0.304 / sqrt(I[M])` nm, so
1 mM -> 9.61 nm and 100 mM -> 0.96 nm; 1.5 mM -> 7.85 nm and 150 mM -> 0.79 nm.

### Three robustness checks on the population

- **Source of the number.** Of the 44, **36** carry `ionic_strength_source =
  inferred_from_named_salt` (derived from a named salt at a stated concentration, per the
  extraction brief) and **8** carry `reported`. Corpus-wide the split is 141 / 128. So the
  population is enriched in *derived* ionic strengths — expected, because a derived strength is
  one the worker had to build from a salt name and a concentration that may sit anywhere in the
  paragraph.
- **A looser grouping.** Grouping on *any shared single line id* rather than on the exact
  citation string gives **69 rows, 16 lines, 9 papers** — a superset that adds PMC10260929,
  PMC11726606 and PMC13182541. The 44 is therefore a lower bound under one specific grouping
  rule, not a closed set.
- **38 of the 44 rows have a printed value; 6 do not** (`value_not_printed`).

---

## 2. Adjudication — all 44 rows, not a sample

The brief asked for >=12 rows across >=4 papers. The ionic-strength population is small enough
to adjudicate exhaustively, so all **44 rows across all 6 papers** were read, which is strictly
stronger than a sample and removes any question of sample selection.

### The verdict scale

The brief named three verdicts. The data forced a fourth, which is stated openly rather than
folded into one of the others:

- **A — genuine ambiguity in the paper.** The cited text does not separate the experiments and a
  reader of it could not either.
- **B — our representation.** The paper separates them explicitly; line granularity is what lost
  it.
- **C — extraction error.** The stored ionic strength is wrong or misattributed, citation aside.
- **D — nothing lost.** One sentence legitimately establishes N conditions, each row carries one
  of them correctly, and no finer text unit exists that would separate them. Adding this
  category is a judgement; its 4 rows are listed separately so anyone can re-assign them.

### The table

Quotes are the deciding clause, verbatim, from the paper. Full paragraphs are in §6.

| row_id | verdict | the quote that settles it |
|---|---|---|
| PMC10450312-r1..r4 | **D** | *"In the current study, 0.1, 1, 10, or 100 mM NaCl solutions were used to represent different PS-NP suspensions exposed to different ionic strengths."* — **this sentence is cited**, it names all four, and each row carries one of them. All four rows are `value_not_printed`: the zetas exist only in *"(c) zeta potentials of PS-NPs at different ionic strengths and pH 7"*, Figure 1. |
| PMC12312160-r1 | **B** | *"…there is a significant decrease … in the ζ potential of SO4-PSNPs from 0 to 0.4 mgTYL mgSO4-PSNPs -1, shifting from -30 ± 1 to -37 ± 1 mV, respectively … at 1 mM NaCl."* |
| PMC12312160-r2 | **B** | same sentence — *"-30 ± 1 to -37 ± 1 mV … at 1 mM NaCl."* |
| PMC12312160-r3 | **B** | *"At 100 mM NaCl, the addition of TYL … The ζ potential value significantly increases … from -31 ± 1 to -7 ± 1 mV…"* |
| PMC12312160-r4 | **B** | same sentence — *"from -31 ± 1 to -7 ± 1 mV"*, at 100 mM NaCl. |
| PMC12312160-r5 | **B** | *"In 10 mM HEPES with 1 mM NaCl and no TYL present, the COOH-PSNPs had … a ζ potential of -47 ± 5 mV…"* |
| PMC12312160-r6 | **B** | *"The ζ potential of COOH-PSNPs is significantly higher … with a mgTYL:mgCOOH-PSNPs concentration ratio of 0.4, -37 ± 4 mV … at 1 mM NaCl."* |
| PMC12312160-r7 | **B** | *"At 100 mM NaCl … the ζ potential of COOH-PSNPs does significantly increase … from -38 ± 3 to -26 ± 2 mV…"* |
| PMC12312160-r8 | **B** | same sentence — *"-38 ± 3 to -26 ± 2 mV"*, at 100 mM NaCl. |
| PMC12312160-r9 | **B** | *"…no significant changes … in ζ potential for the SO4-PSNPs (Figure b, blue circles; -39 ± 2 to -36 ± 4 mV …) … following exposure to CIP at 1 mM NaCl."* |
| PMC12312160-r10 | **B** | same sentence — *"-39 ± 2 to -36 ± 4 mV … at 1 mM NaCl."* |
| PMC12312160-r11 | **B** | same sentence — *"or the COOH-PSNPs (Figure d, blue circles; -54 ± 7 to -49 ± 4 mV …) … at 1 mM NaCl."* |
| PMC12312160-r12 | **B** | same sentence — *"-54 ± 7 to -49 ± 4 mV … at 1 mM NaCl."* |
| PMC12312160-r13 | **B** | *"However, at 100 mM NaCl, a significant difference in ζ potential for both the SO4-PSNPs (Figure b, orange triangles; -38 ± 1 to -22 ± 1 mV …)"* |
| PMC12312160-r14 | **B** | same sentence — *"-38 ± 1 to -22 ± 1 mV"*, at 100 mM NaCl. |
| PMC12312160-r15 | **B** | same sentence — *"and the COOH-PSNPs (Figure d, orange triangles; -43 ± 2 to -38 ± 1 mV …)"*, at 100 mM NaCl. |
| PMC12312160-r16 | **B** | same sentence — *"-43 ± 2 to -38 ± 1 mV"*, at 100 mM NaCl. |
| PMC12598813-r5 | **B** | *"…fresh MPs start only mildly positive (+5.5 mV for PBAT, +6.9 mV for PS)…"* with *"adding NaCl or KCl (0–30 mg L-1) raises the ionic strength from 0.010 M to ≈0.0105 M (10 mM HEPES)"* — same paragraph, so "start" = 0 salt = 10 mM. |
| PMC12598813-r6 | **B** | same clause — *"+6.9 mV for PS"* at the start of the salt series. |
| PMC12598813-r7 | **B** | *"…once salt is introduced ζ rapidly inverts, ending at -16.5 mV (PBAT) and -19.4 mV (PS) at 30 mg L-1 NaCl."* |
| PMC12598813-r8 | **B** | same clause — *"-19.4 mV (PS) at 30 mg L-1 NaCl."* |
| PMC12598813-r9 | **B** | *"…aged MPs … begin strongly negative (-52 mV PBAT, -49 mV PS)…"* |
| PMC12598813-r10 | **B** | same clause — *"-49 mV PS"* at the start of the salt series. |
| PMC12598813-r11 | **B** | *"…finishing at -22.1 and -17.6 mV, respectively"* — i.e. at the 30 mg L-1 end. |
| PMC12598813-r12 | **B** | same clause — *"-17.6 mV"* at the 30 mg L-1 end. |
| PMC12598813-r13 | **C** | *"For example, at 20 mg L-1 salt, aged PBAT is -28.1 mV in NaCl but -34.3 mV in KCl…"* — stored `ionic_strength_mM = 10.0`, identical to the **zero-salt** rows, although the same paragraph says *"adding NaCl or KCl (0–30 mg L-1) raises the ionic strength from 0.010 M to ≈0.0105 M"*. The mg L-1 term was silently dropped. |
| PMC12598813-r14 | **C** | same clause — *"-34.3 mV in KCl"* at 20 mg L-1, also stored as 10.0 mM. |
| PMC13057466-r4 | **B** | *"Under neutral pH conditions, the ζ-potential of PS-Bare in 500 mmol L⁻¹ NaCl and 50 mmol L⁻¹ CaCl2 solutions was measured as -11.1 ± 1.92 mV and -11.2 ± 1.47 mV, respectively…"* |
| PMC13057466-r5 | **B** | same sentence — *"-11.2 ± 1.47 mV"* -> 50 mmol L⁻¹ CaCl2 -> I = 150 mM. |
| PMC13057466-r6 | **B** | *"In contrast, PS-COOH exhibited stronger negative ζ-potentials, with values of -14.5 ± 1.52 mV (NaCl) and -13.9 ± 1.24 mV (CaCl2)."* |
| PMC13057466-r7 | **B** | same sentence — *"-13.9 ± 1.24 mV (CaCl2)"*. |
| PMC13057466-r8 | **B** | *"Conversely, PS-NH2 displayed positive ζ-potentials, measuring 11.9 ± 1.97 mV and 16.5 ± 1.22 mV in the respective solutions."* — anaphoric, resolved two sentences back. Weakest B in the set. |
| PMC13057466-r9 | **B** | same sentence — *"16.5 ± 1.22 mV"* -> the CaCl2 member of *"the respective solutions"*. |
| PMC13181784-r3 | **C** | The cited line contains **no ionic strength at all**: *"The calculated data were in reasonable agreement with the experimental ones only at higher ionic strengths, because at lower salt concentrations…"*. The stored 56 mM occurs exactly once in the paper: *"The CCCs were 56 and 398 mM for NPL(+) and NPL(-), respectively"* — a **critical coagulation concentration**, not a measurement condition. |
| PMC13181784-r4 | **C** | same sentence — 398 mM is the CCC of NPL(-), recorded as the ionic strength of its mobility measurement. The tell: the two rows differ in ionic strength **by particle**, exactly as the CCC sentence pairs them. |
| PMC6187999-r1 | **B** | Cited line is a bare TSV row: `200 194.3±3.3 0.69±0.04 -43.5±0.81 -28.6±2.84 5.68 12`. The 1.5 mM is two lines earlier and four lines later: *"ZP * (mV) at low conductivity"* and *"* Measured at low (1.5 mM NaNO3) and high (150 mM NaNO3) conductivity."* |
| PMC6187999-r2 | **B** | same row; 150 mM from *"high (150 mM NaNO3) conductivity"*, footnote line, not cited. |
| PMC6187999-r3 | **B** | Cited line `500 545.1±6.3 0.70±0.03 -56.3±1.5 -32.8±3.15 3.64 11`; 1.5 mM from the same uncited footnote. |
| PMC6187999-r4 | **B** | same row; 150 mM from the same uncited footnote. |
| PMC6187999-r5 | **B** | Cited line `750 791±23.5 0.74±0.08 -56.1±0.81 -16.5±0.81 1.08 11`; 1.5 mM from the same uncited footnote. |
| PMC6187999-r6 | **B** | same row; 150 mM from the same uncited footnote. |

### The split

| verdict | rows | share | papers |
|---|---|---|---|
| **A — genuine ambiguity in the paper** | **0** | 0.0 % | 0 |
| **B — our representation** | **36** | 81.8 % | 4 (PMC12312160, PMC12598813, PMC13057466, PMC6187999) |
| **C — extraction error** | **4** | 9.1 % | 2 (PMC13181784, PMC12598813) |
| **D — nothing lost** | **4** | 9.1 % | 1 (PMC10450312) |
| total | **44** | | 6 |

Zero is the inconvenient number and it is the headline. **Not one of the 44 rows is a case of a
paper failing to state which ionic strength its zeta belongs to.** In every case the paper says
so; the disagreement is about *where* it says so, and whether our citation unit reaches it.

---

## 3. Which way it cuts

**This is a finding about our representation, not about the literature** — 36 / 44, with 0 / 44
on the other side. The evidence is the §2 table: for every B row the disambiguating clause is
inside the paper and quotable, and in 30 of 36 it is inside the *same paragraph we cited*.

Two mechanisms, and they are opposites:

```
  B-1  paragraph too COARSE  (30 rows: PMC12312160 16, PMC12598813 8, PMC13057466 6)

      one paragraph  --+-- "At 1 mM NaCl   ... -39 +/- 2 to -36 +/- 4 mV"   -> IS = 1 mM
                       +-- "At 100 mM NaCl ... -38 +/- 1 to -22 +/- 1 mV"   -> IS = 100 mM
                           one line_id  ------------------------------------>  both

  B-2  table row too FINE   (6 rows: PMC6187999)

      line 30  header    "ZP * (mV) at low conductivity | ... high conductivity"   <- not cited
      line 32  BODY ROW  "500  545.1+/-6.3  0.70+/-0.03  -56.3+/-1.5  -32.8+/-3.15" <- CITED
      line 36  footnote  "* Measured at low (1.5 mM NaNO3) and high (150 mM ...)"  <- not cited
      line  7  methods   "...sodium nitrate as electrolyte at 150 and 1.5 mM..."   <- not cited
```

B-2 is the one that generalises, because a table body row addressed on its own is not merely
coarse — it is *meaningless*. Measured across the whole corpus:

| does the cited line itself name an ionic strength? | rows | share of 269 |
|---|---|---|
| a concentration **with a unit** *and* an electrolyte | 161 | 59.9 % |
| a concentration with a unit, no electrolyte named | 23 | 8.6 % |
| an electrolyte or ion named, **no unit-bearing concentration** | 58 | 21.6 % |
| **neither** | 27 | 10.0 % |

**85 of 269 rows (31.6 %) carry an ionic strength whose cited line contains no
concentration-with-a-unit at all.** All 27 of the "neither" rows are table lines, across 4
papers (PMC13182541 14, PMC6187999 6, PMC11899741 4, PMC11543686 3). Corpus-wide, **217 rows
(11.5 %) across 14 papers cite only bare table body lines** — no caption, no header, no
footnote.

### The honest counterweight

B-2 is not *purely* our problem, and this is an argument rather than a measurement. A human who
copies -56.3 mV out of PMC6187999's Table 1 into a cross-study comparison, without reading down
to the footnote, makes precisely the error our line citation makes. The paper reported the
condition; it reported it four lines from the number. That is a weaker claim than "the
condition was not reported", and it is the claim the data supports.

---

## 4. Is it retrievable at all? — the eval's kind-A query

The clearest case, put as the kind-A question: *given the retrieved unit, what ionic strength
was this zeta measured at?*

| retrieved unit | can it answer? |
|---|---|
| line 32 alone — the cited line | **no.** Seven numbers and nothing else. Not answerable in principle. |
| lines 30 + 32 — header and body | **no.** "low conductivity" / "high conductivity" is not a concentration. |
| the whole table section (lines 29–39) | **yes.** The footnote gives 1.5 mM and 150 mM NaNO3. |
| table + methods (line 7) | yes, redundantly. |

Three of the article's 48 lines are needed, and the citation carries one. For B-1 the answer is
different and better: retrieving the whole paragraph **does** answer the question, because each
sentence carries its own "At 1 mM NaCl" / "At 100 mM NaCl" prefix. So the failure is not
uniform — it is specific to tables, and to any chunking that separates a value from its column
header and footnotes.

---

## 5. Slide-ready material

**The example.** `PMC6187999`, Table 1, row "500 nm". The cited line, verbatim (tabs shown as
spaces):

```
500     545.1±6.3     0.70±0.03     -56.3±1.5     -32.8±3.15     3.64 11
```

Two zeta potentials for the same particle, -56.3 mV and -32.8 mV, 24 mV apart. Which is which
is decided four lines further down, in the table's own footnote:

```
* Measured at low (1.5 mM NaNO3) and high (150 mM NaNO3) conductivity.
```

1.5 mM vs 150 mM is a hundredfold change in ionic strength: a Debye length of **7.85 nm** versus
**0.79 nm**.

**One sentence for a non-specialist audience.**

> This table gives two surface-charge numbers for the same plastic particle — one in nearly pure
> water, one in salty water — and nothing in the row of numbers says which is which; that is
> printed four lines below in a footnote, so anything that reads the table row by row, human or
> machine, ends up treating two different experiments as one.

---

## 6. The deciding paragraphs, verbatim

Abridged only where marked with `[...]`.

**PMC12312160, line 25** (cited by rows r9–r16, `3462e7d827dbcb55`):

> We compared our TYL results with those of a second model antibiotic, CIP (Figure ). We chose
> CIP due to its zwitterionic nature at a pH of 7.4. **At 1 mM NaCl**, we observed no significant
> changes (n = 5, α = 0.05) in hydrodynamic diameter for the SO4-PSNPs [...] Similarly, we
> observed no significant changes (n = 5, α = 0.05) in ζ potential for the SO4-PSNPs (Figure b,
> blue circles; -39 ± 2 to -36 ± 4 mV from 0 to 0.4 mgCIP:mgSO4-PSNPs, respectively) or the
> COOH-PSNPs (Figure d, blue circles; -54 ± 7 to -49 ± 4 mV from 0 to 0.4 mgCIP:mgCOOH-PSNPs,
> respectively) following exposure to CIP **at 1 mM NaCl**. **At 100 mM NaCl**, we observed no
> significant changes [...] However, **at 100 mM NaCl**, a significant difference in ζ potential
> for both the SO4-PSNPs (Figure b, orange triangles; -38 ± 1 to -22 ± 1 mV from 0 to 0.4
> mgCIP:mgSO4-PSNPs, respectively) and the COOH-PSNPs (Figure d, orange triangles; -43 ± 2 to
> -38 ± 1 mV from 0 to 0.4 mgCIP:mgCOOH-PSNPs, respectively) was observed following exposure to
> CIP.

**PMC10450312, lines 5 and 14** (cited by rows r1–r4, `05b22130be7f9060;0bfc44854df30933`):

> Figure 1. (a) SEM images of the SiO2 surface deposition of PS-NPs at an ionic strength of 10
> mM. (b) Hydrodynamic particle sizes and (c) zeta potentials of PS-NPs at different ionic
> strengths and pH 7. [...]

> A stock suspension of PS-NPs with a nominal size of 100 nm [...] **In the current study, 0.1,
> 1, 10, or 100 mM NaCl solutions were used to represent different PS-NP suspensions exposed to
> different ionic strengths.** The pH of the suspensions was 7.0 ± 0.2 [...] The hydrodynamic
> diameters and zeta potentials of PS-NPs (0.05 g/L) were measured in triplicate using a
> Zetasizer Nano ZSP (Malvern, UK) and DLS at 25 °C. [...]

**PMC6187999, table `t1-ijn-13-6345`**, lines 29–36 (rows r1–r6 cite lines 31, 32 and 33 only):

```
29  Table 1. Physicochemical parameters of PS-NPs and control liposomes
30  PS-NP diameter (nm) | z-average, diameter (nm) | SPAN *** | ZP * (mV) at low conductivity | ZP * (mV) at high conductivity | Particles/mL **
31  750  791±23.5   0.74±0.08  -56.1±0.81  -16.5±0.81  1.08 11      <- cited by r5, r6
32  500  545.1±6.3  0.70±0.03  -56.3±1.5   -32.8±3.15  3.64 11      <- cited by r3, r4
33  200  194.3±3.3  0.69±0.04  -43.5±0.81  -28.6±2.84  5.68 12      <- cited by r1, r2
34  PEGylated liposomes  132.3±1.3  0.83±0.02  -17.9±1.4  -3.6±0.67  9.04 12
35  Notes:
36  * Measured at low (1.5 mM NaNO3) and high (150 mM NaNO3) conductivity.
```

and the Methods, line 7, which says it again:

> The ζ-potential was determined with a Zetasizer Nano ZS (Malvern Instruments, Malvern, UK)
> **using sodium nitrate as electrolyte at 150 and 1.5 mM (high and low conductivity,
> respectively).**

**PMC13181784, line 13** (cited by r3, r4, `f7a5196f0d507a13`) — note it contains no number:

> The magnitude of the EM decreased with an increase in the salt concentration at both NPLs and
> remained close to zero at high salinity. [...] The calculated data were in reasonable agreement
> with the experimental ones only at higher ionic strengths, because at lower salt concentrations
> the electrophoretic mobility is affected by electrokinetic contributions [...]

and line 14, which is where 56 and 398 actually come from and is **not** cited:

> When the CCC data was compared (Table S2), the one determined for NPL(-) was about 5-times
> larger compared to the NPL(+) case. [...] **The CCCs were 56 and 398 mM for NPL(+) and NPL(-),
> respectively**, which are in good agreement with the values obtained by DLS [...]

**PMC13057466, line 25** (cited by rows r4–r9, `8aa776b25baa339f`), final three sentences:

> **Under neutral pH conditions, the ζ-potential of PS-Bare in 500 mmol L⁻¹ NaCl and 50 mmol L⁻¹
> CaCl2 solutions was measured as -11.1 ± 1.92 mV and -11.2 ± 1.47 mV, respectively**, indicating
> minimal influence from electrolyte type. In contrast, PS-COOH exhibited stronger negative
> ζ-potentials, with values of -14.5 ± 1.52 mV (NaCl) and -13.9 ± 1.24 mV (CaCl2). Conversely,
> PS-NH2 displayed positive ζ-potentials, measuring 11.9 ± 1.97 mV and 16.5 ± 1.22 mV in the
> respective solutions.

**PMC12598813, line 31** (cited with methods line 7 by rows r5–r14):

> Ionic-strength suppression is studied [...] The electrokinetic measurements (Table S8–9 and
> Figure S10, Supporting Information) further show that **adding NaCl or KCl (0–30 mg L-1) raises
> the ionic strength from 0.010 M to ≈0.0105 M (10 mM HEPES)**, progressively compressing the
> double layer [...] Figure S10 [...] shows that fresh MPs start only mildly positive (+5.5 mV
> for PBAT, +6.9 mV for PS), and once salt is introduced ζ rapidly inverts, ending at -16.5 mV
> (PBAT) and -19.4 mV (PS) at 30 mg L-1 NaCl. In contrast, aged MPs [...] begin strongly negative
> (-52 mV PBAT, -49 mV PS) and are driven only part-way toward neutrality by the same salt doses,
> finishing at -22.1 and -17.6 mV, respectively [...] **For example, at 20 mg L-1 salt, aged PBAT
> is -28.1 mV in NaCl but -34.3 mV in KCl**, an 18% additional neutralization. [...]

---

## 7. Two corrections

**The brief's headline example is the weakest of the ten, not the strongest.** The commissioning
brief presented `PMC10450312` — four rows on one citation spanning 0.1 / 1 / 10 / 100 mM, a
1000-fold range — as a verified example of the failure. The facts are verified: 4 rows, one
citation, four ionic strengths, confirmed here. The *interpretation* does not survive reading
the paragraph. The cited sentence names all four strengths explicitly, each row carries one of
them correctly, and all four rows are `value_not_printed` because the zetas exist only in Figure
1c. Nothing is lost and nothing is ambiguous; the citation is shared because one sentence
honestly describes four experiments. **The 1000x number should not go on a slide as evidence of
ambiguity.** `PMC6187999`, at 100x, should.

**This document's own first retrievability pass was wrong, for the reason the gate scientist
named.** A first version asked whether the ionic strength "appears on the cited line" by
searching for the number as a digit string. It returned 68 of 71 — i.e. almost everything fine.
It was matching `1.5` inside `-56.3±1.5`, a standard deviation. That is exactly the gate log's
second mechanism: `_number_in` is a unit-blind digit search, and widening the haystack turns it
into noise. The unit-aware rewrite — require a number *immediately followed by* mM / mmol / M /
mol L-1 / mg L-1 — gives the 161 / 23 / 58 / 27 split in §3, and the three PMC6187999 rows that
"passed" the loose check are in the *neither* bucket under the strict one. **The corrected
figures are the ones above.** A check that cannot fail is not a check.

---

## 8. What this does NOT show

- **n is small and one-sided.** 44 rows, 10 citations, **6 papers**. The B verdict rests on 4
  papers and the C verdict on 2. Sixteen of the 36 B rows come from a single paper
  (`PMC12312160`) and 6 more from a single table (`PMC6187999`). These are not independent
  observations and no confidence interval is offered, because one would be misleading.
- **One database, one access tier.** Europe PMC open access only. `out/tables/d1_stats.md`
  records that 89.6 % of the 491 papers report no ionic strength at all; the 269 rows analysed
  here are the minority that do, which is a self-selected and probably better-reported subset.
  Nothing here describes the paywalled literature.
- **The sample is ours and the reading is ours.** One reader adjudicated all 44 rows. There is no
  second annotator, no kappa, and no blind. `docs/GATE_LOG.md` records that the repo's own panel
  agreed at kappa = -0.05 on a different task, which is reason to distrust a single unblinded
  read of this one. The quotes are given so that a disagreeing reader can overturn a verdict
  without re-running anything.
- **It does not measure whether the literature reports conditions well.** It measures whether
  *our citation unit* reaches the conditions the literature does report. `d1_stats.md` is the
  document that measures the first thing; this one does not, and the 0 / 44 in the A column is a
  statement about these 44 rows, not about the corpus.
- **The grouping rule is a choice.** Exact citation string gives 44; any-shared-line gives 69
  across 9 papers. Both are defensible; the second was not adjudicated.
- **pH (45 rows / 10 papers), temperature (8 / 2) and medium (535 / 86) were counted but not
  adjudicated.** Whether their splits look like ionic strength's is unmeasured, and the medium
  population is large enough that assuming so would be careless.
- **Verdict D is an addition.** Four rows sit in a category the commissioning brief did not
  offer. If a reader collapses D into A, the split becomes 4 / 36 / 4 and the headline claim —
  that this is about our representation — is unchanged.

---

## What this changes

1. **`docs/GATE_LOG.md` Card 1 keeps its conclusion and loses one of its reasons.** The gates
   were right that "leave condition scope on the quote" is the safe default: 36 of 44 rows are
   cases where the quote separates what the paragraph does not. But the accompanying framing —
   "The quote separated those experiments. The paragraph does not." — is a statement about *our
   units*, and it should not be read as one about the literature. It is now measured either way.
2. **The talk gets a slide about chunking, not about sloppy reporting.** The honest headline is
   narrower and sharper than the one commissioned: *conditions are frequently reported at a
   distance from the value they qualify — a column header, a table footnote, a methods section —
   and any unit of retrieval that does not carry that distance loses the condition.* 31.6 % of
   our ionic-strength rows cite a line that cannot express an ionic strength.
3. **Two extraction defects to fix, both real, neither about citation.** `PMC13181784-r3/r4`
   record a critical coagulation concentration as a measurement ionic strength;
   `PMC12598813-r13/r14` record 10.0 mM where the paper's own arithmetic puts the value between
   10.0 and 10.5, because `parse_ionic_strength` cannot read mg L-1 and drops the term in
   silence. The second is a coercion gap, not a worker error: a salt named at a stated
   concentration in mass units satisfies the extraction brief's rule, and the parser rejects it
   without saying so.
4. **A table needs a composite address.** B-2 is unfixable by choosing a different text
   granularity, because the header, the body row and the footnote are all genuinely different
   lines. A table row's citation has to carry its caption, header row and footnotes, or the
   retrieved unit is uninterpretable. 217 rows across 14 papers currently cite bare body rows.

---

## Open questions

- Does the same split hold for pH? 45 rows across 10 papers is a larger and more diverse
  population than ionic strength's 6 papers, and pH ranges of 1.2–6.8 and 3–10 inside a single
  citation appear in it.
- What does a composite table address cost, and does it change the 31.6 %?
- Can the kind-A eval be scored on the 85 rows whose cited line cannot express an ionic
  strength? That is a ready-made adversarial slice with a known right answer per row.
