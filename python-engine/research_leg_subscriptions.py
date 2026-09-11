"""Durable, bounded selected-leg retention for intraday research.

The rolling ATM collector is useful for discovery but cannot stand in for a
contract that a policy actually selected.  This small SQLite journal pins the
exact dated token/master identity through its declared intraday management
deadline.  It is research evidence only: it has no order, delivery, profile,
or qualification imports.
"""
from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from fno_models import Contract


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("subscription timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _stamp(value: datetime) -> str:
    return _utc(value).isoformat()


@dataclass(frozen=True)
class ActiveLeg:
    decision_id: str
    contract: Contract
    exchange: str
    master_sha256: str | None
    management_deadline: datetime


class ResearchLegSubscriptionStore:
    """Synchronous journal called through ``asyncio.to_thread`` by producers."""

    def __init__(self, archive_root: str | Path):
        self.path = Path(archive_root) / "selected-leg-subscriptions.sqlite3"

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=5)
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS selected_leg_subscriptions (
          decision_id TEXT NOT NULL,
          token INTEGER NOT NULL,
          exchange TEXT NOT NULL,
          underlying TEXT NOT NULL,
          symbol TEXT NOT NULL,
          expiry TEXT NOT NULL,
          strike REAL NOT NULL,
          instrument_type TEXT NOT NULL,
          lot_size INTEGER NOT NULL,
          tick_size REAL NOT NULL,
          master_sha256 TEXT,
          management_deadline_utc TEXT NOT NULL,
          state TEXT NOT NULL DEFAULT 'ACTIVE',
          registered_at_utc TEXT NOT NULL,
          last_requested_at_utc TEXT,
          last_received_at_utc TEXT,
          missing_count INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (decision_id, token)
        );
        CREATE TABLE IF NOT EXISTS selected_leg_collection_gaps (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          recorded_at_utc TEXT NOT NULL,
          decision_id TEXT NOT NULL,
          token INTEGER NOT NULL,
          reason TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS selected_leg_active_idx
          ON selected_leg_subscriptions (underlying, state, management_deadline_utc);
        """)
        return db

    def register(self, *, decision_id: str, exchange: str, contracts: Iterable[Contract],
                 management_deadline: datetime, master_sha256: str | None = None,
                 registered_at: datetime | None = None) -> int:
        """Pin immutable contracts and deadline; exact retries are idempotent."""
        if not decision_id.strip() or not exchange.strip():
            raise ValueError("decision_id and exchange are required")
        if master_sha256 is not None and (len(master_sha256) != 64 or any(c not in "0123456789abcdef" for c in master_sha256.lower())):
            raise ValueError("master_sha256 must be a SHA-256 digest when supplied")
        deadline = _stamp(management_deadline)
        now = _stamp(registered_at or datetime.now(timezone.utc))
        rows = []
        for contract in contracts:
            if contract.token <= 0 or contract.lot_size <= 0 or not contract.tradingsymbol or contract.instrument_type not in {"CE", "PE"}:
                raise ValueError("selected subscription contract is incomplete")
            if ({"NIFTY": "NFO", "SENSEX": "BFO"}.get(contract.name.upper()) != exchange.upper()
                    or not math.isfinite(contract.strike) or contract.strike <= 0
                    or not math.isfinite(contract.tick_size) or contract.tick_size <= 0):
                raise ValueError("selected subscription contract scope or economics is invalid")
            rows.append((decision_id, int(contract.token), exchange.upper(), contract.name.upper(), contract.tradingsymbol,
                         contract.expiry.isoformat(), float(contract.strike), contract.instrument_type.upper(), int(contract.lot_size),
                         float(contract.tick_size), master_sha256, deadline, now))
        if not rows:
            return 0
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # Check the whole batch under the write lock before changing any
            # row. Retries cannot revive terminal generations or move their
            # deadline/master binding while retaining the old contract fields.
            for row in rows:
                existing = db.execute("""
                    SELECT decision_id,token,exchange,underlying,symbol,expiry,strike,instrument_type,lot_size,tick_size,
                           master_sha256,management_deadline_utc
                    FROM selected_leg_subscriptions WHERE decision_id=? AND token=?
                """, row[:2]).fetchone()
                if existing is not None and tuple(existing) != tuple(row[:12]):
                    raise ValueError("selected subscription identity is immutable")
            db.executemany("""
              INSERT INTO selected_leg_subscriptions(
                decision_id,token,exchange,underlying,symbol,expiry,strike,instrument_type,lot_size,tick_size,
                master_sha256,management_deadline_utc,registered_at_utc)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
              ON CONFLICT(decision_id,token) DO NOTHING
            """, rows)
        return len(rows)

    def active(self, *, underlying: str, now: datetime, capacity: int) -> tuple[list[ActiveLeg], list[ActiveLeg]]:
        """Return active exact legs plus explicit capacity-shortfall legs.

        No nearby-strike substitution is performed.  Contract selection is
        deterministic by earliest deadline then decision/token identity.
        """
        if capacity < 1:
            raise ValueError("active subscription capacity must be positive")
        stamp = _stamp(now)
        with self._connect() as db:
            rows = db.execute("""
                SELECT decision_id,token,exchange,underlying,symbol,expiry,strike,instrument_type,lot_size,tick_size,
                       master_sha256,management_deadline_utc
                FROM selected_leg_subscriptions
                WHERE underlying=? AND state='ACTIVE' AND management_deadline_utc>=?
                ORDER BY management_deadline_utc,decision_id,token
            """, (underlying.upper(), stamp)).fetchall()
        legs = [ActiveLeg(
            decision_id=row[0], contract=Contract(int(row[1]), row[4], row[3], datetime.fromisoformat(row[5]).date(),
                                                    float(row[6]), row[7], int(row[8]), float(row[9])),
            exchange=row[2], master_sha256=row[10], management_deadline=datetime.fromisoformat(row[11]),
        ) for row in rows]
        # Capacity is a provider-token budget, not a decision-row budget.
        # Several ideas may depend on the same contract; retain every owner's
        # coverage while consuming only one quote slot for that contract.
        selected_tokens: set[tuple[str, int]] = set()
        selected, shortfall = [], []
        for leg in legs:
            key = (leg.exchange, leg.contract.token)
            if key in selected_tokens or len(selected_tokens) < capacity:
                selected_tokens.add(key)
                selected.append(leg)
            else:
                shortfall.append(leg)
        return selected, shortfall

    def record_collection(self, *, requested_tokens: Iterable[int], received_tokens: Iterable[int],
                          now: datetime, capacity_shortfall: Iterable[ActiveLeg] = ()) -> None:
        """Persist actual selected-leg request/receipt coverage and every gap."""
        requested, received = {int(token) for token in requested_tokens}, {int(token) for token in received_tokens}
        stamp = _stamp(now)
        with self._connect() as db:
            if requested:
                placeholders = ",".join("?" for _ in requested)
                db.execute(f"UPDATE selected_leg_subscriptions SET last_requested_at_utc=? WHERE state='ACTIVE' AND token IN ({placeholders})",
                           (stamp, *sorted(requested)))
                missing = requested - received
                if missing:
                    missing_placeholders = ",".join("?" for _ in missing)
                    rows = db.execute(f"SELECT decision_id,token FROM selected_leg_subscriptions WHERE state='ACTIVE' AND token IN ({missing_placeholders})",
                                      tuple(sorted(missing))).fetchall()
                    db.execute(f"UPDATE selected_leg_subscriptions SET missing_count=missing_count+1 WHERE state='ACTIVE' AND token IN ({missing_placeholders})",
                               tuple(sorted(missing)))
                    db.executemany("INSERT INTO selected_leg_collection_gaps(recorded_at_utc,decision_id,token,reason) VALUES(?,?,?,?)",
                                   [(stamp, decision, token, "active_leg_packet_missing") for decision, token in rows])
                if received:
                    received_placeholders = ",".join("?" for _ in received)
                    db.execute(f"UPDATE selected_leg_subscriptions SET last_received_at_utc=? WHERE state='ACTIVE' AND token IN ({received_placeholders})",
                               (stamp, *sorted(received)))
            db.executemany("INSERT INTO selected_leg_collection_gaps(recorded_at_utc,decision_id,token,reason) VALUES(?,?,?,?)",
                           [(stamp, leg.decision_id, leg.contract.token, "active_leg_capacity_shortfall") for leg in capacity_shortfall])

    def finalize(self, *, now: datetime, evidence_retention_days: int) -> dict:
        """Release only after deadline, retain terminal coverage for audit, then bound it."""
        if evidence_retention_days < 1:
            raise ValueError("evidence retention must be positive")
        stamp = _stamp(now)
        delete_before = _stamp(_utc(now) - timedelta(days=evidence_retention_days))
        with self._connect() as db:
            released = db.execute("UPDATE selected_leg_subscriptions SET state='TERMINAL' WHERE state='ACTIVE' AND management_deadline_utc<?",
                                  (stamp,)).rowcount
            deleted = db.execute("DELETE FROM selected_leg_subscriptions WHERE state='TERMINAL' AND management_deadline_utc<?",
                                 (delete_before,)).rowcount
            db.execute("DELETE FROM selected_leg_collection_gaps WHERE recorded_at_utc<?", (delete_before,))
            active = db.execute("SELECT COUNT(*) FROM selected_leg_subscriptions WHERE state='ACTIVE'").fetchone()[0]
        return {"released": released, "deleted": deleted, "active": active}

    def readiness(self, *, now: datetime) -> dict:
        """Expose coverage without mistaking it for a strategy qualification."""
        stamp = _stamp(now)
        if not self.path.exists():
            return {"per_index": {}, "recent_gap_count": 0, "qualification": "NOT_EVALUATED_HERE"}
        with sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True) as db:
            active = db.execute("SELECT underlying,COUNT(*),SUM(missing_count) FROM selected_leg_subscriptions WHERE state='ACTIVE' AND management_deadline_utc>=? GROUP BY underlying", (stamp,)).fetchall()
            recent_gaps = db.execute("SELECT COUNT(*) FROM selected_leg_collection_gaps WHERE recorded_at_utc>=?", (_stamp(_utc(now) - timedelta(hours=1)),)).fetchone()[0]
        return {"per_index": {row[0]: {"active_legs": row[1], "missing_packets": row[2]} for row in active},
                "recent_gap_count": recent_gaps, "qualification": "NOT_EVALUATED_HERE"}
