"""What the `jats._find_methods` fix changes, measured on the vendored corpus. No model.

The parser used to take a `sec-type="supplementary-materials"` section for the methods, and a
sec-type match stopped the title fallback, so the real Materials and Methods never reached
`Article.methods_text`. This parses every XML under `config.EPMC_XML_DIR` twice — once with
a private copy of the finder as it was (`_find_methods_before_fix`), once with the fixed
parser — and counts what moves: the methods themselves, the capped text the extraction model
reads, the line documents every stored citation addresses, and the consumers of those
addresses. The gain section is an upper bound by regex, not a measurement, and says so.

Read-only apart from `data/interim/methods_fix_impact.json`.

    uv run python tool/methods_fix_impact.py
"""

from __future__ import annotations

import json
import re
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pandas as pd
from lxml import etree

from mnp import config
from mnp.corpus import jats, lines
from mnp.demo import cases as demo_cases
from mnp.eval.cells import Corpus
from mnp.extract import zeta
from mnp.report import quotes

OUT = config.DATA_INTERIM / "methods_fix_impact.json"
CONDITIONS = ("medium", "ionic_strength", "pH", "temperature", "instrument")
_CITE = re.compile(r"\b(PMC\d+):L(\d+)\b")


def _find_methods_before_fix(body: etree._Element) -> tuple[list[etree._Element], str]:
    """`jats._find_methods` as of 7a0b858: any sec-type matching "method|materials" wins,
    supplementary-materials included, and a win means titles are never tried."""
    by_type = [
        s
        for s in body.iter("sec")
        if s.get("sec-type") and jats.METHODS_SECTYPE_RE.search(s.get("sec-type"))
    ]
    by_type = jats._drop_nested(by_type)
    if by_type:
        return by_type, "sec-type"
    by_title = [s for s in body.iter("sec") if jats.METHODS_TITLE_RE.match(jats._sec_title(s))]
    by_title = jats._drop_nested(by_title)
    if by_title:
        return by_title, "title"
    return [], "none"


@contextmanager
def _old_finder() -> Iterator[None]:
    fixed = jats._find_methods
    jats._find_methods = _find_methods_before_fix
    try:
        yield
    finally:
        jats._find_methods = fixed


def _parse(raw: bytes, pmcid: str, old: bool) -> jats.Article:
    if old:
        with _old_finder():
            article = jats.parse(raw)
    else:
        article = jats.parse(raw)
    article.pmcid = pmcid
    return article


# -- what the model reads ---------------------------------------------------------------------


def _capped_pieces(article: jats.Article) -> list[tuple[str, list[str]]]:
    """`jats.extraction_text(max_tokens=zeta.MAX_TOKENS)` as (header, kept lines).

    A replica of its budget loop, checked against the real thing for every paper, because the
    question is which lines of which piece survive the cap and the string alone does not say.
    """
    budget = zeta.MAX_TOKENS
    kept: list[tuple[str, list[str]]] = []
    for header, body, _ in sorted(jats._pieces(article), key=lambda p: p[2]):
        header_cost = jats.approx_tokens(header) + 1
        if header_cost >= budget:
            break
        taken, cost = [], header_cost
        for line in body.splitlines():
            c = jats.approx_tokens(line) + 1
            if cost + c > budget:
                continue
            taken.append(line)
            cost += c
        if taken:
            kept.append((header, taken))
            budget -= cost
    rebuilt = "\n\n".join(f"{h}\n" + "\n".join(ls) for h, ls in kept)
    if rebuilt != jats.extraction_text(article, max_tokens=zeta.MAX_TOKENS):
        raise SystemExit(f"{article.pmcid}: capped-text replica drifted from jats.extraction_text")
    return kept


def _uncapped_tokens(article: jats.Article) -> int:
    return jats.approx_tokens(jats.extraction_text(article))


def _visible(pieces: list[tuple[str, list[str]]]) -> set[str]:
    return {line for _, ls in pieces for line in ls}


def _methods_kept(pieces: list[tuple[str, list[str]]]) -> list[str]:
    return next((ls for h, ls in pieces if h == "== Methods"), [])


# -- the upper-bound regexes --------------------------------------------------------------------

_CONC = re.compile(r"\d+(?:\.\d+)?\s*(?:mM|mmol|[µμu]M|M)\b")
_SALT = re.compile(
    r"NaCl|KCl|CaCl|MgCl|Na2SO4|NaNO3|KNO3|ionic|buffer|salt|electrolyte", re.IGNORECASE
)
GAIN_RE = {
    "temperature": re.compile(r"\d+(?:\.\d+)?\s*(?:°\s*C|℃)"),
    "pH": re.compile(r"\bpH\s*(?:of|=|was|value of)?\s*\d"),
    "instrument": re.compile(
        r"Zetasizer|Malvern|NanoBrook|Brookhaven|Litesizer|Anton Paar|Horiba|SZ-100|Delsa|"
        r"Stabino|ZetaView|Particle Metrix"
    ),
    "medium": re.compile(
        r"(?:deioni[sz]ed|\bDI\b|Milli-?Q|ultra-?pure|(?:double[- ])?distilled|MQ)\s+water|"
        r"\b(?:NaCl|KCl|CaCl2|PBS|HEPES|Tris|MOPS|MES|buffer|sea\s?water|river water|"
        r"lake water|tap water|culture medium|DMEM|RPMI)\b",
        re.IGNORECASE,
    ),
}


def _ionic_candidate(text: str) -> bool:
    if re.search(r"ionic strength", text, re.IGNORECASE):
        return True
    for m in _CONC.finditer(text):
        window = text[max(0, m.start() - 80) : m.end() + 80]
        if _SALT.search(window):
            return True
    return False


def candidates_in(text: str) -> dict[str, bool]:
    found = {name: bool(rx.search(text)) for name, rx in GAIN_RE.items()}
    found["ionic_strength"] = _ionic_candidate(text)
    return found


# -- line documents -----------------------------------------------------------------------------


# The repair `extract.origin.load_doc` carried when this was measured. The origin reader has
# since gone back to `lines.build_lines`, so these are private copies, like the old finder above.


def _methods_like(sec: etree._Element) -> bool:
    kind = sec.get("sec-type") or ""
    if jats.NOT_METHODS_SECTYPE_RE.search(kind):
        return False
    title = jats._sec_title(sec)
    return bool(jats.METHODS_TITLE_RE.match(title) or jats.METHODS_SECTYPE_RE.search(kind))


def _methods_lost(raw: bytes) -> bool:
    """Every section `jats._find_methods` took for the methods is supplementary material."""
    root = etree.fromstring(raw, parser=etree.XMLParser(recover=True, huge_tree=True))
    body = root.find("body")
    if body is None:
        return False
    secs, source = jats._find_methods(body)
    return source == "sec-type" and all(
        jats.NOT_METHODS_SECTYPE_RE.search(s.get("sec-type") or "") for s in secs
    )


def _append_lost_methods(doc: lines.LinedDoc, raw: bytes) -> lines.LinedDoc:
    """Body paragraphs missing from `doc` that sit in a methods-like section — or, in a paper
    with no methods-like section at all, every body paragraph missing from it."""
    root = etree.fromstring(raw, parser=etree.XMLParser(recover=True, huge_tree=True))
    body = root.find("body")
    if body is None:
        return doc
    have = {x.text for x in doc.lines}
    any_methods = any(_methods_like(s) for s in body.iter("sec"))
    groups: dict[str, list[str]] = {}
    for para in jats._paragraphs(body):
        text = jats._para_text(para)
        if not text or text in have:
            continue
        secs = [a for a in para.iterancestors() if a.tag == "sec"][::-1]
        if any_methods and not any(_methods_like(s) for s in secs):
            continue
        titles = " / ".join(t for t in (jats._sec_title(s) for s in secs) if t) or "Body"
        groups.setdefault(titles, []).append(text)
    if not groups:
        return doc
    rows, spans, taken = list(doc.lines), list(doc.sections), {}
    for titles, texts in groups.items():
        path = lines._unique(f"body:{titles}", taken)
        start = len(rows)
        for ordinal, text in enumerate(texts):
            rows.append(
                lines.Line(len(rows) + 1, text, path, ordinal, lines.line_id(path, ordinal, text))
            )
        spans.append(lines.SectionSpan(path, f"== {titles}", start, len(rows)))
    return lines.LinedDoc(doc.pmcid, tuple(rows), tuple(spans))


def _load_doc(article: jats.Article, raw: bytes) -> lines.LinedDoc:
    """`extract.origin.load_doc` as it was, for an article already parsed, old or new."""
    return _append_lost_methods(lines.build_lines(article), raw)


def _appends(article: jats.Article, raw: bytes) -> int:
    return len(_load_doc(article, raw).lines) - len(lines.build_lines(article).lines)


def _ids(value: object) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    return [x for x in str(value).split(";") if x]


class Paper:
    """Both parses of one XML and everything derived from them, built on first use."""

    def __init__(self, path: Path):
        self.pmcid = path.stem
        self.raw = path.read_bytes()
        self.old = _parse(self.raw, self.pmcid, old=True)
        self.new = _parse(self.raw, self.pmcid, old=False)
        self._cache: dict[str, object] = {}

    @property
    def changed(self) -> bool:
        return (self.old.methods_source, self.old.methods_text) != (
            self.new.methods_source,
            self.new.methods_text,
        )

    def _get(self, key: str, make):
        if key not in self._cache:
            self._cache[key] = make()
        return self._cache[key]

    def doc(self, old: bool) -> lines.LinedDoc:
        a = self.old if old else self.new
        return self._get(f"doc{old}", lambda: lines.build_lines(a))

    def origin_doc(self, old: bool) -> lines.LinedDoc:
        a = self.old if old else self.new
        return self._get(f"odoc{old}", lambda: _load_doc(a, self.raw))

    def pieces(self, old: bool) -> list[tuple[str, list[str]]]:
        a = self.old if old else self.new
        return self._get(f"pieces{old}", lambda: _capped_pieces(a))


# -- the measurement -----------------------------------------------------------------------------


def measure_parse(papers: dict[str, Paper], with_rows: set[str], records: dict) -> dict:
    changed = sorted(p for p, x in papers.items() if x.changed)
    changed_rows = sorted(set(changed) & with_rows)
    transitions = Counter(
        f"{papers[p].old.methods_source}->{papers[p].new.methods_source}" for p in changed_rows
    )
    lost_by_report = {p for p in with_rows if _old_methods_lost(papers[p].raw)}

    def stored_source_mismatch() -> list[str]:
        return sorted(
            p
            for p, r in records.items()
            if p in papers and r.get("methods_source") != papers[p].old.methods_source
        )

    return {
        "xml_files": len(papers),
        "changed_papers_all_xml": len(changed),
        "papers_with_rows": len(with_rows),
        "changed_papers_with_rows": len(changed_rows),
        "methods_source_transitions_with_rows": dict(sorted(transitions.items())),
        "old_supplement_only_with_rows": sum(
            1
            for p in changed_rows
            if papers[p].old.methods_source == "sec-type"
            and "supplement" in papers[p].old.methods_text.lower()
            and papers[p].new.methods_source != "sec-type"
        ),
        "changed_but_not_methods_lost": sorted(set(changed_rows) - lost_by_report),
        "methods_lost_but_unchanged": sorted(lost_by_report - set(changed_rows)),
        "records_whose_stored_methods_source_differs_from_old_parse": stored_source_mismatch(),
        "changed_pmcids_with_rows": changed_rows,
    }


def measure_text(papers: dict[str, Paper], changed_rows: list[str]) -> dict:
    survival = Counter()
    context_changed, extras_changed, text_changed, cap_binds = [], [], [], []
    lost_other, lost_keyword, fewer_candidates, more_candidates = [], [], [], []
    lost_lines, lost_papers = Counter(), Counter()
    per_paper: dict[str, dict] = {}
    for p in changed_rows:
        x = papers[p]
        old_p, new_p = x.pieces(True), x.pieces(False)
        old_text = "\n\n".join(f"{h}\n" + "\n".join(ls) for h, ls in old_p)
        new_text = "\n\n".join(f"{h}\n" + "\n".join(ls) for h, ls in new_p)
        if old_text != new_text:
            text_changed.append(p)
        if x.old.keyword_windows != x.new.keyword_windows:
            context_changed.append(p)
        if [s.title for s in x.old.extra_sections] != [s.title for s in x.new.extra_sections]:
            extras_changed.append(p)
        if _uncapped_tokens(x.new) > zeta.MAX_TOKENS:
            cap_binds.append(p)

        old_methods = {t for t in x.old.methods_text.split("\n") if t}
        recovered = [t for t in x.new.methods_text.split("\n") if t and t not in old_methods]
        kept = set(_methods_kept(new_p))
        survived = sum(1 for t in recovered if t in kept)
        if not recovered:
            survival["no_methods_recovered"] += 1
        elif survived == len(recovered):
            survival["fully"] += 1
        elif survived:
            survival["partly"] += 1
        else:
            survival["not_at_all"] += 1

        old_vis, new_vis = _visible(old_p), _visible(new_p)
        old_methods_kept = set(_methods_kept(old_p))
        gone = old_vis - new_vis
        gone_other = {t for t in gone if t not in old_methods_kept}
        if gone_other:
            lost_other.append(p)
        # A line now inside the methods but not kept was cut by the cap. Anything else was a
        # neighbour in a keyword window whose only hit the methods now cover, so the window
        # is dropped whole and its uncovered neighbours with it.
        new_methods = set(x.new.methods_text.split("\n"))
        cut = {t for t in gone_other if t in new_methods}
        lost_lines["cut_by_cap"] += len(cut)
        lost_lines["window_dropped_with_its_covered_hit"] += len(gone_other - cut)
        lost_papers["cut_by_cap"] += bool(cut)
        lost_papers["window_dropped_with_its_covered_hit"] += bool(gone_other - cut)
        if any(jats.KEYWORD_RE.search(t) for t in gone_other):
            lost_keyword.append(p)
        n_old, n_new = len(zeta.find_candidates(old_text)), len(zeta.find_candidates(new_text))
        if n_new < n_old:
            fewer_candidates.append(p)
        elif n_new > n_old:
            more_candidates.append(p)
        per_paper[p] = {
            "old_source": x.old.methods_source,
            "new_source": x.new.methods_source,
            "recovered_methods_lines": len(recovered),
            "recovered_lines_kept_under_cap": survived,
            "new_visible_lines": len(new_vis - old_vis),
            "lines_no_longer_visible_outside_old_methods": len(gone_other),
            "capped_tokens_old": jats.approx_tokens(old_text),
            "capped_tokens_new": jats.approx_tokens(new_text),
            "uncapped_tokens_new": _uncapped_tokens(x.new),
            "value_candidates_old": n_old,
            "value_candidates_new": n_new,
        }
    return {
        "extraction_text_changed": len(text_changed),
        "cap_binds_on_new_text": len(cap_binds),
        "recovered_methods_survive_cap": dict(survival),
        "context_sections_changed": len(context_changed),
        "extra_sections_changed": len(extras_changed),
        "papers_losing_visible_lines_outside_old_methods": len(lost_other),
        "lost_lines_by_cause": dict(lost_lines),
        "lost_papers_by_cause": dict(lost_papers),
        "papers_losing_a_visible_keyword_line": sorted(lost_keyword),
        "papers_with_fewer_value_candidates": sorted(fewer_candidates),
        "papers_with_more_value_candidates": len(more_candidates),
        "per_paper": per_paper,
    }


def _vanished(x: Paper) -> set[str]:
    old = {ln.line_id for ln in x.doc(True).lines}
    return old - {ln.line_id for ln in x.doc(False).lines}


def measure_addresses(papers: dict[str, Paper], changed: set[str], table: pd.DataFrame) -> dict:
    out: dict[str, dict] = {}
    docs_changed = sum(1 for p in changed if papers[p].doc(True) != papers[p].doc(False))
    vanished = {p: _vanished(papers[p]) for p in changed}
    all_vanished = set().union(*vanished.values()) if vanished else set()

    rows = table[table["pmcid"].isin(changed)]
    ids_total = ids_gone = rows_hit = old_unresolved = 0
    for pmcid, ids in zip(rows["pmcid"], rows["evidence_line_ids"], strict=True):
        new_doc, old_doc = papers[pmcid].doc(False), papers[pmcid].doc(True)
        ids = _ids(ids)
        gone = [i for i in ids if lines.resolve_id(new_doc, i) is None]
        old_unresolved += sum(1 for i in ids if lines.resolve_id(old_doc, i) is None)
        ids_total += len(ids)
        ids_gone += len(gone)
        rows_hit += bool(gone)
    out["d1_zeta_table.evidence_line_ids"] = {
        "rows_in_changed_papers": int(len(rows)),
        "rows_with_ids": int(rows["evidence_line_ids"].notna().sum()),
        "ids": ids_total,
        "ids_no_longer_resolving": ids_gone,
        "rows_with_an_unresolved_id": rows_hit,
        "ids_already_unresolved_in_old_doc": old_unresolved,
    }

    release = pd.read_parquet(config.OUT / "release" / "dataset.parquet")
    withheld = release[release["quote_withheld"].astype(bool) & release["pmcid"].isin(changed)]
    broken = []
    for _, r in withheld.iterrows():
        doc = papers[r["pmcid"]].doc(False)
        try:
            text = quotes.restore(doc, json.loads(r["evidence_quote_spans"]))
        except (KeyError, TypeError, ValueError):
            text = None
        if text is None or quotes.sha256_text(text) != r["evidence_quote_sha256"]:
            broken.append(str(r["row_id"]))
    out["release.withheld_quote_spans"] = {
        "withheld_rows_all_papers": int(release["quote_withheld"].astype(bool).sum()),
        "withheld_rows_in_changed_papers": int(len(withheld)),
        "no_longer_restore_to_their_sha256": len(broken),
        "papers": sorted({b.rsplit("-r", 1)[0] for b in broken}),
    }

    out["answer_keys"] = _answer_keys(papers, changed, all_vanished)
    out["reader_runs"] = _reader_runs(papers, changed, all_vanished)
    out["demo_cases"] = _demo_cases(papers, changed)
    out["line_number_citations_in_committed_files"] = _number_citations(papers, changed)
    return {
        "line_documents_changed": docs_changed,
        "line_ids_vanished_from_changed_papers": len(all_vanished),
        "consumers": out,
    }


def _answer_keys(papers: dict[str, Paper], changed: set[str], vanished: set[str]) -> dict:
    q = config.QUERIES
    out = {}
    for name in ("kind_a_lookup", "kind_b_absence"):
        key = pd.read_csv(q / f"{name}.csv", dtype=str)
        key = key[key["pmcid"].isin(changed)]
        ids = gone = hit = 0
        for pmcid, value in zip(key["pmcid"], key["evidence_line_ids"], strict=True):
            mine = _ids(value)
            lost = sum(1 for i in mine if lines.resolve_id(papers[pmcid].doc(False), i) is None)
            ids, gone, hit = ids + len(mine), gone + lost, hit + bool(lost)
        out[name] = {
            "questions_in_changed_papers": int(len(key)),
            "evidence_line_ids": ids,
            "no_longer_resolving": gone,
            "questions_with_an_unresolved_id": hit,
        }
    d = pd.read_csv(q / "kind_d_mechanism.csv", dtype=str)
    seeds = d[d["seed_pmcid"].isin(changed)]
    seed_gone = sum(
        1
        for p, i in zip(seeds["seed_pmcid"], seeds["seed_line_id"], strict=True)
        if lines.resolve_id(papers[p].doc(False), i) is None
    )
    acceptable = [i for v in d["acceptable_line_ids"] for i in _ids(v)]
    hit = [v for v in d["acceptable_line_ids"] if set(_ids(v)) & vanished]
    out["kind_d_mechanism"] = {
        "questions": int(len(d)),
        "seed_lines_in_changed_papers": int(len(seeds)),
        "seed_lines_no_longer_resolving": seed_gone,
        "acceptable_line_ids": len(acceptable),
        "acceptable_ids_vanished": sum(1 for i in acceptable if i in vanished),
        "questions_with_a_vanished_acceptable_id": len(hit),
    }
    return out


def _reader_runs(papers: dict[str, Paper], changed: set[str], vanished: set[str]) -> dict:
    out = {}
    for path in sorted(config.DATA_INTERIM.glob("runs/*/*.jsonl")):
        if path.name not in ("answers.jsonl", "superseded.jsonl"):
            continue
        tokens = moved = answers_hit = delivered_gone = answers_delivered_hit = 0
        n = 0
        for raw in path.read_text().splitlines():
            if not raw.strip():
                continue
            rec = json.loads(raw)
            n += 1
            hit = False
            for pmcid, num in _CITE.findall(rec.get("text") or ""):
                if pmcid not in changed:
                    continue
                tokens += 1
                if _moved(papers[pmcid].doc(True), papers[pmcid].doc(False), int(num)):
                    moved += 1
                    hit = True
            answers_hit += hit
            gone = [i for i in rec.get("line_ids") or () if i in vanished]
            delivered_gone += len(gone)
            answers_delivered_hit += bool(gone)
        if tokens or delivered_gone:
            out[f"{path.parent.name}/{path.name}"] = {
                "answers": n,
                "cited_lines_in_changed_papers": tokens,
                "cited_line_numbers_now_pointing_elsewhere": moved,
                "answers_with_such_a_citation": answers_hit,
                "delivered_line_ids_vanished": delivered_gone,
                "answers_whose_delivered_lines_lost_an_id": answers_delivered_hit,
            }
    return out


def _moved(old: lines.LinedDoc, new: lines.LinedDoc, n: int) -> bool:
    a, b = lines.resolve(old, n), lines.resolve(new, n)
    return a is not None and (b is None or a.line_id != b.line_id)


def _number_citations(papers: dict[str, Paper], changed: set[str]) -> dict:
    """Every `PMC…:Lnn` written into a committed file, against the document it was read from:
    the origin reader's `load_doc` for the origin files, `build_lines` for everything else."""
    patterns = {
        "origin": [
            "data/interim/origin/answers.jsonl",
            "data/interim/origin/hand_check*.jsonl",
            "out/tables/sample_origin.csv",
            "out/tables/sample_origin_stats.json",
            "out/review/REVIEW.md",
        ],
        "canonical": ["out/demo/cases/*.md", "out/review/audit_sample.csv"],
    }
    out = {}
    for kind, globs in patterns.items():
        for pattern in globs:
            for path in sorted(config.ROOT.glob(pattern)):
                total = moved = findable = 0
                for pmcid, num in _CITE.findall(path.read_text(errors="replace")):
                    if pmcid not in changed:
                        continue
                    x = papers[pmcid]
                    old = x.origin_doc(True) if kind == "origin" else x.doc(True)
                    new = x.origin_doc(False) if kind == "origin" else x.doc(False)
                    total += 1
                    if _moved(old, new, int(num)):
                        moved += 1
                        was = lines.resolve(old, int(num))
                        findable += lines.resolve_id(new, was.line_id) is not None
                if total:
                    out[str(path.relative_to(config.ROOT))] = {
                        "document": kind,
                        "citations_in_changed_papers": total,
                        "now_pointing_elsewhere": moved,
                        "of_which_the_old_line_id_still_exists": findable,
                    }
    return out


def _demo_cases(papers: dict[str, Paper], changed: set[str]) -> dict:
    table = pd.read_csv(config.OUT_TABLES / "d1_zeta_table.csv")
    wanted = {c.pmcid for c in demo_cases.CASES}
    old = Corpus(docs={p: papers[p].doc(True) for p in wanted if p in papers}, table=table)
    new = Corpus(docs={p: papers[p].doc(False) for p in wanted if p in papers}, table=table)

    def failing(corpus: Corpus) -> list[str]:
        return [r for c in demo_cases.CASES if (r := demo_cases.verify(c, table, corpus))]

    return {
        "cases_in_changed_papers": sorted(
            f"{c.nn}-{c.slug}" for c in demo_cases.CASES if c.pmcid in changed
        ),
        "checks_failing_before": failing(old),
        "checks_failing_after": failing(new),
    }


def estimate_gain(papers: dict[str, Paper], changed_rows: list[str], table: pd.DataFrame) -> dict:
    """Upper bound. A regex hit in newly visible text is a candidate, not a value: it may
    describe another experiment, a stock solution or the cell culture."""
    new_text = {}
    for p in changed_rows:
        x = papers[p]
        new_text[p] = "\n".join(sorted(_visible(x.pieces(False)) - _visible(x.pieces(True))))
    found = {p: candidates_in(t) for p, t in new_text.items()}
    rows = table[table["pmcid"].isin(changed_rows)]
    per_condition = {}
    for cond in CONDITIONS:
        unreported = rows[~rows[f"{cond}_reported"].astype(bool)]
        with_candidate = unreported[unreported["pmcid"].map(lambda p, c=cond: found[p][c])]
        per_condition[cond] = {
            "rows_unreported": int(len(unreported)),
            "rows_with_a_candidate_in_new_text": int(len(with_candidate)),
            "papers_unreported": int(unreported["pmcid"].nunique()),
            "papers_with_a_candidate": int(with_candidate["pmcid"].nunique()),
        }
    incomplete = rows[~rows["conditions_complete"].astype(bool)]
    could = [
        r
        for r in incomplete.to_dict(orient="records")
        if all(r[f"{c}_reported"] or found[r["pmcid"]][c] for c in CONDITIONS)
    ]
    return {
        "label": "UPPER-BOUND ESTIMATE by regex over lines newly visible under the cap",
        "rows_in_changed_papers": int(len(rows)),
        "fully_conditioned_now_all_rows": int(table["conditions_complete"].astype(bool).sum()),
        "all_rows": int(len(table)),
        "fully_conditioned_now_in_changed_papers": int(len(rows) - len(incomplete)),
        "per_condition": per_condition,
        "rows_that_could_become_fully_conditioned": len(could),
        "papers_of_those_rows": len({r["pmcid"] for r in could}),
    }


def reextraction_facts(records: dict, changed_rows: list[str], papers: dict[str, Paper]) -> dict:
    recs = [records[p] for p in changed_rows]
    by_run: dict[str, str] = {}
    gaps: dict[str, list[float]] = defaultdict(list)
    for manifest in sorted(config.DATA_INTERIM.glob("runs/*/assignments.jsonl")):
        claims = [json.loads(x) for x in manifest.read_text().splitlines() if x.strip()]
        per_worker: dict[str, list[dict]] = defaultdict(list)
        for c in claims:
            per_worker[c["worker"]].append(c)
            for p in c["pmcids"]:
                by_run[p] = manifest.parent.name
        for ws in per_worker.values():
            ws.sort(key=lambda c: c["claimed_at"])
            for a, b in zip(ws, ws[1:], strict=False):
                start, end = (datetime.fromisoformat(x["claimed_at"]) for x in (a, b))
                gap = (end - start).total_seconds()
                for p in b["pmcids"]:
                    gaps[p].append(gap / len(b["pmcids"]))
    timed = [g for p in changed_rows for g in gaps.get(p, [])]
    return {
        "records": len(recs),
        "model": dict(Counter(r["model"] for r in recs).most_common()),
        "prompt_sha256": dict(Counter(r["prompt_sha256"][:12] for r in recs).most_common()),
        "brief_sha256": dict(
            Counter((r["brief_sha256"] or "none")[:12] for r in recs).most_common()
        ),
        "rows": sum(len(r["measurements"]) for r in recs),
        "records_store_duration_or_billed_tokens": False,
        "papers_in_a_run_with_assignments": dict(
            Counter(by_run.get(p, "none (legacy, no run manifest)") for p in changed_rows)
        ),
        "seconds_between_ingests_same_worker": {
            "label": "ESTIMATE: gap to the same worker's previous ingest, idle time included",
            "papers_timed": sum(1 for p in changed_rows if gaps.get(p)),
            "median_s": round(statistics.median(timed), 1) if timed else None,
        },
        "input_approx_tokens_new_capped_text": sum(
            jats.approx_tokens(jats.extraction_text(papers[p].new, max_tokens=zeta.MAX_TOKENS))
            for p in changed_rows
        ),
        "input_approx_tokens_stored_on_records": sum(r["extraction_tokens"] for r in recs),
    }


def main() -> int:
    table = pd.read_csv(config.OUT_TABLES / "d1_zeta_table.csv")
    with_rows = set(table["pmcid"])
    records = {
        (r := json.loads(x))["pmcid"]: r
        for x in (config.DATA_INTERIM / "extractions.jsonl").read_text().splitlines()
        if x.strip()
    }
    papers = {p.stem: Paper(p) for p in sorted(config.EPMC_XML_DIR.glob("*.xml"))}
    missing = sorted(with_rows - set(papers))
    if missing:
        raise SystemExit(f"no XML for {len(missing)} papers with rows, e.g. {missing[:3]}")

    parse = measure_parse(papers, with_rows, records)
    changed_rows = parse["changed_pmcids_with_rows"]
    changed_all = {p for p, x in papers.items() if x.changed}
    result = {
        "MEASURED": {
            "parse": parse,
            "extraction_text": measure_text(papers, changed_rows),
            "line_addresses": measure_addresses(papers, changed_all, table),
            "origin_repair_after_fix": {
                "papers_with_rows_methods_lost_old": sum(
                    1 for p in with_rows if _old_methods_lost(papers[p].raw)
                ),
                "papers_with_rows_methods_lost_new": sum(
                    1 for p in with_rows if _methods_lost(papers[p].raw)
                ),
                "papers_with_rows_where_load_doc_appends_old": sum(
                    1 for p in with_rows if _appends(papers[p].old, papers[p].raw)
                ),
                "papers_with_rows_where_load_doc_appends_new": sum(
                    1 for p in with_rows if _appends(papers[p].new, papers[p].raw)
                ),
                "new_appends_by_new_methods_source": dict(
                    Counter(
                        papers[p].new.methods_source
                        for p in with_rows
                        if _appends(papers[p].new, papers[p].raw)
                    )
                ),
            },
            "reextraction_records": reextraction_facts(records, changed_rows, papers),
        },
        "ESTIMATE": estimate_gain(papers, changed_rows, table),
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    summary = {k: v for k, v in parse.items() if k != "changed_pmcids_with_rows"}
    print(json.dumps({"parse": summary}, indent=2))
    text = {k: v for k, v in result["MEASURED"]["extraction_text"].items() if k != "per_paper"}
    print(json.dumps({"extraction_text": text}, indent=2))
    rest = ("line_addresses", "origin_repair_after_fix", "reextraction_records")
    rest = {k: result["MEASURED"][k] for k in rest}
    print(json.dumps(rest, indent=2))
    print(json.dumps({"ESTIMATE": result["ESTIMATE"]}, indent=2))
    print(f"-> {OUT.relative_to(config.ROOT)}")
    return 0


def _old_methods_lost(raw: bytes) -> bool:
    """`_methods_lost` as it answered with the old finder."""
    with _old_finder():
        return _methods_lost(raw)


if __name__ == "__main__":
    raise SystemExit(main())
