# mnp-research — session summary: independence, protocol, evaluation, and the sweep

Written 2026-09-17, covering work from 2026-09-14 through 2026-09-15 (six commits,
`11c0d7d`..`550f8f9`). Everything below was read back out of the repository or the git log;
nothing is asserted from memory of the conversation alone.

**Read `SESSION_SUMMARY.md` first** for the state as of 2026-09-13 (the corpus, the
pre-existing D1–D4 build, the rules wave). This file covers what changed after that: the
repository was made to stand alone, given a generated protocol and a per-stage evaluation
harness, and then used to re-read the corpus under a brief that can now be traced.

---

## 1. Why this session happened

Two requests, in order:

1. *"Make it as independent as possible, and there needs to be a protocol of all steps so it
   could be a repeatable methodology."* → three tracks: **I**ndependence, **P**rotocol,
   **E**valuation (plan file:
   `/Users/martindurak/.claude/plans/there-is-my-final-nifty-platypus.md`, addendum
   2026-09-14).
2. *"Extraction needs a comprehensive approach and evaluation of each step."* → the six-stage
   eval harness (`mnp.eval`), and — once a design pass was demanded before spending the
   expensive step — `docs/DEMANDING_PROCESSES.md`, which sizes the re-extraction and fixes its
   order: **pilot → slice → sweep**, each gated on the last.

Everything from Tracks I/P/E onward is built. The sweep is roughly a fifth done.

---

## 2. Independence (Track I) — commit `11c0d7d`

**The defect found while surveying, not asked for:** `queue.dsn()` fell back to
`DATABASE_URL`, which `config.load_env()` read out of the sibling Rust service's `.env`. A
plain `pytest` run with no `MNP_DB_URL` set therefore pointed the queue's integration tests at
the **live `nanoplastics` application database** and tried to `CREATE SCHEMA` in it. Only a
permission error stopped it — 11 errors where the README promised 11 skips. Fixed: the queue
has one variable of its own with no fall-back, and this service reads its own `.env` unless
`MNP_ALLOW_SIBLING_ENV=1` is set. `.env.example` is held against the source by an ast-based
test (`tests/test_config.py::test_env_example_documents_every_key_the_code_reads`).

**The corpus is vendored.** 858 XMLs → `data/raw/epmc/xml.tar.gz`, 27.7 MB, sha256
`9791cc01550bbd840060e0265dc985644971b2d77a479a223a0fddccb989305b`, plus a `sha256sum`-format
manifest. Deterministic build (sorted names, mode 0644, no uid/gid, no mtime, no gzip filename
header) so the hash stays meaningful across rebuilds. `corpus snapshot|verify|restore` are new
subcommands; `verify` reports extra files as loudly as missing ones.

**`report reproduce`** rebuilds every committed artefact from the vendored corpus with the
network **refused** (not merely unused — `socket.connect` raises for the duration), hashes
`extractions.jsonl` before/after to prove it wrote nothing, checks scanner-count staleness
read-only via `extract recount --check`, and names anything that differs from `HEAD`. Its
first run found three published tables that no longer followed from the data and 91 records
carrying pre-fix scanner counts — both silently fixed by re-running `recount`/`review-list`,
now regenerated and committed.

**Paths resolve late.** `ek/qa.py` and `rescale/koelmans2019.py` froze `config.DATA_RAW` at
import time, so redirecting the data root in a test depended on which module was imported
first — one `report` test was passing only by accident. Converted to functions
(`bank_path()`, `raw_dir()`, …) resolved on every call.

---

## 3. Protocol (Track P) — commit `20e7d4c`

`docs/PROTOCOL.md` (now 38 steps) is **generated** from `src/mnp/protocol.py` — never edited
by hand; a test fails if the document differs from `protocol.render()`. Each step states:
purpose (2–3 sentences), inputs, outputs, `deterministic|seeded|judgement`, idempotent?,
network?, what it's scored against, and what invalidates it. Two tests hold it against the
real CLI: every subcommand must have an entry (`ast`-parsed, not grepped — argparse
`choices=[...]` CLIs like `mnp.eval` needed a second discovery path), and every entry must
name a subcommand that still exists.

`src/mnp/runs.py`: `data/interim/runs/<run_id>/manifest.json` records the git commit (and
whether the tree was dirty), the brief hash, the model, the corpus manifest hash, counts, and
the **names** — never values — of environment keys present. `assignments.jsonl` is
append-only, one line per worker claim.

`extract ingest` now **exits 2 without `--brief`** (`--no-brief` is the explicit, logged
opt-out). 833 of 845 pre-existing records could not be traced to instructions that were
deleted with a scratchpad; this is the code-level fix so it cannot happen again silently.

`docs/briefs/gold_annotation.md` — the gold-set rules, written down and explicitly labelled a
**reconstruction**: it describes what the annotation *should* follow, not what the original
annotator read (that text is gone).

---

## 4. Per-stage evaluation (Track E) — commit `67d551d`

`python -m mnp.eval all [--fast]` scores six stages separately, each against its own ground
truth, in `src/mnp/eval/stages.py`:

| stage | metric | ground truth | current score |
|---|---|---|---|
| parse | span recall | 5 hand-located sentences in a fixture XML | **1.00** |
| scan | recall of gold values | 85 values read by hand into `gold_50.csv` | **0.98** — a number nobody had before |
| read | row value precision | `gold_50.csv` | 0.81 (was 0.47 with the S8-disputed paper included, see §5) |
| coerce | exact-match accuracy | 18 cases covering every ratified rule | **1.00** |
| verify | detection rate | 7 fabrications that each reached production once | **1.00** |
| aggregate | artefacts reproduced | the committed `out/` tree | via `report reproduce`, skipped with `--fast` |

**The rule that matters more than any threshold:** a stage with no ground truth reports
`not measured` — never 0.00, never 1.00, because both are claims nobody checked.

Two coercion defects were found and fixed while building the fixtures, both mutation-verified:
a concentration belonging to another compound was credited to a named salt (`"NaCl buffered
with 5 mM HEPES"` fabricated a 5 mM ionic strength — same family as the pre-existing
`FSW + BPA (10 µM)` defect), and Chinese approximation markers (`约为`, `大约`, `左右`) were
unrecognised, so a hedged value stored as exact.

`report reproduce` now runs `eval all --fast` itself — `eval_stages.*` had been committed
without being re-derived by the replay, which is the exact defect the replay exists to catch,
caught in its own output.

---

## 5. Rule S8 — "the plastic particle must be what was measured" — commit `9d040cd`

**Origin.** Scoring the slice (see §6) against gold, one paper decided the entire row-value
precision score: `PMC13520016` filtered its PET nanoparticles out through a 0.2 µm membrane
before every zeta measurement and tabulated "**Zeta Potential of Aβ When Exposed to MNP**".
Its own no-MNP control returned the same value (−34.0 to −27.4 mV) as the MNP-exposed rows —
the species carrying the charge was present whether or not plastic was ever added. Ratified by
Martin: **does not count**. 60 rows removed.

**Generalised into the brief** (`docs/briefs/extraction.md`, hash `21f2ad53…` →
`b1baf33e…` across four amendments): *if the plastic had never been added, would there still
be something in the cuvette with a zeta potential? If yes, the measurement is of that thing.*

**Detector, not decider.** `extract review-measurand` (`src/mnp/extract/measurand.py`) lists
papers matching the shape — particles removed before measurement, a supernatant analysed,
another material's zeta after exposure — for a human to read. It never decides. Tightening it
from a naive scan (25 hits, 16 of them "filtered prior to HPLC analysis", which says nothing
about the zeta) to the current three patterns cut it to 10 papers / 28 rows; both false-positive
shapes are pinned by tests.

**Applying it exposed the rule was too blunt as first written**, and two boundaries were
ratified on top of it:

- **S21** — residual plastic particles suspended in a *treated* water are still particles.
  ("Plastic of course.") The rule removes a measurement when the plastic is *gone* from the
  cuvette or was never the analyte; it does not remove one because the water around the
  particles was treated. 4 rows restored to `PMC12105431` that a first-pass audit had wrongly
  swept out (and a 5th, the paper's *direct* pH-series measurement, was recorded when the
  audit nearly left the paper at zero rows — a genuine near-miss caught by re-reading, not by
  any test).
- **S23** — the tiebreaker for two mixed colloid populations. S8's own test ("would there
  still be something in the cuvette?") answers yes either way when both species are particles,
  so it decides nothing. New rule: **is the other material adsorbed onto the plastic?**
  Adsorbed → a coated plastic particle, record it (a protein corona is the textbook case, and
  **S18** — PS in serum-containing culture medium — was answered *by implication* from this,
  flagged as such rather than presented as a separate ruling). Free in suspension alongside it
  → a mixture, record nothing.
- **S22** — recorded **provisional, not counted**: one paper gives a single wastewater number
  rather than a per-polymer value, with the added plastic granules largely outside the
  instrument's practical range. Reverses if a per-polymer value ever surfaces.

**Net effect on the corpus** after all four rulings: 498 → 491 papers, 1910 → 1890 rows (per
current `d1_stats.json`; the exact count moved twice more inside this range as S21/S22/S23
were applied — see the CHANGELOG for the intermediate 493/1880 checkpoint). **No headline
missing-condition fraction moved by more than 0.4 points** — the argument was never resting on
the rows that were wrong.

---

## 6. The re-read itself — pilot, slice, wave 1 — commits `fc7960b`, `550f8f9`

Depth-first by design (`docs/DEMANDING_PROCESSES.md`): measure one worker on ten papers before
spending hundreds. Every stage ran through `extract show` → an agent reads → `extract ingest
--brief … --run-id … --worker …`, never the OpenRouter API path (no key is configured; not a
blocker for this path).

| stage | papers | workers | rows | dropped | tokens/paper | wall clock |
|---|---|---|---|---|---|---|
| **Pilot** (10 gold) | 10 | 2 | 22 | 0 | ~21k | 3 min 37 s (parallel) |
| **Slice** (28 more gold) | 28 | 4 | 196 | 0 (2 fixed in-flight) | ~19k | ~10 min longest worker |
| **Sweep wave 1** | 80 | 8 | 320 | **0** | ~17.8k | one wave, parallel |

**All 50 gold papers now carry a brief hash.** Scores against gold, excluding the S8-disputed
paper: row value P/R **0.68→0.81 / 0.74→0.80**; row temperature **0.15→0.76** (this was the
study's known-bad field — the old extraction recorded incubation temperatures as measurement
temperatures, now enforced by rule 2 in the brief and in `coerce.parse_temperature` /
`zeta.verify_row`); paper-level instrument, pH and temperature reach **1.00 / 1.00**. The
residual pH/ionic-strength dip is row-count *granularity* (a worker expanding a collective
statement into one row per particle where gold recorded one), not wrong values — across every
matched row pair in the slice there are only 4 pH disagreements total.

**134 of 848 records now trace to a brief** (was 12 before this session). **388 remain** on
`data/interim/worklists/sweep_20260915.txt`.

### Defects wave 1 found that no test would have (all fixed, mutation-verified, commit `550f8f9`)

Two were **silent corruptions** — wrong data that looked right:

1. `_RANGE` matched only `to`/`-`, so `"between −34 mV and −48 mV"` parsed as **−34.0 with no
   flag** — a fabricated precision, indistinguishable from a paper that printed one number.
   Found by a worker who had to rewrite the paper's own words to get the range recognised.
   Fixed with a wider connector set (`to|and|[-–—~]`) plus a signed-number pattern and an
   optional embedded unit token (`-?\d+(?:\.\d+)? (?:mV|V)? (?:to|and|…) -?\d+…`).
2. An unreadable unit (nonlinear mobility, `cm⁴V⁻³s⁻¹`) made `normalise_unit` return `None`,
   which the caller read as *"no unit was printed"* and filled in the conventional default —
   storing a plausible number in the **wrong** unit under a flag (`unit_assumed_…`) that
   asserts the paper printed nothing. It printed something unreadable. Now refuses the row
   with `unit_unrecognised` instead.
3. `OTHER_STEP_RE` (the incubation/exposure guard) tested the **whole joined evidence quote**,
   so a genuine "measured at 25 °C" was flagged `temperature_step_not_measurement` whenever
   *any other piece* of the same quote mentioned a culture or exposure. **Five separate
   workers** (across the slice and wave 1) hit this and every one worked around it by
   *trimming their evidence* — meaning the guard was punishing the more complete quote, exactly
   backwards. Fixed: the check now runs only on the quote-piece that actually carries the
   number (`_piece_with()` in `zeta.py`).

---

## 7. Current verified state

```
uv run pytest -q                    → 817 passed, 11 skipped, 2 deselected
uv run ruff check src tests         → All checks passed!
uv run python -m mnp.report reproduce → reproduced: every committed artefact rebuilt byte for byte
```

D1 headline (`out/tables/d1_stats.json`, current):

| condition | k/n | fraction | 95% Wilson |
|---|---|---|---|
| Ionic strength | 440/491 | 89.6% | 87–92% |
| pH | 392/491 | 79.8% | 76–83% |
| Temperature | 383/491 | 78.0% | 74–81% |
| Dispersion medium | 127/491 | 25.9% | 22–30% |
| Instrument | 90/491 | 18.3% | 15–22% |
| **Any of the five** | **477/491** | **97.1%** | 95–98% |

141 of 491 papers with a measurement print no number anywhere retrievable. 11 of 858 fetched
XMLs have **no retrievable text at all** (conference-abstract volumes, PDF-only deposits) —
`report d1` now counts these apart from papers that were read and found to report nothing;
found independently by two different workers who both flagged the ambiguity unprompted.

**Edge case key** (`tests/edge/key.yaml`): **69 cases, 8 answered, 61 open.** The open ones
by family:

- `A1`–`A5`, `C3/C4/C6/C7/C8`, `M1`–`M7`, `V1`–`V7` — the original 24 from before this
  session, still unanswered (material boundary questions: polymersomes, functional core-shell
  coatings, whether a cited value counts, whether "see Table S1" makes a measurement
  reported).
- `P1`–`P7` — raised by the pilot (2 workers, 10 papers).
- `S1`–`S17`, `S19`, `S20`, `S24`–`S35` — raised by the slice and wave 1 (a mix of granularity
  rulings, material-boundary questions — elastomers/silicones at `S31`, combustion-derived
  particulate at `S29` — and two the *code cannot settle at all*: `S35` a paper prints its
  zeta as bare `"± 45"` with no sign, and `S33` a paper's own table captions contradict its
  body text on which medium is which).

None of the open cases block the sweep from continuing — they're recorded as the worker's
best guess, flagged rather than silently resolved, per the standing instruction. They do mean
some fraction of sweep rows will need re-adjudication if a future ruling reverses a guess a
worker already made (the same mechanism that moved `PMC12105431` and `PMC11857315` this
session).

---

## 8. Next planned steps

**Immediate — continue the sweep.** `data/interim/worklists/sweep_wave2.txt` is already cut
(80 papers, 8×10, same disjoint-batch pattern as wave 1) and ready to launch. At wave 1's
measured rate (~17.8k tokens/paper) the remaining 388 papers project to **~6.9M tokens** total,
~5–6 more waves of this size. Nothing about the pipeline changes between waves; each wave is:

1. Launch 8 parallel worker agents, each with its own 10-paper batch and its own `/tmp`
   scratch directory, brief `docs/briefs/extraction.md` (whatever hash is current), `--run-id
   sweep-<date>`.
2. As each reports, verify against `extractions.jsonl` (never the agent's own prose) —
   row counts, brief hash, dropped-row count.
3. Fold every "brief was silent here" report into `tests/edge/key.yaml` as a new case; do not
   let a worker's guess silently become policy.
4. Watch for **recurring** gaps across ≥2 workers — that's the signal a rule is missing, not
   that a worker was confused (this is how the three coercer/verifier fixes and the
   incinerated-PE/elastomer boundary questions surfaced).
5. Once nothing is calling `extract`, apply any code fixes the wave surfaced, mutation-verify
   each, re-run `extract table` → `report d1` → full test suite → `report reproduce`, commit.

**Needs Martin, in priority order (by how many rows they move):**

1. **`S5`** (from the slice, still open) — does a condition stated in Methods reach a value
   printed in Results for the same quantity? Four separate workers (`S5`, `S24`, `S25`, `S26`)
   have now converged on variants of this question. It is the single highest-leverage open
   ruling: it moves more rows than any other open case, because it's the *commonest sentence
   shape* in the corpus, not an edge case.
2. **`S29`** — is combustion-derived particulate from plastic feedstock (incinerated PE, 99.7%
   carbonaceous) a plastic particle? Decides whether a whole sub-literature (incineration
   studies) enters or leaves the corpus.
3. **`S31`** — are elastomers and silicones (rubber-latex, silicone-rubber nanoparticles) in
   scope, or does "plastic" mean thermoplastics only?
4. The 24 pre-existing `A/C/M/V` cases from before this session — still block gate 2
   (`report gates`) and the fully-adjudicated edge suite; not blocking the sweep itself.
5. **`data/interim/annotation/audit_10.csv`** — ~1 hour blind re-judgement of 10 gold papers,
   for the Cohen's κ line. Until filled, the slide must say "annotated by Claude, not yet
   audited."

**After the sweep finishes (all 468 papers traced):** re-run `report all` for a fully
traceable D1 table, decide whether to extend to the 342 papers with no printed value (currently
backed by the deterministic scanner list alone — no judgement needed there, per the stated
scope cut in `docs/DEMANDING_PROCESSES.md` §3), and reconsider `report gates` / gate 2 once the
24 legacy edge cases have answers.

**Not started, no plan yet:** OpenAlex corpus expansion (documented as future work in
`docs/ARCHITECTURE_PLAN.md` §8, not touched this session); the MCP server wrapping the CLI
(§9, same); D2/D3/D4 are untouched and still current from before 2026-09-13.
