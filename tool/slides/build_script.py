"""Build the talk script, `tool/slides/script.html`: what to say on each slide, and when.

The script is the deck's rehearsal companion. It speaks the deck's own values (`build_slides.build`
at the same ref), so every number said aloud is the number on the slide, and it copies each
slide's title and message out of the rendered deck instead of retyping them. `script_template.html`
holds the words. The only numbers typed here are the time plan: twenty minutes over the five acts of
the design's talk order (docs/DESIGN_2026-10-18_hypotheses-method-evaluation.md §6). Backup slides
have a card but no time.

    unset VIRTUAL_ENV
    uv run python tool/slides/build_script.py [--ref HEAD] [--out tool/slides/script.html]
"""

from __future__ import annotations

import argparse
import importlib.util
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent

_spec = importlib.util.spec_from_file_location("build_slides", HERE / "build_slides.py")
bs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bs)

# Seconds on each timed slide, at about a hundred spoken words a minute.
PLAN = {
    "s1": 30, "s2": 50, "s3": 55, "s4": 55, "s5": 50,
    "s6": 45, "s7": 45, "s8": 55, "s9": 35, "s10": 60, "s11": 50,
    "s12": 65, "s13": 55, "s14": 70, "s15": 70, "s16": 55,
    "s17": 45, "s18": 45, "s19": 70, "s20": 55,
    "s21": 40, "s22": 100,
}  # fmt: skip
ACTS = (
    ("I", "why it matters", ("s1", "s2", "s3", "s4", "s5")),
    ("II", "what is missing", ("s6", "s7", "s8", "s9", "s10", "s11")),
    ("III", "what the numbers say", ("s12", "s13", "s14", "s15", "s16")),
    ("IV", "agents that check", ("s17", "s18", "s19", "s20")),
    ("V", "the close", ("s21", "s22")),
)
#: Slides kept for questions: a card each, no time.
BACKUP = ("s23", "s24", "s25", "s26", "s27")
TOTAL = sum(PLAN.values())
SRC = "tool/slides/build_script.py PLAN"

SLIDE = re.compile(
    r'<section class="slide[^"]*" id="(s\d+)"(.*?)</section>\s*(?=<section class="slide|</main>)',
    re.S,
)


def clock(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


def timing_values() -> dict:
    """Each slide's length and the clock when it ends, each act's length and end, the total."""
    out, elapsed = {}, 0

    def put(key: str, seconds: int) -> None:
        out[key] = {"kind": "clock", "v": seconds, "text": clock(seconds), "src": SRC}

    for name, _, slides in ACTS:
        for sid in slides:
            elapsed += PLAN[sid]
            put(f"t.{sid}", PLAN[sid])
            put(f"at.{sid}", elapsed)
        put(f"act.{name}", sum(PLAN[s] for s in slides))
        put(f"act.{name}.end", elapsed)
    put("talk.total", TOTAL)
    return out


def slide_texts(deck_page: str) -> dict[str, dict[str, str]]:
    """Each slide's title and message as the rendered deck shows them, data slots included."""
    out = {}
    for sid, body in SLIDE.findall(deck_page):
        title = re.search(r"<h([12])[^>]*>(.*?)</h\1>", body, re.S).group(2)
        msg = re.search(r'<p class="(?:msg|sub)">(.*?)</p>', body, re.S).group(1)
        out[sid] = {"title": title, "msg": msg}
    return out


def render(deck: dict, deck_page: str, template: str | None = None) -> str:
    if template is None:
        template = (HERE / "script_template.html").read_text(encoding="utf-8")
    shown = slide_texts(deck_page)
    page = re.sub(r"\{\{(title|msg):(s\d+)\}\}", lambda m: shown[m.group(2)][m.group(1)], template)
    page = re.sub(r"\{\{w:t\.(s\d+)\}\}", lambda m: f"{PLAN[m.group(1)] / TOTAL * 100:.2f}%", page)
    values = {
        **deck["values"],
        **timing_values(),
        "build.commit": {
            "kind": "words",
            "v": deck["commit"],
            "text": deck["commit"],
            "src": "git",
        },
    }
    return bs.render({"ref": deck["ref"], "commit": deck["commit"], "values": values}, page)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ref", default="HEAD", help="git ref to read every input from")
    ap.add_argument("--out", default=str(HERE / "script.html"))
    ap.add_argument("--standalone", action="store_true", help="a whole document, to open as a file")
    args = ap.parse_args()

    deck = bs.build(args.ref)
    out = Path(args.out)
    page = render(deck, bs.render(deck))
    out.write_text(bs.standalone(page) if args.standalone else page, encoding="utf-8")
    print(f"{args.ref} ({deck['commit']}): wrote {out}, {out.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
