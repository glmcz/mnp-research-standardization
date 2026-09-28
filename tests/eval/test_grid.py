"""The cell runner: which reader it calls, what it records, and what it refuses to count."""

import json

import pytest

from mnp.eval import cells, grid, scoring
from mnp.eval.query_sets import AnswerKey, Question
from mnp.eval.query_sets import QueryKind as K

ABSENCE = Question(
    qid="B-001",
    kind=K.b,
    text="What ionic strength was used in PMCAAA?",
    scope=("PMCAAA",),
    target=(("field", "ionic_strength"),),
)
LOOKUP = Question(
    qid="A-001",
    kind=K.a,
    text="In PMCBBB, what zeta potential was reported for polyethylene in 10 mM NaCl?",
    scope=("PMCBBB",),
    target=(("material", "polyethylene"), ("quantity", "zeta_potential")),
)


def _reply(text: str, model: str = grid.READER_MODEL) -> grid.Reply:
    return grid.Reply(text=text, model=model, input_tokens=100, output_tokens=20)


def _cli_output(**overrides) -> str:
    """The shape `claude -p --output-format json` printed on 2026-09-27, trimmed."""
    body = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": '{"reported": false, "value": null, "citations": []}',
        "num_turns": 1,
        "duration_ms": 1100,
        "total_cost_usd": 0.00103,
        "usage": {
            "input_tokens": 120,
            "output_tokens": 8,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        },
        "modelUsage": {grid.READER_MODEL: {"inputTokens": 120, "outputTokens": 8}},
    }
    body.update(overrides)
    return json.dumps(body)


# -- the reader ------------------------------------------------------------------------------


def test_the_reader_has_no_tools_no_settings_and_no_mcp():
    command = grid.reader_command()
    assert command[:2] == ["claude", "-p"]
    assert command[command.index("--tools") + 1] == ""
    assert command[command.index("--setting-sources") + 1] == ""
    assert "--strict-mcp-config" in command
    assert "--system-prompt" in command, "the default coding-agent system prompt must be replaced"
    assert command[command.index("--output-format") + 1] == "json"


def test_the_reader_is_pinned_by_full_model_id_not_an_alias():
    """On CLI 2.1.92 the alias `sonnet` resolved to claude-sonnet-4-6. An alias can move between
    two cells run a week apart, and "the same reader in every cell" would silently stop holding."""
    command = grid.reader_command()
    model = command[command.index("--model") + 1]
    assert model == grid.READER_MODEL
    assert model.startswith("claude-")


def test_the_reader_runs_where_no_instruction_file_can_be_discovered():
    assert grid.instruction_files_above(grid.reader_cwd()) == []


def test_the_instruction_file_guard_finds_a_planted_file(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("answer key: -34.2")
    inner = tmp_path / "a" / "b"
    inner.mkdir(parents=True)
    assert grid.instruction_files_above(inner) == [tmp_path / "CLAUDE.md"]


def test_a_cli_reply_parses_into_text_model_and_token_counts():
    reply = grid.parse_cli_output(_cli_output())
    assert reply.text.startswith('{"reported": false')
    assert reply.model == grid.READER_MODEL
    assert (reply.input_tokens, reply.output_tokens) == (120, 8)
    assert reply.cost_usd == pytest.approx(0.00103)


def test_a_cli_error_is_a_reader_failure_not_an_answer():
    with pytest.raises(grid.ReaderError):
        grid.parse_cli_output(_cli_output(is_error=True, result="rate limited"))


def test_a_reply_from_any_other_model_is_refused():
    other = {"claude-sonnet-4-6": {"inputTokens": 120, "outputTokens": 8}}
    with pytest.raises(grid.ReaderError, match="claude-sonnet-4-6"):
        grid.parse_cli_output(_cli_output(modelUsage=other))


# -- choosing and running --------------------------------------------------------------------


def _questions(kind: K, n: int) -> list[Question]:
    return [Question(qid=f"{kind.value}-{i:03d}", kind=kind, text="q") for i in range(n)]


def test_the_pilot_is_the_first_two_of_every_kind_in_file_order():
    everything = [q for kind in K for q in _questions(kind, 5)]
    picked = grid.pilot(everything)
    assert [q.qid for q in picked] == [
        f"{kind.value}-{i:03d}" for kind in K for i in range(grid.PILOT_PER_KIND)
    ]


def test_the_reader_is_handed_exactly_what_the_cell_builds(corpus, tmp_path):
    seen: list[str] = []

    def reader(prompt: str) -> grid.Reply:
        seen.append(prompt)
        return _reply("{}")

    grid.run_cell("D", [ABSENCE, LOOKUP], corpus, tmp_path, reader)
    assert sorted(seen) == sorted(cells.build_d(q, corpus).prompt for q in (ABSENCE, LOOKUP))


def test_a_resumed_run_never_asks_a_question_twice(corpus, tmp_path):
    asked: list[str] = []

    def reader(prompt: str) -> grid.Reply:
        asked.append(prompt)
        return _reply('{"reported": false, "value": null, "citations": []}')

    grid.run_cell("D", [ABSENCE, LOOKUP], corpus, tmp_path, reader)
    grid.run_cell("D", [ABSENCE, LOOKUP], corpus, tmp_path, reader)
    assert len(asked) == 2
    assert set(grid.load_answers(tmp_path)) == {"B-001", "A-001"}


def test_a_reader_failure_is_retried_later_not_scored_as_the_cells_mistake(corpus, tmp_path):
    def broken(prompt: str) -> grid.Reply:
        raise grid.ReaderError("rate limited")

    grid.run_cell("D", [ABSENCE], corpus, tmp_path, broken)
    assert grid.load_answers(tmp_path) == {}
    assert "rate limited" in (tmp_path / "errors.jsonl").read_text()


def test_the_record_carries_what_was_delivered_and_what_it_cost(corpus, tmp_path):
    grid.run_cell("D", [ABSENCE], corpus, tmp_path, lambda prompt: _reply("{}"))
    record = grid.load_answers(tmp_path)["B-001"]
    built = cells.build_d(ABSENCE, corpus)
    assert record["cell"] == "D"
    assert record["route"] == built.route
    assert record["tokens_delivered"] == built.tokens
    assert record["prompt_sha256"] == grid.sha256(built.prompt)
    assert record["model"] == grid.READER_MODEL
    assert record["input_tokens"] == 100


REFUSAL = (
    "API Error: Claude Code is unable to respond to this request, which appears to violate "
    "our Usage Policy (https://www.anthropic.com/legal/aup)."
)


def test_a_usage_policy_refusal_is_its_own_error():
    with pytest.raises(grid.Refused):
        grid.parse_cli_output(_cli_output(is_error=True, result=REFUSAL))
    assert issubclass(grid.Refused, grid.ReaderError)


def test_a_refusal_is_the_cells_answer_and_is_scored_wrong(corpus, tmp_path):
    """D-008 was refused three times on ordinary colloid text. Martin, 2026-09-28: refuse it --
    count it wrong in the cell, keep it in the denominator, never ask again."""

    def refusing(prompt: str) -> grid.Reply:
        raise grid.Refused(REFUSAL)

    counts = grid.run_cell("D", [ABSENCE], corpus, tmp_path, refusing)
    record = grid.load_answers(tmp_path)["B-001"]
    assert record["refused"] is True
    assert counts["refused"] == 1
    report = grid.score_run(tmp_path, [_absence_key()], corpus)
    assert report.complete is True
    assert [s.correct for s in report.scored] == [False]
    assert "refused 1: B-001" in report.text


def test_a_refusal_logged_as_a_failure_earlier_is_recorded_without_asking_again(corpus, tmp_path):
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "errors.jsonl").write_text(
        json.dumps({"qid": "B-001", "error": f"reader failed: {REFUSAL}", "at": "x"}) + "\n"
    )
    asked: list[str] = []

    def reader(prompt: str) -> grid.Reply:
        asked.append(prompt)
        return _reply("{}")

    grid.run_cell("D", [ABSENCE], corpus, tmp_path, reader)
    assert asked == []
    assert grid.load_answers(tmp_path)["B-001"]["refused"] is True


# -- scoring a run ---------------------------------------------------------------------------


def _absence_key() -> AnswerKey:
    return AnswerKey(
        qid="B-001",
        kind=K.b,
        fields=(("pmcid", "PMCAAA"), ("answer_reported", "False"), ("answer_value", "")),
    )


def _lookup_key() -> AnswerKey:
    return AnswerKey(qid="A-001", kind=K.a, fields=(("pmcid", "PMCBBB"), ("answer_value", "-12.0")))


def test_the_score_names_questions_asked_but_never_answered(corpus, tmp_path):
    def reader(prompt: str) -> grid.Reply:
        if "PMCBBB" in prompt.split("EVIDENCE", 1)[0]:
            raise grid.ReaderError("timed out")
        return _reply('{"reported": false, "value": null, "citations": []}')

    grid.run_cell("D", [ABSENCE, LOOKUP], corpus, tmp_path, reader)
    report = grid.score_run(tmp_path, [_absence_key(), _lookup_key()], corpus)
    assert "answered 1 of 2" in report.text
    assert report.complete is False


def test_a_run_with_kind_e_reports_recall_per_true_verdict(corpus, tmp_path):
    pair = Question(
        qid="E-PMCAAA-r1__PMCBBB-r1",
        kind=K.e,
        text="May PMCAAA-r1 be compared with PMCBBB-r1?",
        scope=("PMCAAA", "PMCBBB"),
        target=(("row_id_a", "PMCAAA-r1"), ("row_id_b", "PMCBBB-r1")),
    )
    key = AnswerKey(qid=pair.qid, kind=K.e, fields=(("verdict", "comparable"),))
    grid.run_cell("D", [pair], corpus, tmp_path, lambda p: _reply('{"verdict": "not_comparable"}'))
    report = grid.score_run(tmp_path, [key], corpus)
    assert "D\tcomparable\t1\t0\t0.000" in report.text
    assert (tmp_path / "verdicts.tsv").read_text().startswith(scoring.VERDICT_HEADER)


def test_scoring_goes_through_the_committed_scorer(corpus, tmp_path):
    grid.run_cell(
        "D",
        [ABSENCE],
        corpus,
        tmp_path,
        lambda prompt: _reply('{"reported": true, "value": 150, "citations": []}'),
    )
    report = grid.score_run(tmp_path, [_absence_key()], corpus)
    expected = scoring.score_one(
        scoring.parse_answer("B-001", "D", '{"reported": true, "value": 150, "citations": []}'),
        _absence_key(),
        corpus,
    )
    assert [s.fabricated for s in report.scored] == [expected.fabricated] == [True]
    assert report.complete is True
    assert (tmp_path / "scored.jsonl").is_file()
    assert (tmp_path / "scores.tsv").read_text().startswith(scoring.HEADER)
