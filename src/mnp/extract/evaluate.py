"""Precision/recall of the extraction against the gold set Claude annotated.

Row level: predictions and gold rows are matched on (pmcid, particle name,
medium class); numeric fields then score TP/FP/FN under per-field tolerances.
None–None is never a true positive — it is simply not counted, otherwise an
extractor that reports nothing looks perfect on every unreported condition.

Paper level: for each *_reported boolean, a paper is positive if any of its
rows is. This is the level the talk's headline numbers live at.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

ROW_FIELDS = ("value", "ionic_strength_mM", "pH", "temperature_C")
BOOLEANS = (
    "medium_reported",
    "ionic_strength_reported",
    "pH_reported",
    "temperature_reported",
    "instrument_reported",
    "conditions_complete",
    "medium_matches_exposure",
)
NAME_THRESHOLD = 0.8
_UNITS = re.compile(r"\b(nm|µm|μm|um|mm)\b", re.IGNORECASE)


def within_tolerance(field: str, a: float, b: float) -> bool:
    d = abs(a - b)
    if field == "value":
        return d <= max(1.0, 0.05 * abs(b))
    if field == "pH":
        return d <= 0.1 + 1e-9
    if field == "temperature_C":
        return d <= 1.0 + 1e-9
    if field == "ionic_strength_mM":
        return d <= 0.10 * abs(b) + 1e-9
    return a == b


def _norm_name(s: str) -> str:
    s = _UNITS.sub(" ", s.lower())
    return re.sub(r"[\s_\-]+", " ", s).strip()


def name_similarity(a, b) -> float:
    """1.0 when either name is missing or one contains the other; else SequenceMatcher."""
    if _isnull(a) or _isnull(b):
        return 1.0
    a, b = _norm_name(str(a)), _norm_name(str(b))
    if not a or not b or a in b or b in a:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _isnull(x) -> bool:
    if x is None:
        return True
    try:
        return bool(pd.isna(x))
    except (TypeError, ValueError):
        return False


@dataclass
class MatchResult:
    matched: list[tuple[str, str]] = field(default_factory=list)
    unmatched_pred: list[str] = field(default_factory=list)
    unmatched_gold: list[str] = field(default_factory=list)


def _measurement_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Rows that report a measurement: a number, a verbatim range/figure-only text, or at
    least a named quantity. Gold 'no measurement' placeholders carry none of these."""
    mask = pd.Series(False, index=df.index)
    for col in ("value", "value_text", "quantity"):
        if col in df.columns:
            mask |= df[col].notna()
    return df[mask]


def match_rows(pred: pd.DataFrame, gold: pd.DataFrame) -> MatchResult:
    pred, gold = _measurement_rows(pred), _measurement_rows(gold)
    result = MatchResult()
    for pmcid in sorted(set(pred.pmcid) | set(gold.pmcid)):
        p = pred[pred.pmcid == pmcid]
        g = gold[gold.pmcid == pmcid]
        pairs = []
        for _, pr in p.iterrows():
            for _, gr in g.iterrows():
                if not _isnull(pr.get("medium_class")) and not _isnull(gr.get("medium_class")):
                    if pr["medium_class"] != gr["medium_class"]:
                        continue
                sim = name_similarity(pr.get("particle_name"), gr.get("particle_name"))
                if sim >= NAME_THRESHOLD:
                    same_value = (
                        not _isnull(pr.get("value"))
                        and not _isnull(gr.get("value"))
                        and within_tolerance("value", float(pr["value"]), float(gr["value"]))
                    )
                    pairs.append((sim + (0.5 if same_value else 0.0), pr["row_id"], gr["row_id"]))
        pairs.sort(key=lambda t: -t[0])
        used_p: set[str] = set()
        used_g: set[str] = set()
        for _, prid, grid in pairs:
            if prid in used_p or grid in used_g:
                continue
            used_p.add(prid)
            used_g.add(grid)
            result.matched.append((prid, grid))
        result.unmatched_pred.extend(r for r in p["row_id"] if r not in used_p)
        result.unmatched_gold.extend(r for r in g["row_id"] if r not in used_g)
    return result


@dataclass
class Score:
    level: str
    field: str
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    @property
    def n(self) -> int:
        return self.tp + self.fp + self.fn

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else float("nan")

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else float("nan")

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        if math.isnan(p) or math.isnan(r) or p + r == 0:
            return float("nan")
        return 2 * p * r / (p + r)

    @property
    def accuracy(self) -> float:
        total = self.tp + self.fp + self.fn + self.tn
        return (self.tp + self.tn) / total if total else float("nan")

    def as_dict(self) -> dict:
        d = asdict(self)
        d.update(n=self.n, precision=self.precision, recall=self.recall, f1=self.f1)
        d["accuracy"] = self.accuracy
        return d


def row_level(pred: pd.DataFrame, gold: pd.DataFrame) -> list[Score]:
    pred, gold = _measurement_rows(pred), _measurement_rows(gold)
    m = match_rows(pred, gold)
    p_by = pred.set_index("row_id")
    g_by = gold.set_index("row_id")
    scores = {f: Score("row", f) for f in ROW_FIELDS}
    for prid, grid in m.matched:
        pr, gr = p_by.loc[prid], g_by.loc[grid]
        for f in ROW_FIELDS:
            pv, gv = pr.get(f), gr.get(f)
            if _isnull(pv) and _isnull(gv):
                continue
            if _isnull(pv):
                scores[f].fn += 1
            elif _isnull(gv):
                scores[f].fp += 1
            elif within_tolerance(f, float(pv), float(gv)):
                scores[f].tp += 1
            else:
                scores[f].fp += 1
                scores[f].fn += 1
    for prid in m.unmatched_pred:
        for f in ROW_FIELDS:
            if not _isnull(p_by.loc[prid].get(f)):
                scores[f].fp += 1
    for grid in m.unmatched_gold:
        for f in ROW_FIELDS:
            if not _isnull(g_by.loc[grid].get(f)):
                scores[f].fn += 1
    return list(scores.values())


def _has_digit(x) -> bool:
    return not _isnull(x) and any(ch.isdigit() for ch in str(x))


def derive_booleans(df: pd.DataFrame) -> pd.DataFrame:
    """The *_reported booleans from raw columns, unless the frame already has them."""
    df = df.copy()
    # the gold CSV uses the plan's column names; map them onto the table's
    for alias, canonical in (
        ("I_reported", "ionic_strength_reported"),
        ("T_reported", "temperature_reported"),
    ):
        if alias in df.columns and canonical not in df.columns:
            df[canonical] = df[alias]
    get = lambda col: df[col] if col in df.columns else pd.Series([None] * len(df), index=df.index)  # noqa: E731
    if "medium_reported" not in df.columns:
        df["medium_reported"] = get("medium_text").map(lambda v: not _isnull(v))
    if "ionic_strength_reported" not in df.columns:
        df["ionic_strength_reported"] = get("ionic_strength_mM").map(lambda v: not _isnull(v))
    if "pH_reported" not in df.columns:
        df["pH_reported"] = get("pH").map(lambda v: not _isnull(v)) | get("pH_text").map(_has_digit)
    if "temperature_reported" not in df.columns:
        df["temperature_reported"] = get("temperature_C").map(lambda v: not _isnull(v)) | get(
            "temperature_qualifier"
        ).map(lambda v: not _isnull(v))
    if "instrument_reported" not in df.columns:
        df["instrument_reported"] = get("instrument").map(lambda v: not _isnull(v))
    if "conditions_complete" not in df.columns:
        df["conditions_complete"] = (
            df["medium_reported"]
            & df["ionic_strength_reported"]
            & df["pH_reported"]
            & df["temperature_reported"]
            & df["instrument_reported"]
        )
    if "medium_matches_exposure" not in df.columns:
        df["medium_matches_exposure"] = None
    for b in BOOLEANS:
        df[b] = df[b].map(lambda v: None if _isnull(v) else bool(v))
    return df


def _paper_flags(df: pd.DataFrame) -> dict[str, dict[str, bool | None]]:
    df = derive_booleans(_measurement_rows(df))
    out: dict[str, dict[str, bool | None]] = {}
    for pmcid, grp in df.groupby("pmcid"):
        flags = {}
        for b in BOOLEANS:
            vals = [v for v in grp[b] if v is not None]
            flags[b] = any(vals) if vals else None
        out[str(pmcid)] = flags
    return out


def paper_level(pred: pd.DataFrame, gold: pd.DataFrame) -> list[Score]:
    p_flags, g_flags = _paper_flags(pred), _paper_flags(gold)
    scores = {b: Score("paper", b) for b in BOOLEANS}
    for pmcid in sorted(set(p_flags) | set(g_flags)):
        for b in BOOLEANS:
            pv = p_flags.get(pmcid, {}).get(b)
            gv = g_flags.get(pmcid, {}).get(b)
            if pmcid not in p_flags:
                pv = False
            if pmcid not in g_flags:
                gv = False
            if pv is None or gv is None:
                continue
            if pv and gv:
                scores[b].tp += 1
            elif pv and not gv:
                scores[b].fp += 1
            elif gv and not pv:
                scores[b].fn += 1
            else:
                scores[b].tn += 1
    return list(scores.values())


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return float("nan"), float("nan")
    p = k / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def cohens_kappa(a: list[bool], b: list[bool]) -> float:
    n = len(a)
    if n == 0 or n != len(b):
        return float("nan")
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


def audit_kappa(gold: pd.DataFrame) -> dict:
    """κ between the first annotator and any second annotator on the same row_id."""
    out = {"n_audited_rows": 0, "kappa": {}}
    if "annotator" not in gold.columns or "row_id" not in gold.columns:
        return out
    g = derive_booleans(gold)
    pairs: list[tuple[pd.Series, pd.Series]] = []
    for _, grp in g.groupby("row_id"):
        annotators = list(dict.fromkeys(grp["annotator"].dropna()))
        if len(annotators) < 2:
            continue
        first = grp[grp.annotator == annotators[0]].iloc[0]
        second = grp[grp.annotator == annotators[1]].iloc[0]
        pairs.append((first, second))
    out["n_audited_rows"] = len(pairs)
    for b in BOOLEANS[:5]:
        a = [bool(f[b]) for f, _ in pairs]
        c = [bool(s[b]) for _, s in pairs]
        out["kappa"][b] = cohens_kappa(a, c)
    return out


def evaluate(pred: pd.DataFrame, gold: pd.DataFrame) -> dict:
    gold_papers = set(gold.pmcid)
    # Precision and recall exist only where there is ground truth. A prediction on a
    # paper nobody annotated is neither right nor wrong, and counting it as a false
    # positive drove precision to 0.05 on a corpus seven times the size of the gold set.
    outside = int(pred.loc[~pred["pmcid"].isin(gold_papers), "pmcid"].nunique())
    pred = pred[pred["pmcid"].isin(gold_papers)]
    gold_with = set(_measurement_rows(gold).pmcid)
    pred_with = set(_measurement_rows(pred).pmcid)
    gold_without = gold_papers - gold_with
    rows = row_level(pred, gold)
    papers = paper_level(pred, gold)
    by = {s.field: s for s in papers}
    return {
        "papers": {
            "gold": len(gold_papers),
            "pred": len(set(pred.pmcid)),
            "pred_outside_gold": outside,
            "gold_without_measurements": len(gold_without),
            "pred_without_measurements_agreeing": len(gold_without - pred_with),
        },
        "row": [s.as_dict() for s in rows],
        "paper": [s.as_dict() for s in papers],
        "headline": {
            "conditions_complete_accuracy": by["conditions_complete"].accuracy,
            "medium_matches_exposure_accuracy": by["medium_matches_exposure"].accuracy,
        },
        "audit": audit_kappa(gold),
    }


def write_precision_recall(report: dict, path: Path) -> Path:
    rows = [dict(r) for r in report["row"]] + [dict(r) for r in report["paper"]]
    df = pd.DataFrame(rows)[
        ["level", "field", "tp", "fp", "fn", "tn", "n", "precision", "recall", "f1", "accuracy"]
    ]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path
