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
| — | none yet | — | — | — |
