"""Find candidate datasets in open catalogues, and list a candidate's files from its repository.

DataCite indexes Zenodo, figshare, Dryad, PANGAEA and most university repositories, so one
search there reaches them all. Every response is cached under data/raw/discover/ (gitignored),
keyed by the request, so a rerun reads the same answers and the search is reproducible.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data/raw/discover/http"
UA = "mnp-research dataset search"
DATACITE = "https://api.datacite.org/dois"
#: What the search asks for: a matrix, or a way of counting, with "microplastic".
QUERIES = (
    "microplastic concentration",
    "microplastic abundance",
    "microplastics surface water",
    "microplastics seawater manta",
    "microplastic trawl",
    "microplastics sediment",
    "microplastics beach",
    "microplastics river",
    "microplastics lake",
    "microplastics estuary",
    "microplastics soil",
    "microplastics atmospheric deposition",
    "microplastics drinking water",
    "microlitter monitoring",
    "nanoplastic concentration",
)
TABULAR = (".csv", ".tsv", ".txt", ".tab", ".xlsx", ".xls", ".zip")


@dataclass
class Candidate:
    doi: str
    title: str
    publisher: str
    year: int | None
    description: str
    subjects: list[str]
    licence: str
    formats: list[str]
    sizes: list[str]
    has_geolocation: bool
    related: list[str] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)


def get(url: str, data: bytes | None = None, headers: dict | None = None) -> bytes:
    """GET (or POST) with a cache keyed by the request. A failed request is not cached."""
    key = hashlib.sha256((url + (data or b"").decode("latin-1")).encode()).hexdigest()[:24]
    path = CACHE / key
    if path.is_file():
        return path.read_bytes()
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
            break
        except Exception:  # noqa: BLE001 - a flaky catalogue is retried, then the error stands
            if attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return body


def _candidate(item: dict, query: str) -> Candidate:
    a = item["attributes"]
    desc = " ".join(d.get("description") or "" for d in a.get("descriptions") or [])
    return Candidate(
        doi=a["doi"].lower(),
        title=(a.get("titles") or [{}])[0].get("title", ""),
        publisher=a.get("publisher") or "",
        year=a.get("publicationYear"),
        description=re.sub(r"\s+", " ", desc)[:1500],
        subjects=[s.get("subject", "") for s in a.get("subjects") or []][:12],
        licence="; ".join(r.get("rights", "") for r in a.get("rightsList") or []),
        formats=list(a.get("formats") or [])[:8],
        sizes=list(a.get("sizes") or [])[:4],
        has_geolocation=bool(a.get("geoLocations")),
        related=[
            f"{r.get('relationType')}:{r.get('relatedIdentifier')}"
            for r in a.get("relatedIdentifiers") or []
        ][:12],
        queries=[query],
    )


def search(queries=QUERIES, pages: int = 3, per_page: int = 100) -> list[Candidate]:
    """DataCite datasets for each query, merged by DOI. A dataset found twice keeps both queries."""
    found: dict[str, Candidate] = {}
    for q in queries:
        for page in range(1, pages + 1):
            url = (
                DATACITE
                + "?"
                + urllib.parse.urlencode(
                    {
                        "query": q,
                        "resource-type-id": "dataset",
                        "page[size]": per_page,
                        "page[number]": page,
                    }  # fmt: skip
                )
            )
            body = json.loads(get(url))
            for item in body.get("data") or []:
                c = _candidate(item, q)
                if c.doi in found:
                    found[c.doi].queries.append(q)
                else:
                    found[c.doi] = c
            if page >= (body.get("meta") or {}).get("totalPages", 0):
                break
    return list(found.values())


def about_plastic(c: Candidate) -> bool:
    """The cheap filter before a model reads anything: is the record about micro/nanoplastic?"""
    text = f"{c.title} {c.description} {' '.join(c.subjects)}".lower()
    return bool(
        re.search(r"micro-?plastic|nano-?plastic|microlitter|micro-?litter|plastic debris", text)
    )


# -- files, from the repository that hosts the DOI ---------------------------------------------


def files(doi: str) -> tuple[str, list[dict]]:
    """(host, [{name, size, url}]) for a DOI whose host has a public file API; else (host, [])."""
    if doi.startswith("10.5281/zenodo."):
        rid = doi.rsplit(".", 1)[-1]
        rec = json.loads(get(f"https://zenodo.org/api/records/{rid}"))
        return "zenodo", [
            {"name": f["key"], "size": f.get("size", 0), "url": f["links"]["self"]}
            for f in rec.get("files") or []
        ]
    if doi.startswith("10.6084/m9.figshare."):
        aid = re.search(r"figshare\.(\d+)", doi)
        if aid:
            art = json.loads(get(f"https://api.figshare.com/v2/articles/{aid.group(1)}"))
            return "figshare", [
                {"name": f["name"], "size": f.get("size", 0), "url": f["download_url"]}
                for f in art.get("files") or []
            ]
    if doi.startswith("10.1594/pangaea."):
        pid = doi.rsplit(".", 1)[-1]
        return "pangaea", [
            {
                "name": f"pangaea_{pid}.tab",
                "size": 0,
                "url": f"https://doi.pangaea.de/10.1594/PANGAEA.{pid}?format=textfile",
            }  # fmt: skip
        ]
    if doi.startswith("10.17632/"):
        m = re.match(r"10\.17632/([a-z0-9]+)(?:\.(\d+))?$", doi)
        if m:
            q = f"&version={m.group(2)}" if m.group(2) else ""
            url = f"https://data.mendeley.com/public-api/datasets/{m.group(1)}/files?folder_id=root{q}"
            fs = json.loads(get(url))
            return "mendeley", [
                {
                    "name": f["filename"],
                    "size": f.get("size", 0),
                    "url": (f.get("content_details") or {}).get("download_url", ""),
                }  # fmt: skip
                for f in fs
                if isinstance(f, dict)
            ]
    if doi.startswith("10.5061/dryad."):
        base = "https://datadryad.org"
        ds = json.loads(get(f"{base}/api/v2/datasets/{urllib.parse.quote('doi:' + doi, safe='')}"))
        version = ds["_links"]["stash:version"]["href"]
        listing = json.loads(get(f"{base}{version}/files"))
        return "dryad", [
            {
                "name": f["path"],
                "size": f.get("size", 0),
                "url": base + f["_links"]["stash:download"]["href"],
            }  # fmt: skip
            for f in (listing.get("_embedded") or {}).get("stash:files") or []
        ]
    host = doi.split("/", 1)[0]
    return host, []


def tabular(fs: list[dict], max_mb: float = 40) -> list[dict]:
    return [
        f for f in fs
        if f["name"].lower().endswith(TABULAR) and (f["size"] or 0) <= max_mb * 1e6
    ]  # fmt: skip


def dedupe(cands: list[Candidate]) -> list[Candidate]:
    """One record per title and publisher: repositories list every version under its own DOI.

    The kept record is the newest, and it inherits every query that found any of its versions.
    """
    best: dict[tuple[str, str], Candidate] = {}
    for c in cands:
        key = (re.sub(r"\s+", " ", c.title.lower()).strip(), c.publisher.lower())
        if key not in best or (c.year or 0) > (best[key].year or 0):
            if key in best:
                c.queries = sorted(set(c.queries) | set(best[key].queries))
            best[key] = c
        else:
            best[key].queries = sorted(set(best[key].queries) | set(c.queries))
    return list(best.values())


def to_dict(c: Candidate) -> dict:
    return asdict(c)
