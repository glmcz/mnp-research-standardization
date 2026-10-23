"""Open a candidate's files and decide from what is in them, not from what its record claims.

A dataset is `usable` for the survey table when one of its tables has coordinates, a date or
year, and a concentration column, in at least MIN_ROWS rows. `partial` has a concentration and
either a place or a date; anything else is `not_usable`. A dataset that NCEI already cites, or
that names NCEI as its source, is flagged so it is not counted as independent.
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import catalog  # noqa: E402

FILES = ROOT / "data/raw/discover/files"
MIN_ROWS = 20
#: Column roles, matched on lower-cased header text.
ROLES = {
    "lat": r"^lat\b|latitude|^lat_|\blat\s*\(",
    "lon": r"^lon\b|^long\b|longitude|^lon_|\blon\s*\(",
    "date": r"date|year|time|sampling.?period",
    "size": r"size|mesh|µm|\bum\b|\bmm\b|fraction|lower.?limit",
}
#: A concentration column names plastic and either a unit per volume, mass or area, or the
#: word for a measured amount. "O2 sat [mg/l]" has a unit but no plastic; "Microplastic part
#: size [µm]" has plastic but no such unit; both were passed by the first run.
_PLASTIC = r"plastic|\bmp\b|\bmps\b|particle|\bitems?\b|\bpieces?\b|fib(?:re|er)|polymer|litter|#"
_PER = r"#/|/\s*(?:m3|m\*\*3|m\^3|l|kg|g|m2|m\*\*2|km2|km\*\*2|m)\b|per (?:m3|litre|liter|kg|km2)"
_AMOUNT = r"measurement|concentration|\bconc\b|density"


def is_concentration(header: str) -> bool:
    low = header.lower()
    if "abundance" in low:
        return True
    per = re.search(_PER, low)
    if not per and re.search(r"size|µm|\bum\b|diam|length|\bvol\b", low):
        return False  # a particle's size or volume, even when its header says "measurement"
    return bool(re.search(_PLASTIC, low)) and bool(per or re.search(_AMOUNT, low))


def roles(columns) -> dict[str, list[str]]:
    """Which columns could carry each role. Header text only; values are checked by count."""
    out: dict[str, list[str]] = {}
    for col in columns:
        low = str(col).lower().strip()
        for role, pat in ROLES.items():
            if re.search(pat, low):
                out.setdefault(role, []).append(str(col))
        if is_concentration(str(col)):
            out.setdefault("conc", []).append(str(col))
    return out


def _pangaea(text: str) -> pd.DataFrame:
    body = text.split("*/\n", 1)[1] if "*/\n" in text else text
    return pd.read_csv(io.StringIO(body), sep="\t")


def read_table(name: str, raw: bytes) -> list[pd.DataFrame]:
    low = name.lower()
    if low.endswith(".zip"):
        import zipfile

        try:
            z = zipfile.ZipFile(io.BytesIO(raw))
        except zipfile.BadZipFile:
            return []
        frames = []
        for member in z.namelist()[:30]:
            if member.lower().endswith(catalog.TABULAR[:-1]) and not member.startswith("__MACOSX"):
                frames += read_table(member, z.read(member))
        return frames
    try:
        if low.endswith((".xlsx", ".xls")):
            sheets = pd.read_excel(io.BytesIO(raw), sheet_name=None, nrows=20000)
            return [s for s in sheets.values() if s.shape[1] >= 3]
        text = raw.decode("utf-8", errors="replace")
        if low.endswith(".tab") or text.startswith("/* DATA DESCRIPTION"):
            return [_pangaea(text)]
        return [pd.read_csv(io.StringIO(text), sep=None, engine="python", nrows=20000)]
    except Exception:  # noqa: BLE001 - an unreadable file is a finding, recorded by the caller
        return []


def judge(frames: list[pd.DataFrame]) -> dict:
    """The best table's roles and row count, and the verdict they earn."""
    best = {"verdict": "not_usable", "rows": 0, "roles": {}}
    rank = {"not_usable": 0, "partial": 1, "usable": 2}
    for f in frames:
        r = roles(f.columns)
        place = "lat" in r and "lon" in r
        if "conc" in r and place and "date" in r and len(f) >= MIN_ROWS:
            verdict = "usable"
        elif "conc" in r and (place or "date" in r):
            verdict = "partial"
        else:
            verdict = "not_usable"
        if (rank[verdict], len(f)) > (rank[best["verdict"]], best["rows"]):
            best = {"verdict": verdict, "rows": int(len(f)), "roles": r}
    return best


def ncei_overlap(c: dict, ncei_dois: set[str]) -> bool:
    text = f"{c['title']} {c['description']} {c['publisher']}".lower()
    related = {r.split(":", 1)[-1].lower() for r in c.get("related") or []}
    return (
        c["doi"] in ncei_dois
        or bool(related & ncei_dois)
        or "ncei" in text
        or "national centers for environmental information" in text
    )


def verify(c: dict, max_files: int = 3) -> dict:
    host, fs = catalog.files(c["doi"], c.get("url", ""))
    tab = catalog.tabular(fs)
    if not fs:
        return {"host": host, "verdict": "not_verifiable", "files": 0, "rows": 0, "roles": {}}
    if not tab:
        return {"host": host, "verdict": "no_table", "files": len(fs), "rows": 0, "roles": {}}
    frames = []
    for f in tab[:max_files]:
        raw = catalog.get(f["url"])
        d = FILES / re.sub(r"[^\w.-]", "_", c["doi"])
        d.mkdir(parents=True, exist_ok=True)
        (d / re.sub(r"[^\w.-]", "_", f["name"])).write_bytes(raw)
        frames += read_table(f["name"], raw)
    return {"host": host, "files": len(fs), **judge(frames)}
