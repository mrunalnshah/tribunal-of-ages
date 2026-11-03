"""Structured LLM calls, with retries and provider fallback hidden inside.

Callers say *what* they want (a Pydantic schema and a model tier) and get a validated
object back. Rate limits, timeouts, malformed JSON and outages are handled here, so no
other module ever deals with them. The only error that escapes is LLMUnavailable.
"""

import logging
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import openai
from pydantic import BaseModel

from tribunal.telemetry import OpenAI

log = logging.getLogger(__name__)
Tier = Literal["fast", "smart"]
TRANSIENT = (openai.RateLimitError, openai.APIConnectionError, openai.InternalServerError)


class LLMUnavailable(Exception):
    """No configured provider produced a valid answer.

    When every provider was only rate-limited or out of quota, `retry_after` is the seconds
    until the soonest one said it would answer again. When anything else went wrong, it's None.
    """

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    api_key: str
    fast_model: str
    smart_model: str
    reasoning_effort: str | None = None  # for reasoning models: "low" keeps them quick and cheap
    cap_field: str = "max_completion_tokens"  # this API's name for the cap on an answer
    cases_per_day: int = 0  # free cases a day this provider adds: an estimate, for capacity


@dataclass
class Usage:
    """What one case cost. Give every call for a case the same Usage, then read it."""

    tokens: int = 0
    provider: str = ""  # who answered the last call
    fallback: bool = False  # whether a backup provider answered any call

    def meta(self) -> dict[str, str]:
        fallback = str(int(self.fallback))
        return {"tokens": str(self.tokens), "provider": self.provider, "fallback": fallback}


class ProviderState(BaseModel):
    name: str
    model: str
    ready: bool  # False while it's resting, out of quota


class LLMClient:
    def __init__(
        self,
        providers: list[Provider],
        timeout: float = 30.0,
        max_wait: float = 20.0,
        max_tokens: dict[str, int] | None = None,
        daily_tokens: int | None = None,
        clock: Callable[[], float] = time.time,
    ):
        """`max_tokens` caps each answer per tier, reasoning included. `daily_tokens` refuses
        every call for the rest of the day (UTC) once that many tokens have been used."""
        if not providers:
            raise ValueError("No LLM provider: set GROQ_API_KEY, GEMINI_API_KEY or OLLAMA_URL")
        self._providers = providers
        self._max_wait = max_wait
        self._max_tokens = max_tokens or {}
        self._daily_tokens = daily_tokens
        self._clock = clock
        self._day, self._spent = "", 0
        self._resting: dict[tuple[str, str], float] = {}  # (API, model) -> quota back at
        self._lock = threading.Lock()
        # max_retries=0: the SDK's own retries would hide failures from our fallback logic.
        self._clients = {
            p.name: OpenAI(base_url=p.base_url, api_key=p.api_key, timeout=timeout, max_retries=0)
            for p in providers
        }

    def complete_json[T: BaseModel](
        self,
        schema: type[T],
        system: str,
        user: str,
        *,
        tier: Tier = "fast",
        temperature: float = 0.0,
        check: Callable[[T], None] | None = None,
        usage: Usage | None = None,
    ) -> T:
        """Return a valid `schema` instance from the first provider that can produce one.

        `check` enforces rules Pydantic can't express: it raises ValueError to reject an
        answer. A rejected or malformed answer is sent back once with the error so the
        model can fix it; after that we move on to the next provider. If every provider is
        only out of quota, the error says when the soonest one expects to answer again.
        """
        self._check_budget()
        limits: list[float] = []  # how long each provider out of quota asked us to wait
        for index, provider in enumerate(self._providers):
            model = provider.fast_model if tier == "fast" else provider.smart_model
            quota = (provider.base_url, model)  # a quota belongs to one API's model
            resting = self._resting.get(quota, 0.0) - self._clock()
            if resting > 0:  # it ran out a moment ago: don't spend a request finding out again
                limits.append(resting)
                continue
            try:
                result = self._ask(
                    provider, model, schema, system, user, tier, temperature, check, usage
                )
                if usage:
                    usage.provider, usage.fallback = provider.name, usage.fallback or index > 0
                return result
            except openai.RateLimitError as err:
                log.warning("provider %s is out of quota for now: %s", provider.name, err)
                wait = _retry_after(err) or 60.0
                self._resting[quota] = self._clock() + wait
                limits.append(wait)
            except (openai.OpenAIError, ValueError) as err:
                log.warning("provider %s failed: %s", provider.name, err)
        busy = len(limits) == len(self._providers)  # only quotas: nothing is actually broken
        raise LLMUnavailable("every LLM provider failed", min(limits) if busy else None)

    def _ask[T: BaseModel](
        self,
        provider: Provider,
        model: str,
        schema: type[T],
        system: str,
        user: str,
        tier: Tier,
        temperature: float,
        check: Callable[[T], None] | None,
        usage: Usage | None,
    ) -> T:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        cap = self._max_tokens.get(tier)
        for _ in range(2):  # the first answer, then one repair attempt
            text = self._chat(provider, model, messages, temperature, cap, usage)
            try:
                result = schema.model_validate_json(_outer_json(text))
                if check:
                    check(result)  # a rejected answer gets the same one repair attempt
                return result
            except ValueError as err:  # pydantic's ValidationError is a ValueError too
                messages += [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": f"Invalid answer: {err}. Reply with fixed JSON."},
                ]
        raise ValueError(f"{provider.name} kept returning invalid JSON")

    def _chat(
        self,
        provider: Provider,
        model: str,
        messages: list,
        temperature: float,
        cap: int | None,
        usage: Usage | None,
    ) -> str:
        """One completion. Transient errors are retried with backoff; long waits are not."""
        options: dict[str, Any] = {}
        if cap:
            options[provider.cap_field] = cap  # reasoning tokens count toward it too
        if provider.reasoning_effort:
            options["extra_body"] = {"reasoning_effort": provider.reasoning_effort}
        for attempt in range(3):
            started = time.perf_counter()
            try:
                response = self._clients[provider.name].chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    response_format={"type": "json_object"},
                    **options,
                )
                tokens = getattr(getattr(response, "usage", None), "total_tokens", 0) or 0
                self._spend(tokens)
                if usage:
                    usage.tokens += tokens
                seconds = time.perf_counter() - started
                log.info("%s/%s answered in %.1fs", provider.name, model, seconds)
                return response.choices[0].message.content or ""
            except TRANSIENT as err:
                wait = _retry_after(err) or 2**attempt + random.random()
                if attempt == 2 or wait > self._max_wait:
                    raise  # still failing, or quota exhausted: let the next provider try
                log.info("%s: %s, retrying in %.1fs", provider.name, type(err).__name__, wait)
                time.sleep(wait)
        raise AssertionError("unreachable")

    def _check_budget(self) -> None:
        """Refuse every call once today's tokens are spent, until midnight UTC."""
        with self._lock:
            self._roll()
            if self._daily_tokens is not None and self._spent >= self._daily_tokens:
                tomorrow = 86400 - self._clock() % 86400
                raise LLMUnavailable("today's token budget is spent", tomorrow)

    def _spend(self, tokens: int) -> None:
        with self._lock:
            self._roll()
            self._spent += tokens

    def status(self) -> list[ProviderState]:
        """Each provider, in fallback order, and whether it's ready or resting out of quota."""
        now = self._clock()
        return [
            ProviderState(
                name=provider.name,
                model=provider.smart_model,
                ready=all(
                    self._resting.get((provider.base_url, model), 0.0) <= now
                    for model in (provider.fast_model, provider.smart_model)
                ),
            )
            for provider in self._providers
        ]

    def _roll(self) -> None:
        today = time.strftime("%Y-%m-%d", time.gmtime(self._clock()))
        if today != self._day:
            self._day, self._spent = today, 0


def _outer_json(text: str) -> str:
    """Models sometimes wrap JSON in prose or code fences; keep the outermost object."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("the answer contains no JSON object")
    return text[start : end + 1]


def _retry_after(err: Exception) -> float | None:
    """Seconds the provider asked us to wait (its Retry-After header), if it said."""
    response = getattr(err, "response", None)
    if response is None:
        return None
    try:
        return float(response.headers["retry-after"])
    except (AttributeError, KeyError, TypeError, ValueError):
        return None
