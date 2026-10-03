"""Where did the particle whose zeta potential was measured come from?

Bought as particles, made in the lab, or collected from a real environment. The question is
asked of each paper once, by the grid's isolated reader, over the paper's lines that speak to
origin: supplier and purchase wording, ways of making or ageing particles, environments and
sampling, plus every line the paper's zeta rows were read from (they are what names the
particles). A paper with more such lines than the budget keeps the highest-signal ones and the
prompt says how many it lost.

Origin is not the measurement medium. A polystyrene bead bought from a catalogue and dispersed
in lake water is commercial; the lake is where it was measured, not where it came from. The
prompt says so twice because the table's `medium_class` already carries "environmental_water"
for 48 rows, and a reader that conflates the two would report those as environmental samples.

The lines come from the paper's line document, `lines.build_lines`: the document the extraction
read and every stored citation addresses. The two recorded runs read something else. Until
9b17a6c the parser took a supplementary-materials section for the Methods in 208 of the 491
papers, so the Materials paragraph that names a supplier never reached the line document;
origin-20260929 read it that way, and origin-20260929b read it with those Methods appended here.
After the fix the appendix patched only papers whose Methods heading the parser still does not
recognise, a parser gap the extraction shares, so it was dropped: one document for every reader.

python -m mnp.extract.origin estimate
python -m mnp.extract.origin run [--run RUN_ID] [--reuse-from RUN_ID] [--jobs N] [--only ...]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from mnp import config, runs
from mnp.corpus import jats, lines
from mnp.eval import grid, scoring

ORIGINS = ("commercial", "lab_fabricated", "environmental", "unclear")
ENVIRONMENTS = (
    "freshwater",
    "seawater",
    "wastewater",
    "soil",
    "sediment",
    "air_dust",
    "biota",
    "other",
)
BUDGET_TOKENS = 3000
#: Martin, 2026-09-29: stop and report before the reader spends more than this.
INPUT_TOKEN_LIMIT = 4_000_000
#: origin-20260929 read the unrepaired line document and was stopped at 224 papers;
#: origin-20260929b read it with the lost Methods appended. Neither read `build_lines` as
#: `load_doc` now does, so the next run needs a new id: resuming this one skips every paper it
#: answered, whatever its prompt is now.
RUN_ID = "origin-20260929b"
PREVIOUS_RUN_ID = "origin-20260929"


def answers_dir() -> Path:
    return config.DATA_INTERIM / "origin"


approx_tokens = jats.approx_tokens

# The reader bills real tokens, the budget above is chars/4. Fitted on the 399 answered
# questions of cellb-sweep-20260928: billed = 632 + 1.47 * approx_tokens(prompt).
_BILLED_OVERHEAD = 632
_BILLED_PER_APPROX = 1.47


def estimate_billed(prompt: str) -> int:
    return round(_BILLED_OVERHEAD + _BILLED_PER_APPROX * approx_tokens(prompt))


# -- which lines speak to origin -------------------------------------------------------------------

_COMPANIES = (
    r"Sigma|Aldrich|Merck|Thermo|Fisher|Invitrogen|Molecular Probes|Polysciences|Bangs"
    r"|microParticles|Cospheric|Magsphere|Alfa Aesar|Spherotech|Duke Scientific|Phosphorex"
    r"|Nanocs|Corpuscular|Degradex|Kisker|micromod|Aladdin|Macklin|BaseLine|Goodfellow"
    r"|Acros|TCI|Lab261|Nanomicro|Zhongke|Huge Biotech\w*|Ruixi|Dow|BASF|ExxonMobil|Sinopec"
    r"|LyondellBasell|Polymer Source|Scientific Polymer|EPRUI|Knowle|Sabic|SABIC|Borealis"
    r"|Arkema|DuPont|Lanxess|Ineos|INEOS|TotalEnergies|Covestro|Evonik|Carl Roth"
    r"|VWR|Solarbio|PolyAn|Microspheres-Nanospheres|Nanomi|Ikerlat"
)

#: family -> (weight, pattern). Weights only order lines when a paper is over budget.
#: Company names are matched case-sensitively: "BaseLine" is a supplier, "baseline" is not.
_CUES: dict[str, tuple[int, re.Pattern[str]]] = {
    "supplier": (
        3,
        re.compile(
            r"(?i:\b(?:purchased|bought|obtained\s+from|supplied\s+by|provided\s+by|"
            r"kindly\s+provided|acquired\s+from|received\s+from|donated|gift\s+from|"
            r"commercial(?:ly)?|manufactured\s+by|sourced\s+from|procured|"
            r"reference\s+materials?|cat(?:alog(?:ue)?)?\.?\s*(?:no|number)|"
            r"product\s+(?:no|number|code))\b)"
            rf"|\b(?:{_COMPANIES})\b"
        ),
    ),
    "company": (
        1,
        re.compile(
            r"\b(?:Inc|Ltd|GmbH|Corp|LLC|Company)\b|\bCo\.,?\s*Ltd|\bB\.V\.|\bS\.r\.l\.|\bS\.A\."
            r"|\bAG\b"
        ),
    ),
    "fabrication": (
        3,
        re.compile(
            r"\b(?:mill(?:ed|ing)?|ball[- ]mill\w*|grind(?:ing)?|ground|"
            r"cryo(?:genic(?:ally)?|-?mill\w*|-?ground|-?grind\w*)|blend(?:ed|er|ing)|"
            r"fragment(?:ed|ation|ing)|abra(?:ded|sion|sive)|laser\s+ablation|"
            r"nano-?precipitation|emulsi(?:on|fication|fied)|synthesi[sz](?:ed|ing|is)|"
            r"polymeri[sz](?:ed|ation)|prepar(?:ed|ation)\s+(?:of|from|by|via|using)|fabricated|"
            r"produced\s+(?:from|by)|made\s+from|cut\s+(?:from|into)|shred(?:ded|ding)|"
            r"pulveri[sz](?:ed|ation)|sand(?:ed|ing)|fil(?:ed|ing)|scraped|microni[sz]ed|mortar|"
            r"crush(?:ed|ing)|pellets?|granules?|tea\s*bags?|bottles?|cups?|"
            r"dissolv(?:ed|ing)\s+in\s+(?:THF|tetrahydrofuran|acetone|toluene|chloroform|"
            r"DCM|dichloromethane|xylene))\b",
            re.IGNORECASE,
        ),
    ),
    "ageing": (
        2,
        re.compile(
            r"\b(?:UV(?:-?[ABC])?\b(?![-\s/]*vis)|ultraviolet|weather(?:ed|ing)|aged|"
            r"ag(?:e)?ing|irradiat(?:ed|ion)|photo-?(?:oxidi[sz]\w*|degrad\w*|ag\w*)|xenon|"
            r"sunlight|ozon\w*|Fenton|persulfate|thermal(?:ly)?\s+(?:aged|oxidi\w*|degrad\w*))",
            re.IGNORECASE,
        ),
    ),
    "collection": (
        3,
        re.compile(
            r"\b(?:collected|sampled|sampling|in\s+the\s+field|in\s+situ|"
            r"field[- ](?:collected|samples?|sites?|campaigns?|study|survey|work)|"
            r"study\s+(?:area|sites?)|environmental\s+samples?)\b",
            re.IGNORECASE,
        ),
    ),
    "environmental": (
        2,
        re.compile(
            r"\b(?:rivers?|lakes?|seas?|sea\s*water|oceans?|oceanic|marine|beach(?:es)?|"
            r"shorelines?|coast(?:al|s)?|estuar\w*|harbou?rs?|bays?|gyres?|sediments?|"
            r"soils?|air|airborne|atmospher\w*|dust|waste\s*water|effluents?|WWTPs?|"
            r"sludge|sewage|storm\s*water|runoff|surface\s+water|ground\s*water|streams?|"
            r"ponds?|reservoirs?|wetlands?|mangroves?|landfills?|farmland|agricultural|"
            r"mulch\w*|tap\s+water|drinking\s+water)\b",
            re.IGNORECASE,
        ),
    ),
}
CITED_WEIGHT = 2
#: A cue in a line about the particles outranks the same cue in a line about a reagent or a
#: cell line: "PS beads were purchased from Polysciences" beats "DAPI was purchased from Sigma".
PARTICLE_WEIGHT = 3
_PARTICLE = re.compile(
    r"\b(?:micro|nano)?(?:plastics?|particles?|spheres?|beads?|fibres?|fibers?|fragments?)\b"
    r"|\b(?:MPs?|NPs?|NPLs?|MNPs?|PS|PE|PP|PET|PETE|PVC|PMMA|HDPE|LDPE|LLDPE|PA\d*|PLA|PU|PC"
    r"|PTFE|PBAT|PHB|EPS|ABS)\b"
    r"|polystyrene|polyethylene|polypropylene|latex|polyamide|nylon|polyester|polyurethane"
    r"|polycarbonate|polylactic|polyvinyl|poly\(|\bpolymers?\b|\bplastics?\b|\bresins?\b",
    re.IGNORECASE,
)
#: A line longer than this is shown as its cue-bearing sentences only. The citation still
#: addresses the whole line; the reader just does not pay for the paragraph around the cue.
LONG_LINE = 250
#: One sentence that names the particles *and* says where they came from is the line the
#: question is about; it outranks everything else.
STATEMENT_WEIGHT = 4
_STATEMENT_FAMILIES = frozenset({"supplier", "fabrication", "collection"})
_SENTENCE = re.compile(r"(?<=[.;!?])\s+(?=[A-Z(])")


def cues(text: str) -> dict[str, int]:
    """The cue families a line carries, with their weights."""
    return {family: weight for family, (weight, rx) in _CUES.items() if rx.search(text)}


@dataclass(frozen=True)
class Evidence:
    pmcid: str
    doc: lines.LinedDoc
    shown: tuple[lines.Line, ...]
    texts: tuple[str, ...]  # what is displayed for each shown line: all of it, or an excerpt
    candidates: int  # lines with any cue or a citation, before the budget

    @property
    def dropped(self) -> int:
        return self.candidates - len(self.shown)

    @property
    def excerpted(self) -> int:
        return sum(t != x.text for x, t in zip(self.shown, self.texts, strict=True))

    @property
    def tokens(self) -> int:
        return sum(approx_tokens(t) + 1 for t in self.texts)


def _name_pattern(name: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(name)}(?!\w)")


def _about_particles(text: str, names: Sequence[re.Pattern[str]]) -> bool:
    return bool(_PARTICLE.search(text)) or any(rx.search(text) for rx in names)


ELISION = "[…]"


def excerpt(text: str, names: Sequence[re.Pattern[str]] = ()) -> str:
    """A long line cut to the sentences that carry a cue, or failing that name the particles."""
    if approx_tokens(text) <= LONG_LINE:
        return text
    sentences = _SENTENCE.split(text)
    keep = [bool(cues(s)) for s in sentences]
    if not any(keep):
        keep = [_about_particles(s, names) for s in sentences]
    if all(keep) or not any(keep):
        return text
    pieces: list[str] = []
    for sentence, kept in zip(sentences, keep, strict=True):
        if kept:
            pieces.append(sentence)
        elif not pieces or pieces[-1] != ELISION:
            pieces.append(ELISION)
    return " ".join(pieces)


def select(
    doc: lines.LinedDoc,
    cited: Iterable[str],
    particle_names: Sequence[str] = (),
    budget: int = BUDGET_TOKENS,
) -> Evidence:
    """Every cue line and cited line, highest signal first until the budget, in reading order."""
    cited = frozenset(cited)
    names = [_name_pattern(n) for n in particle_names if n.strip()]
    scored: list[tuple[int, lines.Line]] = []
    for line in doc.lines:
        score = max(cues(line.text).values(), default=0)
        score += CITED_WEIGHT if line.line_id in cited else 0
        if not score:
            continue
        if _about_particles(line.text, names):
            score += PARTICLE_WEIGHT
            if any(
                _about_particles(sentence, names) and _STATEMENT_FAMILIES & cues(sentence).keys()
                for sentence in _SENTENCE.split(line.text)
            ):
                score += STATEMENT_WEIGHT
        scored.append((score, line))
    # A paper whose candidates fit is shown whole; only an over-budget one is excerpted.
    fits = sum(approx_tokens(line.text) + 1 for _, line in scored) <= budget
    kept: dict[int, tuple[lines.Line, str]] = {}
    cost = 0
    for _, line in sorted(scored, key=lambda s: (-s[0], s[1].n)):
        text = line.text if fits else excerpt(line.text, names)
        c = approx_tokens(text) + 1
        if cost + c > budget:
            continue  # a shorter line further down may still fit
        kept[line.n] = (line, text)
        cost += c
    ordered = [kept[n] for n in sorted(kept)]
    return Evidence(
        pmcid=doc.pmcid or "",
        doc=doc,
        shown=tuple(line for line, _ in ordered),
        texts=tuple(text for _, text in ordered),
        candidates=len(scored),
    )


def load_table() -> pd.DataFrame:
    return pd.read_csv(config.OUT_TABLES / "d1_zeta_table.csv")


def load_doc(pmcid: str, xml_dir: Path | None = None) -> lines.LinedDoc:
    """The paper's line document: `lines.build_lines`, the one every other consumer reads."""
    article = jats.parse(((xml_dir or config.EPMC_XML_DIR) / f"{pmcid}.xml").read_bytes())
    article.pmcid = pmcid
    return lines.build_lines(article)


def cited_ids(rows: pd.DataFrame) -> frozenset[str]:
    return frozenset(
        i for ids in rows["evidence_line_ids"].dropna() for i in str(ids).split(";") if i
    )


def particle_names(rows: pd.DataFrame) -> tuple[str, ...]:
    """Distinct names in row order. The reader answers per name; rows are matched back by it."""
    return tuple(dict.fromkeys(str(n).strip() for n in rows["particle_name"].dropna()))


def evidence_lines(
    pmcid: str,
    table: pd.DataFrame | None = None,
    xml_dir: Path | None = None,
    budget: int = BUDGET_TOKENS,
) -> Evidence:
    table = load_table() if table is None else table
    rows = table[table["pmcid"] == pmcid]
    return select(load_doc(pmcid, xml_dir), cited_ids(rows), particle_names(rows), budget)


# -- the prompt ------------------------------------------------------------------------------------

_RULES = """RULES
- origin is where the particle itself came from, not the liquid it was measured in. A \
commercial polystyrene bead dispersed in river water, seawater or wastewater is still commercial.
- commercial: bought or received ready-made as particles (beads, spheres, powders, reference \
materials) from a company or a reference-material provider. Sieving, washing, dialysing or \
labelling them does not change that.
- lab_fabricated: made in the lab from bulk polymer (pellets, granules, film, sheet, foam, \
fibres, objects) or from consumer products, by milling, grinding, cryogenic grinding, \
blending, cutting, abrasion, fragmentation, laser ablation, nanoprecipitation, emulsion, \
synthesis or polymerisation, or released from a product in the lab (for example by steeping \
a tea bag). This holds even when the bulk polymer or the product was bought, and when the \
particles were made by another research laboratory and given to the authors.
- environmental ONLY if the particles were collected from a real environment (freshwater, \
seawater, wastewater or sludge, soil, sediment, air or dust, organisms, drinking water) and \
then isolated. An environmental water used as the dispersion medium does not make a particle \
environmental, and neither does ageing in the lab that imitates the environment.
- unclear when the lines do not say where this particle came from. Do not infer an origin \
from the particle's name, size or polymer.
- aged_in_lab is separate from origin: true if the authors aged, weathered, irradiated or \
oxidised this particle before measuring it; false if no line describes ageing this particle; \
null if ageing is described but the lines do not say whether it applies to this particle.
- environment: for an environmental particle, where it was collected: freshwater, seawater, \
wastewater (including sludge and effluent), soil, sediment, air_dust, biota (isolated from \
organisms) or other. null for every other origin.
- Answer only from the lines above. Do not use background knowledge about a product or a \
supplier.
- Cite every claim: citations lists the addresses of the lines that show the origin and the \
ageing, each exactly as printed at the start of its line (PMCID:L<n>). An unclear particle \
cites the lines that name it.
- Do not explain your reasoning outside the JSON object."""

_CONTRACT = """OUTPUT
Return exactly one JSON object and nothing else, with one entry per particle listed above:
{"particles": [{"particle_name": "<name exactly as listed>", \
"origin": "commercial" | "lab_fabricated" | "environmental" | "unclear", \
"aged_in_lab": true | false | null, \
"environment": "freshwater" | "seawater" | "wastewater" | "soil" | "sediment" | "air_dust" \
| "biota" | "other" | null, \
"citations": ["PMCID:L<n>", ...], "reason": "<one sentence>"}, ...]}"""


def render(ev: Evidence) -> str:
    """The shown lines under their section headers, each prefixed with its citation address."""
    header_of = {
        n: span.header for span in ev.doc.sections for n in range(span.start + 1, span.stop + 1)
    }
    out: list[str] = []
    current = None
    for line, text in zip(ev.shown, ev.texts, strict=True):
        header = header_of.get(line.n, "")
        if header != current:
            out.append(header)
            current = header
        out.append(f"{ev.pmcid}:L{line.n}\t{text}")
    return "\n".join(out)


def prompt_for(pmcid: str, names: Sequence[str], evidence: Evidence | None = None) -> str:
    ev = evidence if evidence is not None else evidence_lines(pmcid)
    note = (
        f" {ev.dropped} further lines with weaker origin cues were dropped to fit the length "
        "limit; if what you need is not here, answer unclear."
        if ev.dropped
        else ""
    )
    if ev.excerpted:
        note += (
            f" {ev.excerpted} long lines are shown as their relevant sentences only, with "
            f"{ELISION} where the rest of the line was left out."
        )
    listed = "\n".join(json.dumps(n, ensure_ascii=False) for n in names)
    return "\n\n".join(
        [
            f"You are reading lines from one paper, {pmcid}, to say where each particle whose "
            "zeta potential it measured came from: bought as particles, made in the lab, or "
            "collected from a real environment.",
            "PARTICLES\nThe paper's zeta-potential records name these particles. Answer for "
            f"each, using the name exactly as written:\n{listed}",
            "LINES\nEach line starts with its citation address. These are the paper's lines "
            "that mention a supplier, a way of making or ageing particles, an environment or "
            "sampling, and the lines its zeta-potential records were read from."
            f"{note}\n{render(ev)}",
            _RULES.replace("PMCID", pmcid),
            _CONTRACT.replace("PMCID", pmcid),
        ]
    )


# -- reading the reply back ------------------------------------------------------------------------


@dataclass(frozen=True)
class Parsed:
    particles: tuple[Mapping[str, Any], ...]
    unparsed: bool
    problems: tuple[str, ...] = ()


def parse_reply(text: str) -> Parsed:
    """The `particles` list out of whatever the reader wrote. Unreadable is recorded, not raised."""
    answer = scoring.parse_answer("origin", "origin", text)
    found = answer.payload.get("particles")
    if answer.unparsed or not isinstance(found, list):
        return Parsed((), True, ("no particles list",))
    problems: list[str] = []
    particles = []
    for item in found:
        if not isinstance(item, dict) or not str(item.get("particle_name") or "").strip():
            problems.append(f"entry without a particle_name: {item!r:.80}")
            continue
        name = str(item["particle_name"]).strip()
        if item.get("origin") not in ORIGINS:
            problems.append(f"{name}: origin {item.get('origin')!r} not in {ORIGINS}")
        if item.get("environment") not in (*ENVIRONMENTS, None):
            problems.append(f"{name}: environment {item.get('environment')!r} not allowed")
        if item.get("aged_in_lab") not in (True, False, None):
            problems.append(f"{name}: aged_in_lab {item.get('aged_in_lab')!r} not a boolean")
        if not isinstance(item.get("citations", []), list):
            problems.append(f"{name}: citations is not a list")
        particles.append({**item, "particle_name": name})
    return Parsed(tuple(particles), False, tuple(problems))


_CITATION = re.compile(r"^(?:(PMC\w+)\s*:\s*)?L(\d+)$")


@dataclass(frozen=True)
class Citations:
    resolved: tuple[str, ...]
    unresolved: tuple[str, ...]
    line_ids: tuple[str, ...]


def check_citations(doc: lines.LinedDoc, citations: Iterable[Any]) -> Citations:
    """A citation counts only if it addresses a line of *this* paper. A bare `Lnn` is its own."""
    ok, bad, ids = [], [], []
    for token in (str(c).strip() for c in citations):
        match = _CITATION.match(token)
        line = None
        if match and match.group(1) in (None, doc.pmcid):
            line = lines.resolve(doc, int(match.group(2)))
        if line is None:
            bad.append(token)
        else:
            ok.append(token)
            ids.append(line.line_id)
    return Citations(tuple(ok), tuple(bad), tuple(ids))


# -- the run ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Job:
    pmcid: str
    particle_names: tuple[str, ...]
    prompt: str
    lines_shown: int
    lines_dropped: int


def jobs_for(table: pd.DataFrame, pmcids: Iterable[str] | None = None) -> list[Job]:
    wanted = sorted(set(pmcids) if pmcids is not None else set(table["pmcid"]))
    out = []
    for pmcid in wanted:
        rows = table[table["pmcid"] == pmcid]
        names = particle_names(rows)
        ev = select(load_doc(pmcid), cited_ids(rows), names)
        out.append(Job(pmcid, names, prompt_for(pmcid, names, ev), len(ev.shown), ev.dropped))
    return out


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _append(path: Path, record: Mapping[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_answers(directory: Path, run_id: str) -> dict[str, dict[str, Any]]:
    """This run's answers by pmcid. The file is shared by runs; each record names its own."""
    path = directory / "answers.jsonl"
    if not path.is_file():
        return {}
    out = {}
    for text in path.read_text(encoding="utf-8").splitlines():
        if text.strip():
            record = json.loads(text)
            if record.get("run_id") == run_id:
                out[record["pmcid"]] = record
    return out


def billed(directory: Path) -> int:
    """Input tokens actually billed by every run in `directory`; a reused copy cost nothing."""
    path = directory / "answers.jsonl"
    if not path.is_file():
        return 0
    return sum(
        int(record.get("input_tokens") or 0)
        for record in map(json.loads, filter(str.strip, path.read_text("utf-8").splitlines()))
        if not record.get("reused_from")
    )


def run(
    work: Sequence[Job],
    directory: Path,
    run_id: str,
    reader: Callable[[str], grid.Reply] = grid.read,
    jobs: int = 1,
    limit: int = INPUT_TOKEN_LIMIT,
    reuse: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, int]:
    """Ask every paper not yet answered in this run. Append-only, safe to re-run after a crash.

    A reader failure is retried once at once; a second failure goes to errors.jsonl and the
    paper is asked again on the next run. A usage-policy refusal is deterministic, so it is the
    paper's answer and is never asked again. An answer in `reuse` (an earlier run) whose prompt
    hash equals this job's is copied, marked `reused_from`, and not bought twice. Nothing new is
    asked once the input billed by every run recorded in `directory` reaches `limit`.
    """
    directory.mkdir(parents=True, exist_ok=True)
    done = load_answers(directory, run_id)
    reuse = reuse or {}
    todo = [job for job in work if job.pmcid not in done]
    lock = threading.Lock()
    spent = [billed(directory)]
    reused = 0
    for job in list(todo):
        earlier = reuse.get(job.pmcid)
        if earlier and earlier.get("prompt_sha256") == grid.sha256(job.prompt):
            _append(
                directory / "answers.jsonl",
                {**earlier, "run_id": run_id, "reused_from": earlier["run_id"]},
            )
            todo.remove(job)
            reused += 1

    def record(job: Job, reply: grid.Reply | None, refused: str = "") -> None:
        _append(
            directory / "answers.jsonl",
            {
                "run_id": run_id,
                "pmcid": job.pmcid,
                "particle_names": list(job.particle_names),
                "prompt_sha256": grid.sha256(job.prompt),
                "lines_shown": job.lines_shown,
                "lines_dropped": job.lines_dropped,
                "text": reply.text if reply else refused,
                "refused": reply is None,
                "model": reply.model if reply else grid.READER_MODEL,
                "input_tokens": reply.input_tokens if reply else 0,
                "output_tokens": reply.output_tokens if reply else 0,
                "cost_usd": reply.cost_usd if reply else 0.0,
                "duration_ms": reply.duration_ms if reply else 0,
                "at": _now(),
            },
        )

    def ask(job: Job) -> str:
        with lock:
            if spent[0] >= limit:
                return "over_budget"
        error = ""
        for _ in range(2):
            try:
                reply = reader(job.prompt)
            except grid.Refused as exc:
                with lock:
                    record(job, None, str(exc))
                return "refused"
            except grid.ReaderError as exc:
                error = str(exc)
                continue
            with lock:
                spent[0] += reply.input_tokens
                record(job, reply)
            return "answered"
        with lock:
            _append(
                directory / "errors.jsonl",
                {"run_id": run_id, "pmcid": job.pmcid, "error": error, "at": _now()},
            )
        return "failed"

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        outcomes = list(pool.map(ask, todo))
    return {
        "asked": len(work),
        "already_answered": len(work) - len(todo) - reused,
        "reused": reused,
        "answered_now": outcomes.count("answered"),
        "refused": outcomes.count("refused"),
        "reader_failures": outcomes.count("failed"),
        "over_budget": outcomes.count("over_budget"),
        "input_tokens_spent": spent[0],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m mnp.extract.origin")
    p.add_argument("what", choices=["estimate", "run"])
    p.add_argument("--run", default=RUN_ID, help="run id; an existing one resumes")
    p.add_argument("--reuse-from", default=PREVIOUS_RUN_ID, help="copy identical-prompt answers")
    p.add_argument("--jobs", type=int, default=4)
    p.add_argument("--only", nargs="*", help="these pmcids only (a pilot)")
    args = p.parse_args(argv)

    table = load_table()
    work = jobs_for(table, args.only)
    directory = answers_dir()
    done = load_answers(directory, args.run)
    reuse = load_answers(directory, args.reuse_from) if args.reuse_from else {}
    spent = billed(directory)
    todo = [job for job in work if job.pmcid not in done]
    reusable = [
        j for j in todo if reuse.get(j.pmcid, {}).get("prompt_sha256") == grid.sha256(j.prompt)
    ]
    to_buy = [j for j in todo if j not in reusable]
    estimate = sum(estimate_billed(job.prompt) for job in to_buy)
    print(
        f"{len(work)} papers, {sum(len(j.particle_names) for j in work)} particles; "
        f"{len(done)} answered in this run, {len(reusable)} reusable, {len(to_buy)} to ask; "
        f"{sum(j.lines_dropped > 0 for j in work)} papers capped; billed by every run so far "
        f"{spent:,}, estimated for the rest {estimate:,} (limit {INPUT_TOKEN_LIMIT:,})"
    )
    if args.what == "estimate":
        return 0
    if spent + estimate > INPUT_TOKEN_LIMIT:
        print("refusing to start: the estimate exceeds the input-token limit")
        return 1
    runs.start(
        args.run,
        task="sample origin of every measured particle (confirmation only)",
        model=grid.READER_MODEL,
        reader=f"claude -p, tools off, no setting sources ({grid.cli_version()})",
        system_prompt_sha256=grid.sha256(grid.SYSTEM_PROMPT),
        budget_tokens_per_paper=BUDGET_TOKENS,
        input_token_limit=INPUT_TOKEN_LIMIT,
        answers=str((directory / "answers.jsonl").relative_to(config.ROOT)),
        reuses=args.reuse_from,
    )
    counts = run(work, directory, args.run, jobs=args.jobs, reuse=reuse)
    runs.finish(args.run, counts)
    print(json.dumps(counts, indent=2))
    return 0 if not counts["reader_failures"] and not counts["over_budget"] else 1


if __name__ == "__main__":
    sys.exit(main())
