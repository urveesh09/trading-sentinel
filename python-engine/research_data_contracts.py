"""[B1 2026-10-03] Immutable, offline bar-data contracts for research replays.

Backtests must never confuse one bar interval for another, fill from a bar on
which nothing traded, forward-fill a missing session or treat an unverifiable
calendar day as a trading day. This module is the single place that decides
which cached bars a research replay may use and records why every other row
or ticker-day was excluded.

Contracts (see docs/2026-10-03-b1-b2-data-contracts-and-penny-lifecycle.md):

* A run selects exactly one registered interval label. Other labels on the
  same ticker-day (for example 15-minute rows next to minute rows) are counted
  and reported, never merged and never fatal. ``legacy_unknown`` is never
  usable.
* Timestamps are IST wall-clock bar starts. Naive values are read as IST;
  aware values are converted to IST. A bar becomes visible at
  ``start + interval``.
* One invalid row (off grid, outside the session, on a non-trading day,
  impossible OHLC, negative volume, conflicting duplicate) invalidates its
  whole ticker-day. Bad rows are never silently dropped from a usable day.
* Zero-volume bars are marks, not executable evidence.
* Coverage is reported per requested trading day as COMPLETE, PARTIAL,
  INVALID or UNAVAILABLE. Nothing is forward-filled; strategies declare which
  statuses they can use through ``CoverageRequirement``.
* Daily bars are point-in-time: a bar dated D only informs decisions after D.
  Adjustment basis is unknown, so suspected corporate actions are reported,
  never repaired.

No network access, no writes, no broker calls. Loaders open SQLite strictly
read-only and never create a missing database.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import closing
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from typing import Iterable, Mapping, Sequence

CONTRACT_VERSION = "sentinel_bar_data_contract_v1"
IST = timezone(timedelta(hours=5, minutes=30), "IST")
CLOCK = "IST_WALL_CLOCK_BAR_START"
SESSION_OPEN = time(9, 15)
SESSION_MINUTES = 375  # 09:15 -> 15:30
DAILY_ADJUSTMENT_BASIS = "UNKNOWN_AS_CACHED"
CORPORATE_ACTION_MOVE = 0.40
LEGACY_INTERVAL = "legacy_unknown"

BAR_TRADED = "TRADED"
BAR_NO_TRADE_MARK = "NO_TRADE_MARK"
BAR_ZERO_VOLUME_WITH_RANGE = "ZERO_VOLUME_WITH_RANGE"

STATUS_COMPLETE = "COMPLETE"
STATUS_PARTIAL = "PARTIAL"
STATUS_INVALID = "INVALID"
STATUS_UNAVAILABLE = "UNAVAILABLE"


class DatasetUnavailable(RuntimeError):
    """The requested evidence cannot be read; nothing was fabricated."""


@dataclass(frozen=True)
class IntervalSpec:
    label: str
    minutes: int

    @property
    def bars_per_session(self) -> int:
        return SESSION_MINUTES // self.minutes

    @property
    def last_bar_start(self) -> time:
        last = datetime.combine(date(2000, 1, 3), SESSION_OPEN) + timedelta(
            minutes=self.minutes * (self.bars_per_session - 1)
        )
        return last.time()


INTERVALS: Mapping[str, IntervalSpec] = {
    spec.label: spec for spec in (
        IntervalSpec("minute", 1), IntervalSpec("3minute", 3),
        IntervalSpec("5minute", 5), IntervalSpec("15minute", 15),
    )
}


def interval_spec(label: str) -> IntervalSpec:
    if label == LEGACY_INTERVAL:
        raise DatasetUnavailable("legacy_unknown interval provenance is never usable")
    try:
        return INTERVALS[label]
    except KeyError:
        raise ValueError(f"unregistered bar interval: {label!r}") from None


# ---- calendar --------------------------------------------------------------

@dataclass(frozen=True)
class TradingCalendar:
    holidays: frozenset
    valid_from: date
    valid_through: date
    source: str

    def covers(self, day: date) -> bool:
        return self.valid_from <= day <= self.valid_through

    def is_trading_day(self, day: date) -> bool:
        if not self.covers(day):
            raise DatasetUnavailable(f"trading calendar does not cover {day.isoformat()}")
        return day.weekday() < 5 and day not in self.holidays

    def describe(self) -> dict:
        return {
            "source": self.source, "valid_from": self.valid_from.isoformat(),
            "valid_through": self.valid_through.isoformat(),
            "holidays": sorted(day.isoformat() for day in self.holidays),
        }


def default_calendar() -> TradingCalendar:
    """The audited static NSE set; it is valid only for its declared year."""
    from market_calendar import NSE_HOLIDAYS_STATIC, NSE_HOLIDAYS_VALID_THROUGH
    through = date.fromisoformat(NSE_HOLIDAYS_VALID_THROUGH)
    return TradingCalendar(
        holidays=frozenset(NSE_HOLIDAYS_STATIC),
        valid_from=date(through.year, 1, 1), valid_through=through,
        source="market_calendar.NSE_HOLIDAYS_STATIC",
    )


# ---- helpers ----------------------------------------------------------------

def iso_day(value) -> date:
    text = value.isoformat() if isinstance(value, date) else str(value)
    parsed = date.fromisoformat(text)
    if parsed.isoformat() != text:
        raise ValueError("dates must be ISO YYYY-MM-DD")
    return parsed


def parse_bar_start(value) -> datetime:
    """Normalise a cached timestamp to an aware IST datetime or raise."""
    if isinstance(value, datetime):
        stamp = value
    else:
        text = str(value).strip()
        if len(text) < 16:
            raise ValueError("timestamp too short")
        stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        return stamp.replace(tzinfo=IST)
    return stamp.astimezone(IST)


def _finite(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _read_only_connection(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    if not path.is_file():
        raise DatasetUnavailable(f"database not found: {db_path}")
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def _canonical_hash(header: dict, rows: Iterable[tuple]) -> str:
    digest = hashlib.sha256(json.dumps(header, sort_keys=True, separators=(",", ":")).encode())
    for row in rows:
        digest.update(json.dumps(row, separators=(",", ":"), allow_nan=False).encode())
        digest.update(b"\n")
    return f"sha256:{digest.hexdigest()}"


# ---- intraday contract -------------------------------------------------------

@dataclass(frozen=True)
class Bar:
    ticker: str
    start: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    kind: str
    interval_minutes: int

    @property
    def available_at(self) -> datetime:
        return self.start + timedelta(minutes=self.interval_minutes)

    @property
    def executable(self) -> bool:
        return self.kind == BAR_TRADED


@dataclass(frozen=True)
class CoverageRequirement:
    """Which ticker-day statuses a strategy may consume, and why."""
    name: str
    usable_statuses: frozenset
    assumption: str | None = None

    def __post_init__(self):
        allowed = {STATUS_COMPLETE, STATUS_PARTIAL}
        if not self.usable_statuses or not set(self.usable_statuses) <= allowed:
            raise ValueError("usable_statuses must be a non-empty subset of COMPLETE/PARTIAL")


COMPLETE_SESSIONS_ONLY = CoverageRequirement("complete_only", frozenset({STATUS_COMPLETE}))
ALLOW_SESSION_GAPS = CoverageRequirement(
    "allow_gaps", frozenset({STATUS_COMPLETE, STATUS_PARTIAL}),
    assumption="MISSING_MINUTES_TREATED_AS_NO_TRADE_UNVERIFIED",
)
COVERAGE_REQUIREMENTS = {req.name: req for req in (COMPLETE_SESSIONS_ONLY, ALLOW_SESSION_GAPS)}


@dataclass
class IntradayDataset:
    interval: IntervalSpec
    bars: dict = field(default_factory=dict)       # (ticker, iso_day) -> tuple[Bar, ...]
    coverage: list = field(default_factory=list)   # per requested ticker-day
    manifest: dict = field(default_factory=dict)

    def coverage_for(self, ticker: str, day: str) -> dict | None:
        for row in self.coverage:
            if row["ticker"] == ticker and row["trading_date"] == day:
                return row
        return None

    def usable_days(self, requirement: CoverageRequirement) -> list[tuple[str, str]]:
        return sorted(
            (row["ticker"], row["trading_date"]) for row in self.coverage
            if row["status"] in requirement.usable_statuses
        )


def _row_problem(spec: IntervalSpec, stamp: datetime, o, h, l, c, v,
                 calendar: TradingCalendar) -> str | None:
    if stamp.second or stamp.microsecond:
        return "off_grid_seconds"
    minute_of_session = (stamp.hour * 60 + stamp.minute) - (SESSION_OPEN.hour * 60 + SESSION_OPEN.minute)
    if minute_of_session < 0 or minute_of_session > (spec.bars_per_session - 1) * spec.minutes:
        return "outside_session"
    if minute_of_session % spec.minutes:
        return "off_interval_grid"
    if not calendar.is_trading_day(stamp.date()):
        return "non_trading_day"
    if None in (o, h, l, c) or min(o, h, l, c) <= 0:
        return "non_positive_or_non_finite_price"
    if l > min(o, c) or h < max(o, c) or l > h:
        return "ohlc_bounds_violated"
    if v is None or v < 0:
        return "negative_or_non_finite_volume"
    return None


def validate_intraday_rows(
    rows: Iterable[Sequence],
    *,
    interval: str,
    start: str | date,
    end: str | date,
    tickers: Sequence[str],
    calendar: TradingCalendar | None = None,
    source: str = "collected_rows",
) -> IntradayDataset:
    """Validate ``(ticker, interval, datetime, open, high, low, close, volume)`` rows.

    Pure: the caller decides where rows came from. ``tickers`` is the declared
    request; requested ticker-days without rows are reported UNAVAILABLE.
    """
    spec = interval_spec(interval)
    calendar = calendar or default_calendar()
    first, last = iso_day(start), iso_day(end)
    if last < first:
        raise ValueError("end must not precede start")
    requested = tuple(sorted({str(t).strip().upper() for t in tickers if str(t).strip()}))
    if not requested:
        raise ValueError("at least one ticker must be requested")

    label_counts: Counter = Counter()
    other_labels: dict = defaultdict(set)          # (ticker, day) -> labels
    seen: dict = {}                                # (ticker, stamp) -> values
    per_day: dict = defaultdict(list)              # (ticker, day) -> [Bar]
    invalid: dict = defaultdict(Counter)           # (ticker, day) -> reasons
    duplicates: Counter = Counter()
    out_of_request = 0
    for raw in rows:
        ticker = str(raw[0]).strip().upper()
        label = str(raw[1])
        try:
            stamp = parse_bar_start(raw[2])
        except (TypeError, ValueError):
            day_text = str(raw[2])[:10]
            if ticker in requested and label == spec.label:
                invalid[(ticker, day_text)]["unparseable_timestamp"] += 1
            continue
        day = stamp.date()
        if ticker not in requested or not first <= day <= last:
            out_of_request += 1
            continue
        key_day = (ticker, day.isoformat())
        label_counts[label] += 1
        if label != spec.label:
            other_labels[key_day].add(label)
            continue
        if not calendar.covers(day):
            invalid[key_day]["calendar_unavailable"] += 1
            continue
        o, h, l, c, v = (_finite(value) for value in raw[3:8])
        problem = _row_problem(spec, stamp, o, h, l, c, v, calendar)
        if problem:
            invalid[key_day][problem] += 1
            continue
        values = (o, h, l, c, v)
        previous = seen.get((ticker, stamp))
        if previous is not None:
            if previous == values:
                duplicates[key_day] += 1
            else:
                invalid[key_day]["conflicting_duplicate"] += 1
            continue
        seen[(ticker, stamp)] = values
        kind = BAR_TRADED if v > 0 else (BAR_NO_TRADE_MARK if h == l else BAR_ZERO_VOLUME_WITH_RANGE)
        per_day[key_day].append(Bar(ticker, stamp, o, h, l, c, v, kind, spec.minutes))

    dataset = IntradayDataset(interval=spec)
    accepted_rows: list[tuple] = []
    statuses: Counter = Counter()
    day = first
    while day <= last:
        day_text = day.isoformat()
        calendar_ok = calendar.covers(day)
        trading = calendar_ok and calendar.is_trading_day(day)
        for ticker in requested:
            key = (ticker, day_text)
            has_evidence = key in per_day or key in invalid or key in other_labels
            if not calendar_ok and day.weekday() >= 5 and not has_evidence:
                continue  # an uncovered weekend with no rows is not a requested session
            if calendar_ok and not trading and key not in invalid:
                continue  # weekend/holiday: no session was expected
            row = {
                "ticker": ticker, "trading_date": day_text, "interval": spec.label,
                "rows": 0, "expected_bars": spec.bars_per_session, "first_bar": None,
                "last_bar": None, "missing_bars": 0, "traded_bars": 0,
                "no_trade_marks": 0, "zero_volume_with_range": 0,
                "identical_duplicates": int(duplicates.get(key, 0)),
                "other_labels_present": sorted(other_labels.get(key, ())),
                "invalid_reasons": dict(sorted(invalid.get(key, Counter()).items())),
                "reasons": [],
            }
            bars = sorted(per_day.get(key, ()), key=lambda bar: bar.start)
            if not calendar_ok:
                row.update(status=STATUS_UNAVAILABLE, reasons=["calendar_unavailable"])
            elif invalid.get(key):
                row.update(status=STATUS_INVALID, reasons=sorted(invalid[key]))
            elif not bars:
                reasons = ["no_rows_for_interval"]
                if row["other_labels_present"]:
                    reasons.append("only_other_interval_labels")
                row.update(status=STATUS_UNAVAILABLE, reasons=reasons)
            else:
                kinds = Counter(bar.kind for bar in bars)
                first_bar, last_bar = bars[0].start, bars[-1].start
                row.update(
                    rows=len(bars), first_bar=first_bar.isoformat(), last_bar=last_bar.isoformat(),
                    missing_bars=spec.bars_per_session - len(bars),
                    traded_bars=kinds[BAR_TRADED], no_trade_marks=kinds[BAR_NO_TRADE_MARK],
                    zero_volume_with_range=kinds[BAR_ZERO_VOLUME_WITH_RANGE],
                )
                reasons = []
                if first_bar.time() != SESSION_OPEN:
                    reasons.append("late_start")
                if last_bar.time() != spec.last_bar_start:
                    reasons.append("early_end")
                span = int((last_bar - first_bar).total_seconds() // 60) // spec.minutes + 1
                if len(bars) < span:
                    reasons.append("missing_bars")
                if kinds[BAR_ZERO_VOLUME_WITH_RANGE]:
                    reasons.append("zero_volume_with_range")
                row.update(status=STATUS_PARTIAL if reasons else STATUS_COMPLETE, reasons=reasons)
                dataset.bars[key] = tuple(bars)
                accepted_rows.extend(
                    (bar.ticker, bar.start.strftime("%Y-%m-%dT%H:%M:%S"), bar.open, bar.high,
                     bar.low, bar.close, bar.volume) for bar in bars
                )
            if row["status"] == STATUS_INVALID:
                dataset.bars.pop(key, None)
            statuses[row["status"]] += 1
            dataset.coverage.append(row)
        day += timedelta(days=1)

    accepted_rows.sort()
    header = {
        "contract_version": CONTRACT_VERSION, "interval": spec.label, "clock": CLOCK,
        "requested": {"start": first.isoformat(), "end": last.isoformat(), "tickers": list(requested)},
    }
    dataset.manifest = {
        **header, "kind": "intraday", "source": source, "calendar": calendar.describe(),
        "row_counts": {
            "selected_interval_accepted": len(accepted_rows),
            "by_label": dict(sorted(label_counts.items())),
            "outside_request": out_of_request,
        },
        "status_counts": dict(sorted(statuses.items())),
        "dataset_sha256": _canonical_hash(header, accepted_rows),
    }
    return dataset


def load_intraday_dataset(
    db_path: str, *, interval: str, start: str, end: str, tickers: Sequence[str],
    calendar: TradingCalendar | None = None,
) -> IntradayDataset:
    """Read only the requested tickers/dates (every label) and validate them."""
    first, last = iso_day(start), iso_day(end)
    requested = sorted({str(t).strip().upper() for t in tickers if str(t).strip()})
    if not requested:
        raise ValueError("at least one ticker must be requested")
    placeholders = ",".join("?" for _ in requested)
    with closing(_read_only_connection(db_path)) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(intraday_cache)")}
        required = {"ticker", "interval", "datetime", "open", "high", "low", "close", "volume"}
        if not required <= columns:
            raise DatasetUnavailable("intraday_cache lacks interval provenance columns")
        rows = db.execute(
            "SELECT ticker,interval,datetime,open,high,low,close,volume FROM intraday_cache "
            f"WHERE UPPER(ticker) IN ({placeholders}) AND substr(datetime,1,10) BETWEEN ? AND ? "
            "ORDER BY ticker,datetime,interval",
            (*requested, first.isoformat(), last.isoformat()),
        ).fetchall()
    return validate_intraday_rows(
        rows, interval=interval, start=first, end=last, tickers=requested,
        calendar=calendar, source="sqlite:intraday_cache(read-only)",
    )


# ---- daily contract ---------------------------------------------------------

@dataclass(frozen=True)
class DailyBar:
    ticker: str
    day: date
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class DailyDataset:
    bars: dict = field(default_factory=dict)            # ticker -> tuple[DailyBar, ...] ascending
    invalid: dict = field(default_factory=dict)         # ticker -> {reason: count}
    suspected_actions: dict = field(default_factory=dict)  # ticker -> [iso dates]
    off_calendar: dict = field(default_factory=dict)       # ticker -> [iso dates]
    manifest: dict = field(default_factory=dict)

    def known_before(self, ticker: str, day: date, *, since: date | None = None) -> tuple:
        """Bars dated strictly before ``day`` (and on/after ``since``)."""
        return tuple(
            bar for bar in self.bars.get(ticker, ())
            if bar.day < day and (since is None or bar.day >= since)
        )

    def actions_between(self, ticker: str, start: date, end: date) -> list[str]:
        return [d for d in self.suspected_actions.get(ticker, ())
                if start <= date.fromisoformat(d) <= end]

    def off_calendar_between(self, ticker: str, start: date, end: date) -> list[str]:
        return [d for d in self.off_calendar.get(ticker, ())
                if start <= date.fromisoformat(d) <= end]


def validate_daily_rows(
    rows: Iterable[Sequence], *, tickers: Sequence[str], before: str | date,
    calendar: TradingCalendar | None = None, source: str = "collected_rows",
) -> DailyDataset:
    """Validate ``(ticker, date, open, high, low, close, volume)`` daily rows.

    Only rows dated strictly before ``before`` are retained. An invalid daily
    row makes that ticker's daily history unavailable (it is not skipped).

    A well-formed row on a date the audited calendar does not list as a
    session (for example an exchange special session such as a Sunday budget
    session) is kept and reported in ``off_calendar``; strategies decide
    whether such a date may sit inside their warm-up window. It is neither
    silently trusted nor allowed to invalidate an entire history.
    """
    calendar = calendar or default_calendar()
    cutoff = iso_day(before)
    requested = sorted({str(t).strip().upper() for t in tickers if str(t).strip()})
    per_ticker: dict = defaultdict(dict)
    invalid: dict = defaultdict(Counter)
    off_calendar: dict = defaultdict(set)
    zero_volume = 0
    for raw in rows:
        ticker = str(raw[0]).strip().upper()
        if ticker not in requested:
            continue
        try:
            day = iso_day(str(raw[1])[:10])
        except ValueError:
            invalid[ticker]["unparseable_date"] += 1
            continue
        if day >= cutoff:
            continue
        o, h, l, c, v = (_finite(value) for value in raw[2:7])
        problem = None
        if None in (o, h, l, c) or min(o, h, l, c) <= 0:
            problem = "non_positive_or_non_finite_price"
        elif l > min(o, c) or h < max(o, c):
            problem = "ohlc_bounds_violated"
        elif v is None or v < 0:
            problem = "negative_or_non_finite_volume"
        if problem:
            invalid[ticker][problem] += 1
            continue
        bar = DailyBar(ticker, day, o, h, l, c, v)
        if calendar.covers(day) and not calendar.is_trading_day(day):
            off_calendar[ticker].add(day.isoformat())
        previous = per_ticker[ticker].get(day)
        if previous is not None and previous != bar:
            invalid[ticker]["conflicting_duplicate"] += 1
            continue
        per_ticker[ticker][day] = bar
        zero_volume += int(v == 0)
    dataset = DailyDataset()
    accepted: list[tuple] = []
    for ticker in requested:
        if invalid.get(ticker):
            dataset.invalid[ticker] = dict(sorted(invalid[ticker].items()))
            continue
        ordered = tuple(per_ticker[ticker][d] for d in sorted(per_ticker.get(ticker, {})))
        dataset.bars[ticker] = ordered
        actions = []
        for prior, bar in zip(ordered, ordered[1:]):
            if (abs(bar.open / prior.close - 1) > CORPORATE_ACTION_MOVE
                    or abs(bar.close / prior.close - 1) > CORPORATE_ACTION_MOVE):
                actions.append(bar.day.isoformat())
        if actions:
            dataset.suspected_actions[ticker] = actions
        if off_calendar.get(ticker):
            dataset.off_calendar[ticker] = sorted(off_calendar[ticker])
        accepted.extend((b.ticker, b.day.isoformat(), b.open, b.high, b.low, b.close, b.volume)
                        for b in ordered)
    accepted.sort()
    header = {"contract_version": CONTRACT_VERSION, "interval": "day",
              "requested": {"before": cutoff.isoformat(), "tickers": requested}}
    dataset.manifest = {
        **header, "kind": "daily", "source": source,
        "point_in_time_rule": "bar dated D informs decisions only after D",
        "adjustment_basis": DAILY_ADJUSTMENT_BASIS,
        "corporate_action_rule": f"abs move > {CORPORATE_ACTION_MOVE:.0%} reported as suspected, never repaired",
        "accepted_rows": len(accepted), "zero_volume_days": zero_volume,
        "invalid": dict(sorted(dataset.invalid.items())),
        "suspected_corporate_actions": dict(sorted(dataset.suspected_actions.items())),
        "off_calendar_dates": dict(sorted(Counter(
            day for days in dataset.off_calendar.values() for day in days
        ).items())),
        "calendar": calendar.describe(),
        "dataset_sha256": _canonical_hash(header, accepted),
    }
    return dataset


def load_daily_dataset(
    db_path: str, *, tickers: Sequence[str], before: str,
    calendar: TradingCalendar | None = None,
) -> DailyDataset:
    requested = sorted({str(t).strip().upper() for t in tickers if str(t).strip()})
    if not requested:
        raise ValueError("at least one ticker must be requested")
    placeholders = ",".join("?" for _ in requested)
    with closing(_read_only_connection(db_path)) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(ohlcv_cache)")}
        if not {"ticker", "date", "open", "high", "low", "close", "volume"} <= columns:
            raise DatasetUnavailable("ohlcv_cache daily history is missing or incomplete")
        rows = db.execute(
            "SELECT ticker,date,open,high,low,close,volume FROM ohlcv_cache "
            f"WHERE UPPER(ticker) IN ({placeholders}) AND date < ? ORDER BY ticker,date",
            (*requested, iso_day(before).isoformat()),
        ).fetchall()
    return validate_daily_rows(rows, tickers=requested, before=before, calendar=calendar,
                               source="sqlite:ohlcv_cache(read-only)")
