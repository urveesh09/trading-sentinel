"""Pure, restartable `PEN_TRADER_V1` Penny MIS trader policy (research only).

The module is deliberately outside the Penny runtime. It turns complete,
already-available minute bars into setup states, entry intents and position
management decisions. No function here can fetch a quote, reserve cash, submit
an order, write a database row, or touch F&O. Research adapters apply the
shipped Penny risk/executor contracts before an intent becomes a simulated fill.

What makes it different from the shipped breakout evaluator:

* Structure: the anchor is the high of a declared prior base, frozen before
  the confirmation bar. It is not the whole-day high plus a fixed buffer.
* Context instead of a conjunction: participation, bar surge, close location,
  VWAP side, chase distance and overhead room are scored. RSI is recorded but
  is not a reject reason, since a genuine breakout is "overbought" by construction.
* Timing: a strong, unextended breakout is entered on the confirmation bar.
  Otherwise the thesis stays ARMED and waits for a bounded retest/reclaim or a
  holding continuation. Two closes back inside the base invalidate it.
* Stop geometry: anchor minus a volatility-scaled noise allowance, chosen
  before entry and never widened. Overly wide stops and cost-dominated risk are
  declined rather than sized up.
* Thesis exits (THESIS variant): a failed breakout or stalled trade is cut
  early; a working trade locks breakeven, banks half at 2R when the integer
  quantity allows, and trails the remainder.
* Churn control: after a losing exit or invalidation the ticker cools down and
  a new thesis needs a higher anchor; entries per ticker-day are bounded.

Scores rank evidence. They are not win probabilities or profit estimates.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta
from enum import Enum
import hashlib
import math
from typing import Any, Callable, Mapping, Sequence


POLICY_VERSION = "PEN_TRADER_V1"
SESSION_OPEN_MINUTE = 9 * 60 + 15
SESSION_MINUTES = 375.0


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


@dataclass(frozen=True)
class TraderParams:
    """Frozen `PEN_TRADER_V1` parameters, declared before any scored run."""
    policy_version: str = "PEN_TRADER_V1"
    anchor_mode: str = "base"          # "base": prior lookback high; "day_high": new high of day
    base_lookback: int = 30            # bars defining the prior structure
    min_base_bars: int = 15
    entry_start_minute: int = 9 * 60 + 30
    entry_end_minute: int = 14 * 60 + 15
    min_pace_rvol: float = 1.0         # minimum participation (setup definition)
    min_surge: float = 0.0             # breakout-bar volume / prior 20-bar mean; 0 = scored only
    require_vwap: bool = False         # close above session VWAP as a setup requirement
    arm_score: float = 0.45
    fast_entry_score: float = 0.70
    fast_entry_max_chase_atr: float = 0.75
    fast_entry_min_clv: float = 0.60
    exhaustion_rsi: float = 85.0
    max_chase_atr: float = 1.5         # beyond this the breakout waits for a retest
    noise_atr_mult: float = 1.0
    min_noise_pct: float = 0.004
    min_stop_ticks: int = 3
    tick: float = 0.01
    max_stop_pct: float = 0.035
    retest_atr: float = 0.5
    arm_expiry_minutes: int = 15
    max_closes_inside_base: int = 2
    max_cost_share_of_risk: float = 0.25
    cooldown_minutes: int = 20
    max_entries_per_ticker_day: int = 2
    # thesis exit manager
    failed_breakout_closes: int = 2
    stall_minutes: int = 45
    stall_max_mfe_r: float = 0.5
    breakeven_r: float = 1.0
    partial_r: float = 2.0
    trail_start_r: float = 1.5
    trail_atr_mult: float = 2.0
    trail_min_r: float = 1.0
    eod_loss_cut_minute: int = 14 * 60 + 30

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_PARAMS = TraderParams()
# Round 2 (declared 2026-10-04 from the Sep 24-30 development diagnostics, before
# the untouched Sep 7-23/Oct 1 window was evaluated): round 1 lost money before
# costs because local 30-bar highs, early-session and low-participation breakouts
# were noise. V2 keeps the state machine, structural stop, no-RSI-veto and churn
# control but restricts recognition to new-high-of-day structure after 10:30
# with real participation, bar surge and VWAP support, managed by thesis exits.
V2_PARAMS = TraderParams(
    policy_version="PEN_TRADER_V2", anchor_mode="day_high", entry_start_minute=10 * 60 + 30,
    min_pace_rvol=1.8, min_surge=2.0, require_vwap=True, arm_score=0.55,
)
_WEIGHTS = {"participation": 0.25, "surge": 0.25, "close_location": 0.15,
            "vwap_side": 0.15, "chase": 0.10, "room": 0.10}


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


def _floor_tick(price: float, tick: float) -> float:
    return round(math.floor(price / tick + 1e-9) * tick, 6)


def _ceil_tick(price: float, tick: float) -> float:
    return round(math.ceil(price / tick - 1e-9) * tick, 6)


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


# ---- context ------------------------------------------------------------

def compute_context(
    bars: Sequence[CompletedBar], *, median_vol_20d: float | None, params: TraderParams = DEFAULT_PARAMS,
) -> dict[str, Any]:
    """Features for the latest completed bar, using only `bars` (all visible).

    The latest bar is the confirmation candidate. The base/anchor and the noise
    baseline (ATR) use strictly earlier bars, so confirmation data cannot move
    the structure it is judged against. Missing required inputs make the
    context unavailable; nothing is replaced with a neutral value.
    """
    from penny_engine_breakout import _rsi_14_wilder
    missing: list[str] = []
    if len(bars) < params.min_base_bars + 1:
        missing.append("base_bars")
    if not median_vol_20d or not math.isfinite(float(median_vol_20d)) or float(median_vol_20d) <= 0:
        missing.append("median_vol_20d")
    if missing:
        return {"available": False, "missing": missing}
    latest, prior = bars[-1], list(bars[:-1])
    base = prior if params.anchor_mode == "day_high" else prior[-params.base_lookback:]
    anchor = max(bar.high for bar in base)
    anchor_bar = max(base, key=lambda bar: (bar.high, bar.available_at))
    base_low = min(bar.low for bar in base)
    true_ranges = []
    for index, bar in enumerate(prior[-14:], start=max(len(prior) - 14, 0)):
        previous_close = prior[index - 1].close if index > 0 else bar.open
        true_ranges.append(max(bar.high, previous_close) - min(bar.low, previous_close))
    atr = sum(true_ranges) / len(true_ranges) if true_ranges else 0.0
    if atr <= 0:
        return {"available": False, "missing": ["atr_zero_range"]}
    cum_volume = sum(float(bar.volume) for bar in bars)
    typical_volume = sum((bar.high + bar.low + bar.close) / 3 * float(bar.volume) for bar in bars)
    vwap = typical_volume / cum_volume if cum_volume > 0 else None
    minute = latest.available_at.hour * 60 + latest.available_at.minute
    elapsed = min(max(minute - SESSION_OPEN_MINUTE, 1), SESSION_MINUTES)
    pace_rvol = cum_volume / (float(median_vol_20d) * elapsed / SESSION_MINUTES)
    recent = [float(bar.volume) for bar in prior[-20:]]
    mean_recent = sum(recent) / len(recent) if recent else 0.0
    surge = float(latest.volume) / mean_recent if mean_recent > 0 else None
    span = latest.high - latest.low
    close_location = (latest.close - latest.low) / span if span > 0 else 1.0
    prior_day_high = max(bar.high for bar in prior)
    return {
        "available": True, "missing": [], "minute": minute,
        "anchor": anchor, "anchor_available_at": anchor_bar.available_at, "base_low": base_low,
        "base_bars": len(base), "atr": atr, "vwap": vwap, "pace_rvol": pace_rvol, "surge": surge,
        "close_location": close_location, "close": latest.close, "low": latest.low, "high": latest.high,
        "rsi_14": _rsi_14_wilder([bar.close for bar in bars]),
        "chase_atr": (latest.close - anchor) / atr, "prior_day_high": prior_day_high,
    }


def structural_stop(anchor: float, atr: float, params: TraderParams = DEFAULT_PARAMS) -> float:
    """Anchor minus a volatility/price/tick-scaled noise allowance, tick-floored."""
    noise = max(params.noise_atr_mult * atr, params.min_noise_pct * anchor, params.min_stop_ticks * params.tick)
    return _floor_tick(anchor - noise, params.tick)


def score_breakout(context: Mapping[str, Any], params: TraderParams = DEFAULT_PARAMS) -> dict[str, Any]:
    """All condition outcomes and a bounded [0, 1] evidence score."""
    if not context.get("available"):
        return {"eligible": False, "fast_entry": False, "score": None,
                "failures": ["context_unavailable:" + ",".join(context.get("missing", []))], "components": {}}
    failures = []
    if not params.entry_start_minute <= context["minute"] < params.entry_end_minute:
        failures.append("entry_window")
    if context["close"] <= context["anchor"]:
        failures.append("no_close_above_structure")
    if context["base_bars"] < params.min_base_bars:
        failures.append("base_too_short")
    if context["pace_rvol"] < params.min_pace_rvol:
        failures.append("participation_below_pace")
    if params.min_surge and (context["surge"] is None or context["surge"] < params.min_surge):
        failures.append("breakout_bar_surge_below_minimum")
    if params.require_vwap and (context["vwap"] is None or context["close"] <= context["vwap"]):
        failures.append("close_not_above_vwap")
    stop = structural_stop(context["anchor"], context["atr"], params)
    if stop <= 0 or (context["close"] - stop) / context["close"] > params.max_stop_pct:
        failures.append("structural_stop_too_wide")
    risk = context["close"] - stop
    room = None
    if context["prior_day_high"] > context["close"] and risk > 0:
        room = (context["prior_day_high"] - context["close"]) / risk
    components = {
        "participation": min(1.0, max(0.0, (context["pace_rvol"] - 1.0) / 1.5)),
        "surge": 0.0 if context["surge"] is None else min(1.0, max(0.0, (context["surge"] - 1.0) / 2.0)),
        "close_location": context["close_location"],
        "vwap_side": 1.0 if context["vwap"] is not None and context["close"] > context["vwap"] else 0.0,
        "chase": 1.0 - min(1.0, max(0.0, context["chase_atr"]) / params.max_chase_atr),
        "room": 1.0 if room is None else min(1.0, room / 2.0),
    }
    score = round(sum(_WEIGHTS[name] * value for name, value in components.items()), 6)
    if not failures and score < params.arm_score:
        failures.append("score_below_arm")
    eligible = not failures
    fast = (eligible and score >= params.fast_entry_score
            and context["chase_atr"] <= params.fast_entry_max_chase_atr
            and context["close_location"] >= params.fast_entry_min_clv
            and context["rsi_14"] < params.exhaustion_rsi)
    return {"eligible": eligible, "fast_entry": fast, "score": score, "failures": failures,
            "components": {k: round(v, 6) for k, v in components.items()},
            "structural_stop": stop, "room_r": None if room is None else round(room, 6)}


# ---- durable setup state ------------------------------------------------

@dataclass(frozen=True)
class PennySetup:
    """Durable state. Prices/times are frozen at the relevant transition."""
    thesis_id: str
    ticker: str
    policy_version: str
    state: SetupState
    revision: int
    anchor: float
    anchor_available_at: datetime
    created_at: datetime
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
    atr: float = 0.0
    score: float | None = None
    closes_inside_base: int = 0

    def __post_init__(self) -> None:
        if not self.thesis_id or not self.ticker or not self.policy_version:
            raise ValueError("thesis_id, ticker and policy_version are required")
        if self.revision < 0:
            raise ValueError("revision must be non-negative")
        _finite_positive(self.anchor, "anchor")
        _finite_positive(self.invalidation, "invalidation")
        _finite_positive(self.initial_stop, "initial_stop")
        if self.initial_stop >= self.anchor or self.invalidation >= self.anchor:
            raise ValueError("initial stop and invalidation must be below the frozen anchor")
        anchor_time, created = _aware(self.anchor_available_at, "anchor_available_at"), _aware(self.created_at, "created_at")
        expiry = _aware(self.expires_at, "expires_at")
        if created < anchor_time:
            raise ValueError("created_at must not precede the anchor's availability")
        if expiry <= created:
            raise ValueError("expires_at must follow created_at")
        if self.armed_at is not None:
            _aware(self.armed_at, "armed_at")

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["state"] = self.state.value
        for name in ("anchor_available_at", "created_at", "armed_at", "expires_at"):
            if out[name] is not None:
                out[name] = out[name].isoformat()
        return out

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PennySetup":
        payload = dict(value)
        payload["state"] = SetupState(payload["state"])
        for name in ("anchor_available_at", "created_at", "armed_at", "expires_at"):
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
    score: float | None = None


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
    round_trip_cost: float = 0.0


@dataclass(frozen=True)
class SetupOutcome:
    setup: PennySetup | None
    action: str
    reason: str
    intent: EntryIntent | None = None
    evidence: Mapping[str, Any] = field(default_factory=dict)


def _thesis_id(ticker: str, anchor: float, available_at: datetime, version: str = POLICY_VERSION) -> str:
    digest = hashlib.sha256(f"{version}|{ticker}|{anchor:.6f}|{available_at.isoformat()}".encode()).hexdigest()
    return f"PEN-{digest[:20]}"


def begin_watch(
    *, ticker: str, anchor: float, anchor_available_at: datetime, created_at: datetime | None = None,
    expiry_minutes: int = 10, stop: float | None = None, noise_allowance: float = 0.05,
    baseline_accepted: bool = False, atr: float = 0.0, invalidation: float | None = None,
    policy_version: str = POLICY_VERSION,
) -> PennySetup:
    """Create a thesis from a pre-confirmation structure anchor.

    Expiry runs from ``created_at`` (the decision clock), never from the age of
    the anchor bar, so an old base high cannot create an already-expired watch.
    ``invalidation`` is the pre-breakout structure break (normally the base low);
    ordinary consolidation under the anchor must not kill a WATCH. Arming
    replaces it with the trade's structural stop.
    """
    anchor = _finite_positive(anchor, "anchor")
    available = _aware(anchor_available_at, "anchor_available_at")
    created = available if created_at is None else _aware(created_at, "created_at")
    if not isinstance(expiry_minutes, int) or expiry_minutes < 1:
        raise ValueError("expiry_minutes must be a positive integer")
    if stop is None:
        stop = anchor - _finite_positive(noise_allowance, "noise_allowance")
    stop = float(stop)
    if not 0 < stop < anchor:
        raise ValueError("structural stop must be positive and below the anchor")
    watch_invalidation = stop if invalidation is None else min(float(invalidation), stop)
    if watch_invalidation <= 0:
        raise ValueError("invalidation must be positive")
    clean_ticker = str(ticker).strip().upper()
    if not clean_ticker:
        raise ValueError("ticker is required")
    return PennySetup(
        thesis_id=_thesis_id(clean_ticker, anchor, available, policy_version), ticker=clean_ticker,
        policy_version=policy_version, state=SetupState.WATCH, revision=0, anchor=anchor,
        anchor_available_at=available, created_at=created, armed_at=None,
        expires_at=created + timedelta(minutes=expiry_minutes),
        invalidation=watch_invalidation, initial_stop=stop, trigger_close=None, entry_intent_price=None,
        entry_kind=None, baseline_status="baseline_accepted" if baseline_accepted else "baseline_rejected",
        last_observation_id="", reason="watch_created_from_prior_structure", atr=float(atr),
    )


def watch_from_prior_bars(
    *, ticker: str, prior_bars: tuple[CompletedBar, ...], decision_at: datetime,
    expiry_minutes: int = 10, noise_allowance: float = 0.05,
    baseline_accepted: bool = False,
) -> PennySetup | None:
    """Derive a watch from a declared pre-decision structure window.

    Returning ``None`` for insufficient or not-yet-visible history is an
    availability outcome, not a substitute anchor or a permissive fallback.
    """
    decision = _aware(decision_at, "decision_at")
    if len(prior_bars) < 3:
        return None
    if any(bar.available_at > decision for bar in prior_bars):
        return None
    anchor_bar = max(prior_bars, key=lambda bar: (bar.high, bar.available_at, bar.observation_id))
    return begin_watch(ticker=ticker, anchor=anchor_bar.high, anchor_available_at=anchor_bar.available_at,
                       created_at=decision, expiry_minutes=expiry_minutes, noise_allowance=noise_allowance,
                       baseline_accepted=baseline_accepted, invalidation=min(bar.low for bar in prior_bars))


def _transition(setup: PennySetup, state: SetupState, *, observation: CompletedBar,
                reason: str, intent_price: float | None = None, entry_kind: str | None = None,
                stop: float | None = None) -> PennySetup:
    if setup.state == state and setup.last_observation_id == observation.observation_id:
        return setup
    if state not in _TRANSITIONS[setup.state]:
        raise ValueError(f"invalid setup transition {setup.state.value}->{state.value}")
    new_stop = setup.initial_stop
    invalidation = new_stop if state in (SetupState.ARMED, SetupState.ENTRY_INTENT) else setup.invalidation
    if stop is not None:
        if state != SetupState.ENTRY_INTENT:
            raise ValueError("the initial stop can only be refined at entry intent")
        new_stop = min(setup.initial_stop, float(stop))   # pre-entry refinement may only widen structure
        invalidation = new_stop
    return replace(setup, state=state, revision=setup.revision + 1,
                   armed_at=observation.available_at if state == SetupState.ARMED else setup.armed_at,
                   trigger_close=observation.close if state == SetupState.ARMED else setup.trigger_close,
                   entry_intent_price=intent_price if state == SetupState.ENTRY_INTENT else setup.entry_intent_price,
                   entry_kind=entry_kind if state == SetupState.ENTRY_INTENT else setup.entry_kind,
                   initial_stop=new_stop, invalidation=invalidation,
                   last_observation_id=observation.observation_id, reason=reason)


def _intent_outcome(setup: PennySetup, evidence: Mapping[str, Any] | None = None) -> SetupOutcome:
    return SetupOutcome(setup, "ENTRY_INTENT", setup.reason, EntryIntent(
        thesis_id=setup.thesis_id, ticker=setup.ticker, entry_kind=str(setup.entry_kind),
        anchor=setup.anchor, stop=setup.initial_stop, intended_price=float(setup.entry_intent_price),
        baseline_status=setup.baseline_status, score=setup.score,
    ), dict(evidence or {}))


def detect_breakout(
    *, ticker: str, bars: Sequence[CompletedBar], median_vol_20d: float | None,
    decision_at: datetime, baseline_accepted: bool = False, params: TraderParams = DEFAULT_PARAMS,
) -> SetupOutcome:
    """Recognise a fresh structural breakout on the latest completed bar.

    Returns an ARMED thesis, an immediate ENTRY_INTENT for a strong unextended
    breakout, or a NO_SETUP outcome carrying every failed condition.
    """
    decision = _aware(decision_at, "decision_at")
    if not bars or bars[-1].available_at > decision:
        return SetupOutcome(None, "NO_SETUP", "latest_bar_not_available")
    # Cheap structural pre-checks, so a per-minute caller does not pay for a
    # full context on bars that cannot be a breakout. Same outcomes as below.
    minute = bars[-1].available_at.hour * 60 + bars[-1].available_at.minute
    if not params.entry_start_minute <= minute < params.entry_end_minute:
        return SetupOutcome(None, "NO_SETUP", "entry_window")
    lookback = len(bars) if params.anchor_mode == "day_high" else params.base_lookback
    if len(bars) > params.min_base_bars and bars[-1].close <= max(
            bar.high for bar in bars[-1 - lookback:-1]):
        return SetupOutcome(None, "NO_SETUP", "no_close_above_structure")
    context = compute_context(bars, median_vol_20d=median_vol_20d, params=params)
    verdict = score_breakout(context, params)
    evidence = {"context": {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in context.items()},
                "verdict": verdict}
    if not verdict["eligible"]:
        return SetupOutcome(None, "NO_SETUP", verdict["failures"][0], evidence=evidence)
    latest = bars[-1]
    # A fresh breakout: the previous close was still inside the base.
    if len(bars) >= 2 and bars[-2].close > context["anchor"]:
        return SetupOutcome(None, "NO_SETUP", "not_fresh_breakout", evidence=evidence)
    watch = begin_watch(ticker=ticker, anchor=context["anchor"], anchor_available_at=context["anchor_available_at"],
                        created_at=latest.available_at, expiry_minutes=params.arm_expiry_minutes,
                        stop=verdict["structural_stop"], baseline_accepted=baseline_accepted, atr=context["atr"],
                        policy_version=params.policy_version)
    watch = replace(watch, score=verdict["score"])
    armed = _transition(watch, SetupState.ARMED, observation=latest, reason="fresh_breakout_armed")
    if verdict["fast_entry"]:
        intent = _transition(armed, SetupState.ENTRY_INTENT, observation=latest,
                             reason="strong_breakout_fast_entry", intent_price=latest.close, entry_kind="FAST_BREAKOUT")
        return _intent_outcome(intent, evidence)
    return SetupOutcome(armed, "ARMED", armed.reason, evidence=evidence)


def advance_setup(
    setup: PennySetup, observation: CompletedBar, *, decision_at: datetime,
    retest_tolerance: float | None = None, params: TraderParams = DEFAULT_PARAMS,
) -> SetupOutcome:
    """Advance one thesis using only an already-available completed bar.

    WATCH waits below the anchor and is invalidated only by structural breakage
    (the frozen stop), not by ordinary consolidation. ARMED takes a bounded
    retest/reclaim or a holding continuation; repeated closes back inside the
    base or a breached stop invalidate it.
    """
    decision = _aware(decision_at, "decision_at")
    if decision < observation.available_at:
        raise ValueError("decision_at precedes completed-bar availability")
    if retest_tolerance is not None and not 0 <= float(retest_tolerance) <= 0.02:
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
        if observation.close <= setup.anchor:
            inside = setup.closes_inside_base + 1
            if inside >= params.max_closes_inside_base:
                invalid = _transition(setup, SetupState.INVALIDATED, observation=observation,
                                      reason="breakout_failed_back_inside_base")
                return SetupOutcome(replace(invalid, closes_inside_base=inside), "INVALIDATED", invalid.reason)
            waiting = replace(setup, last_observation_id=observation.observation_id,
                              closes_inside_base=inside, reason="armed_close_inside_base")
            return SetupOutcome(waiting, "ARMED", waiting.reason)
        if retest_tolerance is not None:
            zone = setup.anchor * (1 + float(retest_tolerance))
        else:
            zone = setup.anchor + params.retest_atr * max(setup.atr, params.tick)
        if observation.low <= zone:
            # Pre-entry refinement: the retest low is new structure below which
            # the reclaim has failed; the stop can only move further away.
            stop = min(setup.initial_stop, _floor_tick(observation.low - params.min_stop_ticks * params.tick, params.tick))
            intent = _transition(setup, SetupState.ENTRY_INTENT, observation=observation,
                                 reason="bounded_retest_reclaim", intent_price=observation.close,
                                 entry_kind="RETEST_RECLAIM", stop=stop)
        elif observation.close >= float(setup.trigger_close or setup.anchor):
            intent = _transition(setup, SetupState.ENTRY_INTENT, observation=observation,
                                 reason="continuation_confirmed", intent_price=observation.close,
                                 entry_kind="CONTINUATION")
        else:
            waiting = replace(setup, last_observation_id=observation.observation_id,
                              closes_inside_base=0, reason="armed_waiting_for_timing")
            return SetupOutcome(waiting, "ARMED", waiting.reason)
        return _intent_outcome(replace(intent, closes_inside_base=0))
    return SetupOutcome(setup, "NO_ACTION", f"state_{setup.state.value.lower()}")


def plan_entry(intent: EntryIntent, *, executable_price: float, own_cash: float,
               risk_budget: float, per_position_cash_cap: float,
               max_shares: int | None = None,
               round_trip_cost: Callable[[float, float, int], float] | None = None,
               params: TraderParams = DEFAULT_PARAMS) -> EntryPlan | None:
    """Size from structural risk within own cash; refuse gaps/unviable risk.

    ``max_shares`` lets an adapter apply the shipped risk engine's sizing. A
    ``round_trip_cost`` callable declines trades whose costs would dominate
    the planned risk (a stop-out would cost far more than the stop distance).
    """
    entry, cash, risk, cap = (_finite_positive(value, name) for name, value in (
        ("executable_price", executable_price), ("own_cash", own_cash),
        ("risk_budget", risk_budget), ("per_position_cash_cap", per_position_cash_cap)))
    if entry <= intent.stop:
        return None
    risk_per_share = entry - intent.stop
    if risk_per_share / entry > params.max_stop_pct:
        return None
    shares = min(math.floor(risk / risk_per_share), math.floor(min(cash, cap) / entry))
    if max_shares is not None:
        shares = min(shares, int(max_shares))
    if shares < 1:
        return None
    cost = 0.0
    if round_trip_cost is not None:
        cost = float(round_trip_cost(entry, intent.stop, shares))
        if cost > params.max_cost_share_of_risk * shares * risk_per_share:
            return None
    return EntryPlan(intent.thesis_id, entry, intent.stop, shares, risk_per_share,
                     round(shares * risk_per_share, 6), round(shares * entry, 6), round(cost, 6))


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


@dataclass(frozen=True)
class TickerMemory:
    """Per ticker-day churn memory: what was tried and when it may be retried."""
    entries: int = 0
    last_anchor: float | None = None
    cooldown_until: datetime | None = None

    def allows(self, *, anchor: float, now: datetime, params: TraderParams = DEFAULT_PARAMS) -> str | None:
        if self.entries >= params.max_entries_per_ticker_day:
            return "ticker_entry_limit"
        if self.cooldown_until is not None and now < self.cooldown_until:
            return "ticker_cooldown"
        if self.cooldown_until is not None and self.last_anchor is not None and anchor <= self.last_anchor:
            return "needs_higher_anchor_after_failure"
        return None

    def after_entry(self, anchor: float) -> "TickerMemory":
        return replace(self, entries=self.entries + 1, last_anchor=anchor)

    def after_failure(self, anchor: float, now: datetime, params: TraderParams = DEFAULT_PARAMS) -> "TickerMemory":
        top = anchor if self.last_anchor is None else max(anchor, self.last_anchor)
        return replace(self, last_anchor=top, cooldown_until=now + timedelta(minutes=params.cooldown_minutes))


# ---- thesis-based position management ----------------------------------

@dataclass(frozen=True)
class ThesisPosition:
    """Open position with its live thesis record. `stop` only ever rises."""
    thesis_id: str
    ticker: str
    entry_price: float
    entry_at: datetime
    initial_stop: float
    stop: float
    shares_initial: int
    shares_open: int
    anchor: float
    atr: float
    cost_per_share: float
    highest_high: float
    closes_below_anchor: int = 0
    breakeven_locked: bool = False
    partial_taken: bool = False

    @property
    def risk_per_share(self) -> float:
        return self.entry_price - self.initial_stop

    def mfe_r(self) -> float:
        return (self.highest_high - self.entry_price) / self.risk_per_share


@dataclass(frozen=True)
class ManageOutcome:
    position: ThesisPosition
    exit_reason: str | None = None
    new_stop: float | None = None
    partial_quantity: int = 0
    partial_price: float | None = None


def open_thesis_position(plan: EntryPlan, *, ticker: str, anchor: float, atr: float,
                         entry_at: datetime) -> ThesisPosition:
    return ThesisPosition(
        thesis_id=plan.thesis_id, ticker=ticker, entry_price=plan.entry_price, entry_at=_aware(entry_at, "entry_at"),
        initial_stop=plan.stop, stop=plan.stop, shares_initial=plan.shares, shares_open=plan.shares,
        anchor=anchor, atr=atr, cost_per_share=plan.round_trip_cost / plan.shares if plan.shares else 0.0,
        highest_high=plan.entry_price,
    )


def resting_partial(position: ThesisPosition, bar: CompletedBar, params: TraderParams = DEFAULT_PARAMS) -> ManageOutcome:
    """A resting half-size limit at +partial_r fills when a bar trades through it.

    Only an integer half of an open quantity of two or more can be banked; a
    one-share position keeps its single unit and its trail.
    """
    level = round(position.entry_price + params.partial_r * position.risk_per_share, 6)
    if position.partial_taken or position.shares_open < 2 or bar.high < level:
        return ManageOutcome(position)
    quantity = position.shares_open // 2
    updated = replace(position, shares_open=position.shares_open - quantity, partial_taken=True)
    return ManageOutcome(updated, partial_quantity=quantity, partial_price=level)


def manage_position(position: ThesisPosition, bar: CompletedBar, *, decision_at: datetime,
                    params: TraderParams = DEFAULT_PARAMS) -> ManageOutcome:
    """Decide on one completed bar after the fill. Exits beat stop raises.

    The protective stop itself is enforced by the executor/monitor using
    ``position.stop``; this function only raises it, never lowers it.
    """
    decision = _aware(decision_at, "decision_at")
    if decision < bar.available_at:
        raise ValueError("decision_at precedes completed-bar availability")
    risk = position.risk_per_share
    highest = max(position.highest_high, bar.high)
    below = position.closes_below_anchor + 1 if bar.close < position.anchor else 0
    updated = replace(position, highest_high=highest, closes_below_anchor=below)
    if below >= params.failed_breakout_closes:
        return ManageOutcome(updated, exit_reason="THESIS_FAILED_BREAKOUT")
    held = (decision - position.entry_at).total_seconds() / 60.0
    if held >= params.stall_minutes and updated.mfe_r() < params.stall_max_mfe_r and bar.close < position.entry_price:
        return ManageOutcome(updated, exit_reason="THESIS_STALLED")
    minute = decision.hour * 60 + decision.minute
    if minute >= params.eod_loss_cut_minute and bar.close < position.entry_price:
        return ManageOutcome(updated, exit_reason="THESIS_EOD_LOSS_CUT")
    stop = position.stop
    if not updated.breakeven_locked and highest >= position.entry_price + params.breakeven_r * risk:
        stop = max(stop, _ceil_tick(position.entry_price + position.cost_per_share, params.tick))
        updated = replace(updated, breakeven_locked=True)
    if updated.mfe_r() >= params.trail_start_r:
        distance = max(params.trail_atr_mult * position.atr, params.trail_min_r * risk)
        stop = max(stop, _floor_tick(highest - distance, params.tick))
    if stop > position.stop:
        return ManageOutcome(replace(updated, stop=stop), new_stop=stop)
    return ManageOutcome(updated)
