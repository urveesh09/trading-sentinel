"""Offline-safe evidence ledger for proactive strategy research.

This module is deliberately policy-agnostic: it records what a scanner or
allocator did without creating an order, and keeps shadow/replay evidence out
of the live cash books.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Literal, Optional

import aiosqlite

Mode = Literal["LIVE", "PAPER", "SHADOW", "REPLAY"]
_MODES = frozenset({"LIVE", "PAPER", "SHADOW", "REPLAY"})
_STAGES = frozenset({
    "UNIVERSE", "DATA_READY", "SETUP", "COST_VIABLE", "RISK_APPROVED",
    "SELECTED", "SUBMITTED", "FILLED", "MANAGED", "CLOSED", "DEFERRED",
    "REJECTED", "EXPIRED", "UNAVAILABLE",
})

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
