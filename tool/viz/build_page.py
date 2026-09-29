"""Inline data.json into template.html and write mnp-results.html next to them.

python tool/viz/build_page.py
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLACEHOLDER = "__DATA__"


def inline(template: str, data: dict) -> str:
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # A `</` or `<!--` in a string would close the <script> element or open a comment inside it.
    # `<\/` and `<!--` are the same JSON strings, spelled so the HTML parser cannot see them.
    blob = blob.replace("</", "<\\/").replace("<!--", "<\\" + "u0021--")
    assert template.count(PLACEHOLDER) == 1, f"template must hold {PLACEHOLDER} exactly once"
    return template.replace(PLACEHOLDER, blob)


def main() -> None:
    data = json.loads((HERE / "data.json").read_text(encoding="utf-8"))
    template = (HERE / "template.html").read_text(encoding="utf-8")
    out = HERE / "mnp-results.html"
    out.write_text(inline(template, data), encoding="utf-8")
    print(f"wrote {out}, {out.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
