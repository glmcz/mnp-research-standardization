"""tool/run_demo_reader.py asks every case's questions once, into its own run, and resumes."""

import importlib.util
import json

import pandas as pd
import pytest

from mnp import config, runs
from mnp.demo import cases, questions
from mnp.eval import cells, grid

_spec = importlib.util.spec_from_file_location(
    "run_demo_reader", config.ROOT / "tool" / "run_demo_reader.py"
)
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)

TABLE = config.OUT / "tables" / "d1_zeta_table.csv"


@pytest.fixture
def table():
    if not TABLE.is_file():
        pytest.skip("no committed D1 table")
    return pd.read_csv(TABLE)


def test_every_case_question_is_gathered_once(table):
    qs, keys = tool.demo_questions(table)
    expected = sum(len(questions.questions_for(c, table)) for c in cases.CASES)
    assert len(qs) == len(keys) == expected
    assert len({q.qid for q in qs}) == len(qs)
    assert [q.qid for q in qs] == [k.qid for k in keys]


def test_a_run_asks_each_question_once_and_resumes_without_asking_again(
    table, tmp_path, monkeypatch
):
    monkeypatch.setattr(config, "DATA_INTERIM", tmp_path / "interim")
    monkeypatch.setattr(runs, "code_commit", lambda: ("abc1234", False))
    monkeypatch.setattr(grid, "cli_version", lambda: "test")
    asked = []

    def fake(prompt):
        asked.append(prompt)
        return grid.Reply(
            text='{"answer": "not reported", "citations": []}', model=grid.READER_MODEL
        )

    corpus = cells.load_corpus()
    tool.ask("D", "demo-celld-test", table, corpus, jobs=1, reader=fake)
    n = len(tool.demo_questions(table)[0])
    assert len(asked) == n
    tool.ask("D", "demo-celld-test", table, corpus, jobs=1, reader=fake)
    assert len(asked) == n, "a resumed run asks nothing it already answered"
    manifest = json.loads((runs.run_dir("demo-celld-test") / "manifest.json").read_text())
    assert manifest["model"] == grid.READER_MODEL
