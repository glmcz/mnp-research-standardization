# What the three rules do to the corpus

498 papers with a verified measurement, re-verified under the rules ratified
on 2026-09-13 (`docs/DECISIONS_NEEDED.md`). No paper was re-read; this is the
stored extraction scored against the new rules.

| Condition | missing now | missing under the rules | rule |
|---|---|---|---|
| Temperature | 386 / 498 = 77.5% | 411 / 498 = 82.5% | Q2 + Q3 |
| pH | 399 / 498 = 80.1% | 418 / 498 = 83.9% | Q3 |
| Ionic strength | 447 / 498 = 89.8% | ≥ 382 / 498 = 76.7% | Q1, upper bound |

Q1 moves the other way: a printed composition now counts, so the ionic-strength
figure can only fall. The number given is the best case — every paper whose text
holds two or more salt+concentration terms yielding one. Only a re-extraction
settles it.
