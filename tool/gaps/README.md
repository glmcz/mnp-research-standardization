# Measurement gaps

How far apart two numbers land, by what was held the same. One table,
`out/tables/gap_ladder.csv`, drawn on deck slide 21.

```
unset VIRTUAL_ENV
uv run --with openpyxl --with pypdf python tool/gaps/scout_check.py   # the scout's quotes, checked
uv run --with openpyxl python tool/gaps/ladder.py                     # out/tables/gap_ladder.csv
uv run --with openpyxl --with pypdf python -m pytest -q -p no:cacheprovider tool/gaps
```

- **This project's gaps** (`ladder.own`). Each is read from a committed output and recomputed a
  second way in `test_gaps.py`:
  - aging inside one paper;
  - case 14 (the same label and five conditions, another batch);
  - virgin polystyrene between papers;
  - amine polystyrene in another liquid;
  - the same tows converted twice;
  - another database;
  - another study;
  - a net or a pump after converting the window;
  - another size window.
- **Published floors** (`ladder.published`). These are interlaboratory comparisons and reference
  materials found by the gap scout (`.claude/agents/mnp-gap-scout.md`), run as a subagent. Its
  report is `out/tables/gap_scout.json`, in two rounds: the second re-quoted four items so their
  numbers sit inside verbatim quotes.
- **`scout_check.py` fetches every page, PDF or HTML.** It keeps an item only if:
  - the quote is on the page (letters and digits in order, so layout cannot break it);
  - the number sits inside the quote, or each laboratory's value is on the page.
  It kept 5 of 10 items (`out/tables/gap_scout_verified.csv`).
- **How spreads become gaps.** Count spreads (reproducibility standard deviations) are drawn as
  the fold between one deviation above and one below, and only below 100 %. A percentage counts
  only after a word that names a spread, so a recovery is never read as one.
- **SRM 1992.** Its ±5 mV is a combined certification uncertainty at k = 2, not a
  between-laboratory spread, as the certificate says.
