"""python -m mnp.eval all [--fast]
python -m mnp.eval cell --cell D [--pilot] [--run RUN_ID] [--jobs N]
python -m mnp.eval score --run RUN_ID"""

from __future__ import annotations

import argparse
import sys

from mnp import runs
from mnp.eval import cells, grid, stages


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m mnp.eval")
    p.add_argument("what", choices=["all", "cell", "score"])
    p.add_argument("--fast", action="store_true", help="skip the offline replay of the aggregate")
    p.add_argument("--cell", choices=sorted(grid.BUILDERS), default="D")
    p.add_argument("--pilot", action="store_true", help=f"{grid.PILOT_PER_KIND} questions per kind")
    p.add_argument("--run", help="run id under data/interim/runs/; an existing one resumes")
    p.add_argument("--jobs", type=int, default=4, help="reader calls in flight")
    args = p.parse_args(argv)

    if args.what == "all":
        results = stages.run_all(fast=args.fast)
        path = stages.write(results)
        print(stages.summary(results))
        print(f"-> {path}")
        return 1 if any(r.status == "fail" for r in results) else 0

    if args.what == "score":
        if not args.run:
            p.error("score needs --run")
        report = grid.score_run(runs.run_dir(args.run), grid.all_keys(), cells.load_corpus())
        print(report.text)
        return 0 if report.complete else 1

    suffix = "-pilot" if args.pilot else ""
    run_id = args.run or runs.new_run_id(f"cell{args.cell.lower()}{suffix}")
    runs.start(
        run_id,
        cell=args.cell,
        pilot=args.pilot,
        model=grid.READER_MODEL,
        reader=f"claude -p, tools off, no setting sources ({grid.cli_version()})",
        system_prompt_sha256=grid.sha256(grid.SYSTEM_PROMPT),
    )
    questions = grid.all_questions()
    if args.pilot:
        questions = grid.pilot(questions)
    corpus = cells.load_corpus()
    directory = runs.run_dir(run_id)
    counts = grid.run_cell(args.cell, questions, corpus, directory, jobs=args.jobs)
    report = grid.score_run(directory, grid.all_keys(), corpus)
    runs.finish(run_id, counts)
    print(report.text)
    print(f"-> {directory}")
    return 0 if report.complete else 1


if __name__ == "__main__":
    sys.exit(main())
