"""Claude reads each candidate's catalogue record and says what kind of dataset it is.

The model reads metadata only (title, description, subjects, formats) and answers in a fixed
contract. It does not decide what is ingested: `worth_verifying` is a rule over its answer, and
verify.py then opens the files and decides from what is in them. Answers are cached by the
prompt's hash under data/raw/discover/triage/.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "tool" / "hybrid"))
import agents  # noqa: E402

CACHE = ROOT / "data/raw/discover/triage"
BATCH = 12
SYSTEM = (
    "You classify open research datasets from their catalogue records. Answer only from the "
    "record given, and follow the output contract exactly."
)
KINDS = (
    "field_measurements",  # concentrations measured in the environment by the dataset's authors
    "compilation_of_published",  # values gathered from published studies
    "lab_experiment",
    "model_output",
    "method_or_protocol",
    "other",
)
MATRICES = ("ocean_water", "freshwater", "sediment", "beach", "soil", "air", "biota",
            "drinking_water", "wastewater", "other")  # fmt: skip
CONTRACT = f"""OUTPUT
Exactly one JSON object: {{"items": [one object per record, in the order given]}}. Each object:
{{"doi": "<as given>", "kind": one of {list(KINDS)},
 "matrix": [zero or more of {list(MATRICES)}],
 "coordinates": "yes" | "no" | "unclear", "dates": "yes" | "no" | "unclear",
 "size_window": "yes" | "no" | "unclear", "tabular": "yes" | "no" | "unclear",
 "concentrations": "yes" | "no" | "unclear",
 "why": "<one short sentence>"}}
- concentrations: does the dataset hold counts or masses of plastic per volume, mass or area?
- size_window: does the record state the smallest (and largest) particle size counted?
- tabular: is the data a table (csv, xlsx, tab), as opposed to images, spectra or code?"""


def _record(c: dict) -> str:
    return json.dumps(
        {
            "doi": c["doi"],
            "title": c["title"],
            "publisher": c["publisher"],
            "year": c["year"],
            "subjects": c["subjects"][:8],
            "formats": c["formats"][:6],
            "has_geolocation_metadata": c["has_geolocation"],
            "description": c["description"][:700],
        },
        ensure_ascii=False,
    )


def prompt(batch: list[dict]) -> str:
    records = "\n".join(_record(c) for c in batch)
    return f"RECORDS (one JSON object per line)\n{records}\n\n{CONTRACT}"


def classify(cands: list[dict], ask=agents.ask, jobs: int = 1) -> dict[str, dict]:
    """DOI → the model's reading of its record. Cached; a malformed batch is retried once."""
    from concurrent.futures import ThreadPoolExecutor

    batches = [cands[i : i + BATCH] for i in range(0, len(cands), BATCH)]
    out: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        for part in pool.map(lambda b: _classify_batch(b, ask), batches):
            out |= part
    return out


def _classify_batch(batch: list[dict], ask) -> dict[str, dict]:
    p = prompt(batch)
    path = CACHE / (hashlib.sha256(p.encode()).hexdigest()[:24] + ".json")
    if path.is_file():
        items = json.loads(path.read_text())
    else:
        items = None
        for _ in range(2):
            parsed = agents.parse(ask(p, system=SYSTEM).text) or {}
            items = parsed.get("items")
            if isinstance(items, list) and len(items) == len(batch):
                break
            items = None
        if items is None:
            return {}  # counted as unclassified, never guessed
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(items, ensure_ascii=False))
    return {c["doi"]: item for c, item in zip(batch, items, strict=True) if isinstance(item, dict)}


def worth_verifying(t: dict) -> bool:
    """The rule, not the model, decides which files to open."""
    return (
        t.get("kind") in ("field_measurements", "compilation_of_published")
        and t.get("concentrations") != "no"
        and t.get("tabular") != "no"
        and set(t.get("matrix") or []) - {"biota", "other"} != set()
    )
