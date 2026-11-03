"""The court's private history: every grievance filed, word for word, whatever became of it.

The public record shows only published cases, and the ledger keeps only counts. The history
keeps the rest for you to study: cases that were declined, too long to judge, unjudged while
the court was down, or held back for containing contact details, beside the published ones.
Visitors are told on the form. The API never serves it; you read it with `tribunal history`.
It holds no names from the private part of the form, no photos, addresses or fingerprints,
and a visitor's removal link deletes their entry here too.
"""

import json
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tribunal.db import Database

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS history (
        id TEXT PRIMARY KEY,
        filed_at TEXT NOT NULL,
        crime TEXT NOT NULL,
        length INTEGER NOT NULL,
        outrage INTEGER NOT NULL,
        themes TEXT NOT NULL,
        outcome TEXT NOT NULL,
        law_id TEXT NOT NULL,
        record_id TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS history_by_time ON history (filed_at)",
)
COLUMNS = (
    "id",
    "filed_at",
    "crime",
    "length",
    "outrage",
    "themes",
    "outcome",
    "law_id",
    "record_id",
)
INSERT = f"INSERT INTO history ({', '.join(COLUMNS)}) VALUES ({', '.join('?' * len(COLUMNS))})"


class HistoryUnavailable(Exception):
    """The database didn't answer: the history misses an entry, but verdicts carry on."""


class History:
    def __init__(self, url: str, max_chars: int = 5_000):
        self._db = Database(url, HistoryUnavailable)
        self._max_chars = max_chars

    def setup(self) -> None:
        """Create the table and its index if they don't exist yet. Safe on every start."""
        with self._db.connect() as db:
            for statement in SCHEMA:
                db.execute(statement)

    def add(
        self,
        crime: str,
        outrage: int,
        themes: list[str],
        outcome: str,
        law_id: str = "",
        record_id: str = "",
    ) -> str:
        """Keep one grievance as written, up to max_chars, and what became of it."""
        entry = secrets.token_urlsafe(8)
        kept = crime[: self._max_chars]
        listed = json.dumps(themes)
        row = (entry, _now(), kept, len(crime), outrage, listed, outcome, law_id, record_id)
        with self._db.connect() as db:
            db.execute(INSERT, row)
        return entry

    def forget(self, record_id: str) -> int:
        """Delete the entry for a published case its author removed. Returns how many."""
        with self._db.connect() as db:
            return db.execute("DELETE FROM history WHERE record_id = ?", (record_id,)).rowcount

    def export(self, path: Path, days: int | None = None) -> int:
        """Write every entry, or the last `days` days', to a JSON Lines file. Returns how many."""
        sql = f"SELECT {', '.join(COLUMNS)} FROM history"
        args: tuple[str, ...] = ()
        if days is not None:
            sql, args = sql + " WHERE filed_at >= ?", (_ago(days),)
        with self._db.connect() as db:
            rows = db.execute(sql + " ORDER BY filed_at", args).fetchall()
        with path.open("w", encoding="utf-8") as out:
            for row in rows:
                entry = dict(zip(COLUMNS, row, strict=True))
                entry["themes"] = json.loads(entry["themes"])
                out.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return len(rows)

    def prune(self, days: int) -> int:
        """Delete entries older than `days` days. Returns how many."""
        with self._db.connect() as db:
            return db.execute("DELETE FROM history WHERE filed_at < ?", (_ago(days),)).rowcount


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _ago(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat(timespec="microseconds")
