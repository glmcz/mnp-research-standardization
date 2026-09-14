import hashlib
import json
from types import SimpleNamespace

import httpx
import openai
import pytest

from mnp.extract import llm

# -- pure text helpers ---------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ('<think>ponder</think>{"a": 1}', '{"a": 1}'),
        ('<think>\nmulti\nline\n</think>\n\n{"a": 1}', '{"a": 1}'),
        ('<thinking>x</thinking>{"a": 1}', '{"a": 1}'),
        ('{"a": 1}', '{"a": 1}'),
        ('<think>never closed {"a": 1}', ""),
        ('<think>a</think>{"x": 1}<think>b</think>', '{"x": 1}'),
    ],
)
def test_strip_think(raw, expected):
    assert llm.strip_think(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ('{"a": 1}', {"a": 1}),
        ('Sure, here it is:\n{"a": 1}\nHope this helps.', {"a": 1}),
        ('```json\n{"a": [1, 2]}\n```', {"a": [1, 2]}),
        ('{"s": "brace } inside", "n": {"k": "v"}}', {"s": "brace } inside", "n": {"k": "v"}}),
        ('{"s": "esc \\" quote }"}', {"s": 'esc " quote }'}),
        ('{"a": 1} {"b": 2}', {"a": 1}),
    ],
)
def test_first_json_object(raw, expected):
    assert json.loads(llm.first_json_object(raw)) == expected


@pytest.mark.parametrize("raw", ["no json here", '{"a": 1', "", '["list", "only"]'])
def test_first_json_object_rejects_missing_or_unbalanced(raw):
    with pytest.raises(llm.ParseError):
        llm.first_json_object(raw)


def test_cache_key_is_sha256_of_model_system_user():
    k = llm.cache_key("m", "s", "u")
    assert k == hashlib.sha256(b"m\x00s\x00u").hexdigest()
    assert llm.cache_key("m2", "s", "u") != k


# -- fake OpenAI-compatible client ---------------------------------------------


def _status_error(status: int, message: str = "boom") -> openai.APIStatusError:
    request = httpx.Request("POST", "https://example.invalid/chat/completions")
    response = httpx.Response(status, request=request, json={"error": {"message": message}})
    return openai.APIStatusError(message, response=response, body=None)


class FakeClient:
    """Each script entry is either a str (content) or an Exception to raise."""

    def __init__(self, script):
        self.script = list(script)
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=item))],
            model=kwargs["model"],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )


def _client(tmp_path, script, chain=("m1", "m2")):
    fake = FakeClient(script)
    return fake, llm.LLMClient(fake, cache_dir=tmp_path, chain=list(chain), sleep=lambda s: None)


def test_complete_sends_temperature_zero_and_json_object_format(tmp_path):
    fake, c = _client(tmp_path, ['{"ok": true}'])
    out = c.complete("SYS", "USR")
    assert out.text == '{"ok": true}'
    assert out.model == "m1"
    assert out.cached is False
    call = fake.calls[0]
    assert call["model"] == "m1"
    assert call["temperature"] == 0
    assert call["response_format"] == {"type": "json_object"}
    assert call["messages"] == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "USR"},
    ]


def test_429_moves_to_the_next_model(tmp_path):
    fake, c = _client(tmp_path, [_status_error(429), '{"ok": 1}'])
    out = c.complete("s", "u")
    assert out.model == "m2"
    assert [call["model"] for call in fake.calls] == ["m1", "m2"]
    assert [a["status"] for a in out.attempts] == [429, 200]


def test_5xx_moves_to_the_next_model(tmp_path):
    fake, c = _client(tmp_path, [_status_error(502), '{"ok": 1}'])
    assert c.complete("s", "u").model == "m2"


def test_400_mentioning_response_format_retries_same_model_without_it(tmp_path):
    fake, c = _client(
        tmp_path,
        [_status_error(400, "response_format is not supported by this model"), '{"ok": 1}'],
    )
    out = c.complete("s", "u")
    assert out.model == "m1"
    assert "response_format" in fake.calls[0]
    assert "response_format" not in fake.calls[1]


def test_exhausted_chain_raises_with_every_attempt_named(tmp_path):
    fake, c = _client(tmp_path, [_status_error(429), _status_error(503)])
    with pytest.raises(llm.LLMError) as exc:
        c.complete("s", "u")
    assert "m1" in str(exc.value) and "m2" in str(exc.value)
    assert "429" in str(exc.value) and "503" in str(exc.value)


def test_connection_errors_also_fall_through(tmp_path):
    err = openai.APIConnectionError(request=httpx.Request("POST", "https://x.invalid"))
    fake, c = _client(tmp_path, [err, '{"ok": 1}'])
    assert c.complete("s", "u").model == "m2"


def test_second_identical_call_is_served_from_cache(tmp_path):
    fake, c = _client(tmp_path, ['{"ok": 1}'])
    first = c.complete("s", "u")
    second = c.complete("s", "u")
    assert second.text == first.text
    assert second.cached is True
    assert len(fake.calls) == 1
    key = llm.cache_key("m1", "s", "u")
    entry = json.loads((tmp_path / f"{key}.json").read_text())
    assert entry["text"] == '{"ok": 1}'
    assert entry["model"] == "m1"


def test_cache_is_keyed_on_the_model_that_would_be_called(tmp_path):
    fake, c = _client(tmp_path, ['{"a": 1}'])
    c.complete("s", "u")
    other = llm.LLMClient(FakeClient(['{"b": 2}']), cache_dir=tmp_path, chain=["m9"])
    assert json.loads(other.complete("s", "u").text) == {"b": 2}


def test_complete_json_strips_think_and_parses(tmp_path):
    fake, c = _client(tmp_path, ['<think>hmm</think>\n```json\n{"a": 1}\n```'])
    data, completion = c.complete_json("s", "u")
    assert data == {"a": 1}
    assert completion.model == "m1"


def test_complete_json_nudges_once_on_invalid_json(tmp_path):
    fake, c = _client(tmp_path, ["I cannot help with that.", '{"a": 2}'])
    data, _ = c.complete_json("s", "u")
    assert data == {"a": 2}
    assert len(fake.calls) == 2
    assert "valid JSON" in fake.calls[1]["messages"][1]["content"]


def test_complete_json_moves_to_the_next_model_when_one_only_reasons(tmp_path):
    """nemotron-3-super:free returns untagged chain-of-thought as content and never
    reaches the JSON. Nudging it again is wasted; the next model gets a turn."""
    fake, c = _client(tmp_path, ["We need to extract...", "Let me think again...", '{"a": 3}'])
    data, completion = c.complete_json("s", "u")
    assert data == {"a": 3}
    assert completion.model == "m2"
    assert [call["model"] for call in fake.calls] == ["m1", "m1", "m2"]
    assert [a["status"] for a in completion.attempts] == [
        200, "no_json", 200, "no_json_after_nudge", 200,
    ]  # fmt: skip


def test_complete_json_gives_up_only_after_every_model_was_nudged(tmp_path):
    fake, c = _client(tmp_path, ["nope", "still nope", "nope", "nope"])
    with pytest.raises(llm.ParseError) as exc:
        c.complete_json("s", "u")
    assert len(fake.calls) == 4
    assert "m1" in str(exc.value) and "m2" in str(exc.value)


def test_parse_error_is_an_llm_error():
    assert issubclass(llm.ParseError, llm.LLMError)


def test_extra_body_is_forwarded_on_every_call(tmp_path):
    fake = FakeClient(['{"ok": 1}'])
    c = llm.LLMClient(
        fake, cache_dir=tmp_path, chain=["m1"], extra_body={"reasoning": {"exclude": True}}
    )
    c.complete("s", "u")
    assert fake.calls[0]["extra_body"] == {"reasoning": {"exclude": True}}
    assert fake.calls[0]["max_tokens"] >= 8000


def test_complete_json_rejects_a_top_level_array(tmp_path):
    fake, c = _client(tmp_path, ["[1, 2]", '{"a": 1}'])
    data, _ = c.complete_json("s", "u")
    assert data == {"a": 1}


def test_from_env_builds_the_chain_from_openrouter_vars(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_KEY", "sk-test")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://openrouter.example/api/v1")
    monkeypatch.setenv("OPENROUTER_MODEL", "head:free")
    monkeypatch.setenv("OPENROUTER_FALLBACK_MODELS", "f1:free, f2:free")
    c = llm.from_env(cache_dir=tmp_path)
    assert c.chain == ["head:free", "f1:free", "f2:free"]
    assert c.client.max_retries == 0
    assert str(c.client.base_url).startswith("https://openrouter.example/api/v1")


def test_from_env_model_override_replaces_the_head_only(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_KEY", "sk-test")
    monkeypatch.setenv("OPENROUTER_MODEL", "head:free")
    monkeypatch.setenv("OPENROUTER_FALLBACK_MODELS", "f1:free")
    c = llm.from_env(cache_dir=tmp_path, model="paid/model")
    assert c.chain == ["paid/model", "f1:free"]


def test_from_env_prefers_mnp_model_chain_and_excludes_reasoning_on_openrouter(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("OPENROUTER_KEY", "sk-test")
    monkeypatch.setenv("OPENROUTER_MODEL", "head:free")
    monkeypatch.setenv("OPENROUTER_FALLBACK_MODELS", "f1:free")
    monkeypatch.setenv("MNP_MODEL_CHAIN", "a:free, b:free")
    c = llm.from_env(cache_dir=tmp_path)
    assert c.chain == ["a:free", "b:free"]
    assert c.extra_body == {"reasoning": {"exclude": True}}
    assert llm.from_env(cache_dir=tmp_path, model="paid").chain == ["paid", "b:free"]
    assert llm.from_env(cache_dir=tmp_path, chain=["x"]).chain == ["x"]


def test_from_env_requires_a_key(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_KEY", raising=False)
    with pytest.raises(llm.MissingConfig):
        llm.from_env(cache_dir=tmp_path)
