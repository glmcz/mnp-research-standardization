# Stage evaluation

Each stage against its own ground truth. A stage with no ground truth reads
**not measured** — never 0.00 and never 1.00, because both are claims nobody checked.

| stage | metric | value | n | gate | status |
|---|---|---|---|---|---|
| parse | span recall | 1.00 | 5 | 1.00 | pass |
| scan | recall of gold values | 0.98 | 85 | — | reported |
| read | row value precision | 0.81 | 101 | — | reported |
| coerce | exact-match accuracy | 1.00 | 18 | 1.00 | pass |
| verify | detection rate | 1.00 | 7 | 1.00 | pass |
| aggregate | artefacts reproduced | — | 0 | 1.00 | not measured |

## What each stage is scored against

- **parse** — JATS to methods text, tables and keyword windows. Ground truth: tests/eval/fixtures/parse_spans.json — sentences a human located by hand.
- **scan** — find every printed zeta/mobility value in an article. Ground truth: values in gold_50.csv, which were read from the papers by hand.
- **read** — a model or agent turns the article into rows. Ground truth: gold_50.csv.
- **coerce** — strings to numbers, under the ratified rules. Ground truth: tests/eval/fixtures/coerce_cases.json.
- **verify** — reject what the article does not support. Ground truth: tests/eval/fixtures/verify_adversarial.json — production defects.
- **aggregate** — verified rows into the published tables. Ground truth: the committed out/ tree.

## Detail

- **scan**: missed PMC10145996:24.13, PMC4958399:-16.7
- **read**: recall 0.80
