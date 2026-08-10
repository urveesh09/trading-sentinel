"""Source-isolated performance accounting and ledger reconciliation.

The bankroll ledger remains cash truth. Position stores are an independent
observation used to detect missing or duplicate close accounting; they never
replace ledger equity. Missing schemas or incomplete historical rows are
reported as unavailable rather than converted into flattering zeroes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

import aiosqlite

from config import settings
from performance import _division_registry


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(float(value), digits)


def _analytics_registry() -> list[tuple]:
    """Return mode-stable sources; never relabel historical cash by a flag.

    The legacy registry presents classic Penny as one dynamically-labelled
    division. Analytics cannot do that safely: `PENNY` and `PENNY_PAPER` are
    distinct registered ledger allocations, and historical cash must retain a
    stable real/simulated meaning if the environment switch changes.
    """
    # The shared registry now exposes both classic Penny books explicitly;
    # analytics no longer needs to reinterpret a mode-dependent row.
    return list(_division_registry())


def _table_columns(rows: Iterable[Any]) -> set[str]:
    return {str(row[1]) for row in rows}


async def _columns(db: aiosqlite.Connection, table: str) -> set[str] | None:
    try:
        rows = await (await db.execute(f"PRAGMA table_info({table})")).fetchall()
    except Exception:
        return None
    return _table_columns(rows) or None


def _trade_statistics(values: list[float]) -> dict:
    """Metrics whose denominator is a closed cash-ledger trade."""
    if not values:
        return {
            "wins": None, "losses": None, "breakeven": None,
            "win_rate": None, "profit_factor": None,
            "net_expectancy": None, "current_losing_streak": None,
            "max_losing_streak": None,
        }
    wins = [v for v in values if v > 0]
    losses = [v for v in values if v < 0]
    breakeven = len(values) - len(wins) - len(losses)
    decided = len(wins) + len(losses)
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    current_streak = 0
    for value in reversed(values):
        if value < 0:
            current_streak += 1
        else:
            break
    max_streak = streak = 0
    for value in values:
        streak = streak + 1 if value < 0 else 0
        max_streak = max(max_streak, streak)
    return {
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": breakeven,
        "win_rate": _round(len(wins) / decided, 6) if decided else None,
        # No losses is an undefined/infinite ratio, not zero.
        "profit_factor": _round(gross_profit / gross_loss, 6)
        if gross_loss > 0 else None,
        "net_expectancy": _round(sum(values) / len(values), 4),
        "current_losing_streak": current_streak,
        "max_losing_streak": max_streak,
    }


def _drawdown(all_events: list[float], allocation: float) -> dict:
    if not all_events:
        return {
            "max_drawdown": None, "max_drawdown_pct": None,
            "current_drawdown": None, "current_drawdown_pct": None,
        }
    equity = float(allocation)
    peak = equity
    max_amount = 0.0
    max_pct = 0.0
    for pnl in all_events:
        equity += pnl
        peak = max(peak, equity)
        amount = peak - equity
        pct = amount / peak if peak > 0 else None
        max_amount = max(max_amount, amount)
        if pct is not None:
            max_pct = max(max_pct, pct)
    current_amount = peak - equity
    current_pct = current_amount / peak if peak > 0 else None
    return {
        "max_drawdown": _round(max_amount),
        "max_drawdown_pct": _round(max_pct, 6),
        "current_drawdown": _round(current_amount),
        "current_drawdown_pct": _round(current_pct, 6),
    }


async def _ledger_observation(
    db: aiosqlite.Connection, source: str, allocation: float,
) -> tuple[dict, list[str]]:
    warnings: list[str] = []
    columns = await _columns(db, "bankroll_ledger")
    required = {"source", "pnl", "event_type", "timestamp"}
    if columns is None or not required.issubset(columns):
        return ({
            "available": False, "cash_pnl": None, "trade_close_count": None,
            "trade_close_pnl": None, "equity": None,
            **_trade_statistics([]),
            "max_drawdown": None, "max_drawdown_pct": None,
            "current_drawdown": None, "current_drawdown_pct": None,
        }, ["bankroll_ledger unavailable or missing required columns"])

    rows = await (await db.execute(
        "SELECT event_type, pnl FROM bankroll_ledger WHERE source=? "
        "ORDER BY timestamp, rowid", (source,),
    )).fetchall()
    if any(row[1] is None for row in rows):
        warnings.append("ledger contains NULL P&L; cash metrics unavailable")
        return ({
            "available": False, "cash_pnl": None, "trade_close_count": None,
            "trade_close_pnl": None, "equity": None,
            **_trade_statistics([]),
            "max_drawdown": None, "max_drawdown_pct": None,
            "current_drawdown": None, "current_drawdown_pct": None,
        }, warnings)

    all_events = [float(row[1]) for row in rows]
    closes = [float(row[1]) for row in rows if row[0] == "TRADE_CLOSED"]
    stats = _trade_statistics(closes)
    if not closes:
        warnings.append("no ledger trade-close sample; trade metrics unavailable")
    elif stats["profit_factor"] is None:
        warnings.append("profit factor unavailable without a losing trade")
    cash_pnl = sum(all_events)
    return ({
        "available": True,
        "cash_pnl": _round(cash_pnl),
        "trade_close_count": len(closes),
        "trade_close_pnl": _round(sum(closes)),
        "equity": _round(allocation + cash_pnl),
        **stats,
        # Deposits and withdrawals change cash equity but are not strategy
        # returns. The performance curve therefore uses ordered trade closes.
        **_drawdown(closes, allocation),
    }, warnings)


async def _query_position_table(
    db: aiosqlite.Connection, table: str, source: str,
) -> tuple[dict | None, str | None]:
    """Return one store observation, or None when its schema is unavailable."""
    columns = await _columns(db, table)
    if columns is None or "source" not in columns:
        return None, f"{table} unavailable"

    if table == "positions":
        required = {
            "source", "exit_date", "realised_pnl", "r_multiple", "status",
            "entry_price", "shares", "stop_loss_initial",
            "trailing_stop_current",
        }
        if not required.issubset(columns):
            return None, f"{table} missing required accounting columns"
        closed = await (await db.execute(
            "SELECT realised_pnl, r_multiple FROM positions "
            "WHERE source=? AND exit_date IS NOT NULL ORDER BY exit_date, rowid",
            (source,),
        )).fetchall()
        open_row = await (await db.execute(
            "SELECT COALESCE(SUM(entry_price * shares), 0.0), "
            "COALESCE(SUM(MAX(entry_price - COALESCE(trailing_stop_current, "
            "stop_loss_initial, entry_price), 0.0) * shares), 0.0), COUNT(*) "
            "FROM positions WHERE source=? AND exit_date IS NULL "
            "AND status IN ('OPEN','CLOSED_T1')", (source,),
        )).fetchone()
        costs = gross = None
    elif table == "fno_positions":
        required = {
            "source", "status", "pnl", "r_multiple", "costs", "gross_pnl",
            "entry_premium", "qty", "max_loss_rupees", "exit_time",
        }
        if not required.issubset(columns):
            return None, f"{table} missing required accounting columns"
        closed = await (await db.execute(
            "SELECT pnl, r_multiple, costs, gross_pnl FROM fno_positions "
            "WHERE source=? AND status!='OPEN' ORDER BY exit_time, rowid",
            (source,),
        )).fetchall()
        open_row = await (await db.execute(
            "SELECT COALESCE(SUM(entry_premium * qty), 0.0), "
            "COALESCE(SUM(max_loss_rupees), 0.0), COUNT(*) "
            "FROM fno_positions WHERE source=? AND status='OPEN'", (source,),
        )).fetchone()
        costs = sum(float(row[2] or 0.0) for row in closed)
        gross = sum(float(row[3] or 0.0) for row in closed)
    else:  # fno_dr_positions
        required = {
            "source", "status", "pnl", "costs", "gross_pnl",
            "net_premium_rs", "max_loss_rs", "closed_at",
        }
        if not required.issubset(columns):
            return None, f"{table} missing required accounting columns"
        closed = await (await db.execute(
            "SELECT pnl, NULL, costs, gross_pnl FROM fno_dr_positions "
            "WHERE source=? AND status!='OPEN' ORDER BY closed_at, rowid",
            (source,),
        )).fetchall()
        open_row = await (await db.execute(
            "SELECT COALESCE(SUM(ABS(net_premium_rs)), 0.0), "
            "COALESCE(SUM(max_loss_rs), 0.0), COUNT(*) "
            "FROM fno_dr_positions WHERE source=? AND status='OPEN'", (source,),
        )).fetchone()
        costs = sum(float(row[2] or 0.0) for row in closed)
        gross = sum(float(row[3] or 0.0) for row in closed)

    incomplete = any(row[0] is None for row in closed)
    pnls = [float(row[0]) for row in closed if row[0] is not None]
    rs = [float(row[1]) for row in closed if row[1] is not None]
    return ({
        "closed_count": len(closed),
        "valued_closed_count": len(pnls),
        "closed_pnl": None if incomplete else _round(sum(pnls)),
        "wins": sum(1 for value in pnls if value > 0),
        "losses": sum(1 for value in pnls if value < 0),
        "avg_r": _round(sum(rs) / len(rs), 4) if rs else None,
        "r_count": len(rs),
        "costs": _round(costs),
        "gross_pnl": _round(gross),
        "open_exposure": _round(float(open_row[0] or 0.0)),
        "open_risk": _round(float(open_row[1] or 0.0)),
        "open_count": int(open_row[2] or 0),
        "incomplete": incomplete,
    }, None)


async def _position_observation(
    db: aiosqlite.Connection, source: str,
) -> tuple[dict, list[str]]:
    tables = ["fno_positions", "fno_dr_positions"] if source.startswith("FNO_") else ["positions"]
    observations: list[dict] = []
    warnings: list[str] = []
    for table in tables:
        try:
            observation, warning = await _query_position_table(db, table, source)
        except Exception as exc:
            observation, warning = None, f"{table} query unavailable: {exc}"
        if observation is not None:
            observations.append(observation)
        if warning:
            warnings.append(warning)
    if not observations:
        return ({
            "available": False, "closed_count": None, "closed_pnl": None,
            "wins": None, "losses": None, "win_rate": None, "avg_r": None,
            "r_count": None,
            "costs": None, "cost_drag_pct": None, "open_count": None,
            "open_exposure": None, "open_risk": None,
        }, warnings)

    incomplete = any(item["incomplete"] for item in observations)
    closed_count = sum(item["closed_count"] for item in observations)
    wins = sum(item["wins"] for item in observations)
    losses = sum(item["losses"] for item in observations)
    rs_weighted = [
        (item["avg_r"], item["r_count"])
        for item in observations if item["avg_r"] is not None
    ]
    cost_values = [item["costs"] for item in observations if item["costs"] is not None]
    gross_values = [item["gross_pnl"] for item in observations if item["gross_pnl"] is not None]
    costs = sum(cost_values) if cost_values else None
    gross = sum(gross_values) if gross_values else None
    if incomplete:
        warnings.append("closed position rows contain NULL P&L; observed P&L unavailable")
    if costs is None:
        warnings.append("position store does not retain transaction costs")
    elif not gross:
        warnings.append("cost drag unavailable because observed gross P&L is zero")
    decided = wins + losses
    return ({
        "available": True,
        "closed_count": closed_count,
        "closed_pnl": None if incomplete else _round(sum(
            item["closed_pnl"] or 0.0 for item in observations
        )),
        "wins": wins,
        "losses": losses,
        "win_rate": _round(wins / decided, 6) if decided else None,
        "avg_r": _round(
            sum(avg * count for avg, count in rs_weighted) /
            sum(count for _, count in rs_weighted), 4,
        ) if rs_weighted and sum(count for _, count in rs_weighted) else None,
        "r_count": sum(item["r_count"] for item in observations),
        "costs": _round(costs),
        "cost_drag_pct": _round(costs / abs(gross), 6)
        if costs is not None and gross else None,
        "open_count": sum(item["open_count"] for item in observations),
        "open_exposure": _round(sum(item["open_exposure"] for item in observations)),
        "open_risk": _round(sum(item["open_risk"] for item in observations)),
    }, warnings)


def _reconcile(ledger: dict, positions: dict) -> dict:
    if not ledger["available"] or not positions["available"]:
        return {
            "status": "UNAVAILABLE", "pnl_delta": None, "count_gap": None,
            "ledger_is_cash_truth": True,
        }
    if positions["closed_pnl"] is None:
        return {
            "status": "UNAVAILABLE", "pnl_delta": None,
            "count_gap": positions["closed_count"] - ledger["trade_close_count"],
            "ledger_is_cash_truth": True,
        }
    if ledger["trade_close_count"] == 0 and positions["closed_count"] == 0:
        return {
            "status": "UNAVAILABLE", "pnl_delta": None, "count_gap": 0,
            "ledger_is_cash_truth": True,
        }
    pnl_delta = positions["closed_pnl"] - ledger["trade_close_pnl"]
    count_gap = positions["closed_count"] - ledger["trade_close_count"]
    return {
        "status": "MATCH" if abs(pnl_delta) <= 0.01 and count_gap == 0 else "MISMATCH",
        "pnl_delta": _round(pnl_delta),
        "count_gap": count_gap,
        "ledger_is_cash_truth": True,
    }


async def division_performance(db_path: str) -> dict:
    divisions = []
    async with aiosqlite.connect(db_path) as db:
        for key, label, source, pool, allocation, mode in _analytics_registry():
            ledger, ledger_warnings = await _ledger_observation(db, source, allocation)
            positions, position_warnings = await _position_observation(db, source)
            warnings = ledger_warnings + position_warnings
            reconciliation = _reconcile(ledger, positions)
            if reconciliation["status"] == "MISMATCH":
                warnings.append("ledger and position close observations disagree")
            divisions.append({
                "key": key, "label": label, "source": source, "pool": pool,
                "mode": mode, "allocation": _round(allocation),
                "ledger": ledger, "positions": positions,
                "reconciliation": reconciliation, "warnings": warnings,
            })

    totals = {}
    for mode in ("live", "paper"):
        rows = [row for row in divisions if row["mode"] == mode]
        allocation = sum(row["allocation"] for row in rows)
        cash_available = all(row["ledger"]["available"] for row in rows)
        cash_pnl = sum(row["ledger"]["cash_pnl"] for row in rows) if cash_available else None
        totals[mode] = {
            "allocation": _round(allocation),
            "cash_pnl": _round(cash_pnl),
            "equity": _round(allocation + cash_pnl) if cash_pnl is not None else None,
            "division_count": len(rows),
        }

    # Swing and Momentum are complementary slices of INITIAL_BANKROLL. This
    # invariant proves the live total did not count that shared seed twice.
    nifty_allocation = sum(
        row["allocation"] for row in divisions
        if row["source"] in {"SYSTEM", "MOMENTUM"}
    )
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "accounting_truth": "bankroll_ledger",
        "divisions": divisions,
        "totals": totals,
        "invariants": {
            "nifty_allocation": _round(nifty_allocation),
            "nifty_allocation_expected": _round(float(settings.INITIAL_BANKROLL)),
            "nifty_not_double_counted": abs(
                nifty_allocation - float(settings.INITIAL_BANKROLL)
            ) <= 0.01,
        },
    }
