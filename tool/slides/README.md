# Reading What Isn't There: the conference deck

Twenty-two timed slides for the 20-minute talk, in six acts with the datasets first (survey validation in `tool/survey/`, the dataset search agent in `tool/discover/`, aging pairs in `tool/p2/aging.py`, the hybrid agent in `tool/hybrid/`), and sixteen backup slides for questions, generated as one HTML page. It is the results page's sibling (`tool/viz/`) and is built the same way: data first, read from one commit, then a template filled with it.

- `build_slides.py` first runs `tool/viz/build_data.py`'s `build(ref)`, so its checks against REVIEW.md run at the same ref, and stops if any disagree. It then reads the rest with `git show <ref>:<path>`: the final grid runs (`celld-final-20261003`, `cellb-final-20261003`), the re-read control's `summary.json`, `docs/DECISIONS.md` for the quoted examples, `out/demo/METHOD.md` for the reason each condition matters, and the release `LICENSE`. Every number becomes a value with its raw form, its shown text and its source.
- `template.html` holds the words. A `{{key}}` slot becomes `<span data-k="key">` around the value's text, `{{svg:name}}` becomes a chart the builder draws as inline SVG from the same values (to scale, coloured from the page's tokens), and `{{w:key}}` becomes a bar's width. The deck's data is inlined as JSON through `tool/viz/build_page.py`'s `inline`.
- The build stops when a slide's claim no longer holds: case 14 must still be the only comparable pair across papers, its harmonised intervals must not overlap, the cited-value example must still be gone from the record, `out/review/audit_sample.csv` must hold no verdict, since slide 38 says the human audit has not been done, and the blind labels must not be complete, since slide 32 reports agreement, not accuracy. Every timed card in the script must fit 130 spoken words a minute.

```
unset VIRTUAL_ENV
uv run python tool/slides/build_slides.py [--ref HEAD] [--out tool/slides/slides.html]
uv run pytest -q -p no:cacheprovider tool/slides/test_slides.py
```

`slides.html` is a build output and is not committed. It is the fragment the artifact host wraps; `--standalone` writes a whole document instead (doctype, viewport), to open as a file on a phone or offline. `build_script.py` takes the same flag. Open it in a browser: on a wide screen one slide fills the window. Arrow keys, space, Page Up/Down and a click move between slides, Home and End jump to the ends, `N` shows the speaker notes, `F` asks for fullscreen, and `#s5` in the address opens slide 5. On a phone the slides stack as one column.

## The talk script

`build_script.py` writes `script.html`, the rehearsal companion: what to say on each slide, how long it gets, the clock when you leave it, questions to expect, and a checklist for the day. It builds the deck first and speaks the deck's own values, so every number said aloud is the number on the slide, and it copies each slide's title and message out of the rendered deck. `script_template.html` holds the words. The only numbers typed by hand are the time plan (`PLAN`), about a hundred spoken words a minute, and a test holds its five acts to twenty minutes. Backup slides (`BACKUP`) get a card and no time. The script's digits go through the same scan as the deck's.

```
unset VIRTUAL_ENV
uv run python tool/slides/build_script.py [--ref HEAD] [--out tool/slides/script.html]
```

## The tests

`test_slides.py` reads every source again without the builder, by another route where one exists: REVIEW.md's printed numbers rather than the census module, the runs' own `verdicts.tsv` and `scores.tsv`, DECISIONS.md's wording, the demo case's own sentence, and Henry's function recomputed from the formula REVIEW.md §5.4 prints. A value with no source fails. The rendered page is then scanned: every digit a viewer can see must sit inside a `data-k` element showing that value, or be one of a short list of identifiers (register ids, REVIEW claims and sections, rule and case names, a file path, the slide's own number, a validation rung V0 to V3 or a prediction P1 to P6 looked up in the design and the pre-registration, and the "1:1" and "25 °C" of the Debye note), and each of those is looked up in its source too. Two tests change one value or one source and require the check to name exactly that value.

`shots.py` screenshots chosen slides at desktop size or phone width (`--phone`), to look at before publishing; it needs Google Chrome.

`export.py OUT_DIR` writes `talk_deck.pdf` and `talk_deck.pptx` from the built `slides.html`: each slide a picture of the page as presented (so the text is not editable), the speaker notes in PowerPoint's notes pane and each slide's title as its picture's alt text. Run it with `uv run --with playwright --with pillow --with python-pptx`; it needs Google Chrome too.

`export_text.py OUT_DIR` writes `talk_text.docx`: every slide's title, message, other text, figure labels, speaker notes, and for timed slides the spoken script and the bridge to the next, under a short brief for whoever rewrites it (numbers stay as they are). Run it with `uv run --with beautifulsoup4 --with python-docx`. A rewrite comes back into `template.html` and `script_template.html` by hand, keeping each `{{key}}`.
