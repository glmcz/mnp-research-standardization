"""A leased work queue, so many workers can share a corpus without colliding.

The first corpus run assigned chunks from snapshots taken while other chunks were still in
flight. Two workers were handed the same papers (wasted effort, and collisions on shared
scratch files), and when a rate limit killed ten workers their work was neither finished nor
returned. Both are scheduling faults, and both disappear if claiming is atomic and leases
expire.

PostgreSQL does the hard part: `SELECT … FOR UPDATE SKIP LOCKED` hands each worker a disjoint
set in one statement, with no application-level locking.

The queue is a *scheduler*, never a result. `extractions.jsonl` remains the scientific
record; losing this database costs a re-run, not a finding.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from mnp import config

try:  # psycopg is optional until the queue is used
    import psycopg
except ImportError:  # pragma: no cover - exercised by environments without the driver
    psycopg = None

STATES = ("pending", "leased", "done", "failed", "skipped")
MAX_ATTEMPTS = 3
DEFAULT_LEASE_SECONDS = 1800


def dsn() -> str | None:
    """Where the queue lives. One variable of its own, and nothing else.

    There is deliberately no fall-back to ``DATABASE_URL``: that variable belongs to the Rust
    service, and reading it pointed the queue's tests at the live application database.
    """
    return config.getenv("MNP_DB_URL")


def available() -> bool:
    """Is a server actually reachable? Used to skip integration tests, never to hide errors."""
    if psycopg is None or not dsn():
        return False
    try:
        with psycopg.connect(dsn(), connect_timeout=3) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


def _now() -> datetime:
    return datetime.now(UTC)


class Queue:
    """Work items keyed by PMCID, in one schema so tests cannot touch real runs."""

    def __init__(self, schema: str = "mnp", url: str | None = None):
        if psycopg is None:
            raise RuntimeError("psycopg is not installed; `uv sync` first")
        self.url = url or dsn()
        if not self.url:
            raise RuntimeError("set MNP_DB_URL to use the queue (see .env.example)")
        self.schema = schema
        self._conn: psycopg.Connection | None = None

    # -- lifecycle ----------------------------------------------------------------
    def __enter__(self) -> Queue:
        self._conn = psycopg.connect(self.url, autocommit=True)
        self._conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{self.schema}"')
        self._create()
        return self

    def __exit__(self, *exc) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> psycopg.Connection:
        if self._conn is None:
            raise RuntimeError("use the Queue as a context manager")
        return self._conn

    @property
    def table(self) -> str:
        return f'"{self.schema}".work'

    def _create(self) -> None:
        self.conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.table} (
                pmcid       text PRIMARY KEY,
                state       text NOT NULL DEFAULT 'pending',
                worker      text,
                lease_until timestamptz,
                attempts    integer NOT NULL DEFAULT 0,
                run_id      text,
                brief_sha   text,
                note        text,
                updated_at  timestamptz NOT NULL DEFAULT now()
            )
        """)

    def reset(self) -> None:
        self.conn.execute(f"TRUNCATE {self.table}")

    def drop(self) -> None:
        self.conn.execute(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE')

    # -- operations ---------------------------------------------------------------
    def init(self, pmcids, run_id: str, brief_sha: str) -> int:
        """Add work. Papers already present keep their state, so this is safe to repeat."""
        rows = [(p, run_id, brief_sha) for p in pmcids]
        with self.conn.cursor() as cur:
            cur.executemany(
                f"""INSERT INTO {self.table} (pmcid, run_id, brief_sha)
                    VALUES (%s, %s, %s) ON CONFLICT (pmcid) DO NOTHING
                 RETURNING pmcid""",
                rows,
                returning=True,
            )
            added = 0
            while True:
                if cur.fetchone() is not None:
                    added += 1
                if not cur.nextset():
                    break
            return added

    def claim(self, worker: str, n: int, lease_seconds: int = DEFAULT_LEASE_SECONDS) -> list[str]:
        """Take up to n pending papers, atomically.

        Ordered by pmcid so that a queue rebuilt from the same list hands out the same work
        in the same order — assignment is reproducible even though the queue is not in git.
        """
        until = _now() + timedelta(seconds=lease_seconds)
        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                WITH picked AS (
                    SELECT pmcid FROM {self.table}
                     WHERE state = 'pending' AND attempts < %s
                     ORDER BY pmcid
                     FOR UPDATE SKIP LOCKED
                     LIMIT %s
                )
                UPDATE {self.table} w
                   SET state = 'leased', worker = %s, lease_until = %s, updated_at = now()
                  FROM picked
                 WHERE w.pmcid = picked.pmcid
             RETURNING w.pmcid
                """,
                (MAX_ATTEMPTS, n, worker, until),
            )
            return sorted(r[0] for r in cur.fetchall())

    def done(self, worker: str, pmcids, brief_sha: str | None = None) -> int:
        """Close papers this worker holds. Papers it does not hold are left alone."""
        with self.conn.cursor() as cur:
            cur.execute(
                f"""UPDATE {self.table}
                       SET state = 'done', worker = %s, lease_until = NULL,
                           brief_sha = COALESCE(%s, brief_sha), updated_at = now()
                     WHERE pmcid = ANY(%s) AND worker = %s AND state = 'leased'
                 RETURNING pmcid""",
                (worker, brief_sha, list(pmcids), worker),
            )
            return len(cur.fetchall())

    def fail(self, pmcid: str, note: str) -> None:
        self.conn.execute(
            f"""UPDATE {self.table}
                   SET state = 'failed', note = %s, lease_until = NULL, updated_at = now()
                 WHERE pmcid = %s""",
            (note, pmcid),
        )

    def reap(self) -> int:
        """Return expired leases to the queue; retire work that has failed too often."""
        with self.conn.cursor() as cur:
            cur.execute(
                f"""UPDATE {self.table}
                       SET state = CASE WHEN attempts + 1 >= %s THEN 'failed' ELSE 'pending' END,
                           attempts = attempts + 1,
                           worker = NULL, lease_until = NULL,
                           note = CASE WHEN attempts + 1 >= %s
                                       THEN 'lease expired ' || (attempts + 1) || ' times'
                                       ELSE note END,
                           updated_at = now()
                     WHERE state = 'leased' AND lease_until < now()
                 RETURNING pmcid""",
                (MAX_ATTEMPTS, MAX_ATTEMPTS),
            )
            return len(cur.fetchall())

    # -- inspection ---------------------------------------------------------------
    def status(self) -> dict[str, int]:
        """Counts by state, including the zeros — a progress report with holes in it
        invites the reader to guess, and guessing is what this queue exists to stop."""
        counts = dict.fromkeys(STATES, 0)
        with self.conn.cursor() as cur:
            cur.execute(f"SELECT state, count(*) FROM {self.table} GROUP BY state")
            for state, n in cur.fetchall():
                counts[state] = n
        return counts

    def attempts(self, pmcid: str) -> int:
        with self.conn.cursor() as cur:
            cur.execute(f"SELECT attempts FROM {self.table} WHERE pmcid = %s", (pmcid,))
            row = cur.fetchone()
            return row[0] if row else 0

    def brief_of(self, pmcid: str) -> str | None:
        with self.conn.cursor() as cur:
            cur.execute(f"SELECT brief_sha FROM {self.table} WHERE pmcid = %s", (pmcid,))
            row = cur.fetchone()
            return row[0] if row else None

    def holders(self) -> dict[str, list[str]]:
        """Who is holding what, for a progress report that does not trust worker reports."""
        with self.conn.cursor() as cur:
            cur.execute(
                f"SELECT worker, pmcid FROM {self.table} WHERE state = 'leased' ORDER BY pmcid"
            )
            out: dict[str, list[str]] = {}
            for worker, pmcid in cur.fetchall():
                out.setdefault(worker, []).append(pmcid)
            return out


@contextmanager
def open_queue(schema: str = "mnp"):
    with Queue(schema=schema) as q:
        yield q
