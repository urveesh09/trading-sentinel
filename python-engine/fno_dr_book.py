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
from datetime import date, datetime, timezone
from typing import Callable, List, Optional

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
from fno_models import Contract, ContractQuote, FnoDirection, Leg, OptionType

logger = structlog.get_logger()

SOURCE_PAPER = "FNO_PAPER"


# ---------------------------------------------------------------------------
# config accessors (getattr defaults -- no config.py edit required to run)
# ---------------------------------------------------------------------------

def _enabled() -> bool:
    return bool(getattr(settings, "FNO_DR_PAPER_ENABLED", True))


def _strike_step() -> float:
    return float(getattr(settings, "FNO_DR_STRIKE_STEP", getattr(settings, "FNO_STRIKE_STEP", 50.0)))


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
    # Immutable, selected-contract evidence.  The pricing engine deliberately
    # does not infer this later from a same-strike quote: expiry/token/lot can
    # change while a paper structure is open.
    contract_legs: tuple[dict, ...]


def _contract_leg_snapshot(leg: Leg, quote: Optional[ContractQuote]) -> Optional[dict]:
    """Return bounded, exact identity for one selected option leg.

    ``Contract`` intentionally has no exchange field because the F&O book owns
    one segment.  Defined-risk paper structures are NFO-only today, so retain
    that fact explicitly rather than leaving downstream audit code to guess.
    """
    contract = getattr(quote, "contract", None)
    if contract is None:
        return None
    underlying = str(getattr(contract, "name", "")).upper()
    symbol = str(getattr(contract, "tradingsymbol", "")).upper()
    try:
        expiry = contract.expiry.isoformat()
        token = int(contract.token)
        lot_size = int(contract.lot_size)
        strike = float(contract.strike)
    except (AttributeError, TypeError, ValueError):
        return None
    if (
        not underlying or len(underlying) > 64 or not symbol or len(symbol) > 128
        or token <= 0 or lot_size <= 0 or strike != float(leg.strike)
        or str(getattr(contract, "instrument_type", "")).upper() != leg.opt_type.value
    ):
        return None
    return {
        "opt_type": leg.opt_type.value,
        "strike": float(leg.strike),
        "quantity": int(leg.quantity),
        "premium": float(leg.premium),
        "contract": {
            "underlying": underlying,
            "expiry": expiry,
            "exchange": "NFO",
            "token": token,
            "tradingsymbol": symbol,
            "lot_size": lot_size,
            "instrument_type": leg.opt_type.value,
        },
    }


def _selected_contract_legs(snap: ChainSnapshot, legs: List[Leg]) -> Optional[tuple[dict, ...]]:
    """Bind every priced leg to one exact, same-expiry, same-lot contract."""
    bound: list[dict] = []
    lots: set[int] = set()
    expiries: set[str] = set()
    for leg in legs:
        item = _contract_leg_snapshot(leg, snap.quote(leg.strike, leg.opt_type))
        if item is None:
            return None
        bound.append(item)
        lots.add(int(item["contract"]["lot_size"]))
        expiries.add(str(item["contract"]["expiry"]))
    if len(lots) != 1 or len(expiries) != 1:
        return None
    # The snapshot expiry is the selected option expiry, not merely a display
    # field.  Refuse a mismatched adapter rather than persisting an ambiguous
    # lifecycle that later code could mistakenly value.
    if len(bound) == 0 or next(iter(expiries)) != snap.expiry.isoformat():
        return None
    return tuple(bound)


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
    # Select the structure geometry first, then bind it to the exact quoted
    # contracts and rebuild it with their lot size.  A global fallback lot can
    # be stale across SEBI revisions and must never determine paper cash.
    provisional_lot = 1

    if kind == StructureKind.DEBIT_SPREAD:
        if direction is None:
            return None
        structure = build_debit_spread(direction, atm, step, _debit_width(), prem, provisional_lot)
    else:
        structure = build_iron_condor(atm, step, _condor_offset(), _condor_wing(), prem, provisional_lot)

    if structure is None or not structure.is_defined_risk:
        logger.info(
            "fno_dr_stand_aside reason=unpriceable_or_invalid_structure kind=%s",
            kind.value,
        )
        return None
    contract_legs = _selected_contract_legs(snap, structure.legs)
    if contract_legs is None:
        logger.info("fno_dr_stand_aside reason=missing_or_inconsistent_contract_identity")
        return None
    lot = int(contract_legs[0]["contract"]["lot_size"])
    if kind == StructureKind.DEBIT_SPREAD:
        structure = build_debit_spread(direction, atm, step, _debit_width(), prem, lot)
    else:
        structure = build_iron_condor(atm, step, _condor_offset(), _condor_wing(), prem, lot)
    if structure is None or not structure.is_defined_risk:
        return None
    if structure.max_loss_rs > _max_loss_ceiling():
        logger.info(
            "fno_dr_skip reason=max_loss_over_ceiling kind=%s max_loss=%.0f ceiling=%.0f",
            kind.value, structure.max_loss_rs, _max_loss_ceiling(),
        )
        return None
    return PlannedStructure(
        structure=structure, entry_underlying=float(snap.forward), contract_legs=contract_legs,
    )


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


def _bound_legs_to_json(contract_legs: tuple[dict, ...]) -> str:
    """Serialize one bounded, immutable contract identity packet."""
    raw = json.dumps(list(contract_legs), separators=(",", ":"), sort_keys=True)
    if len(raw) > 4096:
        raise ValueError("defined-risk contract identity exceeds retention bound")
    return raw


def _bound_legs_from_row(row: dict) -> Optional[list[dict]]:
    """Return only fully valid v1 identities; legacy rows stay unverified."""
    try:
        raw = row["legs_json"]
        if not isinstance(raw, str) or len(raw) > 4096:
            return None
        entries = json.loads(raw)
    except (KeyError, TypeError, ValueError):
        return None
    if not isinstance(entries, list) or not entries:
        return None
    parsed: list[dict] = []
    for item in entries:
        try:
            if not isinstance(item, dict) or not isinstance(item.get("contract"), dict):
                return None
            contract = item["contract"]
            opt_type = OptionType(item["opt_type"])
            strike = float(item["strike"])
            quantity = int(item["quantity"])
            premium = float(item["premium"])
            expiry = date.fromisoformat(str(contract["expiry"]))
            token = int(contract["token"])
            lot_size = int(contract["lot_size"])
            underlying = str(contract["underlying"]).upper()
            symbol = str(contract["tradingsymbol"]).upper()
        except (KeyError, TypeError, ValueError):
            return None
        if (
            not math.isfinite(strike) or not math.isfinite(premium) or premium < 0
            or quantity == 0 or token <= 0 or lot_size <= 0 or not underlying
            or len(underlying) > 64 or not symbol or len(symbol) > 128
            or contract.get("exchange") != "NFO"
            or str(contract.get("instrument_type", "")).upper() != opt_type.value
            or not isinstance(expiry, date)
        ):
            return None
        parsed.append(item)
    return parsed


def _matching_quote(snap: ChainSnapshot, stored: dict) -> Optional[ContractQuote]:
    quote = snap.quote(float(stored["strike"]), OptionType(stored["opt_type"]))
    contract = getattr(quote, "contract", None)
    expected = stored["contract"]
    if contract is None:
        return None
    expiry = getattr(contract, "expiry", None)
    if (
        int(getattr(contract, "token", 0)) != int(expected["token"])
        or str(getattr(contract, "tradingsymbol", "")).upper() != expected["tradingsymbol"]
        or str(getattr(contract, "name", "")).upper() != expected["underlying"]
        or not isinstance(expiry, date) or expiry.isoformat() != expected["expiry"]
        or int(getattr(contract, "lot_size", 0)) != int(expected["lot_size"])
        or float(getattr(contract, "strike", 0.0)) != float(stored["strike"])
        or str(getattr(contract, "instrument_type", "")).upper() != stored["opt_type"]
    ):
        return None
    return quote


def _bound_price_functions(row: dict, snap: Optional[ChainSnapshot]) -> tuple[Optional[Callable], Optional[Callable], str]:
    """Return model-mid/executable-exit lookups only for exact stored legs."""
    if snap is None:
        return None, None, "snapshot_unavailable"
    stored = _bound_legs_from_row(row)
    if stored is None:
        return None, None, "legacy_or_malformed_contract_identity"
    quotes: dict[tuple[float, str], ContractQuote] = {}
    for item in stored:
        quote = _matching_quote(snap, item)
        if quote is None:
            return None, None, "stored_contract_not_in_snapshot"
        quotes[(float(item["strike"]), str(item["opt_type"]))] = quote

    def mid(opt: OptionType, strike: float) -> Optional[float]:
        quote = quotes.get((float(strike), opt.value))
        return float(quote.mid) if quote is not None and math.isfinite(quote.mid) and quote.mid > 0 else None

    def executable(opt: OptionType, strike: float, quantity: int) -> Optional[float]:
        quote = quotes.get((float(strike), opt.value))
        if quote is None:
            return None
        price = quote.bid if quantity > 0 else quote.ask
        return float(price) if price and math.isfinite(price) and price > 0 else None
    return mid, executable, "ok"


def exact_open_leg_tokens(rows: List[dict]) -> list[int]:
    """Return only validated retained leg tokens for active DR management."""
    tokens: set[int] = set()
    for row in rows:
        bound = _bound_legs_from_row(row)
        if bound is None:
            return []
        tokens.update(int(item["contract"]["token"]) for item in bound)
    return sorted(tokens)


def exact_leg_snapshot_from_quotes(
    rows: List[dict], raw_quotes: dict, now_ist: datetime, forward: Optional[float],
) -> Optional[ChainSnapshot]:
    """Build a valuation snapshot only from the persisted contracts.

    This deliberately refuses missing/mismatched identities.  It prevents a
    nearest-expiry/ATM reconstruction from valuing an open spread after an
    expiry rollover or a large forward move.
    """
    quotes = {}
    expiry = None
    lot_size = None
    for row in rows:
        bound = _bound_legs_from_row(row)
        if bound is None:
            return None
        for item in bound:
            identity = item["contract"]
            token = int(identity["token"])
            raw = raw_quotes.get(token)
            if not isinstance(raw, dict):
                return None
            if raw.get("instrument_token") not in (None, token, str(token)):
                return None
            try:
                contract = Contract(
                    token=token, tradingsymbol=identity["tradingsymbol"],
                    name=identity["underlying"], expiry=date.fromisoformat(identity["expiry"]),
                    strike=float(item["strike"]), instrument_type=identity["instrument_type"],
                    lot_size=int(identity["lot_size"]),
                )
            except (KeyError, TypeError, ValueError):
                return None
            depth = raw.get("depth") or {}
            buys, sells = depth.get("buy") or [], depth.get("sell") or []
            bid = float(buys[0].get("price") or 0.0) if buys else 0.0
            ask = float(sells[0].get("price") or 0.0) if sells else 0.0
            quotes[(contract.strike, contract.instrument_type)] = ContractQuote(
                contract=contract, bid=bid, ask=ask, ltp=float(raw.get("last_price") or 0.0),
            )
            if expiry is None:
                expiry, lot_size = contract.expiry, contract.lot_size
            elif expiry != contract.expiry or lot_size != contract.lot_size:
                return None
    if not quotes or expiry is None or lot_size is None:
        return None
    return ChainSnapshot(
        taken_at=now_ist, expiry=expiry, forward=float(forward or 0.0),
        parity_forward=None, lot_size=lot_size, fut_quote=None, quotes=quotes,
        requested_tokens=tuple(sorted(int(quote.contract.token) for quote in quotes.values())),
        received_tokens=tuple(sorted(int(raw) for raw in raw_quotes)),
    )


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


def structure_executable_pnl_rs(legs: List[Leg], lot_size: int, exit_prem) -> Optional[float]:
    """Cash P&L at sell-bid/buy-ask, separate from the mid valuation."""
    total_pts = 0.0
    for leg in legs:
        current = exit_prem(leg.opt_type, leg.strike, leg.quantity)
        if current is None:
            return None
        total_pts += leg.quantity * (current - leg.premium)
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
    ,model_gross_pnl REAL
    ,model_pnl       REAL
    ,cash_gross_pnl  REAL
    ,cash_pnl        REAL
    ,pricing_policy  TEXT
    ,settlement_state TEXT NOT NULL DEFAULT 'OPEN'
    ,unresolved_reason TEXT
    ,unresolved_at TEXT
);
"""


# [F0-R1 2026-10-03] Structural loss and the frozen entry fee reserve are the
# structure's shared worst-case cash until its terminal close. No writer
# updates them; once populated they cannot be rewritten.
_DR_RISK_EVIDENCE_IMMUTABLE_DDL = """
CREATE TRIGGER IF NOT EXISTS fno_dr_positions_risk_evidence_immutable
BEFORE UPDATE OF max_loss_rs, entry_cost_rs
ON fno_dr_positions
FOR EACH ROW WHEN
    (OLD.max_loss_rs IS NOT NULL AND NEW.max_loss_rs IS NOT OLD.max_loss_rs)
    OR (OLD.entry_cost_rs IS NOT NULL AND NEW.entry_cost_rs IS NOT OLD.entry_cost_rs)
BEGIN
    SELECT RAISE(ABORT, 'fno defined-risk exposure evidence is immutable');
END
"""


async def init_dr_db(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(_DDL)
        await db.execute(_DR_RISK_EVIDENCE_IMMUTABLE_DDL)
        # Additive migration: legacy positions never gain guessed contract
        # identity or valuation.  They remain readable and explicitly
        # unverified by the report/management path.
        for column, ddl in (
            ("model_gross_pnl", "REAL"), ("model_pnl", "REAL"),
            ("cash_gross_pnl", "REAL"), ("cash_pnl", "REAL"),
            ("pricing_policy", "TEXT"), ("settlement_state", "TEXT NOT NULL DEFAULT 'OPEN'"),
            ("unresolved_reason", "TEXT"), ("unresolved_at", "TEXT"),
        ):
            try:
                await db.execute(f"ALTER TABLE fno_dr_positions ADD COLUMN {column} {ddl}")
            except aiosqlite.OperationalError:
                pass
        await db.commit()


async def open_structures(db_path: str, source: str = SOURCE_PAPER) -> List[dict]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM fno_dr_positions WHERE source=? AND status IN ('OPEN','UNRESOLVED')",
            (source,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def insert_structure(
    db_path: str, source: str, planned: PlannedStructure, now_ist: datetime,
    *, reservation_key: Optional[str] = None,
) -> int:
    s = planned.structure
    cost = structure_round_trip_cost(s)
    async with aiosqlite.connect(db_path) as db:
        if reservation_key:
            await db.execute("BEGIN IMMEDIATE")
        cur = await db.execute(
            """INSERT INTO fno_dr_positions
               (source, kind, legs_json, lot_size, lots, entry_underlying,
                net_premium_rs, max_profit_rs, max_loss_rs, entry_cost_rs,
                status, opened_at)
               VALUES (?,?,?,?,?,?,?,?,?,?, 'OPEN', ?)""",
            (source, s.kind.value, _bound_legs_to_json(planned.contract_legs), s.lot_size, 1,
             planned.entry_underlying, round(s.net_premium * s.lot_size, 2),
             s.max_profit_rs, s.max_loss_rs, cost, now_ist.isoformat()),
        )
        row_id = int(cur.lastrowid)
        if reservation_key:
            from fno_shared_risk import consume_shared_fno_risk_reservation_in_transaction
            consumed = await consume_shared_fno_risk_reservation_in_transaction(
                db, reservation_key=reservation_key, source=source,
                book="DEFINED_RISK", position_ref=f"fno_dr_position:{row_id}",
                resolved_at=now_ist,
            )
            if not consumed:
                await db.rollback()
                raise RuntimeError("shared_risk_reservation_not_consumed")
        await db.commit()
        return row_id


async def _mark_unresolved(
    db_path: str, row_id: int, reason: str, now_ist: datetime,
) -> None:
    """Retain an unpriced hard-flat exposure; it is never available capital."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """UPDATE fno_dr_positions SET status='UNRESOLVED', settlement_state='UNRESOLVED',
               unresolved_reason=?, unresolved_at=?, exit_reason=?
               WHERE id=? AND status IN ('OPEN', 'UNRESOLVED')""",
            (reason[:120], now_ist.isoformat(), "squareoff_unpriced", row_id),
        )
        await db.commit()


async def _settle_structure_atomically(
    db_path: str, row: dict, model_gross: float, cash_gross: float,
    costs: float, exit_underlying: Optional[float], reason: str, now_ist: datetime,
) -> bool:
    """Commit one exact close and one ledger cash event, or neither.

    The ledger is cash truth.  ``gross_pnl``/``pnl`` retain the new *versioned*
    executable cash basis, while model-mid values are retained in their own
    columns for comparable paper research.
    """
    from performance import allocation_for_source, init_ledger

    await init_dr_db(db_path)
    await init_ledger(db_path)
    source = str(row["source"])
    origin_ref = f"fno_dr_structure:{int(row['id'])}"
    cash_net = round(cash_gross - costs, 2)
    model_net = round(model_gross - costs, 2)
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            db.row_factory = aiosqlite.Row
            current = await (await db.execute(
                "SELECT status FROM fno_dr_positions WHERE id=?", (int(row["id"]),)
            )).fetchone()
            if current is None or current["status"] == "CLOSED":
                await db.rollback()
                return False
            before_row = await (await db.execute(
                "SELECT COALESCE(SUM(pnl), 0.0) FROM bankroll_ledger WHERE source=?", (source,)
            )).fetchone()
            before = float(allocation_for_source(source)) + float(before_row[0] or 0.0)
            after = before + cash_net
            await db.execute(
                """INSERT INTO bankroll_ledger
                   (timestamp,event_type,ticker,pnl,bankroll_before,bankroll_after,source,notes,origin_ref,settlement_generation)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (datetime.now(timezone.utc).isoformat(), "TRADE_CLOSED", f"DR_{row['kind']}",
                 cash_net, before, after, source, f"fno_dr_exit {reason}", origin_ref, 1),
            )
            updated = await db.execute(
                """UPDATE fno_dr_positions SET status='CLOSED', settlement_state='SETTLED',
                   exit_underlying=?, exit_reason=?, gross_pnl=?, costs=?, pnl=?, closed_at=?,
                   model_gross_pnl=?, model_pnl=?, cash_gross_pnl=?, cash_pnl=?,
                   pricing_policy='ENTRY_MID_EXIT_BID_ASK_V1', unresolved_reason=NULL, unresolved_at=NULL
                   WHERE id=? AND status IN ('OPEN','UNRESOLVED')""",
                (exit_underlying, reason, round(cash_gross, 2), round(costs, 2), cash_net,
                 now_ist.isoformat(), round(model_gross, 2), model_net, round(cash_gross, 2),
                 cash_net, int(row["id"])),
            )
            if updated.rowcount != 1:
                await db.rollback()
                return False
            await db.commit()
            return True
    except Exception as exc:
        logger.error("fno_dr_atomic_settlement_failed id=%s err=%s", row.get("id"), str(exc))
        return False


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
        for row in rows:
            legs = _legs_from_json(row["legs_json"])
            mid_lookup, executable_lookup, price_state = _bound_price_functions(row, snap)
            mtm = structure_mtm_rs(legs, int(row["lot_size"]), mid_lookup) if mid_lookup else None
            should_exit, reason = evaluate_dr_exit(row, mtm, now_ist)
            if not should_exit:
                continue
            cash_gross = structure_executable_pnl_rs(legs, int(row["lot_size"]), executable_lookup) if executable_lookup else None
            if mtm is None or cash_gross is None:
                if reason == "squareoff":
                    await _mark_unresolved(db_path, int(row["id"]), price_state, now_ist)
                    logger.warning("fno_dr_unresolved id=%s reason=%s", row.get("id"), price_state)
                continue
            costs = float(row.get("entry_cost_rs") or 0.0)
            spot = float(snap.forward) if snap is not None and snap.forward else None
            settled = await _settle_structure_atomically(
                db_path, row, mtm, cash_gross, costs, spot, reason, now_ist,
            )
            if not settled:
                continue
            logger.info(
                "fno_dr_closed id=%s kind=%s reason=%s model_gross=%.2f cash_gross=%.2f costs=%.2f cash_net=%.2f",
                row.get("id"), row.get("kind"), reason, mtm, cash_gross, costs, cash_gross - costs,
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
    *, action_clock: Optional[Callable[[], datetime]] = None,
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
        await init_dr_db(db_path)
        if action_clock is not None:
            now_ist = action_clock()
            nm = now_ist.hour * 60 + now_ist.minute
            if not (_entry_lo_min() <= nm <= _entry_hi_min()):
                return None
            if not 0 <= snap.age_sec(now_ist) <= settings.FNO_MAX_CHAIN_AGE_SEC:
                logger.info("fno_dr_entry_skipped reason=chain_freshness")
                return None
        planned = plan_structure(snap, has_directional_signal, direction, now_ist)
        if planned is None:
            return None
        if action_clock is not None:
            for leg in planned.structure.legs:
                quote = snap.quote(leg.strike, leg.opt_type)
                if (quote is None or quote.last_trade_time is None
                        or not 0 <= (now_ist - quote.last_trade_time).total_seconds()
                        <= settings.FNO_MAX_QUOTE_AGE_SEC):
                    logger.info("fno_dr_entry_skipped reason=quote_freshness")
                    return None
        # F0-B uses the same fee-inclusive catastrophe reservation as the
        # directional book.  Initialise only durable local schemas; no quote,
        # order, message or exit path is touched here.
        from fno_shared_risk import (
            init_shared_fno_risk_db, policy_from_settings,
            reserve_shared_fno_risk, shared_fno_entry_policy,
        )
        from fno_positions import init_fno_positions_db
        from performance import init_ledger
        await init_ledger(db_path)
        await init_fno_positions_db(db_path)
        await init_shared_fno_risk_db(db_path)
        shared_policy = policy_from_settings()
        shared_decision = await shared_fno_entry_policy(
            db_path, source=source, pool_rs=float(settings.FNO_PAPER_BANKROLL),
            today_ist=now_ist.date(), policy=shared_policy,
        )
        if not shared_decision.allowed:
            logger.warning("fno_dr_entry_skipped reason=%s", shared_decision.reason)
            return None
        s = planned.structure
        reservation_key = "dr:%s:%s:%s" % (
            source, now_ist.isoformat(),
            ",".join(str(leg["contract"]["token"]) for leg in planned.contract_legs),
        )
        admission = await reserve_shared_fno_risk(
            db_path, source=source, pool_rs=float(settings.FNO_PAPER_BANKROLL),
            reservation_key=reservation_key, book="DEFINED_RISK",
            worst_case_cash_rs=s.max_loss_rs + structure_round_trip_cost(s),
            entry_day_ist=now_ist.date(), policy=shared_policy,
        )
        if not admission.allowed:
            logger.warning("fno_dr_entry_skipped reason=%s", admission.reason)
            return None
        row_id = await insert_structure(
            db_path, source, planned, now_ist, reservation_key=reservation_key,
        )
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
