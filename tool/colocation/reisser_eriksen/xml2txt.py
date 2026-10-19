"""JATS XML -> plain text, one paragraph per line, prefixed with its section path.

Usage: python -I xml2txt.py <in.xml> <out.txt>
"""

import sys
import xml.etree.ElementTree as ET


def text(el):
    return " ".join("".join(el.itertext()).split())


root = ET.parse(sys.argv[1]).getroot()
out = []
front = root.find("front")
if front is not None:
    for c in front.iter("contrib"):
        n = c.find("name")
        if n is not None:
            aff = [x.get("rid") for x in c.findall("xref") if x.get("ref-type") == "aff"]
            out.append(f"[AUTHOR] {text(n)} aff={aff}")
    for a in front.iter("aff"):
        out.append(f"[AFF {a.get('id')}] {text(a)}")
    for a in front.iter("abstract"):
        out.append(f"[ABSTRACT] {text(a)}")


def walk(el, path):
    for ch in el:
        if ch.tag == "sec":
            t = ch.find("title")
            walk(ch, path + [text(t) if t is not None else "?"])
        elif ch.tag in ("p", "table-wrap", "fig", "supplementary-material", "disp-formula"):
            label = ch.find("label")
            cap = ch.find("caption")
            head = " ".join(x for x in [text(label) if label is not None else "", ""] if x)
            if ch.tag == "p":
                out.append(f"[{' > '.join(path)}] {text(ch)}")
            else:
                out.append(f"[{' > '.join(path)}] <{ch.tag} {head}> {text(ch)}")


body = root.find("body")
if body is not None:
    walk(body, [])
back = root.find("back")
if back is not None:
    for ch in back:
        if ch.tag != "ref-list":
            walk(ch, ["back:" + ch.tag])
    for r in back.iter("ref"):
        out.append(f"[REF {r.get('id')}] {text(r)}")
open(sys.argv[2], "w").write("\n".join(out) + "\n")
print(len(out), "lines")
