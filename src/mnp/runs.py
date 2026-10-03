"""One directory per orchestrated run: what was asked for, of which code, against which corpus.

The first corpus run produced 845 records that cannot be audited — the brief lived in a
scratchpad and was deleted, the work lists drifted, and nothing recorded which code was
running. None of that was expensive to prevent; it was simply never asked for.

A manifest records what a reader needs to reconstruct the conditions: the commit (and whether
the tree was dirty), the brief hash, the model, the corpus manifest, the counts, and the
*names* of the environment keys that were set. Never their values — a manifest is committed.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from mnp import config

# Recorded by name so a reader can tell a run with a key from one without. Never the value.
WATCHED_ENV = (
    "OPENROUTER_KEY",
    "OPENROUTER_MODEL",
    "OPENROUTER_FALLBACK_MODELS",
    "MNP_MODEL_CHAIN",
    "MNP_DB_URL",
    "MNP_CONTACT_EMAIL",
    "MNP_ENV_FILE",
    "MNP_ALLOW_SIBLING_ENV",
)


def runs_dir() -> Path:
    return config.DATA_INTERIM / "runs"


def run_dir(run_id: str) -> Path:
    return runs_dir() / run_id


def new_run_id(prefix: str = "run") -> str:
    return f"{prefix}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"


def code_commit() -> tuple[str | None, bool]:
    """The commit this ran from, and whether the tree had uncommitted changes."""
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=config.ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=config.ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover - no git here
        return None, False
    return head, bool(status)


def _corpus_manifest_sha256() -> str | None:
    from mnp.corpus import snapshot

    path = config.EPMC_XML_DIR.parent / "manifest.sha256"
    return snapshot.sha256_file(path) if path.is_file() else None


def _env_keys_present() -> list[str]:
    return [key for key in WATCHED_ENV if config.getenv(key)]


def start(run_id: str, **fields) -> Path:
    """Create the run's manifest, or return the existing one. Resuming is not a new run."""
    directory = run_dir(run_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "manifest.json"
    if path.is_file():
        return path
    commit, dirty = code_commit()
    manifest = {
        "run_id": run_id,
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "ended_at": None,
        "code_commit": commit,
        "code_dirty": dirty,
        "corpus_manifest_sha256": _corpus_manifest_sha256(),
        "env_keys_present": _env_keys_present(),
        "counts": {},
        **fields,
    }
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    return path


def load(run_id: str) -> dict:
    return json.loads((run_dir(run_id) / "manifest.json").read_text())


def assign(run_id: str, worker: str, pmcids: list[str]) -> Path:
    """Append one assignment. Append-only: a lost worker's claim stays in the record."""
    path = run_dir(run_id) / "assignments.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "worker": worker,
        "pmcids": list(pmcids),
        "claimed_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    with path.open("a") as fh:
        fh.write(json.dumps(row) + "\n")
    return path


def finish(run_id: str, counts: dict | None = None) -> Path:
    path = run_dir(run_id) / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["ended_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    if counts:
        manifest["counts"] = counts
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    return path
