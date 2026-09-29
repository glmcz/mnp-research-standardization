# MNP-KB v0 Atlas: the results page

One HTML page that draws the dataset's headline results. It is built in two steps.

- `build_data.py` reads every input from one commit with `git show <ref>:<path>`, never from the working tree, and computes the numbers with the repo's own code (`resample`, `comparability`, `harmonise`, `scoring`, `release`). It then checks 105 of them against `out/review/REVIEW.md` at the same commit, writes the result into the data's `checks` list, and exits 1 if any disagree or if REVIEW.md no longer has the shape the checks expect.
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
