"""The one module that knows which database is behind the app: SQLite while you develop and
test, Postgres in production. Callers write SQL once, with ? placeholders, and it runs on
both. Any database error becomes the caller's own exception, so a failure stays local: a
closed ledger never takes the public record down with it, and neither stops a verdict.
"""

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import closing, contextmanager
from typing import Any


class Database:
    def __init__(self, url: str, unavailable: type[Exception]):
        self._url = url
        self._unavailable = unavailable
        if url.startswith("sqlite:///"):
            self._errors: tuple[type[Exception], ...] = (sqlite3.Error,)
        elif url.startswith(("postgresql://", "postgres://")):
            import psycopg

            self._errors = (psycopg.Error,)
        else:
            raise ValueError("DATABASE_URL must start with sqlite:/// or postgresql://")

    @contextmanager
    def connect(self) -> Iterator["Connection"]:
        """One unit of work: committed if it succeeds, rolled back if it fails. Any database
        error, including one that can't connect at all, becomes the `unavailable` exception."""
        try:
            if self._url.startswith("sqlite:///"):
                path = self._url.removeprefix("sqlite:///")
                with closing(sqlite3.connect(path)) as conn, conn:  # `with conn` commits
                    yield Connection(conn, "?")
            else:
                import psycopg

                with psycopg.connect(self._url, connect_timeout=10) as pg:
                    yield Connection(pg, "%s")
        except self._errors as err:
            raise self._unavailable(str(err)) from err


class Connection:
    """Runs SQL written with ? placeholders on either driver."""

    def __init__(self, conn: Any, mark: str):
        self._conn = conn
        self._mark = mark

    def execute(self, sql: str, args: Sequence[Any] = ()) -> Any:
        return self._conn.execute(sql.replace("?", self._mark), tuple(args))

    def executemany(self, sql: str, rows: Sequence[Sequence[Any]]) -> None:
        cursor = self._conn.cursor()
        try:
            cursor.executemany(sql.replace("?", self._mark), [tuple(row) for row in rows])
        finally:
            cursor.close()
