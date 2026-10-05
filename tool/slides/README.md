# Reading What Isn't There: the conference deck

Sixteen slides for the 20-minute talk, generated as one HTML page. It is the results page's sibling (`tool/viz/`) and is built the same way: data first, read from one commit, then a template filled with it.

- `build_slides.py` first runs `tool/viz/build_data.py`'s `build(ref)`, so the 149 checks against REVIEW.md run at the same ref, and stops if any disagree. It then reads the rest with `git show <ref>:<path>`: the final grid runs (`celld-final-20261003`, `cellb-final-20261003`), the re-read control's `summary.json`, `docs/DECISIONS.md` for the quoted examples, `out/demo/METHOD.md` for the reason each condition matters, and the release `LICENSE`. Every number becomes a value with its raw form, its shown text and its source.
- `template.html` holds the words. A `{{key}}` slot becomes `<span data-k="key">` around the value's text, `{{svg:name}}` becomes a chart the builder draws as inline SVG from the same values (to scale, coloured from the page's tokens), and `{{w:key}}` becomes a bar's width. The deck's data is inlined as JSON through `tool/viz/build_page.py`'s `inline`.
- The build stops when a slide's claim no longer holds: case 14 must still be the only comparable pair across papers, its harmonised intervals must not overlap, the cited-value example must still be gone from the record, and `out/review/audit_sample.csv` must hold no verdict, since slide 14 says the human audit has not been done.

```
unset VIRTUAL_ENV
uv run python tool/slides/build_slides.py [--ref HEAD] [--out tool/slides/slides.html]
uv run pytest -q -p no:cacheprovider tool/slides/test_slides.py
```

`slides.html` is a build output and is not committed. Open it in a browser: on a wide screen one slide fills the window. Arrow keys, space, Page Up/Down and a click move between slides, Home and End jump to the ends, `N` shows the speaker notes, `F` asks for fullscreen, and `#s5` in the address opens slide 5. On a phone the slides stack as one column.

## The tests

`test_slides.py` reads every source again without the builder, by another route where one exists: REVIEW.md's printed numbers rather than the census module, the runs' own `verdicts.tsv` and `scores.tsv`, DECISIONS.md's wording, the demo case's own sentence, and Henry's function recomputed from the formula REVIEW.md §5.4 prints. A value with no source fails. The rendered page is then scanned: every digit a viewer can see must sit inside a `data-k` element showing that value, or be one of a short list of identifiers (register ids, REVIEW claims and sections, rule and case names, a file path, the slide's own number, and the "1:1" and "25 °C" of the Debye note), and each of those is looked up in its source too. Two tests change one value or one source and require the check to name exactly that value.
