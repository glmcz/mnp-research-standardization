"""Screenshots of chosen slides, to look at before publishing: desktop (16:9) and phone width.

    uv run --with playwright python tool/slides/shots.py OUT_DIR s5,s14 [--phone]
    # OUT_DIR/desk-s5.png ... ; prints where each slide's body ends against its source line

Uses the installed Google Chrome. The deck is a fragment, so it is wrapped in a document first.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("ids")
    ap.add_argument("--phone", action="store_true")
    ap.add_argument("--deck", type=Path, default=HERE / "slides.html")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    wrap = a.out / "deck_wrapped.html"
    wrap.write_text(
        "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' "
        "content='width=device-width,initial-scale=1'></head><body>"
        + a.deck.read_text(encoding="utf-8")
        + "</body></html>",
        encoding="utf-8",
    )
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME)
        if a.phone:
            pg = b.new_page(viewport={"width": 375, "height": 800}, color_scheme="dark")
            pg.goto(wrap.as_uri(), wait_until="networkidle")
            pg.wait_for_timeout(600)
            print("page width", pg.evaluate("document.documentElement.scrollWidth"))
            for sid in a.ids.split(","):
                pg.locator(f"#{sid}").screenshot(path=str(a.out / f"phone-{sid}.png"))
        else:
            pg = b.new_page(viewport={"width": 1280, "height": 720}, color_scheme="light")
            for sid in a.ids.split(","):
                pg.goto(wrap.as_uri() + "#" + sid)
                pg.wait_for_timeout(450)
                pg.screenshot(path=str(a.out / f"desk-{sid}.png"))
                box = pg.evaluate(
                    f"""() => {{ const s = document.getElementById('{sid}');
                    const src = s.querySelector('.src'), body = s.querySelector('.body');
                    if (!src || !body) return null;
                    const a = body.getBoundingClientRect(), b = src.getBoundingClientRect();
                    return [Math.round(a.bottom), Math.round(b.top)]; }}"""
                )
                print(sid, "body bottom / source top", box)
        b.close()


if __name__ == "__main__":
    main()
