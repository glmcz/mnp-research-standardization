"""python -m mnp.eval all [--fast]"""

from __future__ import annotations

import argparse
import sys

from mnp.eval import stages


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m mnp.eval")
    p.add_argument("what", choices=["all"])
    p.add_argument("--fast", action="store_true", help="skip the offline replay of the aggregate")
    args = p.parse_args(argv)
    results = stages.run_all(fast=args.fast)
    path = stages.write(results)
    print(stages.summary(results))
    print(f"-> {path}")
    return 1 if any(r.status == "fail" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
