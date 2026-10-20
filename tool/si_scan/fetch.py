"""Download the supplementary files of every paper in the zeta table from the PMC Open Access
bucket (pmc-oa-opendata on S3, public, no key).

What counts as SI is what the paper's own JATS lists under <supplementary-material>. A file is
fetched only if its extension can carry text (PDF, Word, Excel, PowerPoint, csv, html, zip);
videos and images are recorded as skipped. Every outcome is a row in manifest.csv, so a paper
whose SI could not be read is never mistaken for a paper whose SI says nothing.

Usage: python -I fetch.py <d1_zeta_table.csv> <jats_xml_dir> <out_dir>
"""

import csv
import hashlib
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath

BUCKET = "https://pmc-oa-opendata.s3.amazonaws.com"
S3NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"
XLINK = "{http://www.w3.org/1999/xlink}href"
UA = {"User-Agent": "NanoSolve-mnp-research (SI census)"}
TEXT_EXT = {
    ".pdf",
    ".docx",
    ".doc",
    ".xlsx",
    ".xls",
    ".csv",
    ".txt",
    ".htm",
    ".html",
    ".pptx",
    ".ppt",
    ".zip",
    ".rtf",
    ".odt",
    ".tex",
}
MAX_BYTES = 80_000_000


def get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read()


def si_hrefs(xml_path: Path) -> list[str]:
    root = ET.parse(xml_path).getroot()
    hrefs = []
    for sm in root.iter("supplementary-material"):
        for el in sm.iter():
            h = el.get(XLINK)
            if h and h not in hrefs:
                hrefs.append(h)
    return hrefs


def s3_listing(pmcid: str) -> dict[str, tuple[str, int, str]]:
    """basename -> (key, size, md5) for the newest version of the article."""
    q = urllib.parse.urlencode({"list-type": "2", "prefix": f"{pmcid}.", "max-keys": "1000"})
    root = ET.fromstring(get(f"{BUCKET}/?{q}"))
    by_version: dict[int, dict] = {}
    for c in root.iter(f"{S3NS}Contents"):
        key = c.findtext(f"{S3NS}Key")
        version = int(key.split("/", 1)[0].split(".")[1])
        size = int(c.findtext(f"{S3NS}Size"))
        etag = c.findtext(f"{S3NS}ETag").strip('"')
        by_version.setdefault(version, {})[PurePosixPath(key).name] = (key, size, etag)
    return by_version[max(by_version)] if by_version else {}


def fetch_paper(pmcid: str, xml_dir: Path, out: Path) -> list[dict]:
    hrefs = si_hrefs(xml_dir / f"{pmcid}.xml")
    if not hrefs:
        return [{"pmcid": pmcid, "href": "", "status": "no_si_listed"}]
    try:
        listing = s3_listing(pmcid)
    except Exception as e:  # noqa: BLE001 - recorded, never silent
        return [{"pmcid": pmcid, "href": h, "status": f"listing_error:{e}"} for h in hrefs]
    rows = []
    for h in hrefs:
        row = {"pmcid": pmcid, "href": h}
        name = PurePosixPath(h).name
        ext = PurePosixPath(name).suffix.lower()
        if h.startswith(("http://", "https://", "ftp://")):
            row["status"] = "external_link"
        elif ext not in TEXT_EXT:
            row["status"] = "skipped_media"
        elif name not in listing:
            row["status"] = "not_in_bucket"
        elif listing[name][1] > MAX_BYTES:
            row.update(status="too_big", bytes=listing[name][1])
        else:
            key, size, md5 = listing[name]
            target = out / pmcid / name
            if not (target.is_file() and target.stat().st_size == size):
                data = get(f"{BUCKET}/{urllib.parse.quote(key)}")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            if "-" in md5:  # multipart upload: the ETag is not the file's md5
                status = "ok_unverified"
            elif hashlib.md5(target.read_bytes()).hexdigest() == md5:
                status = "ok"
            else:
                status = "md5_mismatch"
            row.update(status=status, bytes=size, md5=md5)
        rows.append(row)
    return rows


def main() -> None:
    table, xml_dir, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    with table.open() as fh:
        pmcids = sorted({r["pmcid"] for r in csv.DictReader(fh)})
    out.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(lambda p: fetch_paper(p, xml_dir, out), pmcids))
    fields = ["pmcid", "href", "status", "bytes", "md5"]
    with (out / "manifest.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fields)
        w.writeheader()
        for rows in results:
            w.writerows(rows)
    counts: dict[str, int] = {}
    for rows in results:
        for r in rows:
            s = r["status"].split(":")[0]
            counts[s] = counts.get(s, 0) + 1
    print(f"papers {len(pmcids)}  files by status {counts}")


if __name__ == "__main__":
    main()
