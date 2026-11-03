import httpx2  # the HTTP library the OpenAI SDK uses since version 3
import openai
import pytest
from pydantic import BaseModel

from tribunal import llm as llm_module
from tribunal.llm import LLMClient, LLMUnavailable, Provider, Usage


class Answer(BaseModel):
    ok: bool


def rate_limited(wait_seconds: str) -> openai.RateLimitError:
    request = httpx2.Request("POST", "https://example.test")
    response = httpx2.Response(429, request=request, headers={"retry-after": wait_seconds})
    return openai.RateLimitError("slow down", response=response, body=None)


def connection_error() -> openai.APIConnectionError:
    return openai.APIConnectionError(request=httpx2.Request("POST", "https://example.test"))


class FakeOpenAI:
    """Stands in for openai.OpenAI. Each provider replays a script of answers or errors."""

    scripts: dict[str, list] = {}
    sent: list[dict] = []  # every request, as sent

    def __init__(self, base_url: str, **_):
        self.script = FakeOpenAI.scripts[base_url]
        self.chat = self.completions = self

    def create(self, **request):
        FakeOpenAI.sent.append(request)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        message = type("Message", (), {"content": step})
        usage = type("Usage", (), {"total_tokens": 100})
        choice = type("Choice", (), {"message": message})
        return type("Response", (), {"choices": [choice], "usage": usage})


def make_client(monkeypatch, **scripts: list) -> LLMClient:
    monkeypatch.setattr(llm_module, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(llm_module.time, "sleep", lambda seconds: None)  # no real waiting
    FakeOpenAI.scripts = scripts
    return LLMClient([Provider(name, name, "key", "fast", "smart") for name in scripts])


def test_retries_a_short_rate_limit(monkeypatch):
    llm = make_client(monkeypatch, groq=[rate_limited("2"), '{"ok": true}'])
    assert llm.complete_json(Answer, "system", "user").ok


def test_falls_back_when_the_quota_is_gone(monkeypatch):
    llm = make_client(monkeypatch, groq=[rate_limited("3600")], gemini=['{"ok": true}'])
    assert llm.complete_json(Answer, "system", "user").ok


def test_repairs_invalid_json_once(monkeypatch):
    llm = make_client(monkeypatch, groq=["Sure! Here you go", '```json\n{"ok": true}\n```'])
    assert llm.complete_json(Answer, "system", "user").ok


def test_raises_only_when_every_provider_fails(monkeypatch):
    llm = make_client(monkeypatch, groq=["nope", "still nope"], gemini=[connection_error()] * 3)
    with pytest.raises(LLMUnavailable) as failure:
        llm.complete_json(Answer, "system", "user")
    assert failure.value.retry_after is None  # something is broken, so no time to come back


def test_says_when_to_come_back_when_every_provider_is_out_of_quota(monkeypatch):
    llm = make_client(monkeypatch, groq=[rate_limited("3600")], gemini=[rate_limited("120")])
    with pytest.raises(LLMUnavailable) as failure:
        llm.complete_json(Answer, "system", "user")
    assert failure.value.retry_after == 120


def test_caps_each_answer_and_stops_for_the_day_when_the_tokens_run_out(monkeypatch):
    monkeypatch.setattr(llm_module, "OpenAI", FakeOpenAI)
    FakeOpenAI.scripts, FakeOpenAI.sent = {"groq": ['{"ok": true}', '{"ok": true}']}, []
    provider = Provider("groq", "groq", "key", "fast", "smart", reasoning_effort="low")
    llm = LLMClient([provider], max_tokens={"fast": 50}, daily_tokens=150)
    llm.complete_json(Answer, "system", "user")
    assert FakeOpenAI.sent[0]["max_completion_tokens"] == 50
    assert FakeOpenAI.sent[0]["extra_body"] == {"reasoning_effort": "low"}
    llm.complete_json(Answer, "system", "user")  # 200 tokens used: past the budget of 150
    with pytest.raises(LLMUnavailable) as caught:
        llm.complete_json(Answer, "system", "user")
    assert caught.value.retry_after is not None and caught.value.retry_after > 0


def test_a_spent_model_is_skipped_until_its_quota_returns(monkeypatch):
    monkeypatch.setattr(llm_module, "OpenAI", FakeOpenAI)
    FakeOpenAI.scripts = {"api": [rate_limited("3600"), '{"ok": true}', '{"ok": true}']}
    first = Provider("groq", "api", "k", "small", "big")
    spare = Provider("spare", "api", "k", "big", "small")  # the same API, models swapped
    llm = LLMClient([first, spare])
    assert llm.complete_json(Answer, "system", "user", tier="smart").ok  # big ran out: small
    assert llm.complete_json(Answer, "system", "user", tier="smart").ok  # big isn't asked again


def test_the_meter_says_what_a_case_cost_and_who_answered(monkeypatch):
    monkeypatch.setattr(llm_module, "OpenAI", FakeOpenAI)
    FakeOpenAI.scripts = {"groq": [rate_limited("3600")], "backup": ['{"ok": true}'] * 2}
    groq = Provider("groq", "groq", "k", "f", "s")
    backup = Provider("backup", "backup", "k", "f", "s")
    llm = LLMClient([groq, backup])
    usage = Usage()
    llm.complete_json(Answer, "system", "user", usage=usage)  # groq is out: backup answers
    llm.complete_json(Answer, "system", "user", usage=usage)  # groq is resting: not asked
    assert (usage.tokens, usage.provider, usage.fallback) == (200, "backup", True)
    states = [(state.name, state.ready) for state in llm.status()]
    assert states == [("groq", False), ("backup", True)]
