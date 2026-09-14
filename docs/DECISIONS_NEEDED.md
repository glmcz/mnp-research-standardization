# Three rules — **settled 2026-09-13**

Written 2026-09-13. Everything here is quoted from the papers or counted from
`data/interim/extractions.jsonl`; nothing is estimated.

---

## Why this document exists

Three LLM judges were given the same 17 disagreements between the hand-annotated gold set and
the extraction, the same brief, and the same papers. Two were Claude (different sessions,
readings anonymised and order-flipped); one was external (nemotron-3-super-120b, reached over
an API with no filesystem and no access to this repository).

| Pair | n | agreement | Cohen's κ (95% CI) |
|---|---|---|---|
| external vs claude-1 | 13 | 69% | **+0.41** (0.00 – 0.84) |
| claude-1 vs claude-2 | 13 | 31% | **−0.05** (−0.24 – 0.13) |
| external vs claude-2 | 14 | 0% | **−0.66** (−0.87 – −0.26) |

κ = −0.05 between two judges of the same family is worse than chance. The external judge was
the most self-consistent of the three (93% order consistency; it named the same source when
the two readings were swapped), but it agrees with neither Claude judge.

The disagreements are not noise. They line up exactly:

| Field | external | claude-1 | claude-2 |
|---|---|---|---|
| ionic strength ×4 | extraction | gold | gold |
| temperature ×6 | gold | gold | extraction |
| pH ×3 | extraction | extraction | ambiguous |

Every one is a **rule** disagreement, not a misreading. The brief is silent or ambiguous on
three rules, and all three feed the study's headline number. No amount of judging settles
this; it needs a decision.

---

## Q1 — Does a printed PBS recipe count as a reported ionic strength?

### What the paper says (PMC4958399, Methods, verbatim)

> The initial buffer used for particle analysis was phosphate buffered saline (1× PBS tablet
> (0.01 M phosphate buffer, 0.0027 M potassium chloride, 0.137 M sodium chloride) in 200 mL
> deionised water (18.2 MΩ cm)). PBS tablets (P4417) were purchased from Sigma-Aldrich, UK.

### The competing readings

- **Gold (139.7 mM, reported).** Two named monovalent salts at stated concentrations:
  0.137 M NaCl + 0.0027 M KCl = 139.7 mM. The phosphate is excluded because its speciation
  at pH 7.4 is not stated. The brief's own rule is "a named salt at a stated concentration
  counts", and this is a stated composition, not a looked-up nominal value.
- **Extraction (null, not reported).** The paper never writes the words "ionic strength". The
  reader must know that I = Σcᵢzᵢ²/2, recognise which components are fully dissociated, and
  decide to drop the phosphate. That is a calculation the reader performs, not a value the
  paper reports.

### What the judges said

External judge: **extraction** (null) on all four cases. Claude-1 and claude-2: **gold**
(139.7), both citing the printed recipe as the brief's stated-composition exception.

### How much it moves

**72 rows across 25 papers** have PBS as the medium; **63 of them currently record no ionic
strength**. If a printed recipe counts, those rows gain one — and the study's headline
("ionic strength missing in 89.8% of papers") moves by up to 25 papers, or **5 percentage
points**.

### What also matters

A deterministic check found that `parse_ionic_strength` only recognises salt *abbreviations*
(`NaCl`, `KCl`), not the spelled-out names this paper actually uses ("sodium chloride",
"potassium chloride"). So even if you answer "counts", the pipeline cannot currently reproduce
139.7 from the text — the gold annotator did the chemistry by hand. Answering "counts"
therefore also commits to a code change.

**Decision (Martin, 2026-09-13):** ☐ counts as reported ☐ does not count ☑ **counts, but flagged as derived** — a stated composition establishes ionic strength when the calculation follows directly from explicitly stated ionic species and concentrations.

---

## Q2 — Is an incubation temperature the measurement temperature?

### What the paper says (PMC4958399, Methods, verbatim)

> Each sample was vortexed for 30 s and sonicated for 1 min before incubation. Samples were
> then incubated at 25 and 37 °C in a mini dry bath (Benchmark Scientific, USA) for 10 min
> prior to TRPS analysis.

The temperature at which the TRPS measurement itself was performed is never stated anywhere
in the paper.

### The competing readings

- **Gold (null, not reported).** The 25/37 °C belong to a dry bath, explicitly "prior to TRPS
  analysis". Between the bath and the instrument the sample can equilibrate to room
  temperature; ε and η — which convert mobility to zeta — are temperature-dependent, so the
  measurement temperature is the one that matters and it is absent.
- **Extraction (25 / 37 °C, reported).** The paper's entire experiment *is* the temperature
  comparison; 25 and 37 °C are stated in the body text and are the condition under which each
  reported value was produced. Recording null discards the paper's own variable.

### What the judges said

External judge and claude-1: **gold** (null — the incubation is a different step). Claude-2:
**extraction**, on the ground that the temperatures are "directly stated in the body text".

### How much it moves

**397 rows across 95 papers** carry a temperature. **54 of those rows** have evidence quotes
that mention incubation, exposure or culture — the ones at risk of recording the wrong step.

This rule is already the single largest measured source of extraction error: row-level
temperature scores **P 0.15 / R 0.23** against the gold set, and every disagreement traced
back to this distinction.

**Decision (Martin, 2026-09-13):** ☑ **incubation is not the measurement temperature** ☐ it counts if no other temperature is given ☐ it counts, flagged as the incubation step. Only a temperature explicitly associated with the zeta-potential measurement counts; incubation, exposure and culture temperature are separate conditions.

---

## Q3 — Does a condition stated in one part of a paper carry to another?

### What the paper says (PMC4958399, Discussion, verbatim)

> Our samples were all suspended in PBS buffer at pH 7.4, and therefore, the albumin is
> expected to occupy the largest area of the nanoparticle surface as the adsorption is
> occurring at a pH furthest from its isoelectric point.

This is the paper's only numeric pH. It appears inside a paragraph reasoning about isolated
proteins and their isoelectric points. The three rows in dispute belong to a *different*
experiment — the plasma/serum comparison in Fig. 4 — where pH is never restated.

### The competing readings

- **Carries (pH 7.4 reported).** "Our samples were **all** suspended in PBS buffer at pH 7.4"
  is a statement about every sample in the study, not about one subsection.
- **Does not carry (null).** The sentence sits in an argument about protein isoelectric
  points; plasma and serum were separately diluted, and the paper never re-states pH for that
  experiment. Reading it across is an inference.
- **Ambiguous.** The paper does not determine it.

### What the judges said

External judge and claude-1: **extraction** (the pH carries). Claude-2: **ambiguous** — and
argued the brief has an explicit rule for temperature ("incubation ≠ measurement") but no
equivalent rule for scope, so this had to be decided by analogy.

### How much it moves

**1 016 rows across 264 papers** — more than half the corpus — have evidence quotes that
stitch together separate sentences with `" || "`, meaning at least one condition was carried
from somewhere else in the paper. A rule here touches more rows than Q1 and Q2 combined.

**Decision (Martin, 2026-09-13):** ☐ a condition stated once applies to every measurement in the paper ☑ **it applies only within the experiment where it is stated** ☐ it carries unless the paper describes a separate preparation ☐ ambiguity is itself the answer. Do not propagate conditions across distinct experimental preparations or measurements unless the paper explicitly establishes that the condition applies to them.

---

## What the answers changed

Recorded in `tests/edge/key.yaml` (C1, C2, C5), in `docs/briefs/extraction.md` — whose hash
moved from `0266af56…` to `21f2ad53…`, so every record produced from here on is traceable to
these rules and not to the earlier ones — in the worker system prompt (`prompt_sha256` moved
too), and in the two personas that encode the rules.

Code, each guard mutation-verified (revert the fix, watch a named test turn red):

| Rule | Change | Flag it raises |
|---|---|---|
| Q1 | `coerce.parse_ionic_strength` reads spelled-out salt names and sums a printed composition; phosphate at an unstated pH contributes nothing | `derived_from_composition` |
| Q2 | `coerce.parse_temperature` returns null for a temperature belonging to another step | `temperature_not_measurement` |
| Q2 | `zeta.verify_row` flags a temperature quoted inside an incubation sentence | `temperature_step_not_measurement` |
| Q3 | `zeta.verify_row` requires each condition in the row's **own** evidence, not merely in the article | `pH_not_in_evidence`, `temperature_not_in_evidence`, `ionic_strength_not_in_evidence` |

## The judges, scored against your answers

The 17 disputed cases, ground truth derived from the three rules above:

| Judge | n scored | agreement | Cohen's κ (95% CI) |
|---|---|---|---|
| claude-1 (blinded, order 1) | 16 | **100%** | **+1.00** (1.00 – 1.00) |
| external (nemotron-3-super-120b, API only) | 14 | 64% | +0.34 (0.00 – 0.71) |
| claude-2 (blinded, order 2) | 14 | 57% | +0.22 (0.00 – 0.59) |

Per rule, correct / cases: Q1 external 0/6, claude-1 5/6, claude-2 6/6 · Q2 external 6/6,
claude-1 6/6, claude-2 0/6 · Q3 external 4/4, claude-1 4/4, claude-2 1/4.

**Read this carefully before trusting it.** Claude-1 matching you on every scoreable case is
a result about *one* 17-case set, and it is the judge closest to the model that wrote both the
pipeline and this document — a κ of 1.00 there is as consistent with shared assumptions as
with correctness. What the table does establish is the negative: **no single judge can run
unsupervised**. Each of the three got an entire rule wrong, and a different one each
time — external on Q1, claude-2 on Q2, claude-2 again on Q3.

Majority-of-three would in fact have landed all three rules correctly here (2 of 3 on Q1,
2 of 3 on Q2, 2 of 3 on Q3). That is worth noting and not worth relying on: it is one
17-case set, each rule rests on 4–6 cases, and the majority was 2–1 every time, so a single
judge changing its mind flips it. Treat a judge panel as a detector of *which* cases are rule
disputes — at that it was perfect, every one of the 17 was a rule question, not a
misreading — not as a decider of them.

Answer key: `data/interim/worklists/judge_key_human.json`. Re-score with
`mnp.report.judge.cohen_kappa` + `bootstrap_ci`.

## One thing still worth checking

There may be an external standard for this. ISO 13099 covers zeta-potential measurement
methodology, and reporting checklists exist in the nanomaterial-characterisation literature
(MIRIBEL, the eNanoMapper/NanoCommons work). I have **not** verified what they say about
these three specific questions, and did not want to paraphrase a standard I had not read. If
one of them already settles a rule, that is a stronger answer than any judgement of ours, and
worth ten minutes of checking before you decide.
