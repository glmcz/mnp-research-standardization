"""One reading packet per candidate paper: its rows with no ionic strength, how the main text
described each row's liquid, and every SI statement the scan found near a zeta mention.

Candidates are papers with at least one row without an ionic strength and at least one scan hit:
a strict statement anywhere in the SI, or a broad-net window near a zeta mention.

Usage: python -I packets.py <d1_zeta_table.csv> <scan_out_dir> <si_text_dir> <packet_dir>
"""

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROW_FIELDS = [
    "row_id",
    "particle_name",
    "material",
    "size_nominal_nm",
    "value_text",
    "medium_text",
    "medium_class",
    "pH_text",
    "evidence_location",
]


def main() -> None:
    table, scan_dir, text_dir, packet_dir = map(Path, sys.argv[1:5])
    rows = defaultdict(list)
    with table.open() as fh:
        for r in csv.DictReader(fh):
            rows[r["pmcid"]].append(r)
    cands = defaultdict(list)
    for line in (scan_dir / "si_candidates.jsonl").read_text().splitlines():
        c = json.loads(line)
        cands[c["pmcid"]].append(c)
    packet_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for pmcid, cs in sorted(cands.items()):
        open_rows = [r for r in rows[pmcid] if r["ionic_strength_reported"] != "True"]
        if not open_rows:
            continue
        out = [
            f"# {pmcid}",
            "",
            f"SI text files: {text_dir.resolve() / pmcid}",
            "",
            "## Rows with no ionic strength from the main text",
            "",
        ]
        for r in open_rows:
            out.append("- " + " | ".join(f"{k}={r[k]}" for k in ROW_FIELDS if r[k]))
            out.append(f"  main-text quote: {r['evidence_quote'][:400]}")
        out += ["", "## What the scan found in the SI", ""]
        seen = set()
        for c in cs:
            key = (c["file"], c["statement"] or c["snippet"])
            if key in seen:
                continue
            seen.add(key)
            tags = [c["kind"], "near zeta" if c["near_zeta"] else "not near zeta"]
            if c["buffer_named"]:
                tags.append("buffer named")
            out.append(f"### {c['file']} ({', '.join(tags)})")
            if c["statement"]:
                out.append(f"statement: {c['statement']}")
            out.append(f"context: {c['snippet']}")
            out.append("")
        (packet_dir / f"{pmcid}.md").write_text("\n".join(out))
        made.append(pmcid)
    (packet_dir / "papers.txt").write_text("\n".join(made) + "\n")
    print(f"packets {len(made)}")


if __name__ == "__main__":
    main()
