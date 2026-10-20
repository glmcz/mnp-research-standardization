"""Turn every fetched supplementary file into plain text, one .txt per file (or per zip member).

PDF via pdftotext, Word/RTF/HTML/ODT via macOS textutil, xlsx and pptx read from their XML,
xls via xlrd. A zip is opened one level deep. Each file lands in index.csv with its status, so a
scanned PDF with no text layer reads as "no_text", not as an SI that states nothing.

Usage: python -I to_text.py <pmc_si_dir> <out_dir>
"""

import csv
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path, PurePosixPath

SHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
DRAW_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
TEXTUTIL = {".doc", ".docx", ".rtf", ".htm", ".html", ".odt"}
PLAIN = {".csv", ".txt", ".tex"}
MIN_CHARS_PER_PDF_PAGE = 100


def pdf_text(path: Path) -> str:
    return subprocess.run(
        ["pdftotext", "-enc", "UTF-8", str(path), "-"], capture_output=True, check=True, timeout=300
    ).stdout.decode("utf-8", "replace")


def pdf_pages(path: Path) -> int:
    info = subprocess.run(["pdfinfo", str(path)], capture_output=True, timeout=60).stdout.decode(
        "utf-8", "replace"
    )
    m = re.search(r"^Pages:\s+(\d+)", info, re.M)
    return int(m.group(1)) if m else 1


def textutil_text(path: Path) -> str:
    return subprocess.run(
        ["textutil", "-convert", "txt", "-stdout", str(path)],
        capture_output=True,
        check=True,
        timeout=300,
    ).stdout.decode("utf-8", "replace")


def xlsx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(f"{SHEET_NS}si"):
                shared.append("".join(t.text or "" for t in si.iter(f"{SHEET_NS}t")))
        lines = []
        for name in sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n)):
            lines.append(f"## {PurePosixPath(name).stem}")
            for row in ET.fromstring(z.read(name)).iter(f"{SHEET_NS}row"):
                cells = []
                for c in row.iter(f"{SHEET_NS}c"):
                    v = c.findtext(f"{SHEET_NS}v")
                    if c.get("t") == "s" and v is not None:
                        v = shared[int(v)]
                    elif c.get("t") == "inlineStr":
                        v = "".join(t.text or "" for t in c.iter(f"{SHEET_NS}t"))
                    cells.append(v or "")
                if any(cells):
                    lines.append("\t".join(cells))
        return "\n".join(lines)


def xls_text(path: Path) -> str:
    import xlrd

    book = xlrd.open_workbook(str(path))
    lines = []
    for sheet in book.sheets():
        lines.append(f"## {sheet.name}")
        for r in range(sheet.nrows):
            cells = [str(v) for v in sheet.row_values(r)]
            if any(cells):
                lines.append("\t".join(cells))
    return "\n".join(lines)


def pptx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        slides = sorted(
            (n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)),
            key=lambda n: int(re.search(r"(\d+)\.xml$", n).group(1)),
        )
        return "\n".join(
            " ".join(t.text or "" for t in ET.fromstring(z.read(n)).iter(f"{DRAW_NS}t"))
            for n in slides
        )


def convert(path: Path) -> tuple[str, str]:
    """(status, text) for one file that is not a zip."""
    ext = path.suffix.lower()
    try:
        if ext == ".pdf":
            text = pdf_text(path)
            if len(text.strip()) < MIN_CHARS_PER_PDF_PAGE * pdf_pages(path):
                return "no_text", text
            return "ok", text
        if ext in TEXTUTIL:
            return "ok", textutil_text(path)
        if ext == ".xlsx":
            return "ok", xlsx_text(path)
        if ext == ".xls":
            # some "xls" files are tab-separated text with the wrong extension
            raw = path.read_bytes()
            if b"\x00" not in raw[:4096]:
                return "ok", raw.decode("utf-8", "replace")
            return "ok", xls_text(path)
        if ext == ".pptx":
            return "ok", pptx_text(path)
        if ext in PLAIN:
            return "ok", path.read_bytes().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001 - recorded in the index, never silent
        return f"error:{type(e).__name__}", ""
    return "unsupported", ""


def safe_name(member: str) -> str:
    return re.sub(r"[^\w.\-]+", "_", PurePosixPath(member).name)[:150] or "member"


def main() -> None:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    rows = []
    for paper in sorted(p for p in src.iterdir() if p.is_dir()):
        for f in sorted(paper.iterdir()):
            if f.suffix.lower() != ".zip":
                status, text = convert(f)
                rows.append(
                    dict(pmcid=paper.name, file=f.name, member="", status=status, chars=len(text))
                )
                if text:
                    (out / paper.name).mkdir(parents=True, exist_ok=True)
                    (out / paper.name / f"{f.name}.txt").write_text(text)
                continue
            try:
                z = zipfile.ZipFile(f)
            except zipfile.BadZipFile:
                rows.append(
                    dict(
                        pmcid=paper.name, file=f.name, member="", status="error:BadZipFile", chars=0
                    )
                )
                continue
            with z, tempfile.TemporaryDirectory() as tmp:
                for info in z.infolist():
                    if info.is_dir() or "__MACOSX" in info.filename or info.file_size > 80_000_000:
                        continue
                    name = safe_name(info.filename)
                    member = Path(tmp) / name
                    member.write_bytes(z.read(info))
                    status, text = convert(member)
                    rows.append(
                        dict(
                            pmcid=paper.name,
                            file=f.name,
                            member=info.filename,
                            status=status,
                            chars=len(text),
                        )
                    )
                    if text:
                        (out / paper.name).mkdir(parents=True, exist_ok=True)
                        (out / paper.name / f"{f.name}__{name}.txt").write_text(text)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "index.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, ["pmcid", "file", "member", "status", "chars"])
        w.writeheader()
        w.writerows(rows)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"].split(":")[0]] = counts.get(r["status"].split(":")[0], 0) + 1
    print(f"files {len(rows)}  by status {counts}")


if __name__ == "__main__":
    main()
