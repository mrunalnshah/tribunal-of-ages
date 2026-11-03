"""HTTP layer: validates requests, protects the quotas, and maps errors to status codes.

All judging happens in Tribunal and all storing in Records; this module only translates
between HTTP and them. Visitors are told that every verdict goes into the public record, and
nothing else they send is kept: there's no cache, and no access log (see the Dockerfile).
Run it with: uvicorn tribunal.api:create_app --factory
"""

import logging
import math
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from tribunal import telemetry
from tribunal.config import Settings
from tribunal.court import Tribunal, TribunalUnavailable
from tribunal.guards import BodyLimit, Guard, RateLimited
from tribunal.history import History, HistoryUnavailable
from tribunal.llm import ProviderState
from tribunal.models import CRIME_MAX, KEPT_MAX, Case, Catalog, Law, Ruling
from tribunal.records import Published, Record, Records, RecordsUnavailable, unpublishable
from tribunal.stats import Ledger, Stats, StatsUnavailable

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
CLOSED = "The public record is closed right now. Verdicts still work."
NOT_PUBLISHED = "It was judged, but the public record is closed, so it wasn't published."
NO_CONSENT = "Tick the box first: the grievance and its verdict will be public."
TOO_LONG = (
    f"The court reads grievances of up to {CRIME_MAX} characters, and yours has {{length}}. "
    "It's been kept: trim it and file it again to have it judged."
)


class Feedback(BaseModel):
    trace_id: str = Field(min_length=1, max_length=64)
    value: int = Field(ge=-1, le=1)


class CaseRequest(Case):
    crime: str = Field(min_length=10, max_length=KEPT_MAX)  # over CRIME_MAX: kept, never judged
    record: bool = True  # False: judged, never published (the website, unless Publish is ticked)
    consent: bool = False  # the visitor ticked: "my grievance and its verdict will be public"


class Answer(Ruling):
    """A ruling, plus what happened to it in the public record."""

    record: Published | None = None
    record_note: str = ""
    cases_left: int | None = None  # how many more cases this visitor may file today


class Removal(BaseModel):
    key: str = Field(min_length=8, max_length=64)


class Saved(BaseModel):
    """Tokens the court didn't spend. Both figures are estimates, and the page says so."""

    refused: int  # requests stopped before any AI call
    refused_tokens: int  # refused × the measured tokens per case
    contempt: int  # off-topic asks held in contempt instead of answered
    contempt_tokens: int  # contempt × ESTIMATED_ANSWER_TOKENS, an assumption


class Board(BaseModel):
    """The System page, in one answer."""

    ledger: Ledger
    per_day: int  # most cases the court can hear today
    tokens_per_day: int  # the daily budget of AI tokens
    visitor_daily_limit: int
    saved: Saved
    providers: list[ProviderState]


def create_app(
    settings: Settings | None = None,
    tribunal: Tribunal | None = None,
    catalog: Catalog | None = None,
    records: Records | None = None,
    stats: Stats | None = None,
    history: History | None = None,
) -> FastAPI:
    """Build the app. Tests pass fakes; production loads the real parts at startup."""
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.catalog = catalog or _load_catalog(Path(settings.catalog_path))
        if tribunal is not None:
            app.state.tribunal = tribunal
        else:
            from tribunal.wiring import build_tribunal  # loads ML models: only for real runs

            app.state.tribunal = build_tribunal(settings)
        if records is not None or not settings.database_url:
            app.state.records = records  # None: this court keeps no public record
        else:
            from tribunal.wiring import build_records

            app.state.records = build_records(settings)
        if stats is not None or not settings.database_url:
            app.state.stats = stats  # None: this court keeps no ledger
        else:
            from tribunal.wiring import build_stats

            app.state.stats = build_stats(settings)
        if history is not None or not settings.database_url:
            app.state.history = history  # None: this court keeps no history
        else:
            from tribunal.wiring import build_history

            app.state.history = build_history(settings)
        yield
        telemetry.flush()

    app = FastAPI(title="Tribunal of Ages", version="1.1.0", lifespan=lifespan)
    # Added first, so CORS wraps it and even a 413 reaches the browser readably.
    app.add_middleware(
        BodyLimit, max_bytes=settings.max_body_bytes, on_refuse=lambda: _refused(app)
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.get("/api/v1/catalog")
    def get_catalog(request: Request) -> Catalog:
        """The themes and jurisdictions a case may choose from. The website builds its form
        from this, so a new theme appears there without touching the frontend."""
        return request.app.state.catalog

    guard = Guard(
        settings.requests_per_minute, settings.cases_per_day, settings.visitor_daily_limit
    )
    reports = Guard(10, 1_000)  # reporting costs no LLM call, so it gets its own limit

    @app.exception_handler(RateLimited)
    async def rate_limited(request: Request, err: RateLimited) -> JSONResponse:
        if request.url.path == "/api/v1/verdicts":
            await run_in_threadpool(_refused, request.app)
        headers = {"Retry-After": str(err.retry_after)}
        return JSONResponse({"detail": err.reason}, status_code=429, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, err: RequestValidationError) -> JSONResponse:
        if request.url.path == "/api/v1/verdicts":
            await run_in_threadpool(_refused, request.app)
        return await request_validation_exception_handler(request, err)

    @app.exception_handler(StatsUnavailable)
    async def ledger_closed(_: Request, err: StatsUnavailable) -> JSONResponse:
        return JSONResponse({"detail": "The ledger is closed right now."}, status_code=503)

    @app.exception_handler(RecordsUnavailable)
    async def record_closed(_: Request, err: RecordsUnavailable) -> JSONResponse:
        return JSONResponse({"detail": CLOSED}, status_code=503)

    @app.post("/api/v1/verdicts")
    def verdict(case: CaseRequest, request: Request) -> Answer:
        try:
            request.app.state.catalog.check(case.themes, case.jurisdiction)
        except ValueError as err:
            raise HTTPException(422, str(err)) from err
        if case.record and request.app.state.records is not None and not case.consent:
            raise HTTPException(422, NO_CONSENT)  # before any LLM call is spent on it
        visitor = request.client.host if request.client else "unknown"
        kept = request.app.state.history
        if len(case.crime) > CRIME_MAX:  # kept, but never sent to an AI, so it costs no case
            guard.check(visitor, costs_a_case=False)
            _kept(kept, case, "too_long")
            _refused(request.app)
            raise HTTPException(422, TOO_LONG.format(length=len(case.crime)))
        left = guard.check(visitor)
        try:
            ruling = request.app.state.tribunal.judge(Case(**case.model_dump(exclude={"record"})))
        except TribunalUnavailable as err:
            _kept(kept, case, "unjudged")
            if err.retry_after is not None:  # only out of quota: say when the court reopens
                wait = max(1, math.ceil(err.retry_after))
                reopens = _about(wait)
                message = f"The court has used its AI allowance for now. It reopens in {reopens}."
                raise HTTPException(429, message, headers={"Retry-After": str(wait)}) from err
            message = "The court's scribes (our AI providers) aren't responding. Try again soon."
            raise HTTPException(503, message) from err
        _counted(request.app.state.stats, ruling)
        board["at"] = -math.inf  # the next stats request sees this case
        answer = _publish(request.app.state.records, case, ruling)
        law_id = ruling.law.law_id if ruling.law else ""
        _kept(kept, case, ruling.kind, law_id, answer.record.id if answer.record else "")
        answer.cases_left = left
        return answer

    board: dict[str, Any] = {"at": -math.inf, "value": None}

    @app.get("/api/v1/stats")
    def ledger(request: Request) -> Board:
        """The court's ledger, today's capacity, and who's answering. Refreshed every minute."""
        if time.monotonic() - board["at"] > 60:
            found = request.app.state.stats
            if found is None:
                raise HTTPException(503, "This court keeps no ledger yet.")
            kept = found.ledger()
            llm = getattr(request.app.state.tribunal, "llm", None)
            saved = Saved(
                refused=kept.refused,
                refused_tokens=kept.refused * (kept.tokens_per_case or 2_000),
                contempt=kept.kinds["contempt"],
                contempt_tokens=kept.kinds["contempt"] * settings.estimated_answer_tokens,
            )
            board["value"] = Board(
                ledger=kept,
                per_day=settings.cases_per_day,
                tokens_per_day=settings.tokens_per_day,
                visitor_daily_limit=settings.visitor_daily_limit,
                saved=saved,
                providers=llm.status() if llm else [],
            )
            board["at"] = time.monotonic()
        return board["value"]

    @app.get("/api/v1/records")
    def list_records(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=50)] = 12,
        before: str | None = None,
        law: str | None = None,
        theme: str | None = None,
    ) -> list[Record]:
        """The newest public cases. Pass the last one's created_at as `before` for more."""
        return _open(request).recent(limit, before, law, theme)

    counted: dict[str, Any] = {"at": -math.inf, "counts": {}}

    @app.get("/api/v1/records/counts")
    def record_counts(request: Request) -> dict[str, int]:
        """How many public verdicts cite each law, refreshed at most every five minutes."""
        if time.monotonic() - counted["at"] > 300:
            counted["counts"] = _open(request).counts()
            counted["at"] = time.monotonic()
        return counted["counts"]

    @app.get("/api/v1/records/{record_id}")
    def one_record(record_id: str, request: Request) -> Record:
        found = _open(request).get(record_id)
        if found is None:
            raise HTTPException(404, "No public case with that ID.")
        return found

    @app.post("/api/v1/records/{record_id}/report", status_code=204)
    def report(record_id: str, request: Request) -> None:
        reports.check(request.client.host if request.client else "unknown")
        _open(request).report(record_id)

    @app.post("/api/v1/records/{record_id}/remove", status_code=204)
    def remove(record_id: str, removal: Removal, request: Request) -> None:
        if not _open(request).remove(record_id, removal.key):
            raise HTTPException(404, "No case with that ID and key.")
        if request.app.state.history is not None:
            try:
                request.app.state.history.forget(record_id)  # its private entry goes too
            except HistoryUnavailable as err:
                logging.getLogger(__name__).warning("the history is unavailable: %s", err)

    @app.get("/api/v1/laws/{law_id}")
    def law(law_id: str, request: Request) -> Law:
        found = request.app.state.tribunal.index.get(law_id)
        if found is None:
            raise HTTPException(404, f"No law with id {law_id!r}")
        return found

    @app.post("/api/v1/feedback", status_code=204)
    def feedback(item: Feedback) -> None:
        telemetry.score(item.trace_id, item.value)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    @app.get("/readyz")
    def readyz(request: Request) -> dict:
        try:
            laws = request.app.state.tribunal.index.count()
        except Exception as err:  # any failure here means "not ready"
            raise HTTPException(503, "search index unreachable") from err
        return {"ok": True, "laws": laws}

    return app


def _load_catalog(path: Path) -> Catalog:
    if not path.exists():
        raise RuntimeError(f"{path} is missing: run `uv run tribunal curate` first")
    return Catalog.model_validate_json(path.read_text(encoding="utf-8"))


def _open(request: Request) -> Records:
    """The public record, or a 503 when this server keeps none."""
    found = request.app.state.records
    if found is None:
        raise HTTPException(503, "This court keeps no public record yet.")
    return found


def _counted(stats: Stats | None, ruling: Ruling) -> None:
    """Add a case to the ledger. A closed ledger is logged, never a reason to fail a verdict."""
    if stats is None:
        return
    try:
        stats.add_case(ruling)
    except StatsUnavailable as err:
        logging.getLogger(__name__).warning("the ledger is unavailable: %s", err)


def _kept(
    history: History | None, case: CaseRequest, outcome: str, law_id: str = "", record_id: str = ""
) -> None:
    """Keep a grievance in the private history. Health checks and load tests aren't kept."""
    if history is None or not case.record:
        return
    try:
        history.add(case.crime, case.outrage, case.themes, outcome, law_id, record_id)
    except HistoryUnavailable as err:
        logging.getLogger(__name__).warning("the history is unavailable: %s", err)


def _refused(app: FastAPI) -> None:
    """Count a request stopped before any AI call, if this court keeps a ledger."""
    found = getattr(app.state, "stats", None)
    if found is not None:
        try:
            found.add_refusal()
        except StatsUnavailable:
            pass  # a closed ledger can't count, and mustn't stop the refusal itself


def _publish(records: Records | None, case: CaseRequest, ruling: Ruling) -> Answer:
    """Put a verdict into the public record, unless it shouldn't or can't go there."""
    answer = Answer(**ruling.model_dump())
    if ruling.kind == "declined" or not case.record or records is None:
        return answer
    if reason := unpublishable(case.crime):
        answer.record_note = reason
        return answer
    try:
        answer.record = records.add(case, ruling)
    except RecordsUnavailable:
        answer.record_note = NOT_PUBLISHED
    return answer


def _about(seconds: int) -> str:
    """A wait in words, rounded up: 'a minute or so', 'about 12 minutes', 'about 3 hours'."""
    if seconds <= 60:
        return "a minute or so"
    if seconds < 90 * 60:
        return f"about {max(2, round(seconds / 60))} minutes"
    return f"about {round(seconds / 3600)} hours"
