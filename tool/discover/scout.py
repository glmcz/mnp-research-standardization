"""The scout's finds, checked by code: every file it named is opened, judged, and its claims tested.

The scout (`.claude/agents/mnp-dataset-scout.md`) is a Claude agent run as a subagent with web
search. It reports what it read in `out/tables/dataset_scout.json`; it decides nothing. Here code
downloads each file it named (cached, like the catalogue run), applies the same rules as
`verify.judge`, and sets each claim the agent made (coordinates, dates, size window, a
concentration) against the columns the file actually has.

    uv run --with openpyxl python tool/discover/scout.py
    # out/tables/dataset_scout_verified.csv
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import catalog  # noqa: E402
import verify  # noqa: E402

SCOUT = ROOT / "out/tables/dataset_scout.json"
OUT = ROOT / "out/tables/dataset_scout_verified.csv"
#: The agent's claim, and the column roles that would bear it out.
CLAIMS = {"coordinates": ("lat", "lon"), "dates": ("date",), "size_window": ("size",)}


def check(c: dict, max_files: int = 3) -> dict:
    frames, opened, errors = [], 0, []
    for f in c["files"][:max_files]:
        try:
            raw = catalog.get(f["url"])
        except Exception as exc:  # noqa: BLE001 - a file that will not download is a finding
            errors.append(f"{type(exc).__name__}: {exc}"[:120])
            continue
        opened += 1
        keep = verify.FILES / re.sub(r"[^\w.-]", "_", c["doi"] or c["name"][:40])
        keep.mkdir(parents=True, exist_ok=True)
        (keep / f"scout_{opened}.{f['format']}").write_bytes(raw)  # gitignored, pinned on ingest
        frames += verify.read_table(f"scout.{f['format']}", raw)
    if frames:
        j = verify.judge(frames)
    else:
        j = {"verdict": "no_table" if opened else "not_verifiable", "rows": 0, "roles": {}}
    row = {
        "name": c["name"][:90],
        "doi": c["doi"],
        "files_named": len(c["files"]),
        "files_opened": opened,
        "verdict": j["verdict"],
        "rows": j["rows"],
        "roles": json.dumps(j["roles"]),
        "error": "; ".join(errors) or None,
    }
    # a claim is about the dataset, so it is tested against every file's columns together
    seen = set().union(*(verify.roles(f.columns) for f in frames)) if frames else set()
    found = {claim: all(k in seen for k in keys) for claim, keys in CLAIMS.items()}
    found["concentration"] = "conc" in seen
    said = {claim: c.get(claim, "unclear") for claim in CLAIMS}
    said["concentration"] = "unclear" if c.get("unit", "unclear").startswith("unclear") else "yes"
    for claim in found:
        row[f"agent_{claim}"] = said[claim]
        row[f"code_{claim}"] = "yes" if found[claim] else "no"
        # a claim is tested only where a file was read and the agent committed to an answer
        tested = said[claim] != "unclear" and bool(frames)
        row[f"agree_{claim}"] = (said[claim] == "yes") == found[claim] if tested else None
    return row


def main() -> None:
    cands = json.loads(SCOUT.read_text())["candidates"]
    rows = pd.DataFrame([check(c) for c in cands])
    rows.to_csv(OUT, index=False)
    agree = rows.filter(like="agree_")
    tested = int(agree.notna().sum().sum())
    print(rows[["name", "verdict", "rows", "files_opened"]].to_string())
    print(f"claims tested {tested}, held {int(agree.eq(True).sum().sum())}")


if __name__ == "__main__":
    main()
