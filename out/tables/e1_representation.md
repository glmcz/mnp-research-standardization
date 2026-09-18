# E1 — representation bake-off

50 gold papers, `cl100k_base`, one shared block set (`mnp.corpus.represent`).

Every markdown and JSON arm is built from the same lines of the same parse, so only the serialisation differs. `md_plain` reproducing `text_current` to the token is the check that the block set is the parser's own and not a second copy of it.

| representation | tok/paper | median | × md_plain | addressable to | E1 published | Δ |
|---|---|---|---|---|---|---|
| `xml_raw` | 41,127 | 36,766 | 7.80 | xpath | 41,127 | +0.0% |
| `text_current` | 5,273 | 4,896 | 1.00 | nothing | 5,273 | +0.0% |
| `md_plain` | 5,273 | 4,896 | 1.00 | nothing | 5,273 | +0.0% |
| `md_anchored` | 5,319 | 4,960 | 1.01 | section | 5,309 | +0.2% |
| `md_linenum` | 5,360 | 4,964 | 1.02 | line | 5,373 | -0.2% |
| `md_spanids` | 5,934 | 5,543 | 1.13 | sentence | 5,908 | +0.4% |
| `ir_json` | 9,384 | 8,800 | 1.78 | sentence | 7,626 | +23.0% |

## What the tokens are spent on

Block kinds of `md_plain`, header and body together. The keyword windows are the block a first pass of E1 omitted, which is how `md_anchored` came to be reported at 0.72× — cheaper than the document it decorates.

| block kind | tok/paper | share |
|---|---|---|
| methods | 1,238 | 23.5% |
| section | 476 | 9.0% |
| figure_caption | 803 | 15.2% |
| abstract | 336 | 6.4% |
| table | 751 | 14.2% |
| context | 1,667 | 31.6% |
| **all blocks** | **5,271** | |
