"""The demo cases — one paper per failure mode the corpus actually contains, and one pair.

Each `Case` pins a paper **and** a check that proves the paper still shows its mode against the
live `d1_zeta_table.csv`. `verify` runs that check; when it fails, `docs/DESIGN_2026-09-28_demo.md`
says to replace the paper with the best-fitting one from the table, which is what happened here
for cases 03 and 01 — see the note above `CASES`. Case 14's mode only exists across two papers,
so it also pins the pair of rows it is built on.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd

from mnp.corpus import lines as corpus_lines
from mnp.demo.walk import BUFFER_RE, CONDUCTIVITY_RE
from mnp.eval import comparability as comp
from mnp.eval.cells import Corpus

#: (pmcid, table, corpus) -> whether the paper's rows still show the case's mode.
Check = Callable[[str, pd.DataFrame, Corpus], bool]


def _str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def _float(value: Any) -> float | None:
    text = _str(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _rows(table: pd.DataFrame, pmcid: str) -> list[dict[str, Any]]:
    return table[table["pmcid"] == pmcid].to_dict(orient="records")


@dataclass(frozen=True)
class Case:
    nn: str
    slug: str
    pmcid: str
    mode: str
    why: str
    check: Check
    #: The two row ids a case is built on when its mode only shows across papers.
    pair: tuple[str, str] | None = None

    @property
    def pmcids(self) -> tuple[str, ...]:
        """Every paper the case shows: its own first, then the other side of its pair."""
        if self.pair is None:
            return (self.pmcid,)
        # row ids are "<pmcid>-r<n>" (mnp.extract.zeta)
        others = sorted({row_id.rsplit("-r", 1)[0] for row_id in self.pair} - {self.pmcid})
        return (self.pmcid, *others)


def _comparable_pairs(table: pd.DataFrame) -> list[comp.PairSpec]:
    rows = [comp.ZetaRow.from_mapping(r) for r in table.to_dict(orient="records")]
    return comp.comparable_census(rows)


# -- the checks, one per case, each literally the design table's own words ------------------


def _check_01_fully_conditioned(pmcid: str, table: pd.DataFrame, corpus: Corpus) -> bool:
    """>=1 pair of this paper's rows -- both of them its own -- is in the comparable census."""
    return any(spec.a.pmcid == spec.b.pmcid == pmcid for spec in _comparable_pairs(table))


def _check_02_one_particle_three_media(pmcid: str, table: pd.DataFrame, corpus: Corpus) -> bool:
    """>=3 rows of one particle, >=3 distinct medium_class, zeta spread >= 50 mV."""
    rows = [r for r in _rows(table, pmcid) if _str(r.get("quantity")) == "zeta_potential"]
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (
            _str(row.get("material")),
            _str(row.get("functionalisation")),
            _str(row.get("particle_name")),
        )
        groups.setdefault(key, []).append(row)
    for members in groups.values():
        if len(members) < 3:
            continue
        classes = {_str(row.get("medium_class")) for row in members}
        values = [v for row in members if (v := _float(row.get("value"))) is not None]
        if len(classes) >= 3 and values and (max(values) - min(values)) >= 50.0:
            return True
    return False


def _check_03_conductivity_not_ionic_strength(
    pmcid: str, table: pd.DataFrame, corpus: Corpus
) -> bool:
    """medium_text matches conductivity (uS, mS/cm, "conductiv"); ionic_strength_reported False."""
    rows = _rows(table, pmcid)
    matched = [row for row in rows if CONDUCTIVITY_RE.search(_str(row.get("medium_text")))]
    return bool(matched) and all(not bool(row.get("ionic_strength_reported")) for row in matched)


def _check_04_derived_from_composition(pmcid: str, table: pd.DataFrame, corpus: Corpus) -> bool:
    """>=1 row with ionic_strength_source == inferred_from_named_salt."""
    rows = _rows(table, pmcid)
    return any(_str(row.get("ionic_strength_source")) == "inferred_from_named_salt" for row in rows)


def _check_05_buffer_named_only(pmcid: str, table: pd.DataFrame, corpus: Corpus) -> bool:
    """medium_text names PBS/HEPES/Tris; ionic_strength_reported False."""
    rows = _rows(table, pmcid)
    matched = [row for row in rows if BUFFER_RE.search(_str(row.get("medium_text")))]
    return bool(matched) and all(not bool(row.get("ionic_strength_reported")) for row in matched)


def _check_06_biological_medium(pmcid: str, table: pd.DataFrame, corpus: Corpus) -> bool:
    """>=10 rows with medium_class == culture_medium."""
    rows = _rows(table, pmcid)
    return sum(1 for row in rows if _str(row.get("medium_class")) == "culture_medium") >= 10


def _check_07_incubation_not_measurement_temperature(
    pmcid: str, table: pd.DataFrame, corpus: Corpus
) -> bool:
    """temperature_reported False on every row, and a line mentions incubation at 37 C."""
    rows = _rows(table, pmcid)
    if not rows or any(bool(row.get("temperature_reported")) for row in rows):
        return False
    doc = corpus.docs.get(pmcid)
    if doc is None:
        return False
    return any("37" in line.text and "incubat" in line.text.lower() for line in doc.lines)


def _check_08_room_temperature(pmcid: str, table: pd.DataFrame, corpus: Corpus) -> bool:
    """>=1 row with a non-null temperature_qualifier."""
    rows = _rows(table, pmcid)
    return any(_str(row.get("temperature_qualifier")) for row in rows)


def _check_09_mobility_reported(pmcid: str, table: pd.DataFrame, corpus: Corpus) -> bool:
    """>=1 row with quantity == electrophoretic_mobility."""
    rows = _rows(table, pmcid)
    return any(_str(row.get("quantity")) == "electrophoretic_mobility" for row in rows)


def _check_10_size_regime(pmcid: str, table: pd.DataFrame, corpus: Corpus) -> bool:
    """Two rows, one material+functionalisation+medium, sizes >=10x apart, opposite signs."""
    rows = [r for r in _rows(table, pmcid) if _str(r.get("quantity")) == "zeta_potential"]
    for i, a in enumerate(rows):
        for b in rows[i + 1 :]:
            if (
                _str(a.get("material")) != _str(b.get("material"))
                or _str(a.get("functionalisation")) != _str(b.get("functionalisation"))
                or _str(a.get("medium_text")) != _str(b.get("medium_text"))
            ):
                continue
            size_a, size_b = _float(a.get("size_measured_nm")), _float(b.get("size_measured_nm"))
            value_a, value_b = _float(a.get("value")), _float(b.get("value"))
            if None in (size_a, size_b, value_a, value_b) or min(size_a, size_b) <= 0:
                continue
            ratio = max(size_a, size_b) / min(size_a, size_b)
            if ratio >= 10.0 and (value_a > 0) != (value_b > 0):
                return True
    return False


#: A natural water named in the paper's own words. medium_class is a reader's label, and two
#: readings disagree on it often enough that the re-read filed case 11's effluents as `other`.
ENVIRONMENTAL_WATER_RE = re.compile(
    r"\b(?:effluent|wastewater|river|lake|seawater|groundwater)\b", re.IGNORECASE
)


def _check_11_environmental_matrix(pmcid: str, table: pd.DataFrame, corpus: Corpus) -> bool:
    """>=1 row whose medium_text names an environmental water, never its medium_class."""
    rows = _rows(table, pmcid)
    return any(ENVIRONMENTAL_WATER_RE.search(_str(row.get("medium_text"))) for row in rows)


def _check_12_weathered(pmcid: str, table: pd.DataFrame, corpus: Corpus) -> bool:
    """'aged', 'weather' or 'UV' in functionalisation or particle_name."""
    rows = _rows(table, pmcid)
    terms = ("aged", "weather", "uv")
    for row in rows:
        text = f"{_str(row.get('functionalisation'))} {_str(row.get('particle_name'))}".lower()
        if any(term in text for term in terms):
            return True
    return False


#: The two contradicting lines of PMC12598813 (FINDINGS.md E2c): methods says 5-30% w/v
#: (50-300 g/L), results says 0-30 mg/L for the same salinity series -- a 1000x-10000x gap.
CASE_13_METHODS_LINE_ID = "cf37d7ddb8101b4f"
CASE_13_RESULTS_LINE_ID = "60921ad810c8b672"


def _check_13_self_contradiction(pmcid: str, table: pd.DataFrame, corpus: Corpus) -> bool:
    """The two contradicting salt-concentration lines both resolve in the paper."""
    doc = corpus.docs.get(pmcid)
    if doc is None:
        return False
    return (
        corpus_lines.resolve_id(doc, CASE_13_METHODS_LINE_ID) is not None
        and corpus_lines.resolve_id(doc, CASE_13_RESULTS_LINE_ID) is not None
    )


#: The only cross-paper comparable pair on the 2026-10-03 table: one lab's 100 nm polystyrene
#: in 0.3 mM NaCl, pH 7.4, 25 C, Zetasizer Nano-ZS, in two papers three years apart.
CASE_14_PAIR = ("PMC10260929-r1", "PMC13298883-r1")
CASE_14_MIN_GAP_MV = 20.0


def _check_14_comparable_yet_apart(pmcid: str, table: pd.DataFrame, corpus: Corpus) -> bool:
    """The pinned pair is in the comparable census, this paper is one side, values >=20 mV apart."""
    first, second = CASE_14_PAIR
    if not any(row_id.startswith(f"{pmcid}-r") for row_id in CASE_14_PAIR):
        return False
    if not any((s.a.row_id, s.b.row_id) == CASE_14_PAIR for s in _comparable_pairs(table)):
        return False
    values = {
        _str(row.get("row_id")): _float(row.get("value"))
        for row in table[table["row_id"].isin(CASE_14_PAIR)].to_dict(orient="records")
    }
    a, b = values.get(first), values.get(second)
    return a is not None and b is not None and abs(a - b) >= CASE_14_MIN_GAP_MV


# -- the cases --------------------------------------------------------------------------------
#
# Case 03 was pinned to PMC13181784 in the design table. Its own rows never print a
# conductivity unit (uS/cm, mS/cm) anywhere in `medium_text` -- the check fails on the real
# data. PMC12673110 does: two media are named only by conductivity ("230 uS/cm (tap water)",
# "4,000 uS/cm (NaCl solution)"), on all four of its rows, and none of them reports an ionic
# strength. Replaced per the design file's own instruction ("pick the paper that best
# satisfies it ... and say so").
#
# Case 01 was pinned to PMC11099890. Its pairs were built on an "ionic strength" of "5 mM
# phosphate", a buffer concentration that rule R3 clears, so after the 2026-10-03 re-read it has
# none. PMC12955872 has a pair inside it (Martin, 2026-10-03).
#
# Case 14 is pinned to PMC13298883 rather than PMC10260929, though either is one side of its
# pair: PS-100 is unique in its paper, so kind A asks about the pair's own row, while
# PMC10260929-r1 shares its lookup key with r6 (same particle, same 0.3 mM NaCl, value not
# printed) and a kind A there would land off the pair. Neither paper has a kind B.

CASES: tuple[Case, ...] = (
    Case(
        nn="01",
        slug="fully-conditioned",
        pmcid="PMC12955872",
        mode="the rare success",
        why=(
            "Two PEGylated carboxylate polystyrene particles, nominally 20 and 40 nm, give -2.91 "
            "and -2.04 mV in the same 15x diluted PBS (~10 mM NaCl, pH 7.4) at 25 C on the same "
            "Zetasizer NanoZS: every condition is printed, and these two rows are one of only "
            "two fully comparable pairs in the 1,908-row corpus "
            "(`comparability.comparable_census`). Their measured sizes, 56.2 and 60.9 nm, put "
            "kappa*a at 9.2 and 10.0, so Henry's f differs by about 1% and the key can place "
            "both values on one scale. The paper's 100 nm sibling in the same medium (139.8 nm, "
            "kappa*a 23) is refused on exactly that axis: a fully conditioned row is necessary "
            "for a comparison, and still not enough once the particles sit in different "
            "conversion regimes."
        ),
        check=_check_01_fully_conditioned,
    ),
    Case(
        nn="02",
        slug="one-particle-three-media",
        pmcid="PMC10141840",
        mode="medium alone moves zeta 54 mV",
        why=(
            "One 1.14 micron polystyrene particle, one pH, one temperature, one instrument -- "
            "the only thing that changes across these three rows is the medium, and the zeta "
            "potential swings from about -68 mV in water to about -14 mV in a culture medium. "
            "None of the three rows states an ionic strength, and each fails for a different "
            "reason: water gives a conductivity, PBS names a buffer with no printed "
            "composition, and the culture medium's composition is not printed at all -- three "
            "unrelated causes for the same missing number."
        ),
        check=_check_02_one_particle_three_media,
    ),
    Case(
        nn="03",
        slug="conductivity-not-ionic-strength",
        pmcid="PMC12673110",
        mode="a number printed, not the one needed",
        why=(
            "Two aqueous media here are named by their conductivity rather than by a stated "
            "ionic strength: tap water at 230 uS/cm, a NaCl solution at 4,000 uS/cm. "
            "Conductivity and ionic strength are related, but only through an assumed ionic "
            "composition the paper never gives, so none of these rows converts to a usable "
            "ionic strength here. This is a paper printing a number, and that number still "
            "not being the one the standardisation walk needs."
        ),
        check=_check_03_conductivity_not_ionic_strength,
    ),
    Case(
        nn="04",
        slug="derived-from-composition",
        pmcid="PMC12312160",
        mode="ionic strength derived from a printed composition, never looked up",
        why=(
            "Every zeta row here states its dispersion as 10 mM HEPES plus either 1 mM or "
            "100 mM NaCl -- a printed composition, not a number copied from a lookup table. "
            "Because the paper gives the actual salt concentration, the walk can compute an "
            "ionic strength for each row and mark it derived, neither reported nor "
            "unreported. That distinction -- computed from what is on the page versus assumed "
            "from what a medium's name usually means -- is the entire reason the derived "
            "verdict exists."
        ),
        check=_check_04_derived_from_composition,
    ),
    Case(
        nn="05",
        slug="buffer-named-only",
        pmcid="PMC6981174",
        mode='"PBS" alone is not an ionic strength',
        why=(
            "All seven rows disperse the particle in some form of PBS, one of the "
            "best-known buffers in the field, which is exactly why it is dangerous here. The "
            "paper never prints PBS's composition, so its well-known nominal ionic strength "
            "is deliberately not looked up, and every row's ionic strength stays unreported. "
            "Knowing what a name usually means is not the same claim as the paper stating a "
            "number, and the walk only ever encodes the second."
        ),
        check=_check_05_buffer_named_only,
    ),
    Case(
        nn="06",
        slug="biological-medium",
        pmcid="PMC8719689",
        mode="corona: different particles converge",
        why=(
            "Seventy-two of this paper's ninety rows disperse particles in a culture medium, "
            "the setting where a protein corona forms around whatever material or "
            "functionalisation the particle started with. That is the mechanism the abstract "
            "calls convergence: chemically distinct particles arrive at a similar surface "
            "charge once serum proteins coat them, so the zeta value alone stops "
            "distinguishing the particle that produced it. None of these rows states an "
            "ionic strength either, for the same reason as the buffer case: a culture medium "
            "is a named liquid whose composition is not printed."
        ),
        check=_check_06_biological_medium,
    ),
    Case(
        nn="07",
        slug="incubation-not-measurement-temperature",
        pmcid="PMC4958399",
        mode="25/37 C incubation is not the measurement T",
        why=(
            "None of this paper's fifteen rows reports the temperature the zeta potential was "
            "actually measured at, even though the text says particles were incubated with "
            "plasma or serum proteins at 25 C and again at 37 C. Incubation temperature is "
            "not measurement temperature, and the walk never lets one stand in for the "
            "other, even when it is the only temperature the paper gives anywhere. The paper "
            "also runs its one particle through nine different protein and biofluid "
            "dispersions on a PBS background, so a lookup question about it has to name the "
            "particle to stay unambiguous."
        ),
        check=_check_07_incubation_not_measurement_temperature,
    ),
    Case(
        nn="08",
        slug="room-temperature",
        pmcid="PMC13520334",
        mode='"room temperature" counts as reported, flagged nominal',
        why=(
            'Thirty rows in this paper give their temperature only as "room temperature", '
            "never as a number. The walk still counts that as reported, because the paper did "
            "state something about temperature, but it flags the value nominal rather than "
            "treating a qualitative phrase as if it carried a number's precision. Medium and "
            "instrument are both named on the same rows, yet neither ionic strength nor pH is "
            "stated anywhere -- a nominal temperature is not a sign this paper under-reports "
            "everywhere, only exactly what it does not print."
        ),
        check=_check_08_room_temperature,
    ),
    Case(
        nn="09",
        slug="mobility-reported",
        pmcid="PMC11117817",
        mode="the measured quantity; zeta computable per model",
        why=(
            "Sixteen of this paper's thirty-two rows report electrophoretic mobility "
            "directly, the quantity an instrument actually measures before any model "
            "converts it to a zeta potential. Because the raw observable is on the page, "
            "recovering zeta only needs the conversion model and, where that is missing, an "
            "interval rather than a single number -- the opposite situation from a paper that "
            "prints an already-converted zeta and never says which model produced it. That is "
            "also why this case's own lookup question below asks about a mobility row: it is "
            "the number this paper actually measured."
        ),
        check=_check_09_mobility_reported,
    ),
    Case(
        nn="10",
        slug="size-regime",
        pmcid="PMC10145996",
        mode="50 nm vs 1 um PS-NH2: +24 vs -34 mV",
        why=(
            "Two rows, one particle chemistry -- amine-functionalised polystyrene -- in the "
            "same medium, and the only thing that changes is size: 50.7 nm carries a positive "
            "zeta potential, 955 nm carries a negative one. A roughly nineteen-fold change in "
            "size flips the sign of the surface charge, which is exactly the argument that a "
            "zeta value without its particle's size attached is not comparable to anything."
        ),
        check=_check_10_size_regime,
    ),
    Case(
        nn="11",
        slug="environmental-matrix",
        pmcid="PMC9318256",
        mode="effluent before/after treatment",
        why=(
            "Ten rows span five industrial effluents -- resin, paint, pharmaceutical, PVC and "
            "textile -- each sampled before and after in-house wastewater treatment, so the "
            "zeta potential belongs to whatever particles the effluent carried, in a matrix "
            "whose ionic strength and pH are never given. Comparing it with a lab-prepared "
            "dispersion elsewhere in the corpus would compare two kinds of experiment even where "
            "the numbers look alike. The case is recognised by what the paper prints "
            '("effluent"), not by medium_class: that field is a reader\'s label, and the '
            "re-read filed these rows under `other` where the earlier reading had "
            "environmental_water."
        ),
        check=_check_11_environmental_matrix,
    ),
    Case(
        nn="12",
        slug="weathered",
        pmcid="PMC11543686",
        mode="aging changes charge and has no field",
        why=(
            'Twenty-eight of this paper\'s forty-two rows carry "aged", "UV" or "weather" '
            "somewhere in their functionalisation or particle name, because ageing changes "
            "surface charge and this dataset has no field to record it -- not a duration, not "
            'a UV dose, nothing. A row that says "UV-aged PS" is not the same particle as '
            '"PS", and the standardisation walk has no condition that can tell the two apart '
            "the way it tells media or pH apart."
        ),
        check=_check_12_weathered,
    ),
    Case(
        nn="13",
        slug="self-contradiction",
        pmcid="PMC12598813",
        mode="one salt concentration printed twice, ~1e3-1e4x apart",
        why=(
            "The Methods section states the salinity series as 5% to 30% weight-by-volume -- "
            "50 to 300 g/L -- while the Results section states the same series as 0 to "
            "30 mg/L, a difference of three to four orders of magnitude. Both statements "
            "resolve to real lines in the paper, and every automated check that reads one "
            "sentence at a time passed this row, because the contradiction only exists across "
            "the two sentences. Four of this paper's fourteen rows leave the ionic strength "
            "unreported rather than picking a side, precisely because the dataset cannot "
            'silently choose which of two contradicting numbers the paper "really" meant.'
        ),
        check=_check_13_self_contradiction,
    ),
    Case(
        nn="14",
        slug="comparable-yet-apart",
        pmcid="PMC13298883",
        mode="comparable on all five conditions, yet 34 mV apart within one lab",
        why=(
            "Two papers from one laboratory (Bioelectrochemistry, University of Bialystok; "
            "every author of the 2026 paper also signs the 2023 one) measure nominally 100 nm "
            "plain polystyrene under the same printed conditions -- 0.3 mM NaCl, pH 7.4, 25 C, "
            "Zetasizer Nano-ZS -- and report -48.7 +/- 1.4 mV (Sigma-Aldrich 43302, "
            "119.5 nm measured) and -14.7 +/- 0.29 mV (supplier not stated, 158.1 nm measured). "
            "This is the only pair in the 1,908-row corpus that the comparability key passes "
            "across a paper boundary, and the 34 mV gap is not the conversion model's: neither "
            "paper names one, yet with f_m left open between Huckel and Smoluchowski on both "
            "rows the harmonised intervals still do not overlap. Five reported conditions make "
            'two rows comparable; they do not make two lots of "100 nm PS" the same particle.'
        ),
        check=_check_14_comparable_yet_apart,
        pair=CASE_14_PAIR,
    ),
)


def verify(case: Case, table: pd.DataFrame, corpus: Corpus) -> str | None:
    """`None` when `case.check` passes against the live data, a reason string when it doesn't."""
    try:
        ok = case.check(case.pmcid, table, corpus)
    except Exception as exc:  # noqa: BLE001 - a broken check is itself the failure to report
        return f"{case.nn}-{case.slug} ({case.pmcid}): check raised {exc!r}"
    if ok:
        return None
    return f"{case.nn}-{case.slug} ({case.pmcid}): check failed against the current table/corpus"
