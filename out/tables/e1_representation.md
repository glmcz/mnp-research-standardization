# E1 — representation bake-off

50 gold papers, `cl100k_base`, one shared block set (`mnp.corpus.represent`).

Every markdown and JSON arm is built from the same lines of the same parse, so only the serialisation differs. `md_plain` reproducing `text_current` to the token is the check that the block set is the parser's own and not a second copy of it.

| representation | tok/paper | median | × md_plain | addressable to | E1 published | Δ |
|---|---|---|---|---|---|---|
| `xml_raw` | 41,127 | 36,766 | 7.06 | xpath | 41,127 | +0.0% |
| `text_current` | 5,826 | 6,010 | 1.00 | nothing | 5,273 | +10.5% |
| `md_plain` | 5,826 | 6,010 | 1.00 | nothing | 5,273 | +10.5% |
| `md_anchored` | 5,869 | 6,066 | 1.01 | section | 5,309 | +10.5% |
| `md_linenum` | 5,923 | 6,124 | 1.02 | line | 5,373 | +10.2% |
| `md_spanids` | 6,562 | 6,719 | 1.13 | sentence | 5,908 | +11.1% |
| `ir_json` | 10,294 | 10,148 | 1.77 | sentence | 7,626 | +35.0% |

## What the tokens are spent on

Block kinds of `md_plain`, header and body together. The keyword windows are the block a first pass of E1 omitted, which is how `md_anchored` came to be reported at 0.72× — cheaper than the document it decorates.

| block kind | tok/paper | share |
|---|---|---|
| methods | 2,063 | 35.4% |
| section | 384 | 6.6% |
| figure_caption | 803 | 13.8% |
| abstract | 336 | 5.8% |
| table | 751 | 12.9% |
| context | 1,488 | 25.5% |
| **all blocks** | **5,825** | |
