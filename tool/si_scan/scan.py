"""Sort every paper in the zeta table by what its supplementary text says about ionic strength.

The rules are the main pipeline's own (`mnp.extract.coerce`): "ionic strength"/"salinity"/"IS"
next to a concentration, or a concentration bound to a named salt (RC-02). A buffer's
concentration is not an ionic strength (RC-10), and DI water names a medium, not an ionic
strength. Those rules are strict, so a second, broad net (BROAD_RE: any salt, electrolyte,
buffer, seawater or concentration near a zeta mention) feeds the reading step too. The scan only
nominates; a reader decides whether a statement is the zeta measurement's condition, and
verify.py decides whether the reader's value stands.

Categories, first match wins:
  no_si_listed          the JATS lists no supplementary material
  si_unreadable         SI listed, but no file yielded text (external link, not in bucket, scanned)
  si_is_near_zeta       a strict statement sits within WINDOW characters of a zeta mention
  si_is_elsewhere       a strict statement exists, but not near a zeta mention (a recipe table
                        the main text points to is often here, so these are read too)
  si_salt_words_near_zeta  no strict statement; the broad net fires near a zeta mention
  si_zeta_no_is         zeta mentioned, and neither net fires
  si_no_zeta            SI never mentions zeta, and holds no strict statement

Independent of the category, `mass_recipes` counts salts printed in mass units ("Sodium
chloride 6.65 g/L"). The extraction never converts those, so they are a finding, not a claim.

Usage: python -I scan.py <d1_zeta_table.csv> <pmc_si_dir> <si_text_dir> <out_dir>
"""

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from mnp.extract.coerce import (
    BUFFER_RE,
    IONIC_PHRASE,
    _powers_of_ten,
    _salt_terms,
    concentrations_mM,
)

ZETA_RE = re.compile(r"zeta|ζ|electrophoretic\s+mobilit|zetasizer|zetapals", re.IGNORECASE)
DI_RE = re.compile(
    r"deioni[sz]ed|\bDI\s+water|milli-?q|ultrapure|distilled|double[- ]distilled", re.IGNORECASE
)
_SALT_NAME = (
    r"(?:NaCl|KCl|CaCl2?|MgCl2?|MgSO4|Na2SO4|NaHCO3|KH2PO4|K2HPO4|Na2HPO4|NaH2PO4|"
    r"(?:sodium|potassium|calcium|magnesium)\s+(?:chloride|sulfate|sulphate|bicarbonate|"
    r"hydrogen\s+carbonate|phosphate))"
)
_MASS_CONC = (
    r"\d+(?:[.,]\d+)?\s*(?:[mµμu]?g\s*(?:/|per\s+|\s)\s*(?:[mµμ]?L|l|litre|liter)\b|[mµμu]?g\s*L-1)"
)
# inline ("NaCl 6.65 g/L", "0.15 g/L KCl") or a table whose header carries the unit
# ("Chemical PSF (g/L) Sodium chloride 6.65", PMC13185065)
_UNIT_HEADER = r"\(\s*[mµμu]?g\s*(?:/|\s)\s*(?:[mµμ]?L|l)(?:-1)?\s*\)"
MASS_RECIPE_RE = re.compile(
    rf"{_SALT_NAME}[^.;]{{0,40}}?{_MASS_CONC}|{_MASS_CONC}[^.;]{{0,15}}?{_SALT_NAME}|"
    rf"{_UNIT_HEADER}[^;]{{0,300}}?{_SALT_NAME}\s*(?:\([^)]{{0,20}}\)\s*)?\d",
    re.IGNORECASE,
)
BROAD_RE = re.compile(
    r"ionic\s*strength|salinity|electrolyte|\bNaCl|\bKCl|CaCl|MgCl|NaNO3|KNO3|Na2SO4|\bPBS\b|"
    r"buffer|HEPES|sea\s*water|saline|conductivit|"
    r"\d\s*(?:[mµμu]?mol|[mµμu]?M\b)",
    re.IGNORECASE,
)
WINDOW = 600
TEXT_STATUSES = {"ok"}
# "10 mmol·L−1": the extraction's unit regexes take "mmol L-1" but not the middle dot
UNIT_DOT = re.compile(r"(mol|g)\s*[·⋅•]\s*(?=L)")


def flatten(text: str) -> str:
    """Whitespace folded (pdftotext wraps lines mid-sentence, parting "10 mM" from "NaCl")
    and the unit middle dot dropped. verify.py folds quotes the same way."""
    return UNIT_DOT.sub(r"\1 ", re.sub(r"\s+", " ", text))


# A sentence ends at a full stop that is not a decimal point, or at a semicolon. Splitting on
# every "." cut "0.15 M NaCl" into "0" and "15 M NaCl", a thousandfold error.
SENTENCE_RE = re.compile(r"(?:[^.;]|(?<=\d)\.(?=\d)){1,400}")


def statements(text: str) -> list[tuple[int, int, str]]:
    """(start, end, kind) of every ionic-strength-bearing sentence in whitespace-flattened text."""
    found = []
    for m in SENTENCE_RE.finditer(text):
        s = _powers_of_ten(m.group(0))
        if IONIC_PHRASE.search(s) and concentrations_mM(s):
            found.append((m.start(), m.end(), "ionic_phrase"))
        elif _salt_terms(s):
            found.append((m.start(), m.end(), "salt_concentration"))
    return found


def main() -> None:
    table, si_dir, text_dir, out = map(Path, sys.argv[1:5])
    rows_by_paper = defaultdict(list)
    with table.open() as fh:
        for r in csv.DictReader(fh):
            rows_by_paper[r["pmcid"]].append(r)
    manifest = defaultdict(list)
    with (si_dir / "manifest.csv").open() as fh:
        for r in csv.DictReader(fh):
            manifest[r["pmcid"]].append(r)
    index = defaultdict(list)
    with (text_dir / "index.csv").open() as fh:
        for r in csv.DictReader(fh):
            index[r["pmcid"]].append(r)

    out.mkdir(parents=True, exist_ok=True)
    papers, candidates = [], []
    for pmcid, rows in sorted(rows_by_paper.items()):
        listed = [m for m in manifest[pmcid] if m["status"] != "no_si_listed"]
        readable = [i for i in index[pmcid] if i["status"] in TEXT_STATUSES and int(i["chars"]) > 0]
        texts = (
            {p.name: flatten(p.read_text()) for p in sorted((text_dir / pmcid).glob("*.txt"))}
            if readable
            else {}
        )
        rec = dict(
            pmcid=pmcid,
            n_rows=len(rows),
            main_is_rows=sum(r["ionic_strength_reported"] == "True" for r in rows),
            si_files_listed=len(listed),
            si_files_text=len(readable),
            si_files_no_text=sum(i["status"] == "no_text" for i in index[pmcid]),
            si_chars=sum(len(t) for t in texts.values()),
        )
        zeta_hits = is_hits = near = broad = mass = 0
        di_near_zeta = False
        for name, text in texts.items():
            zetas = [m.start() for m in ZETA_RE.finditer(text)]
            zeta_hits += len(zetas)
            covered = set()
            for start, end, kind in statements(text):
                is_hits += 1
                close = [z for z in zetas if start - WINDOW <= z <= end + WINDOW]
                near += bool(close)
                covered.update(close)
                lo = max(0, min([start, *close]) - 250)
                hi = min(len(text), max([end, *close]) + 250)
                candidates.append(
                    dict(
                        pmcid=pmcid,
                        file=name,
                        kind=kind,
                        near_zeta=bool(close),
                        statement=text[start:end].strip(),
                        buffer_named=bool(BUFFER_RE.search(text[start:end])),
                        snippet=text[lo:hi].strip(),
                    )
                )
            for m in MASS_RECIPE_RE.finditer(text):
                mass += 1
                if mass <= 3:
                    candidates.append(
                        dict(
                            pmcid=pmcid,
                            file=name,
                            kind="mass_recipe",
                            near_zeta=any(abs(z - m.start()) <= WINDOW for z in zetas),
                            statement=m.group(0),
                            buffer_named=False,
                            snippet=text[max(0, m.start() - 300) : m.end() + 300].strip(),
                        )
                    )
            last_hi = -1
            for z in zetas:
                lo, hi = max(0, z - WINDOW), z + WINDOW
                window = text[lo:hi]
                if DI_RE.search(window):
                    di_near_zeta = True
                if z in covered or lo < last_hi or not BROAD_RE.search(window):
                    continue
                broad += 1
                last_hi = hi
                candidates.append(
                    dict(
                        pmcid=pmcid,
                        file=name,
                        kind="broad_window",
                        near_zeta=True,
                        statement="",
                        buffer_named=bool(BUFFER_RE.search(window)),
                        snippet=window.strip(),
                    )
                )
        if not listed:
            category = "no_si_listed"
        elif not texts:
            category = "si_unreadable"
        elif near:
            category = "si_is_near_zeta"
        elif is_hits:
            category = "si_is_elsewhere"
        elif broad:
            category = "si_salt_words_near_zeta"
        elif zeta_hits:
            category = "si_zeta_no_is"
        else:
            category = "si_no_zeta"
        rec.update(
            zeta_mentions=zeta_hits,
            is_statements=is_hits,
            is_near_zeta=near,
            broad_windows=broad,
            mass_recipes=mass,
            di_water_near_zeta=di_near_zeta,
            category=category,
        )
        papers.append(rec)

    with (out / "si_papers.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, list(papers[0]))
        w.writeheader()
        w.writerows(papers)
    with (out / "si_candidates.jsonl").open("w") as fh:
        for c in candidates:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    cats = Counter(p["category"] for p in papers)
    print(f"papers {len(papers)}")
    for k, v in cats.most_common():
        no_main = sum(1 for p in papers if p["category"] == k and p["main_is_rows"] == 0)
        print(f"  {k:24s} {v:4d}   (of which no IS row in main text: {no_main})")
    print(
        f"candidate statements {len(candidates)} in {len({c['pmcid'] for c in candidates})} papers"
    )


if __name__ == "__main__":
    main()
