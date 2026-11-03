"""The court's ledger: how many cases it has judged, of what kind, under which laws, and at
what cost, counted a day at a time. Counts only: no grievance, name or address is stored.

Each case adds one to a handful of named counters ("cases", "kind:contempt", "law:hammurabi-8",
"provider:groq"), one row per counter per day. The table stays small however busy the court
gets, and a new counter needs no new column. The System page reads it all back in one call.
"""

from collections import Counter
from datetime import UTC, date, datetime, timedelta

from pydantic import BaseModel

from tribunal.db import Database
from tribunal.models import Ruling

SCHEMA = """CREATE TABLE IF NOT EXISTS counts (
    day TEXT NOT NULL,
    name TEXT NOT NULL,
    total INTEGER NOT NULL,
    PRIMARY KEY (day, name)
)"""
ADD = (
    "INSERT INTO counts (day, name, total) VALUES (?, ?, ?)"
    " ON CONFLICT (day, name) DO UPDATE SET total = counts.total + excluded.total"
)
TOTALS = "SELECT name, SUM(total) FROM counts GROUP BY name"
RECENT = "SELECT day, name, total FROM counts WHERE day >= ? AND name IN (?, ?)"
ONE_DAY = "SELECT name, total FROM counts WHERE day = ?"
KINDS = ("verdict", "contempt", "declined")


class Day(BaseModel):
    day: str
    cases: int
    contempt: int


class Cited(BaseModel):
    law_id: str
    times: int


class Ledger(BaseModel):
    """Everything the ledger knows, before the API adds today's capacity."""

    all_time: int
    today: int
    kinds: dict[str, int]  # verdict, contempt and declined, all time
    days: list[Day]  # oldest first, with empty days filled in
    laws: list[Cited]  # the most-cited laws, most first
    providers_today: dict[str, int]  # which provider answered each of today's cases
    fallbacks_today: int  # cases a backup provider answered
    refused: int  # requests stopped before any AI call, all time
    tokens_today: int  # AI tokens today's cases used
    tokens_all_time: int
    tokens_per_case: int  # measured average; 0 until a case has been measured


class StatsUnavailable(Exception):
    """The database didn't answer: the ledger is closed for now, but verdicts carry on."""


class Stats:
    def __init__(self, url: str):
        self._db = Database(url, StatsUnavailable)

    def setup(self) -> None:
        """Create the table if it doesn't exist yet. Safe on every start."""
        with self._db.connect() as db:
            db.execute(SCHEMA)

    def add_case(self, ruling: Ruling) -> None:
        """Count one judged case: its kind, its law, who answered, and the tokens it used."""
        names: Counter[str] = Counter({"cases": 1, f"kind:{ruling.kind}": 1})
        if ruling.law:
            names[f"law:{ruling.law.law_id}"] += 1
        if provider := ruling.meta.get("provider"):
            names[f"provider:{provider}"] += 1
        if ruling.meta.get("fallback") == "1":
            names["fallbacks"] += 1
        if tokens := int(ruling.meta.get("tokens") or 0):
            names["tokens"] += tokens
            names["metered"] += 1  # cases whose tokens were measured
        self._add(names)

    def add_refusal(self) -> None:
        """Count one request stopped before any AI call: too big, malformed, or over a limit."""
        self._add(Counter({"refused": 1}))

    def ledger(self, days: int = 30, top: int = 5) -> Ledger:
        today = _today()
        first = (date.fromisoformat(today) - timedelta(days=days - 1)).isoformat()
        with self._db.connect() as db:
            totals = dict(db.execute(TOTALS).fetchall())
            recent = db.execute(RECENT, (first, "cases", "kind:contempt")).fetchall()
            now = dict(db.execute(ONE_DAY, (today,)).fetchall())
        series = {_day(first, n): Day(day=_day(first, n), cases=0, contempt=0) for n in range(days)}
        for day, name, total in recent:
            if day in series:
                setattr(series[day], "cases" if name == "cases" else "contempt", int(total))
        cited = [(n[4:], int(t)) for n, t in totals.items() if n.startswith("law:")]
        cited.sort(key=lambda law: -law[1])
        metered = int(totals.get("metered", 0))
        return Ledger(
            all_time=int(totals.get("cases", 0)),
            today=int(now.get("cases", 0)),
            kinds={kind: int(totals.get(f"kind:{kind}", 0)) for kind in KINDS},
            days=list(series.values()),
            laws=[Cited(law_id=law_id, times=times) for law_id, times in cited[:top]],
            providers_today={n[9:]: int(t) for n, t in now.items() if n.startswith("provider:")},
            fallbacks_today=int(now.get("fallbacks", 0)),
            refused=int(totals.get("refused", 0)),
            tokens_today=int(now.get("tokens", 0)),
            tokens_all_time=int(totals.get("tokens", 0)),
            tokens_per_case=int(totals.get("tokens", 0)) // metered if metered else 0,
        )

    def _add(self, names: Counter[str]) -> None:
        today = _today()
        with self._db.connect() as db:
            db.executemany(ADD, [(today, name, total) for name, total in names.items()])


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def _day(first: str, offset: int) -> str:
    return (date.fromisoformat(first) + timedelta(days=offset)).isoformat()
