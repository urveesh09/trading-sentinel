"""Offline paired directional replay of native N11T and frozen N012-A."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import hashlib
import importlib
from pathlib import Path
import sys
from typing import Iterable, Sequence

import fno_n11
from config import settings
from exam_scoring import summarize
from fno_exit_rules import IST
from shared_control import EntryDecision, Exit, SharedControl, Tick


RULES_PATH = Path(__file__).resolve().parent.parent / "2026-11-05-fno-expiry-followup/regular_rules.py"
RULES_SHA256 = "aef23b08f721e6ccddec64038b3906a93067685f7901e57c1be8178f90904233"
ARMS = ("N11T", "N012-A")


def frozen_rules():
    source = RULES_PATH.read_text(encoding="utf-8")
    if hashlib.sha256(source.encode()).hexdigest() != RULES_SHA256:
        raise ValueError("N012-A rule differs from freeze 2758869")
    sys.path.insert(0, str(RULES_PATH.parent))
    try:
        rules = importlib.import_module("regular_rules")
    finally:
        sys.path.pop(0)
    if Path(rules.__file__).resolve() != RULES_PATH:
        raise ValueError("loaded N012-A rule path differs from freeze")
    return rules


class TrendControl(SharedControl):
    def __init__(self, allocation, *, gate_tape=None):
        super().__init__(allocation, gate_tape=gate_tape)
        self._rules = frozen_rules()

    def _exit_params(self, position, now, future, params):
        if position.strategy == fno_n11.ADD:
            return params
        trend = getattr(position, "_n012_trend", None)
        if trend is None:
            trend = self._rules.Trend()
            position._n012_trend = trend
        status = trend.update(now, future, position.direction)
        return self._rules.trend_params(params, position, status)


@dataclass(frozen=True)
class CoverageGap:
    arm: str
    at: datetime
    reason: str
    position_id: int | None = None
    venue: str | None = None
    token: int | None = None


@dataclass(frozen=True)
class EntryResult:
    reason: str
    symbol: str | None
    qty: int | None
    cash_before_rs: float


@dataclass(frozen=True)
class EntryChange:
    at: datetime
    venue: str
    bar_ts: str
    control: EntryResult
    candidate: EntryResult


@dataclass(frozen=True)
class PairResult:
    gaps: tuple[CoverageGap, ...]
    entry_changes: tuple[EntryChange, ...]
    exits: dict[str, tuple[Exit, ...]]
    summaries: dict[str, dict] | None
    net_delta: Decimal | None
    uses_external_spreads: bool


def entry_result(book: SharedControl, decision: EntryDecision) -> EntryResult:
    p = book.positions.get(decision.position_id)
    return EntryResult(decision.reason, p.tradingsymbol if p else None, p.qty if p else None,
                       decision.cash_before_rs)


def compare(ticks: Iterable[Tick], expected_scan_clocks: Sequence[datetime], *,
            allocation=250_000., gate_tape=None) -> PairResult:
    """Drive separate wallets with one tape and an independently declared scan schedule.

    The caller qualifies the market inputs at each listed scan and supplies
    externally confirmed, identical spread events. The paired result is a
    directional comparison conditional on those events.
    """
    scans = set(expected_scan_clocks)
    if (not scans or len(scans) != len(expected_scan_clocks)
            or any(at.utcoffset() is None for at in scans)):
        raise ValueError("expected scan clocks must be distinct aware timestamps")
    days = {at.astimezone(IST).date() for at in scans}
    books = (SharedControl(allocation, gate_tape=gate_tape),
             TrendControl(allocation, gate_tape=gate_tape))
    gaps, changes = [], []
    exits = {arm: [] for arm in ARMS}
    seen_scans, end_by_day = set(), {}
    previous = None
    reported_by_position = defaultdict(set)
    uses_external_spreads = False
    for tick in ticks:
        at = tick.at
        if at.utcoffset() is None or (previous is not None and at <= previous):
            raise ValueError("paired ticks must be aware and strictly increasing")
        now = at.astimezone(IST)
        day = now.date()
        if day not in days or (tick.entries and at not in scans):
            raise ValueError("market tick outside the declared entry scan schedule")
        if previous is not None and previous.astimezone(IST).date() != day and any(book.positions for book in books):
            break
        if at in scans:
            seen_scans.add(at)
        end_by_day[day] = now
        if tick.spread_reserve_rs or tick.spread_closes or (tick.earned and tick.earned.spread_reserve_rs):
            uses_external_spreads = True
        decisions = []
        for arm, book in zip(ARMS, books, strict=True):
            held = dict(book.positions)
            for p in held.values():
                reported = reported_by_position[arm, p.id]
                elapsed = (at - previous).total_seconds()
                if elapsed > settings.FNO_FAST_EXIT_INTERVAL_SEC and "management_clock_gap" not in reported:
                    gaps.append(CoverageGap(arm, at, "management_clock_gap", p.id, p.underlying, p.token))
                    reported.add("management_clock_gap")
                venue_mark = tick.marks.get(p.underlying)
                if (venue_mark is None or venue_mark.future is None) and "held_future_missing" not in reported:
                    gaps.append(CoverageGap(arm, at, "held_future_missing", p.id, p.underlying, p.token))
                    reported.add("held_future_missing")
            result = book.step(tick)
            exits[arm].extend(result.exits)
            for position_id in result.missing_marks:
                p = held[position_id]
                reported = reported_by_position[arm, position_id]
                if "held_bid_missing" not in reported:
                    gaps.append(CoverageGap(arm, at, "held_bid_missing", position_id, p.underlying, p.token))
                    reported.add("held_bid_missing")
            for item in result.entries:
                if item.reason in ("n11:gate_evidence_unavailable", "entry_depth_unavailable"):
                    gaps.append(CoverageGap(arm, at, item.reason))
            for item in result.earned:
                if item.reason in ("earned_stage_unavailable", "earned_quote_unavailable",
                                   "earned_ask_depth_unavailable", "parent_management_unavailable"):
                    p = held[item.parent_id]
                    gaps.append(CoverageGap(arm, at, item.reason, p.id, p.underlying, p.token))
            decisions.append(result.entries)
        for left, right in zip(*decisions, strict=True):
            if (left.venue, left.bar_ts) != (right.venue, right.bar_ts):
                raise ValueError("paired entry decisions differ in signal identity")
            a, b = entry_result(books[0], left), entry_result(books[1], right)
            if (a.reason, a.symbol, a.qty) != (b.reason, b.symbol, b.qty):
                changes.append(EntryChange(at, left.venue, left.bar_ts, a, b))
        previous = at

    gaps.extend(CoverageGap("BOTH", at, "entry_scan_missing") for at in sorted(scans - seen_scans))
    for day in sorted(days):
        until = end_by_day.get(day)
        if until is None or until.hour * 60 + until.minute < settings.FNO_HARD_FLAT_MIN:
            clock = min(at for at in scans if at.astimezone(IST).date() == day)
            gaps.append(CoverageGap("BOTH", until or clock, "session_horizon_missing"))
    for arm, book in zip(ARMS, books, strict=True):
        for p in book.positions.values():
            gaps.append(CoverageGap(arm, previous, "unresolved_position", p.id, p.underlying, p.token))

    summaries = None
    delta = None
    if not gaps:
        summaries = {
            arm: summarize([{"status": "CLOSED", "exit_time": close.at.isoformat(), "net_pnl": close.pnl}
                            for close in book.closes], Decimal(str(allocation)))
            for arm, book in zip(ARMS, books, strict=True)
        }
        delta = summaries[ARMS[1]]["net"] - summaries[ARMS[0]]["net"]
    return PairResult(tuple(gaps), tuple(changes), {arm: tuple(rows) for arm, rows in exits.items()},
                      summaries, delta, uses_external_spreads)
