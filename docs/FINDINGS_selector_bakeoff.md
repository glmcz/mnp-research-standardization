# Findings — does knowing the question help you pick the lines that answer it?

Companion to `docs/FINDINGS.md`, same rules: numbers are **measured** unless marked
*projected*, and what came out badly stays in.

Scoring axes, fixed: **accuracy · cost · throughput/time · size · packaging**. This entry is
accuracy-of-selection against cost-in-tokens. No model was run. No network. No tokens spent.

---

## E6 — selector bake-off

**Question.** `jats.extraction_text` (`src/mnp/corpus/jats.py:416-442`) chooses what an
extraction model reads **query-blind**: it sorts the pieces of a paper by a hand-tuned
priority — keyword windows, tables, characterisation sections, figure captions, abstract,
methods — and fills a 12 000-token budget from the top. `DESIGN_2026-09-17_tool-value-grid.md`
§1 proposes replacing it with a **query-conditioned** selector (substrate S3). Does that help,
and by how much?

Stated so it can come out negative: if the query-blind selector is not beaten, that is the
finding.

### Why this is measurable now

Phase 2.1 put `evidence_line_ids` on every row of `out/tables/d1_zeta_table.csv`: the
`line_id` of each line the row's evidence was actually read from. That is **1 890 rows of
ground truth for "which lines answer this question"**, already on disk, costing zero model
tokens to score against.

### Method

A **selector** is `(LinedDoc, Query) -> tuple[int, ...]`: a total ranking of the paper's line
numbers, best first. Total rather than top-k, so recall at every k is defined for every
selector and nobody is scored on a shorter list than anybody else.

A **case** is one published row: its paper's line document, the set of `line_id`s its evidence
came from, and a query. 1 890 cases, 491 papers, **0 rows dropped** — every stored evidence id
resolves in its own document.

Five selectors, all deterministic, no model calls:

| | what it is |
|---|---|
| `whole` | the line document in written order. The ceiling: recall 1.0 when k covers the paper |
| `incumbent` | `extraction_text`'s own order. **Not a reimplementation** — `incumbent_text` reproduces `jats.extraction_text` character for character at budgets 200/500/1 000/2 000/4 000/12 000/uncapped, pinned by a test |
| `bm25` | Okapi BM25 over lines, built to win — see the sweep below |
| `structured` | query-conditioned: the row's own fields as **typed** matchers (numeric, lexical, cue) with per-field weights, i.e. retrieval over the record's graph rather than over its words |
| `random` | the floor, seeded per paper |

Metrics, per selector per k, averaged over the 1 890 cases:

- **recall@k** — fraction of rows whose *every* evidence line is in the top k. Not partial: a
  row whose value line is retrieved and whose ionic-strength line is not cannot be answered.
  **57.0 %** of rows have more than one evidence line, so the distinction is not academic.
- **partial recall@k** — fraction of evidence lines retrieved.
- **tokens@k** — `jats.approx_tokens` (`len/4`) plus one separator per line, the budget loop's
  own measure. **Approximate**: `tiktoken` is not a dependency here and was not added.
- **recall per 1 000 tokens** — the ratio that matters. A selector that wins on recall by
  returning everything has not won.

Two query variants, because the first one is confounded (see **Leakage**):

- **value query** — every field the row carries: material, functionalisation, particle name,
  supplier, quantity, value, medium, medium class, instrument, ionic strength, pH,
  temperature, sizes. Mean **28.4** distinct terms.
- **label query** — the same question asked in the schema's `checklist_label` words, carrying
  no value the model read out of the paper. Mean **24.0** terms. The one row-derived term is
  which quantity is asked about, because that is the question rather than the answer.

Both selectors see the same information: `bm25` reads the fields flattened into a string,
`structured` reads them as typed fields. The difference between them is the use made of the
record's shape, not extra knowledge.

Code: `src/mnp/eval/selectors.py`. Tests: `tests/eval/test_selectors.py`.

```
uv run python -c "
from mnp.eval import selectors as S
c = S.load_corpus(); cases = S.build_cases(c, S.value_query)
for name, sel in S.SELECTORS.items():
    for s in S.score(cases, name, sel):
        print(s.selector, s.k, round(s.recall,4), round(s.partial,4), round(s.tokens,1))
print(S.score_incumbent_at_budget(cases))
"
```

### The corpus these numbers are averaged over

| | mean | median | max |
|---|---|---|---|
| lines per paper | 44.2 | 38 | 218 |
| tokens per paper (`approx_tokens`) | 5 512 | 4 926 | 31 688 |
| evidence lines per row | 2.06 | 2 | 12 |

**Papers whose line document exceeds the 12 000-token budget: 13 of 491 — 2.6 %.** The
incumbent's budget almost never bites. That single number reframes the whole question, and it
is the first thing the results say.

### Results — value query (the confounded one)

| selector | k | recall@k | partial@k | tokens | recall / 1k tok |
|---|---|---|---|---|---|
| `whole` | 5 | 0.0984 | 0.2143 | 556 | 0.177 |
| `incumbent` | 5 | 0.1196 | 0.1908 | 1 238 | 0.097 |
| `random` | 5 | 0.0667 | 0.1302 | 694 | 0.096 |
| `bm25` | 5 | 0.6714 | 0.8041 | 952 | 0.706 |
| **`structured`** | 5 | **0.7397** | **0.8656** | 1 438 | 0.514 |
| `whole` | 10 | 0.1698 | 0.3294 | 1 231 | 0.138 |
| `incumbent` | 10 | 0.2270 | 0.3509 | 2 048 | 0.111 |
| `random` | 10 | 0.1709 | 0.2862 | 1 376 | 0.124 |
| **`bm25`** | 10 | **0.8561** | **0.9349** | 1 967 | 0.435 |
| `structured` | 10 | 0.8508 | 0.9410 | 2 667 | 0.319 |
| `whole` | 20 | 0.3148 | 0.4869 | 2 645 | 0.119 |
| `incumbent` | 20 | 0.4439 | 0.6010 | 3 137 | 0.142 |
| `random` | 20 | 0.3598 | 0.5025 | 2 679 | 0.134 |
| **`bm25`** | 20 | **0.9312** | 0.9747 | 3 701 | 0.252 |
| `structured` | 20 | 0.9249 | 0.9743 | 4 356 | 0.212 |
| `whole` | 40 | 0.6556 | 0.7577 | 4 698 | 0.140 |
| `incumbent` | 40 | 0.7016 | 0.8121 | 4 550 | 0.154 |
| `random` | 40 | 0.6762 | 0.7770 | 4 543 | 0.149 |
| `bm25` | 40 | 0.9899 | 0.9975 | 5 563 | 0.178 |
| `structured` | 40 | 0.9889 | 0.9974 | 5 756 | 0.172 |
| any | all | 1.0000 | 1.0000 | 6 611 | 0.151 |
| **`incumbent` at its real 12 000-token budget** | — | **1.0000** | **1.0000** | **6 438** | **0.155** |

The last row is the one that decides the question. **At the operating point production
actually runs, the incumbent has recall 1.0** — it drops 173 tokens per paper on average and
never once drops an evidence line. (§ *What this does not show* says why that number is partly
circular, and it is still the number the rival has to beat.)

Paired exact McNemar tests over the same 1 890 rows:

| comparison | k | wins for the first | wins for the second | p |
|---|---|---|---|---|
| `bm25` vs `incumbent` | 5 | 1 052 | 9 | 3.7e-298 |
| `structured` vs `incumbent` | 5 | 1 181 | 9 | < 1e-300 |
| `structured` vs `bm25` | 5 | 258 | 129 | 5.1e-11 |
| `structured` vs `bm25` | 10 | 80 | 90 | 0.49 |
| `structured` vs `bm25` | 20 | 20 | 32 | 0.126 |
| `incumbent` vs `random` | 20 | 332 | 173 | 1.4e-12 |

### Results — label query (the low-leakage variant)

| selector | k | recall@k | partial@k | tokens | recall / 1k tok |
|---|---|---|---|---|---|
| `incumbent` | 5 | 0.1196 | 0.1908 | 1 238 | 0.097 |
| `random` | 5 | 0.0667 | 0.1302 | 694 | 0.096 |
| `bm25` | 5 | 0.3984 | 0.5614 | 1 010 | 0.395 |
| `structured` | 5 | 0.4095 | 0.5762 | 1 637 | 0.250 |
| `incumbent` | 10 | 0.2270 | 0.3509 | 2 048 | 0.111 |
| `random` | 10 | 0.1709 | 0.2862 | 1 376 | 0.124 |
| `bm25` | 10 | 0.5206 | 0.6842 | 2 144 | 0.243 |
| `structured` | 10 | 0.5090 | 0.6736 | 2 907 | 0.175 |
| `incumbent` | 20 | 0.4439 | 0.6010 | 3 137 | 0.142 |
| `random` | 20 | 0.3598 | 0.5025 | 2 679 | 0.134 |
| `bm25` | 20 | 0.6169 | 0.7701 | 4 009 | 0.154 |
| `structured` | 20 | 0.6106 | 0.7660 | 4 568 | 0.134 |
| `incumbent` | 40 | 0.7016 | 0.8121 | 4 550 | 0.154 |
| `bm25` | 40 | 0.7693 | 0.8578 | 5 823 | 0.132 |
| `structured` | 40 | 0.7667 | 0.8544 | 5 929 | 0.129 |

`whole`, `incumbent` and `random` are query-blind, so their rows are identical to the table
above by construction; they are repeated here as the reference the query-conditioned rows move
against.

### What it costs to reach a recall target

Smallest k reaching each target, and the tokens delivered there.

| selector | query | 0.90 | 0.95 | 0.99 | 1.00 |
|---|---|---|---|---|---|
| `bm25` | value | k=14, 2 720 tok | k=26, 4 483 tok | k=44, 5 729 tok | k=59, **6 097 tok** |
| `structured` | value | k=17, 3 947 tok | k=27, 5 047 tok | k=41, 5 787 tok | k=80, 6 405 tok |
| `bm25` | label | k=80, 6 401 tok | k=80, 6 401 tok | k=120, 6 588 tok | all, 6 611 tok |
| `structured` | label | k=80, 6 433 tok | k=120, 6 588 tok | k=120, 6 588 tok | all, 6 611 tok |
| `incumbent` | — | k=80, 5 791 tok | k=120, 6 504 tok | k=120, 6 504 tok | all, 6 611 tok |
| `random` | — | k=80, 6 058 tok | k=120, 6 505 tok | k=120, 6 505 tok | all, 6 611 tok |
| **`incumbent` at its real budget** | — | — | — | — | **6 438 tok** |

## Leakage — the confound, measured

A query built from a row's own fields is built from words that were read **out of** the
evidence line, so a lexical selector may be finding its own answer. Per query: the fraction of
its distinct content terms printed verbatim in the evidence lines, versus in one seeded random
other line of the same paper.

| query | terms in the evidence line | terms in a random other line | ratio |
|---|---|---|---|
| **value** | **0.553** (median 0.606) | 0.092 (median 0.061) | **6.02×** |
| **label** | 0.259 (median 0.250) | 0.061 (median 0.042) | **4.23×** |

**Leakage is large.** Over half of a value query's terms are printed verbatim in the line it is
meant to find. The lexical selectors — and `structured`'s lexical fields with them — are
flattered, so **the comparison between them is more trustworthy than their absolute scores**.
Read `bm25` 0.856 @ k=10 as "what retrieval looks like when the query already contains the
answer's words", not as a forecast for a reader asking a real question.

The label query cuts leakage by more than half (0.553 → 0.259) and the selectors fall with it:
`bm25` recall@10 goes **0.856 → 0.521**, `structured` **0.851 → 0.509**. About four tenths of
the query-conditioned advantage was leakage.

**Does the ranking survive?** Yes, in order; no, in margin.

- `bm25` and `structured` stay far above `incumbent` and `random` at every k
  (recall@10: 0.52 / 0.51 vs 0.23 / 0.17; McNemar p < 1e-100 at k=5 and k=10).
- `structured` vs `bm25` **flips from significant to a tie**: at k=5 the value query makes
  `structured` the winner (258 vs 129, p = 5.1e-11), and under the label query the same
  comparison is 111 vs 90, p = 0.16 — no difference. `structured`'s edge was the leaked
  number, not the structure.
- At full recall the ranking **inverts**: under the label query no query-conditioned selector
  reaches 1.00 before handing over the whole document (6 611 tok), which is *worse* than the
  incumbent's real 6 438.

### What it says

1. **The incumbent's budget almost never bites.** 13 of 491 papers exceed 12 000 tokens. On
   the other 97.4 % the "selector" selects everything, so there is no selection to improve.
   Query conditioning cannot buy recall here. It can only buy tokens.
2. **At its real operating point the incumbent is already at recall 1.0, for 6 438 tokens.**
   The best query-conditioned selector needs **6 097 tokens** to match that under the
   confounded query — a **5.3 % saving** — and cannot match it at all under the honest one.
3. **As a ranking the incumbent is poor, and that is a separate fact.** recall@10 = 0.227
   against `bm25`'s 0.856 (value) or 0.521 (label). If a budget ever did bite hard, the
   hand-tuned priority would be the wrong thing to cut with.
4. **The hand-tuned priority is worth about 5–8 recall points over shuffling the paper.**
   `incumbent` vs `random`: 0.227 vs 0.171 at k=10, 0.444 vs 0.360 at k=20 (p = 1.4e-12).
   Real, small, and much less than the file's care implies.
5. **Written order is worse than chance at large k** — `whole` 0.656 vs `random` 0.676 at
   k=40 — because `lines`' document order puts tables and keyword windows last and those are
   where a lot of the evidence is. Reading a paper top-down is a bad budget strategy.
6. **Structure beat words only where the number leaked.** `structured` wins at k ≤ 5 under the
   value query and ties everywhere else. Its numeric field is doing the work, and that field
   is exactly the one the confound inflates.
7. **Savings only exist if you accept less than perfect recall.** `bm25` at recall 0.95 costs
   4 483 tokens, a 30 % saving on the incumbent's 6 438 — paid for by 5 % of rows becoming
   unanswerable. That is a product decision, not a measurement.

### What it changes

**It argues against building S3 as a replacement for `extraction_text` on this corpus.** The
delta the design doc hoped for is 5.3 % of the reading tokens in the best case and negative in
the honest case, against a 2.6 % chance the budget even bites. The reading path is ~30 % of
end-to-end tokens (`FINDINGS.md`, E1 ceiling), so the whole prize is **~1.6 % of the budget**.

Where it does argue for something: **at corpus scale, where selection is forced.** `FINDINGS.md`
E1b measured the corpus at 2.64× a 1 M window, so cells C and E of the grid must choose lines
whether anyone likes it or not. There the relevant number is not 5 % but the k=10 gap — 0.52
against 0.23 — and a query-conditioned selector is clearly the right thing to choose with.
**The finding is that the value of query conditioning lives in the retrieval cells, not in the
per-paper reading path.**

### What this does not show

- **The ground truth is the incumbent's own output, so `incumbent@12k = 1.0` is partly
  circular.** The evidence lines are lines a model quoted, and that model only ever saw
  `extraction_text(a, 12 000)`. It could not have cited a line the incumbent dropped. The
  incumbent's recall at its budget is therefore guaranteed by construction, not earned, and
  every selector's "recall 1.0 at k=all" inherits the same bias. What the comparison *is* sound
  for is **ordering**: all five selectors rank the same universe of lines, and the @k curves
  are not circular.
- **Recall is measured against the lines the extraction happened to quote, not against every
  line that would answer.** A selector that finds a *different* line carrying the same value is
  scored wrong. So these are lower bounds, and they are lower by an unmeasured amount.
- **Absence is not in the query set at all.** All 1 890 rows have evidence. Kind B of
  `DESIGN_2026-09-17_tool-value-grid.md` §3 — "what ionic strength was used, where none was
  reported" — has no evidence line by definition, and is the question the abstract is actually
  about. Nothing here measures it.
- **These are extraction targets, not a reader's questions.** Both variants are derived from a
  schema row. A mechanism question ("why does a protein corona change measured zeta") is kind
  D and is not represented.
- **BM25 was tuned on the rows it is scored on.** k1 swept over 0.9–6.0, b over 0.0–1.0 against
  recall@10 on all 1 890 cases; `k1 = 2.0, b = 1.0` was the best cell. That is deliberate — a
  weak BM25 makes the result worthless — but it means BM25's numbers are optimistic, and so is
  the margin by which it beats `structured`. The plateau is flat: every cell with b ≥ 0.75 and
  k1 ≥ 1.2 scores recall@10 between 0.822 and 0.862, so nothing here turns on the tuning.
- **Tokens are `len/4`, not `cl100k_base`.** Same caveat as `FINDINGS.md` E1b: the ratios are
  more trustworthy than the absolute counts.
- **No model read anything.** Whether a model given `bm25`'s ten lines extracts as well as one
  given the whole paper is not measured here, and retrieval that drops context can hurt a
  reader in ways recall does not see.
