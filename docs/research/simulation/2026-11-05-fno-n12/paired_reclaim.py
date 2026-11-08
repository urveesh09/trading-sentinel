"""Attribute the shared-wallet reclaim's incremental quote-replay results."""

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Iterable, Mapping, Sequence

from config import settings
from fno_exit_rules import IST
from paired_control import CoverageGap, EntryChange, PairResult, _compare
from prior_range_reclaim import Signal
from reclaim_shared import ReclaimControl, ReclaimDecision, ReclaimQuote
from shared_control import Exit, SharedControl, Tick


BASELINE, CHALLENGER = "N11T", "N11T+RECLAIM"


@dataclass(frozen=True)
class CapitalContext:
    held: tuple[tuple[str, str, int], ...]
    open_premium: float
    trades_today: int
    directional_net: float
    halts: tuple[str, ...]
    multiplier: float
    stance: str
    reentry: float | None


@dataclass(frozen=True)
class NativeEntryTrace:
    change: EntryChange
    baseline: CapitalContext
    challenger: CapitalContext


@dataclass(frozen=True, order=True)
class Ticket:
    at: datetime
    venue: str
    signal_bar: str
    kind: str
    parent_at: datetime | None = None


@dataclass(frozen=True)
class NativeTerms:
    symbol: str
    qty: int
    entry_premium: float
    premium_stop: float
    exit: Exit | None = None


@dataclass(frozen=True)
class EarnedContext:
    reason: str
    cash_before: float | None


@dataclass(frozen=True)
class NativeChange:
    ticket: Ticket
    baseline: NativeTerms | None
    challenger: NativeTerms | None
    baseline_earned: EarnedContext | None
    challenger_earned: EarnedContext | None


@dataclass(frozen=True)
class ReclaimPairResult:
    pair: PairResult
    reclaim_entries: tuple[ReclaimDecision, ...]
    reclaim_exits: tuple[Exit, ...]
    native_entries: tuple[NativeEntryTrace, ...]
    native_trades: tuple[NativeChange, ...]
    reclaim_net: Decimal | None
    native_net_delta: Decimal | None


class _TraceEntries:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.contexts = {}

    def _enter(self, venue, obs, now, tick):
        halts, stance = self._risk(now)
        day = now.date()
        key = (now, venue, obs.signal.bar_ts)
        reentry = self._stopped.get((day, venue), {}) if settings.FNO_REENTRY_REQUIRES_CONFIRMATION else {}
        self.contexts[key] = CapitalContext(
            tuple(sorted((p.strategy or "", p.tradingsymbol, p.qty) for p in self.positions.values())),
            self._open_premium(), self._trades.get(day, 0), self._directional_net.get(day, 0.),
            halts, stance.multiplier, stance.reason,
            reentry.get(obs.signal.direction.value),
        )
        return super()._enter(venue, obs, now, tick)


class _Control(_TraceEntries, SharedControl):
    pass


class _Challenger(_TraceEntries, ReclaimControl):
    def __init__(self, allocation, gate_tape, signals, quotes, stress_multiple):
        super().__init__(allocation, gate_tape=gate_tape, stress_multiple=stress_multiple)
        self.signals = signals
        self.quotes = quotes
        self.reclaim_entries = []

    def step(self, tick):
        result = self.step_with_reclaim(tick, self.quotes.get(tick.at))
        if result.entry is not None:
            self.reclaim_entries.append(result.entry)
        return result.shared

    def gaps(self):
        seen = {decision.signal_at for decision in self.reclaim_entries}
        for signal_at in sorted(self.signals.keys() - seen):
            yield CoverageGap(CHALLENGER, signal_at, "reclaim_first_quote_missing", venue="NIFTY")
        for decision in self.reclaim_entries:
            if decision.reason in {"first_quote_outside_window", "unverified_nifty_future", "unverified_nifty_chain"}:
                yield CoverageGap(CHALLENGER, decision.at, decision.reason, venue="NIFTY")


class _Trades:
    def __init__(self):
        self.keys = {}
        self.terms = {}
        self.earned = {}

    def _entry(self, book, position_id, key):
        if key in self.terms or position_id in self.keys:
            raise ValueError(f"Duplicate native trade identity: {key}")
        p = book.positions[position_id]
        self.keys[position_id] = key
        self.terms[key] = NativeTerms(p.tradingsymbol, p.qty, p.entry_premium, p.premium_stop)

    def observe(self, book, tick, result):
        for item in result.entries:
            if item.position_id is not None:
                self._entry(book, item.position_id, Ticket(tick.at, item.venue, item.bar_ts, "parent"))
        for item in result.earned:
            parent = self.keys[item.parent_id]
            key = Ticket(tick.at, parent.venue, parent.signal_bar, "earned", parent.at)
            self.earned[key] = EarnedContext(item.reason, item.cash_before_rs)
            if item.position_id is not None:
                self._entry(book, item.position_id, key)
        for close in result.exits:
            key = self.keys.get(close.position_id)
            if key is not None:
                # Each replay assigns its own integer IDs. The ticket key matches economic identity.
                self.terms[key] = replace(self.terms[key], exit=replace(close, position_id=0))

    def net(self):
        return sum((Decimal(str(item.exit.net)) for item in self.terms.values() if item.exit), Decimal(0))


def _quote_map(signals, quotes, scans):
    days = {at.astimezone(IST).date() for at in scans if at.utcoffset() is not None}
    signal_days, routed, matched = set(), {}, set()
    for at, signal in signals.items():
        if at.utcoffset() is None:
            raise ValueError("reclaim signal clock must be aware")
        local = at.astimezone(IST)
        day = local.date()
        if (day not in days or day in signal_days or local.second or local.microsecond
                or local.hour * 60 + local.minute != signal.minute):
            raise ValueError("reclaim signal outside the declared session or repeated")
        signal_days.add(day)
    for quote in quotes:
        at = quote.chain.taken_at
        if (signals.get(quote.signal_at) != quote.signal or quote.signal_at in matched
                or at.utcoffset() is None or at in routed
                or at.astimezone(IST).date() != quote.signal_at.astimezone(IST).date()):
            raise ValueError("reclaim quote does not uniquely match a declared signal")
        matched.add(quote.signal_at)
        routed[at] = quote
    return routed


def compare_reclaim(ticks: Iterable[Tick], expected_scans: Sequence[datetime], *,
                    signals: Mapping[datetime, Signal], quotes: Iterable[ReclaimQuote],
                    allocation=250_000., gate_tape=None, stress_multiple=0) -> ReclaimPairResult:
    """Compare complete quote paths conditional on the supplied common spread events."""
    routed = _quote_map(signals, quotes, expected_scans)
    control = _Control(allocation, gate_tape=gate_tape, stress_multiple=stress_multiple)
    challenger = _Challenger(allocation, gate_tape, signals, routed, stress_multiple)
    ledgers = {BASELINE: _Trades(), CHALLENGER: _Trades()}

    def observe(arm, book, tick, result):
        ledgers[arm].observe(book, tick, result)

    pair = _compare(ticks, expected_scans, (control, challenger), (BASELINE, CHALLENGER),
                    allocation=allocation, observe=observe, extra_coverage=challenger.gaps)
    entry_traces = []
    for change in pair.entry_changes:
        key = (change.at, change.venue, change.bar_ts)
        entry_traces.append(NativeEntryTrace(change, control.contexts[key], challenger.contexts[key]))
    left, right = ledgers[BASELINE], ledgers[CHALLENGER]
    native_changes = []
    for key in sorted(left.terms.keys() | right.terms.keys()):
        before, after = left.terms.get(key), right.terms.get(key)
        if before != after:
            native_changes.append(NativeChange(key, before, after, left.earned.get(key), right.earned.get(key)))

    reclaim_ids = {item.position_id for item in challenger.reclaim_entries if item.position_id is not None}
    reclaim_exits = tuple(close for close in pair.exits[CHALLENGER] if close.position_id in reclaim_ids)
    reclaim_net = native_delta = None
    if pair.net_delta is not None:
        if (len(reclaim_exits) != len(reclaim_ids) or any(not terms.exit for ledger in (left, right)
                                                        for terms in ledger.terms.values())):
            raise ValueError("Qualified shared wallet did not settle all accepted tickets")
        reclaim_net = sum((Decimal(str(item.net)) for item in reclaim_exits), Decimal(0))
        native_delta = right.net() - left.net()
        if pair.net_delta != native_delta + reclaim_net:
            raise ValueError("Native and reclaim deltas do not reconcile with the shared wallets")
    return ReclaimPairResult(pair, tuple(challenger.reclaim_entries), reclaim_exits,
                             tuple(entry_traces), tuple(native_changes), reclaim_net, native_delta)
