"""The blind labelling page for Q2: 30 rows drawn at random from the 69 candidates.

Martin labels each row's cause from the same lines the readers saw, without seeing any reader's
or judge's answer. The page saves each label to its own `db` collection, `labels/<row_id>`.
`labels_from_db.py` turns an export of that collection into the labels.jsonl that
`python -m mnp.validate.sign score` reads.

uv run python tool/validate/build_labels.py   # writes tool/validate/labels.html (publish it)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "tool" / "viz"))
from build_page import inline  # noqa: E402

from mnp.extract import origin  # noqa: E402
from mnp.validate import sign  # noqa: E402

SEED = 20261019
N = 30
DEFINITIONS = {
    "ph": "The lines give a pH at which this group does not carry its usual charge.",
    "corona": "Proteins, serum, a culture medium, humic or organic matter, or another coating "
              "adsorbed in the measured liquid.",
    "ions": "Salts or buffer ions in the measured liquid that the lines connect to the charge.",
    "label_error": "The lines show the particle is not the one with this surface group.",
    "extraction_error": "The paper prints this value with the other sign, or it belongs to "
                        "another particle or condition.",
    "other_stated": "The paper itself states another reason.",
    "unexplained": "The lines do not give a reason.",
}


def sample(cands) -> list[str]:
    """A simple random sample with a fixed seed, so estimates carry to all candidates."""
    ids = sorted(cands.row_id)
    return sorted(np.random.default_rng(SEED).choice(ids, size=N, replace=False).tolist())


def main() -> None:
    cands = sign.candidates()
    picked = set(sample(cands))
    papers, cases = {}, []
    for pmcid, rows in cands.groupby("pmcid"):
        if not picked & set(rows.row_id):
            continue
        cited = {i for ids in rows.evidence_line_ids.dropna() for i in str(ids).split(";") if i}
        ev = sign.select(origin.load_doc(pmcid), cited)
        papers[pmcid] = origin.render(ev)
        for r in rows.to_dict("records"):
            if r["row_id"] in picked:
                cases.append({
                    "row_id": r["row_id"], "pmcid": pmcid, "particle": r["particle_name"],
                    "surface": r["surface"], "zeta_mV": r["zeta_mV"],
                    "liquid": r["medium_text"] if isinstance(r["medium_text"], str) else None,
                    "pH": None if r["pH"] != r["pH"] else r["pH"],
                })
    data = {"cases": cases, "papers": papers, "causes": list(sign.CAUSES),
            "definitions": DEFINITIONS, "seed": SEED, "of": len(cands)}
    out = HERE / "labels.html"
    out.write_text(inline((HERE / "labels_template.html").read_text(encoding="utf-8"), data),
                   encoding="utf-8")
    print(f"wrote {out}: {len(cases)} cases from {len(papers)} papers")


if __name__ == "__main__":
    main()
