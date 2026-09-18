# Findings — how an agent should be given a scientific paper

A running log. Each entry states what was measured, on what, and what it changes.
Numbers are **measured** unless marked *projected*. Corrections stay in place, marked, rather
than being edited away.

Scoring axes, fixed: **accuracy · cost · throughput/time · size · packaging**.

---

## E1 — representation bake-off

**Question.** An agent must be handed the paper somehow. Which serialisation, and what does
citability cost?

**Method.** 50 gold papers (`gold_50.csv`), parsed with the existing `mnp.corpus.jats`
parser, re-serialised seven ways, measured with `cl100k_base`. Every markdown and JSON
representation is built from **one shared block set** — abstract, methods, extra sections,
keyword-context windows, tables (caption + TSV + footnotes), figure captions — so the content
is identical across rows. Sanity check: `md_plain` reproduces `text_current` to the token
(5 273 both), which is what a shared block set should do.

Script: `scratchpad/e1b_addressing.py`. Raw: `scratchpad/e1b.csv`.

| representation | tok/paper | median | × md_plain | addressable to |
|---|---|---|---|---|
| `xml_raw` — JATS as served | **41 127** | 36 766 | **7.80** | xpath |
| `text_current` — what readers get today | 5 273 | 4 896 | 1.00 | nothing |
| `md_plain` | 5 273 | 4 896 | 1.00 | nothing |
| `md_anchored` — `{#section}` anchors | 5 309 | 4 924 | **1.01** | section |
| **`md_linenum`** — `N\t` prefix per line | 5 373 | 4 980 | **1.02** | **line** |
| `md_spanids` — `[sNNNN]` per sentence | 5 908 | 5 528 | 1.12 | sentence |
| `ir_json` — typed spans | 7 626 | 6 800 | **1.45** | sentence |

### What it says

1. **Never hand an agent raw JATS.** 7.8× the tokens for content a parser already extracts.
   This is the answer to "why not XML": XML is the *source* format, not the *reading* format.
2. **Exact citability costs 2 %.** Line numbering is within noise of plain text and gives a
   stable address for every line. Sentence-level IDs cost 12 %; full JSON costs **45 %**.
3. **JSON's 45 % is paid on the wrong path.** The reading path is where the tokens go, and
   JSON's structure buys the *agent* nothing it cannot get from a line number. JSON's value is
   machine-side: validation, indexing, deterministic resolution.

### What it changes

Two representations, two consumers, neither paying for the other:

```
  JATS XML (vendored, sha256-pinned)
        |
        |  deterministic, no model, no network
        v
  canonical document  --+--> md_linenum   -> the AGENT reads this        (1.02x)
                        |
                        +--> ir.json      -> the MACHINE resolves this   (never read whole)
                                             span ids, quantity spans,
                                             condition index, schema
```

The record cites `(doc_id, line)` — not quote text.

### The consequence that is worth more than the tokens

`verify_row` currently "requires the quoted evidence to be a substring of the article"
(`src/mnp/extract/zeta.py:5`). That is the mechanism **five independent workers gamed** by
trimming their evidence, because the whole-quote guard punished the more complete quote.

Under line citation the agent returns a **reference**, not text. It does not author the
evidence, so there is nothing to trim: verification becomes "does line 142 of the canonical
document contain this number", a deterministic lookup. **The failure mode is removed by the
representation rather than patched by a guard.**

### Correction

A first pass reported `md_anchored` at **0.72× — cheaper than plain text.** That was wrong:
that markdown build omitted the keyword-context windows, which are **1 662 tok/paper, 31.8 %
of the content**, and are genuinely additive (a prefix check found **0 %** of window text
repeated in methods or extra sections — the windows pull from Results and Discussion, which
are not otherwise included). With the content equalised, markdown is **cost-neutral**, not
28 % cheaper. The 1.22× first reported for `ir_json` was understated for the same reason; the
fair figure is **1.45×**.

### Ceiling on what representation can save

Wave 1 measured **~17.8 k tokens per paper end to end**, of which the paper itself is
**~5.3 k — about 30 %**. The rest is system prompt, brief, reasoning and output. So the
*whole* spread between the cheapest and most expensive sane representation (1.00 → 1.45) moves
the total budget by roughly **13 %**. Representation is worth getting right, and it is not
where an order of magnitude lives. Raw XML would have been an order of magnitude — in the
wrong direction.

### Not yet measured

Cost is settled; **accuracy is not**. Whether `md_linenum` extracts *as well as* the current
plain text — and whether the condition index changes what a reader finds — is E2, and it
needs real reads scored against `gold_50`.

---

## E1b — does the corpus fit in a context window?

**Question.** Before measuring whether retrieval helps, settle whether it is needed at all. If
the papers fit in the model's context, retrieval is optional and the KB has to justify itself
against simply reading everything.

**Method.** Arithmetic over E1's measured per-paper token counts. **No model was run and no
tokens were spent.** Against a 1 M-token window.

| representation | tok/paper | corpus (491 papers) | fits 1 M? | papers per 1 M |
|---|---|---|---|---|
| `xml_raw` | 41 127 | 20 193 357 | no | **24** |
| `md_plain` | 5 273 | 2 589 043 | no | 189 |
| **`md_linenum`** | 5 373 | **2 638 143** | **no** | **186** |
| `ir_json` | 7 626 | 3 744 366 | no | 131 |

### What it says

1. **The corpus does not fit, in any representation.** At the cheapest sane one it is
   **2.64× too large**. This is a stronger claim than a measurement and it cost nothing: long
   context does not reach this corpus, so retrieval is not optional at corpus scale. Whether it
   *helps* is still open — that is the eval.
2. **At `gold_50` scale it fits comfortably** — 50 papers is **268 650 tokens**, about a
   quarter of the window. So "put it all in context" is a fair rival there, and that is the
   only scale at which it can be run honestly. Cell A is specified at gold-50 scale for this
   reason, not for cost.
3. **The converter has a second job.** It buys **7.65× more papers per window** than raw JATS
   (24 → 186). Line-addressability was its first argument; this is its second, and it matters
   more, because it is what puts long context on the table at all rather than what makes it 2 %
   cheaper.

### Caveat on the inputs

Every number above is derived from E1's `cl100k_base` counts. **E1 cannot currently be re-run
in this repo**: its script lived in `scratchpad/` and is gone, and `tiktoken` is not a declared
dependency. The arithmetic here is reproducible; the constants it multiplies are not, yet.
Re-committing E1 as a real experiment with the dependency declared is queued.

---

## E2b — how often is the latent surface state even mentioned?

**Question.** `AGENT_MNP_LEARNING_APPROACH.md` proposes a third schema layer for latent surface
state, with 23 candidate fields. Before extracting any of them: how often does a paper in this
corpus mention the concept at all? A field nobody reports is not a column, it is a sentence.

**Method.** Case-insensitive regex over `full_text` of all 858 vendored XMLs, 851 of which
carry retrievable text. **No model, no tokens.** This counts *mentions*, so every figure is an
**upper bound** on how often the thing is reported as a measurement condition.

| concept | papers | % | shape it earns |
|---|---|---|---|
| weathering / aging | 656 | 77.1 % | column |
| oxidation | 395 | 46.4 % | column |
| sonication | 392 | 46.1 % | column |
| additives / plasticiser | 277 | 32.5 % | column |
| abrasion / fragmentation | 239 | 28.1 % | column |
| radical | 193 | 22.7 % | column |
| protein corona | 181 | 21.3 % | column |
| biofilm | 105 | 12.3 % | column |
| **zeta conversion model** (Smoluchowski / Hückel) | **48** | **5.6 %** | column, and see below |
| contact electrification / triboelectric | 11 | 1.3 % | one sentence |
| charge heterogeneity / charge mosaic | 8 | 0.9 % | one sentence |

### Read the high numbers sceptically and the low ones straight

The loose patterns inflate. `corona` catches coronavirus; `aged` and `radical` catch ordinary
prose. So 77.1 % for weathering is an upper bound that is probably far above the truth.

The **low** numbers are the trustworthy ones, because their patterns admit almost no false
positives. `Smoluchowski` and `Hückel` are not words that appear by accident.

### The number worth taking to the talk

**94.4 % of papers report a zeta potential without naming the model that produced it.**

Zeta is not measured. Electrophoretic mobility is measured, and zeta is a model-dependent
conversion of it. Smoluchowski and Hückel differ by a factor of **1.5** and are valid in
opposite κa regimes. So for 19 papers in 20, the reported number is underdetermined *before*
any question of missing conditions arises.

This is a different and arguably harder claim than `conditions_complete = 3.3 %`. That one says
the context is missing. This one says **the reported quantity itself is not fully defined**.

### The awkward part, stated plainly

The reframe that motivated this scan rests on contact electrification and charge mosaics. Those
are the **two least-supported concepts in the corpus**, at 1.3 % and 0.9 %. They cannot be
grounded per row and must not be presented as if they were measured here. They are interpretive
background, which is what `AGENT_MNP_LEARNING_APPROACH.md` §"Near-Term Implementation" already
concludes — now with a number behind it.

---

## Open questions this raises

- Does line-number citation change extraction accuracy, in either direction? (E2)
- Does a pre-computed condition index reduce reads, or just move the cost? (E2)
- What is the token cost of the *brief* relative to the paper — 70 % of the budget is not the
  paper, and none of it has been measured. (E5)
- **At `gold_50` scale, where everything fits in context, does retrieval beat reading all fifty
  papers?** If not, retrieval is a scale argument rather than a quality one, and the honest
  headline becomes E1b's arithmetic. (cell A, `DESIGN_2026-09-17_tool-value-grid.md` §1)
- **E1 itself is not currently reproducible.** Its script was session-local and `tiktoken` is
  not a declared dependency, so the numbers this whole document multiplies cannot be
  regenerated from a clean checkout. Every downstream claim inherits that. Re-committing E1 as
  a first-class experiment is queued behind the line-addressed representation, which is one of
  the arms it needs to measure.
