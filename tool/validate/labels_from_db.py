"""Turn the labelling page's saved labels into the labels.jsonl that `mnp.validate.sign` scores.

The page saves one document per row under `labels/<row_id>`. Export them with the ArtifactData
tool (`list`, collection "labels", `out_dir` = the directory below), then run:

uv run python tool/validate/labels_from_db.py data/interim/validate/sign/labels_db
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from mnp.validate import sign


def main(src: str) -> None:
    files = sorted(Path(src).rglob("*.json"))
    out = []
    for f in files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        body = doc.get("data", doc)  # the export wraps the body in "data"; accept both
        if body.get("cause") in sign.CAUSES:
            out.append({"pmcid": body["pmcid"], "row_id": body["row_id"], "cause": body["cause"],
                        "note": body.get("note", ""), "at": body.get("at", "")})
    path = sign.labels_path()
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out), "utf-8")
    print(f"{len(out)} labels from {len(files)} files -> {path}")


if __name__ == "__main__":
    main(sys.argv[1])
