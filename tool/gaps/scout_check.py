"""The gap scout's interlaboratory numbers, kept only where code finds them on the cited page.

The scout (`.claude/agents/mnp-gap-scout.md`) reports a spread with a verbatim quote and the URL
that prints it. Here code fetches the page (cached), reduces it to text, and keeps an item only if
the quote is on the page and the spread's number is inside the quote: the rule the extractor
follows for papers (EX-02). A kept spread becomes a gap in the unit of its family: mV for charge,
a fold between laboratories for counts.

    uv run --with openpyxl python tool/gaps/scout_check.py
    # out/tables/gap_scout.json (the agent's report) -> out/tables/gap_scout_verified.csv
"""

from __future__ import annotations

import html
import io
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "tool" / "discover"))
import catalog  # noqa: E402

SCOUT = ROOT / "out/tables/gap_scout.json"
OUT = ROOT / "out/tables/gap_scout_verified.csv"
_NUM = r"-?\d+(?:\.\d+)?"


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        self.skip += tag in ("script", "style")

    def handle_endtag(self, tag):
        self.skip -= tag in ("script", "style") and self.skip > 0

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def norm(text: str) -> str:
    """One spelling for what typography varies: dashes, minus signs, spaces, case."""
    t = html.unescape(text)
    t = re.sub(r"[−–—‐‑]", "-", t)
    t = re.sub(r"[   ]", " ", t).replace("±", "+/-")
    return re.sub(r"\s+", " ", t).strip().lower()


def page_text(raw: bytes) -> str:
    if raw[:4] == b"%PDF":
        from pypdf import PdfReader

        text = "\n".join(pg.extract_text() or "" for pg in PdfReader(io.BytesIO(raw)).pages)
        return norm(re.sub(r"-\n(?=[a-z])", "", text))  # a word split across a line break
    p = _Text()
    p.feed(raw.decode("utf-8", errors="replace"))
    return norm(" ".join(p.parts))


def numbers(text: str) -> list[float]:
    return [float(x) for x in re.findall(_NUM, norm(text).replace(",", ""))]


def per_lab(spread: str) -> list[str]:
    """Per-laboratory values as printed after their labels ("Lab3 -26.71(15.21)" gives -26.71)."""
    return re.findall(r"lab\s*\d+\s*(?:row)?\s*:?\s*(" + _NUM + ")", norm(spread))


SPREAD_WORDS = r"\bsd\b|\brsd\b|standard deviation|reproducib|precision|uncertaint"


def percents(quote: str) -> list[float]:
    """Percentages after the first word that names a spread: a recovery before it is not one."""
    m = re.search(SPREAD_WORDS, norm(quote))
    tail = norm(quote)[m.start() :] if m else ""
    return [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*%", tail)]


def skeleton(text: str) -> str:
    """Letters, digits, points and percent signs only: a PDF's line breaks, hyphenation and
    dashes cannot break a match, and every printed character of substance still must."""
    return re.sub(r"[^a-z0-9.%]", "", norm(text))


def gap(item: dict) -> tuple[float | None, str, float | None]:
    """The spread as a gap (value, metric, upper end): mV for charge, a fold for counts."""
    kind, unit = item["spread_kind"], norm(item.get("unit") or "")
    family = item["family"]
    if kind == "per_lab" and per_lab(item["spread"]) and family == "A" and "mv" in unit:
        xs = [float(x) for x in per_lab(item["spread"])]
        return max(xs) - min(xs), f"range of {len(xs)} laboratory means", None
    # a percentage is a spread only where its sentence says so
    if kind == "other" and family == "B" and re.search(SPREAD_WORDS, norm(item["quote"])):
        cs = [c for c in percents(item["quote"]) if c < 100]  # a fold needs a SD under 100 %
        if cs:
            fold = [(1 + c / 100) / (1 - c / 100) for c in (min(cs), max(cs))]
            return fold[0], "plus over minus one reproducibility SD, as a fold", fold[1]
    m = re.search(r"expanded uncertainty\s*(" + _NUM + r")\s*mv", norm(item["spread"]))
    if kind == "other" and family == "A" and m:
        u = abs(float(m.group(1)))
        if u in [abs(x) for x in numbers(item["quote"])]:
            return u, "certified expanded uncertainty, k = 2", None
    xs = [abs(x) for x in numbers(item["spread"])]
    if not xs:
        return None, "no number", None
    if family == "A":
        if "mv" not in unit:
            return None, "not in mV", None
        if kind in ("range", "per_lab") and len(xs) >= 2:
            return max(xs) - min(xs), "range between laboratories", None
        if kind == "sd":
            return xs[0], "reproducibility SD", None
        if kind == "cv":
            centre = [abs(x) for x in numbers(item.get("central") or "")]
            if centre:
                return xs[0] / 100 * centre[0], "CV times the mean", None
            return None, "no mean", None
        return None, f"spread kind {kind}", None
    if kind in ("range", "per_lab") and len(xs) >= 2 and min(xs) > 0:
        return max(xs) / min(xs), "fold between laboratories", None
    if kind == "cv" and max(xs[:2]) < 100:
        fold = [(1 + c / 100) / (1 - c / 100) for c in xs[:2]]
        return (
            min(fold),
            "plus over minus one CV, as a fold",
            (max(fold) if len(fold) > 1 else None),
        )
    return None, f"spread kind {kind}", None


def check(item: dict) -> dict:
    keys = ("family", "name", "url", "material", "unit", "spread_kind", "spread", "central",
            "labs", "quote")  # fmt: skip
    row = {k: item.get(k) for k in keys}
    try:
        text = page_text(catalog.get(item["url"]))
    except Exception as exc:  # noqa: BLE001 - a page that will not load is a finding
        return row | {"kept": False, "why": f"fetch failed: {type(exc).__name__}"}
    quote = norm(item["quote"])
    if skeleton(quote) not in skeleton(text):
        return row | {"kept": False, "why": "quote not on the page"}
    labs = per_lab(item["spread"]) if item["spread_kind"] == "per_lab" else []
    if labs:
        # a table cannot sit in a quote: each laboratory's value must be on the page as printed
        if not all(re.search(r"(?<![\d.])" + re.escape(x) + r"(?!\d)", text) for x in labs):
            return row | {"kept": False, "why": "a laboratory value is not on the page"}
    elif item["spread_kind"] == "other":
        if not numbers(item["quote"]):
            return row | {"kept": False, "why": "no number in the quote"}
    else:
        inside = numbers(item["spread"])
        if not inside or not all(f"{abs(x):g}" in quote.replace(",", "") for x in inside[:2]):
            return row | {"kept": False, "why": "spread number not in the quote"}
    value, metric, high = gap(item)
    if value is None:
        return row | {"kept": False, "why": metric}
    why = "quote found, values on the page" if labs else "quote found, number inside"
    # further sentences the agent quoted from the same page, each kept only if it is there
    extra = [q for q in item.get("extra_quotes") or [] if skeleton(q) in skeleton(text)]
    return row | {"kept": True, "why": why, "value": value, "high": high, "metric": metric,
                  "extra_found": json.dumps(extra)}  # fmt: skip


def merged(items: list[dict]) -> list[dict]:
    """One row per page for per-laboratory tables the agent split over several items."""
    out, seen = [], {}
    for it in items:
        if it["spread_kind"] == "per_lab" and it["url"] in seen:
            first = seen[it["url"]]
            first["spread"] += "; " + it["spread"]
            first["merged"] = first.get("merged", 1) + 1
            continue
        if it["spread_kind"] == "per_lab":
            seen[it["url"]] = it = dict(it)
        out.append(it)
    for it in out:
        if it.get("merged"):  # the union of the laboratories named, each value once
            labs = dict(
                re.findall(r"lab\s*(\d+)\s*(?:row)?\s*:?\s*(" + _NUM + ")", norm(it["spread"]))
            )
            it["spread"] = "; ".join(f"Lab{k} {v}" for k, v in sorted(labs.items()))
    return out


def main() -> None:
    items = merged(json.loads(SCOUT.read_text())["items"])
    t = pd.DataFrame([check(i) for i in items])
    t.to_csv(OUT, index=False)
    print(t[["family", "name", "kept", "why"]].to_string())


if __name__ == "__main__":
    main()
