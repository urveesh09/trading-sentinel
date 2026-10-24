"""[O21-SC 2026-10-21] Every paper book on one standard capital.

Each book trades its own notional (F&O ₹2.5L, Momentum ₹50k, overnight
₹25k, Penny ₹1L...), so their rupee results cannot be compared, and none
answers "what would ₹2L in this book have done?". The owner's plan is to
give a proven book a standard amount (₹2L or ₹5L), then test real money
scaled down. This module replays each book's own closed trades on one
capital S, without changing any book:

  - every trade keeps the book's exposure relative to its own reference
    capital: units at S = round(book units x S / reference), whole lots or
    shares, so a trade too small for S (one NIFTY lot at ₹10k) is skipped
    and counted, not shrunk to a fraction;
  - own cash only: a trade that does not fit the sleeve's free cash is
    sized down to what fits, or skipped and counted;
  - charges are recomputed at the new size: the real F&O/equity schedules
    where entry and exit prices are stored, else the book's own charges
    with the flat ₹20-per-order part kept fixed and the rest scaled;
  - ``since`` restricts the replay to trades opened on or after a date, so
    the current version of a book (rules change often) can be scored apart
    from its history.

The P&L at S = the book's own net P&L when S equals its reference and no
trade is skipped. Results are paper and inherit each book's fill model;
scaling an equity book far above its reference assumes the same fills at a
larger size, which the output flags. Nothing here is a forecast of live
results or a promotion decision.
"""
from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Optional

import pytz
import structlog

from config import settings

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")

DEFAULT_CAPITAL = 200000.0
MIN_CAPITAL, MAX_CAPITAL = 1000.0, 10_000_000.0
FLAT_ORDER_RS = 20.0 * 1.18          # brokerage + GST per executed F&O order
EQUITY_SCALE_WARN = 2.0               # an equity book scaled beyond 2x its reference


@dataclass
class TradeRow:
    """One closed trade of a book, in the book's own units."""
    opened_at: datetime
    closed_at: datetime
    label: str
    units: int                         # lots (F&O) or shares (equity)
    unit_cash: float                   # own cash tied per unit
    net_pnl: float                     # the book's net P&L for this trade
    cost_fn: Callable[[int], float]    # round-trip charges for n units
    assumed: bool = False              # settled on an assumed price
    units_estimated: bool = False      # share count not stored; from the book's sizing cap


@dataclass
class BookSpec:
    key: str
    label: str
    kind: str                          # FNO | EQUITY
    live_path: str
    reference: Optional[float]         # None: derived from the book's peak deployment
    rows: list = field(default_factory=list)
    note: str = ""


# ---------------------------------------------------------------------------
# pure replay
# ---------------------------------------------------------------------------

def _round_units(units: int, k: float) -> int:
    return int(math.floor(units * k + 0.5 + 1e-9))


def scaled_pnl(row: TradeRow, n: int) -> float:
    """Net P&L of the same trade with n units; equals net_pnl at n = units."""
    if n == row.units:
        return row.net_pnl
    gross_per_unit = (row.net_pnl + row.cost_fn(row.units)) / row.units
    return gross_per_unit * n - row.cost_fn(n)


def peak_deployment(rows: list[TradeRow]) -> float:
    """Most cash the book itself had in open trades at one time."""
    events = []
    for row in rows:
        cash = row.units * row.unit_cash
        events.append((row.opened_at, 1, cash))
        events.append((row.closed_at, 0, -cash))
    level = peak = 0.0
    for _, _, delta in sorted(events, key=lambda e: (e[0], e[1])):
        level += delta
        peak = max(peak, level)
    return peak


def replay(rows: list[TradeRow], capital: float, reference: float) -> dict:
    """The book's trades on ``capital`` with whole units and own cash only."""
    k = capital / reference if reference > 0 else 0.0
    ordered = sorted(rows, key=lambda r: (r.opened_at, r.closed_at))
    cash = capital
    open_trades: list = []          # (closed_at, cash, pnl)
    closes: list = []               # (closed_at, pnl)
    taken = small = no_cash = resized = 0
    peak_used = 0.0
    assumed_pnl = 0.0

    def release(until: Optional[datetime]):
        nonlocal cash
        still = []
        for item in sorted(open_trades, key=lambda t: t[0]):
            if until is None or item[0] <= until:
                cash += item[1] + item[2]
                closes.append((item[0], item[2]))
            else:
                still.append(item)
        open_trades[:] = still

    for row in ordered:
        release(row.opened_at)
        n = _round_units(row.units, k)
        if n <= 0:
            small += 1
            continue
        need = n * row.unit_cash
        if need > cash + 1e-6:
            fit = int(cash // row.unit_cash) if row.unit_cash > 0 else 0
            if fit <= 0:
                no_cash += 1
                continue
            n, need = fit, fit * row.unit_cash
            resized += 1
        pnl = scaled_pnl(row, n)
        if row.assumed:
            assumed_pnl += pnl
        cash -= need
        open_trades.append((row.closed_at, need, pnl))
        taken += 1
        peak_used = max(peak_used, sum(t[1] for t in open_trades))
    release(None)
    closes.sort(key=lambda c: c[0])
    equity = peak = capital
    max_dd = 0.0
    for _, pnl in closes:
        equity += pnl
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    pnls = [p for _, p in closes]
    wins = [p for p in pnls if p > 0]
    losses = [-p for p in pnls if p <= 0]
    net = sum(pnls)
    return {
        "scale": round(k, 4), "trades_in_book": len(rows), "trades_taken": taken,
        "skipped_too_small": small, "skipped_no_cash": no_cash, "sized_down_for_cash": resized,
        "net_pnl": round(net, 2), "return_pct": round(net / capital * 100, 2) if capital else None,
        "max_drawdown": round(max_dd, 2), "max_drawdown_pct": round(max_dd / capital * 100, 2) if capital else None,
        "profit_factor": round(sum(wins) / sum(losses), 2) if losses and sum(losses) > 0 else None,
        "win_rate_pct": round(len(wins) / len(pnls) * 100, 1) if pnls else None,
        "best_trade": round(max(pnls), 2) if pnls else None,
        "worst_trade": round(min(pnls), 2) if pnls else None,
        "peak_deployed": round(peak_used, 2),
        "peak_deployed_pct": round(peak_used / capital * 100, 1) if capital else None,
        "assumed_pnl": round(assumed_pnl, 2),
        "curve": [(ts.isoformat(), round(p, 2)) for ts, p in closes],
    }


def combine_curves(curves: list[list], capital: float) -> dict:
    """An equal-split account: all sleeves' closes in time order."""
    closes = sorted((datetime.fromisoformat(ts), p) for curve in curves for ts, p in curve)
    equity = peak = capital
    max_dd = 0.0
    for _, pnl in closes:
        equity += pnl
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    net = sum(p for _, p in closes)
    return {"net_pnl": round(net, 2), "return_pct": round(net / capital * 100, 2),
            "max_drawdown": round(max_dd, 2), "max_drawdown_pct": round(max_dd / capital * 100, 2),
            "closes": len(closes)}


# ---------------------------------------------------------------------------
# loaders (read-only)
# ---------------------------------------------------------------------------

def _dt(value) -> Optional[datetime]:
    if value in (None, ""):
        return None
    text = value.decode() if isinstance(value, bytes) else str(value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.fromisoformat(text[:10])
        except ValueError:
            return None
    return parsed.astimezone(IST) if parsed.tzinfo else IST.localize(parsed)


def _num(value) -> Optional[float]:
    """A stored number; an 8-byte blob is a numpy int64 written raw (VPRPL, Aug 11)."""
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        return float(int.from_bytes(value, "little", signed=True)) if len(value) == 8 else None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _close_time(value, opened: datetime) -> Optional[datetime]:
    """A date-only exit closes at 15:30 IST that day, never before the entry."""
    text = value.decode() if isinstance(value, bytes) else str(value or "")
    if len(text) == 10:
        try:
            closed = IST.localize(datetime.fromisoformat(f"{text}T15:30:00"))
        except ValueError:
            return None
        return max(closed, opened)
    return _dt(text)


def _ro(path: str) -> Optional[sqlite3.Connection]:
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        conn.text_factory = lambda b: b.decode("utf-8", "replace")
        return conn
    except sqlite3.Error:
        return None


def _scaled_costs(total: float, units: int, orders: int) -> Callable[[int], float]:
    fixed = min(max(total, 0.0), orders * FLAT_ORDER_RS)
    variable = max(total - fixed, 0.0)
    return lambda n: fixed + variable * n / units if units else fixed


def _fno_single(conn) -> list[TradeRow]:
    from fno_costs import calc_fno_costs, options_exchange_for
    rows = []
    for (entry_time, exit_time, underlying, lots, initial_lots, lot_size, entry, exit_, pnl, costs,
         qty, initial_qty, symbol) in conn.execute(
            "SELECT entry_time, exit_time, underlying, lots, initial_lots, lot_size, entry_premium, exit_premium, "
            "pnl, costs, qty, initial_qty, tradingsymbol FROM fno_positions "
            "WHERE source='FNO_PAPER' AND status='CLOSED' AND pnl IS NOT NULL"):
        units = int(initial_lots or lots or 0)
        if units <= 0 or not lot_size or entry is None or exit_ is None:
            continue
        opened, closed = _dt(entry_time), _dt(exit_time)
        if opened is None or closed is None:
            continue
        exchange = options_exchange_for(underlying)
        partial = bool(initial_qty and qty and initial_qty != qty)
        if partial:
            cost_fn = _scaled_costs(float(costs or 0), units, 3)
        else:
            cost_fn = (lambda n, e=float(entry), x=float(exit_), ls=int(lot_size), ex=exchange:
                       calc_fno_costs(e, x, n * ls, exchange=ex))
        rows.append(TradeRow(opened, closed, str(symbol), units, float(entry) * int(lot_size),
                             float(pnl), cost_fn))
    return rows


def _fno_spreads(conn) -> list[TradeRow]:
    import json
    rows = []
    for opened_at, closed_at, kind, lots, max_loss, pnl, cash_pnl, costs, legs_json in conn.execute(
            "SELECT opened_at, closed_at, kind, lots, max_loss_rs, pnl, cash_pnl, costs, legs_json "
            "FROM fno_dr_positions WHERE status='CLOSED' AND pnl IS NOT NULL"):
        units = int(lots or 0)
        opened, closed = _dt(opened_at), _dt(closed_at)
        if units <= 0 or opened is None or closed is None or not max_loss:
            continue
        try:
            legs = len(json.loads(legs_json or "[]")) or 2
        except ValueError:
            legs = 2
        net = float(cash_pnl if cash_pnl is not None else pnl)
        rows.append(TradeRow(opened, closed, str(kind), units, float(max_loss) / units, net,
                             _scaled_costs(float(costs or 0), units, 2 * legs)))
    return rows


def _expiry(conn) -> list[TradeRow]:
    rows = []
    for day, play, entry_ts, lots, lot_size, entry, net, assumed, costs, max_loss, side, width, events in conn.execute(
            "SELECT day, play, entry_ts, lots, lot_size, entry_price, net_pnl, assumed_pnl, costs, max_loss, "
            "side, width, events FROM expiry_paper_positions WHERE play IN ('A','B','C') "
            "AND status IN ('CLOSED','SETTLED_ASSUMED')"):
        units = int(lots or 0)
        opened = _dt(entry_ts)
        if units <= 0 or opened is None or not lot_size:
            continue
        closed = IST.localize(datetime.fromisoformat(f"{day}T15:40:00"))    # [O24-MC] F&O closes at 15:40
        spread = width is not None
        unit_cash = (float(max_loss) / units if spread and max_loss else float(entry or 0) * int(lot_size))
        if unit_cash <= 0:
            continue
        orders = (4 if spread else 2) + (str(events or "").count("BANK") if events else 0)
        total = float(net or 0) + float(assumed or 0)
        rows.append(TradeRow(opened, closed, f"{day} {play}", units, unit_cash, total,
                             _scaled_costs(float(costs or 0), units, orders), assumed=assumed is not None))
    return rows


def _overnight(conn) -> list[TradeRow]:
    from penny_risk import calc_penny_costs
    rows = []
    for ticker, entry_ts, exit_date, entry, shares, exit_, net in conn.execute(
            "SELECT ticker, entry_ts, exit_date, entry_price, shares, exit_price, net_pnl "
            "FROM edge_overnight_paper_trades WHERE net_pnl IS NOT NULL AND exit_price IS NOT NULL"):
        opened = _dt(entry_ts)
        if opened is None or not shares or not entry or not exit_date:
            continue
        closed = IST.localize(datetime.fromisoformat(f"{exit_date}T09:20:00"))
        rows.append(TradeRow(opened, closed, str(ticker), int(shares), float(entry), float(net),
                             lambda n, e=float(entry), x=float(exit_): calc_penny_costs(e, x, n, is_intraday=False)))
    return rows


def _positions(conn, source: str, per_stock_cap: Optional[float] = None) -> list[TradeRow]:
    from penny_risk import calc_penny_costs
    rows = []
    for ticker, entry_date, exit_date, entry, exit_, shares, pnl, product in conn.execute(
            "SELECT ticker, entry_date, exit_date, entry_price, exit_price, shares, realised_pnl, product_type "
            "FROM positions WHERE source=? AND (status LIKE 'CLOSED%' OR status='STOPPED_OUT') "
            "AND realised_pnl IS NOT NULL", (source,)):
        opened = _dt(entry_date)
        entry, exit_, shares, pnl = _num(entry), _num(exit_), _num(shares), _num(pnl)
        if opened is None or not entry or exit_ is None or pnl is None:
            continue
        estimated = False
        if not shares and per_stock_cap:
            # Penny rows closed since September store shares=0. The book
            # sizes to its per-stock cap, so the count is that cap's shares.
            shares, estimated = max(1, int(per_stock_cap // entry)), True
        if not shares:
            continue
        closed = _close_time(exit_date, opened)
        if closed is None:
            continue
        intraday = str(product or "MIS").upper() != "CNC"
        rows.append(TradeRow(opened, closed, str(ticker), int(shares), entry, pnl,
                             lambda n, e=entry, x=exit_, i=intraday: calc_penny_costs(e, x, n, is_intraday=i),
                             units_estimated=estimated))
    return rows


def _ledger_closes(conn, source: str) -> int:
    try:
        return int(conn.execute("SELECT COUNT(*) FROM bankroll_ledger WHERE source=? AND event_type='TRADE_CLOSED'",
                                (source,)).fetchone()[0])
    except sqlite3.Error:
        return 0


def load_books(db_path: str) -> list[BookSpec]:
    books = [
        BookSpec("fno_single", "F&O single option", "FNO", "NFO only, behind the go-live bar",
                 float(settings.FNO_PAPER_BANKROLL)),
        BookSpec("fno_spreads", "F&O defined-risk spreads", "FNO", "none (paper only)",
                 float(settings.FNO_PAPER_BANKROLL)),
        # The expiry book has no pool: it risks EXPIRY_PAPER_BUDGET per play
        # per day. Read through the F&O book's own rule (risk FNO_MAX_RISK_PCT
        # of the pool per trade), three main plays need 3 x 2,500 / 2% = ₹3.75L.
        # Its peak cash in open trades (~₹9k) would scale it 22x at ₹2L, far
        # past what expiry-day option depth or its risk design supports.
        BookSpec("expiry", "Expiry-day book (A/B/C)", "FNO", "none (paper only)",
                 3 * float(settings.EXPIRY_PAPER_BUDGET) / float(settings.FNO_MAX_RISK_PCT),
                 note="risk-budgeted, no pool: reference = 3 plays x ₹2,500 budget at the F&O 2% risk rule"),
        BookSpec("overnight", "EDGE overnight", "EQUITY", "none (paper only)",
                 float(settings.EDGE_OVERNIGHT_PAPER_BANKROLL)),
        BookSpec("momentum", "Momentum (paper)", "EQUITY", "manual Telegram only",
                 float(settings.MOMENTUM_PAPER_BANKROLL)),
        BookSpec("penny", "Classic Penny (paper)", "EQUITY", "yes, switched off",
                 float(settings.PENNY_PAPER_BANKROLL)),
        BookSpec("edge_morning", "EDGE morning (paper)", "EQUITY", "yes, switched off",
                 float(settings.PENNY_EDGE_PAPER_BANKROLL)),
    ]
    main = _ro(db_path)
    side = {"expiry": _ro(f"{db_path}.expiry-paper.db"), "overnight": _ro(f"{db_path}.edge-overnight-paper.db")}
    loaders = {
        "fno_single": lambda: _fno_single(main), "fno_spreads": lambda: _fno_spreads(main),
        "expiry": lambda: _expiry(side["expiry"]), "overnight": lambda: _overnight(side["overnight"]),
        "momentum": lambda: _positions(main, "MOMENTUM_PAPER"),
        "penny": lambda: _positions(main, "PENNY_PAPER", float(settings.PENNY_PER_STOCK_CAP)),
        "edge_morning": lambda: _positions(main, "EDGE_PAPER"),
    }
    for book in books:
        try:
            book.rows = loaders[book.key]()
        except (sqlite3.Error, AttributeError, TypeError, ValueError) as exc:
            book.note = (book.note + "; " if book.note else "") + f"unreadable ({type(exc).__name__})"
            book.rows = []
    if main is not None:
        for key, source in (("momentum", "MOMENTUM_PAPER"), ("penny", "PENNY_PAPER"), ("edge_morning", "EDGE_PAPER")):
            ledger = _ledger_closes(main, source)
            book = next(b for b in books if b.key == key)
            if ledger and ledger != len(book.rows):
                book.note = (book.note + "; " if book.note else "") + (
                    f"positions hold {len(book.rows)} of the ledger's {ledger} closes; "
                    "the replay covers those rows only")
            estimated = sum(1 for r in book.rows if r.units_estimated)
            if estimated:
                book.note = (book.note + "; " if book.note else "") + (
                    f"{estimated} row(s) stored no share count after close; sized from the per-stock cap")
    for conn in [main, *side.values()]:
        if conn is not None:
            conn.close()
    return books


async def load_standard_capital(db_path: str, *, capital: Optional[float] = None,
                                since: Optional[str] = None) -> dict:
    import asyncio
    capital = float(capital if capital is not None else getattr(settings, "STANDARD_CAPITAL_INR", DEFAULT_CAPITAL))
    if not (MIN_CAPITAL <= capital <= MAX_CAPITAL) or not math.isfinite(capital):
        raise ValueError(f"capital must be between {MIN_CAPITAL:,.0f} and {MAX_CAPITAL:,.0f}")
    since_dt = None
    if since:
        try:
            since_dt = IST.localize(datetime.fromisoformat(since[:10]))
        except ValueError as exc:
            raise ValueError("since must be YYYY-MM-DD") from exc
    books = await asyncio.to_thread(load_books, db_path)
    return standard_capital_view(books, capital=capital, since=since_dt, now=datetime.now(IST))


def standard_capital_view(books: list[BookSpec], *, capital: float, since: Optional[datetime],
                          now: datetime) -> dict:
    out = []
    curves = []
    active = [b for b in books if any(since is None or r.opened_at >= since for r in b.rows)]
    split = capital / len(active) if active else capital
    for book in books:
        rows = [r for r in book.rows if since is None or r.opened_at >= since]
        reference = book.reference or (math.ceil(peak_deployment(book.rows) / 1000.0) * 1000.0 if book.rows else 0.0)
        item = {"key": book.key, "label": book.label, "kind": book.kind, "live_path": book.live_path,
                "reference_capital": round(reference, 2), "note": book.note, "flags": []}
        if not rows or reference <= 0:
            item.update(trades_in_book=0, trades_taken=0, net_pnl=None)
            out.append(item)
            continue
        result = replay(rows, capital, reference)
        last30 = now - timedelta(days=30)
        recent = [r for r in rows if r.opened_at >= last30]
        result["last_30d_pnl"] = replay(recent, capital, reference)["net_pnl"] if recent else 0.0
        result["first_trade"] = min(r.opened_at for r in rows).date().isoformat()
        result["last_trade"] = max(r.closed_at for r in rows).date().isoformat()
        result["book_own_net_pnl"] = round(sum(r.net_pnl for r in rows), 2)
        at_reference = replay(rows, reference, reference)["net_pnl"]
        if abs(at_reference - result["book_own_net_pnl"]) > 1.0:
            item["flags"].append(
                f"at its own ₹{reference:,.0f} the own-cash replay gives ₹{at_reference:,.0f} against the "
                f"book's ₹{result['book_own_net_pnl']:,.0f}: the book held more than its pool at once")
        if book.kind == "EQUITY" and result["scale"] > EQUITY_SCALE_WARN:
            item["flags"].append(f"scaled x{result['scale']:.1f}: same fills assumed at a bigger size; "
                                 "liquidity not verified")
        if result["skipped_too_small"]:
            item["flags"].append(f"{result['skipped_too_small']} trade(s) too small for this capital")
        if result["assumed_pnl"]:
            item["flags"].append(f"₹{result['assumed_pnl']:,.0f} of the P&L settled on assumed prices")
        curve = result.pop("curve")
        item.update(result)
        item["curve"] = curve[-400:]
        out.append(item)
        if book in active:
            curves.append(replay(rows, split, reference)["curve"])
    combined = combine_curves(curves, capital) if curves else None
    if combined is not None:
        combined["books"] = len(curves)
        combined["per_book"] = round(split, 2)
    return {
        "capital": capital, "since": since.date().isoformat() if since else None,
        "books": out, "equal_split": combined,
        "method": {
            # [A22-E2] What this replay is and is not (shown first on the page).
            "scope": "scales each book's closed paper trades; open positions are not included; "
                     "not a whole-portfolio replay and not an exit experiment",
            "units": "round(book units x capital / reference capital); 0 = too small, skipped",
            "cash": "own cash only; a trade that does not fit is sized down or skipped",
            "charges": "recomputed at the new size; flat ₹20/order kept fixed where only totals are stored",
            "source": "each book's own closed paper trades, read-only",
        },
        "paper_only": True, "forecast": False, "as_of": now.isoformat(),
    }
