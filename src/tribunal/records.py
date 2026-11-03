"""The public record: every verdict, word for word, with the law that decided it.

Visitors are told before they file that their case will be published. Three safeguards keep
the record fit to read: a case with an email address, a phone number or a link is judged
but not published; enough reports hide a case until you review it; and whoever filed a case
gets a private key that removes it. The SQL is plain enough for SQLite and Postgres alike;
db.py decides which one is behind it.
"""

import hashlib
import json
import re
import secrets
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from tribunal.db import Database
from tribunal.models import Case, Ruling

CONTACT = re.compile(
    r"[\w.+-]+@[\w-]+\.\w"  # an email address
    r"|https?://|www\.|\b\w[\w-]*\.(?:com|net|org|io|co|app|dev|me|info)\b"  # a link
    r"|(?:\+?\d[\s().-]*){9,}",  # a phone number: nine digits or more
    re.IGNORECASE,
)
SCHEMA = (
    """CREATE TABLE IF NOT EXISTS records (
        id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        crime TEXT NOT NULL,
        outrage INTEGER NOT NULL,
        themes TEXT NOT NULL,
        law_id TEXT NOT NULL,
        ruling TEXT NOT NULL,
        reports INTEGER NOT NULL DEFAULT 0,
        hidden INTEGER NOT NULL DEFAULT 0,
        removal_hash TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS records_by_time ON records (created_at)",
    "CREATE INDEX IF NOT EXISTS records_by_law ON records (law_id)",
)
COLUMNS = "id, created_at, crime, outrage, themes, ruling"


class Record(BaseModel):
    """One published case, as every visitor sees it."""

    id: str
    created_at: str  # ISO 8601, in UTC
    crime: str
    outrage: int
    themes: list[str]
    ruling: Ruling


class Published(BaseModel):
    """What the person who filed a case gets back: its ID, and the key that removes it."""

    id: str
    removal_key: str


class RecordsUnavailable(Exception):
    """The database didn't answer: the record is closed for now, but verdicts carry on."""


def unpublishable(crime: str) -> str | None:
    """Why a case can't go into the public record, or None when it can."""
    if CONTACT.search(crime):
        return "It was judged, but it contains contact details or a link, so it wasn't published."
    return None


class Records:
    def __init__(self, url: str, report_limit: int = 3):
        self._db = Database(url, RecordsUnavailable)
        self._report_limit = report_limit

    def setup(self) -> None:
        """Create the table and its indexes if they don't exist yet. Safe on every start."""
        with self._db.connect() as db:
            for statement in SCHEMA:
                db.execute(statement)

    def add(self, case: Case, ruling: Ruling) -> Published:
        record_id, key = secrets.token_urlsafe(6), secrets.token_urlsafe(16)
        public = ruling.model_copy(update={"meta": {}})  # trace IDs stay private
        law_id = ruling.law.law_id if ruling.law else ""
        row = (record_id, _now(), case.crime, case.outrage, json.dumps(case.themes), law_id)
        with self._db.connect() as db:
            db.execute(
                "INSERT INTO records (id, created_at, crime, outrage, themes, law_id, ruling,"
                " removal_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (*row, public.model_dump_json(), _hash(key)),
            )
        return Published(id=record_id, removal_key=key)

    def recent(
        self,
        limit: int = 12,
        before: str | None = None,
        law_id: str | None = None,
        theme: str | None = None,
    ) -> list[Record]:
        """The newest visible cases; pass the last one's created_at as `before` for more."""
        sql = f"SELECT {COLUMNS} FROM records WHERE hidden = 0"
        args: list[Any] = []
        if before:
            sql, args = sql + " AND created_at < ?", [*args, before]
        if law_id:
            sql, args = sql + " AND law_id = ?", [*args, law_id]
        if theme:
            sql, args = sql + " AND themes LIKE ?", [*args, f'%"{theme}"%']
        with self._db.connect() as db:
            rows = db.execute(sql + " ORDER BY created_at DESC LIMIT ?", [*args, limit]).fetchall()
        return [_record(row) for row in rows]

    def get(self, record_id: str) -> Record | None:
        with self._db.connect() as db:
            sql = f"SELECT {COLUMNS} FROM records WHERE id = ? AND hidden = 0"
            row = db.execute(sql, (record_id,)).fetchone()
        return _record(row) if row else None

    def counts(self) -> dict[str, int]:
        """How many visible verdicts cite each law: the library shows these."""
        with self._db.connect() as db:
            sql = "SELECT law_id, COUNT(*) FROM records WHERE hidden = 0 GROUP BY law_id"
            rows = db.execute(sql).fetchall()
        return {law_id: count for law_id, count in rows}

    def report(self, record_id: str) -> None:
        """Count one report. Enough of them hide the case until you review it."""
        with self._db.connect() as db:
            db.execute(
                "UPDATE records SET reports = reports + 1,"
                " hidden = CASE WHEN reports + 1 >= ? THEN 1 ELSE hidden END WHERE id = ?",
                (self._report_limit, record_id),
            )

    def remove(self, record_id: str, key: str) -> bool:
        """Delete a case for whoever holds its removal key."""
        with self._db.connect() as db:
            sql = "DELETE FROM records WHERE id = ? AND removal_hash = ?"
            return db.execute(sql, (record_id, _hash(key))).rowcount > 0

    def reported(self) -> list[tuple[str, int, bool, str]]:
        """Every reported case, most reported first: (id, reports, hidden, what was written)."""
        with self._db.connect() as db:
            sql = "SELECT id, reports, hidden, crime FROM records WHERE reports > 0"
            rows = db.execute(sql + " ORDER BY reports DESC").fetchall()
        return [(rid, reports, bool(hidden), crime) for rid, reports, hidden, crime in rows]

    def set_hidden(self, record_id: str, hidden: bool) -> bool:
        with self._db.connect() as db:
            sql = "UPDATE records SET hidden = ?, reports = 0 WHERE id = ?"
            return db.execute(sql, (int(hidden), record_id)).rowcount > 0

    def delete(self, record_id: str) -> bool:
        with self._db.connect() as db:
            return db.execute("DELETE FROM records WHERE id = ?", (record_id,)).rowcount > 0


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _record(row: Sequence[Any]) -> Record:
    record_id, created_at, crime, outrage, themes, ruling = row
    return Record(
        id=record_id,
        created_at=created_at,
        crime=crime,
        outrage=outrage,
        themes=json.loads(themes),
        ruling=Ruling.model_validate_json(ruling),
    )
