# MNP-KB v0 Atlas: the results page

One HTML page that draws the dataset's headline results. It is built in two steps.

- `build_data.py` reads every input from one commit with `git show <ref>:<path>`, never from the working tree, and computes the numbers with the repo's own code (`resample`, `comparability`, `harmonise`, `scoring`, `release`). It then checks 105 of them against `out/review/REVIEW.md` at the same commit, writes the result into the data's `checks` list, and exits 1 if any disagree or if REVIEW.md no longer has the shape the checks expect.
- Where the particles came from (section 3) is read from `out/tables/sample_origin_stats.json`, the counts after the second reading (by a Claude agent, not a person) that `report origin` writes. At a ref without that file the data has no `origin` key and the page hides the section, which is how 4a3087c still rebuilds its reference exactly. Where REVIEW.md at the ref carries claim C11, 20 more checks hold the origin numbers against it; where it does not yet (d4be112, which committed the table before the guide described it) the page shows the section and says it is not cross-checked.
- The scope box under the lede carries the block REVIEW.md, the dataset card and the demo open with, rendered by the same function (`mnp.report.scope`) from the ref's tables. It is built only where the ref has the origin table, so at 4a3087c the data has no `scope` key and the box stays hidden. Where REVIEW.md at the ref opens with the block, one more check holds the two word for word; where it does not yet, the box says it is not cross-checked.
- `build_page.py` inlines `data.json` into `template.html` and writes `mnp-results.html`. The JSON is escaped so it cannot close its `<script>` element.

```
unset VIRTUAL_ENV
uv run python tool/viz/build_data.py [--ref HEAD] [--out tool/viz/data.json]
uv run python tool/viz/build_page.py
```

`data.json` and `mnp-results.html` are build outputs.

## The acceptance fixture

`reference_4a3087c.json` is the data the original, lost `build_data.py` wrote at commit 4a3087c, recovered from the published page. `test_reference.py` rebuilds it with `--ref 4a3087c` and requires the same keys, list order, value types and strings, with floats equal to 1e-9 relative:

```
uv run pytest tool/viz/test_reference.py
```

The fixture records `"ref": "HEAD"` because HEAD was 4a3087c when it was built. The test allows that one field to differ.
