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


@dataclass(frozen=True)
class ShadowAllocation:
    opportunity_id: str
    quantity: int
    executable_price: float
    fee_reserve: float
    reserved_capital: float
    initial_risk: float


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
    quantity = 0; entry = None
    for bar in future_bars:
        try:
            stamp = _stamp(datetime.fromisoformat(str(bar["timestamp"])))
            open_, high, low, close = (float(bar[key]) for key in ("open", "high", "low", "close"))
        except (KeyError, TypeError, ValueError):
            continue
        if not all(math.isfinite(value) and value > 0 for value in (open_, high, low, close)) or low > min(open_, close) or high < max(open_, close):
            continue
        if entry is None:
            if stamp <= cutoff or stamp > entry_deadline:
                continue
            entry = open_ * (1 + slip)
            quantity = (allocation.quantity if allocation is not None else min(max_quantity if max_quantity is not None else math.inf, math.floor(cash / (entry * (1 + fee_rate)))))
            if quantity < 1:
                return ShadowSimulation("NO_FILL", 0, None, None, None, None, None, "INSUFFICIENT_CASH_AFTER_FEES")
            if allocation is not None and (allocation.opportunity_id != proposal.opportunity_id or entry * quantity * (1 + fee_rate) > allocation.reserved_capital + .01):
                return ShadowSimulation("NO_FILL", 0, None, None, None, None, None, "ALLOCATION_NO_LONGER_FEASIBLE")
            if entry <= proposal.stop or entry >= proposal.target:
                return ShadowSimulation("NO_FILL", 0, None, None, None, None, None, "GAP_INVALIDATES_ENTRY_GEOMETRY")
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
        return ShadowSimulation("CLOSED", quantity, round(entry, 4), round(exit_price, 4), round(gross, 4), round(fees, 4), round(gross-fees, 4), reason)
    if entry is None:
        return ShadowSimulation("NO_FILL", 0, None, None, None, None, None, "NO_EXECUTABLE_BAR_AFTER_SIGNAL")
    return ShadowSimulation("OPEN", quantity, round(entry, 4), None, None, None, None, "DATA_END_OPEN_POSITION")

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
            "SELECT mode, MAX(observed_at) FROM proactive_scan_runs GROUP BY mode"
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
    for mode, last_at in rows:
        last = _stamp(datetime.fromisoformat(last_at)) if last_at else None
        if last is None or now - last > max_scan_gap * 2:
            findings.append({"mode": mode, "code": "MISSED_SCAN_INTERVALS", "last_event_at": last_at})
    for mode, opportunity_id, event_at in dropped:
        findings.append({"mode": mode, "code": "DROPPED_RISK_APPROVED_WORKFLOW", "opportunity_id": opportunity_id, "last_event_at": event_at})
    return findings


async def run_shadow_workflow(
    db_path: str, *, account_id: str, universe: dict[str, list[dict]], now: datetime,
    scenario_capital: float = 8_000, future_bars: Optional[dict[str, list[dict]]] = None,
) -> dict:
    """Run the bounded fixture-backed SHADOW path; never calls a broker.

    This is the application consumer for the proposal/allocator/simulator
    contracts. Callers provide completed bars and optional later bars so data
    provenance remains explicit and deterministic.
    """
    now = _stamp(now); future_bars = future_bars or {}
    proposals: list[ShadowProposal] = []
    for instrument, bars in sorted(universe.items()):
        scan_id = hashlib.sha256(f"{account_id}:{instrument}:{now.isoformat()}".encode()).hexdigest()[:20]
        built = build_shadow_proposals(instrument, bars, now=now)
        policies = {proposal.policy_id for proposal in built} or {"shadow_registry_v1"}
        for policy_id in policies:
            await record_scan_run(db_path, scan_id=f"{scan_id}:{policy_id}", policy_id=policy_id,
                                  account_id=account_id, mode="SHADOW", status="SUCCESS", observed_at=now,
                                  reason="COMPLETED_BARS" if built else "NO_COMPLETED_SETUP")
        for proposal in built:
            await record_opportunity_event(db_path, opportunity_id=proposal.opportunity_id,
                policy_id=proposal.policy_id, policy_version="v1", account_id=account_id,
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
    allocations, reasons = size_shadow_allocations(proposals, capital=scenario_capital)
    allocated = {item.opportunity_id: item for item in allocations}
    outcomes = []
    for proposal in proposals:
        allocation = allocated.get(proposal.opportunity_id)
        if allocation is None:
            await record_opportunity_event(db_path, opportunity_id=proposal.opportunity_id, policy_id=proposal.policy_id,
                policy_version="v1", account_id=account_id, mode="SHADOW", instrument=proposal.instrument,
                stage="DEFERRED", reason_code=reasons[proposal.opportunity_id], idempotency_key=f"{proposal.opportunity_id}:deferred",
                observed_at=now)
            continue
        await record_opportunity_event(db_path, opportunity_id=proposal.opportunity_id, policy_id=proposal.policy_id,
            policy_version="v1", account_id=account_id, mode="SHADOW", instrument=proposal.instrument,
            stage="SELECTED", reason_code="SHARED_CASH_RESERVED", idempotency_key=f"{proposal.opportunity_id}:selected", observed_at=now)
        result = simulate_shadow_trade(proposal, future_bars.get(proposal.instrument, []), cash=scenario_capital, allocation=allocation)
        stage = "CLOSED" if result.status == "CLOSED" else "FILLED" if result.status == "OPEN" else "EXPIRED"
        await record_opportunity_event(db_path, opportunity_id=proposal.opportunity_id, policy_id=proposal.policy_id,
            policy_version="v1", account_id=account_id, mode="SHADOW", instrument=proposal.instrument,
            stage=stage, reason_code=result.reason, idempotency_key=f"{proposal.opportunity_id}:{stage.lower()}", observed_at=now,
            detail={"quantity": result.quantity, "gross_pnl": result.gross_pnl, "fees": result.fees, "net_pnl": result.net_pnl})
        outcomes.append({"opportunity_id": proposal.opportunity_id, "status": result.status, "net_pnl": result.net_pnl, "reason": result.reason})
    return {"mode": "SHADOW", "proposals": len(proposals), "allocations": len(allocations), "outcomes": outcomes, "reasons": reasons}


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
            "SELECT mode, COUNT(*) FROM proactive_scan_runs WHERE date(observed_at) >= date('now', ?) GROUP BY mode",
            (f'-{days - 1} days',),
        )
        scan_rows = await cur.fetchall()
        cur = await db.execute(
            "SELECT mode, flow_type, COALESCE(SUM(amount),0) FROM proactive_cash_flows "
            "GROUP BY mode, flow_type"
        )
        flows = await cur.fetchall()
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
    return {"as_of": datetime.now(timezone.utc).isoformat(), "days": days, "modes": by_mode, "funding_flows": funding,
            "note": "Events are operational evidence; only reconciled live ledgers establish live profit."}
