"""Protection for the free quotas: who may file a case right now, and how big a request may
be before it's even read.

Guard counts visitors by a keyed fingerprint of their address, never the address itself, and
replaces the key every day, so yesterday's counts can't be linked to anyone. It enforces cases
a minute and a day per visitor, and cases a day for everyone. BodyLimit refuses an oversized
request before reading it, so a pasted novel costs nothing at all.
"""

import asyncio
import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from typing import Any

Clock = Callable[[], float]


class RateLimited(Exception):
    def __init__(self, retry_after: int, reason: str):
        super().__init__(reason)
        self.retry_after = retry_after
        self.reason = reason


class Guard:
    def __init__(
        self,
        per_minute: int,
        per_day: int,
        visitor_per_day: int | None = None,
        clock: Clock = time.time,
    ):
        self._per_minute = per_minute
        self._per_day = per_day
        self._visitor_per_day = visitor_per_day
        self._clock = clock
        self._recent: dict[str, deque[float]] = defaultdict(deque)
        self._today: dict[str, int] = defaultdict(int)  # requests per fingerprint, today
        self._day = ""
        self._used_today = 0
        self._key = secrets.token_bytes(16)
        self._lock = threading.Lock()

    def check(self, visitor: str, costs_a_case: bool = True) -> int | None:
        """Count one request from `visitor`, or raise RateLimited.

        A request that costs a case uses the daily budgets; one that doesn't (no AI call) only
        the per-minute limit. Returns how many cases the visitor has left today, or None.
        """
        with self._lock:
            now = self._clock()
            today = time.strftime("%Y-%m-%d", time.gmtime(now))
            if today != self._day:
                self._day, self._used_today = today, 0
                self._recent.clear()  # also stops the visitor tables from growing forever
                self._today.clear()
                self._key = secrets.token_bytes(16)  # yesterday's fingerprints mean nothing
            tomorrow = 86400 - int(now % 86400)
            if costs_a_case and self._used_today >= self._per_day:
                raise RateLimited(tomorrow, "The Tribunal is in recess until tomorrow.")
            who = self._fingerprint(visitor)
            limit = self._visitor_per_day
            if costs_a_case and limit is not None and self._today[who] >= limit:
                reason = f"You've filed today's {limit} cases. The court will hear you tomorrow."
                raise RateLimited(tomorrow, reason)
            window = self._recent[who]
            while window and now - window[0] >= 60:
                window.popleft()
            if len(window) >= self._per_minute:
                wait = int(60 - (now - window[0])) + 1
                raise RateLimited(wait, "Too many cases at once. The court needs a breather.")
            window.append(now)
            if not costs_a_case:
                return None
            self._today[who] += 1
            self._used_today += 1
            return None if limit is None else limit - self._today[who]

    def _fingerprint(self, visitor: str) -> str:
        return hashlib.blake2b(visitor.encode(), key=self._key, digest_size=8).hexdigest()


class BodyLimit:
    """ASGI middleware: answer 413 to a request body over `max_bytes`, without reading it all.

    The declared length is checked first; a body sent without one is counted as it arrives.
    """

    def __init__(self, app: Any, max_bytes: int, on_refuse: Callable[[], None] | None = None):
        self.app = app
        self.max_bytes = max_bytes
        self.on_refuse = on_refuse  # called, off the event loop, for each refusal

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = dict(scope.get("headers", [])).get(b"content-length", b"0")
        if not declared.isdigit() or int(declared) > self.max_bytes:
            await self._refuse(send)
            return
        seen = 0

        async def counted() -> Any:
            nonlocal seen
            message = await receive()
            seen += len(message.get("body", b""))
            if seen > self.max_bytes:
                raise _TooLarge
            return message

        try:
            await self.app(scope, counted, send)
        except _TooLarge:
            await self._refuse(send)

    async def _refuse(self, send: Any) -> None:
        if self.on_refuse:
            await asyncio.to_thread(self.on_refuse)
        await _too_large(send)


class _TooLarge(Exception):
    pass


async def _too_large(send: Any) -> None:
    body = b'{"detail": "That request is too large for the court."}'
    headers = [(b"content-type", b"application/json"), (b"content-length", b"%d" % len(body))]
    await send({"type": "http.response.start", "status": 413, "headers": headers})
    await send({"type": "http.response.body", "body": body})
