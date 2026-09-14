# Session handoff — the three judgement rules, ratified

Written 2026-09-13, at the end of the session that settled them. Every number here was read
back out of the repository after the last change; where something is an estimate rather than
a measurement it says so.

**Read `SESSION_SUMMARY.md` first** for what the study is and what the pipeline does. This
file covers only what this session changed, and it is the file to start from if you are
picking the work up cold.

---

## 1. What this session was for

Three rules decided how the study's headline number is computed, and the brief was silent or
ambiguous on all three. Three LLM judges had been given the same 17 gold-vs-extraction
disagreements; they split along the rules rather than along the readings, and κ between two
judges of the same family was **−0.05** — worse than chance. No amount of judging settles a
rule. It needed a person.

Martin answered. This session recorded the answers, put them into the code, measured what
they cost, and scored the judges against them.

## 2. The three rules

| | Question | Decision |
|---|---|---|
| **Q1** | Does a printed PBS recipe count as a reported ionic strength? | **Counts, flagged as derived.** A stated composition establishes ionic strength when the calculation follows directly from explicitly stated ionic species and concentrations. 0.137 M NaCl + 0.0027 M KCl = 139.7 mM; phosphate at an unstated pH contributes nothing. |
| **Q2** | Is an incubation temperature the measurement temperature? | **No.** Only a temperature explicitly associated with the zeta-potential measurement counts. Incubation, exposure and culture temperature are separate conditions — even when the paper gives no other temperature, and even when temperature is the paper's own variable. |
| **Q3** | Does a condition stated in one part of a paper carry to another? | **Only within the experiment where it is stated.** Do not propagate conditions across distinct preparations or measurements unless the paper explicitly establishes that they apply. |

Recorded in five places, so a reader of the data can find the rule that produced it:

- `tests/edge/key.yaml` — cases **C1, C2, C5**, with the reasoning.
- `docs/DECISIONS_NEEDED.md` — checkboxes ticked, plus the papers' own words and the judges'
  verdicts. Now a decision record, not an open question.
- `docs/briefs/extraction.md` — sha256 moved **`0266af56…` → `21f2ad53…`**. Every record
  ingested from here on carries the new hash, so the rule change is visible in the data.
- `src/mnp/extract/prompts.py` — worker system prompt, rules 6–8. `prompt_sha256` moved to
  **`b3790c68…`**.
- `.claude/agents/mnp-extractor.md` and `mnp-gold-annotator.md`.

## 3. What changed in the code

Each guard was mutation-verified: the fix reverted, a named test watched to go red, the fix
restored. Six mutations, six reds.

| Rule | Change | Flag it raises |
|---|---|---|
| Q1 | `coerce.parse_ionic_strength` reads spelled-out salt names (`_SALT_WORDS`) and sums a printed composition segment by segment (`_salt_terms`) | `derived_from_composition` |
| Q2 | `coerce.parse_temperature` returns null when the string names another step (`OTHER_STEP_RE`) | `temperature_not_measurement` |
| Q2 | `zeta.verify_row` catches a temperature whose quote is an incubation sentence | `temperature_step_not_measurement` |
| Q3 | `zeta._scope_flags` requires each condition to appear in the row's **own** evidence quote, not merely somewhere in the article | `pH_not_in_evidence`, `temperature_not_in_evidence`, `ionic_strength_not_in_evidence` |

The Q3 check is what makes "only within the experiment" mechanically checkable: a worker that
carries a condition must quote the sentence establishing it beside the value's row (join with
`" || "`). Before this, conditions were checked against the whole article, which passes any
condition stated anywhere in the paper — exactly the reading the rule forbids.

`parse_ionic_strength` keeps its old behaviour on everything it already handled: `10 mM NaCl`
→ 10, `10 mM CaCl2` → 30 with `computed_from_salt`, `FSW + BPA (10 µM)` → still nothing.

**One fixture had to change.** `ROW_NACL` in `tests/extract/test_zeta.py` recorded a pH from
the Methods with a Table 1 quote — the exact pattern Q3 forbids. Its quote now carries the pH
sentence too. That is the rule working, not a test bent to fit.

## 4. What the rules cost

`tool/rules_impact.py` re-scores the stored corpus under the new rules without re-reading a
paper, and writes `out/tables/rules_impact.md`. Its "missing now" column reproduces D1's
numbers exactly, which is the check that it counts the same way D1 does.

| Condition | missing now | under the rules | rule |
|---|---|---|---|
| Temperature | 386 / 498 = 77.5% | **411 / 498 = 82.5%** | Q2 + Q3 |
| pH | 399 / 498 = 80.1% | **418 / 498 = 83.9%** | Q3 |
| Ionic strength | 447 / 498 = 89.8% | **≥ 382 / 498 = 76.7%** | Q1, upper bound |

Q1 moves the figure the other way, and its number is a **bound, not a result**: it counts
papers whose full text holds two or more salt+concentration terms, which is an upper limit on
how many could gain an ionic strength. Whether those salts describe the measurement medium is
a judgement only a re-extraction can make.

**The published D1 table is the pre-rules reading.** `README.md`, `SESSION_SUMMARY.md` and
`CHANGELOG.md` all now say so at the point where they show the numbers. Re-extraction under
the recorded brief is what makes them current, and it is open item #1.

## 5. The judges, scored against the human answers

Ground truth for all 17 disputed cases was derived from the three rules and stored at
`data/interim/worklists/judge_key_human.json`. Scoring used `report/judge.py`
(`cohen_kappa`, `bootstrap_ci`, 3000 resamples, seed 11).

| Judge | n scored | agreement | Cohen's κ (95% CI) |
|---|---|---|---|
| claude-1 (blinded, order 1) | 16 | **100%** | **+1.00** (1.00 – 1.00) |
| external (nemotron-3-super-120b, API only, no filesystem) | 14 | 64% | +0.34 (0.00 – 0.71) |
| claude-2 (blinded, order 2) | 14 | 57% | +0.22 (0.00 – 0.59) |

Per rule, correct / cases:

| | Q1 (6) | Q2 (6) | Q3 (4) |
|---|---|---|---|
| external | 0 | 6 | 4 |
| claude-1 | 5 | 6 | 4 |
| claude-2 | 6 | 0 | 1 |

**How to read this.** Claude-1's κ = 1.00 is one 17-case set, judged by the family that wrote
both the pipeline and the brief; shared assumptions explain it as well as correctness does.
Do not quote it as evidence that a Claude judge is accurate.

What the table does establish is the negative, and it is solid: **each judge got an entire
rule wrong, and a different one each time.** No single judge can run unsupervised.
Majority-of-three would in fact have landed all three rules correctly here — on 2–1 margins
over 4–6 cases each, so one judge changing its mind flips it. Treat a panel as a detector of
*which* cases are rule disputes (at that it was perfect: all 17 were rule questions, none was
a misreading) and never as the decider of them.

Earlier pairwise numbers, for the record: external-vs-claude-1 κ +0.41, claude-1-vs-claude-2
**−0.05**, external-vs-claude-2 −0.66. The external judge was the most self-consistent (93%
order consistency, 16/17 grounded) and still agreed with neither Claude.

## 6. Two things found on the way

**The corpus is 498 papers / 1 910 rows, not 499 / 1 914.** The gate run re-extracted twelve
gold papers under a recorded brief, and PMC5876619 came back with no rows: the worker declined
to record a measurement the paper only points to ("see Table S1 for … zeta potentials"), where
the gold annotator had recorded one with a null value and the note `si_only`. That is edge
case **V7**, still unanswered. One paper, one unratified rule, and it moved the headline
denominator — which is the argument for answering the other 24 cases.

All the published tables were rebuilt at the new counts (`python -m mnp.report d1`), and
`README.md`, `SESSION_SUMMARY.md`, `docs/METHODOLOGY.md` and `CHANGELOG.md` were corrected.

**Gate 2 printed FAIL for a failure nobody caused.** The moment the key had its first three
answers, the runner — which passes an empty persona dict, because the CLI never asks a
persona anything — scored 3 answered cases against silence and reported 0% agreement. A
persona that was asked and stayed silent is a disagreement (that is deliberate, and tested).
A persona that was never asked has failed nothing. `gates.run_all` now distinguishes
`persona_answers=None` from `{}` and reports `passed: None` with the reason.

## 7. State at the end of the session

```
737 tests pass, 2 deselected           uv run pytest -q          (11 queue tests need the DB)
ruff clean                             uv run ruff check src tests tool
```

Gates on the pilot slice (`uv run python -m mnp.report gates --slice data/interim/worklists/gate3_slice.txt`):

```
Gate 1 contract — PASS          12 records
Gate 2 edge     — not evaluated 3 answered; no persona verdicts supplied
Gate 3 gold     — PASS          12 gold papers, 7 with predicted rows, 4 agreeing empties
Gate 4 pilot    — not evaluated 45 rows, 3.75 rows/paper, mean coverage 0.659
```

The queue needs `./tool/test_db.sh up` and
`export MNP_DB_URL=postgresql://mnp:mnp@localhost:55432/mnp`; without it those 11 tests skip
rather than fail. With a *wrong* `MNP_DB_URL` they error — which is how they should behave,
but read the error before assuming the code broke.

## 8. What to do next, in order

1. **Re-extract under the recorded brief.** This is the debt the rules created and the one
   they were meant to pay: 833 of 845 records still carry `brief_sha256: null`, and every
   published D1 number is the pre-rules reading. Use the queue
   (`python -m mnp.queue init/claim/done`), the `mnp-extractor` persona, and
   `extract ingest --brief docs/briefs/extraction.md`. Run it as a separate `run_id` and
   report both readings — the denominators change.
2. **Answer the remaining 24 edge cases**, V7 first (§6). Gate 2 stays unevaluated until a
   persona is actually asked them; wire the persona's verdicts into
   `gates.run_all(persona_answers=…)`.
3. **Fill `data/interim/annotation/audit_10.csv`** (41 rows, 10 papers) for Cohen's κ between
   annotators. Until then the slide must say "annotated by Claude, not yet audited".
4. **Name the eval framework** for `docs/ARCHITECTURE_PLAN.md` §6 — DeepEval, promptfoo,
   Inspect, Langfuse. The gates are a plain scorer today; adapting them is small once chosen.
5. Longer-term, unchanged: the TEM/SEM primary-size schema gap, OpenAlex as a discovery layer
   (~3 513 works against our 858; 78% of a 600-work sample is not in our corpus), and an MCP
   server so tool access becomes the permission boundary.

## 9. Traps this session confirmed

- **A green mutation means a broken test.** Six mutations were run here and all six went red,
  because the tests were written to discriminate. Earlier in the project five came back green
  and proved nothing.
- **A rule change that makes a test fail may be the rule working.** `ROW_NACL` failing under
  Q3 was correct behaviour. Check which of the two is wrong before editing either.
- **Re-derive a headline before quoting it.** `out/tables/d1_stats.json` was four hours stale
  and said 499 papers while the live store said 498. Timestamps, then rebuild.
- **An empty input is not agreement, in either direction.** The key's blank verdicts were
  already excluded from scoring; the persona's silence was not. Both halves need the rule.
- **Verify a claim against the data, not the report.** The corpus lost a paper and nothing
  announced it; it surfaced only by counting rows in `extractions.jsonl` and comparing.
