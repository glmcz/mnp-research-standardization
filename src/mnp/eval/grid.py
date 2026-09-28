"""Run one cell of the grid against the query set with a headless reader, then score it.

The reader is ``claude -p``: the Claude Code CLI on this machine's own login, because no API key
is configured here on purpose. Everything that could reach it besides the prompt is switched off,
and each switch is pinned by a test:

* **no tools** (``--tools ""``), so it cannot open the answer key sitting in ``queries/``;
* **no setting sources and no MCP**, so no hook, plugin or server adds context;
* **its own system prompt**, replacing the coding-agent one;
* **a working directory with no CLAUDE.md above it.** Auto-discovery walks up from the cwd, and
  this repository's instruction files name the headline numbers.

**The model is pinned by full id, and every reply is checked against it.** On CLI 2.1.92 the
alias ``sonnet`` resolved to ``claude-sonnet-4-6``. Cells run days apart; an alias would let the
reader change between them while every manifest still said "sonnet".

Cells B and D are one-shot — their prompt is a pure function of question and corpus — so their
whole run lives here. C and E are multi-turn and are not run by this module.

A reader failure (timeout, rate limit, wrong model) is **not an answer**. It goes to
``errors.jsonl`` and the question is asked again on resume. An answer that arrives and cannot be
parsed *is* an answer, and the scorer counts it wrong: that is the cell's failure, not the
infrastructure's.
"""

from __future__ import annotations

import functools
import hashlib
import json
import subprocess
import tempfile
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mnp.eval import cells, query_sets, scoring
from mnp.eval.query_sets import AnswerKey, QueryKind, Question

#: The one reader for every cell. Changing it invalidates every cell already run.
READER_MODEL = "claude-sonnet-5"
SYSTEM_PROMPT = (
    "You answer one question about scientific papers, using only the evidence in the user "
    "message. Follow its rules and output contract exactly."
)
TIMEOUT_S = 300
PILOT_PER_KIND = 2
INSTRUCTION_FILES = ("CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md")

BUILDERS: dict[str, Callable[[Question, cells.Corpus], cells.Delivered]] = {
    "B": cells.build_b,
    "D": cells.build_d,
}


class ReaderError(RuntimeError):
    """The reader did not produce an answer. Retried on resume; never scored."""


class Refused(ReaderError):
    """The API's usage-policy filter refused the prompt.

    Unlike a timeout this is deterministic: D-008 was refused three times on ordinary colloid
    text. Martin, 2026-09-28: refuse it. So a refusal is the cell's answer -- recorded, scored
    wrong, kept in the denominator, and never asked again.
    """


_REFUSAL_MARK = "Usage Policy"


@dataclass(frozen=True)
class Reply:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# -- the reader ------------------------------------------------------------------------------


def reader_command(model: str = READER_MODEL) -> list[str]:
    return [
        "claude",
        "-p",
        "--model",
        model,
        "--tools",
        "",
        "--setting-sources",
        "",
        "--strict-mcp-config",
        "--no-session-persistence",
        "--system-prompt",
        SYSTEM_PROMPT,
        "--output-format",
        "json",
    ]


@functools.cache
def reader_cwd() -> Path:
    return Path(tempfile.mkdtemp(prefix="mnp-reader-"))


def instruction_files_above(path: Path) -> list[Path]:
    found = []
    for directory in (path, *path.parents):
        found.extend(directory / name for name in INSTRUCTION_FILES if (directory / name).is_file())
    return found


def parse_cli_output(stdout: str, model: str = READER_MODEL) -> Reply:
    try:
        body = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ReaderError(f"reader printed no JSON: {stdout[:200]!r}") from exc
    if body.get("is_error") or body.get("subtype") != "success":
        message = str(body.get("result") or body.get("subtype"))
        if _REFUSAL_MARK in message:
            raise Refused(f"reader refused: {message[:300]}")
        raise ReaderError(f"reader failed: {message[:300]}")
    models = sorted(body.get("modelUsage") or {})
    if models != [model]:
        raise ReaderError(f"reply came from {models}, not {model}")
    usage = body.get("usage") or {}
    return Reply(
        text=str(body.get("result") or ""),
        model=models[0],
        input_tokens=sum(
            int(usage.get(name) or 0)
            for name in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
        ),
        output_tokens=int(usage.get("output_tokens") or 0),
        cost_usd=float(body.get("total_cost_usd") or 0.0),
        duration_ms=int(body.get("duration_ms") or 0),
    )


def read(prompt: str) -> Reply:
    cwd = reader_cwd()
    planted = instruction_files_above(cwd)
    if planted:
        raise ReaderError(f"instruction files above the reader's cwd: {planted}")
    try:
        done = subprocess.run(
            reader_command(),
            input=prompt,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as exc:
        raise ReaderError(f"timed out after {TIMEOUT_S} s") from exc
    if done.returncode != 0 and not done.stdout.strip():
        raise ReaderError(f"exit {done.returncode}: {done.stderr.strip()[-300:]}")
    return parse_cli_output(done.stdout)


def cli_version() -> str:
    try:
        return subprocess.run(
            ["claude", "--version"], capture_output=True, text=True, timeout=30
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


# -- choosing the questions --------------------------------------------------------------------


def all_questions() -> list[Question]:
    return [q for kind in QueryKind for q in query_sets.read_questions(kind)]


def all_keys() -> list[AnswerKey]:
    return [k for kind in QueryKind for k in query_sets.read_answer_key(kind)]


def pilot(questions: Iterable[Question], per_kind: int = PILOT_PER_KIND) -> list[Question]:
    """The first few of every kind, in file order. File order is already seeded and shuffled."""
    taken: dict[QueryKind, int] = {}
    picked = []
    for question in questions:
        if taken.get(question.kind, 0) < per_kind:
            taken[question.kind] = taken.get(question.kind, 0) + 1
            picked.append(question)
    return picked


# -- running a cell ------------------------------------------------------------------------------


def _append(path: Path, record: Mapping[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def load_answers(directory: Path) -> dict[str, dict[str, Any]]:
    path = directory / "answers.jsonl"
    if not path.is_file():
        return {}
    answers = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            answers[record["qid"]] = record
    return answers


def _refused_before(directory: Path) -> set[str]:
    """Questions an earlier run logged as a usage-policy failure, from before refusals were
    their own outcome. They are recorded as refused rather than asked again."""
    path = directory / "errors.jsonl"
    if not path.is_file():
        return set()
    return {
        json.loads(line)["qid"]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and _REFUSAL_MARK in json.loads(line).get("error", "")
    }


def _asked(directory: Path) -> list[str]:
    path = directory / "asked.txt"
    return path.read_text(encoding="utf-8").split() if path.is_file() else []


def run_cell(
    cell: str,
    questions: Sequence[Question],
    corpus: cells.Corpus,
    directory: Path,
    reader: Callable[[str], Reply] = read,
    jobs: int = 1,
) -> dict[str, int]:
    """Ask every question not already answered in `directory`. Safe to re-run after a crash.

    `asked.txt` is written before any reading: it is the denominator, fixed by the plan and not
    by whichever answers happened to come back.
    """
    build = BUILDERS[cell]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "asked.txt").write_text("".join(f"{q.qid}\n" for q in questions))
    done = load_answers(directory)
    refused_before = _refused_before(directory)
    todo = [(q, build(q, corpus)) for q in questions if q.qid not in done]
    lock = threading.Lock()

    def record_refusal(question: Question, delivered: cells.Delivered, message: str) -> None:
        with lock:
            _append(
                directory / "answers.jsonl",
                {
                    "qid": question.qid,
                    "kind": question.kind.value,
                    "cell": cell,
                    "route": delivered.route,
                    "tokens_delivered": delivered.tokens,
                    "prompt_sha256": sha256(delivered.prompt),
                    "row_ids": list(delivered.row_ids),
                    "line_ids": list(delivered.line_ids),
                    "text": message,
                    "refused": True,
                    "model": READER_MODEL,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_usd": 0.0,
                    "duration_ms": 0,
                    "answered_at": _now(),
                },
            )

    def ask(item: tuple[Question, cells.Delivered]) -> str:
        question, delivered = item
        if question.qid in refused_before:
            record_refusal(
                question, delivered, "refused by the usage-policy filter in an earlier run"
            )
            return "refused"
        try:
            reply = reader(delivered.prompt)
        except Refused as exc:
            record_refusal(question, delivered, str(exc))
            return "refused"
        except ReaderError as exc:
            with lock:
                _append(
                    directory / "errors.jsonl",
                    {"qid": question.qid, "error": str(exc), "at": _now()},
                )
            return "failed"
        record = {
            "qid": question.qid,
            "kind": question.kind.value,
            "cell": cell,
            "route": delivered.route,
            "tokens_delivered": delivered.tokens,
            "prompt_sha256": sha256(delivered.prompt),
            "row_ids": list(delivered.row_ids),
            "line_ids": list(delivered.line_ids),
            "text": reply.text,
            "model": reply.model,
            "input_tokens": reply.input_tokens,
            "output_tokens": reply.output_tokens,
            "cost_usd": reply.cost_usd,
            "duration_ms": reply.duration_ms,
            "answered_at": _now(),
        }
        with lock:
            _append(directory / "answers.jsonl", record)
        return "answered"

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        outcomes = list(pool.map(ask, todo))
    return {
        "asked": len(questions),
        "already_answered": len(questions) - len(todo),
        "answered_now": outcomes.count("answered"),
        "refused": outcomes.count("refused"),
        "reader_failures": outcomes.count("failed"),
    }


# -- scoring a run -------------------------------------------------------------------------------


@dataclass(frozen=True)
class RunScore:
    text: str
    scored: list[scoring.Scored]
    complete: bool


def score_run(directory: Path, keys: Sequence[AnswerKey], corpus: cells.Corpus) -> RunScore:
    asked = _asked(directory)
    wanted = set(asked)
    answers = {qid: rec for qid, rec in load_answers(directory).items() if qid in wanted}
    parsed = [
        scoring.parse_answer(
            qid, rec["cell"], rec["text"], tokens_delivered=rec["tokens_delivered"]
        )
        for qid, rec in answers.items()
    ]
    scored = scoring.score_all(parsed, keys, corpus)
    table = scoring.table(scoring.aggregate(scored))

    with (directory / "scored.jsonl").open("w", encoding="utf-8") as handle:
        for item in scored:
            handle.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")
    (directory / "scores.tsv").write_text(table + "\n")
    verdicts = scoring.verdict_table(scored)
    has_e = verdicts.count("\n") > 0
    if has_e:
        (directory / "verdicts.tsv").write_text(verdicts + "\n")

    missing = [qid for qid in asked if qid not in answers]
    refused = [qid for qid in asked if answers.get(qid, {}).get("refused")]
    lines = [
        f"answered {len(answers)} of {len(asked)}"
        + (f"; refused {len(refused)}: {' '.join(refused)}" if refused else ""),
        f"reader tokens: {sum(r['input_tokens'] for r in answers.values())} in, "
        f"{sum(r['output_tokens'] for r in answers.values())} out",
        "",
        table,
    ]
    if has_e:
        lines += ["", verdicts]
    if missing:
        lines += ["", f"not yet answered: {' '.join(missing)}"]
    return RunScore(text="\n".join(lines), scored=scored, complete=not missing)
