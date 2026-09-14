"""Europe PMC REST client: search with cursorMark paging, full-text JATS fetch.

Polite by construction: a contact address is mandatory (config.user_agent
raises without it), requests are spaced by a token bucket, and 429/5xx get a
short backoff. Everything is persisted so a re-run never re-downloads.
"""

from __future__ import annotations

import csv
import json
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pandas as pd

from mnp import config
from mnp.config import MissingConfig

__all__ = ["EuropePMC", "MissingConfig", "hit_count", "records_to_frame", "without_oa_filter"]

BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
RETRY_STATUSES = {429, 500, 502, 503, 504}


class EuropePMC:
    def __init__(
        self,
        client: httpx.Client,
        search_dir: Path,
        xml_dir: Path,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        rate_per_s: float = 5.0,
        max_retries: int = 3,
    ) -> None:
        self.client = client
        self.search_dir = Path(search_dir)
        self.xml_dir = Path(xml_dir)
        self.sleep = sleep
        self.clock = clock
        self.min_interval = 1.0 / rate_per_s
        self.max_retries = max_retries  # total attempts per request
        self.user_agent = config.user_agent()
        self._last_request_at: float | None = None

    # -- transport -----------------------------------------------------------

    def _throttle(self) -> None:
        if self._last_request_at is not None:
            wait = self.min_interval - (self.clock() - self._last_request_at)
            if wait > 0:
                self.sleep(wait)
        self._last_request_at = self.clock()

    def _get(self, url: str, params: dict | None = None) -> httpx.Response:
        """GET with throttling and backoff on 429/5xx. Returns the last response."""
        response: httpx.Response | None = None
        for attempt in range(self.max_retries):
            self._throttle()
            response = self.client.get(
                url, params=params, headers={"User-Agent": self.user_agent}, timeout=60.0
            )
            if response.status_code not in RETRY_STATUSES:
                return response
            if attempt < self.max_retries - 1:
                self.sleep(2.0**attempt)
        assert response is not None
        return response

    # -- search --------------------------------------------------------------

    def search(self, query: str, page_size: int = 1000) -> list[dict]:
        """All records for a query, persisting every page as page_NNNN.json."""
        self.search_dir.mkdir(parents=True, exist_ok=True)
        records: list[dict] = []
        cursor = "*"
        for page_no in range(10_000):
            response = self._get(
                f"{BASE}/search",
                {
                    "query": query,
                    "format": "json",
                    "resultType": "lite",
                    "pageSize": str(page_size),
                    "cursorMark": cursor,
                },
            )
            response.raise_for_status()
            page = response.json()
            (self.search_dir / f"page_{page_no:04d}.json").write_text(json.dumps(page))
            batch = page.get("resultList", {}).get("result", [])
            records.extend(batch)
            next_cursor = page.get("nextCursorMark")
            if not batch or not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
        with (self.search_dir / "search.jsonl").open("w") as fh:
            for r in records:
                fh.write(json.dumps(r) + "\n")
        return records

    # -- full text -----------------------------------------------------------

    def fetch_full_text(self, pmcid: str) -> Path | None:
        """JATS XML for one PMCID, cached on disk. None (and a log row) on failure."""
        self.xml_dir.mkdir(parents=True, exist_ok=True)
        target = self.xml_dir / f"{pmcid}.xml"
        if target.is_file() and target.stat().st_size > 0:
            return target
        response = self._get(f"{BASE}/{pmcid}/fullTextXML")
        if response.status_code != 200 or not response.content:
            self._log_failure(pmcid, response.status_code)
            return None
        target.write_bytes(response.content)
        return target

    def _log_failure(self, pmcid: str, status: int) -> None:
        log = self.xml_dir / "fetch_log.csv"
        new = not log.exists()
        with log.open("a", newline="") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(["pmcid", "status", "at"])
            w.writerow([pmcid, status, datetime.now(UTC).isoformat(timespec="seconds")])


def hit_count(client: httpx.Client, query: str) -> int:
    response = client.get(
        f"{BASE}/search",
        params={"query": query, "format": "json", "resultType": "lite", "pageSize": "1"},
        headers={"User-Agent": config.user_agent()},
        timeout=60.0,
    )
    response.raise_for_status()
    return int(response.json()["hitCount"])


_OA_FILTER = re.compile(r"\s+AND\s+OPEN_ACCESS:y\b", re.IGNORECASE)


def without_oa_filter(query: str) -> str:
    """The same query without the open-access restriction: the 'all' denominator."""
    return _OA_FILTER.sub("", query, count=1)


def records_to_frame(records: list[dict]) -> pd.DataFrame:
    """Keep records that have full text (a PMCID); drop DOI duplicates, first wins."""
    rows = []
    seen_dois: set[str] = set()
    for r in records:
        pmcid = r.get("pmcid")
        if not pmcid:
            continue
        doi = r.get("doi")
        key = doi.lower().strip() if doi else None
        if key:
            if key in seen_dois:
                continue
            seen_dois.add(key)
        rows.append(
            {
                "pmcid": pmcid,
                "doi": doi,
                "year": r.get("pubYear"),
                "journal": r.get("journalTitle"),
                "is_oa": r.get("isOpenAccess") == "Y",
                "title": r.get("title"),
                "pub_type": r.get("pubType"),
            }
        )
    df = pd.DataFrame(
        rows, columns=["pmcid", "doi", "year", "journal", "is_oa", "title", "pub_type"]
    )
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    return df
