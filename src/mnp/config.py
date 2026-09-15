"""Paths, environment loading and the outbound User-Agent.

This service reads its own ``.env`` and nothing else. The Rust service's
``.env`` next door holds the same keys, and sharing it kept exactly one copy on
this machine — but it also meant an ambient ``DATABASE_URL`` reached code here
that had no business seeing it. It is now opt-in: set ``MNP_ALLOW_SIBLING_ENV=1``
to layer it underneath ours, or ``MNP_ENV_FILE`` to replace the search entirely.
Nothing here ever writes to either file.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

from mnp import __version__

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
DATA_RAW = DATA / "raw"
DATA_INTERIM = DATA / "interim"
DATA_PROCESSED = DATA / "processed"
OUT = ROOT / "out"
QUERIES = ROOT / "queries"

EPMC_SEARCH_DIR = DATA_RAW / "epmc" / "search"
EPMC_XML_DIR = DATA_RAW / "epmc" / "xml"
LLM_CACHE = DATA_INTERIM / "llm_cache"
ANNOTATION = DATA_INTERIM / "annotation"
OUT_TABLES = OUT / "tables"
OUT_FIGURES = OUT / "figures"
OUT_SCHEMA = OUT / "schema"


class MissingConfig(RuntimeError):
    """A required environment variable is unset or blank."""


SIBLING_ENV = ROOT.parent / "nanoSolve-backend" / ".env"


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def env_files() -> tuple[Path, ...]:
    """Every .env to merge, highest precedence first.

    ``MNP_ENV_FILE`` replaces the search rather than extending it, so a test can guarantee
    that no file on this machine is read.
    """
    override = os.environ.get("MNP_ENV_FILE")
    if override:
        return (Path(override),)
    if _truthy(os.environ.get("MNP_ALLOW_SIBLING_ENV")):
        return (ROOT / ".env", SIBLING_ENV)
    return (ROOT / ".env",)


def load_env() -> None:
    """Merge the .env files into os.environ. The shell wins; then the first file that has it."""
    for path in env_files():
        if not path.is_file():
            continue
        for key, value in dotenv_values(path).items():
            if value is not None and key not in os.environ:
                os.environ[key] = value


def getenv(name: str, default: str | None = None) -> str | None:
    load_env()
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return value


def require(name: str, hint: str = "") -> str:
    value = getenv(name)
    if value is None:
        suffix = f" {hint}" if hint else ""
        where = ", ".join(str(p) for p in env_files())
        raise MissingConfig(f"{name} is unset or blank (looked in {where}).{suffix}")
    return value


def user_agent() -> str:
    """Europe PMC asks for a contact address; refuse to crawl anonymously."""
    email = require(
        "MNP_CONTACT_EMAIL",
        "Europe PMC requires a contact address in the User-Agent; export it before fetching.",
    )
    return f"NanoSolve-mnp-research/{__version__} (mailto:{email})"


def ensure_dirs() -> None:
    for d in (
        EPMC_SEARCH_DIR,
        EPMC_XML_DIR,
        LLM_CACHE,
        ANNOTATION,
        DATA_PROCESSED / "posteriors",
        OUT_TABLES,
        OUT_FIGURES,
        OUT_SCHEMA,
    ):
        d.mkdir(parents=True, exist_ok=True)
