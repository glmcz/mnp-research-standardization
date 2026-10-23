# The hybrid agent, and the experiment against naive Claude

A model picks an operation and phrases the answer. Code checks the plan, computes over the full
data, guards (allow, caveat or refuse, with a reason from a fixed list), and rejects any number
the composer did not get from the result. The experiment runs the same questions through:

- N0: closed-book Claude;
- N2: Claude with the data a person would paste;
- H: the hybrid;
- Hg: the hybrid without the guard;
- Hng: the hybrid without the grounding check.

Pre-registration: `docs/PREREG_2026-10.md`, P8–P10.

```
unset VIRTUAL_ENV
uv run --with openpyxl python tool/hybrid/questions.py                    # queries/hybrid_questions.jsonl
uv run --with openpyxl python tool/hybrid/run.py run --arm H --rep 1      # then N2, N0, Hg, Hng
uv run --with openpyxl python tool/hybrid/run.py score                    # out/tables/hybrid_results.json
uv run --with openpyxl python -m pytest -q -p no:cacheprovider tool/hybrid
```

- `ops.py` holds the operation registry, with typed argument domains (`Literal`), the executor and
  the guard.
- `questions.py` holds 19 questions. Each truth is computed with plain pandas over the source
  files, not through `ops.py`, and a test holds every reference plan to that truth.
- `agents.py` holds the one answer contract for all arms, the pasted-data packets, the planner
  and composer prompts, and the grounding check. A DOI's digits never ground a number.
- `run.py` writes one file per answer under `data/interim/runs/hy-<arm>-r<rep>/`. A re-run
  resumes. Rep 0 is the pilot and is never scored. Hg and Hng reuse H's plan and result.
- All calls go through the pinned local CLI (`claude -p`, claude-sonnet-5), with the
  `grid.reader_command` flags and a neutral system prompt shared by every arm.
