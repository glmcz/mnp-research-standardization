# ideas.md — session handoff, 2026-09-17

Everything proposed in the 2026-09-17 scoping session: what was accepted, what was
**rejected and why**, every number that was measured, and what is still open.

Read this before proposing anything. Several framings below were already tried and turned
down; re-proposing them costs a round trip.

Companions: `docs/PLAN_2026-09-28.md` (current plan), `docs/FINDINGS.md` (running experiment
log), `docs/METHODOLOGY.md` (how the corpus was built, 2026-09-13),
`SESSION_2026-09-15_INDEPENDENCE_AND_SWEEP.md` (state before this session).

---

## 1. The situation

- Talk: *"From Detection to Predicting Micro- and Nanoplastic Behavior: Limitations of Current
  Methods and the Need for Multiparametric Standardization"*.
- **The abstract scored low — at an AI conference.**
- **Deadline 2026-09-28.** This session ran 2026-09-17, so eleven days, evenings.
- Martin is a AI / Python / energy-markets engineer. Not a colloid chemist. That is a fact about
  the method, not a caveat.

**Diagnosis, agreed:** the abstract is not wrong, its **tense** is. "Artificial intelligence"
appears exactly once — final sentence, future tense, hedged: *"standardized multiparametric
datasets could also provide a foundation for applying artificial intelligence methods…"*.
At an AI venue a promise is not a contribution.

**Martin's ruling: the abstract stays exactly as written.** The fix is to **deliver that
closing paragraph** and present it in the past tense, with an evaluation.

---

## 2. Rejected — do not re-propose

| # | Idea | Why it was rejected |
|---|---|---|
| R1 | Rewrite the abstract for an AI audience | Martin: abstract stays. Its argument is the argument |
| R2 | Headline = "LLM judges are unreliable" (κ = −0.05) + prompt provenance | 2023 material. Martin: *"seems to me as easy case and not from senior AI engineer"* |
| R3 | Posterior-information-gain ablation: NPE + SBC, posterior entropy vs reporting completeness | Claude's idea. Genuinely sound, **not this talk**. Killed by Claude to make room |
| R4 | Thesis = "how to teach a system a domain you don't know", five layers of borrowed expertise | Good material, superseded by the dataset framing. **Survives as slides**, not as the spine |
| R5 | Thesis = the multi-agent extraction system, validator tiers 1–3, ablation A/B/C/D | Superseded. Best failure stories survive as slides |
| R6 | Ship the dataset labelled "annotated by Claude, not yet audited" | Martin: *"not acceptable, since even creation of datasets need reliable reproducable way, so other could validate and come to the same results"* |
| R7 | Call the paper→IR converter a "transformer tool" | At an AI venue that word is the architecture. It will derail the first question |
| R8 | Hand the agent raw JATS XML | **Measured: 7.80× the tokens** of plain text (E1) |
| R9 | JSON as the agent-facing reading format | **Measured: 1.45×**, buying the agent nothing a line number gives at 1.02× (E1) |

---

## 3. Accepted direction

**Ship a dataset an agent queries instead of parsing papers — and a reproducible methodology
for building one.**

Working name **MNP-KB**. Four parts:

| | part | state |
|---|---|---|
| 1 | dataset — conditioned measurement records, provenance, **explicit absence** | 1 890 rows / 491 papers / 151 materials, **exists** |
| 2 | schema — pydantic → JSON Schema 2020-12 → reporting checklist | exists (`out/schema/`, `out/checklist.md`) |
| 3 | retrieval layer — structured filters + semantic over evidence | to build |
| 4 | agent interface — MCP server, scoped in `docs/ARCHITECTURE_PLAN.md` §9 | to build |

Plus the evaluation against a naive RAG baseline, which is what makes it a talk and not a
data release.

**Two hard commitments from Martin:**
1. **A vanilla dataset v0 ships by 28.9 regardless.** Parquet + JSONL + JSON Schema + dataset
   card, built from the existing 1 890 rows so it depends on nothing else landing.
2. **Claude works in a loop** — iterate, document findings, return with a final methodology
   Martin can present with confidence on **accuracy · cost · throughput/time · size ·
   packaging** (importable Python package for RAG/LLM systems).

---

## 4. The architecture that came out of it

```
  JATS XML  (vendored, sha256-pinned, 858 files — Europe PMC serves this; not a choice)
        |
        |   DETERMINISTIC: no model, no network. Anyone regenerates it identically.
        |   typed sections, stable line/span ids, tables linearised with header binding,
        |   quantity spans (number + unit + normalised SI + raw), condition index,
        |   cross-refs resolved or explicitly marked unresolvable
        v
  canonical document
        |
        +---> md_linenum   ->  the AGENT reads this            (1.02x plain text)
        |
        +---> ir.json      ->  the MACHINE resolves this       (never read whole)
                               span ids, quantity index, schema validation

  RECORD cites (doc_id, line) -- not quote text.
```

### Why this shape

- **Mixed content** (italic species name, subscript, formula, cross-ref anchor *mid-sentence*)
  is XML's one genuine advantage and JATS uses it heavily. Resolution: plain normalised `text`
  (what the model reads) + **offset-based `marks` sidecar** (what markup was there). Offsets,
  not nesting — the ProseMirror / HF-tokenizer-offset solution. Nothing lost, nothing nested.
- **Line citation removes a failure mode structurally.** `verify_row` currently "requires the
  quoted evidence to be a substring of the article" (`src/mnp/extract/zeta.py:5`) — the
  mechanism **five independent workers gamed** by trimming evidence to pass a guard that
  punished the fuller quote. Under line citation the agent returns a *reference*, does not
  author the evidence, and **has nothing to trim**.

---

## 5. The reproducibility argument (replaces "annotated by Claude")

**The precise gap.** `report reproduce` rebuilds every committed artefact byte-for-byte with
the network refused, in 21 s — but it reproduces **from stored LLM output**, not from the
papers. The dataset is reproducible *downstream of the reading*, not *through* it.

**The honest reframe.** Nobody can promise a third party identical rows from a different
model. What they can promise:

1. the **substrate** regenerates byte-for-byte, deterministically, offline;
2. a third party re-runs extraction with their own model and reports **per-span agreement**
   against the published rows;
3. that agreement number *is* the reproducibility claim — a measured envelope, not an
   assertion.

**Per-row confidence tiers, shipped as columns** (so downstream agents filter on
reproducibility rather than trusting the table):

| signal | how |
|---|---|
| deterministic backing | the regex scanner independently found the value — **0.98 recall, measured** |
| cross-family agreement | ≥2 *different-family* models bind the same spans |
| human κ | stratified audit, published with a CI |

**The inversion worth leading with: absence claims are the dataset's *most* reproducible
part.** "Ionic strength not reported" is checkable by a deterministic scan — if no
ionic-strength quantity span exists anywhere in the document, the claim holds **with no model
involved**. The abstract is *about* absence, so the dataset's central claims are its most
verifiable ones. That is backwards from every literature-mined dataset in the field.

---

## 6. Every measured number

### 6.1 The corpus and dataset (computed 2026-09-17 from `out/tables/d1_zeta_table.csv`)

| | |
|---|---|
| rows / papers / distinct materials | **1 890 / 491 / 151** |
| rows with a printed value | 1 384 (506 report a measurement with no retrievable number) |
| **fully conditioned rows** (`conditions_complete`) | **62 — 3.3 %** ← the abstract's thesis in one number |
| **evidence stitched from ≥2 separate passages** | **1 169 — 61.9 %** ← chunk-and-embed cannot work here |
| `evidence_location` naming ≥2 locations | 184 — 9.7 % |
| `evidence_verified` | **1 890 / 1 890 — 100 %** |
| ionic strength reported (row level) | 269 — 14.2 % |
| pH reported | 402 — 21.3 % |
| temperature reported | 529 — 28.0 % |
| medium reported | 1 572 — 83.2 % |
| instrument reported | 1 679 — 88.8 % |
| distinct `prompt_sha256` across the table | **2** — prompt provenance is currently coarse |
| papers omitting ≥1 of the five conditions | **97.1 %** (`d1_stats.json`) |
| corpus | 858 XMLs, 27.7 MB, sha256 `9791cc01…` |

Top flags: `value_not_printed` 357, `value_not_printed;unit_assumed_mV` 99, `approx` 27,
`value_is_range` 20.

### 6.2 E1 — representation cost (50 gold papers, `cl100k_base`)

| representation | tok/paper | × md_plain | addressable to |
|---|---|---|---|
| `xml_raw` | **41 127** | **7.80** | xpath |
| `text_current` = `md_plain` | 5 273 | 1.00 | nothing |
| `md_anchored` | 5 309 | 1.01 | section |
| **`md_linenum`** | 5 373 | **1.02** | **line** |
| `md_spanids` | 5 908 | 1.12 | sentence |
| `ir_json` | 7 626 | **1.45** | sentence |

Content-block composition per paper: keyword windows 1 662 (31.8 %), methods 1 236 (23.6 %),
tables 733 (14.0 %), figure captions 798 (15.3 %), extra sections 464 (8.9 %), abstract
333 (6.4 %). Keyword windows are **additive, not duplicated** — 0 % overlap with methods or
extra sections; they pull from Results/Discussion, which are not otherwise included.

**Ceiling:** the paper is ~5.3 k of the ~17.8 k tokens/paper measured in wave 1 — about
**30 %**. The whole 1.00→1.45 spread moves the total budget ~13 %. Representation is worth
getting right and is **not** where an order of magnitude lives.

### 6.3 Pipeline quality (from `mnp.eval all`)

| stage | metric | score |
|---|---|---|
| parse | span recall | 1.00 |
| scan | recall of gold values | **0.98** |
| read | row value precision | 0.81 (**0.47** with PMC13520016 included) |
| coerce | exact-match accuracy | 1.00 |
| verify | fabrication detection | 1.00 (7/7) |

**One paper — one *measurand* error, not a parsing error — moved headline precision by 34
points.** Generic extraction metrics on this corpus are dominated by domain-specific referent
errors.

### 6.4 Throughput and human cost

| stage | papers | workers | tok/paper | wall clock |
|---|---|---|---|---|
| pilot | 10 | 2 | ~21 k | 3 min 37 s |
| slice | 28 | 4 | ~19 k | ~10 min (longest worker) |
| wave 1 | 80 | 8 | **~17.8 k** | one wave, parallel |

Cost per paper **fell 15 % as batch size grew**; cause unresolved (brief amortisation vs
within-batch warm-up), distinguishable by one shuffled half-size batch. Deterministic half of
the pipeline: **21 s** for 858 XMLs + 845 records — not worth parallelising.

**Human anchor: 17 expert decisions moved >1 000 rows and up to 5 points of headline.**
Expert attention, not tokens, is the binding constraint.

### 6.5 Failure modes with receipts (the defensibility table)

| Component | Forced by | Count |
|---|---|---|
| Disjoint claims (`FOR UPDATE SKIP LOCKED`) | first run gave two workers the same papers | — |
| Leases, requeue | ten workers died to a rate limit; recovery was luck | 10 |
| Brief hash enforced at ingest (`exit 2`) | records untraceable to the prompt that made them | 833 of 845 |
| Verbatim quote guard | fabricated quotes, each reached production once | 7 of 7 |
| Condition must be in the row's **own** evidence | conditions stitched across experiments | 1 016 rows / 264 papers |
| Refuse row on unrecognised unit | `normalise_unit → None` read as "nothing was printed", filled with the conventional default under a flag asserting nothing was printed | 1 defect class |
| Guard scoped to the number-bearing quote piece | whole-quote guard punished the **fuller** evidence; workers trimmed to pass | **5 independent workers** |
| Panel routes, never decides | detection 17/17, decision at chance | κ = **−0.05** |
| `not measured` never 0.00 or 1.00 | both are claims nobody checked | — |
| Replay with network refused | published tables that no longer followed from the data | 3 tables, 91 records |

Majority-of-3 judging **would** have got all three ratified rules right — 2–1 each time, 4–6
cases per rule. **Martin refused to rely on it.** Keep that refusal in the talk; it is the
most senior thing in the repo.

---

## 7. Experiment agenda

| | experiment | ground truth | status |
|---|---|---|---|
| **E1** | representation bake-off — XML vs text vs markdown variants vs JSON IR | tokens & bytes | **DONE**, `docs/FINDINGS.md` |
| **E2** | accuracy: does `md_linenum` extract as well as plain text? does the condition index reduce reads or relocate cost? | `gold_50.csv` | **next**, ~0.9 M tokens/arm |
| E3 | absence detection: deterministic scanner vs LLM assertion vs both | `*_reported` booleans | open |
| E4 | cross-family agreement envelope on a shared substrate | per-span agreement | open |
| E5 | cost/throughput curve; settle the 21k→19k→17.8k batch effect; **measure the brief's share of the 70 % that is not the paper** | measured | open |
| E6 | size on disk; what a pip package ships | measured | open |
| E7 | naive RAG baseline vs MNP-KB — **the result** | see §8 | open |

---

## 8. The evaluation that makes it a talk (E7)

Two systems, one query set, ground truth from `gold_50` and from the dataset's own
`*_reported` booleans.

| kind | query | n *(projected)* | ground truth |
|---|---|---|---|
| **A — conditioned lookup** | "zeta of PS-COOH in seawater, and at what ionic strength?" | ~30 | `gold_50.csv` |
| **B — absence** | "what ionic strength was used in PMC…?" where none was reported | ~30 | `ionic_strength_reported = False` |
| **C — comparison** | "papers reporting PS zeta at I between 100–200 mM" | ~10 | structured filter |

Metrics: answer accuracy, **fabrication rate on kind B**, citation correctness.

**The baseline must be built to win, or the result is worthless.** Claude owns both systems;
*"you strawmanned the baseline"* is the obvious kill shot. So: section-aware chunking with
JATS metadata retained (not blind 512-token splits), competent embedder **plus a reranker**,
same reader model, tuning procedure published — and **report where RAG wins**, which it will,
on mechanism and discussion questions the KB has no field for.

`torch>=2.2` is already a dependency (sbi pulls it), so a local embedding model adds no heavy
dependency and preserves the property that **no API key is configured**.

### Why chunk-and-embed structurally cannot do this

1. **61.9 % of records need ≥2 separate passages.** Worked example, `PMC10458608-r1`,
   verbatim: *"The zeta potential (ζ) of nanoparticles was also measured in water, CCM, and
   chyme. || The zeta potential or surface charge of nanoparticles was measured from pH 2 to 7
   in water, CCM, and chyme using a Stabino Zeta (Microtrac GmbH…)"* —
   `evidence_location: Section 3.1 / Methods 2.1`. Retrieve either sentence alone: fluent,
   on-topic, **no number, no ionic strength**. The record says so:
   `value_text = "not printed"`, `ionic_strength_source = "unreported"`.
2. **Absence has no passage to retrieve.** RAG returns the nearest number and the reader
   states it. The KB answers from a boolean.
3. **Numeric range comparison is not a similarity operation** — and it is exactly the
   comparability the abstract asks for.

---

## 9. Ideas parked, not killed

- **Retrieval over ratified precedent.** `tests/edge/key.yaml` (69 questions, 8 answered)
  becomes a live index: a sentence that looks like a decided case retrieves the nearest ruling
  *and its reasoning*. One expert-hour applied thousands of times.
- **Question deduplication as a priority signal.** `S5`/`S24`/`S25`/`S26` are one question in
  four wordings; convergence count ranks what to ratify next. Currently a human instruction
  ("watch for recurring gaps across ≥2 workers").
- **The measurand judge.** "If the plastic had never been added, would there still be
  something in the cuvette with a zeta potential?" — a counterfactual over experimental
  procedure, answered from prose. Current detector is 3 regexes over 10 papers / 28 rows.
  **Caution, from the repo's own docstring:** a naive scan got 25 hits, **16 of them "filtered
  prior to HPLC analysis"**. Topically identical to the true positives, decision-relevantly
  opposite. Generic embeddings will make the same mistake — the deciding fact is *what the
  removal precedes*, a relation, not a topic. Bake-off: 3 regexes vs cosine vs
  regex-recall→rerank vs contrastive on ratified pairs. **If cosine loses to three regexes
  written by a non-expert, that is a finding and it goes on a slide as-is.**
- **`tests/edge/key.yaml` as a benchmark.** 69 expert-authored questions, each bound to a real
  PMCID, 61 unlabelled. Five kinds needing different judges: measurand, material boundary,
  scope/carry, provenance, undecidable. For the **boundary** kind the field itself has no
  consensus — so the judge's target cannot be the label, only *"a boundary case is present,
  and it is this one."* Which is exactly the split already measured: 17/17 detection, chance
  on decision.
- **Schema induction from reader disagreement.** `out/checklist.md` records that **no ontology
  term exists for ionic strength** in ENM/NPO/CHMO/ENVO; only **3 of 17** checklist rows carry
  a CURIE. The fields readers keep inventing are the fields the ontology is missing.
- **Contrast case.** `docs/ARCHITECTURE_PLAN.md` §8 names **caNanoLab** and
  **eNanoMapper/NanoCommons** — existing places where the conditions *are* recorded.
- **OpenAlex expansion.** Would roughly triple the corpus (3 513 works vs 858 fetched) and
  **changes every denominator — that is a new study**, run as `run_id=2026-xx-openalex`.

---

## 10. Open, needs Martin

1. **S5 / S29 / S31 rulings** (~2 h). S5 first: four workers converged on variants, and it is
   the commonest sentence shape in the corpus, not an edge case. **Gates the sweep** — a
   ruling applied before is free; after, it means re-reading the rows it touches.
2. **κ audit, blind, `data/interim/annotation/audit_10.csv`** (~1 h). Consider widening to ~30
   papers stratified by flag type — it is the calibration of the whole dataset, not a footnote.
3. **Dataset name and licence.** CC-BY is the default expectation for a citable scientific
   dataset. Source XMLs are open access but **licences vary per paper** (`articles.parquet`
   carries a `license` column). The card must state what is redistributed — extracted values +
   short verbatim quotes — versus what is not (full texts).
4. **Retrofit vs re-extract.** Retrofit = locate the existing 1 890 verified quotes into IR
   spans (~1 session; they are 100 % verified so they *will* locate), but the binding
   judgement still comes from the original run. Re-extract = every row born span-cited and
   cross-family, ~17.5 M tokens, **will not finish by 28.9**.
   **Claude's recommendation: retrofit everything + re-extract a stratified ~100-row sample
   with a second model family.** Span citations across the whole dataset *and* a measured
   agreement envelope, in budget. v1.0 ships tiered; v2.0 fully re-extracted after the talk.
5. **Talk length and audience level** — decides how much of §6.5 survives.

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| "You strawmanned the RAG baseline" | §8 — strong baseline, tuning published, report where it wins |
| "Your ground truth is your own model" | κ audit; until filled the caveat ships **on the dataset card**, not just a slide |
| "n = 491 papers, one database" | Say it. OpenAlex triples it and changes every denominator — a new study |
| Live MCP demo fails on stage | Record it too. Never demo live-only |
| Sweep overruns | It is the last item for a reason. Cut it first — no headline moved >0.4 pts across all four S-rulings, so D1 is stable and the sweep buys traceability, not the number |

---

## 12. File map

| Path | What |
|---|---|
| `Martin - From Detection to Predicting Micro.md` | the abstract — **unchanged, stays as written** |
| `docs/PLAN_2026-09-28.md` | current plan (dataset + RAG eval framing) |
| `docs/FINDINGS.md` | running experiment log; E1 done, with its correction |
| `docs/METHODOLOGY.md` | how the corpus was built (2026-09-13), deterministic/judgement split |
| `docs/DECISIONS_NEEDED.md` | Q1–Q3 ratified 2026-09-13; the judge-panel κ tables |
| `docs/DEMANDING_PROCESSES.md` | pilot→slice→sweep design and measured costs |
| `docs/ARCHITECTURE_PLAN.md` | §8 sources/OpenAlex, §9 MCP scoping |
| `tests/edge/key.yaml` | 69 adjudication questions, 8 answered |
| `out/tables/d1_zeta_table.csv` | the dataset, 1 890 rows × 39 cols |
| `data/interim/annotation/gold_50.csv` | gold set — **annotated by Claude, not yet audited** |
| `data/raw/epmc/xml/` | 858 vendored JATS XMLs, hash-pinned |
| `scratchpad/e1b_addressing.py`, `e1b.csv` | E1 script and raw results (session scratchpad, **not committed**) |

---

## 13. Standing rules from this session

- **"not measured" is never 0.00 and never 1.00** — both are claims nobody checked.
- **Never impute.** `normalise_unit → None` once meant "nothing was printed" and got the
  conventional default. Absence is a value, not a gap.
- **Verify against `extractions.jsonl`, never a worker's own prose.** Three workers reported
  success having written nothing.
- **Two workers flagging the same gap is a rule gap, not a confused worker.**
- **A worse brief spent on 491 papers is the expensive mistake** — gate before widening.
- **Mark what was ratified by judgement.** `docs/DECISIONS_NEEDED.md` names its own limit:
  *"There may be an external standard for this. ISO 13099 … I have NOT verified what they say
  about these three specific questions."* That line is the credibility of the whole approach.
