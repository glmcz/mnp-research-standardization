# Design — tools as measured hypotheses, not assumed architecture

**Written 2026-09-17. Talk 2026-09-28 — a checkpoint, not a wall.** Supersedes
`PLAN_2026-09-28.md` §4 (the evaluation) and §5 (the schedule). §1–3, §6–9 of that plan stand
unchanged. `ideas.md` §2 (rejected ideas) and §13 (standing rules) still bind.

**The binding constraint is the token quota, not the calendar.** So this plan is priced in
tokens, not in evenings, and the cut line is ordered by tokens per finding. What is not
finished by 28.9 lands after 28.9; what is finished by 28.9 goes on a slide. The one thing the
date still decides is which findings are *presentable*, and §5 marks those.

---

## 0. What changed

The plan said: **MNP-KB is the product, naive RAG is the baseline it beats.**

That pre-decides the result. Martin's reframe: the converter, RAG and the KB are all *tools
meant to help an agent read papers*. Whether any of them adds value is a measurement, not a
premise.

Two consequences, and they are the whole design:

1. **The zero is not RAG. The zero is no tool.** A reader handed plain paper text. Every tool
   must beat that, and must beat the cheaper tool below it.
2. **A naive one-shot RAG baseline is a strawman by the field's own 2026 standard**, so
   beating it proves nothing. The strong rival is an *agent* searching the converted corpus
   with no KB at all. If that rival wins, the KB earns nothing. That comparison is the talk.

---

## 1. The grid, not a ladder

The first draft of this design was a ladder — T0 plain text, T1 converter, T2 RAG, T3 KB, T4
hybrid. That was wrong, and the field's own survey literature says why: **GraphRAG changes
*what* you retrieve from; agentic RAG changes *how* retrieval happens.** Two independent axes.
A ladder moves both at once per rung, so no rung's delta means anything.

**Substrate — what the reader sees**

| | | state |
|---|---|---|
| **S0** | plain text, `extraction_text()` today | exists |
| **S1** | line-addressed converted text + machine sidecar (§2) | **build** |
| **S2** | structured records: 1 890 rows, conditions, absence booleans | exists as CSV; query layer to build |

**Control — how evidence gets chosen**

| | | state |
|---|---|---|
| **C0** | none. Everything in context | free |
| **C1/C2** | one-shot similarity / hybrid + reranker | build (was plan item 4) |
| **C3** | static route: structured filter first, prose fallback | build (was plan item 3) |
| **C4** | agent decides what to fetch, whether it is enough, whether to fetch again | build (was plan item 6, MCP) |

### The five cells that get run

| cell | substrate × control | what it is |
|---|---|---|
| **A** | S1 × C0 | "why not just put the papers in context?" |
| **B** | S1 × C2 | the baseline built to win |
| **C** | S1 × C4 | **the dangerous rival** — agentic search, no KB |
| **D** | S2 × C3 | the product as originally planned |
| **E** | S2 × C4 | the product, current generation |

`S0 × C0` needs no run: E1 already measured it at 5 273 tok/paper, and it is the reference
point for every token number below.

### The deltas are the findings

Each moves exactly one variable.

| delta | question | if it comes out flat |
|---|---|---|
| **B → D** | does structure beat prose retrieval? | the original plan's thesis fails |
| **C → E** | does structure help an *agent*? | **the KB earns nothing.** Say so |
| **B → C** | does agency help without structure? | agentic framing is decoration here |
| **D → E** | does agency help with structure? | ship the static router, skip the loop |
| **A vs rest** | does retrieval earn anything at all? | retrieval only pays at corpus scale |

---

## 2. S1 — the converter, specified

Today the model authors its own evidence: it returns a quote, and `verify_row`
(`src/mnp/extract/zeta.py:415`) checks that quote is a substring of the article. The model
wrote the string it is judged on. Five independent workers trimmed quotes to pass that guard;
seven fabricated quotes reached production before it existed.

S1 numbers every unit of the existing parse and has the model return **pointers**, not prose.

```
  JATS XML (vendored, sha256-pinned, 858 files)
        │
        │  deterministic — no model, no network, ~21 s for the corpus
        ▼
  canonical document
        │
        ├──► md_linenum   the AGENT reads this          1.02× plain text (E1, measured)
        │                 "L212\t The zeta potential was -34.2 mV ..."
        │
        └──► sidecar      the MACHINE resolves this     never read whole
                          L212 → sha(section_path, ordinal, normalised_text)
                          marks: offsets of sub/sup/italic/minus
                          quantity index, condition index
```

**A line is a paragraph.** `_section_lines()` (`src/mnp/corpus/jats.py:158`) already yields one
entry per `<p>`, section title, or table TSV row — roughly 50 per paper. That is why E1
measured +2 %: about 100 extra tokens. Sentence-level ids cost 12 %, JSON 45 %. Paragraph
granularity is the cheap choice, and verification at that granularity is "is the value printed
somewhere in this paragraph" — which `_number_in` and `find_candidates` already do on arbitrary
text.

**Three decisions, with reasons:**

- **Number in the text, hash in the sidecar.** The model sees `L212` — two tokens. Ingest
  resolves it to `sha(section_path, ordinal, normalised_text)` and stores *that*. A later
  parser fix that shifts line numbers does not invalidate stored citations. `parser_sha` joins
  `prompt_sha256` in provenance.
- **Marks as offsets, never nesting.** The model reads normalised text; the sidecar records
  where the subscripts, italics and minus signs were. The thin-space minus-sign flip found by
  a second reader last session becomes machine-checkable at a known offset.
- **Table rows: line-only citation for now.** Ambiguous when one row carries both a size and a
  zeta — the scanner auditor's "two-quantity cell". Accept the ambiguity, flag it, revisit only
  if it shows up in the eval.

**What S1 is not.** Not a re-extraction. The 1 890 existing rows are 100 % verbatim-verified,
so their quotes **will** locate by substring into line ids. Retrofit, do not re-read. This is
`ideas.md` §10.4's recommendation, and under a token budget it is not a compromise but the
obvious move: **the retrofit costs zero model tokens**, while re-extracting the corpus costs
~17.5 M. The deterministic half of this pipeline already rebuilds 858 XMLs in 21 s for nothing.

**Why this matters beyond citation.** A 1 M-token context holds **186 papers** of converted
text and **24 papers** of raw JATS — a **7.65×** difference in how much corpus fits (see
`FINDINGS.md` E1b). The converter is what makes cell A viable at all. It does not compete with
long context; it is the reason long context is on the table.

**Parked: the executable form.** Having the model emit a small program (`FIND` / `BIND` /
`ABSENT` / `EMIT`) that a deterministic VM runs against the sidecar would make fabrication
structurally *unrepresentable* rather than merely caught, and would make cross-model agreement
a per-instruction diff. It needs a VM and a full re-extraction. Not in eleven days. S1's line
citation is its cheap half; build the rest after the talk if the eval says citation helped.

---

## 3. Query set and metrics

Four kinds. Kind D is new, and it exists so the result is not rigged.

| kind | example | n | ground truth |
|---|---|---|---|
| **A** conditioned lookup | "zeta of PS-COOH in seawater, and at what ionic strength?" | ~30 | `gold_50.csv` |
| **B** absence | "what ionic strength was used in PMC…?" where none was reported | ~30 | `ionic_strength_reported = False` |
| **C** comparison | "papers reporting PS zeta at I between 100–200 mM" | ~10 | structured filter |
| **D** mechanism / prose | "why does a protein corona change measured zeta?" | ~10 | **the KB has no field for this. Prose retrieval should win. Report it** |

**Per cell, per kind:**

| metric | why |
|---|---|
| answer accuracy | the obvious one |
| **fabrication rate on kind B** | the money metric. Absence is what the abstract is about |
| citation correctness | a right answer with a wrong citation is not a right answer |
| tokens per question | cell A's number is the slide: 491 × 5 373 ≈ **2.64 M** for one question |
| wall clock per question | "convenient" has to mean something |
| **retrieval calls per question** | agentic search over-searches; accuracy bought at nine calls is a different product from accuracy at two |

Same reader model in every cell. Same query set. Same parser — so "you gave RAG a worse
parser" is structurally unavailable as a criticism.

**Pilot before sweep, every cell.** Ten questions first, read the output, then the remaining
seventy. Every cell. A cell that is broken on question three should not be discovered on
question eighty — that is the single largest avoidable token cost in this plan.

---

## 4. The gate agents

Two reviewers in `.claude/agents/`, matching the format of the four that already exist there.
Both `model: opus`, tools `Bash, Read` only — a gate never edits.

| file | role |
|---|---|
| `mnp-gate-engineer.md` | sceptical engineer: measurement, reproducibility, scope, strawmen |
| `mnp-gate-scientist.md` | sceptical nanoparticle/colloid scientist: measurand, comparability, absence-vs-not-present |

**Input is a step card:** what · why · files touched · **estimated tokens, and what makes it
that many** · *the measurement that would show it failed* · **the abstract sentence it serves**
· **the plan item it serves**. A card missing either alignment line is escalated unread. A card
whose token estimate has no stated basis is escalated too — the estimate is the thing the gate
is there to argue with.

**Verdict is `ALLOW` or `ESCALATE`. There is no `REJECT`.** This is the one non-obvious rule,
and the repo's own numbers decide it: the judge panel detected disagreement 17/17 and decided
at **κ = −0.05**. An LLM panel is good at finding the fork and bad at choosing the branch. So
the gates argue both sides and Martin decides — the same shape as `mnp-adjudicator`'s
"genuinely ambiguous" verdict, which is a legitimate outcome there and here. `ALLOW` requires
at least one concrete pro, zero blocking cons, and both alignment quotes; it may carry
conditions. Both agents must `ALLOW` or the step escalates. No third judge, no majority vote —
that refusal is `ideas.md` §6.5's most senior line and it stays.

**Blocking cons, auto-escalate:** re-proposes anything in `ideas.md` §2 (R1–R9); breaks a §13
standing rule; touches the gold set or changes a denominator; needs a new API key or paid
dependency; **costs more than 2 M tokens**; names no failure measurement.

Engineer adds: an unmeasured claim, a strawmanned baseline, a step that is not reproducible
offline, scope creep, and — since the quota is the binding constraint — **spending model tokens
on work a deterministic pass could do instead**. Scientist adds: wrong measurand, "not reported" drifting into "not
present", comparability claimed without conditions, contradiction with the abstract — which
the scientist flags and never overrules, because the abstract is fixed.

Alignment targets are **read fresh on every run**, never copied into the agent file: the
abstract, `PLAN_2026-09-28.md` §1 and §4, `ideas.md` §2 and §13. Verdicts append to
`docs/GATE_LOG.md`, written by the caller, not by the agents.

---

## 4b. What the measurements changed — revision of 2026-09-18

Four things were measured since this document was written. Three of them moved the plan.

**The converter's value is not where §2 claimed.** E6 (`FINDINGS_selector_bakeoff.md`) measured
five selectors against 1 890 rows of real ground truth. The 12 000-token budget binds on **12–13
papers of 491**, so on ~97 % of papers the incumbent selects nothing. A perfect selector is worth
about **1.6 % of end-to-end tokens**. **Do not rebuild the reading path.** Line citation still
earned its place, but for verification and for making E6 possible at all, not for cost.

**The graph is not supported as a selector.** The structured selector beat BM25 on a query built
from a row's own fields and **tied** on an honest one. Over half a value query's terms are
printed verbatim in the line it is meant to find. Its edge was the leak. Use BM25 in the
retrieval cells: thirty lines, no schema coupling.

**But the graph is rescued as a representation of relations, which is a different claim.**
`AGENT_MNP_LEARNING_APPROACH.md` proposes asking whether two measurements *can be compared*. That
is a predicate over a pair of records. No passage in the corpus states it; it exists only in the
join. Retrieval cannot reach it by construction, exactly as absence cannot. This is the plan's
strongest anti-retrieval argument extended from absence to **comparability**, which is what the
abstract is actually about.

**A new headline candidate, from E2b.** Only **5.6 %** of papers name the model converting
mobility to zeta. So **94.4 %** report a zeta whose defining conversion is unstated, where
Smoluchowski and Hückel differ by a factor of **1.5**. `conditions_complete = 3.3 %` says the
context is missing; this says the reported quantity is **not fully defined**. It is a mention
scan and needs one refinement before it goes on a slide — see §7.

### The consequence for §3: a fifth query kind

| kind | question | can a strong RAG baseline compete? |
|---|---|---|
| A conditioned lookup | value plus its conditions | yes |
| B absence | what was not reported | no — nothing to retrieve |
| C comparison | numeric filter across papers | no — not a similarity operation |
| D mechanism / prose | why does a corona change zeta | **yes, and it should win** |
| **E comparability** | **may these two rows be compared, and what blocks it** | **no — the fact is in the join, not in any passage** |

Kind E is new and it is the cheapest strong result available. Its **ground truth is derivable
deterministically** from the conditions already in `d1_zeta_table.csv`, at zero model tokens.
Tokens are spent only asking agents to answer, not building the answer key.

The obvious objection — "you chose a task the baseline cannot do" — is answered by the abstract
itself: this is its central claim, not a contrived task. Kinds A and D stay in, and D is expected
to be lost.

---

## 5. The work, priced in tokens

### Status, 2026-09-18 — read this before the table below

**Done and committed**, all at zero model tokens: the converter (`lines.py`); line citations on
**1 890 / 1 890** rows via `extract retrofit`; the dataset release with a card whose every
statistic is computed at build time; both gate reviewers, exercised once for real; the narrowed
verification change; E1b, E2b and E6. Suite at **899 passing**, `report reproduce` exits 0.

**Next, in order. Everything here is free or cheap; the expensive cells wait.**

| # | item | tokens | why now |
|---|---|---|---|
| N1 | **Kind E query set + deterministic answer key** | **~0** | The answer key is computable from conditions already in the table. Cheapest strong result available, and it is the abstract's thesis made executable |
| N2 | Card 2 — the two extraction defects, through the gates | ~60 k | A published percentage moves, so the rule this repo wrote applies to it |
| N3 | Refine the 94.4 % conversion-model figure (§7) | ~0 | It is a mention scan. Fix the denominator before it reaches a slide |
| N4 | E1 re-commit: `tiktoken` + the three missing serialisers | ~0 | Every number in this document multiplies constants that cannot be regenerated |
| N5 | Cell D — structured query layer, now including kind E | ~0.25 M | The product |
| N6 | Cell B — BM25 retrieval, built to win | ~0.7 M | `src/mnp/eval/selectors.py` already contains the tuned BM25 |
| N7 | Cell C — agentic, KB withheld | ~2.4 M | The rival that can kill the thesis |
| N8 | Cell E — agentic with the KB | ~1.2 M | |

**Cut, with reasons.** Cell A (long context) is dropped: E1b's arithmetic already makes the
point for nothing, and running it costs ~2.4 M even cached. The query-conditioned selector is
dropped from the *reading* path per E6; it survives only inside the retrieval cells, as BM25.

**Unchanged:** never cut the results table, and never cut cell C.

---


**The organising rule: deterministic work is free, so do all of it, properly. Spend model
tokens only where a model must actually read something.** This repo already proves the point —
858 XMLs and 845 records rebuild in 21 s for zero tokens, while one extraction wave over 80
papers costs 1.4 M.

Estimates use the measured 17.8 k tokens/paper for extraction work and 5 373 tokens/paper for
converted reading text. Query set is 80 questions (30 A + 30 B + 10 C + 10 D). Assume roughly
2× on top of every figure for iteration and debugging on first attempt.

| # | item | owner | **tokens** | on a slide by 28.9? |
|---|---|---|---|---|
| 1 | **S1 converter**: numbering, sidecar, retrofit 1 890 quotes → line ids, citation-scoped verify | C | **~0** deterministic | yes |
| 2 | dataset release form: parquet + JSONL + JSON Schema + dataset card | C | **~0** deterministic | yes |
| 3 | corpus-scale long-context arithmetic (2.64 M > 1 M window) | C | **0** — it is division | yes |
| 4 | **S5 / S29 / S31 rulings** | **M** | 0 (human hours) | yes |
| 5 | **κ audit**, blind, 10 gold papers | **M** | 0 (human hour) | yes |
| 6 | Zenodo DOI + licence | M + C | ~0 | yes |
| 7 | query set, kinds A–D, ground truth from `gold_50` + `*_reported` | C | ~0.1 M | — |
| 8 | cell **D** — structured filters + semantic over evidence | C | **~0.25 M** | yes |
| 9 | cell **B** — strong RAG on S1: hybrid + reranker, tuning published | C | ~0.7 M | yes |
| 10 | gate agents `mnp-gate-engineer` / `mnp-gate-scientist` + `GATE_LOG.md` | C | ~0.7 M (≈30 k per card × 12 × 2) | yes |
| 11 | cell **E** — MCP server, agent over KB tools | C | ~1.2 M | yes |
| 12 | E2 — does line numbering change extraction *accuracy*? 50 papers × 2 arms | C | ~1.8 M | if it lands |
| 13 | cell **C** — same loop, prose tools only, KB withheld | C | ~2.4 M | **the one worth overrunning for** |
| 14 | cell **A** — long context at gold-50 scale, prompt-cached | C | **~2.4 M cached / ~21 M uncached** | if it lands |
| 15 | run all cells × all kinds, write the table | C | folded into 8–14 | yes |
| 16 | slides | M + C | ~0.2 M | — |
| — | ~~sweep waves 2–3~~ | — | ~~2.8 M~~ | **cut** |

**Total if everything runs: ~9.5 M, call it 15–25 M with iteration.**

### Three corrections the token budget forces

**Cell A was mispriced.** In the day-costed draft it was "0.5 session, cheap". In tokens it is
the most expensive thing in the plan. Two fixes, both of which make it *better*, not just
cheaper:

- **At corpus scale it is not expensive, it is impossible.** 491 papers × 5 373 = **2.64 M
  tokens**, against a 1 M window. That is arithmetic, costs nothing to compute, and is a
  stronger claim than any measurement: long context does not reach this corpus at all. Item 3.
- **At `gold_50` scale it is a fair fight and it is runnable.** Fifty papers is a 269 k-token
  window — the same fifty the ground truth comes from. Fixed prefix, prompt-cached, all eighty
  questions batched inside one cache lifetime: ~2.4 M instead of ~21 M. **Caching is what makes
  this cell exist.** Without it, cut the cell and keep item 3.

**The sweep stays cut, for a better reason than before.** Time was never the argument. It costs
2.8 M tokens and no S-ruling has moved a headline by more than 0.4 points. It buys traceability,
not the number. Highest token cost, lowest finding density in the plan.

**E2 comes back.** It was cut for calendar reasons. At 1.8 M it is mid-priced, it needs no
supervision, and it answers a question the converter's whole case rests on — whether line
numbering changes what a reader *finds*, not just what it costs. Run it unattended while the
cells are being built.

### Order

1. **Everything free, first** — items 1–6. No token risk, and items 1 and 2 are the substrate
   everything else reads. The dataset ships from here regardless of what follows.
2. **Cheapest finding next** — items 7, 8, 9. Cells D and B together already answer the
   original plan's thesis (B → D: does structure beat prose retrieval?) for under 1 M.
3. **Gates before the expensive half** — item 10. They exist to challenge items 11–14, so they
   have to precede them.
4. **The expensive half, in rising price** — 11, 12, 13, 14. Pilot ten questions, read the
   output, then the rest.

### Cut line, ordered by tokens per finding

Cut from the bottom: item 14 (cell A — keep item 3's arithmetic, say the measurement was not
run), then item 12 (E2), then item 9 drops from reranked to plain hybrid.

**Never cut item 13.** Cell C is the strongest rival to the entire thesis, it is the comparison
a reviewer will demand, and at 2.4 M it is not even the most expensive line in the table. If
the budget only stretches to one expensive cell, it is this one.

**Never cut item 15.** It is the result.

---

## 6. What would change my mind

- **Cell C ≈ cell E on kinds A and B** → an agent with good prose tools does not need the KB.
  The contribution narrows to kind C and to the dataset as an artefact. This is the most likely
  way the talk's thesis loses, and it is the reason cell C is being built at all.
- **Cell A ≈ everything at `gold_50` scale** → retrieval earns nothing until the corpus outgrows
  the context window, and the honest headline becomes the arithmetic rather than the KB: fifty
  papers fit in 269 k tokens and need no retrieval at all; 491 papers need 2.64 M and do not fit.
  Retrieval is then a scale argument, not a quality one. Say it that way.
- **Cell B ≈ cell D on kind A** → the extraction layer is not earning its cost for lookup.
- **κ < 0.6** (§5 item 5) → the gold set is not ground truth, every extraction score is
  provisional, and the dataset card says so before anyone else finds it.
- **Cells D/E beat cell B on kind D** → the query set is broken, not the finding. Kind D exists
  for prose retrieval to win. If it does not, suspect the queries first.

---

## 7. Open, needs Martin

1. **The actual token budget.** This plan is a priced menu precisely because the number is
   unknown — it works at any budget by cutting from the bottom of §5. But the real figure
   changes where the line falls, and it is the only input that would change the ordering. Two
   things worth knowing: what the quota is, and whether it resets weekly.
2. **S5 / S29 / S31 rulings** (item 4). Zero tokens, highest value per hour in the plan.
3. **κ audit** (item 5). One hour, blind, zero tokens.
4. **Dataset name and licence.** CC-BY is the default expectation. Source XMLs are open access
   with per-paper licences; the card must state what is redistributed (extracted values + short
   verbatim quotes) versus what is not (full texts).
5. **Talk length.** Decides how much of the failure-mode material survives.
6. **The `ALLOW`/`ESCALATE` rule** (§4). Decided here on the repo's own κ evidence. Reversible
   in one line if Martin wants the gates to be able to refuse outright.

Items 2 and 3 are the two highest-leverage things in this entire document and they cost no
model tokens at all.

---

## 8. Sources for the §1 framing

Checked 2026-09-17. The two-axis distinction in §1 is the field's own, not an invention of this
document, and these are safe to name on a slide.

| claim | source |
|---|---|
| retrieval trained on whether a passage helped the *answer*, not on query similarity | Agentic-R, Findings of ACL 2026 — https://aclanthology.org/2026.findings-acl.785/ · https://arxiv.org/abs/2601.11888 |
| agentic RAG taxonomy: single-agent, multi-agent, hierarchical, corrective, adaptive, graph-based | https://arxiv.org/pdf/2501.09136 |
| **GraphRAG changes what you retrieve from; agentic RAG changes how retrieval happens** | Agentic GraphRAG survey — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6713979 |
| over-search as agentic search's characteristic failure — the reason §3 counts retrieval calls | SAAS — https://arxiv.org/pdf/2605.29796 |

One caution carried from `agent_rag.md`, which is where this framing entered: that note also
points at hypothesis generation, web search over live literature, and self-improving retrieval.
All three are out of scope. Web search in particular breaks the offline-reproducible property
that the whole reproducibility argument in `ideas.md` §5 rests on.
