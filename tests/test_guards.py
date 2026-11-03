import asyncio

import pytest

from tribunal.guards import BodyLimit, Guard, RateLimited


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


def test_per_minute_limit_resets_after_a_minute():
    clock = Clock()
    guard = Guard(per_minute=2, per_day=100, clock=clock)
    guard.check("1.2.3.4")
    guard.check("1.2.3.4")
    with pytest.raises(RateLimited) as caught:
        guard.check("1.2.3.4")
    assert caught.value.retry_after > 0
    guard.check("5.6.7.8")  # other visitors are unaffected
    clock.now += 61
    guard.check("1.2.3.4")


def test_daily_budget_is_shared_by_everyone():
    guard = Guard(per_minute=10, per_day=2, clock=Clock())
    guard.check("a")
    guard.check("b")
    with pytest.raises(RateLimited):
        guard.check("c")


def test_visitors_are_counted_without_keeping_their_addresses():
    guard = Guard(per_minute=5, per_day=100, clock=Clock())
    guard.check("203.0.113.7")
    assert "203.0.113.7" not in repr(vars(guard))


def test_each_visitor_may_file_a_few_cases_a_day():
    clock = Clock()
    guard = Guard(per_minute=10, per_day=100, visitor_per_day=3, clock=clock)
    assert [guard.check("1.2.3.4") for _ in range(3)] == [2, 1, 0]
    with pytest.raises(RateLimited) as caught:
        guard.check("1.2.3.4")
    assert "tomorrow" in caught.value.reason and caught.value.retry_after > 0
    assert guard.check("5.6.7.8") == 2  # other visitors are unaffected
    clock.now += 86400
    assert guard.check("1.2.3.4") == 2  # a new day


def test_an_oversized_request_is_refused_before_it_is_read():
    async def app(scope, receive, send):
        while (await receive()).get("more_body"):
            pass
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    def status(headers: list, chunks: list[bytes]) -> int:
        sent: list[dict] = []

        async def receive():
            return {"type": "http.request", "body": chunks.pop(0), "more_body": bool(chunks)}

        async def send(message):
            sent.append(message)

        limited = BodyLimit(app, max_bytes=10, on_refuse=lambda: refusals.append(1))
        asyncio.run(limited({"type": "http", "headers": headers}, receive, send))
        return sent[0]["status"]

    refusals: list[int] = []
    assert status([(b"content-length", b"5")], [b"hello"]) == 200
    assert status([(b"content-length", b"999999")], [b"x"]) == 413  # refused from the header
    assert status([], [b"0123456789", b"more"]) == 413  # no length given: counted as it arrives
    assert len(refusals) == 2  # each refusal is counted, for the ledger


def test_a_request_that_costs_no_case_leaves_the_daily_budgets_alone():
    guard = Guard(per_minute=10, per_day=1, visitor_per_day=1, clock=Clock())
    assert guard.check("1.2.3.4", costs_a_case=False) is None
    assert guard.check("1.2.3.4") == 0  # the visitor's one case is still there
