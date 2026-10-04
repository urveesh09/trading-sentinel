"""T0 pure, restartable `PEN_TRADER_V1` setup-state prototype.

This module is deliberately outside the Penny runtime.  It turns complete,
already-available bars into *entry intent* only; no function here can fetch a
quote, reserve cash, submit an order, write a database row, or change F&O.
Later research adapters must still apply the shipped Penny risk/executor
contracts before an intent could become a simulated fill.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from enum import Enum
import hashlib
import math
from typing import Any, Mapping


POLICY_VERSION = "PEN_TRADER_V1"


class SetupState(str, Enum):
    WATCH = "WATCH"
    ARMED = "ARMED"
    ENTRY_INTENT = "ENTRY_INTENT"
    OPEN = "OPEN"
    EXIT_PENDING = "EXIT_PENDING"
    CLOSED = "CLOSED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"
    COOLDOWN = "COOLDOWN"


_TERMINAL = frozenset({SetupState.CLOSED, SetupState.INVALIDATED, SetupState.EXPIRED})
_TRANSITIONS = {
    SetupState.WATCH: {SetupState.ARMED, SetupState.INVALIDATED, SetupState.EXPIRED},
    SetupState.ARMED: {SetupState.ENTRY_INTENT, SetupState.INVALIDATED, SetupState.EXPIRED},
    SetupState.ENTRY_INTENT: {SetupState.OPEN, SetupState.INVALIDATED, SetupState.EXPIRED},
    SetupState.OPEN: {SetupState.EXIT_PENDING},
    SetupState.EXIT_PENDING: {SetupState.CLOSED},
    SetupState.CLOSED: {SetupState.COOLDOWN},
    SetupState.COOLDOWN: set(),
    SetupState.INVALIDATED: set(),
    SetupState.EXPIRED: set(),
}


def _finite_positive(value: float, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite and positive") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return number


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


@dataclass(frozen=True)
class CompletedBar:
    """One completed, visible minute bar. `available_at` is the causal clock."""
    observation_id: str
    observed_at: datetime
    available_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        if not str(self.observation_id).strip():
            raise ValueError("observation_id is required")
        observed, available = _aware(self.observed_at, "observed_at"), _aware(self.available_at, "available_at")
        if available < observed:
            raise ValueError("available_at must not precede observed_at")
        open_, high, low, close = (_finite_positive(value, name) for name, value in (
            ("open", self.open), ("high", self.high), ("low", self.low), ("close", self.close)))
        if low > min(open_, close) or high < max(open_, close) or low > high:
            raise ValueError("bar OHLC geometry is invalid")
        try:
            volume = float(self.volume)
        except (TypeError, ValueError) as exc:
            raise ValueError("volume must be finite and non-negative") from exc
        if not math.isfinite(volume) or volume < 0:
            raise ValueError("volume must be finite and non-negative")


@dataclass(frozen=True)
class PennySetup:
    """Durable state. All prices/times are frozen at the relevant transition."""
    thesis_id: str
    ticker: str
    policy_version: str
    state: SetupState
    revision: int
    anchor: float
    anchor_available_at: datetime
    armed_at: datetime | None
    expires_at: datetime
    invalidation: float
    initial_stop: float
    trigger_close: float | None
    entry_intent_price: float | None
    entry_kind: str | None
    baseline_status: str
    last_observation_id: str
    reason: str

    def __post_init__(self) -> None:
        if not self.thesis_id or not self.ticker or not self.policy_version:
            raise ValueError("thesis_id, ticker and policy_version are required")
        if self.revision < 0:
            raise ValueError("revision must be non-negative")
        _finite_positive(self.anchor, "anchor")
        _finite_positive(self.invalidation, "invalidation")
        _finite_positive(self.initial_stop, "initial_stop")
        if self.invalidation != self.initial_stop:
            raise ValueError("initial stop must equal the frozen invalidation")
        if self.initial_stop >= self.anchor:
            raise ValueError("initial stop must be below the frozen anchor")
        anchor_time, expiry = _aware(self.anchor_available_at, "anchor_available_at"), _aware(self.expires_at, "expires_at")
        if expiry <= anchor_time:
            raise ValueError("expires_at must follow anchor_available_at")
        if self.armed_at is not None:
            _aware(self.armed_at, "armed_at")

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["state"] = self.state.value
        for name in ("anchor_available_at", "armed_at", "expires_at"):
            if out[name] is not None:
                out[name] = out[name].isoformat()
        return out

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PennySetup":
        payload = dict(value)
        payload["state"] = SetupState(payload["state"])
        for name in ("anchor_available_at", "armed_at", "expires_at"):
            if payload.get(name) is not None:
                payload[name] = datetime.fromisoformat(str(payload[name]).replace("Z", "+00:00"))
        return cls(**payload)


@dataclass(frozen=True)
class EntryIntent:
    thesis_id: str
    ticker: str
    entry_kind: str
    anchor: float
    stop: float
    intended_price: float
    baseline_status: str


@dataclass(frozen=True)
class EntryPlan:
    """Bounded risk sizing of an intent, still not an order or fill."""
    thesis_id: str
    entry_price: float
    stop: float
    shares: int
    risk_per_share: float
    risk_rupees: float
    cash_rupees: float


@dataclass(frozen=True)
class SetupOutcome:
    setup: PennySetup | None
    action: str
    reason: str
    intent: EntryIntent | None = None


def _thesis_id(ticker: str, anchor: float, available_at: datetime) -> str:
    digest = hashlib.sha256(f"{POLICY_VERSION}|{ticker}|{anchor:.6f}|{available_at.isoformat()}".encode()).hexdigest()
    return f"PEN-{digest[:20]}"


def begin_watch(
    *, ticker: str, anchor: float, anchor_available_at: datetime, expiry_minutes: int = 10,
    noise_allowance: float = 0.05, baseline_accepted: bool = False,
) -> PennySetup:
    """Create a new thesis from a pre-confirmation structure anchor only."""
    anchor = _finite_positive(anchor, "anchor")
    available = _aware(anchor_available_at, "anchor_available_at")
    if not isinstance(expiry_minutes, int) or expiry_minutes < 1:
        raise ValueError("expiry_minutes must be a positive integer")
    allowance = _finite_positive(noise_allowance, "noise_allowance")
    stop = anchor - allowance
    if stop <= 0:
        raise ValueError("noise allowance makes the structural stop non-positive")
    clean_ticker = str(ticker).strip().upper()
    if not clean_ticker:
        raise ValueError("ticker is required")
    return PennySetup(
        thesis_id=_thesis_id(clean_ticker, anchor, available), ticker=clean_ticker,
        policy_version=POLICY_VERSION, state=SetupState.WATCH, revision=0, anchor=anchor,
        anchor_available_at=available, armed_at=None, expires_at=available + timedelta(minutes=expiry_minutes),
        invalidation=stop, initial_stop=stop, trigger_close=None, entry_intent_price=None,
        entry_kind=None, baseline_status="baseline_accepted" if baseline_accepted else "baseline_rejected",
        last_observation_id="", reason="watch_created_from_prior_structure",
    )


def watch_from_prior_bars(
    *, ticker: str, prior_bars: tuple[CompletedBar, ...], decision_at: datetime,
    expiry_minutes: int = 10, noise_allowance: float = 0.05,
    baseline_accepted: bool = False,
) -> PennySetup | None:
    """Derive a watch from a declared pre-decision structure window.

    The current/confirmation bar is intentionally not an input.  Returning
    ``None`` for insufficient or not-yet-visible history is an availability
    outcome, not a substitute anchor or a permissive fallback.
    """
    decision = _aware(decision_at, "decision_at")
    if len(prior_bars) < 3:
        return None
    if any(bar.available_at > decision for bar in prior_bars):
        return None
    anchor_bar = max(prior_bars, key=lambda bar: (bar.high, bar.available_at, bar.observation_id))
    return begin_watch(ticker=ticker, anchor=anchor_bar.high,
                       anchor_available_at=anchor_bar.available_at,
                       expiry_minutes=expiry_minutes, noise_allowance=noise_allowance,
                       baseline_accepted=baseline_accepted)


def _transition(setup: PennySetup, state: SetupState, *, observation: CompletedBar,
                reason: str, intent_price: float | None = None, entry_kind: str | None = None) -> PennySetup:
    if setup.state == state and setup.last_observation_id == observation.observation_id:
        return setup
    if state not in _TRANSITIONS[setup.state]:
        raise ValueError(f"invalid setup transition {setup.state.value}->{state.value}")
    return replace(setup, state=state, revision=setup.revision + 1,
                   armed_at=observation.available_at if state == SetupState.ARMED else setup.armed_at,
                   trigger_close=observation.close if state == SetupState.ARMED else setup.trigger_close,
                   entry_intent_price=intent_price if state == SetupState.ENTRY_INTENT else setup.entry_intent_price,
                   entry_kind=entry_kind if state == SetupState.ENTRY_INTENT else setup.entry_kind,
                   last_observation_id=observation.observation_id, reason=reason)


def advance_setup(
    setup: PennySetup, observation: CompletedBar, *, decision_at: datetime,
    retest_tolerance: float = 0.002,
) -> SetupOutcome:
    """Advance one armed thesis using only an already-available completed bar."""
    decision = _aware(decision_at, "decision_at")
    if decision < observation.available_at:
        raise ValueError("decision_at precedes completed-bar availability")
    if not 0 <= float(retest_tolerance) <= 0.02:
        raise ValueError("retest_tolerance must be between 0 and 0.02")
    if observation.observation_id == setup.last_observation_id:
        return SetupOutcome(setup, "IDEMPOTENT", "duplicate_observation")
    if setup.state in _TERMINAL or setup.state == SetupState.COOLDOWN:
        return SetupOutcome(setup, "TERMINAL", f"state_{setup.state.value.lower()}")
    if observation.available_at > setup.expires_at:
        expired = _transition(setup, SetupState.EXPIRED, observation=observation, reason="setup_expired")
        return SetupOutcome(expired, "EXPIRED", expired.reason)
    if observation.low <= setup.invalidation:
        invalid = _transition(setup, SetupState.INVALIDATED, observation=observation, reason="structural_invalidation")
        return SetupOutcome(invalid, "INVALIDATED", invalid.reason)
    if setup.state == SetupState.WATCH:
        if observation.close <= setup.anchor:
            watched = replace(setup, last_observation_id=observation.observation_id, reason="watch_waiting_for_breakout")
            return SetupOutcome(watched, "WATCH", watched.reason)
        armed = _transition(setup, SetupState.ARMED, observation=observation, reason="fresh_breakout_armed")
        return SetupOutcome(armed, "ARMED", armed.reason)
    if setup.state == SetupState.ARMED:
        # Both timing choices retain the original pre-confirmation anchor.
        if observation.low <= setup.anchor * (1 + float(retest_tolerance)) and observation.close > setup.anchor:
            intent = _transition(setup, SetupState.ENTRY_INTENT, observation=observation,
                                 reason="bounded_retest_reclaim", intent_price=observation.close,
                                 entry_kind="RETEST_RECLAIM")
        elif observation.low > setup.anchor and observation.close >= float(setup.trigger_close or setup.anchor):
            intent = _transition(setup, SetupState.ENTRY_INTENT, observation=observation,
                                 reason="continuation_confirmed", intent_price=observation.close,
                                 entry_kind="CONTINUATION")
        else:
            waiting = replace(setup, last_observation_id=observation.observation_id, reason="armed_waiting_for_timing")
            return SetupOutcome(waiting, "ARMED", waiting.reason)
        return SetupOutcome(intent, "ENTRY_INTENT", intent.reason, EntryIntent(
            thesis_id=intent.thesis_id, ticker=intent.ticker, entry_kind=str(intent.entry_kind),
            anchor=intent.anchor, stop=intent.initial_stop, intended_price=float(intent.entry_intent_price),
            baseline_status=intent.baseline_status,
        ))
    return SetupOutcome(setup, "NO_ACTION", f"state_{setup.state.value.lower()}")


def plan_entry(intent: EntryIntent, *, executable_price: float, own_cash: float,
               risk_budget: float, per_position_cash_cap: float) -> EntryPlan | None:
    """Size down from structural risk; refuse gaps/zero affordable quantity."""
    entry, cash, risk, cap = (_finite_positive(value, name) for name, value in (
        ("executable_price", executable_price), ("own_cash", own_cash),
        ("risk_budget", risk_budget), ("per_position_cash_cap", per_position_cash_cap)))
    if entry <= intent.stop:
        return None
    risk_per_share = entry - intent.stop
    shares = min(math.floor(risk / risk_per_share), math.floor(min(cash, cap) / entry))
    if shares < 1:
        return None
    return EntryPlan(intent.thesis_id, entry, intent.stop, shares, risk_per_share,
                     round(shares * risk_per_share, 6), round(shares * entry, 6))


def mark_open(setup: PennySetup, *, observation: CompletedBar) -> PennySetup:
    return _transition(setup, SetupState.OPEN, observation=observation, reason="entry_fill_confirmed")


def mark_exit_pending(setup: PennySetup, *, observation: CompletedBar) -> PennySetup:
    return _transition(setup, SetupState.EXIT_PENDING, observation=observation, reason="exit_submission_pending")


def mark_closed(setup: PennySetup, *, observation: CompletedBar) -> PennySetup:
    return _transition(setup, SetupState.CLOSED, observation=observation, reason="exit_fill_confirmed")


def begin_new_thesis(previous: PennySetup, **watch_kwargs: Any) -> PennySetup:
    """Terminal histories never auto-rearm; callers must record a new anchor."""
    if previous.state not in _TERMINAL and previous.state != SetupState.COOLDOWN:
        raise ValueError("a new thesis requires terminal or cooldown prior state")
    fresh = begin_watch(**watch_kwargs)
    if fresh.thesis_id == previous.thesis_id:
        raise ValueError("a new thesis needs a distinct anchor/time identity")
    return fresh
