"""python -m mnp.rescale fetch-si | parse | run"""

from __future__ import annotations

import argparse

from mnp import config
from mnp.rescale import koelmans2019 as k


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m mnp.rescale")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("fetch-si", help="download the Koelmans 2019 SI zip and extract mmc1.docx")
    sub.add_parser("parse", help="parse Table S1 into data/raw/koelmans2019/table_s1.csv")
    sub.add_parser("run", help="fetch, parse, rescale and write the D3 tables and figure")
    args = parser.parse_args(argv)

    if args.command in ("fetch-si", "run"):
        print(f"SI docx: {k.fetch_si()}")
    if args.command in ("parse", "run"):
        table = k.parse_table_s1(k.RAW_DIR / k.DOCX_NAME)
        print(f"Table S1: {len(table)} rows -> {k.write_table_s1(table)}")
    if args.command == "run":
        from mnp.report import d3

        written = d3.build(
            config.OUT_TABLES,
            config.OUT_FIGURES,
            processed=config.DATA_PROCESSED / "rescaled.parquet",
        )
        for path in written:
            print(path)


if __name__ == "__main__":
    main()
