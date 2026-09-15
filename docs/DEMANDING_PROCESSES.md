# The expensive processes: design, budget, and the order they run in

Written 2026-09-14. Every number below was measured in this repository, not estimated from
memory; where a figure is a projection it says so.

The study has four processes that cost real time. They are designed here as one system,
because they share the same scarce resource — attention that reads a paper — and the same
failure modes: work handed out twice, work lost when a worker dies, and judgement recorded
without the instructions that produced it.

---

## 1. What each one actually costs

| Process | Unit | Volume | Measured cost | Bound by |
|---|---|---|---|---|
| **Re-extraction under a recorded brief** | one paper | 833 records with no brief, of which **491 carry measurements** | 18.2 M chars total ≈ **4.6 M input tokens**; measured-only subset 10.8 M chars ≈ **2.7 M tokens** | agent attention |
| Corpus fetch | one XML | 858 | ~3 min wall clock at 5 req/s; now **vendored**, so zero on a rebuild | Europe PMC politeness |
| Offline replay | whole corpus | 858 XMLs + 845 records | **21 s** end to end | CPU |
| NPE training + SBC | one posterior | 1 model × 50 k sims | minutes of CPU, seeded | torch |

The first row is the only one that matters for the schedule. Everything else is minutes.

**There is no OpenRouter key**, so extraction runs through the subagent path: `extract show`
prints what a worker reads, the worker writes JSON, `extract ingest` applies coercion, the
verbatim-quote guard and the condition checks. That path is not cheaper per paper — it is
the same reading — but it is bounded by agent slots rather than by an API budget.

---

## 2. The architecture it has to fit

Each piece already exists; the design is in how they compose, not in new machinery.

```
          docs/briefs/extraction.md ── sha256 ─────────────┐
                                                           │ recorded on every record
  corpus (vendored, hash-pinned)                           │
        │                                                  │
        ├── extract show  ──▶  worker reads one paper  ──▶ JSON
        │                            (judgement)           │
        │                                                  ▼
  work queue (Postgres, FOR UPDATE SKIP LOCKED)     extract ingest
        │  leases, attempts ≤ 3, disjoint claims      coerce → verify → coverage
        │                                                  │
        └── runs/<run_id>/manifest.json ◀──────────────────┤ commit, brief, model, counts
                          assignments.jsonl ◀──────────────┘ who claimed what, when
```

Four properties fall out, and each one is a failure from the first run that cannot recur:

- **Disjoint claims.** `SELECT … FOR UPDATE SKIP LOCKED` hands each worker its own papers.
  The first run assigned chunks from stale snapshots and gave two workers the same papers.
- **Work is never lost.** A lease expires and the paper returns to the queue; ten workers
  died to a rate limit last time and recovery was luck.
- **Idempotent unit.** One paper, keyed by PMCID. Re-ingesting replaces; a crash costs the
  papers in flight, not the run.
- **Provenance is enforced, not documented.** `ingest` now exits 2 without `--brief`. The
  last run's persona documented the flag before the CLI had it, and six records were written
  with no provenance at all.

---

## 3. Depth first, then width

Fanning out to N workers before measuring one is how the first run produced 845 records
nobody can audit. The order is fixed:

| Stage | Papers | What it answers | Gate before widening |
|---|---|---|---|
| **Pilot** | 10, from the gold set | How long does one worker take per paper, and does it agree with gold? | row value P/R ≥ the 12-paper gate run (0.88/0.88); zero unverified quotes |
| **Slice** | 38 remaining gold papers | Does the recorded brief move the published numbers? | `report gate --slice`, and a drift report against the stored rows |
| **Sweep** | 491 with measurements | The published table, traceable | `report reproduce` green; every record carries a brief hash |
| *(optional)* | 342 without measurements | The "no measurement" claim, traceable | same |

The pilot is not ceremony: its measured minutes-per-paper is what turns 491 papers into a
schedule, and its agreement with gold is what says the brief is good enough to spend them on.

**Scope cut, if the clock wins.** The slide's claims rest on the 498 papers that carry a
measurement. The 342 papers with none are backed by the scanner list
(`d1_papers_without_printed_values`), which is deterministic and needs no judgement at all.
Re-extract the 491; leave the 342 labelled as extracted under a brief that no longer exists.

---

## 3b. What the pilot measured (2026-09-14, run `pilot-20260914`)

Two workers, five papers each, under brief `21f2ad534dc1`, through `extract ingest` with a
run manifest. All ten are gold papers, so the result is scoreable.

| | measured |
|---|---|
| Wall clock, 10 papers, 2 workers in parallel | **3 min 37 s** |
| Per paper per worker | **0.5–0.7 min** |
| Agent tokens per paper | **~21 k** (90 k and 117 k for five papers each) |
| Rows recorded | 22, **zero dropped**, every quote verified first time |
| Row value precision / recall vs gold | **1.00 / 1.00** (7 tp, 0 fp) — the 12-paper gate run scored 0.88 / 0.88 |
| Paper instrument reported | 1.00 |
| Paper medium reported | 0.83 — **one disagreement, and it is a rule dispute, not a defect** |

**Projection for the sweep**, from the per-paper figures above:

| Scope | Papers | Agent tokens | Wall clock at 4 workers | at 8 workers |
|---|---|---|---|---|
| Measured-only (recommended) | 491 | ~10.3 M | ~75 min | ~37 min |
| Everything with no brief | 833 | ~17.5 M | ~2 h 5 min | ~62 min |

The sweep is **an hour of wall clock**, not a week. That changes the calculus: the thing worth
being careful about is not the cost, it is whether the brief is right before it is spent.

**The one disagreement.** PMC11204973 prints no zeta value at all; its only zeta text is
*"Previous experiments revealed that nanoparticle preparation in MilliQ water maintained the
Zeta potential…"*, with no citation number. The gold annotator recorded no measurement; the
worker recorded four rows in MilliQ water, and **flagged it as undecidable without being asked
to**. That is the signal the architecture predicts: two readers disagreeing on a rule nobody
has ratified, rather than one of them being wrong.

---

## 4. Optimisations that are worth it, and one that is not

- **Batch per worker, not per paper.** A worker claims 8–10 papers in one statement and
  ingests each as it finishes. The claim is the expensive round trip, not the read.
- **Per-worker scratch paths.** Shared `/tmp/<PMCID>.json` names caused workers to overwrite
  each other mid-run. Each worker writes under its own directory, named by worker id.
- **Never re-read a paper that already carries the current brief hash.** Resume is free:
  the queue skips `done`, and `ingest` is keyed by PMCID.
- **Cache the prompt, not the answer.** `extract show` output is deterministic from the
  parsed article, so a re-run costs nothing until the parser changes.
- **Not worth it: parallelising the deterministic half.** Parse, scan, verify and every
  aggregate together take 21 s for the whole corpus. Any effort spent there is effort not
  spent on the only slow thing.

---

## 5. What stops the run

| Condition | Response |
|---|---|
| A worker reports success having written nothing | Check `extractions.jsonl`, not the report — this happened three times |
| Two workers flag the same missing rule | That is a rule gap, not a confused worker; it goes to the edge set |
| A quote fails the verbatim guard | The row is dropped and counted, never silently kept |
| Gate scores below the pilot's | Stop. A worse brief spent on 491 papers is the expensive mistake |
