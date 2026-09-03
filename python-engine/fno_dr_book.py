"""
[FNO-DR-BOOK 2026-07-20] Paper book that trades the defined-risk structures
from fno_defined_risk (Phase 2 wiring). It rides the EXISTING run_fno_tick:
that tick already builds the directional signal and the chain snapshot, so
this book reuses both -- no second scheduler job, no duplicate market data.

Scope (P1, paper only):
  - One structure open at a time per source (FNO_PAPER). Simple, auditable.
  - 1-lot unit; a structure whose 1-lot max-loss exceeds FNO_DR_MAX_LOSS_RS is
    skipped rather than force-sized. Multi-lot pool sizing is a later refinement
    (fno_risk.lots_for_pool) and gated behind the promotion bar anyway.
  - Mark-to-mid P&L; exit on target / stop (fractions of the structure's own
    max-profit / max-loss) or the intraday square-off time. Every close writes
    to bankroll_ledger under FNO_PAPER via performance.record_trade_close, so
    the strategy funnel and /bankroll/divisions pick it up automatically.

Storage is a self-contained fno_dr_positions table (structure-level, legs as
JSON) so the single-leg fno_positions engine is untouched.

Purity note: the decision math lives in fno_defined_risk (pure); this module
owns I/O (DB + the snapshot adapter) and the paper lifecycle only.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import aiosqlite
import structlog

from config import settings
from fno_analytics import atm_iv
from fno_chain import ChainSnapshot
from fno_defined_risk import (
    RouterParams, Structure, StructureKind,
    build_debit_spread, build_iron_condor, select_structure,
    structure_round_trip_cost,
)
from fno_models import FnoDirection, Leg, OptionType

logger = structlog.get_logger()

SOURCE_PAPER = "FNO_PAPER"


# ---------------------------------------------------------------------------
# config accessors (getattr defaults -- no config.py edit required to run)
# ---------------------------------------------------------------------------

def _enabled() -> bool:
    return bool(getattr(settings, "FNO_DR_PAPER_ENABLED", True))


def _strike_step() -> float:
    return float(getattr(settings, "FNO_DR_STRIKE_STEP", getattr(settings, "FNO_STRIKE_STEP", 50.0)))


def _lot_size() -> int:
    return int(getattr(settings, "FNO_DR_LOT_SIZE", getattr(settings, "FNO_LOT_SIZE", 75)))


def _debit_width() -> int:
    return int(getattr(settings, "FNO_DR_DEBIT_WIDTH", 2))


def _condor_offset() -> int:
    return int(getattr(settings, "FNO_DR_CONDOR_SHORT_OFFSET", 4))


def _condor_wing() -> int:
    return int(getattr(settings, "FNO_DR_CONDOR_WING_WIDTH", 2))


def _max_loss_ceiling() -> float:
    return float(getattr(settings, "FNO_DR_MAX_LOSS_RS", 10000.0))


def _target_frac() -> float:
    return float(getattr(settings, "FNO_DR_TARGET_FRAC", 0.5))   # take half of max profit


def _stop_frac() -> float:
    return float(getattr(settings, "FNO_DR_STOP_FRAC", 0.6))     # cut at 60% of max loss


def _entry_lo_min() -> int:
    return int(getattr(settings, "FNO_DR_ENTRY_START_MIN", 9 * 60 + 30))   # 09:30


def _entry_hi_min() -> int:
    return int(getattr(settings, "FNO_DR_ENTRY_END_MIN", 14 * 60 + 45))    # 14:45


def _squareoff_min() -> int:
    return int(getattr(settings, "FNO_DR_SQUAREOFF_MIN", 15 * 60 + 10))    # 15:10


def _iv_low() -> float:
    return float(getattr(settings, "FNO_DR_IV_LOW", 0.10))


def _iv_high() -> float:
    return float(getattr(settings, "FNO_DR_IV_HIGH", 0.20))


# ---------------------------------------------------------------------------
# snapshot adapters (the only coupling to the live chain format)
# ---------------------------------------------------------------------------

def premium_lookup_from_snapshot(snap: ChainSnapshot):
    """Adapt a ChainSnapshot into fno_defined_risk.PremiumLookup. Uses the
    two-sided mid; returns None for a missing / one-sided (illiquid) strike so
    the builder stands aside rather than trade a price it cannot trust."""
    def prem(opt: OptionType, strike: float) -> Optional[float]:
        q = snap.quote(float(strike), opt)
        if q is None:
            return None
        m = q.mid
        return float(m) if m and m > 0 else None
    return prem


def _nearest_strike(spot: float, step: float) -> float:
    return round(spot / step) * step


def expected_move_pct_from_snapshot(snap: ChainSnapshot, step: float) -> Optional[float]:
    """ATM straddle / spot -- the market's own priced expected move to expiry.
    Snapshot-only (no history needed)."""
    if not snap.forward or snap.forward <= 0:
        return None
    atm = _nearest_strike(snap.forward, step)
    ce = snap.quote(atm, OptionType.CE)
    pe = snap.quote(atm, OptionType.PE)
    if ce is None or pe is None or ce.mid <= 0 or pe.mid <= 0:
        return None
    return (ce.mid + pe.mid) / snap.forward


def iv_rank_proxy(iv: Optional[float]) -> Optional[float]:
    """A snapshot-only stand-in for IV-rank: map ATM IV linearly onto [0,1]
    between config IV_LOW and IV_HIGH. A true percentile-rank needs an IV
    history store (a later refinement); this is enough to keep the condor from
    selling cheap premium."""
    if iv is None:
        return None
    lo, hi = _iv_low(), _iv_high()
    if hi <= lo:
        return None
    return max(0.0, min(1.0, (iv - lo) / (hi - lo)))


# ---------------------------------------------------------------------------
# planning
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlannedStructure:
    structure: Structure
    entry_underlying: float


def plan_structure(
    snap: ChainSnapshot,
    has_directional_signal: bool,
    direction: Optional[FnoDirection],
    now_ist: datetime,
) -> Optional[PlannedStructure]:
    """Pure-ish: from the snapshot + the tick's directional signal, pick and
    build a defined-risk structure, or None (stand aside). No DB, no orders."""
    if snap is None or not snap.forward or snap.forward <= 0:
        logger.info("fno_dr_stand_aside reason=invalid_snapshot")
        return None
    step = _strike_step()
    iv = atm_iv(snap, now_ist)
    em = expected_move_pct_from_snapshot(snap, step)
    iv_rank = iv_rank_proxy(iv)
    kind = select_structure(
        has_directional_signal=has_directional_signal,
        iv_rank=iv_rank,
        expected_move_pct=em,
    )
    if kind is None:
        params = RouterParams()
        if has_directional_signal:
            reason = "expected_move_below_debit_min"
        elif iv_rank is None or em is None:
            reason = "missing_iv_or_expected_move"
        elif iv_rank < params.min_iv_rank_condor:
            reason = "iv_rank_below_condor_min"
        else:
            reason = "expected_move_above_condor_max"
        logger.info(
            "fno_dr_stand_aside reason=%s directional=%s iv=%s iv_rank=%s "
            "expected_move_pct=%s",
            reason, has_directional_signal,
            round(iv, 6) if iv is not None else None,
            round(iv_rank, 4) if iv_rank is not None else None,
            round(em, 6) if em is not None else None,
        )
        return None
    prem = premium_lookup_from_snapshot(snap)
    atm = _nearest_strike(snap.forward, step)
    lot = _lot_size()

    if kind == StructureKind.DEBIT_SPREAD:
        if direction is None:
            return None
        structure = build_debit_spread(direction, atm, step, _debit_width(), prem, lot)
    else:
        structure = build_iron_condor(atm, step, _condor_offset(), _condor_wing(), prem, lot)

    if structure is None or not structure.is_defined_risk:
        logger.info(
            "fno_dr_stand_aside reason=unpriceable_or_invalid_structure kind=%s",
            kind.value,
        )
        return None
    if structure.max_loss_rs > _max_loss_ceiling():
        logger.info(
            "fno_dr_skip reason=max_loss_over_ceiling kind=%s max_loss=%.0f ceiling=%.0f",
            kind.value, structure.max_loss_rs, _max_loss_ceiling(),
        )
        return None
    return PlannedStructure(structure=structure, entry_underlying=float(snap.forward))


# ---------------------------------------------------------------------------
# mark-to-market + exit
# ---------------------------------------------------------------------------

def _legs_from_json(legs_json: str) -> List[Leg]:
    return [
        Leg(opt_type=OptionType(d["opt_type"]), strike=float(d["strike"]),
            quantity=int(d["quantity"]), premium=float(d["premium"]))
        for d in json.loads(legs_json)
    ]


def _legs_to_json(legs: List[Leg]) -> str:
    return json.dumps([
        {"opt_type": leg.opt_type.value, "strike": leg.strike,
         "quantity": leg.quantity, "premium": leg.premium}
        for leg in legs
    ])


def structure_mtm_rs(legs: List[Leg], lot_size: int, prem) -> Optional[float]:
    """Gross mark-to-market P&L in rupees vs entry, at current mid premiums.
    Returns None if any leg cannot be priced (do not exit on a blind mark)."""
    total_pts = 0.0
    for leg in legs:
        cur = prem(leg.opt_type, leg.strike)
        if cur is None:
            return None
        total_pts += leg.quantity * (cur - leg.premium)
    return total_pts * lot_size


def evaluate_dr_exit(row: dict, mtm_gross: Optional[float], now_ist: datetime):
    """(should_exit, reason). Target/stop are fractions of the structure's own
    max-profit / max-loss; plus a hard intraday square-off."""
    nm = now_ist.hour * 60 + now_ist.minute
    if nm >= _squareoff_min():
        return True, "squareoff"
    if mtm_gross is None:
        return False, "unpriced"
    max_profit = float(row.get("max_profit_rs") or 0.0)
    max_loss = float(row.get("max_loss_rs") or 0.0)
    if max_profit > 0 and mtm_gross >= _target_frac() * max_profit:
        return True, "target"
    if max_loss > 0 and mtm_gross <= -_stop_frac() * max_loss:
        return True, "stop"
    return False, "hold"


# ---------------------------------------------------------------------------
# storage
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS fno_dr_positions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT NOT NULL,
    kind          TEXT NOT NULL,
    legs_json     TEXT NOT NULL,
    lot_size      INTEGER NOT NULL,
    lots          INTEGER NOT NULL DEFAULT 1,
    entry_underlying REAL,
    net_premium_rs   REAL,
    max_profit_rs    REAL,
    max_loss_rs      REAL,
    entry_cost_rs    REAL,
    status        TEXT NOT NULL DEFAULT 'OPEN',
    opened_at     TEXT,
    exit_underlying  REAL,
    exit_reason   TEXT,
    gross_pnl     REAL,
    costs         REAL,
    pnl           REAL,
    closed_at     TEXT
);
"""


async def init_dr_db(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(_DDL)
        await db.commit()


async def open_structures(db_path: str, source: str = SOURCE_PAPER) -> List[dict]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM fno_dr_positions WHERE source=? AND status='OPEN'",
            (source,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def insert_structure(
    db_path: str, source: str, planned: PlannedStructure, now_ist: datetime,
) -> int:
    s = planned.structure
    cost = structure_round_trip_cost(s)
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            """INSERT INTO fno_dr_positions
               (source, kind, legs_json, lot_size, lots, entry_underlying,
                net_premium_rs, max_profit_rs, max_loss_rs, entry_cost_rs,
                status, opened_at)
               VALUES (?,?,?,?,?,?,?,?,?,?, 'OPEN', ?)""",
            (source, s.kind.value, _legs_to_json(s.legs), s.lot_size, 1,
             planned.entry_underlying, round(s.net_premium * s.lot_size, 2),
             s.max_profit_rs, s.max_loss_rs, cost, now_ist.isoformat()),
        )
        await db.commit()
        return int(cur.lastrowid)


async def close_structure(
    db_path: str, row_id: int, gross_pnl: float, costs: float,
    exit_underlying: Optional[float], reason: str, now_ist: datetime,
) -> None:
    net = round(gross_pnl - costs, 2)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """UPDATE fno_dr_positions
               SET status='CLOSED', exit_underlying=?, exit_reason=?,
                   gross_pnl=?, costs=?, pnl=?, closed_at=?
               WHERE id=? AND status='OPEN'""",
            (exit_underlying, reason, round(gross_pnl, 2), round(costs, 2),
             net, now_ist.isoformat(), row_id),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# lifecycle -- called from run_fno_tick with the tick's own snap + sig
# ---------------------------------------------------------------------------

async def manage_dr_structures(
    db_path: str, snap: ChainSnapshot, now_ist: datetime, source: str = SOURCE_PAPER,
) -> int:
    """Mark every open structure to current mids and close the ones that hit
    target / stop / square-off. Returns the number closed. Never raises."""
    closed = 0
    try:
        rows = await open_structures(db_path, source)
        if not rows:
            return 0
        prem = premium_lookup_from_snapshot(snap) if snap is not None else None
        for row in rows:
            legs = _legs_from_json(row["legs_json"])
            mtm = structure_mtm_rs(legs, int(row["lot_size"]), prem) if prem else None
            should_exit, reason = evaluate_dr_exit(row, mtm, now_ist)
            if not should_exit:
                continue
            # On a square-off we may be unpriced; book the last-known gross (0
            # if never priced) minus costs -- honest and bounded by max_loss.
            gross = mtm if mtm is not None else 0.0
            costs = float(row.get("entry_cost_rs") or 0.0)
            spot = float(snap.forward) if snap is not None and snap.forward else None
            await close_structure(db_path, int(row["id"]), gross, costs, spot, reason, now_ist)
            try:
                from performance import record_trade_close
                await record_trade_close(
                    db_path, f"DR_{row['kind']}", round(gross - costs, 2),
                    notes=f"fno_dr_exit {reason}", source=source,
                )
            except Exception as exc:
                logger.error("fno_dr_ledger_write_failed id=%s err=%s", row.get("id"), str(exc))
            logger.info(
                "fno_dr_closed id=%s kind=%s reason=%s gross=%.2f costs=%.2f net=%.2f",
                row.get("id"), row.get("kind"), reason, gross, costs, gross - costs,
            )
            closed += 1
    except Exception as exc:
        logger.error("fno_dr_manage_failed err=%s", str(exc), exc_info=True)
    return closed


async def maybe_open_dr_structure(
    db_path: str,
    snap: ChainSnapshot,
    has_directional_signal: bool,
    direction: Optional[FnoDirection],
    now_ist: datetime,
    source: str = SOURCE_PAPER,
) -> Optional[int]:
    """Open ONE structure if flat and inside the entry window. Returns the new
    row id, or None. Never raises."""
    if not _enabled():
        return None
    try:
        nm = now_ist.hour * 60 + now_ist.minute
        if not (_entry_lo_min() <= nm <= _entry_hi_min()):
            return None
        if await open_structures(db_path, source):
            return None  # one at a time
        planned = plan_structure(snap, has_directional_signal, direction, now_ist)
        if planned is None:
            return None
        await init_dr_db(db_path)
        row_id = await insert_structure(db_path, source, planned, now_ist)
        s = planned.structure
        logger.info(
            "fno_dr_opened id=%d kind=%s legs=%d max_loss=%.0f max_profit=%.0f "
            "net_premium_rs=%.0f spot=%.1f",
            row_id, s.kind.value, len(s.legs), s.max_loss_rs, s.max_profit_rs,
            s.net_premium * s.lot_size, planned.entry_underlying,
        )
        return row_id
    except Exception as exc:
        logger.error("fno_dr_open_failed err=%s", str(exc), exc_info=True)
        return None
