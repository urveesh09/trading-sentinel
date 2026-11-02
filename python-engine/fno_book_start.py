"""[F11 2026-11-02] Where the F&O paper book's money starts.

The owner gave N11's paper book a fresh Rs 2,50,000 from November 3, 2026. Before that, the two paper books had lost
Rs 33,844 since July, nearly all of it before N11 existed. That left the book 13.54% under its peak: quarter size, and
about Rs 3,656 above the 15% halt, so N11's own rules could hardly run.

Nothing is deleted or rewritten. Every old trade stays in the ledger and the position tables, and evidence that judges
the strategy over its whole life (the go-live bar, the promotion report) still reads all of it. Only the readers that
decide or show the book's money count from this date: equity, its peak, the size stance, and the day, week, month,
drawdown and loss-streak brakes.

FNO_PAPER only. The real-money test keeps its own capital and floor, and every other division is untouched.
Back to the whole history: FNO_PAPER_BOOK_START= (empty) and an engine restart.
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Optional
from zoneinfo import ZoneInfo

from config import settings

IST = ZoneInfo("Asia/Kolkata")
FRESH_SOURCE = "FNO_PAPER"


def book_start(source: str) -> Optional[datetime]:
    """The instant ``source``'s current book began (midnight IST), or None when its whole history counts."""
    if source != FRESH_SOURCE:
        return None
    raw = str(settings.FNO_PAPER_BOOK_START or "").strip()
    return datetime.combine(date.fromisoformat(raw), time(0, 0), IST) if raw else None


def in_book(source: str, at: datetime) -> bool:
    """Does an event at this aware instant belong to ``source``'s current book?"""
    start = book_start(source)
    return start is None or at >= start


def since_sql(source: str, column: str = "timestamp") -> tuple[str, tuple]:
    """(SQL to append after a WHERE, its arguments): the rows of ``source``'s current book.

    SQLite's julianday reads each stored offset, so UTC ledger stamps and IST position stamps compare correctly.
    """
    start = book_start(source)
    if start is None:
        return "", ()
    return f" AND julianday({column}) >= julianday(?)", (start.isoformat(),)
