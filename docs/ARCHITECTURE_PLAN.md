# Architecture plan — a reproducible, auditable extraction pipeline

Status: **plan only.** Nothing here is built. Written 2026-09-13 after the first corpus run,
whose weaknesses are catalogued in `METHODOLOGY.md`.

The goal is that a stranger with this repository and an API key reproduces every published
number, and that every row can be traced to the paper, the instructions and the agent that
produced it.

---

## 0. Terms, and one thing I need you to confirm

Three properties, which are not the same thing:

- **Deterministic** — same input, same output. True of the parser, scanner, verifier and
  reports. Never true of an LLM reading a paper.
- **Idempotent** — running a step twice changes nothing the second time. Achievable
  everywhere, including extraction, because the unit of work is one paper and the store is
  keyed by PMCID.
- **Reproducible** — someone else gets the same *result*, and where judgement was involved,
  can see exactly what judgement was asked for and audit it.

Extraction can be idempotent and reproducible-with-audit, but not deterministic. The plan
below aims at: deterministic everywhere it is possible, idempotent everywhere, and every
judgement recorded with the exact instructions that produced it.

> **"DFS evaluation" — I am not certain what you mean.** I have assumed *depth-first*: before
> fanning out to hundreds of workers, take one worker and one small set of papers all the way
> through, measure it against human-checked ground truth, and only then widen. That is §6.
> If you meant something else (a specific framework, or a decision-tree/search evaluation of
> agent configurations), say so and I will rework §6 — it is the section that most depends on
> the answer.

---

## 1. Where the first run actually failed

Short version, evidence in `METHODOLOGY.md` §4:

| Failure | Consequence |
|---|---|
| Briefs lived in a scratchpad | the main extraction brief is **gone**; no row traces to its instructions |
| One `prompt_sha256` for all 845 records | provenance field exists but carries no information |
| Chunks assigned from stale snapshots | duplicated work, `/tmp` payload collisions |
| Workers could spawn workers | three reported success having done nothing |
| Filter applied to the population being measured | "never printed" undercounted 17 vs 144 |
| Rate limits killed 10 workers | recovery was luck (idempotent ingest), not design |

Every one is an orchestration flaw. The scientific pipeline was sound.

---

## 2. Everything in the repository, nothing in a scratchpad

```
data/
  raw/epmc/…                  # unchanged: fetched XML, immutable
  interim/
    articles.parquet          # parsed corpus
    extractions.jsonl         # one record per paper, append-only, keyed by PMCID
    worklists/                # NEW: every list a worker was ever given
    # (the work queue lives in PostgreSQL, not here — see §3)
    runs/<run_id>/            # NEW: one directory per orchestrated run
      manifest.json           #   config, brief hashes, model, code commit, start/end
      assignments.jsonl       #   worker_id, pmcids, claimed_at, released_at
      reports/<worker>.md     #   what each worker reported back, verbatim
docs/
  briefs/                     # NEW: every brief, versioned in git
    extraction.md
    nonumber.md
    gold_annotation.md
```

Rules: a worker may write only to `runs/<run_id>/` and through `extract ingest`. The
scratchpad is used for nothing that explains a result. `data/raw/` is never written after
fetch.

**Cost of not doing this:** already paid. The brief that governed ~65 workers and most of the
corpus cannot be recovered.

---

## 3. A work queue with leases

PostgreSQL, matching the rest of the stack. The decisive feature is
`SELECT … FOR UPDATE SKIP LOCKED`: many workers claim disjoint work in one statement with no
application-level locking, which is exactly the failure (`METHODOLOGY.md` §4.3) that caused
duplicate work and `/tmp` collisions in the first run.

One consequence to be deliberate about: the queue is now **operational state outside the
repository**, so it cannot itself be the reproducibility record. That is fine as long as the
queue is treated as a scheduler and never as a result — `extractions.jsonl` stays the durable
scientific record, and `runs/<run_id>/manifest.json` (in the repo) records what was assigned
and under which brief. Losing the database must cost a re-run, never a result.

```sql
CREATE TABLE mnp_work (
  pmcid       TEXT PRIMARY KEY,
  state       TEXT NOT NULL,      -- pending | leased | done | failed | skipped
  worker      TEXT,               -- who holds the lease
  lease_until TEXT,               -- ISO timestamp
  attempts    INTEGER DEFAULT 0,
  run_id      TEXT,
  brief_sha   TEXT,               -- which brief this paper was done under
  updated_at  TEXT NOT NULL
);
```

```
extract queue init  --from <list> --run <id>     # idempotent: existing rows keep their state
extract queue claim --worker <id> --n 10         # FOR UPDATE SKIP LOCKED, one statement
extract queue done  --worker <id>                # VERIFIES against extractions.jsonl, then marks
extract queue reap                               # expired leases → pending, attempts += 1
extract queue status                             # counts by state; the only progress report
```

Invariants this buys:

- Two workers can never receive the same paper → no duplicate work, no `/tmp` collisions.
- A worker that dies loses its lease; `reap` returns the papers. Rate-limit death becomes a
  non-event rather than a recovery exercise.
- `done` is a *verification*, not an assertion: it checks each claimed PMCID has a record
  whose `model` and `brief_sha` match this worker. A worker that delegated and did nothing
  fails here instead of reporting success.
- `attempts >= 3` → `failed`, surfaced for a human. Never silently retried forever.

**Idempotency:** `init` on an existing queue is a no-op for finished work (`ON CONFLICT DO
NOTHING`). Re-running the whole pipeline re-extracts nothing already `done`. Dropping the
table and re-initialising reproduces the same claim order given the same list, because claims
are ordered by PMCID rather than by insertion or chance.

**Connection:** `MNP_DB_URL`, falling back to the stack's `DATABASE_URL`. Tests run against a
throwaway container (`tool/test_db.sh`) and skip when no server is reachable, so the suite
never depends on a developer's local state.

---

## 4. Agent personas

Each is a file in `.claude/agents/` — versioned, tool-restricted, with its brief inline. The
tool restriction is the point: **no persona below has the Agent tool**, so the delegation
failure is structurally impossible rather than discouraged.

### 4.1 `mnp-extractor` — reads a paper, writes rows
- **Tools:** Bash, Read (no Write — payloads go through `extract ingest --stdin`)
- **Input:** one PMCID at a time from its lease
- **Judgement it owns:** is this a synthetic-polymer particle; is this value this study's own
  measurement or a citation; which conditions are stated
- **Judgement it must not make:** never compute, convert, average or infer a number; never
  assume 25 °C, pH 7 or water
- **Output contract:** JSON rows + a one-line verdict per paper
- **Success:** rows verified by the ingest verifier; `value_unparseable` drops are its bugs to
  fix, `value_not_printed` flags are correct outcomes

### 4.2 `mnp-gold-annotator` — builds ground truth
- **Tools:** Bash, Read, Write (writes only to `runs/<id>/gold/`)
- Reads the article **through the same `show` view the extractor sees**, deliberately: the
  annotator's confusion is a differential test of the parser, which is how nine parser defects
  were found in the first run
- Never sees extractor output. Annotates against explicit written rules, and flags every
  borderline call rather than resolving it silently

### 4.3 `mnp-adjudicator` — resolves disagreement
- **Tools:** Bash, Read
- **Input:** one paper where gold and extraction disagree, both readings, and the article
- **Output:** which is right and why, or "genuinely ambiguous — the paper does not say"
- Exists because the first run had no defined way to resolve a disagreement; I adjudicated ad
  hoc, and once was wrong (the "300× spread" false alarm, `METHODOLOGY.md` §4)

### 4.4 `mnp-scanner-auditor` — attacks the regex
- **Tools:** Bash, Read
- **Input:** papers the scanner found *no* value in, plus a sample it did
- **Job:** find printed values the scanner missed, and values it claimed that are not zeta
- Every recall fix in the first run came from a worker noticing this in passing. Make it a job
  instead of a side effect.

### 4.5 `mnp-librarian` — source acquisition
- **Tools:** Bash, WebFetch
- Resolves a DOI list to full text across sources (§8), records per paper which source
  supplied it and under what licence

---

## 5. Orchestration pattern

One loop, run by a script rather than by a conversation:

```
extract queue init --from todo.txt --run 2026-09-20-corpus
for round in 1..N:
    extract queue reap
    dispatch W workers:  claim → extract → ingest → done
    extract queue status   # the only source of progress truth
until status shows pending == 0 and leased == 0
extract report all --run 2026-09-20-corpus
```

Properties: the orchestrator holds no state (the queue does), any worker can die at any
point, and progress is read from the database rather than from what an agent said. Resuming
after an interruption is `reap` plus another round.

**What I would *not* do again:** dispatch chunks by hand from a conversation, 114 times.

---

## 6. Evaluate the agents *before* the corpus run

Depth-first, cheapest gate first. Do not start the corpus until gate 3 passes.

| Gate | Set | Measures | Pass condition |
|---|---|---|---|
| 1 · fixture | 5 papers with known answers, in `tests/fixtures/` | does the persona follow its contract at all | 100% schema-valid, 0 delegation, 0 writes outside its sandbox |
| 2 · edge set | the 24 cases in §7 | judgement on the hard calls | ≥ 20/24 match the human key; every miss explained |
| 3 · gold slice | 30 gold papers, unseen by this persona | precision/recall vs ground truth | paper-level precision ≥ 0.90 on medium & instrument; row-level value P ≥ 0.75 |
| 4 · pilot | 50 random corpus papers | cost and behaviour at scale | ≥ 95% of papers need ≤ 2 ingests; wall-clock and token cost per paper recorded |

Gates 1–3 cost ~60 papers of work — roughly 6 workers, well under an hour. The first run
skipped all of this and paid for it in re-annotation and re-extraction.

**Also measure the configuration, not just the persona.** Papers per worker (5 / 10 / 20) and
model tier (Sonnet / Opus) were guesses in the first run. Gate 4 is the place to measure them
against rows-per-paper and cost.

---

## 6b. What the first gate run actually found

Gate 3 was run for real on 2026-09-13: two workers, twelve gold papers, claiming from the
queue, blind to both the stored records and the gold annotations. It found **six defects
before a corpus sweep rather than after** — which is the entire argument for gating.

| Defect | Severity |
|---|---|
| `--brief` documented in the persona but never wired into the CLI | provenance silently absent on every record a compliant worker produced |
| an unrelated µM concentration in a medium string recorded as a **reported** ionic strength | inflates the study's headline metric |
| `<0 mV` parsed as `0.0` | fabricates a measurement, with the wrong sign |
| a not-zeta phrase anywhere in a paragraph suppressing real values 400 characters away | silently undercounts coverage |
| `accelerat` matching the ordinary verb "accelerates" | suppresses real values |
| polymersomes and functional core-shell coatings undefined in the brief | both workers flagged it independently |

Three of the six were mine, introduced in the same session that wrote the plan. The two
workers found the same brief gap independently, which is the signal that a rule is genuinely
missing rather than one worker being confused.

Scores against gold on that slice, after the fixes: row value P 0.88 / R 0.88 (corpus run:
0.68 / 0.74), row temperature 0.57 / 0.57 (corpus run: 0.15 / 0.23), paper-level instrument,
pH and temperature all 1.00 / 1.00. Twelve papers is a small slice and the ionic-strength row
was measured against pre-fix records, so both need a re-run before they are quotable.

---

## 7. Edge tests for human evaluation

24 real papers from the corpus, chosen because each is a decision the pipeline got wrong, got
right by luck, or where two readers could legitimately differ. You answer them once; the
answers become the key that every future persona is scored against.

**Built**: `tests/edge/edge_cases.md` (26 cases — 24 planned, plus two raised by gate-3
workers) and `tests/edge/key.yaml` awaiting your answers. Each case is one paper, one
question, five minutes.

**Material boundary** — what counts as a plastic?
1. PLGA drug-delivery nanoparticles (synthetic polyester, not a pollutant)
2. Lignin nanoparticles (natural polymer, plastic-adjacent)
3. Polymer-coated iron oxide (polymer surface, inorganic core)
4. BiVO₄ micromotor with a 0.6 wt% MIP shell
5. Cellulose nanocrystals used as a plastic substitute
6. PDMS/PAA-coated magnetite used to *capture* plastics

**Attribution** — whose measurement is it?
7. A zeta value cited from another study in the discussion
8. A "±30 mV colloidal stability" textbook threshold
9. A PS standard used only to calibrate the instrument
10. Zeta of the *effluent* containing plastics, not of isolated particles
11. Aβ protein measured after the PET particles were filtered out

**The number** — is a value reported?
12. "approximately −5 to −14 mV" (a range)
13. Value only in a figure
14. Value only in supplementary Table S1
15. "maintained the zeta potential" (qualitative only)
16. "−50 ± 9.7" printed with no unit anywhere
17. "± 45 and ± 20" (magnitude, sign unstated)

**Conditions** — was a condition reported?
18. "PBS" with the tablet composition given (computable I) vs bare "PBS"
19. Incubation at 37 °C, measurement temperature never stated
20. "room temperature"
21. pH given as a range, 6.8–7.2
22. "Zetasizer" with no model number
23. Medium stated only as "the experimental medium"
24. Conditions stated once in Methods for all measurements — do they apply to every row?

Cases 12–17 and 18–24 are where the corpus statistic actually lives: 19 is exactly the
distinction that drives row-level temperature to P = 0.15.

---

## 8. Sources — the gap is the index, not the language

Measured today against the live APIs:

| Source | Works on this topic | Notes |
|---|---|---|
| Europe PMC, current query, all access | 1,117 | 943 have full text; **858 fetched** |
| Europe PMC, `LANG:"chi"` | **4** | Chinese-*language* indexing is negligible here |
| Europe PMC preprints | 14 | |
| OpenAlex, same topic | **3,513** | 77% open access |
| OpenAlex, China-affiliated | **1,002** (862 OA) | 29% of the field |

Overlap, measured by sampling 600 OpenAlex works against our corpus: **22% are already in it,
78% are not.**

So the Chinese-paper concern resolves into something more actionable than a language problem.
Chinese groups are ~29% of this literature and publish in English-language journals; what
excludes them is that Europe PMC indexes a fraction of those journals. The fix is a second
index, not a translation step.

**Proposed acquisition order:**
1. **OpenAlex** as the discovery layer (DOI + OA location), Europe PMC kept as one full-text
   supplier among several. Expected to roughly triple the corpus.
2. **Unpaywall / OA locations** for PDFs where no JATS XML exists — needs a PDF-to-text stage
   the pipeline does not have, and PDF tables are materially worse than JATS tables. Treat PDF
   papers as a separate, clearly-labelled tier.
3. **Structured datasets** — `caNanoLab` (NCI, responds) and `eNanoMapper`/NanoCommons both
   hold nanomaterial characterisation records *with* conditions. These are the natural
   contrast case for the talk: places where the conditions *are* recorded.
4. **CNKI / Wanfang** only if a genuinely Chinese-language body of work is suspected. Both are
   subscription, neither has an open API, and today's numbers suggest a small return.

**Honest caveat:** tripling the corpus changes the denominator and every published fraction.
That is a new study, not an extension of this one — run it as `run_id=2026-xx-openalex` and
report both.

---

## 9. MCP and A2A — where each genuinely fits

**MCP** is the right fit for *this* pipeline. Wrap the CLI as an MCP server exposing
`show_paper`, `ingest_rows`, `queue_claim`, `queue_done`, `scanner_report`, `units_report`.
Then:
- any agent runtime (Claude Code, or another) drives the same pipeline with no bespoke glue;
- tool access *is* the permission boundary — a persona that lacks `ingest_rows` cannot write,
  enforced by the server rather than by the prompt;
- every call is logged server-side, which is the audit trail §2 wants, for free.

This is a real simplification, not architecture for its own sake: it replaces "paste this
brief and hope the worker runs the right command" with a typed contract.

**A2A** I would not adopt for the bulk extraction, and I want to be straight about why. A2A
buys agent-to-agent discovery and negotiation; this workload is embarrassingly parallel with
zero inter-worker communication, and a queue already handles it with far less machinery.
Adding A2A here would be complexity without a matching problem.

Where A2A *would* earn its place:
- **Adjudication** (§4.3): extractor and annotator disagree, and a third agent needs both
  readings plus the ability to question each. That is a genuine multi-party exchange.
- **Cross-organisation work**: if another group runs their own extractor over their own
  corpus and you want to compare or federate without sharing infrastructure.

My recommendation: build MCP now, treat A2A as a later experiment scoped to adjudication, and
do not let it into the critical path of a reproducible run.

---

## 10. Migration — what to do first

Order matters; each step is useful alone.

1. **Write the briefs into `docs/briefs/` and hash them into every record** (`--brief`,
   `brief_sha256`). Ten lines. Without it nothing else is auditable. *Already partly done: the
   surviving brief and work lists are now in the repo.*
2. **Queue** (§3) — removes duplicate work, collisions and rate-limit fragility.
3. **Personas as `.claude/agents/` files** (§4) — makes delegation impossible and versions the
   briefs in git.
4. **Edge set + your answers** (§7) — one hour of your time, and it becomes the gate every
   future change is measured against.
5. **Gates 1–4** (§6) on the current extractor, to get a baseline before changing anything.
6. **MCP server** (§9) once the CLI surface has settled.
7. **OpenAlex acquisition** (§8) as a new run, reported separately.

Steps 1–3 are a day. Step 4 needs you. Steps 5–7 are the interesting part, and none of it is
worth starting before 1–3, because without them we cannot tell whether a change helped.
