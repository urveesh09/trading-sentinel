"""Offline-safe evidence ledger for proactive strategy research.

This module is deliberately policy-agnostic: it records what a scanner or
allocator did without creating an order, and keeps shadow/replay evidence out
of the live cash books.
"""
from __future__ import annotations

import json
import hashlib
import math
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Optional

import aiosqlite

Mode = Literal["LIVE", "PAPER", "SHADOW", "REPLAY"]
_MODES = frozenset({"LIVE", "PAPER", "SHADOW", "REPLAY"})
_STAGES = frozenset({
    "UNIVERSE", "DATA_READY", "SETUP", "COST_VIABLE", "RISK_APPROVED",
    "SELECTED", "SUBMITTED", "FILLED", "MANAGED", "CLOSED", "DEFERRED",
    "REJECTED", "EXPIRED", "UNAVAILABLE",
})
_WATCH_TRANSITIONS = {
    "WATCHING": {"ARMED", "INVALIDATED", "EXPIRED"},
    "ARMED": {"TRIGGERED", "SELECTED", "INVALIDATED", "EXPIRED"},
    "TRIGGERED": {"SELECTED", "DEFERRED", "REJECTED", "EXPIRED"},
    "DEFERRED": {"TRIGGERED", "INVALIDATED", "EXPIRED"},
    "SELECTED": {"COMPLETED", "INVALIDATED", "EXPIRED"},
}


@dataclass(frozen=True)
class ShadowProposal:
    """Completed-bar-only research proposal; never an order instruction."""
    opportunity_id: str
    policy_id: str
    instrument: str
    entry: float
    stop: float
    target: float
    valid_until: datetime
    score: float
    required_capital: float
    reason: str
    signal_at: Optional[datetime] = None
    data_cutoff: Optional[datetime] = None
    entry_deadline: Optional[datetime] = None
    holding_deadline: Optional[datetime] = None


@dataclass(frozen=True)
class ShadowSimulation:
    status: str
    quantity: int
    entry_price: Optional[float]
    exit_price: Optional[float]
    gross_pnl: Optional[float]
    fees: Optional[float]
    net_pnl: Optional[float]
    reason: str
    entry_at: Optional[datetime] = None
    last_bar_at: Optional[datetime] = None


@dataclass(frozen=True)
class ShadowAllocation:
    opportunity_id: str
    quantity: int
    executable_price: float
    fee_reserve: float
    reserved_capital: float
    initial_risk: float


@dataclass(frozen=True)
class ShadowPosition:
    """Durable, synthetic-only position state; it is never a broker position."""
    opportunity_id: str
    account_id: str
    policy_id: str
    instrument: str
    quantity: int
    entry_price: float
    entry_fees: float
    stop_price: float
    target_price: float
    opened_at: datetime
    holding_deadline: datetime
    last_bar_at: datetime


def _proposal_id(policy_id: str, instrument: str, bar_time: datetime) -> str:
    return hashlib.sha256(f"{policy_id}:{instrument}:{_stamp(bar_time).isoformat()}".encode()).hexdigest()[:20]


def shadow_history_state(bars: object, *, now: datetime) -> str:
    """Classify input before a scanner can call missing/bad data a success."""
    now = _stamp(now)
    if not isinstance(bars, list):
        return "INVALID_HISTORY"
    if len(bars) < 21:
        return "INSUFFICIENT_HISTORY"
    try:
        stamps = [_stamp(datetime.fromisoformat(str(bar["timestamp"]))) for bar in bars]
        opens = [float(bar["open"]) for bar in bars]
        closes = [float(bar["close"]) for bar in bars]
        highs = [float(bar["high"]) for bar in bars]
        lows = [float(bar["low"]) for bar in bars]
        volumes = [float(bar["volume"]) for bar in bars]
    except (KeyError, TypeError, ValueError):
        return "INVALID_HISTORY"
    if (any(right <= left for left, right in zip(stamps, stamps[1:])) or any(stamp > now for stamp in stamps)
            or not all(math.isfinite(value) and value > 0 for value in opens + closes + highs + lows)
            or not all(math.isfinite(value) and value >= 0 for value in volumes)
            or any(low > min(open_, close) or high < max(open_, close)
                   for open_, high, low, close in zip(opens, highs, lows, closes))):
        return "INVALID_HISTORY"
    return "STALE_HISTORY" if stamps[-1] + timedelta(minutes=30) <= now else "READY"


def build_shadow_proposals(instrument: str, bars: list[dict], *, now: datetime) -> list[ShadowProposal]:
    """Three reproducible completed-bar hypotheses with no look-ahead.

    Bars contain timestamp/open/high/low/close/volume. The last bar is the
    observed completed trigger; every reference excludes it where required.
    """
    now = _stamp(now)
    if shadow_history_state(bars, now=now) != "READY":
        return []
    try:
        stamps = [_stamp(datetime.fromisoformat(str(bar["timestamp"]))) for bar in bars]
        opens = [float(bar["open"]) for bar in bars]
        closes = [float(bar["close"]) for bar in bars]
        highs = [float(bar["high"]) for bar in bars]
        lows = [float(bar["low"]) for bar in bars]
        volumes = [float(bar["volume"]) for bar in bars]
        trigger_at = stamps[-1]
    except (KeyError, TypeError, ValueError):
        return []
    last, prior = closes[-1], closes[-2]
    fast, slow = sum(closes[-5:]) / 5, sum(closes[-20:]) / 20
    proposals: list[ShadowProposal] = []
    expiry = trigger_at + timedelta(minutes=30)
    # Trend: uptrend, pullback toward fast MA, then confirmed completed-bar reclaim.
    if fast > slow and closes[-3] <= fast * 1.01 and last > prior:
        stop = min(lows[-3:])
        if 0 < stop < last:
            proposals.append(ShadowProposal(_proposal_id("trend_pullback_v1", instrument, trigger_at), "trend_pullback_v1", instrument, last, stop, last + 2 * (last-stop), expiry, fast/slow, last, "TREND_PULLBACK_RECLAIM", trigger_at, trigger_at, expiry, expiry + timedelta(hours=4)))
    # Range: low directional drift, downside stretch, then stabilization/reclaim.
    window = closes[-15:-1]
    mean = sum(window) / len(window)
    if max(window)-min(window) <= mean * .06 and closes[-2] < mean * .985 and last > closes[-2]:
        stop = min(lows[-2:])
        if 0 < stop < last:
            if mean > last:
                proposals.append(ShadowProposal(_proposal_id("range_reversion_v1", instrument, trigger_at), "range_reversion_v1", instrument, last, stop, mean, expiry, (mean-last)/mean, last, "RANGE_STABILIZATION_RECLAIM", trigger_at, trigger_at, expiry, expiry + timedelta(hours=4)))
    # Breakout: previous range contracts vs older range; trigger breaks prior range on volume.
    recent_width = max(highs[-6:-1]) - min(lows[-6:-1])
    old_width = max(highs[-16:-6]) - min(lows[-16:-6])
    prior_high = max(highs[-6:-1])
    if old_width > 0 and recent_width < old_width * .7 and last > prior_high and volumes[-1] > sum(volumes[-11:-1])/10:
        stop = min(lows[-6:-1])
        if 0 < stop < last:
            proposals.append(ShadowProposal(_proposal_id("contraction_breakout_v1", instrument, trigger_at), "contraction_breakout_v1", instrument, last, stop, last + 2 * (last-stop), expiry, volumes[-1]/(sum(volumes[-11:-1])/10), last, "CONTRACTION_BREAKOUT", trigger_at, trigger_at, expiry, expiry + timedelta(hours=4)))
    return proposals


def allocate_shadow_proposals(proposals: list[ShadowProposal], *, capital: float, reserved: float = 0.0) -> tuple[list[ShadowProposal], dict[str, str]]:
    """Choose feasible, non-duplicated proposals; cash is a valid outcome."""
    free = max(0.0, float(capital) - float(reserved))
    selected: list[ShadowProposal] = []
    reasons: dict[str, str] = {}
    seen = set()
    for proposal in sorted(proposals, key=lambda item: item.score, reverse=True):
        if proposal.instrument in seen:
            reasons[proposal.opportunity_id] = "DUPLICATE_INSTRUMENT_EXPOSURE"
        elif proposal.required_capital > free:
            reasons[proposal.opportunity_id] = "INSUFFICIENT_SHADOW_CASH_AFTER_COST_RESERVE"
        else:
            selected.append(proposal); seen.add(proposal.instrument); free -= proposal.required_capital
            reasons[proposal.opportunity_id] = "SELECTED"
    return selected, reasons


def size_shadow_allocations(
    proposals: list[ShadowProposal], *, capital: float, reserved: float = 0.0,
    fee_rate: float = .001, slippage_bps: float = 5,
) -> tuple[list[ShadowAllocation], dict[str, str]]:
    """Create the one cash reservation that both selection and simulation use."""
    if capital < 0 or reserved < 0 or fee_rate < 0 or slippage_bps < 0:
        raise ValueError("invalid allocation assumptions")
    free = max(0.0, float(capital) - float(reserved))
    allocations: list[ShadowAllocation] = []
    reasons: dict[str, str] = {}
    instruments: set[str] = set()
    for proposal in sorted(proposals, key=lambda item: (item.score, item.policy_id), reverse=True):
        if proposal.instrument in instruments:
            reasons[proposal.opportunity_id] = "DUPLICATE_INSTRUMENT_EXPOSURE"; continue
        price = proposal.entry * (1 + slippage_bps / 10_000)
        quantity = math.floor(free / (price * (1 + fee_rate)))
        if quantity < 1:
            reasons[proposal.opportunity_id] = "INSUFFICIENT_SHADOW_CASH_AFTER_COST_RESERVE"; continue
        fees = price * quantity * fee_rate
        reserve = price * quantity + fees
        allocations.append(ShadowAllocation(proposal.opportunity_id, quantity, round(price, 4), round(fees, 4), round(reserve, 4), round((price-proposal.stop)*quantity, 4)))
        free -= reserve; instruments.add(proposal.instrument); reasons[proposal.opportunity_id] = "SELECTED"
    return allocations, reasons


def simulate_shadow_trade(
    proposal: ShadowProposal, future_bars: list[dict], *, cash: float,
    fee_rate: float = .001, slippage_bps: float = 5, max_quantity: Optional[int] = None,
    allocation: Optional[ShadowAllocation] = None,
) -> ShadowSimulation:
    """Conservative long-only completed-bar simulator for research evidence.

    Entry is at the first subsequent bar open plus slippage. If stop and target
    occur in one bar, stop wins: OHLC cannot establish the intrabar order.
    """
    if cash <= 0 or fee_rate < 0 or slippage_bps < 0:
        raise ValueError("invalid simulation assumptions")
    slip = slippage_bps / 10_000
    if max_quantity is not None and (not isinstance(max_quantity, int) or max_quantity < 0):
        raise ValueError("max_quantity must be a non-negative integer")
    cutoff = _stamp(proposal.data_cutoff or proposal.signal_at or proposal.valid_until)
    entry_deadline = _stamp(proposal.entry_deadline or proposal.valid_until)
    holding_deadline = _stamp(proposal.holding_deadline or proposal.valid_until)
    if not (proposal.stop > 0 and proposal.entry > proposal.stop and proposal.target > proposal.entry and entry_deadline >= cutoff and holding_deadline >= entry_deadline):
        return ShadowSimulation("INVALID", 0, None, None, None, None, None, "INVALID_PROPOSAL_GEOMETRY_OR_TIMING")
    normalised = _normalise_shadow_bars(future_bars)
    if normalised is None:
        return ShadowSimulation("INVALID", 0, None, None, None, None, None, "INVALID_OR_UNORDERED_FUTURE_BARS")
    quantity = 0; entry = None; entry_at = None; last_bar_at = None
    for stamp, open_, high, low, _close in normalised:
        if entry is None:
            if stamp <= cutoff or stamp > entry_deadline:
                continue
            entry = open_ * (1 + slip)
            entry_at = stamp
            quantity = (allocation.quantity if allocation is not None else min(max_quantity if max_quantity is not None else math.inf, math.floor(cash / (entry * (1 + fee_rate)))))
            if quantity < 1:
                return ShadowSimulation("NO_FILL", 0, None, None, None, None, None, "INSUFFICIENT_CASH_AFTER_FEES")
            if allocation is not None and (allocation.opportunity_id != proposal.opportunity_id or entry * quantity * (1 + fee_rate) > allocation.reserved_capital + .01):
                return ShadowSimulation("NO_FILL", 0, None, None, None, None, None, "ALLOCATION_NO_LONGER_FEASIBLE")
            if entry <= proposal.stop or entry >= proposal.target:
                return ShadowSimulation("NO_FILL", 0, None, None, None, None, None, "GAP_INVALIDATES_ENTRY_GEOMETRY")
        last_bar_at = stamp
        if stamp > holding_deadline:
            exit_price = open_ * (1-slip); reason = "HOLDING_DEADLINE"
        elif low <= proposal.stop and high >= proposal.target:
            exit_price = min(open_, proposal.stop) * (1 - slip); reason = "AMBIGUOUS_BAR_STOP_FIRST"
        elif low <= proposal.stop:
            exit_price = min(open_, proposal.stop) * (1 - slip); reason = "STOP"
        elif high >= proposal.target:
            exit_price = proposal.target * (1 - slip); reason = "TARGET"
        else:
            continue
        gross = (exit_price - entry) * quantity
        fees = (entry + exit_price) * quantity * fee_rate
        return ShadowSimulation("CLOSED", quantity, round(entry, 4), round(exit_price, 4), round(gross, 4), round(fees, 4), round(gross-fees, 4), reason, entry_at, stamp)
    if entry is None:
        return ShadowSimulation("NO_FILL", 0, None, None, None, None, None, "NO_EXECUTABLE_BAR_AFTER_SIGNAL")
    return ShadowSimulation("OPEN", quantity, round(entry, 4), None, None, None, None, "DATA_END_OPEN_POSITION", entry_at, last_bar_at)


def _normalise_shadow_bars(bars: object) -> Optional[list[tuple[datetime, float, float, float, float]]]:
    """Validate a complete OHLC series and give the simulator one time order."""
    if not isinstance(bars, list):
        return None
    normalised = []
    try:
        for bar in bars:
            if not isinstance(bar, dict):
                return None
            stamp = _stamp(datetime.fromisoformat(str(bar["timestamp"])))
            open_, high, low, close = (float(bar[key]) for key in ("open", "high", "low", "close"))
            if (not all(math.isfinite(value) and value > 0 for value in (open_, high, low, close))
                    or low > min(open_, close) or high < max(open_, close)):
                return None
            normalised.append((stamp, open_, high, low, close))
    except (KeyError, TypeError, ValueError):
        return None
    normalised.sort(key=lambda item: item[0])
    if any(right[0] <= left[0] for left, right in zip(normalised, normalised[1:])):
        return None
    return normalised


def _bars_visible_as_of(bars: object, *, as_of: datetime) -> object:
    """Treat every fixture timestamp as a completed-bar timestamp.

    Rows completed after ``as_of`` are deliberately withheld.  Invalid visible
    rows are retained so the normal simulator/input validator reports them;
    invalid future rows cannot contaminate an earlier clock step.
    """
    if not isinstance(bars, list):
        return bars
    visible = []
    for bar in bars:
        try:
            stamp = _stamp(datetime.fromisoformat(str(bar["timestamp"])))
        except (KeyError, TypeError, ValueError):
            visible.append(bar)
            continue
        if stamp <= as_of:
            visible.append(bar)
    return visible


def simulate_open_shadow_position(
    position: ShadowPosition, future_bars: list[dict], *, fee_rate: float = .001,
    slippage_bps: float = 5,
) -> ShadowSimulation:
    """Advance one existing synthetic position using only bars not seen before."""
    if fee_rate < 0 or slippage_bps < 0:
        raise ValueError("invalid simulation assumptions")
    normalised = _normalise_shadow_bars(future_bars)
    if normalised is None:
        return ShadowSimulation("INVALID", position.quantity, position.entry_price, None, None, None, None, "INVALID_OR_UNORDERED_FUTURE_BARS", position.opened_at, position.last_bar_at)
    slip = slippage_bps / 10_000
    last_bar_at = position.last_bar_at
    for stamp, open_, high, low, _close in normalised:
        if stamp <= position.last_bar_at:
            continue
        last_bar_at = stamp
        if stamp > position.holding_deadline:
            exit_price = open_ * (1 - slip); reason = "HOLDING_DEADLINE"
        elif low <= position.stop_price and high >= position.target_price:
            exit_price = min(open_, position.stop_price) * (1 - slip); reason = "AMBIGUOUS_BAR_STOP_FIRST"
        elif low <= position.stop_price:
            exit_price = min(open_, position.stop_price) * (1 - slip); reason = "STOP"
        elif high >= position.target_price:
            exit_price = position.target_price * (1 - slip); reason = "TARGET"
        else:
            continue
        gross = (exit_price - position.entry_price) * position.quantity
        fees = position.entry_fees + exit_price * position.quantity * fee_rate
        return ShadowSimulation("CLOSED", position.quantity, position.entry_price, round(exit_price, 4), round(gross, 4), round(fees, 4), round(gross-fees, 4), reason, position.opened_at, stamp)
    return ShadowSimulation("OPEN", position.quantity, position.entry_price, None, None, None, None, "DATA_END_OPEN_POSITION", position.opened_at, last_bar_at)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS proactive_opportunities (
 opportunity_id TEXT PRIMARY KEY, policy_id TEXT NOT NULL, policy_version TEXT NOT NULL,
 account_id TEXT NOT NULL, mode TEXT NOT NULL, instrument TEXT NOT NULL,
 observed_at TEXT NOT NULL, valid_until TEXT, current_state TEXT NOT NULL,
 current_reason TEXT, detail_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS proactive_events (
 event_id INTEGER PRIMARY KEY AUTOINCREMENT, opportunity_id TEXT NOT NULL,
 decision_id TEXT, mode TEXT NOT NULL, stage TEXT NOT NULL, reason_code TEXT NOT NULL,
 event_at TEXT NOT NULL, session_date TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE,
 detail_json TEXT NOT NULL, FOREIGN KEY(opportunity_id) REFERENCES proactive_opportunities(opportunity_id)
);
CREATE INDEX IF NOT EXISTS idx_proactive_events_session ON proactive_events(session_date, mode, stage);
CREATE TABLE IF NOT EXISTS proactive_cash_flows (
 flow_id TEXT PRIMARY KEY, mode TEXT NOT NULL, flow_type TEXT NOT NULL,
 amount REAL NOT NULL, occurred_at TEXT NOT NULL, note TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS proactive_scan_runs (
 scan_id TEXT PRIMARY KEY, policy_id TEXT NOT NULL, account_id TEXT NOT NULL,
 mode TEXT NOT NULL, status TEXT NOT NULL, observed_at TEXT NOT NULL,
 reason TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS proactive_watchlist (
 opportunity_id TEXT PRIMARY KEY, state TEXT NOT NULL, reason TEXT NOT NULL,
 updated_at TEXT NOT NULL, valid_until TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS proactive_shadow_positions (
 opportunity_id TEXT PRIMARY KEY, account_id TEXT NOT NULL, policy_id TEXT NOT NULL,
 instrument TEXT NOT NULL, status TEXT NOT NULL, quantity INTEGER NOT NULL,
 entry_price REAL NOT NULL, entry_fees REAL NOT NULL, stop_price REAL NOT NULL,
 target_price REAL NOT NULL, opened_at TEXT NOT NULL, holding_deadline TEXT NOT NULL,
 last_bar_at TEXT NOT NULL, exit_price REAL, exit_fees REAL, gross_pnl REAL,
 net_pnl REAL, closed_at TEXT, close_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_shadow_positions_account_status
 ON proactive_shadow_positions(account_id, status);
CREATE TABLE IF NOT EXISTS proactive_shadow_runs (
 run_key TEXT PRIMARY KEY, account_id TEXT NOT NULL, run_id TEXT NOT NULL,
 manifest_json TEXT NOT NULL, created_at TEXT NOT NULL,
 last_as_of TEXT, last_sequence INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS proactive_shadow_run_steps (
 run_key TEXT NOT NULL, as_of TEXT NOT NULL, input_digest TEXT NOT NULL,
 origin TEXT NOT NULL, status TEXT NOT NULL, result_json TEXT,
 claimed_at TEXT NOT NULL, completed_at TEXT,
 PRIMARY KEY (run_key, as_of),
 FOREIGN KEY(run_key) REFERENCES proactive_shadow_runs(run_key)
);
"""


def _stamp(value: Optional[datetime] = None) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


async def init_proactive_intelligence(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(_SCHEMA)
        columns = {row[1] for row in await (await db.execute("PRAGMA table_info(proactive_shadow_runs)")).fetchall()}
        if "last_as_of" not in columns:
            await db.execute("ALTER TABLE proactive_shadow_runs ADD COLUMN last_as_of TEXT")
        if "last_sequence" not in columns:
            await db.execute("ALTER TABLE proactive_shadow_runs ADD COLUMN last_sequence INTEGER NOT NULL DEFAULT 0")
        await db.commit()


def _shadow_run_storage_key(account_id: str, run_id: str) -> str:
    """Keep legacy/default Dev records readable while isolating named scenarios."""
    if not account_id or not run_id:
        raise ValueError("shadow account and run identity are required")
    if run_id == "default-v1":
        return account_id
    digest = hashlib.sha256(f"{account_id}\x00{run_id}".encode()).hexdigest()[:24]
    return f"shadow-run:{digest}"


async def _ensure_shadow_run(
    db_path: str, *, account_id: str, run_id: str, scenario_capital: float,
    fee_rate: float, slippage_bps: float,
) -> str:
    """Bind one named research run to immutable economic assumptions."""
    if not all(isinstance(value, str) and value for value in (account_id, run_id)):
        raise ValueError("shadow account and run identity are required")
    manifest = {
        "version": "shadow-run-v1", "scenario_capital": float(scenario_capital),
        "fee_rate": float(fee_rate), "slippage_bps": float(slippage_bps),
        "policy_manifest": "three-sleeves-v1",
    }
    if (not math.isfinite(float(scenario_capital)) or float(scenario_capital) <= 0
            or not math.isfinite(float(fee_rate)) or float(fee_rate) < 0
            or not math.isfinite(float(slippage_bps)) or float(slippage_bps) < 0):
        raise ValueError("shadow run assumptions must be finite")
    key = _shadow_run_storage_key(account_id, run_id)
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    await init_proactive_intelligence(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("BEGIN IMMEDIATE")
        row = await (await db.execute(
            "SELECT manifest_json FROM proactive_shadow_runs WHERE run_key=?", (key,),
        )).fetchone()
        if row is not None:
            if row[0] != payload:
                await db.rollback()
                raise ValueError("shadow run manifest conflicts with existing evidence; create a new run_id")
            await db.commit()
            return key
        await db.execute(
            "INSERT INTO proactive_shadow_runs (run_key,account_id,run_id,manifest_json,created_at) VALUES (?,?,?,?,?)",
            (key, account_id, run_id, payload, datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()
    return key


async def _shadow_run_manifest(db_path: str, *, run_key: str) -> dict:
    await init_proactive_intelligence(db_path)
    async with aiosqlite.connect(db_path) as db:
        row = await (await db.execute(
            "SELECT manifest_json FROM proactive_shadow_runs WHERE run_key=?", (run_key,),
        )).fetchone()
    if row is None:
        raise ValueError("unknown shadow run")
    try:
        manifest = json.loads(row[0])
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("stored shadow run manifest is invalid") from exc
    if not isinstance(manifest, dict):
        raise ValueError("stored shadow run manifest is invalid")
    return manifest


async def _claim_shadow_step(
    db_path: str, *, run_key: str, as_of: datetime, input_digest: str, origin: str,
) -> Optional[dict]:
    """Claim one immutable evaluation step, or return an exact completed retry."""
    if origin not in {"SHADOW", "REPLAY"}:
        raise ValueError("unsupported shadow execution origin")
    await init_proactive_intelligence(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("BEGIN IMMEDIATE")
        run = await (await db.execute(
            "SELECT last_as_of FROM proactive_shadow_runs WHERE run_key=?", (run_key,),
        )).fetchone()
        if run is None:
            await db.rollback(); raise ValueError("unknown shadow run")
        last_as_of = _stamp(datetime.fromisoformat(run[0])) if run[0] else None
        if last_as_of is not None and as_of < last_as_of:
            await db.rollback(); raise ValueError("shadow run clock cannot move backwards")
        row = await (await db.execute(
            "SELECT input_digest,status,result_json FROM proactive_shadow_run_steps WHERE run_key=? AND as_of=?",
            (run_key, as_of.isoformat()),
        )).fetchone()
        if row is not None:
            if row[0] != input_digest:
                await db.rollback(); raise ValueError("shadow run step input conflicts with established clock")
            if row[1] == "COMPLETED" and row[2]:
                await db.rollback(); return json.loads(row[2])
            await db.rollback(); raise RuntimeError("shadow run step is already in progress")
        await db.execute(
            "INSERT INTO proactive_shadow_run_steps (run_key,as_of,input_digest,origin,status,claimed_at) VALUES (?,?,?,?,?,?)",
            (run_key, as_of.isoformat(), input_digest, origin, "RUNNING", datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()
    return None


async def _complete_shadow_step(db_path: str, *, run_key: str, as_of: datetime, input_digest: str, result: dict) -> None:
    """Commit the immutable retry result and monotonically advance run clock."""
    payload = json.dumps(result, sort_keys=True, separators=(",", ":"), default=str)
    await init_proactive_intelligence(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("BEGIN IMMEDIATE")
        cur = await db.execute(
            "UPDATE proactive_shadow_run_steps SET status='COMPLETED',result_json=?,completed_at=? "
            "WHERE run_key=? AND as_of=? AND input_digest=? AND status='RUNNING'",
            (payload, datetime.now(timezone.utc).isoformat(), run_key, as_of.isoformat(), input_digest),
        )
        if cur.rowcount != 1:
            await db.rollback(); raise RuntimeError("shadow run step ownership was lost")
        await db.execute(
            "UPDATE proactive_shadow_runs SET last_as_of=?,last_sequence=last_sequence+1 "
            "WHERE run_key=? AND (last_as_of IS NULL OR last_as_of<=?)",
            (as_of.isoformat(), run_key, as_of.isoformat()),
        )
        await db.commit()


async def record_opportunity_event(
    db_path: str, *, opportunity_id: str, policy_id: str, policy_version: str,
    account_id: str, mode: Mode, instrument: str, stage: str, reason_code: str,
    idempotency_key: str, observed_at: datetime, valid_until: Optional[datetime] = None,
    decision_id: Optional[str] = None, detail: Optional[dict] = None,
) -> bool:
    """Append one idempotent, non-executing strategy stage event."""
    if mode not in _MODES or stage not in _STAGES:
        raise ValueError("unsupported mode or stage")
    if not all(isinstance(v, str) and v for v in (opportunity_id, policy_id, policy_version, account_id, instrument, reason_code, idempotency_key)):
        raise ValueError("opportunity identity fields are required")
    observed = _stamp(observed_at)
    expiry = _stamp(valid_until) if valid_until else None
    if expiry and expiry <= observed:
        raise ValueError("valid_until must be after observed_at")
    payload = detail or {}
    await init_proactive_intelligence(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("BEGIN IMMEDIATE")
        await db.execute(
            "INSERT OR IGNORE INTO proactive_opportunities "
            "(opportunity_id,policy_id,policy_version,account_id,mode,instrument,observed_at,valid_until,current_state,current_reason,detail_json) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (opportunity_id, policy_id, policy_version, account_id, mode, instrument,
             observed.isoformat(), expiry.isoformat() if expiry else None, stage, reason_code,
             json.dumps(payload, sort_keys=True)),
        )
        cur = await db.execute(
            "INSERT OR IGNORE INTO proactive_events "
            "(opportunity_id,decision_id,mode,stage,reason_code,event_at,session_date,idempotency_key,detail_json) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (opportunity_id, decision_id, mode, stage, reason_code, observed.isoformat(),
             observed.date().isoformat(), idempotency_key, json.dumps(payload, sort_keys=True)),
        )
        if cur.rowcount:
            await db.execute(
                "UPDATE proactive_opportunities SET current_state=?, current_reason=?, detail_json=? WHERE opportunity_id=?",
                (stage, reason_code, json.dumps(payload, sort_keys=True), opportunity_id),
            )
        await db.commit()
        return bool(cur.rowcount)


async def transition_watchlist(
    db_path: str, *, opportunity_id: str, state: str, reason: str, now: datetime,
    valid_until: Optional[datetime] = None,
) -> bool:
    """Persist an allowed watchlist transition; repeated scans cannot reset it."""
    now = _stamp(now)
    await init_proactive_intelligence(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("BEGIN IMMEDIATE")
        row = await (await db.execute("SELECT state, valid_until FROM proactive_watchlist WHERE opportunity_id=?", (opportunity_id,))).fetchone()
        if row is None:
            if state != "WATCHING" or valid_until is None or _stamp(valid_until) <= now:
                await db.rollback(); raise ValueError("new watchlist item requires future WATCHING expiry")
            await db.execute("INSERT INTO proactive_watchlist VALUES (?,?,?,?,?)", (opportunity_id, state, reason, now.isoformat(), _stamp(valid_until).isoformat()))
            await db.commit(); return True
        previous, expiry = row
        # Entry validity expires pending setups, not an already selected/fill
        # lifecycle. A selected synthetic position can complete after entry
        # expiry while its independent holding deadline is still active.
        if now >= _stamp(datetime.fromisoformat(expiry)) and state != "EXPIRED" and previous != "SELECTED":
            await db.rollback(); return False
        if state not in _WATCH_TRANSITIONS.get(previous, set()):
            await db.rollback(); return False
        await db.execute("UPDATE proactive_watchlist SET state=?, reason=?, updated_at=? WHERE opportunity_id=?", (state, reason, now.isoformat(), opportunity_id))
        await db.commit(); return True


async def record_cash_flow(
    db_path: str, *, flow_id: str, mode: Mode, flow_type: str, amount: float,
    occurred_at: datetime, note: str,
) -> bool:
    """Record funding separately from trading evidence, idempotently."""
    if mode not in _MODES or flow_type not in {"DEPOSIT", "WITHDRAWAL", "EXPENSE"}:
        raise ValueError("unsupported cash-flow mode or type")
    if not flow_id or not note or not math.isfinite(float(amount)) or float(amount) <= 0:
        raise ValueError("cash flow requires positive amount, identity and note")
    occurred = _stamp(occurred_at)
    await init_proactive_intelligence(db_path)
    signed = float(amount) if flow_type == "DEPOSIT" else -float(amount)
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "INSERT OR IGNORE INTO proactive_cash_flows (flow_id,mode,flow_type,amount,occurred_at,note) VALUES (?,?,?,?,?,?)",
            (flow_id, mode, flow_type, signed, occurred.isoformat(), note),
        )
        await db.commit()
        return bool(cur.rowcount)


async def record_scan_run(
    db_path: str, *, scan_id: str, policy_id: str, account_id: str, mode: Mode,
    status: str, observed_at: datetime, reason: str = "COMPLETED",
) -> bool:
    """Record scanner liveness separately from candidate lifecycle events."""
    if mode not in _MODES or status not in {"SUCCESS", "FAILED", "UNAVAILABLE"}:
        raise ValueError("unsupported scan mode or status")
    if not all(isinstance(value, str) and value for value in (scan_id, policy_id, account_id, reason)):
        raise ValueError("scan identity fields are required")
    at = _stamp(observed_at)
    await init_proactive_intelligence(db_path)
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "INSERT OR IGNORE INTO proactive_scan_runs VALUES (?,?,?,?,?,?,?)",
            (scan_id, policy_id, account_id, mode, status, at.isoformat(), reason),
        )
        await db.commit()
        return bool(cur.rowcount)


async def proactive_inactivity_diagnostics(db_path: str, *, now: datetime, max_scan_gap: timedelta = timedelta(minutes=30)) -> list[dict]:
    """Return evidence gaps; diagnostics never alter a strategy threshold."""
    now = _stamp(now)
    await init_proactive_intelligence(db_path)
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute(
            "SELECT s.mode, s.observed_at, s.status, s.reason "
            "FROM proactive_scan_runs s JOIN ("
            "SELECT mode, MAX(observed_at) AS observed_at FROM proactive_scan_runs GROUP BY mode"
            ") latest ON latest.mode=s.mode AND latest.observed_at=s.observed_at"
        )).fetchall()
        dropped = await (await db.execute(
            "SELECT r.mode, r.opportunity_id, MAX(r.event_at) FROM proactive_events r "
            "WHERE r.stage='RISK_APPROVED' AND NOT EXISTS (SELECT 1 FROM proactive_events t "
            "WHERE t.opportunity_id=r.opportunity_id AND t.event_at>=r.event_at "
            "AND t.stage IN ('SUBMITTED','FILLED','CLOSED','REJECTED','DEFERRED','EXPIRED')) "
            "GROUP BY r.mode, r.opportunity_id"
        )).fetchall()
    findings = []
    if not rows:
        findings.append({"mode": None, "code": "SCANNER_NEVER_CONFIGURED_OR_RAN", "last_event_at": None})
    for mode, last_at, status, reason in rows:
        last = _stamp(datetime.fromisoformat(last_at)) if last_at else None
        if status != "SUCCESS":
            findings.append({"mode": mode, "code": "SCANNER_SOURCE_UNAVAILABLE", "last_event_at": last_at, "reason": reason})
        if last is None or now - last > max_scan_gap * 2:
            findings.append({"mode": mode, "code": "MISSED_SCAN_INTERVALS", "last_event_at": last_at})
    for mode, opportunity_id, event_at in dropped:
        findings.append({"mode": mode, "code": "DROPPED_RISK_APPROVED_WORKFLOW", "opportunity_id": opportunity_id, "last_event_at": event_at})
    return findings


async def _shadow_positions(db_path: str, *, account_id: str, status: Optional[str] = None) -> list[ShadowPosition]:
    await init_proactive_intelligence(db_path)
    query = (
        "SELECT opportunity_id,account_id,policy_id,instrument,quantity,entry_price,entry_fees,"
        "stop_price,target_price,opened_at,holding_deadline,last_bar_at "
        "FROM proactive_shadow_positions WHERE account_id=?"
    )
    params: tuple = (account_id,)
    if status:
        query += " AND status=?"; params += (status,)
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute(query, params)).fetchall()
    return [ShadowPosition(
        opportunity_id=row[0], account_id=row[1], policy_id=row[2], instrument=row[3],
        quantity=int(row[4]), entry_price=float(row[5]), entry_fees=float(row[6]),
        stop_price=float(row[7]), target_price=float(row[8]),
        opened_at=_stamp(datetime.fromisoformat(row[9])),
        holding_deadline=_stamp(datetime.fromisoformat(row[10])),
        last_bar_at=_stamp(datetime.fromisoformat(row[11])),
    ) for row in rows]


async def _shadow_account_state(db_path: str, *, account_id: str, scenario_capital: float) -> tuple[float, set[str], set[str]]:
    """Return free synthetic cash plus open instrument/opportunity identities."""
    if not math.isfinite(scenario_capital) or scenario_capital <= 0:
        raise ValueError("scenario capital must be positive and finite")
    await init_proactive_intelligence(db_path)
    async with aiosqlite.connect(db_path) as db:
        open_rows = await (await db.execute(
            "SELECT opportunity_id,instrument,entry_price,entry_fees,quantity FROM proactive_shadow_positions "
            "WHERE account_id=? AND status='OPEN'", (account_id,),
        )).fetchall()
        closed_rows = await (await db.execute(
            "SELECT opportunity_id FROM proactive_shadow_positions WHERE account_id=? AND status='CLOSED'", (account_id,),
        )).fetchall()
        realised_row = await (await db.execute(
            "SELECT COALESCE(SUM(net_pnl),0) FROM proactive_shadow_positions "
            "WHERE account_id=? AND status='CLOSED'", (account_id,),
        )).fetchone()
    reserved = sum(float(row[2]) * int(row[4]) + float(row[3]) for row in open_rows)
    free_cash = max(0.0, float(scenario_capital) + float(realised_row[0]) - reserved)
    return free_cash, {row[1] for row in open_rows}, {row[0] for row in open_rows} | {row[0] for row in closed_rows}


async def _persist_new_shadow_position(
    db_path: str, *, proposal: ShadowProposal, account_id: str, result: ShadowSimulation,
    fee_rate: float = .001,
) -> bool:
    """Create an immutable synthetic fill/outcome exactly once per opportunity."""
    if result.status not in {"OPEN", "CLOSED"} or not result.entry_price or not result.entry_at:
        raise ValueError("only filled shadow simulations can create positions")
    entry_fees = round(result.entry_price * result.quantity * fee_rate, 4)
    exit_fees = round((result.fees or 0.0) - entry_fees, 4) if result.status == "CLOSED" else None
    await init_proactive_intelligence(db_path)
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "INSERT OR IGNORE INTO proactive_shadow_positions ("
            "opportunity_id,account_id,policy_id,instrument,status,quantity,entry_price,entry_fees,"
            "stop_price,target_price,opened_at,holding_deadline,last_bar_at,exit_price,exit_fees,gross_pnl,net_pnl,closed_at,close_reason"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (proposal.opportunity_id, account_id, proposal.policy_id, proposal.instrument, result.status,
             result.quantity, result.entry_price, entry_fees, proposal.stop, proposal.target,
             result.entry_at.isoformat(), _stamp(proposal.holding_deadline or proposal.valid_until).isoformat(),
             _stamp(result.last_bar_at or result.entry_at).isoformat(), result.exit_price, exit_fees,
             result.gross_pnl, result.net_pnl,
             _stamp(result.last_bar_at).isoformat() if result.status == "CLOSED" and result.last_bar_at else None,
             result.reason if result.status == "CLOSED" else None),
        )
        await db.commit()
        return bool(cur.rowcount)


async def _advance_open_shadow_positions(
    db_path: str, *, account_id: str, future_bars: dict[str, list[dict]],
    fee_rate: float = .001, slippage_bps: float = 5,
) -> list[tuple[ShadowPosition, ShadowSimulation]]:
    """Advance persisted synthetic positions before admitting any new exposure."""
    updates: list[tuple[ShadowPosition, ShadowSimulation]] = []
    for position in await _shadow_positions(db_path, account_id=account_id, status="OPEN"):
        result = simulate_open_shadow_position(
            position, future_bars.get(position.instrument, []),
            fee_rate=fee_rate, slippage_bps=slippage_bps,
        )
        if result.status == "INVALID":
            continue  # Preserve the existing position; malformed later data cannot close it.
        if result.status == "OPEN" and result.last_bar_at == position.last_bar_at:
            continue
        async with aiosqlite.connect(db_path) as db:
            if result.status == "CLOSED":
                exit_fees = round((result.fees or 0.0) - position.entry_fees, 4)
                await db.execute(
                    "UPDATE proactive_shadow_positions SET status='CLOSED',last_bar_at=?,exit_price=?,"
                    "exit_fees=?,gross_pnl=?,net_pnl=?,closed_at=?,close_reason=? "
                    "WHERE opportunity_id=? AND status='OPEN'",
                    (_stamp(result.last_bar_at).isoformat(), result.exit_price, exit_fees, result.gross_pnl,
                     result.net_pnl, _stamp(result.last_bar_at).isoformat(), result.reason, position.opportunity_id),
                )
            else:
                await db.execute(
                    "UPDATE proactive_shadow_positions SET last_bar_at=? WHERE opportunity_id=? AND status='OPEN'",
                    (_stamp(result.last_bar_at).isoformat(), position.opportunity_id),
                )
            await db.commit()
        updates.append((position, result))
    return updates


async def _expire_pending_shadow_watchlists(db_path: str, *, now: datetime) -> list[tuple[str, str, str, str, str]]:
    """Expire unfilled pending entries independently of current universe output."""
    await init_proactive_intelligence(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("BEGIN IMMEDIATE")
        rows = await (await db.execute(
            "SELECT w.opportunity_id,o.policy_id,o.policy_version,o.account_id,o.instrument "
            "FROM proactive_watchlist w JOIN proactive_opportunities o ON o.opportunity_id=w.opportunity_id "
            "LEFT JOIN proactive_shadow_positions p ON p.opportunity_id=w.opportunity_id "
            "WHERE w.state IN ('WATCHING','ARMED','SELECTED') AND w.valid_until<=? "
            "AND p.opportunity_id IS NULL",
            (now.isoformat(),),
        )).fetchall()
        for opportunity_id, *_rest in rows:
            await db.execute(
                "UPDATE proactive_watchlist SET state='EXPIRED',reason='ENTRY_DEADLINE',updated_at=? "
                "WHERE opportunity_id=? AND state IN ('WATCHING','ARMED','SELECTED')",
                (now.isoformat(), opportunity_id),
            )
        await db.commit()
    return [tuple(row) for row in rows]


async def repair_shadow_evidence(db_path: str, *, account_id: str) -> int:
    """Rebuild missing immutable lifecycle events from the economic ledger.

    Positions are authoritative for synthetic cash.  This idempotent repair
    makes an interruption after a position write observable without inventing
    a second fill or changing any economics.
    """
    await init_proactive_intelligence(db_path)
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute(
            "SELECT opportunity_id,policy_id,instrument,status,quantity,entry_price,entry_fees,"
            "opened_at,closed_at,close_reason,gross_pnl,net_pnl,exit_fees "
            "FROM proactive_shadow_positions WHERE account_id=?", (account_id,)
        )).fetchall()
    repaired = 0
    for row in rows:
        (opportunity_id, policy_id, instrument, status, quantity, entry_price, entry_fees,
         opened_at, closed_at, close_reason, gross_pnl, net_pnl, exit_fees) = row
        if await record_opportunity_event(
            db_path, opportunity_id=opportunity_id, policy_id=policy_id, policy_version="v1",
            account_id=account_id, mode="SHADOW", instrument=instrument, stage="FILLED",
            reason_code="RECOVERED_POSITION_LEDGER", idempotency_key=f"{opportunity_id}:filled",
            observed_at=_stamp(datetime.fromisoformat(opened_at)),
            detail={"quantity": quantity, "entry_price": entry_price, "fees": entry_fees},
        ):
            repaired += 1
        if status == "CLOSED" and closed_at and await record_opportunity_event(
            db_path, opportunity_id=opportunity_id, policy_id=policy_id, policy_version="v1",
            account_id=account_id, mode="SHADOW", instrument=instrument, stage="CLOSED",
            reason_code=close_reason or "RECOVERED_POSITION_LEDGER",
            idempotency_key=f"{opportunity_id}:closed", observed_at=_stamp(datetime.fromisoformat(closed_at)),
            detail={"quantity": quantity, "gross_pnl": gross_pnl, "fees": (entry_fees or 0) + (exit_fees or 0), "net_pnl": net_pnl},
        ):
            repaired += 1
    return repaired


async def run_shadow_workflow(
    db_path: str, *, account_id: str, universe: dict[str, list[dict]], now: datetime,
    scenario_capital: float = 8_000, future_bars: Optional[dict[str, list[dict]]] = None,
    run_id: str = "default-v1", fee_rate: float = .001, slippage_bps: float = 5,
    origin: str = "SHADOW",
) -> dict:
    """Run the bounded fixture-backed SHADOW path; never calls a broker.

    This is the application consumer for the proposal/allocator/simulator
    contracts. Callers provide completed bars and optional later bars so data
    provenance remains explicit and deterministic.
    """
    # ``now`` is the evaluation clock, not merely an event-label timestamp.
    # Fixture timestamps mean completed bars; nothing later is observable.
    now = _stamp(now); future_bars = future_bars or {}
    storage_account_id = await _ensure_shadow_run(
        db_path, account_id=account_id, run_id=run_id, scenario_capital=scenario_capital,
        fee_rate=fee_rate, slippage_bps=slippage_bps,
    )
    manifest = await _shadow_run_manifest(db_path, run_key=storage_account_id)
    persisted_fee_rate = float(manifest["fee_rate"])
    persisted_slippage_bps = float(manifest["slippage_bps"])
    visible_future_bars = {
        instrument: _bars_visible_as_of(bars, as_of=now)
        for instrument, bars in future_bars.items()
    }
    visible_universe = {
        instrument: _bars_visible_as_of(bars, as_of=now)
        for instrument, bars in universe.items()
    }
    step_input_digest = hashlib.sha256(json.dumps(
        {"universe": visible_universe, "future_bars": visible_future_bars},
        sort_keys=True, default=str, separators=(",", ":"),
    ).encode()).hexdigest()
    prior_result = await _claim_shadow_step(
        db_path, run_key=storage_account_id, as_of=now,
        input_digest=step_input_digest, origin=origin,
    )
    if prior_result is not None:
        return prior_result
    repaired_evidence = await repair_shadow_evidence(db_path, account_id=storage_account_id)
    expired_pending = await _expire_pending_shadow_watchlists(db_path, now=now)
    for opportunity_id, policy_id, policy_version, stored_account_id, instrument in expired_pending:
        await record_opportunity_event(
            db_path, opportunity_id=opportunity_id, policy_id=policy_id,
            policy_version=policy_version, account_id=stored_account_id,
            mode="SHADOW", instrument=instrument, stage="EXPIRED",
            reason_code="ENTRY_DEADLINE", idempotency_key=f"{opportunity_id}:expired",
            observed_at=now,
        )
    # Existing exposure is advanced first. A malformed update cannot erase a
    # position, and any realised result is then reflected in free scenario cash.
    managed = await _advance_open_shadow_positions(
        db_path, account_id=storage_account_id, future_bars=visible_future_bars,
        fee_rate=persisted_fee_rate, slippage_bps=persisted_slippage_bps,
    )
    for position, result in managed:
        if result.status == "CLOSED":
            try:
                await transition_watchlist(
                    db_path, opportunity_id=position.opportunity_id, state="COMPLETED",
                    reason=result.reason, now=result.last_bar_at or now,
                )
            except ValueError:
                # A pre-lifecycle synthetic record can be reconciled without
                # inventing a missing watchlist row.
                pass
            await record_opportunity_event(
                db_path, opportunity_id=position.opportunity_id, policy_id=position.policy_id,
                policy_version="v1", account_id=storage_account_id, mode="SHADOW", instrument=position.instrument,
                stage="CLOSED", reason_code=result.reason,
                idempotency_key=f"{position.opportunity_id}:closed",
                observed_at=result.last_bar_at or now,
                detail={"quantity": result.quantity, "gross_pnl": result.gross_pnl,
                        "fees": result.fees, "net_pnl": result.net_pnl},
            )
    proposals: list[ShadowProposal] = []
    for instrument, visible_bars in sorted(visible_universe.items()):
        # A rerun over identical completed data is one scan, not fresh evidence.
        # The full supplied-bar digest also changes when the source corrects a
        # historical bar even if its final timestamp stays the same.
        source_digest = hashlib.sha256(json.dumps(visible_bars, sort_keys=True, default=str).encode()).hexdigest()[:20]
        scan_id = hashlib.sha256(f"{storage_account_id}:{instrument}:{source_digest}".encode()).hexdigest()[:20]
        history_state = shadow_history_state(visible_bars, now=now)
        built = build_shadow_proposals(instrument, visible_bars, now=now)
        policies = {proposal.policy_id for proposal in built} or {"shadow_registry_v1"}
        for policy_id in policies:
            await record_scan_run(db_path, scan_id=f"{scan_id}:{policy_id}", policy_id=policy_id,
                                  account_id=storage_account_id, mode="SHADOW",
                                  status="SUCCESS" if history_state == "READY" else "UNAVAILABLE",
                                  observed_at=now,
                                  reason="COMPLETED_BARS" if built else (
                                      "NO_COMPLETED_SETUP" if history_state == "READY" else history_state
                                  ))
        if history_state != "READY":
            continue
        for proposal in built:
            proposal = replace(
                proposal,
                opportunity_id=hashlib.sha256(
                    f"{storage_account_id}:{proposal.opportunity_id}".encode()
                ).hexdigest()[:24],
            )
            await record_opportunity_event(db_path, opportunity_id=proposal.opportunity_id,
                policy_id=proposal.policy_id, policy_version="v1", account_id=storage_account_id,
                mode="SHADOW", instrument=proposal.instrument, stage="SETUP", reason_code=proposal.reason,
                idempotency_key=f"{proposal.opportunity_id}:setup", observed_at=proposal.signal_at or now,
                valid_until=proposal.entry_deadline, detail={"data_cutoff": (proposal.data_cutoff or now).isoformat()})
            try:
                await transition_watchlist(db_path, opportunity_id=proposal.opportunity_id, state="WATCHING",
                                           reason=proposal.reason, now=proposal.signal_at or now,
                                           valid_until=proposal.entry_deadline or proposal.valid_until)
                await transition_watchlist(db_path, opportunity_id=proposal.opportunity_id, state="ARMED",
                                           reason="COMPLETED_BAR", now=proposal.signal_at or now)
            except ValueError:
                pass  # An idempotent/restarted scan retains the original lifecycle.
            proposals.append(proposal)
    free_cash, open_instruments, recorded_opportunities = await _shadow_account_state(
        db_path, account_id=storage_account_id, scenario_capital=scenario_capital,
    )
    candidates: list[ShadowProposal] = []
    reasons: dict[str, str] = {}
    for proposal in proposals:
        if proposal.opportunity_id in recorded_opportunities:
            reasons[proposal.opportunity_id] = "RECORDED_SHADOW_OUTCOME"
        elif proposal.instrument in open_instruments:
            reasons[proposal.opportunity_id] = "OPEN_SHADOW_INSTRUMENT_EXPOSURE"
        else:
            candidates.append(proposal)
    allocations, allocation_reasons = size_shadow_allocations(
        candidates, capital=free_cash, fee_rate=persisted_fee_rate, slippage_bps=persisted_slippage_bps,
    )
    reasons.update(allocation_reasons)
    allocated = {item.opportunity_id: item for item in allocations}
    outcomes = []
    for proposal in proposals:
        allocation = allocated.get(proposal.opportunity_id)
        if allocation is None:
            if reasons[proposal.opportunity_id] in {"RECORDED_SHADOW_OUTCOME", "OPEN_SHADOW_INSTRUMENT_EXPOSURE"}:
                continue
            await record_opportunity_event(db_path, opportunity_id=proposal.opportunity_id, policy_id=proposal.policy_id,
                policy_version="v1", account_id=storage_account_id, mode="SHADOW", instrument=proposal.instrument,
                stage="DEFERRED", reason_code=reasons[proposal.opportunity_id], idempotency_key=f"{proposal.opportunity_id}:deferred",
                observed_at=now)
            continue
        if now >= _stamp(proposal.entry_deadline or proposal.valid_until):
            await transition_watchlist(
                db_path, opportunity_id=proposal.opportunity_id, state="EXPIRED",
                reason="ENTRY_DEADLINE", now=now,
            )
            await record_opportunity_event(db_path, opportunity_id=proposal.opportunity_id, policy_id=proposal.policy_id,
                policy_version="v1", account_id=storage_account_id, mode="SHADOW", instrument=proposal.instrument,
                stage="EXPIRED", reason_code="ENTRY_DEADLINE", idempotency_key=f"{proposal.opportunity_id}:expired",
                observed_at=now)
            reasons[proposal.opportunity_id] = "ENTRY_DEADLINE"
            continue
        await transition_watchlist(
            db_path, opportunity_id=proposal.opportunity_id, state="SELECTED",
            reason="SHARED_CASH_RESERVED", now=now,
        )
        await record_opportunity_event(db_path, opportunity_id=proposal.opportunity_id, policy_id=proposal.policy_id,
            policy_version="v1", account_id=storage_account_id, mode="SHADOW", instrument=proposal.instrument,
            stage="SELECTED", reason_code="SHARED_CASH_RESERVED", idempotency_key=f"{proposal.opportunity_id}:selected", observed_at=now)
        result = simulate_shadow_trade(proposal, visible_future_bars.get(proposal.instrument, []), cash=free_cash, fee_rate=persisted_fee_rate, slippage_bps=persisted_slippage_bps, allocation=allocation)
        if result.status == "CLOSED":
            stage = "CLOSED"
        elif result.status == "OPEN":
            stage = "FILLED"
        elif result.reason == "NO_EXECUTABLE_BAR_AFTER_SIGNAL" and now < _stamp(proposal.entry_deadline or proposal.valid_until):
            stage = "UNAVAILABLE"
        elif result.reason in {"GAP_INVALIDATES_ENTRY_GEOMETRY", "INVALID_PROPOSAL_GEOMETRY_OR_TIMING", "INVALID_OR_UNORDERED_FUTURE_BARS"}:
            stage = "REJECTED"
        else:
            stage = "EXPIRED"
        if result.status in {"OPEN", "CLOSED"}:
            await _persist_new_shadow_position(
                db_path, proposal=proposal, account_id=storage_account_id, result=result,
                fee_rate=persisted_fee_rate,
            )
            await transition_watchlist(
                db_path, opportunity_id=proposal.opportunity_id, state="COMPLETED",
                reason=result.reason, now=result.last_bar_at or now,
            )
        elif stage == "EXPIRED":
            await transition_watchlist(
                db_path, opportunity_id=proposal.opportunity_id, state="EXPIRED",
                reason=result.reason, now=now,
            )
        await record_opportunity_event(db_path, opportunity_id=proposal.opportunity_id, policy_id=proposal.policy_id,
            policy_version="v1", account_id=storage_account_id, mode="SHADOW", instrument=proposal.instrument,
            stage=stage, reason_code=result.reason, idempotency_key=f"{proposal.opportunity_id}:{stage.lower()}", observed_at=now,
            detail={"quantity": result.quantity, "gross_pnl": result.gross_pnl, "fees": result.fees, "net_pnl": result.net_pnl})
        outcomes.append({"opportunity_id": proposal.opportunity_id, "status": result.status, "net_pnl": result.net_pnl, "reason": result.reason})
    post_free_cash, _post_open_instruments, _post_identities = await _shadow_account_state(
        db_path, account_id=storage_account_id, scenario_capital=scenario_capital,
    )
    result = {"mode": "SHADOW", "origin": origin, "account_id": account_id, "run_id": run_id, "as_of": now.isoformat(), "proposals": len(proposals), "allocations": len(allocations), "outcomes": outcomes, "reasons": reasons,
              "free_cash": round(post_free_cash, 4), "managed_positions": len(managed), "expired_pending": len(expired_pending),
              "repaired_evidence": repaired_evidence}
    await _complete_shadow_step(
        db_path, run_key=storage_account_id, as_of=now,
        input_digest=step_input_digest, result=result,
    )
    return result


async def run_shadow_replay(
    db_path: str, *, account_id: str, universe: dict[str, list[dict]],
    clock_steps: list[datetime], scenario_capital: float = 8_000,
    future_bars: Optional[dict[str, list[dict]]] = None, run_id: str = "default-v1",
) -> list[dict]:
    """Run the same incremental SHADOW workflow at explicit replay clocks."""
    steps = [_stamp(step) for step in clock_steps]
    if any(right <= left for left, right in zip(steps, steps[1:])):
        raise ValueError("replay clock steps must be strictly increasing")
    return [await run_shadow_workflow(
        db_path, account_id=account_id, universe=universe, now=step,
        scenario_capital=scenario_capital, future_bars=future_bars, run_id=run_id, origin="REPLAY",
    ) for step in steps]


async def _record_shadow_configuration_state(
    db_path: str, *, account_id: str, observed_at: datetime, reason: str,
) -> None:
    """Persist an enabled-but-unusable fixture source as liveness evidence."""
    identity = hashlib.sha256(f"{account_id}:{reason}:{observed_at.isoformat()}".encode()).hexdigest()[:20]
    await record_scan_run(
        db_path, scan_id=f"shadow-config:{identity}", policy_id="shadow_registry_v1",
        account_id=account_id, mode="SHADOW", status="UNAVAILABLE",
        observed_at=observed_at, reason=reason,
    )


def _validate_shadow_bar_collections(collection: object, *, field: str, allow_empty: bool) -> dict[str, list[dict]]:
    """Reject malformed fixture data before it can be misreported as a scan."""
    if not isinstance(collection, dict) or (not allow_empty and not collection):
        raise ValueError(f"fixture {field} must be a non-empty object")
    for instrument, bars in collection.items():
        if not isinstance(instrument, str) or not instrument or not isinstance(bars, list):
            raise ValueError(f"fixture {field} has invalid instrument or bar collection")
        for bar in bars:
            if not isinstance(bar, dict):
                raise ValueError(f"fixture {field} contains a non-object bar")
            try:
                _stamp(datetime.fromisoformat(str(bar["timestamp"])))
                open_, high, low, close, volume = (float(bar[key]) for key in ("open", "high", "low", "close", "volume"))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"fixture {field} bar is incomplete") from exc
            if (not all(math.isfinite(value) and value > 0 for value in (open_, high, low, close, volume))
                    or low > min(open_, close) or high < max(open_, close)):
                raise ValueError(f"fixture {field} bar violates OHLCV bounds")
    return collection


async def run_configured_shadow_workflow(*, now: Optional[datetime] = None) -> dict:
    """Run an explicitly enabled local SHADOW fixture, never a live feed.

    The configuration is intentionally stricter than a generic JSON loader:
    the fixture must declare ``mode: SHADOW`` and contain only the bar payload
    consumed by :func:`run_shadow_workflow`.  Missing or malformed input is
    recorded as unavailable rather than presented as a quiet, successful scan.
    """
    from config import settings

    observed_at = _stamp(now or datetime.now(timezone.utc))
    account_id = str(settings.PROACTIVE_SHADOW_ACCOUNT_ID).strip()
    if not settings.PROACTIVE_SHADOW_ENABLED:
        return {"mode": "SHADOW", "state": "DISABLED"}
    if not account_id:
        raise ValueError("PROACTIVE_SHADOW_ACCOUNT_ID is required when enabled")
    fixture_path = str(settings.PROACTIVE_SHADOW_FIXTURE_PATH).strip()
    if not fixture_path:
        await _record_shadow_configuration_state(
            settings.DB_PATH, account_id=account_id, observed_at=observed_at,
            reason="FIXTURE_SOURCE_UNCONFIGURED",
        )
        return {"mode": "SHADOW", "state": "FIXTURE_SOURCE_UNCONFIGURED"}
    try:
        payload = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("mode") != "SHADOW":
            raise ValueError("fixture must declare mode=SHADOW")
        universe = _validate_shadow_bar_collections(payload.get("universe"), field="universe", allow_empty=False)
        future_bars = _validate_shadow_bar_collections(payload.get("future_bars", {}), field="future_bars", allow_empty=True)
        run_id = str(payload.get("run_id", settings.PROACTIVE_SHADOW_RUN_ID)).strip()
        capital = float(settings.PROACTIVE_SHADOW_SCENARIO_CAPITAL)
        if not run_id or not math.isfinite(capital) or capital <= 0:
            raise ValueError("shadow run identity and scenario capital are required")
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        await _record_shadow_configuration_state(
            settings.DB_PATH, account_id=account_id, observed_at=observed_at,
            reason=f"FIXTURE_SOURCE_INVALID:{type(exc).__name__}",
        )
        return {"mode": "SHADOW", "state": "FIXTURE_SOURCE_INVALID"}
    result = await run_shadow_workflow(
        settings.DB_PATH, account_id=account_id, universe=universe,
        future_bars=future_bars, scenario_capital=capital, run_id=run_id, now=observed_at,
    )
    return {**result, "state": "COMPLETED"}


async def proactive_activity_report(db_path: str, *, days: int = 7) -> dict:
    """Mode-separated counts; absent evidence is explicit rather than zero-health."""
    if not 1 <= days <= 366:
        raise ValueError("days must be within 1..366")
    await init_proactive_intelligence(db_path)
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT mode, stage, COUNT(*), COUNT(DISTINCT opportunity_id) FROM proactive_events "
            "WHERE session_date >= date('now', ?) GROUP BY mode, stage",
            (f'-{days - 1} days',),
        )
        rows = await cur.fetchall()
        cur = await db.execute(
            "SELECT mode, COUNT(DISTINCT opportunity_id) FROM proactive_events WHERE session_date >= date('now', ?) GROUP BY mode",
            (f'-{days - 1} days',),
        )
        unique_rows = await cur.fetchall()
        cur = await db.execute(
            "SELECT mode, COUNT(*) FROM proactive_scan_runs WHERE status='SUCCESS' AND date(observed_at) >= date('now', ?) GROUP BY mode",
            (f'-{days - 1} days',),
        )
        scan_rows = await cur.fetchall()
        cur = await db.execute(
            "SELECT mode, flow_type, COALESCE(SUM(amount),0) FROM proactive_cash_flows "
            "GROUP BY mode, flow_type"
        )
        flows = await cur.fetchall()
        cur = await db.execute(
            "SELECT p.account_id,COALESCE(r.run_id,'legacy'),r.manifest_json,"
            "SUM(CASE WHEN status='OPEN' THEN 1 ELSE 0 END),"
            "SUM(CASE WHEN status='CLOSED' THEN 1 ELSE 0 END),"
            "COALESCE(SUM(CASE WHEN status='OPEN' THEN entry_price*quantity+entry_fees ELSE 0 END),0),"
            "COALESCE(SUM(CASE WHEN status='CLOSED' THEN gross_pnl ELSE 0 END),0),"
            "COALESCE(SUM(CASE WHEN status='CLOSED' THEN exit_fees+entry_fees ELSE 0 END),0),"
            "COALESCE(SUM(CASE WHEN status='CLOSED' THEN net_pnl ELSE 0 END),0) "
            "FROM proactive_shadow_positions p LEFT JOIN proactive_shadow_runs r ON r.run_key=p.account_id "
            "GROUP BY p.account_id,COALESCE(r.run_id,'legacy'),r.manifest_json",
        )
        position_rows = await cur.fetchall()
    by_mode: dict[str, dict] = {mode: {"scan_evaluations": 0, "unique_opportunities": 0, "stages": {}} for mode in sorted(_MODES)}
    for mode, stage, count, _unique_count in rows:
        by_mode[mode]["stages"][stage] = int(count)
    for mode, unique_count in unique_rows:
        by_mode[mode]["unique_opportunities"] = int(unique_count)
    for mode, scan_count in scan_rows:
        by_mode[mode]["scan_evaluations"] = int(scan_count)
    funding = {mode: {} for mode in _MODES}
    for mode, flow_type, amount in flows:
        funding[mode][flow_type] = float(amount)
    shadow_positions = []
    for row in position_rows:
        try:
            manifest = json.loads(row[2]) if row[2] else {}
            scenario_capital = float(manifest["scenario_capital"]) if manifest else None
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            scenario_capital = None
        reserved, realised = float(row[5]), float(row[8])
        shadow_positions.append({
            "account_id": row[0], "run_id": row[1], "open_positions": int(row[3]), "closed_positions": int(row[4]),
            "reserved_capital": round(reserved, 4), "gross_pnl": round(float(row[6]), 4),
            "fees": round(float(row[7]), 4), "net_pnl": round(realised, 4),
            "scenario_capital": scenario_capital,
            "free_cash": (round(max(0.0, scenario_capital + realised - reserved), 4)
                          if scenario_capital is not None else None),
            "marked_unrealized_pnl": None,
            "unrealized_state": "UNAVAILABLE_NO_CURRENT_MARK",
        })
    return {"as_of": datetime.now(timezone.utc).isoformat(), "days": days, "modes": by_mode, "funding_flows": funding,
            "shadow_positions": shadow_positions,
            "note": "Events are operational evidence; only reconciled live ledgers establish live profit."}
