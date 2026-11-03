"""Composition root: the one place that knows how the real parts fit together.

Every other module receives its collaborators as arguments. That's why tests can pass
fakes, and why swapping Qdrant or an LLM provider touches only this file and config.py.
"""

import logging

from qdrant_client import QdrantClient

from tribunal.config import Settings
from tribunal.court import Tribunal
from tribunal.history import History, HistoryUnavailable
from tribunal.llm import LLMClient
from tribunal.records import Records, RecordsUnavailable
from tribunal.search import LawIndex, Models
from tribunal.stats import Stats, StatsUnavailable

log = logging.getLogger(__name__)


def build_index(settings: Settings) -> LawIndex:
    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
    return LawIndex(client, Models(settings.model_cache), settings.collection)


def build_tribunal(settings: Settings) -> Tribunal:
    llm = LLMClient(
        settings.providers(),
        timeout=settings.llm_timeout,
        max_tokens={
            "fast": settings.max_output_tokens_fast,
            "smart": settings.max_output_tokens_smart,
        },
        daily_tokens=settings.tokens_per_day,
    )
    return Tribunal(llm, build_index(settings))


def build_records(settings: Settings) -> Records | None:
    """The public record, or None when DATABASE_URL isn't set."""
    if not settings.database_url:
        return None
    records = Records(settings.database_url, settings.record_report_limit)
    try:
        records.setup()
    except RecordsUnavailable as err:  # start anyway: verdicts don't need the record
        log.warning("the public record is unavailable: %s", err)
    return records


def build_stats(settings: Settings) -> Stats | None:
    """The court's ledger, kept beside the public record; None when DATABASE_URL isn't set."""
    if not settings.database_url:
        return None
    stats = Stats(settings.database_url)
    try:
        stats.setup()
    except StatsUnavailable as err:  # start anyway: verdicts don't need the ledger
        log.warning("the ledger is unavailable: %s", err)
    return stats


def build_history(settings: Settings) -> History | None:
    """The private history of every grievance; None when DATABASE_URL isn't set."""
    if not settings.database_url:
        return None
    history = History(settings.database_url)
    try:
        history.setup()
    except HistoryUnavailable as err:  # start anyway: verdicts don't need the history
        log.warning("the history is unavailable: %s", err)
    return history
