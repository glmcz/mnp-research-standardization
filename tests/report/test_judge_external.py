"""An external judge: a different model family, reached over an API, with no filesystem.

Two Claude judges on identical cases agreed at kappa 0.11 — barely above chance — and split
systematically on the contested temperature rule. A judge drawn from the same family as the
extractor also carries self-preference bias (a model rating its own output more highly).
Both problems point the same way: bring in a judge that shares neither the family nor the
machine.
"""

from mnp.report import judge_external as jx

CASE = {
    "case": "c1",
    "pmcid": "PMC1",
    "field": "temperature_C",
    "reading_A": 25.0,
    "reading_B": None,
}
ARTICLE = "Particles were incubated at 25 C in a dry bath prior to TRPS analysis."


class FakeClient:
    """Stands in for the API; records what it was asked."""

    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def complete_json(self, system, user, **kw):
        self.calls.append({"system": system, "user": user, **kw})
        # LLMClient returns (data, completion) — the fake must match, or the tests pass
        # against an interface that does not exist.
        return self.reply, object()


def test_the_prompt_contains_the_article_and_the_two_readings():
    c = FakeClient({"verdict": "B", "quote": "incubated at 25 C", "reasoning": "incubation"})
    jx.judge_case(c, CASE, ARTICLE)
    user = c.calls[0]["user"]
    assert ARTICLE in user
    assert "25.0" in user and "not reported" in user.lower()


def test_the_prompt_never_reveals_which_reading_is_which():
    c = FakeClient({"verdict": "A", "quote": "x", "reasoning": ""})
    jx.judge_case(c, CASE, ARTICLE)
    blob = (c.calls[0]["system"] + c.calls[0]["user"]).lower()
    assert "gold" not in blob
    assert "extraction" not in blob


def test_abstention_is_offered_explicitly():
    """A judge that cannot abstain will manufacture a decision."""
    c = FakeClient({"verdict": "ambiguous", "quote": "", "reasoning": ""})
    v = jx.judge_case(c, CASE, ARTICLE)
    assert "ambiguous" in c.calls[0]["system"].lower()
    assert v["verdict"] == "ambiguous"


def test_a_verdict_outside_the_allowed_set_is_rejected():
    c = FakeClient({"verdict": "probably A", "quote": "incubated at 25 C", "reasoning": ""})
    v = jx.judge_case(c, CASE, ARTICLE)
    assert v["verdict"] == "unparseable"


def test_a_quote_not_in_the_article_is_marked_ungrounded():
    c = FakeClient({"verdict": "A", "quote": "a sentence never written", "reasoning": ""})
    v = jx.judge_case(c, CASE, ARTICLE)
    assert v["grounded"] is False


def test_a_grounded_verdict_is_marked_so():
    c = FakeClient({"verdict": "B", "quote": "incubated at 25 C", "reasoning": "incubation"})
    v = jx.judge_case(c, CASE, ARTICLE)
    assert v["grounded"] is True and v["verdict"] == "B"


def test_running_both_orders_swaps_the_readings():
    c = FakeClient({"verdict": "A", "quote": "incubated at 25 C", "reasoning": ""})
    jx.run_case_both_orders(c, CASE, ARTICLE)
    first, second = c.calls[0]["user"], c.calls[1]["user"]
    assert first != second
    assert first.index("25.0") != second.index("25.0")


def test_a_bare_dict_return_is_also_accepted():
    """Anything that returns parsed JSON can drive the harness, not just LLMClient."""

    class Bare:
        def complete_json(self, system, user, **kw):
            return {"verdict": "B", "quote": "incubated at 25 C", "reasoning": ""}

    assert jx.judge_case(Bare(), CASE, ARTICLE)["verdict"] == "B"


def test_a_failed_call_is_recorded_not_silently_dropped():
    class Broken:
        def complete_json(self, *a, **k):
            raise RuntimeError("all models failed")

    v = jx.judge_case(Broken(), CASE, ARTICLE)
    assert v["verdict"] == "error"
    assert "all models failed" in v["error"]
