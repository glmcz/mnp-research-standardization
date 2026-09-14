"""``python -m mnp.ek qa`` — recompute the printed-curve bank and gate any digitised data."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mnp import config
from mnp.ek import qa


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m mnp.ek")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("qa", help="recompute printed fits, overlay digitised CSVs, write tables")
    p.add_argument("--bank", type=Path, default=qa.BANK_PATH)
    p.add_argument("--digitised-dir", type=Path, default=qa.DIGITISED_DIR)
    p.add_argument("--tables", type=Path, default=config.OUT_TABLES)
    p.add_argument("--figures", type=Path, default=config.OUT_FIGURES)
    args = parser.parse_args(argv)

    config.ensure_dirs()
    rows = qa.run_qa(args.bank, args.digitised_dir, args.tables, args.figures)
    for row in rows:
        detail = row["missing"] if row["status"] == "incomplete" else row["validity_note"]
        residual = (
            "" if row["residual_max_frac"] is None else f" residual {row['residual_max_frac']:.3%}"
        )
        print(f"{row['status']:22s} {row['key']:60s}{residual}  {detail}")
    complete = sum(r["status"] != "incomplete" for r in rows)
    print(f"{len(rows)} rows, {complete} recomputed, {len(rows) - complete} incomplete")
    print(f"tables: {args.tables}/d4_params.csv, d4_qa_residuals.csv")
    print(f"figure: {args.figures}/d4_qa_overlay.png")
    ok = qa.all_gates_pass(rows)
    print("gates:", "pass" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
