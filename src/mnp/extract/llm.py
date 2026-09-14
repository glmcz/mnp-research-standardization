"""OpenAI-compatible chat client with a model fallback chain and a disk cache.

Mirrors sensei_core/llm_groq.py in shape (OpenAI SDK, max_retries=0, walk the
chain on 429/5xx) without its Postgres bookkeeping. Known pitfalls handled
here rather than in callers: reasoning models leak `<think>` blocks into
content, some free endpoints 400 on `response_format`, and chains change
under you — so every reply is cached by (model, system, user).
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import openai
from openai import OpenAI

from mnp import config
from mnp.config import MissingConfig

__all__ = [
    "LLMClient",
    "LLMError",
    "MissingConfig",
    "ParseError",
    "cache_key",
    "first_json_object",
    "from_env",
    "strip_think",
]


class LLMError(RuntimeError):
    """Every model in the chain failed."""


class ParseError(LLMError, ValueError):
    """No model in the chain produced a usable JSON object."""


_THINK_CLOSED = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", re.DOTALL)
_THINK_OPEN = re.compile(r"<think(?:ing)?>.*\Z", re.DOTALL)


def strip_think(text: str) -> str:
    """Remove `<think>…</think>` blocks; an unterminated one swallows the rest."""
    text = _THINK_CLOSED.sub("", text)
    text = _THINK_OPEN.sub("", text)
    return text.strip()


def first_json_object(text: str) -> str:
    """The first brace-balanced `{…}` in text, string- and escape-aware."""
    start = text.find("{")
    if start < 0:
        raise ParseError("no JSON object in reply")
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ParseError("unbalanced JSON object in reply")


def cache_key(model: str, system: str, user: str) -> str:
    return hashlib.sha256(f"{model}\x00{system}\x00{user}".encode()).hexdigest()


@dataclass
class Completion:
    text: str
    model: str
    cached: bool
    attempts: list[dict] = field(default_factory=list)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class LLMClient:
    def __init__(
        self,
        client,
        *,
        cache_dir: Path,
        chain: list[str],
        sleep: Callable[[float], None] = time.sleep,
        max_tokens: int = 16_000,
        extra_body: dict | None = None,
    ) -> None:
        if not chain:
            raise MissingConfig("model chain is empty")
        self.client = client
        self.cache_dir = Path(cache_dir)
        self.chain = list(chain)
        self.sleep = sleep
        self.max_tokens = max_tokens
        # OpenRouter: {"reasoning": {"exclude": True}} keeps chain-of-thought out of
        # `content`. Reasoning models otherwise return it as plain text, untagged.
        self.extra_body = extra_body

    # -- one call --------------------------------------------------------------

    def _call(self, model: str, system: str, user: str, json_mode: bool, temperature: float):
        kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": self.max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if self.extra_body:
            kwargs["extra_body"] = self.extra_body
        return self.client.chat.completions.create(**kwargs)

    class _ModelFailed(Exception):
        pass

    def _complete_one(
        self,
        model: str,
        system: str,
        user: str,
        attempts: list[dict],
        json_mode: bool,
        temperature: float,
    ) -> Completion:
        """One model: cache hit, or up to two calls (the second only for a response_format 400)."""
        path = self.cache_dir / f"{cache_key(model, system, user)}.json"
        if path.is_file():
            entry = json.loads(path.read_text())
            return Completion(entry["text"], entry["model"], True, attempts)
        use_json = json_mode
        for _ in range(2):
            try:
                resp = self._call(model, system, user, use_json, temperature)
            except openai.APIStatusError as e:
                status = e.status_code
                attempts.append({"model": model, "status": status, "error": str(e)[:300]})
                if status == 400 and use_json and "response_format" in str(e).lower():
                    use_json = False
                    continue
                if status == 429:
                    self.sleep(1.0)
                raise self._ModelFailed() from e
            except openai.APIConnectionError as e:
                attempts.append({"model": model, "status": None, "error": str(e)[:300]})
                raise self._ModelFailed() from e
            text = resp.choices[0].message.content or ""
            usage = getattr(resp, "usage", None)
            attempts.append({"model": model, "status": 200})
            path.write_text(
                json.dumps(
                    {
                        "model": model,
                        "served_model": getattr(resp, "model", model),
                        "text": text,
                        "json_mode": use_json,
                        "created": datetime.now(UTC).isoformat(timespec="seconds"),
                    }
                )
            )
            return Completion(
                text,
                model,
                False,
                attempts,
                getattr(usage, "prompt_tokens", None),
                getattr(usage, "completion_tokens", None),
            )
        raise self._ModelFailed()

    @staticmethod
    def _summary(attempts: list[dict]) -> str:
        return "; ".join(f"{a['model']} {a['status']}" for a in attempts)

    def complete(
        self, system: str, user: str, *, json_mode: bool = True, temperature: float = 0
    ) -> Completion:
        """Walk the chain until one model answers. Cached per (model, system, user)."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        attempts: list[dict] = []
        for model in self.chain:
            try:
                return self._complete_one(model, system, user, attempts, json_mode, temperature)
            except self._ModelFailed:
                continue
        raise LLMError(f"all models failed: {self._summary(attempts)}")

    # -- JSON ------------------------------------------------------------------

    @staticmethod
    def _parse(text: str) -> dict | None:
        try:
            obj = json.loads(first_json_object(strip_think(text)))
        except (ParseError, json.JSONDecodeError):
            return None
        return obj if isinstance(obj, dict) else None

    def complete_json(
        self, system: str, user: str, *, json_mode: bool = True, temperature: float = 0
    ) -> tuple[dict, Completion]:
        """A JSON object from the first model in the chain that produces one.

        Per model: one call, then one nudge if the reply held no JSON object.
        A model that only reasons (content is chain-of-thought, no JSON) is
        abandoned for the next one instead of being nudged forever.
        """
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        attempts: list[dict] = []
        nudged = (
            f"{user}\n\nYour previous reply was not valid JSON. "
            "Return exactly one JSON object and nothing else."
        )
        for model in self.chain:
            for prompt, label in ((user, "no_json"), (nudged, "no_json_after_nudge")):
                try:
                    completion = self._complete_one(
                        model, system, prompt, attempts, json_mode, temperature
                    )
                except self._ModelFailed:
                    break
                data = self._parse(completion.text)
                if data is not None:
                    completion.attempts = attempts
                    return data, completion
                attempts.append({"model": model, "status": label})
        raise ParseError(f"no JSON object from any model: {self._summary(attempts)}")


def _split(csv: str | None) -> list[str]:
    return [m.strip() for m in (csv or "").split(",") if m.strip()]


def from_env(
    cache_dir: Path | None = None, model: str | None = None, chain: list[str] | None = None
) -> LLMClient:
    """Chain precedence: explicit `chain` > MNP_MODEL_CHAIN > [OPENROUTER_MODEL] +
    OPENROUTER_FALLBACK_MODELS. `model` always replaces the head."""
    key = config.require("OPENROUTER_KEY")
    base_url = config.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    if chain is None:
        chain = _split(config.getenv("MNP_MODEL_CHAIN"))
    if not chain:
        head = config.getenv("OPENROUTER_MODEL")
        chain = ([head] if head else []) + _split(config.getenv("OPENROUTER_FALLBACK_MODELS"))
    if model:
        chain = [model] + [m for m in chain[1:] if m != model]
    if not chain:
        raise MissingConfig("no model: set OPENROUTER_MODEL or MNP_MODEL_CHAIN, or pass --model")
    client = OpenAI(api_key=key, base_url=base_url, max_retries=0, timeout=300.0)
    extra_body = {"reasoning": {"exclude": True}} if "openrouter" in base_url else None
    return LLMClient(
        client, cache_dir=cache_dir or config.LLM_CACHE, chain=chain, extra_body=extra_body
    )
