# mnp-research — session summary and handoff

Written 2026-09-13. Everything below was read back out of the repository; where a number
could not be verified it says so.

**Read this first, then `SESSION_2026-09-13_RULES.md`** (the three judgement rules Martin
ratified, what they cost, and why the table below is the pre-rules reading), **then
`docs/ARCHITECTURE_PLAN.md`.** The service is two things at once: a
finished literature study (D1–D4, numbers below), and a half-migrated pipeline that is being
rebuilt so the study can be reproduced by someone else.

---

## 1. What the study found

All 858 open-access full texts were parsed; every paper mentioning zeta potential or
electrophoretic mobility was read. **498 papers report a plastic-particle measurement**
(1 910 rows, every row's evidence quote verified verbatim against the article).

| Missing condition | k / 498 | fraction | 95% Wilson |
|---|---|---|---|
| Ionic strength | 447 | 89.8% | 87–92% |
| pH | 399 | 80.1% | 76–83% |
| Temperature | 386 | 77.5% | 74–81% |
| Dispersion medium | 131 | 26.3% | 23–30% |
| Instrument | 91 | 18.3% | 15–22% |
| **Any of the five** | **484** | **97.2%** | 95–98% |

**144 of the 498** report a measurement without printing a number anywhere in the retrievable
text — figure, supplement or qualitative statement only.

**These numbers predate the three rules ratified on 2026-09-13** (§9). Scored against those
rules without re-reading a paper (`tool/rules_impact.py`, `out/tables/rules_impact.md`),
temperature missing moves to **82.5%**, pH to **83.9%**, and ionic strength to **≥76.7%**.
The re-extraction under the recorded brief is what makes the published table current.

A 50-paper hand-annotated sample agrees on every row and its interval covers the corpus value
(`out/tables/d1_gold_stats.md`). Quote either; they were produced by different methods.

**One figure not to quote from the corpus: temperature.** The extraction records an
*incubation* temperature as the measurement temperature (row-level P 0.15 in the corpus run).
Use the gold number, 18 of 24. The rule is now ratified and enforced in code (§9), but the
corpus rows were produced before it.

D2 (schema + checklist), D3 (rescaling) and D4 (Ohshima soft-particle model, MCMC + NPE,
SBC) are complete; artefacts in `out/`.

---

## 2. What is trustworthy, and what is not

**Trustworthy.** The corpus, the parser, the value scanner, the verifier, every aggregate,
and the test suite: **737 tests, ruff clean**. Re-running `corpus parse`, `extract recount`
and `report all` from the stored XML reproduces every published number.

**Not trustworthy as provenance.** 833 of 845 extraction records carry `brief_sha256: null`.
They were produced before briefs were versioned, and the brief that governed most of the
corpus was kept in a session scratchpad and **has been deleted**. For any such row you can
say which model produced it, not under which instructions. `docs/briefs/extraction.md` is a
reconstruction, labelled as one.

The gate reports this every run, so the debt stays visible:

```
Provenance: 12 of 845 records carry a brief hash.
833 records cannot be traced to their brief: PMC10020838, …
```

---

## 3. How to run it

```bash
cd services/mnp-research
uv sync --all-groups
export MNP_CONTACT_EMAIL='you@example.org'          # Europe PMC requires a contact

uv run pytest -q                                    # 737 tests, ~12 s
uv run ruff check src tests

./tool/test_db.sh up                                # throwaway Postgres for queue tests
export MNP_DB_URL=postgresql://mnp:mnp@localhost:55432/mnp

uv run python -m mnp.report all                     # rebuild every deliverable
uv run python -m mnp.report gates --slice data/interim/worklists/gate3_slice.txt
```

Queue tests **skip** when no database is reachable — they do not fail. If you see
`11 skipped`, start the database.

---

## 4. The pipeline

| Stage | Module | Deterministic |
|---|---|---|
| search / fetch / parse | `corpus/` | yes |
| scan for printed values | `extract/zeta.py::find_candidates` | yes |
| **read the paper, write rows** | a worker agent | **no — judgement** |
| verify rows against the article | `extract/zeta.py::verify_row` | yes |
| read the printed unit from the article | `extract/units.py` | yes |
| aggregate and report | `report/` | yes |

The split is the design: a scanner that knows nothing about materials, a worker that judges,
a verifier that checks the judgement against the text. Each has caught errors the others
could not.

`coverage` is **not recall**. The scanner finds printed zeta values of any material, so a
paper reporting zeta for a metal oxide alongside its plastic scores low while being extracted
correctly.

---

## 5. Machinery built this session (steps 1–4 of the plan)

| Piece | File | What it prevents |
|---|---|---|
| Brief provenance | `extract/provenance.py`, `ingest --brief` | a rule change invisible in the data |
| Work queue, leases | `queue.py` (Postgres, `FOR UPDATE SKIP LOCKED`) | two workers given the same paper; work lost when a worker dies |
| Agent personas | `.claude/agents/` × 4, **none with the Agent tool** | workers delegating and reporting success having done nothing |
| Gates 1–4 | `report/gates.py`, `report/gate.py`, `report/edge.py` | shipping a persona nobody measured |
| Edge set | `tests/edge/` (27 cases) | judgement rules nobody ever ratified |

Two rules inside the gate matter more than the thresholds: a field with **no ground truth is
not scored** (precision 0.00 on zero true positives says nothing about a persona), and
**provenance is part of the verdict**.

---

## 6. What the gate found when it was first run

Two workers, twelve gold papers, claiming from the queue, blind to the stored records and the
gold set. It found **six defects before a corpus sweep rather than after** — three of them
introduced the same day, by me:

1. `--brief` documented in the persona but never wired into the CLI, so a compliant worker
   produced six records with no provenance at all.
2. An unrelated concentration in a medium string (`"FSW + BPA (10 µM)"`) recorded as a
   **reported** ionic strength — inflating the study's headline metric.
3. `<0 mV` parsed as `0.0` — a fabricated measurement, with the wrong sign.
4. A not-zeta phrase anywhere in a paragraph suppressing real values 400 characters away.
5. `accelerat` matching the ordinary verb "accelerates".
6. Polymersomes and functional core-shell coatings undefined in the brief — flagged
   independently by both workers, which is the signal a rule is missing rather than a worker
   confused.

All fixed and mutation-verified. **Three mutations first came back green**: the test proved
nothing until it was rewritten to discriminate. That pattern recurs — treat a green mutation
as a broken test, not a safe change.

Scores on that slice after the fixes: row value P 0.88 / R 0.88 (corpus run 0.68 / 0.74), row
temperature 0.57 / 0.57 (corpus run 0.15 / 0.23), paper-level instrument, pH and temperature
1.00. **Twelve papers is indicative, not a result.**

---

## 7. Open items

**Needs Martin, blocks gate 2.** `tests/edge/key.yaml` — **3 of 27 answered** (C1, C2, C5,
see §9). The 24 open ones are his too: the material boundary (polymersomes? functional
core-shell coatings?), whether a cited value counts, whether a "see Table S1" pointer makes a
measurement reported. That last one — case **V7** — is not hypothetical: it is why the corpus
moved from 499 papers to 498 when a gate worker re-read PMC5876619 and the gold annotator's
"si_only" row disappeared. The personas encode *my* reading of the other 24, ratified by
nobody; three of the cases were contributed by workers who disagreed with it.

**Needs Martin, blocks §6 of the plan.** Which eval framework to wire the gates into —
DeepEval, promptfoo, DSPy, Inspect, Langfuse? The gates are a plain scorer today; adapting
them is small once the choice is made.

**Needs Martin, one hour.** The blind audit sheet `data/interim/annotation/audit_10.csv`
(41 rows, 10 papers) for Cohen's κ. Until it is filled the slide must say "annotated by
Claude, not yet audited".

**Open engineering, in order.**

1. Re-extract under a recorded brief. 833 records are untraceable; that is the debt.
2. Schema gap: TEM/SEM *primary* size has no field. `size_measured_nm` is pinned to the
   hydrodynamic ontology term and `size_nominal_nm` means the supplier's claim, so a
   dry-size measurement currently has nowhere to go.
3. Source expansion. OpenAlex holds ~3 513 works on this topic against our 858, and **78% of
   a 600-work sample is not in our corpus**. Chinese groups are ~29% of the field but publish
   in English-language journals — the gap is the index, not the language, so the fix is
   OpenAlex as a discovery layer, not translation. Europe PMC holds **4** Chinese-language
   papers on this topic. Tripling the corpus changes every denominator: run it as a separate
   `run_id` and report both.
4. MCP server wrapping the CLI, so tool access becomes the permission boundary. A2A is
   **not** recommended for bulk extraction (embarrassingly parallel, no inter-worker
   communication); scope it to adjudication if at all.

---

## 8. Traps that cost time, so they do not cost it twice

- **A green mutation means a broken test.** Happened three times in one session.
- **Verify agent reports against the data.** One worker reported success having processed
  zero papers; another's "300× spread" alarm was my own analysis error, caught only by
  re-checking. Both were found by reading `extractions.jsonl`, not the report.
- **Per-worker scratch paths are mandatory.** Shared `/tmp/<PMCID>.json` names caused
  concurrent workers to overwrite each other mid-run.
- **Evidence quotes must be literally contiguous.** Joining a table header to a
  non-adjacent row with a newline fails verification; use `" || "` for separate pieces.
- **Do not filter the population on the thing you are measuring.** Extracting only papers
  that print a value hid the 144 papers that report a measurement without one.
- **`uv run` from the service directory**, and a failed `cd` in a compound command silently
  skips the rest of the chain — that swallowed a patch once.

---

## 9. The three rules, ratified 2026-09-13

Martin settled the three rules that every judge disagreed on (`docs/DECISIONS_NEEDED.md`
carries the papers' own words, the judges' verdicts and how much each rule moves):

1. **A printed composition is an ionic strength**, recorded as derived — 0.137 M NaCl +
   0.0027 M KCl = 139.7 mM. A component whose speciation is unstated contributes nothing.
2. **An incubation temperature is not the measurement temperature**, even when the paper
   gives no other temperature.
3. **A condition applies only within the experiment that states it.**

Now in `tests/edge/key.yaml` (C1/C2/C5), `docs/briefs/extraction.md` (hash `0266af56…` →
`21f2ad53…`), the worker system prompt, and both personas. Enforced by
`coerce.parse_ionic_strength`, `coerce.parse_temperature` and `zeta.verify_row`'s new
`*_not_in_evidence` and `temperature_step_not_measurement` flags — every guard
mutation-verified.

**The judges, scored against Martin rather than each other:** claude-1 κ +1.00 (16 cases),
external nemotron +0.34, claude-2 +0.22. Each got one entire rule wrong, a different one
each. No single judge runs unsupervised; a panel is a detector of *which* cases are rule
disputes (it was perfect at that — all 17 were), not a decider of them.
