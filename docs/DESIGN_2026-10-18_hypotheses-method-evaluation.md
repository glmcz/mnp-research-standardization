# Design 2026-10-18 — hypotheses, method, evaluation

The backbone of the talk from here to 2026-10-30, written after the review call
(`docs/2026-10-10-review-call.md`), the supplement check (`docs/2026-10-12-si-ionic-strength.md`),
the P2 page (`tool/p2/`) and the dataset recon (`tool/datasets/README.md`).

Martin's request: go back to the start, and from there state the hypotheses, the method and the
evaluation, including an engineering approach with metrics he can present. "The start" is the
abstract (`docs/Martin - From Detection to Predicting Micro.md`). Each hypothesis below is one of
its sentences, made testable.

New data goes into an **extension layer** (decided 2026-10-18). The frozen corpus
(`out/tables/d1_zeta_table.csv`, 467 papers, 1 903 rows) and every number the deck already
prints stay as they are. Extension tables carry their own sources and pins.

---

## 0. From the abstract to five hypotheses

| abstract says | hypothesis | kind |
|---|---|---|
| "To ensure comparability … it is necessary to account for … measurement conditions" | **H1 Absence.** Literature zeta values cannot be compared because the conditions that define them are not reported. | science, measured |
| "a single zeta potential value cannot unambiguously characterize an MNP surface … chemically distinct particles may exhibit similar zeta potential values" | **H2 Under-determination.** A zeta value does not identify the polymer, the size or the surface. The liquid and the surface chemistry explain more of it than the polymer or the size. | science, partly measured |
| "the reported number of particles can vary substantially depending on the detection and identification limits of a given method" | **H3 Size window.** Concentration studies disagree largely because they count different size windows, and rescaling to one window does not repair it. | science, partly measured |
| "Harmonization of these data is essential for … accurately comparing results" | **H4 Aggregation.** Harmonised databases change the measurements they hold, and the change is not documented per record. | science, one case |
| "standardized multiparametric datasets could also provide a foundation for applying artificial intelligence methods" | **H5 Engineering.** Agents can build and check such a dataset only if a model reads and code decides. An added challenge stage lowers the rate of wrong verdicts at a cost that can be measured. | engineering, to measure |

Exploratory vs confirmatory. Some results below were found by looking (the P2 page). They are
labelled **exploratory** and are not presented as tests. A **confirmatory** test runs on data
nobody has looked at yet, with the prediction written down first (§4).

---

## 1. The hypotheses, one by one

Each block lists the prediction, the method, the metric, what would refute it, and its status.

### H1 Absence — status: measured, robust to the supplement check

- **Prediction.** In a census of rows that describe the same particle, most pairs fail on a
  condition one paper did not state, not on a stated difference. Ionic strength is the condition
  missing most often.
- **Method.**
  - **Corpus:** one Europe PMC open-access query (CP-01). Each paper is read by a worker agent,
    and every row is verified by code against its source line (METHODOLOGY §6).
  - **Absence:** recorded as a value, never imputed.
  - **Comparison:** pairs are compared by `comparable()`.
  - **Supplements:** checked for every paper (`tool/si_scan/`).
- **Metrics.**
  - Reporting rate per condition, per row and per paper, with Wilson intervals and paper-clustered
    bootstrap intervals (FINDINGS E2e: rows cluster, so 1 903 is not the sample size).
  - Share of same-particle pairs lost only to absence.
  - Gain from the supplements.
- **Would refute it:** the supplements supplying the missing ionic strength for most papers.
- **Result.**
  - Ionic strength is reported for 38 of 467 papers in the main text (8.1 %), and for 43 (9.2 %)
    with the supplements.
  - The supplements rescue 5 of 429 papers.
  - 29 075 of 166 965 same-particle pairs are lost only to absence. Ionic strength is missing in
    28 984 of them (99.7 %).
  - Sources: REVIEW.md C-items, SI doc.

### H2 Under-determination — status: H2a exploratory, H2b to pre-register

- **H2a, descriptive (exploratory, from the P2 page).**
  - Pooled over 1 046 zeta values with a size (278 papers), size against zeta: Spearman ρ = 0.02.
  - Eight of nine named polymers have medians from −32.0 to −12.3 mV.
  - Nylon's median is +21.8 mV, but 20 of its 25 values come from one paper.
  - Of 117 amine polystyrene values, 67 are negative. The median moves with the liquid: DI water
    +6.5, salt solution −13.7, buffer −41.8.
  - Source: `tool/p2/data.json`, `test_p2.py`.
- **H2b, predictive (confirmatory, not yet run).** Can a model predict a zeta value from the
  particle's descriptors, and which descriptors carry the signal?
  - **Method.** Gradient-boosted trees on the 1 046 rows, five feature sets:
    {size}, {polymer}, {surface}, {liquid class, pH}, {all}.
  - **Cross-validation grouped by paper,** so a paper never sits in both training and test.
    This matters: rows from one paper share a lab, an instrument and a liquid, and ungrouped CV
    would score that leakage as skill.
  - **Metric:** out-of-paper R² per feature set, with paper-bootstrap intervals, and permutation
    importance on the full model.
  - **Prediction (to be written by Martin before the run, §4):** R²({liquid, pH}) and
    R²({surface}) exceed R²({size}) and R²({polymer}). R²({all}) stays well below 1, because
    ionic strength, the condition that matters most, is the one that is missing.
  - **Would refute it:** {polymer} or {size} out-predicting {liquid, pH} and {surface}.
  - **Bridge to H5:** Yang et al. 2026 (Environ Pollut 410:128905) report a zeta model with test
    R² 0.69 on 31 particles. Our number says how far that carries to 1 046 literature values
    measured in liquids nobody standardised.
- **The curve, kept honest.**
  - One particle measured at several salts is the only route to a hard/soft call
    (review call, item 7).
  - The corpus holds 27 particles in 8 papers measured at two or more ionic strengths, and two
    clean series.
  - The cleanest, PMC10260929, clumps above 100 mM: hydrodynamic size goes from 119.5 to
    250.5 nm. So "same particle" must be checked against the measured size, not assumed.

### H3 Size window — status: H3a exploratory on two databases, confirmatory on soil; H3b case; H3c partly measured

- **H3a: across studies, a finer lower size limit goes with a higher reported concentration.**
  - **Exploratory:** NCEI ocean water ρ = −0.26 (p 0.027, 73 studies); MP-SED sediment
    ρ = −0.25 (p 0.038, 71).
  - **Confirmatory:** the global soil dataset (Wu et al., Zenodo 20806151, 297 studies), which
    nobody on this project has analysed yet. Same statistic, sign predicted negative, magnitude
    written down first.
  - **Also on soil:** whether the 201 places with two or more studies disagree less after
    rescaling.
- **H3b: within one river, the size window decides the count.** *Corrected 2026-10-19: an
  earlier version said "the method decides".*
  - Weser estuary, PANGAEA 937685 and 938143 (CC BY 4.0): one study sampled two complementary
    size fractions at the same 23 stations. S-MP is 11–500 µm (pump, µFTIR); L-MP is
    500–5000 µm (net, ATR-FTIR).
  - The small fraction outnumbers the large by a median of 5 237 (22 stations; one found no large
    particles), which implies a power-law α ≈ 3.24, against the 1.6 usually assumed. *(5 340 corrected to 5 237 on 2026-10-19: one station with no large particles had added an infinite ratio to the median.)*
  - It is not a measurement disagreement. It shows how much any count depends on where its
    window starts, and that the default slope can be badly wrong for small particles.
  - The identification method also differs between the fractions, which is a confounder.
- **H3c: rescaling to one size window does not repair the disagreement.**
  - D3 (the results page) puts 34 drinking and freshwater studies on 1–5000 µm with the
    Kooi & Koelmans power law. The spread goes from 8.3 decades to 7.5 at α = 1.6.
  - **New (confirmatory):** MPsizeBase (Zenodo 20832480) holds 203 measured size distributions.
    Fit α for each, and report how many fall within 1.6 ± 0.3.
  - **Prediction, written first:** a wide spread of α, so one assumed slope is not a safe
    correction.
- **Time as a confounder (exploratory).**
  - NCEI's finest size limit falls with the year: ρ = −0.33 (p 0.00066, 102 study rows).
  - Combined with H3a, a count that rises over the years is partly finer nets.
  - MP-SED shows the same sign, not significant (ρ −0.19, p 0.14).

### H4 Aggregation — status: one resolved case, generalised by H5

- **Case.** Reisser 2013 and Eriksen 2014 report the same 171 net tows, with Reisser as an
  Eriksen author.
  - In pieces/km² the papers agree within 0.1 % for 168 of the 171 tows.
  - NCEI converts the two differently:
    - net depth 0.085 m for Reisser's Manta tows, where the paper states 0.17 m;
    - 0.08 m for every Eriksen tow;
    - a size cut under 5 mm for Eriksen, none for Reisser.
  - One tow therefore carries two values (median ratio: Manta 1.13, Neuston 0.36), and 17 tows
    are zero in one and positive in the other.
  - Source: `tool/colocation/reisser_eriksen/README.md`.
- **A trap.** Reisser's own wind-mixing median is 1.9, and a first, wrong pairing gave ×1.9.
  The match is a coincidence that only arithmetic exposes.
- **Not yet asked:** why NCEI used 0.085 m. Do not call it an error on stage until NCEI answers
  (an outward contact; Martin's call).

### H5 Engineering — status: to build and measure (§3)

**A validation system** in which a model reads and code decides, plus a challenge stage. It turns
H1–H4's one-off checks into one repeatable process, and it is how the extension data arrives.

---

## 2. Method — the principles every part follows

Kept from the build (METHODOLOGY §6) and from P2:

1. **Model reads, code decides.** A model proposes, and code accepts only what it can check:
   - the quote is verbatim in the source;
   - the value is printed in the quote;
   - the arithmetic reproduces the claimed number.
2. **Absence is a value.** Nothing is imputed. "Not reported" is recorded and counted.
3. **Pinned inputs.** Every external file carries a sha256. A build stops if one changes.
4. **Second routes.** Each number the talk prints is recomputed by a test that does not use the
   builder's code. Every guard is mutation-tested: put the bug back, and the test fails.
5. **Clustered statistics.** Rows cluster by paper. Intervals are paper-bootstrap intervals and
   cross-validation is grouped by paper.
6. **Exploratory vs confirmatory.** A prediction is written in `docs/PREREG_2026-10.md` and
   committed before the confirmatory run. The commit hash is the timestamp.
7. **Report where the method loses.** As the grid did with kind D: a prose question the table
   has no field for.

---

## 3. H5 — the validation system and its evaluation

### 3.1 The system

```
question ─► DISCOVER   code    candidates: absent conditions | values contradicting their label | records of one measurement
          ─► FETCH      code    main text + supplements (PMC OA S3, md5) + external data (figshare, NCEI archive)
          ─► READ       model   isolated reader (claude -p, tools off), answer + cited line ids
          ─► VERIFY     code    quote verbatim? value printed? units? arithmetic reproduces?
          ─► CHALLENGE  model   second blind reader; disagreement → abstain or escalate
          ─► VERDICT    code    verdict + provenance; abstentions counted, never hidden
```

The same pipeline runs three questions:

| question | instance | status |
|---|---|---|
| Q1 Is the absence real? | ionic strength not in the main text: is it in the supplement? | **done** as `tool/si_scan` (3 readers, code verify, random recall check) |
| Q2 Why does a value contradict its label? | the 67 negative amine polystyrene values: pH, protein corona, ions, labelling error, extraction error, unexplained | **build first**. All its papers are already in the corpus with line documents |
| Q3 Do two records of one measurement agree? | duplicate or co-located survey records | the Reisser/Eriksen case is solved by hand. The system has to find it again unaided, and that is its test |

The engineering carried over: an atomic work queue with leases (METHODOLOGY §5.1), a reader with
no Agent tool (§5.2), the brief's hash on every verdict (§5.3), and idempotent writes.

### 3.2 Evaluation: an ablation ladder, where each rung adds one stage

| config | stages | what the delta answers |
|---|---|---|
| **V0** | read only: one model gives a verdict and an explanation | the naive "ask the AI" baseline |
| **V1** | V0 + code verification | what checking quotes and arithmetic buys |
| **V2** | V1 + challenge by a second blind reader | what the adversary buys |
| **V3** | V2 + a human on disagreements only | what the human buys, per minute spent |

The same reader model, the same candidates and the same line documents in every config. As in
the grid, one variable moves per step, so each delta means something.

### 3.3 Ground truth and metrics

**Ground truth.**
- Martin labels a stratified random sample of 30 candidates for Q2 from the papers, blind to the
  system's verdicts.
- This is also the first piece of the human audit (OD-03), so the gold set stops being
  model-annotated for this question.

**Trap set.** Cases with a known answer that a pattern-matcher gets wrong:
- the wind-mixing 1.9 in Reisser (a coincidence);
- PMC10260929's clumped beads (not the same particle);
- a nominally positive bead reported negative in buffer (not an error);
- MP-GERE's review repeating a primary study's numbers (a duplicate).

**Metrics, per config:**

| metric | why it matters |
|---|---|
| verdict accuracy and balanced accuracy against Martin's labels | balanced, because "unexplained" may dominate (lesson of C9 kind E) |
| **false-explanation rate**: an explanation that fails code verification or contradicts the human label | the money metric. A confident wrong cause is worse than "unexplained" |
| traps caught / traps | does the system fall for coincidences? |
| citation validity (quote verbatim, line exists) | code-checked, so it should reach 100 % from V1 on |
| abstention rate, and accuracy on the verdicts not abstained | a system may refuse; it may not bluff |
| reader agreement, V2 (Cohen's κ) | how often two blind readers disagree |
| cost: tokens, model calls, wall clock per verdict; human minutes per verdict (V3) | "better" has a price, and the talk names it |

**What would refute H5:** V0 already as accurate as V2 with the same false-explanation rate. Then
the stages are decoration, and the talk says so.

### 3.4 An independent judge layer: scale the evaluation past 30 labels

Martin's 30 labels are the ground truth, but 30 cases give wide intervals. A judge layer scores
every verdict from every config. Only judges that agree with Martin's labels are trusted.

**Independence by design.**
- **Different families.** The reader is Claude (Sonnet). The jury is three judges from three other
  model families via OpenRouter, each with a pinned model id (free model ids drift; see memory
  `mnp-research-llm-extraction`).
- **Not Jev** (skipped 2026-10-19). For reference: Jev (TypeSafe), a decision-only judge that returns label probabilities rather than
  text (Li, Miao, Krishnan, Padman, arXiv 2609.26550, 2026; built into DeepEval as `JevEval`).
  It needs a paid TypeSafe API key and sends paper excerpts to a third party, so it is Martin's
  call.
- **Blind.** A judge never sees which config (V0–V3) produced a verdict.
- **Same format for all.** Every explanation is rendered in one fixed schema and length, so a
  longer or more fluent explanation cannot win on style (verbosity bias, Zheng et al. 2023,
  MT-Bench). Order is randomised per call (position bias).
- **A panel, not one judge.** A jury of diverse models is less biased than a single strong judge
  (Verga et al. 2024, "Replacing Judges with Juries"). Majority vote, with disagreement reported.

**What judges are asked: typed, decomposed questions**

| id | question | type | who answers |
|---|---|---|---|
| J1 | Do the cited lines exist and say what the explanation claims? | yes/no | the jury (code already checks that the quote exists; this checks the meaning) |
| J2 | Which cause do the lines support best: pH, corona, ions, label error, extraction error, unexplained? | choice | the jury |
| J3 | Should a careful reader abstain on this evidence? | yes/no | the jury |
| — | Does the arithmetic or derivation hold? | — | **code, never a judge.** Derivation is where judges fail (arXiv 2609.26550), and the 1.9 coincidence is exactly that case |

**Judging the judges (meta-evaluation, before any judge score is used).**
- **Agreement.** Each judge's agreement with Martin's 30 labels and with the trap set: accuracy
  and Cohen's κ. A judge enters the jury only above a threshold written in the PREREG
  (proposed: κ ≥ 0.6, every trap caught).
- **Calibration.** For tier 1's probabilities (Nimble, Decision-1): Brier score and a reliability plot.
- **Bias probes.**
  - Swap the order of the options.
  - Pad a wrong explanation with fluent, confident text.
  - Self-preference: add a Claude judge as a probe only, and compare its leniency on
    Claude-written explanations with the jury's.

**Then the scale-up.** Run the jury over all candidates × V0–V3, and report:
- the judge-estimated false-explanation rate with a bootstrap interval, next to the
  human-measured one on the 30;
- where the jury disagrees with itself.

**A three-tier cascade, decision models first** (verified 2026-10-19):

| tier | judge | what it is | access | caveat |
|---|---|---|---|---|
| 1 | **Nimble** (Bespoke Labs; HF `bespokelabs/Bespoke-Nimble-9B` v1–v3) | LoRA of Qwen3.5-9B. Reads one-token answer logits and returns a probability per option over a flat enum/boolean schema | **local**: `ollama pull nimble` (v2), so no paper text leaves the Mac | licence not stated on the repo, so check it; prompts up to 8 192 tokens; labels synthetic; calibration varies by set |
| 1 | **Microsoft-Decision-1** | post-trained from Qwen3.5-9B; typed choices with probabilities | OpenRouter (already configured) | **same base as Nimble**, so tier 1 counts as one family; vendor benchmarks only |
| — | Jev (TypeSafe) | decision-only judge; arXiv 2609.26550 | paid API | **skipped** (Martin, 2026-10-19): tier 1 is Nimble + Decision-1 |
| 2 | LLM jury | 3 non-Claude families, J1–J3 with a short reason | OpenRouter | the costliest tier; verbosity and position probes apply |
| 3 | Martin | the ground truth | — | minutes are counted |

**How it routes.**
- Tier 1 answers J1–J3 as typed fields.
- A field whose top probability clears the frozen threshold is accepted. The rest go to tier 2.
- A jury that is not unanimous escalates to Martin.
- Fields are scored independently (Nimble's documented limit), so consistency across J1–J3 is
  checked in code. For example, "abstain = yes" together with a confident cause is a conflict.

**Calibration and independence are measured, not assumed.**
- **Calibration.** Fit tier 1's temperature on half of the human labels plus the traps, and report
  ECE and Brier on the other half with bootstrap intervals. 30 labels make this noisy, so label
  60 if time allows.
- **Independence.**
  - The pairwise correlation of error indicators between judges (phi).
  - The share of tier 1's confident errors that tier 2 repeats. A follow-up summary, not yet
    verified (emergentmind 2609.29769), claims LLM judges repeat nearly all of Jev's confident
    errors. If that holds here, the cascade saves cost but adds no safety, and the talk says so.
- **Report per tier:** accuracy against Martin, escalation rate, cost, latency, and human minutes
  saved.

Out of scope: DecisionLLM-style offline reinforcement learning for multi-step decisions (bidding,
planning). Our judging is a single-step typed choice, which is what decision models are for.

**Where it also helps the grid.** Kind D (mechanism questions) has no answer key. A calibrated
jury is the only scalable judge there, and it is the case where retrieval should win.

**Cost.** About 67 candidates × 4 configs × 3 judges ≈ 800 short calls, plus the probes. Small
next to the reading.

---

## 4. Pre-registration — written before the confirmatory runs

`docs/PREREG_2026-10.md` gets one entry per test, committed before the run. **Martin writes the
predictions**: the direction, a number or range, and what would make him wrong.

| test | data | the prediction to write |
|---|---|---|
| H2b | the 1 046 rows, CV grouped by paper | the order of R² across the five feature sets; R²(all) |
| H3a-soil | the soil dataset, untouched | sign and size of ρ(lower limit, median); does rescaling shrink disagreement at the 201 places? |
| H3c | MPsizeBase, 203 distributions | the share of α within 1.6 ± 0.3 |
| H5 | Q2, V0 to V3 | V0's false-explanation rate; the V1 and V2 deltas |
| Judges | tier 1 and the jury on the 30 labels and the traps | the κ entry threshold; tier 1's escalation threshold (frozen before the scale-up, as arXiv 2609.26550 does); which bias probe a judge fails |

---

## 5. Twelve days

| when | what | output |
|---|---|---|
| 18–19.10 | Extension data: soil, MPsizeBase, Weser, the zeta size-bin rule (pinned, second-route tests) · PREREG written and committed | `tool/p2` extended; `docs/PREREG_2026-10.md` |
| 20–21.10 | H2b model · H3a-soil · H3c α · P2 page updated with confirmatory results, marked as such | P2 v4 |
| 22–24.10 | H5: system skeleton (queue, reader, verify, challenge) · Q2 run V0–V2 · Martin labels 30 · V3 on disagreements | `src/mnp/validate/`, run ids |
| 24–25.10 | Judge layer (§3.4): jury calibration on the 30 labels + traps · bias probes · scale-up over V0–V3 · metrics table | judge run ids, the metrics table |
| 26–27.10 | Deck in the new order: hypothesis, method, evaluation, result; script cards | deck v4, script v5 |
| 28.10 | Rehearsal | |
| 29.10 | Buffer | |

**Cut line, in this order if late:**
1. V3;
2. Q3 rediscovery;
3. H3c;
4. the P2 page polish.

Never cut: the PREREG entries, Martin's 30 labels, the V0 → V2 delta.

---

## 6. How the talk changes

| | |
|---|---|
| **Opening** | motivation (charge decides biology), what zeta is |
| **Then** | the five hypotheses as the abstract's own sentences |
| **H1** | today's absence slides, now with "we checked the supplements: 8.1 % → 9.2 %" |
| **H2** | P2 Part 1 (size explains nothing; the amine sign flips), then the H2b model as a test, not a picture |
| **H3** | the Weser pair (×5 237), the rectangles, then the soil result as the confirmation |
| **H4** | same tow, two values, and the 1.9 trap |
| **H5** | the system, the ablation ladder, the false-explanation rate per rung, the cost per rung |
| **Close** | what AI can and cannot do here, and the call |

---

## 7. Open, needs Martin

1. **Write the PREREG predictions** (§4) before the runs. They are his, not the system's.
2. **The 30 labels for Q2.** About 2–3 minutes each with the paper open, done blind.
3. **NCEI contact about 0.085 m.** Ask, or present it as "differs from the paper's stated depth".
4. **The deck order** (handoff §6.1) is replaced by §6 here. Confirm.
5. ~~Jev~~: skipped 2026-10-19.
7. **Predictions.** Martin has none of his own (2026-10-19), so `docs/PREREG_2026-10.md` derives
   each prediction from published values or physics, never from the data being tested, and
   Martin accepts or edits each before it is committed.
6. **Nimble's licence:** check the Hugging Face model card before it appears on a slide.
