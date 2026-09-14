"""Which instructions produced a row.

The first corpus run could not answer this. Every one of its 845 records carried the same
`prompt_sha256` — the ingest CLI's system prompt — while the brief that actually decided
what counts as a plastic, whether a range is a value, and whether a cited number belongs to
this study lived in a session scratchpad that was later deleted.

A brief is therefore treated as data: it lives in `docs/briefs/`, it is versioned in git,
and its hash is stored on every record it produced. Editing a brief changes the hash, so a
mid-run rule change becomes visible instead of silent.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from mnp import config

BRIEFS_DIR = config.ROOT / "docs" / "briefs"


class BriefNotFound(FileNotFoundError):
    """A brief was named but is not on disk. Never silently treated as 'no brief'."""


@dataclass(frozen=True)
class BriefRef:
    """A brief, identified by content rather than by where it happens to sit."""

    path: str  # relative to docs/briefs/ when it lives there, else the basename
    sha256: str
    text: str

    @property
    def short(self) -> str:
        return self.sha256[:12]


def load_brief(path: str | Path) -> BriefRef:
    p = Path(path)
    if not p.is_file():
        raise BriefNotFound(f"no brief at {p}")
    raw = p.read_bytes()
    try:
        rel = str(p.resolve().relative_to(BRIEFS_DIR.resolve()))
    except ValueError:
        rel = p.name
    return BriefRef(path=rel, sha256=hashlib.sha256(raw).hexdigest(), text=raw.decode("utf-8"))


def available_briefs() -> list[BriefRef]:
    """Every brief in the repository, so a worker can be pointed at one by name."""
    if not BRIEFS_DIR.is_dir():
        return []
    return [load_brief(p) for p in sorted(BRIEFS_DIR.glob("*.md"))]


def audit(jsonl: str | Path) -> dict:
    """How much of a store can be traced back to its instructions."""
    path = Path(jsonl)
    records = 0
    untraceable: list[str] = []
    briefs: dict[str, int] = {}
    if path.is_file():
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            records += 1
            sha = r.get("brief_sha256")
            if sha:
                briefs[sha] = briefs.get(sha, 0) + 1
            else:
                untraceable.append(r.get("pmcid"))
    return {
        "records": records,
        "untraceable": len(untraceable),
        "untraceable_pmcids": untraceable,
        "briefs": briefs,
        "traceable_fraction": (records - len(untraceable)) / records if records else None,
    }
