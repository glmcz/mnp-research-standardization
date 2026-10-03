"""Deterministic parsing of what the model copied.

The model is told to copy strings as printed. Everything numeric — value, ±,
scientific notation, unit conversion, ionic strength from a named salt, Kelvin,
pH ranges — is parsed here, where it can be unit-tested, instead of trusted.
Every non-obvious decision leaves a flag on the row.
"""

from __future__ import annotations

import re

from pydantic import ValidationError

from mnp.schema.models import (
    UNITS_FOR_QUANTITY,
    Evidence,
    MeasurementConditions,
    MediumClass,
    Quantity,
    SurfaceMeasurement,
    Unit,
    ValueSource,
)

NULL_STRINGS = {
    "", "null", "none", "n/a", "na", "nd", "n.d.", "n.d", "not reported", "not stated",
    "not given", "unknown", "unreported", "-", "—", "–", "?", "nan",
}  # fmt: skip


def clean(raw) -> str | None:
    """Strip; map the model's many spellings of 'nothing' to None."""
    if raw is None or isinstance(raw, bool):
        return None
    if not isinstance(raw, str):
        return str(raw)
    s = raw.strip()
    return None if s.lower() in NULL_STRINGS else s


def _minus(s: str) -> str:
    """Every dash to an ASCII hyphen, for parsing only.

    The article text keeps its dashes; a number about to be parsed does not need to.
    """
    from mnp.corpus.jats import _DASHES, normalise_minus

    dashed = normalise_minus(s).translate(str.maketrans({d: "-" for d in _DASHES}))
    return _decimal_comma(dashed)


_NUM = r"-?\d+(?:\.\d+)?"
# A comma between digits is a decimal separator in much of Europe ("0,026 M"), but a
# comma is also a list separator ("[4,5]"). Convert only inside a single number, and
# only when the string has no period already doing that job.
_DECIMAL_COMMA = re.compile(r"(?<=\d),(?=\d{1,3}(?!\d))")


def _decimal_comma(s: str) -> str:
    """A comma inside one number becomes a decimal point. Citation lists are left alone."""
    if "." in s or "[" in s:
        return s
    return _DECIMAL_COMMA.sub(".", s)


# A hyphen between two numbers is a range. Scientific notation is checked first, so
# "10-8" inside "-3.2 x 10-8" is never mistaken for one.
# Every way a paper writes a range. "and" and the dashes were missing, so
# "between -34 mV and -48 mV" parsed as -34.0 with no flag — a fabricated precision,
# indistinguishable in the data from a paper that printed one number.
# A signed number, a unit the paper may repeat on the first endpoint, then the connector.
# Papers write "-34 to -48", "between -34 mV and -48 mV", "+21–+30" and "-21 ~ -30", and the
# unit in the middle is what defeated the simpler pattern.
_RNUM = r"[+-]?\d+(?:\.\d+)?"
_RANGE = re.compile(rf"({_RNUM})\s*(?:mV|mv|V)?\s*(?:to|and|[-–—~])\s*({_RNUM})")
_SCI = re.compile(rf"({_NUM})\s*[×xX*·]\s*10\s*\^?\s*\(?\s*(-?\d+)\s*\)?")
_EXP = re.compile(rf"({_NUM})[eE](-?\d+)")
# A standard deviation is a magnitude; one paper prints "-52.42 \u00b1 -0.26", and a
# pattern that refuses the sign skips the value and matches the deviation instead.
_PM = re.compile(rf"({_NUM})\s*(?:\u00b1|\+/-|\+-)\s*(-?\d+(?:\.\d+)?)")
_PLAIN = re.compile(_NUM)
# 约 / 约为 / 大约 / 左右 are "approximately" in Chinese, which the corpus contains. Unflagged,
# the paper's own hedge is silently recorded as an exact measurement.
_APPROX = re.compile(
    r"~|≈|\babout\b|\bapprox(?:\.|imately)?\b|\bca\.?\s|大约|约为|约|左右",
    re.IGNORECASE,
)
_ZETA_KW = re.compile(r"zeta|ζ|mobilit|surface charge|surface potential", re.IGNORECASE)


_INEQUALITY = re.compile(r"[<>≤≥]\s*-?\d")


def parse_number(raw) -> tuple[float | None, float | None, list[str]]:
    """(value, sd, flags). Handles ±, ×10^n, e-notation, ~, and ranges (rejected)."""
    if isinstance(raw, bool):
        return None, None, ["unparseable"]
    if isinstance(raw, int | float):
        return float(raw), None, []
    s = clean(raw)
    if s is None:
        return None, None, ["unparseable"]
    s = _minus(s)
    flags: list[str] = []
    if _INEQUALITY.search(s):
        # "<0 mV" means negative, not zero. Reading it as 0.0 would store a measurement
        # the paper never made, with the wrong sign into the bargain.
        return None, None, ["inequality_bound"]
    if _APPROX.search(s):
        flags.append("approx")
        s = _APPROX.sub(" ", s)
    m = _SCI.search(s) or _EXP.search(s)
    if m:
        return float(m.group(1)) * 10.0 ** int(m.group(2)), None, flags
    if _RANGE.search(s):
        return None, None, ["range"]
    m = _PM.search(s)
    if m:
        return float(m.group(1)), abs(float(m.group(2))), flags
    m = _PLAIN.search(s)
    if m:
        return float(m.group(0)), None, flags
    return None, None, ["unparseable"]


# -- units ------------------------------------------------------------------------

# Superscripts must become ASCII before anything looks for "10-8": a unit printed as
# "10⁻⁸ m²V⁻¹s⁻¹" once went unrecognised and every mobility in that paper was multiplied
# by 1e8 (-4.00 stored as -400).
_SUPERSCRIPTS = str.maketrans(
    {
        "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7",
        "⁸": "8", "⁹": "9", "⁻": "-", "⁺": "+",
    }
)  # fmt: skip
_UNIT_SUBS = (
    ("µ", "u"), ("μ", "u"), ("·", " "), ("×", "x"),
    ("−", "-"), ("–", "-"), ("—", "-"), ("‐", "-"), ("‑", "-"),
    ("^", ""), ("(", ""), (")", ""), ("**", ""),
)  # fmt: skip
# The canonical printed unit is 1e-8 m^2 V^-1 s^-1. A mobility unit is read as
# (printed exponent) + (area unit exponent), and the factor is what takes it to 1e-8:
#   m^2/Vs        ->  0 + 0  -> 1e8
#   10^-8 m^2/Vs  -> -8 + 0  -> 1
#   cm^2/Vs       ->  0 + -4 -> 1e4   (1 cm^2 = 1e-4 m^2)
#   10^-4 cm^2/Vs -> -4 + -4 -> 1     (the paper's own prefactor cancels the cm^2)
# Guessing from substrings instead of computing this stored one paper's 16 mobility rows
# 1e4 too small and another's 1e4 too large.
_EXPONENT = re.compile(r"(?:10|1e)\s*-\s*(\d+)")
_AREA_EXPONENT = (("cm2", -4), ("mm2", -6), ("um2", -12), ("m2", 0))


def _mobility_factor(compact: str, spaced: str) -> float | None:
    """Multiplier taking a value in this unit to units of 1e-8 m^2 V^-1 s^-1."""
    # A nonlinear mobility (cm^4 V^-3 s^-1) has no m^2 in it and so resolves to None
    # here: it is a different physical quantity and must never be relabelled as mobility.
    area = next((exp for name, exp in _AREA_EXPONENT if name in compact), None)
    if area is None:
        return None
    m = _EXPONENT.search(spaced)
    printed = -int(m.group(1)) if m else 0
    return 10.0 ** (printed + area + 8)


def normalise_unit(raw) -> tuple[Unit | None, float]:
    """(unit, factor): multiply the value by factor to express it in that unit."""
    s = clean(raw)
    if s is None:
        return None, 1.0
    s = s.translate(_SUPERSCRIPTS).lower()
    for a, b in _UNIT_SUBS:
        s = s.replace(a, b)
    s = re.sub(r"\s+", " ", s).strip()
    if s in {"mv", "millivolt", "millivolts"}:
        return Unit.mV, 1.0
    compact = s.replace(" ", "")
    # "(um/s)/(V/cm)" is the same practical unit written as a velocity per field
    # strength: um*cm/(V*s). Both spellings are already 1e-8 m2/V/s.
    if re.search(r"um/s.*v/cm|umsv?-?1.*vcm|ums-1/vcm", compact):
        return Unit.um_cm_per_Vs, 1.0
    if compact in {"um_cm_per_vs", "umcmpervs"}:  # the schema's own enum name
        return Unit.um_cm_per_Vs, 1.0
    if "umcm" in compact:  # the printed mixed unit um*cm/(V*s) is already 1e-8 m2/V/s
        return Unit.um_cm_per_Vs, 1.0
    if "v" in compact and "s" in compact:
        factor = _mobility_factor(compact, s)
        if factor is not None:
            return Unit.um_cm_per_Vs, factor
    return None, 1.0


_TRAILING_UNIT = re.compile(r"\d\s*([a-zA-Zµμ][^\d±]*)$")


def _unit_in_value(raw) -> str | None:
    if not isinstance(raw, str):
        return None
    m = _TRAILING_UNIT.search(raw.strip())
    return m.group(1).strip() if m else None


# -- conditions -------------------------------------------------------------------

_SALTS = {
    "nacl": 1.0, "kcl": 1.0, "licl": 1.0, "cscl": 1.0, "nh4cl": 1.0, "nano3": 1.0,
    "kno3": 1.0, "nabr": 1.0, "kbr": 1.0, "naf": 1.0,
    "cacl2": 3.0, "mgcl2": 3.0, "bacl2": 3.0, "srcl2": 3.0, "ca(no3)2": 3.0, "mg(no3)2": 3.0,
    "na2so4": 3.0, "k2so4": 3.0, "mgso4": 4.0, "caso4": 4.0,
}  # fmt: skip

# Papers that print a buffer recipe usually spell the salts out: the PBS tablet in
# PMC4958399 reads "0.0027 M potassium chloride, 0.137 M sodium chloride". Matching only
# the abbreviations made that composition unreadable to the pipeline while the gold
# annotator (Claude) computed 139.7 mM from it.
_SALT_WORDS = {
    "sodium chloride": 1.0, "potassium chloride": 1.0, "lithium chloride": 1.0,
    "caesium chloride": 1.0, "cesium chloride": 1.0, "ammonium chloride": 1.0,
    "sodium nitrate": 1.0, "potassium nitrate": 1.0, "sodium bromide": 1.0,
    "potassium bromide": 1.0, "sodium fluoride": 1.0,
    "calcium chloride": 3.0, "magnesium chloride": 3.0, "barium chloride": 3.0,
    "strontium chloride": 3.0, "calcium nitrate": 3.0, "magnesium nitrate": 3.0,
    "sodium sulfate": 3.0, "sodium sulphate": 3.0, "potassium sulfate": 3.0,
    "potassium sulphate": 3.0, "magnesium sulfate": 4.0, "magnesium sulphate": 4.0,
    "calcium sulfate": 4.0, "calcium sulphate": 4.0,
}  # fmt: skip
_SALT_ALIASES = {**_SALTS, **_SALT_WORDS}
SALT_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(_SALT_ALIASES, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)
_UM_RE = re.compile(rf"({_NUM})\s*(?:[µμu]M\b|[µμu]mol\s*/?\s*L)")
_MM_RE = re.compile(rf"({_NUM})\s*(?:mM\b|mmol\s*/?\s*L|mmol\s*L\s*-1)", re.IGNORECASE)
_M_RE = re.compile(rf"({_NUM})\s*(?:M\b|mol\s*/?\s*L)")
_SEGMENT = re.compile(r"[,;)(]|\band\b|\bplus\b|\+")


def _concentration_mM(s: str) -> float | None:
    """The first concentration in `s`, in mM, or None."""
    if m := _UM_RE.search(s):
        return float(m.group(1)) / 1000.0
    if m := _MM_RE.search(s):
        return float(m.group(1))
    if m := _M_RE.search(s):
        return float(m.group(1)) * 1000.0
    return None


# Between a concentration and the salt it belongs to there may be spaces, "of", or a bracket —
# nothing else. "5 mM HEPES" next to the word NaCl states HEPES's concentration, not NaCl's.
_BINDING = re.compile(r"^[\s(\[]*(?:of\s+)?$")


def _bound_salt(segment: str, start: int, end: int):
    """The salt this concentration actually names, or None if it names something else.

    `start`/`end` bracket the concentration in `segment`. The salt must sit immediately after
    it ("10 mM NaCl") or immediately before it ("NaCl (10 mM)"); anything in between means the
    number belongs to whatever *is* adjacent. A named salt merely present in the same sentence
    does not get to claim a number — that fabricated a 5 mM ionic strength for a solution whose
    NaCl concentration the paper never stated.
    """
    after = SALT_RE.search(segment, end)
    if after and _BINDING.match(segment[end : after.start()]):
        return after
    for before in SALT_RE.finditer(segment[:start]):
        if _BINDING.match(segment[before.end() : start].replace(",", "")):
            return before
    return None


def _salt_terms(s: str) -> list[tuple[float, float]]:
    """[(mM, valence factor)] for every 'concentration + named salt' pair in the string.

    Segmented so a recipe contributes one term per salt. Components without a named salt
    — "0.01 M phosphate buffer" — contribute nothing: their speciation depends on a pH the
    paper may not state, so the sum would be a guess rather than a derivation. A concentration
    bound to something other than a salt contributes nothing either, for the same reason.
    """
    terms: list[tuple[float, float]] = []
    for segment in _SEGMENT.split(s):
        for regex, scale in ((_UM_RE, 0.001), (_MM_RE, 1.0), (_M_RE, 1000.0)):
            if m := regex.search(segment):
                salt = _bound_salt(segment, m.start(), m.end())
                if salt:
                    terms.append((float(m.group(1)) * scale, _SALT_ALIASES[salt.group(1).lower()]))
                break
    return terms


# "IS" only in capitals: matched case-insensitively it took the English word "is" for the
# abbreviation, and a medium or quote that says "is" anywhere then kept its buffer
# concentration as an ionic strength (PMC8169765, PMC7378059).
IONIC_PHRASE = re.compile(r"(?i:ionic\s*strength|salinity)|\bIS\b")
# A buffer named beside a concentration. Its ionic strength depends on a speciation at the
# measured pH that papers rarely print, so the number is the buffer's, not the solution's.
BUFFER_RE = re.compile(
    r"buffer|phosphate|\bPBS\b|HEPES|\bTris|\bMES\b|MOPS|PIPES|citrate|acetate|"
    r"bicarbonate|borate|carbonate|glycine",
    re.IGNORECASE,
)
_BUFFER_REACH = 40  # characters either side of the concentration


def buffer_concentration(text: str, mM: float) -> bool:
    """Is `mM` printed in `text` as a buffer's concentration that the text never calls an ionic
    strength? A salt bound to the number ("10 mM NaCl in phosphate buffer") makes it a salt's;
    a paper that names its ionic strength keeps it, right or wrong (Martin, 2026-10-03)."""
    if IONIC_PHRASE.search(text):
        return False
    for regex, scale in ((_UM_RE, 0.001), (_MM_RE, 1.0), (_M_RE, 1000.0)):
        for m in regex.finditer(text):
            if abs(float(m.group(1)) * scale - mM) > 1e-6 * max(1.0, mM):
                continue
            if _bound_salt(text, m.start(), m.end()):
                continue
            # the window stops at a passage break: the next passage is another sentence
            left = text.rfind("||", 0, m.start())
            right = text.find("||", m.end())
            lo = max(m.start() - _BUFFER_REACH, left + 2 if left >= 0 else 0)
            hi = min(m.end() + _BUFFER_REACH, right if right >= 0 else len(text))
            if BUFFER_RE.search(text[lo:hi]):
                return True
    return False


def parse_ionic_strength(
    raw, from_medium: bool = False
) -> tuple[float | None, ValueSource, list[str]]:
    """mM from '10 mM', '0.15 M', '150 mmol/L', a named salt ('10 mM CaCl2' -> 30), or a
    printed composition ('0.0027 M KCl, 0.137 M NaCl' -> 139.7).

    A stated composition establishes the ionic strength when the sum follows directly from
    named species at stated concentrations (Martin's rule, 2026-09-13); such a value is
    marked `inferred_from_named_salt` and flagged `derived_from_composition`, never as a
    plainly reported number.

    `from_medium` reads a concentration out of a *medium description*, where a number is
    only an ionic strength if a named electrolyte or the words "ionic strength" say so.
    "FSW + BPA (10 µM)" names a co-exposure concentration, and recording it as a reported
    ionic strength is the worst error this pipeline can make: the study measures how often
    that condition goes unreported.
    """
    if isinstance(raw, int | float) and not isinstance(raw, bool):
        return float(raw), ValueSource.reported, []
    s = clean(raw)
    if s is None:
        return None, ValueSource.unreported, []
    s = _minus(s)
    terms = _salt_terms(s)
    if not terms:
        # the salt and its concentration may sit either side of a segment break — but they
        # must still be adjacent across it, or the number belongs to something else.
        for regex, scale in ((_UM_RE, 0.001), (_MM_RE, 1.0), (_M_RE, 1000.0)):
            if m := regex.search(s):
                if salt := _bound_salt(s, m.start(), m.end()):
                    terms = [(float(m.group(1)) * scale, _SALT_ALIASES[salt.group(1).lower()])]
                break
    if terms:
        total = sum(mM * factor for mM, factor in terms)
        flags = ["computed_from_salt"] if any(f != 1.0 for _, f in terms) else []
        if len(terms) > 1:
            flags.append("derived_from_composition")
        return total, ValueSource.inferred_from_named_salt, flags
    mM = _concentration_mM(s)
    if mM is None:
        return None, ValueSource.unreported, []
    if from_medium and not IONIC_PHRASE.search(s):
        return None, ValueSource.unreported, ["concentration_not_an_ionic_strength"]
    return mM, ValueSource.reported, []


_KELVIN = re.compile(r"(\d+(?:\.\d+)?)\s*K\b")
_CELSIUS = re.compile(
    rf"({_NUM})\s*(?:±\s*\d+(?:\.\d+)?\s*)?(?:°\s*C\b|℃|deg(?:rees)?(?:\s*C)?\b|C\b)",
    re.IGNORECASE,
)
_ROOM = re.compile(r"room\s*temp|\bRT\b|ambient", re.IGNORECASE)

# Only a temperature tied to the zeta measurement counts (Martin's rule, 2026-09-13).
# Incubation, exposure, culture, storage and digestion are separate conditions, even when
# the paper states no other temperature and even when temperature is its own variable:
# epsilon and eta convert mobility to zeta at the temperature of the *measurement*.
OTHER_STEP_RE = re.compile(
    r"incubat|pre-?treat|exposure|exposed|cultur|storage|stored|digest|oven|dry\s*bath|"
    r"overnight|prior\s+to|before\s+(?:the\s+)?(?:measure|analys|analyz)|shaking|agitat",
    re.IGNORECASE,
)


def parse_temperature(raw) -> tuple[float | None, str | None, list[str]]:
    """(°C, qualifier, flags). 'room temperature' is a reported, nominal temperature.

    A temperature belonging to another step is not reported at all: '37 °C incubation'
    yields None with `temperature_not_measurement`.
    """
    if isinstance(raw, int | float) and not isinstance(raw, bool):
        return float(raw), None, []
    s = clean(raw)
    if s is None:
        return None, None, []
    s = _minus(s)
    if OTHER_STEP_RE.search(s):
        return None, None, ["temperature_not_measurement"]
    if m := _KELVIN.search(s):
        return float(m.group(1)) - 273.15, None, ["kelvin_converted"]
    if m := _CELSIUS.search(s):
        return float(m.group(1)), None, []
    if _ROOM.search(s):
        return None, s, []
    if m := _PLAIN.search(s):
        return float(m.group(0)), None, ["unit_assumed_C"]
    return None, None, ["unparseable"]


_PH_RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:–|—|-|to|and)\s*(\d+(?:\.\d+)?)")
_PH_NUM = re.compile(r"(\d+(?:\.\d+)?)")


def parse_ph(raw) -> tuple[float | None, str | None]:
    """(pH, pH_text). A single number in [0, 14] is numeric; anything else is text."""
    if isinstance(raw, int | float) and not isinstance(raw, bool):
        return (float(raw), None) if 0 <= raw <= 14 else (None, str(raw))
    s = clean(raw)
    if s is None:
        return None, None
    s = _minus(s)
    if _PH_RANGE.search(s):
        return None, s
    if m := _PH_NUM.search(s):
        v = float(m.group(1))
        return (v, None) if 0 <= v <= 14 else (None, s)
    return None, s


_MEDIUM_RULES: tuple[tuple[MediumClass, re.Pattern], ...] = (
    (
        MediumClass.DI_water,
        re.compile(
            r"deioni[sz]ed|\bdi water|milli-?q|ultrapure|distilled|nanopure|type i water|"
            r"\bmq water|\bddh2o|\bdh2o|\bdd water",
            re.IGNORECASE,
        ),
    ),
    (
        MediumClass.buffer,
        re.compile(r"\bpbs\b|hepes|\btris\b|\bmops\b|\bmes\b|buffer|phosphate", re.IGNORECASE),
    ),
    (
        MediumClass.culture_medium,
        re.compile(
            r"\bdmem\b|\brpmi\b|\bmem\b|\bmedium\b|\bmedia\b|f-?12|ham'?s|\bbroth\b|\blb\b|"
            r"\bfbs\b|\bfcs\b",
            re.IGNORECASE,
        ),
    ),
    (
        MediumClass.biofluid,
        re.compile(
            r"plasma|serum|blood|saliva|urine|mucus|synovial|lung fluid|gastric|intestinal|"
            r"bile|lymph|milk|sweat",
            re.IGNORECASE,
        ),
    ),
    (
        MediumClass.environmental_water,
        re.compile(
            r"sea ?water|river|lake|tap water|wastewater|effluent|groundwater|estuar|marine|"
            r"freshwater|pond|rain|surface water|drinking water|natural water|stream",
            re.IGNORECASE,
        ),
    ),
    (
        MediumClass.salt_solution,
        re.compile(rf"{SALT_RE.pattern}|\bmM\b|\bM\b|electrolyte|saline|salt", re.IGNORECASE),
    ),
)


def infer_medium_class(text) -> MediumClass:
    s = clean(text)
    if s is None:
        return MediumClass.unreported
    for cls, pattern in _MEDIUM_RULES:
        if pattern.search(s):
            return cls
    return MediumClass.other


# -- quantity ---------------------------------------------------------------------


def parse_quantity(raw) -> Quantity | None:
    s = clean(raw)
    if s is None:
        return None
    s = s.lower()
    if "mobilit" in s or "epm" in s:
        return Quantity.electrophoretic_mobility
    if "zeta" in s or "ζ" in s or "potential" in s:
        return Quantity.zeta_potential
    return None


_SIZE_UNIT = re.compile(r"(nm|µm|μm|um|mm)\b", re.IGNORECASE)


def parse_size_nm(raw) -> float | None:
    v, _, flags = parse_number(raw)
    if v is None:
        return None
    if isinstance(raw, str) and (m := _SIZE_UNIT.search(raw)):
        unit = m.group(1).lower().replace("µ", "u").replace("μ", "u")
        v *= {"nm": 1.0, "um": 1000.0, "mm": 1e6}[unit]
    return v if v > 0 else None


def _bool(raw) -> bool | None:
    if isinstance(raw, bool):
        return raw
    s = clean(raw)
    if s is None:
        return None
    s = s.lower()
    if s in {"true", "yes", "y", "1"}:
        return True
    if s in {"false", "no", "n", "0"}:
        return False
    return None


# -- the row ----------------------------------------------------------------------


def _pick(raw: dict, cond: dict, *keys):
    for k in keys:
        for src in (cond, raw):
            if k in src and src[k] not in (None, ""):
                return src[k]
    return None


def coerce_measurement(raw: dict) -> tuple[SurfaceMeasurement | None, list[str]]:
    """Model output row → schema row. None with reasons when the value is unusable."""
    flags: list[str] = []
    cond = raw.get("conditions") if isinstance(raw.get("conditions"), dict) else {}

    value, sd, vflags = parse_number(raw.get("value"))
    value_text: str | None = None
    if value is None:
        raw_value = raw.get("value")
        quote = clean(raw.get("evidence_quote"))
        if "range" in vflags and isinstance(raw_value, str):
            # "-5 to -14": the paper reports a zeta potential, just not one number
            value_text = clean(_minus(raw_value))
            flags.append("value_is_range")
        elif raw_value in (None, "") and quote and _ZETA_KW.search(quote):
            # figure-only or "slightly negative": reported, conditions still count
            value_text = "not printed"
            flags.append("value_not_printed")
        else:
            flags.append("value_unparseable")
            flags.extend(f for f in vflags if f != "unparseable")
            return None, flags
    # "range"/"unparseable" described the failure to read a single number; once the
    # verbatim text is kept they are noise, not findings.
    if value_text is None:
        flags.extend(vflags)

    unit, factor = normalise_unit(raw.get("unit"))
    printed_unit = clean(raw.get("unit"))
    if unit is None:
        unit, factor = normalise_unit(_unit_in_value(raw.get("value")))
    if unit is None and printed_unit:
        # The paper printed a unit we cannot read (nonlinear mobility in cm4 V-3 s-1, say).
        # Falling through to the default would store a plausible number in the wrong unit and
        # flag it `unit_assumed_...`, which asserts the paper printed nothing. It did.
        flags.append("unit_unrecognised")
        return None, flags
    quantity = parse_quantity(raw.get("quantity"))
    if quantity is None:
        if unit is Unit.mV:
            quantity = Quantity.zeta_potential
        elif unit is Unit.um_cm_per_Vs:
            quantity = Quantity.electrophoretic_mobility
        else:
            flags.append("quantity_unknown")
            return None, flags
    if unit is None:
        # Each quantity has one conventional printed unit, so an unstated one is an
        # omission rather than an ambiguity: assume it and say so. A mobility row used
        # to be dropped here when it had no value to judge the magnitude by, which threw
        # away exactly the figure-only rows this study is about.
        if quantity is Quantity.zeta_potential:
            unit, flags = Unit.mV, flags + ["unit_assumed_mV"]
        else:
            unit, flags = Unit.um_cm_per_Vs, flags + ["unit_assumed_um_cm_per_Vs"]
    if unit not in UNITS_FOR_QUANTITY[quantity]:
        flags.append("unit_quantity_mismatch")
        return None, flags
    if value is None:
        pass
    elif factor != 1.0:
        converted = value * factor
        # Colloid mobilities live within a few units of 1e-8 m2/V/s. A conversion that
        # lands far outside that read the unit wrongly; keep the printed number instead
        # of storing a corrupted one.
        if quantity is Quantity.electrophoretic_mobility and abs(converted) > 100:
            flags.append("unit_conversion_refused_implausible")
        else:
            value = converted
            sd = sd * factor if sd is not None else None
            flags.append("unit_converted")
    elif quantity is Quantity.electrophoretic_mobility and abs(value) < 1e-4:
        value *= 1e8
        sd = sd * 1e8 if sd is not None else None
        flags.append("magnitude_rescaled")

    if sd is None and raw.get("sd") not in (None, ""):
        sd = parse_number(raw.get("sd"))[0]
    n_val = parse_number(raw.get("n"))[0] if raw.get("n") not in (None, "") else None
    n = int(n_val) if n_val is not None and n_val >= 1 else None

    medium_text = clean(_pick(raw, cond, "medium_text", "medium"))
    mc_raw = clean(_pick(raw, cond, "medium_class"))
    medium_class: MediumClass | None = None
    if mc_raw is not None:
        try:
            medium_class = MediumClass(
                mc_raw.strip().lower().replace(" ", "_").replace("di_", "DI_")
            )
        except ValueError:
            medium_class = None
            flags.append("medium_class_inferred")
    if medium_class is None or (medium_class is MediumClass.unreported and medium_text):
        medium_class = infer_medium_class(medium_text)

    i_raw = _pick(raw, cond, "ionic_strength", "ionic_strength_mM", "ionic_strength_text")
    mM, source, iflags = parse_ionic_strength(i_raw)
    if mM is None and medium_text:
        mM, source, iflags = parse_ionic_strength(medium_text, from_medium=True)
        if mM is not None:
            iflags = iflags + ["ionic_strength_from_medium"]
    flags.extend(iflags)

    pH, pH_text = parse_ph(_pick(raw, cond, "pH", "ph", "pH_text"))
    temp_c, temp_q, tflags = parse_temperature(
        _pick(raw, cond, "temperature", "temperature_C", "temperature_text")
    )
    flags.extend(tflags)

    evidence_raw = raw.get("evidence") if isinstance(raw.get("evidence"), dict) else {}
    quote = clean(raw.get("evidence_quote") or evidence_raw.get("quote"))
    location = clean(raw.get("evidence_location") or evidence_raw.get("location"))

    try:
        measurement = SurfaceMeasurement(
            particle_name=clean(raw.get("particle_name")),
            material=clean(raw.get("material")),
            functionalisation=clean(raw.get("functionalisation")),
            supplier=clean(raw.get("supplier")),
            size_nominal_nm=parse_size_nm(raw.get("size_nominal_nm") or raw.get("size_nominal")),
            size_measured_nm=parse_size_nm(raw.get("size_measured_nm") or raw.get("size_measured")),
            quantity=quantity,
            value=value,
            value_text=value_text,
            unit=unit,
            sd=sd if sd is None or sd >= 0 else None,
            n=n,
            conditions=MeasurementConditions(
                medium_text=medium_text,
                medium_class=medium_class,
                ionic_strength_mM=mM,
                ionic_strength_source=source,
                pH=pH,
                pH_text=pH_text,
                temperature_C=temp_c,
                temperature_qualifier=temp_q,
                instrument=clean(_pick(raw, cond, "instrument")),
                instrument_settings=clean(_pick(raw, cond, "instrument_settings")),
            ),
            medium_matches_exposure=_bool(raw.get("medium_matches_exposure")),
            evidence=Evidence(quote=quote, location=location) if quote else None,
        )
    except ValidationError as e:
        flags.append("validation_error:" + "; ".join(err["msg"] for err in e.errors())[:200])
        return None, flags
    return measurement, flags
