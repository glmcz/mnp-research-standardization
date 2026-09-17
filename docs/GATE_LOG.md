# Gate log

Every step that spends model tokens gets a card, two verdicts, and a row here. Written by the
caller, never by the agents. Design in `DESIGN_2026-09-17_tool-value-grid.md` §4.

Reviewers: `.claude/agents/mnp-gate-engineer.md` (measurable, reproducible, affordable, in
scope) and `.claude/agents/mnp-gate-scientist.md` (right measurand, conditions carried,
comparability not asserted for free).

**Both must `ALLOW`, or the step escalates to Martin.** Neither can `REJECT` — the panel in
this repo detected disagreement 17/17 and decided at κ = −0.05, so the gates find the fork and
Martin picks the branch.

## The card

```
STEP:       <what>
WHY:        <why now>
FILES:      <touched>
TOKENS:     <estimate> — <what makes it that many>
FAILS IF:   <the measurement that would show it did not work>
ABSTRACT:   "<the sentence it serves, quoted>"
PLAN:       <the item in DESIGN_2026-09-17_tool-value-grid.md §5>
```

A card missing `ABSTRACT` or `PLAN` is escalated unread. A `TOKENS` estimate with no stated
basis is escalated too — the estimate is what the gates are there to argue with.

## Ungated by design

Deterministic, zero-token work is not gated: it costs nothing and the plan's §5 order runs it
first. That covers the converter, the release form, the corpus arithmetic, and anything else
that spends no model tokens. The gates exist for §5 items 11–14, the expensive half.

---

## Verdicts

| date | step | engineer | scientist | outcome |
|---|---|---|---|---|
| 2026-09-18 | Card 1 — citation-scoped verification | ESCALATE | ESCALATE | **not built.** Blocked on the scope question below |

---

## Card 1 — citation-scoped verification

Submitted 2026-09-18. Awaiting both verdicts.

```
STEP:       Change verify_row (src/mnp/extract/zeta.py:415-451) to check the value
            against the LINE the row cites, instead of against the quote string the
            model itself wrote. The quote check stays as a second signal; the cited
            line becomes the primary one.

WHY:        Today the model authors the string it is judged on. verify_row asks only
            that the quote be a substring of the article, so a model can trim its
            evidence until it passes. Five independent workers did exactly that, to
            pass a guard that punished the fuller quote. Seven fabricated quotes
            reached production before the guard existed. A row that cites a line
            returns a reference and has nothing to trim. P2.1 has just put a
            resolvable line_id on every row, so the primitive now exists.

FILES:      src/mnp/extract/zeta.py — verify_row :415-451, _piece_with :454-459
            tests/extract/test_zeta.py
            tests/eval/fixtures/verify_adversarial.json (read only, 7 known defects)

TOKENS:     ~0 at runtime. The guard is deterministic: no model, no network. Re-verifying
            all 1 890 rows is a pass over stored records and the parsed corpus, which
            rebuilds in 21 s. The only model tokens this step spends are the two gate
            reviews themselves, ~60 k.

FAILS IF:   evidence_verified moves off 1 890 / 1 890 without a per-row account of every
            row that changed; OR fabrication detection on verify_adversarial.json drops
            below the current 7/7; OR any row's conditions stop being checked against
            that row's own evidence, which is Martin's scope rule of 2026-09-13.

ABSTRACT:   "To ensure comparability across studies, it is necessary to account for
            particle size ranges and analytical method limits, surface properties,
            measurement conditions, and environmental parameters."

PLAN:       DESIGN_2026-09-17_tool-value-grid.md §5 item 1 — the last piece of the S1
            converter. §2 names this guard as the failure mode line citation removes
            structurally.
```

**Known risk, stated rather than discovered:** this can move a denominator.
`evidence_verified` is 1 890 / 1 890 today and that figure is on the dataset card in
`out/release/DATASET_CARD.md`, which is committed and inside the reproduction claim. If the
number moves, the card moves, and anyone who already read it read something else.

**Second risk:** `verify_row` receives `article.full_text`, the whole article, while the
line-addressed document covers only the extraction view. A quote living outside that view is
verifiable today and would not be line-citable. Phase 1 and the P2.1 retrofit both measured
that gap at zero, but zero measured twice is not zero by construction.

### Verdicts on Card 1 — both ESCALATE, 2026-09-18

Neither reviewer predicted; both ran the change and measured it. The claims below were then
re-checked independently against the published table before being written down here.

**Engineer.** The card's own `FAILS IF` is already tripped by the step as specified. Put the
seven cases of `tests/eval/fixtures/verify_adversarial.json` through the change and detection
falls from **7/7 to 5/7**. Case 6 is "condition carried in from another experiment", which *is*
Martin's scope rule of 2026-09-13. Case 4 is a non-contiguous quote glued across a newline:
`lines._match` splits passages on newlines by design, which is right for a locator and wrong for
a guard.

Second engineer finding, since it bears on every future card: on the retrofitted 1 890 rows the
change is **monotone-permissive and can catch nothing new.** The line ids were derived *from*
the quotes by substring, so every cited line already contains its quote. Flags can only be
removed. The untrimmable-evidence property the card sells binds only rows extracted *after* the
guard exists, and no re-extraction is in budget.

**The card was also defective, and the engineer caught it.** `FILES` named one caller of
`verify_row`. There are three outside the tests: `zeta.py:673`, `eval/stages.py:265`,
`tool/rules_impact.py:44`. A signature change breaks `measure_verify`, which is the very 7/7
measurement the card's own `FAILS IF` rests on. Verified by grep.

**Scientist.** A line is a paragraph, so "the row's own evidence" silently grows about **3.8×**
at the median. Thirty-four rows lose a scope flag — a condition read from a neighbouring
experiment becoming clean — and 123 gain `temperature_step_not_measurement` because
`_piece_with` can no longer isolate the passage carrying the number.

Its decisive example, re-verified here against `out/tables/d1_zeta_table.csv`:

| check | result |
|---|---|
| `PMC12312160` rows citing line `3462e7d827dbcb55` | **8** |
| ionic strengths among them | **1 mM and 100 mM** |
| widest case, `PMC10450312`, one citation | **0.1 / 1 / 10 / 100 mM — a 1000× range** |
| rows corpus-wide where one citation spans several ionic strengths | **44** |

A 100× ionic-strength difference is the difference between a Debye length of about 9.6 nm and
0.96 nm. The quote separated those experiments. The paragraph does not. Ionic strength is the
worst condition to lose, because it is the one that decides whether the paper's own
mobility-to-zeta conversion was in a valid κa regime at all.

The scientist's second mechanism: `_number_in` is a **unit-blind digit search**, so widening the
haystack turns it into noise. Distinct numeric tokens per haystack rise from a median of 8 in
the quote to 17 in the cited line. A ball mill's "diameter of 10 mm" verifies "10 mM KNO₃". pH,
temperature and ionic strength are small bare integers and collide readily; a zeta value does
not, which is precisely why the value survives this change and the conditions do not.

### Where they converge

Both reviewers, from opposite directions, land on the same split and the same default:

- **Move the value and quote-existence checks to the cited line.** Safe. Exactly **1 row of
  1 384** changes.
- **Leave condition scope on the quote.** The sentence stays the unit within which a condition
  is established, and the 34/123 deltas go to zero.

Both also flag that the card's third `FAILS IF` is unfalsifiable as written, because it never
says whether "the row's own evidence" denotes the quote or the cited line.

### Blocked on

Whether a condition's scope is the **sentence the worker quoted** or the **paragraph the row
cites**. The dataset currently answers "the sentence" for 794 rows carrying a scoped condition.
The step changes that answer to "the paragraph" without asking, and `1 890` is the denominator
under every percentage published in `out/release/DATASET_CARD.md`.

Nothing was built. No denominator moved.
