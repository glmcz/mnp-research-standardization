"""Paths, environment loading and the outbound User-Agent.

Secrets live in the Rust service's .env (services/nanoSolve-backend/.env) so
there is exactly one copy of the OpenRouter/Groq keys on this machine. Nothing
here writes to that file; MNP_ENV_FILE points somewhere else in tests.
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


def env_file() -> Path:
    """The .env to read. Defaults to the Rust service's, overridable for tests."""
    override = os.environ.get("MNP_ENV_FILE")
    if override:
        return Path(override)
    return ROOT.parent / "nanoSolve-backend" / ".env"


def load_env() -> None:
    """Merge the .env into os.environ without overriding what the shell set."""
    path = env_file()
    if not path.is_file():
        return
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
        raise MissingConfig(f"{name} is unset or blank (looked in {env_file()}).{suffix}")
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
