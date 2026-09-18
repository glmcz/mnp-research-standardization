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

Script: **`uv run python -m mnp.report e1`** (`src/mnp/report/e1.py`, serialisers in
`src/mnp/corpus/represent.py`). Raw: `out/tables/e1_representation.csv`, committed and
inside the replay. *Was* `scratchpad/e1b_addressing.py`, which was session-local and is gone —
see the re-run note below.*

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

~~Every number above is derived from E1's `cl100k_base` counts. **E1 cannot currently be re-run
in this repo.**~~ **Resolved 2026-09-18.** `report e1` rebuilds the bake-off in 2.4 s, offline,
inside the replay. Six of seven arms reproduce the published figures; `xml_raw`, `text_current`
and `md_plain` land on them exactly, mean and median.

`ir_json` does **not** reproduce: 9 384 measured against 7 626 published, **+23 %**. E1 wrote
"typed spans" and never wrote the schema down, so there is nothing to reproduce against. Five
shapes were measured, spanning 6 826 to 9 384, and the published figure sits between two of
them. **Read that row as 1.3×–1.8× depending on schema**, not as 1.45×. E1b's conclusion holds
either way and gets stronger: at 9 384 the corpus is 4 607 544 tokens and **106** papers per 1 M
window rather than 131.

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

### Correction — the denominator was wrong

The 5.6 % / 94.4 % above divides by **all 851 readable papers**. That is the wrong denominator:
a paper that reports only an electrophoretic mobility needs no conversion, so it cannot be
faulted for not naming one. The right denominator is papers that report a **zeta potential**.

Recomputed on that basis, with the pattern widened to include Henry's function as well as
Smoluchowski and Hückel:

| denominator | n | name a model | do not |
|---|---|---|---|
| papers reporting a zeta value | 485 | 33 — 6.8 % | **452 — 93.2 %** |
| papers reporting a mobility value | 13 | 6 — 46.2 % | 7 — 53.8 % |

**The headline is 93.2 %, not 94.4 %.** Use the corrected figure.

### The contrast is worth more than the headline

Papers reporting the **measured** quantity name the conversion model **6.8× more often** than
papers reporting the **derived** one: 46.2 % against 6.8 %.

That is backwards from what a reader needs. A paper reporting mobility has given you the raw
observable and you could convert it yourself; it is the papers reporting zeta — where the
conversion has already been applied and baked in — that most need to say which one, and they
are the ones that almost never do.

**Caveat, stated because n is small:** the mobility group is **13 papers**. Treat the contrast
as a direction worth checking, not a measured ratio, and do not put 6.8× on a slide as though
it had a confidence interval. The 93.2 % rests on 485 papers and is solid.

### The awkward part, stated plainly

The reframe that motivated this scan rests on contact electrification and charge mosaics. Those
are the **two least-supported concepts in the corpus**, at 1.3 % and 0.9 %. They cannot be
grounded per row and must not be presented as if they were measured here. They are interpretive
background, which is what `AGENT_MNP_LEARNING_APPROACH.md` §"Near-Term Implementation" already
concludes — now with a number behind it.

---

## E2c — a paper that contradicts itself by four orders of magnitude

**How it was found.** Not by looking. A gate review claimed four rows of `PMC12598813` stored a
worker-computed ionic strength as if it were reported. Checking that claim against the article
showed the reviewer was **wrong** — the number is the paper's own — and showed something worse
that neither the extraction nor the review had noticed.

**The paper states its salt concentration twice, in two places, and the two do not agree.**

> Results: *"adding NaCl or KCl (0–30 mg L⁻¹) raises the ionic strength from 0.010 M to
> ≈0.0105 M (10 mM HEPES)"*

> Methods: *"NaCl and KCl were added in concentrations ranging from 5% to 30% (w/v) to achieve
> varying ionic strengths"*

| statement | salt | ionic strength |
|---|---|---|
| Results | 0–30 mg L⁻¹ | 10.0 → **10.5 mM**, internally consistent |
| Methods | 5–30 % w/v = 50–300 g L⁻¹ | **856 – 5 133 mM** |

**Ratio between the two: 1 667× at the bottom of the range, 10 000× at the top.** The Debye
length differs by a factor of about 40 to 70 across that gap, so the two readings describe
physically different experiments.

### What our dataset did about it

Stored **10.5 mM**, source `reported`. That is defensible — the Results sentence does print it,
and a `ionic_strength_not_in_text` flag fired only because the paper writes `0.0105 M` where the
row writes `10.5`, a unit-scale mismatch in the verifier rather than a fabrication.

But the dataset **silently chose between two contradictory statements and recorded no trace that
a choice was made.** Every guard in this pipeline passed: the quote is verbatim, the value is in
the evidence, the condition is in the row's own evidence. None of them can see a second sentence
elsewhere in the paper saying something incompatible.

### What it implies

1. **`ValueSource` has no way to say this.** Today it is `reported`, `unreported`,
   `inferred_from_named_salt`. `docs/AGENT_MNP_LEARNING_APPROACH.md` proposed a
   `contradictory` value; here is a live case that needs it. A row reading `contradictory` with
   both citations is more honest than either number alone.
2. **Verbatim verification cannot detect contradiction.** It is a per-row, per-quote check, and
   contradiction is a property of a *pair* of passages. This is the same structural point as
   kind E comparability: the fact lives in the join, not in any passage.
3. **It is not knowable how common this is.** One case was found by accident while checking
   something else. A deterministic detector — two ionic-strength statements in one paper more
   than, say, 10× apart — would be cheap and has not been run.

**For the talk this is stronger than a missing condition.** A missing condition means nobody
wrote it down. This means it *was* written down, twice, incompatibly, and every automated check
we have says the row is fine.

---

## E2d — `inferred_from_named_salt` does not record what it inferred from

**How it was found.** A gate review claimed `parse_ionic_strength` no longer produces what the
stored rows contain. That reproduces: `parse_ionic_strength("10 mM HEPES, 20 mg L-1 NaCl",
from_medium=True)` returns `(None, unreported, ['concentration_not_an_ionic_strength'])` today,
while the committed rows read `10.0 / inferred_from_named_salt`.

**Measured.** Of **141** rows whose source is `inferred_from_named_salt`, **39 cannot be
re-derived from their own `medium_text`** by the current parser.

### A wrong conclusion, recorded because the process matters more than the tidy version

The first reading of those 39 was that 14 were **imputations** — a value stored where no salt is
named. Two examples were going to carry that claim:

| row | `medium_text` | stored |
|---|---|---|
| `PMC11846901-r1` | `aqueous dispersions` | 10.0 mM |
| `PMC4958399-r1` | `PBS` | 139.7 mM |

**Both are legitimate, and the claim was wrong.** `PMC4958399` prints the composition in full —
*"1× PBS tablet (0.01 M phosphate buffer, 0.0027 M potassium chloride, 0.137 M sodium
chloride)"* — which derives to 139.7 mM, exactly as `docs/briefs/gold_annotation.md` instructs.
`PMC11846901` prints an ionic strength and names NaCl. Neither was invented.

The error was judging provenance from **one summary column without reading the paper**. That is
the same mistake the engineer gate made on `PMC12598813` in the same hour, and the same one
Card 2 made about its callers. Three instances, one session, one root cause: *a field that
summarises is not the thing the decision was made from.*

### What actually survives

**1. The provenance is unfalsifiable.** `inferred_from_named_salt` asserts that a derivation
happened. It does not record **what from**. The inputs are not stored, `medium_text` is a
summary rather than the parsed string, so for 39 rows the claim can be neither reproduced nor
refuted. This is the `verification-gap` class again: written once, never re-run. `pH_text` and
`temperature_qualifier` exist for exactly this reason on their own conditions; ionic strength
has no equivalent.

**2. One genuine parser bug, isolated and reproducible:**

| input | result |
|---|---|
| `1 mM NaCl` | 1.0 mM ✓ |
| `1 mM sodium chloride` | 1.0 mM ✓ |
| `1 mM aqueous sodium chloride (NaCl)` | **None** ✗ |

The parser binds a concentration to a salt named one way, and loses it when the salt is named
**both** ways with a word in between. It then emits `concentration_not_an_ionic_strength`, which
is actively misleading: the concentration *is* an ionic strength, and the parser simply failed
to bind it. Four rows of `PMC12700194` sit on this.

**3. The drift is real but its size is not yet known.** 39 of 141 do not re-derive; how many are
this bug, how many are the missing-input problem, and how many are something else has not been
established, because establishing it needs the papers read, not the column.

## Open questions this raises

- Does line-number citation change extraction accuracy, in either direction? (E2)
- Does a pre-computed condition index reduce reads, or just move the cost? (E2)
- What is the token cost of the *brief* relative to the paper — 70 % of the budget is not the
  paper, and none of it has been measured. (E5)
- **At `gold_50` scale, where everything fits in context, does retrieval beat reading all fifty
  papers?** If not, retrieval is a scale argument rather than a quality one, and the honest
  headline becomes E1b's arithmetic. (cell A, `DESIGN_2026-09-17_tool-value-grid.md` §1)
- ~~**E1 itself is not currently reproducible.**~~ **Closed 2026-09-18** by `report e1`. One
  residual: `tiktoken` fetches its BPE table once into its own cache, so a **first** replay on a
  fresh clone with no network fails on E1. Vendoring that file sha-pinned beside `xml.tar.gz`
  and setting `TIKTOKEN_CACHE_DIR` would close it; not done.
- **What is the right `ir_json` schema?** The arm is schema-dependent across 6 826–9 384 tokens
  and E1 never specified one. Either specify it or stop quoting a single number for it.
