"""Ask the demo's reader questions in cells D and B, into the runs `report demo` reads.

    uv run python tool/run_demo_reader.py --suffix 20261003 [--jobs 4] [--cell D B]

Every case's questions (`mnp.demo.questions.questions_for`) go through `grid.run_cell`, the
same isolated, model-pinned reader `eval cell` uses, into
`data/interim/runs/demo-cell{d,b}-<suffix>` with the same manifest, then are scored. A run that
exists resumes: an answered question is never asked again. `mnp.demo.render.CELL_D_RUN` and
`CELL_B_RUN` name the runs the demo shows.

The first demo runs (2026-09-28) were asked from a script that lived in a session scratchpad and
was lost; this one lives in the repo so the next re-ask is the same procedure.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

import pandas as pd

from mnp import config, runs
from mnp.demo import cases, questions
from mnp.eval import cells, grid
from mnp.eval.query_sets import AnswerKey, Question


def demo_questions(table: pd.DataFrame) -> tuple[list[Question], list[AnswerKey]]:
    """Every case's questions and keys, in case order."""
    qs: list[Question] = []
    keys: list[AnswerKey] = []
    for case in cases.CASES:
        for q, k in questions.questions_for(case, table):
            qs.append(q)
            keys.append(k)
    return qs, keys


def ask(
    cell: str, run_id: str, table: pd.DataFrame, corpus: cells.Corpus, jobs: int, reader=grid.read
) -> grid.RunScore:
    qs, keys = demo_questions(table)
    runs.start(
        run_id,
        cell=cell,
        task=f"demo reader questions, {len(cases.CASES)} cases",
        model=grid.READER_MODEL,
        reader=f"claude -p, tools off, no setting sources ({grid.cli_version()})",
        system_prompt_sha256=grid.sha256(grid.SYSTEM_PROMPT),
    )
    directory = runs.run_dir(run_id)
    counts = grid.run_cell(cell, qs, corpus, directory, reader=reader, jobs=jobs)
    report = grid.score_run(directory, keys, corpus)
    runs.finish(run_id, counts)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tool/run_demo_reader.py")
    p.add_argument("--suffix", required=True, help="run ids are demo-cell{d,b}-<suffix>")
    p.add_argument("--cell", nargs="+", default=["D", "B"], choices=sorted(grid.BUILDERS))
    p.add_argument("--jobs", type=int, default=4)
    args = p.parse_args(argv)
    table = pd.read_csv(config.OUT / "tables" / "d1_zeta_table.csv")
    corpus = cells.load_corpus()
    ok = True
    for cell in args.cell:
        report = ask(cell, f"demo-cell{cell.lower()}-{args.suffix}", table, corpus, args.jobs)
        print(report.text)
        ok = ok and report.complete
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
