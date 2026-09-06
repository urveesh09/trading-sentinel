"""Offline-safe evidence ledger for proactive strategy research.

This module is deliberately policy-agnostic: it records what a scanner or
allocator did without creating an order, and keeps shadow/replay evidence out
of the live cash books.
"""
from __future__ import annotations

import json
import hashlib
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
    "ARMED": {"TRIGGERED", "INVALIDATED", "EXPIRED"},
    "TRIGGERED": {"SELECTED", "DEFERRED", "REJECTED", "EXPIRED"},
    "DEFERRED": {"TRIGGERED", "INVALIDATED", "EXPIRED"},
    "SELECTED": {"COMPLETED", "INVALIDATED"},
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


def _proposal_id(policy_id: str, instrument: str, bar_time: datetime) -> str:
    return hashlib.sha256(f"{policy_id}:{instrument}:{_stamp(bar_time).isoformat()}".encode()).hexdigest()[:20]


def build_shadow_proposals(instrument: str, bars: list[dict], *, now: datetime) -> list[ShadowProposal]:
    """Three reproducible completed-bar hypotheses with no look-ahead.

    Bars contain timestamp/open/high/low/close/volume. The last bar is the
    observed completed trigger; every reference excludes it where required.
    """
    now = _stamp(now)
    if len(bars) < 21:
        return []
    try:
        closes = [float(bar["close"]) for bar in bars]
        highs = [float(bar["high"]) for bar in bars]
        lows = [float(bar["low"]) for bar in bars]
        volumes = [float(bar["volume"]) for bar in bars]
        trigger_at = _stamp(datetime.fromisoformat(str(bars[-1]["timestamp"])))
    except (KeyError, TypeError, ValueError):
        return []
    if trigger_at > now or min(closes + highs + lows) <= 0:
        return []
    last, prior = closes[-1], closes[-2]
    fast, slow = sum(closes[-5:]) / 5, sum(closes[-20:]) / 20
    proposals: list[ShadowProposal] = []
    expiry = trigger_at + timedelta(minutes=30)
    # Trend: uptrend, pullback toward fast MA, then confirmed completed-bar reclaim.
    if fast > slow and closes[-3] <= fast * 1.01 and last > prior:
        stop = min(lows[-3:])
        if 0 < stop < last:
            proposals.append(ShadowProposal(_proposal_id("trend_pullback_v1", instrument, trigger_at), "trend_pullback_v1", instrument, last, stop, last + 2 * (last-stop), expiry, fast/slow, last, "TREND_PULLBACK_RECLAIM"))
    # Range: low directional drift, downside stretch, then stabilization/reclaim.
    window = closes[-15:-1]
    mean = sum(window) / len(window)
    if max(window)-min(window) <= mean * .06 and closes[-2] < mean * .985 and last > closes[-2]:
        stop = min(lows[-2:])
        if 0 < stop < last:
            proposals.append(ShadowProposal(_proposal_id("range_reversion_v1", instrument, trigger_at), "range_reversion_v1", instrument, last, stop, mean, expiry, (mean-last)/mean, last, "RANGE_STABILIZATION_RECLAIM"))
    # Breakout: previous range contracts vs older range; trigger breaks prior range on volume.
    recent_width = max(highs[-6:-1]) - min(lows[-6:-1])
    old_width = max(highs[-16:-6]) - min(lows[-16:-6])
    prior_high = max(highs[-6:-1])
    if old_width > 0 and recent_width < old_width * .7 and last > prior_high and volumes[-1] > sum(volumes[-11:-1])/10:
        stop = min(lows[-6:-1])
        if 0 < stop < last:
            proposals.append(ShadowProposal(_proposal_id("contraction_breakout_v1", instrument, trigger_at), "contraction_breakout_v1", instrument, last, stop, last + 2 * (last-stop), expiry, volumes[-1]/(sum(volumes[-11:-1])/10), last, "CONTRACTION_BREAKOUT"))
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


def simulate_shadow_trade(
    proposal: ShadowProposal, future_bars: list[dict], *, cash: float,
    fee_rate: float = .001, slippage_bps: float = 5, max_quantity: Optional[int] = None,
) -> ShadowSimulation:
    """Conservative long-only completed-bar simulator for research evidence.

    Entry is at the first subsequent bar open plus slippage. If stop and target
    occur in one bar, stop wins: OHLC cannot establish the intrabar order.
    """
    if cash <= 0 or fee_rate < 0 or slippage_bps < 0:
        raise ValueError("invalid simulation assumptions")
    slip = slippage_bps / 10_000
    quantity = min(max_quantity or math.inf, math.floor(cash / (proposal.entry * (1 + fee_rate))))
    if quantity < 1:
        return ShadowSimulation("NO_FILL", 0, None, None, None, None, None, "INSUFFICIENT_CASH_AFTER_FEES")
    for bar in future_bars:
        try:
            stamp = _stamp(datetime.fromisoformat(str(bar["timestamp"])))
            if stamp > proposal.valid_until:
                break
            entry = float(bar["open"]) * (1 + slip)
            high, low = float(bar["high"]), float(bar["low"])
        except (KeyError, TypeError, ValueError):
            continue
        if entry <= 0:
            continue
        exit_price = None; reason = "TIME_EXIT"
        if low <= proposal.stop and high >= proposal.target:
            exit_price = proposal.stop * (1 - slip); reason = "AMBIGUOUS_BAR_STOP_FIRST"
        elif low <= proposal.stop:
            exit_price = proposal.stop * (1 - slip); reason = "STOP"
        elif high >= proposal.target:
            exit_price = proposal.target * (1 - slip); reason = "TARGET"
        else:
            exit_price = float(bar["close"]) * (1 - slip)
        gross = (exit_price - entry) * quantity
        fees = (entry + exit_price) * quantity * fee_rate
        return ShadowSimulation("CLOSED", quantity, round(entry, 4), round(exit_price, 4), round(gross, 4), round(fees, 4), round(gross-fees, 4), reason)
    return ShadowSimulation("NO_FILL", 0, None, None, None, None, None, "NO_EXECUTABLE_BAR_AFTER_SIGNAL")

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
CREATE TABLE IF NOT EXISTS proactive_watchlist (
 opportunity_id TEXT PRIMARY KEY, state TEXT NOT NULL, reason TEXT NOT NULL,
 updated_at TEXT NOT NULL, valid_until TEXT NOT NULL
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
        if now >= _stamp(datetime.fromisoformat(expiry)) and state != "EXPIRED":
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


async def proactive_inactivity_diagnostics(db_path: str, *, now: datetime, max_scan_gap: timedelta = timedelta(minutes=30)) -> list[dict]:
    """Return evidence gaps; diagnostics never alter a strategy threshold."""
    now = _stamp(now)
    await init_proactive_intelligence(db_path)
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute(
            "SELECT mode, MAX(event_at), SUM(CASE WHEN stage='RISK_APPROVED' THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN stage IN ('SUBMITTED','FILLED') THEN 1 ELSE 0 END) FROM proactive_events GROUP BY mode"
        )).fetchall()
    findings = []
    for mode, last_at, approved, fills in rows:
        last = _stamp(datetime.fromisoformat(last_at)) if last_at else None
        if last is None or now - last > max_scan_gap * 2:
            findings.append({"mode": mode, "code": "MISSED_SCAN_INTERVALS", "last_event_at": last_at})
        if int(approved or 0) and not int(fills or 0):
            findings.append({"mode": mode, "code": "DROPPED_RISK_APPROVED_WORKFLOW", "last_event_at": last_at})
    return findings


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
            "SELECT mode, flow_type, COALESCE(SUM(amount),0) FROM proactive_cash_flows "
            "GROUP BY mode, flow_type"
        )
        flows = await cur.fetchall()
    by_mode: dict[str, dict] = {mode: {"scan_evaluations": 0, "unique_opportunities": 0, "stages": {}} for mode in sorted(_MODES)}
    for mode, stage, count, unique_count in rows:
        by_mode[mode]["stages"][stage] = int(count)
        by_mode[mode]["scan_evaluations"] += int(count)
        by_mode[mode]["unique_opportunities"] = max(by_mode[mode]["unique_opportunities"], int(unique_count))
    funding = {mode: {} for mode in _MODES}
    for mode, flow_type, amount in flows:
        funding[mode][flow_type] = float(amount)
    return {"as_of": datetime.now(timezone.utc).isoformat(), "days": days, "modes": by_mode, "funding_flows": funding,
            "note": "Events are operational evidence; only reconciled live ledgers establish live profit."}
