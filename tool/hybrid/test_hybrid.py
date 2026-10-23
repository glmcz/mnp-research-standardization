"""The hybrid agent's code: operations against independent truth, the guard, grounding, the arms.

unset VIRTUAL_ENV; uv run --with openpyxl python -m pytest -q -p no:cacheprovider tool/hybrid
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import agents  # noqa: E402
import ops  # noqa: E402
import questions  # noqa: E402
import run  # noqa: E402

from mnp.eval import grid  # noqa: E402


@pytest.fixture(scope="module")
def qs():
    return questions.build()


def test_every_reference_plan_reproduces_the_independent_truth(qs) -> None:
    for q in qs:
        plan = ops.Plan(q.ref_plan["op"], q.ref_plan["args"])
        assert plan.validate() == [], q.qid
        result = ops.execute(plan)
        verdict, reasons = ops.guard(plan, result)
        assert verdict == q.verdict, (q.qid, verdict, reasons)
        if q.caveat:
            assert q.caveat in reasons, (q.qid, reasons)
        if q.truth is None:
            continue
        got = run._scalar(result.value)
        tol = q.meta.get("tolerance_abs")
        if tol is not None:
            assert abs(got - q.truth) <= tol, (q.qid, got, q.truth)
        elif q.tolerance:
            assert abs(got - q.truth) <= q.tolerance * abs(q.truth), (q.qid, got, q.truth)


def test_the_question_never_states_its_own_answer(qs) -> None:
    for q in qs:
        if q.truth is not None and abs(q.truth) >= 1:
            assert not agents._matches(q.truth, agents.numbers_in(q.text)), q.qid


def test_a_plan_from_a_model_is_checked_before_it_runs() -> None:
    assert ops.Plan("bogus").validate() == ["unknown op 'bogus'"]
    assert ops.Plan("study_count", {"period": 2015, "x": 1}).validate() == ["unknown arg 'x'"]
    assert ops.Plan("study_count", {}).validate() == ["missing arg 'period'"]
    # the pilot's planner wrote names a person would use; the registry's values are enforced
    loose = ops.Plan("completeness", {"dataset": "soil microplastic", "field": "sampling method"})
    assert len(loose.validate()) == 2
    assert ops.Plan("completeness", {"dataset": "soil", "field": "method"}).validate() == []


def test_grounding_rejects_a_number_the_result_does_not_hold() -> None:
    allowed = [93.7, 0.081, 3.27]
    assert (
        agents.ungrounded({"value": 93.7, "answer": "about 94 times, 8.1 % of papers"}, allowed)
        == []
    )
    assert agents.ungrounded({"value": 93.7, "answer": "a rise of 120 times"}, allowed) == [120.0]
    assert agents.ungrounded({"value": 5.0, "answer": ""}, allowed) == [5.0]


class FakeReader:
    """Plays the planner and the composer; the composer slips in a number the result lacks."""

    def __init__(self, plan: dict, slip: bool) -> None:
        self.plan, self.slip, self.prompts = plan, slip, []

    def __call__(self, prompt: str) -> grid.Reply:
        self.prompts.append(prompt)
        if prompt.startswith("QUESTION") and "OPERATIONS" in prompt:
            text = json.dumps(self.plan)
        else:
            n = 777 if self.slip else 3
            text = json.dumps(
                {
                    "value": n,
                    "verdict": "allow",
                    "caveats": [],
                    "answer": f"they differ about {n} times",
                }
            )
        return grid.Reply(text=text, model="fake", input_tokens=10, output_tokens=5)


def test_the_hybrid_sets_value_and_verdict_in_code_and_drops_invented_numbers(qs) -> None:
    q = next(x for x in qs if x.qid == "T1")
    fake = FakeReader(q.ref_plan, slip=True)
    rec = run.hybrid(q, ask=fake)
    h, hg = rec["H"]["final"], rec["Hg"]["final"]
    assert rec["H"]["draft_ungrounded"] == [777.0, 777.0]
    assert h["verdict"] == "caveat" and h["caveats"] == ["composition_shift"]
    assert h["value"] == pytest.approx(q.truth, rel=0.05)
    assert "777" not in h["answer"]
    assert hg["verdict"] == "allow"  # without the guard the model's own verdict stands
    assert any("Rewrite" in p for p in fake.prompts)


def test_an_invalid_plan_is_retried_once_then_counted_as_an_abstention(qs) -> None:
    q = qs[0]
    rec = run.hybrid(q, ask=FakeReader({"op": "invent_a_number"}, slip=False))
    assert rec["answer"] is None and rec["abstained"] == "invalid plan"


def test_scoring_needs_the_flag_the_value_and_the_named_reason(qs) -> None:
    q = next(x for x in qs if x.qid == "D1")
    good = {"answer": {"value": 1.0, "verdict": "refuse", "caveats": ["held_twice"]}}
    wrong_reason = {"answer": {"value": 1.0, "verdict": "refuse", "caveats": ["method_mix"]}}
    naive = {"answer": {"value": 1.0, "verdict": "allow", "caveats": []}}
    assert run.score_one(q, good)["correct"]
    assert not run.score_one(q, wrong_reason)["correct"]
    assert not run.score_one(q, naive)["correct"]


def test_mcnemar_counts_only_discordant_pairs() -> None:
    m = run.mcnemar([True, True, False, False], [True, False, True, False])
    assert (m["only_this_right"], m["only_H_right"]) == (1, 1) and m["p"] == 1.0
