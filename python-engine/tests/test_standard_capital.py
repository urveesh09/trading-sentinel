"""[O21-SC] Standard-capital replay: identity at the reference, whole units, own cash, charges."""
import sqlite3
from datetime import datetime, timedelta

import pytest
import pytz

import standard_capital as sc
from config import settings
from fno_costs import calc_fno_costs

IST = pytz.timezone("Asia/Kolkata")


def T(day, h=10, m=0):
    return IST.localize(datetime(2026, 10, day, h, m))


def _fno(day, entry, exit_, lots=1, lot_size=75, hold_min=60):
    qty = lots * lot_size
    net = (exit_ - entry) * qty - calc_fno_costs(entry, exit_, qty)
    return sc.TradeRow(T(day), T(day) + timedelta(minutes=hold_min), f"d{day}", lots, entry * lot_size, net,
                       lambda n, e=entry, x=exit_, ls=lot_size: calc_fno_costs(e, x, n * ls))


def test_replay_at_the_reference_is_the_books_own_pnl():
    rows = [_fno(1, 100, 120), _fno(2, 100, 80, lots=2), _fno(3, 90, 99)]
    result = sc.replay(rows, 250000, 250000)
    assert result["net_pnl"] == round(sum(r.net_pnl for r in rows), 2)
    assert result["trades_taken"] == 3 and result["skipped_too_small"] == 0


def test_scaling_uses_whole_lots_and_recomputed_charges():
    row = _fno(1, 100, 120)
    result = sc.replay([row], 500000, 250000)          # x2 -> 2 lots
    assert result["net_pnl"] == round(20 * 150 - calc_fno_costs(100, 120, 150), 2)
    # x0.8 rounds back to the same lot: the ₹2L answer equals the ₹2.5L book.
    assert sc.replay([row], 200000, 250000)["net_pnl"] == round(row.net_pnl, 2)
    # x0.04 (₹10k): a NIFTY lot does not exist at that size.
    small = sc.replay([row], 10000, 250000)
    assert small["trades_taken"] == 0 and small["skipped_too_small"] == 1 and small["net_pnl"] == 0


def test_own_cash_sizes_down_then_skips_overlapping_trades():
    a = sc.TradeRow(T(1, 10), T(1, 12), "a", 600, 100.0, 600.0, lambda n: 0.0)
    b = sc.TradeRow(T(1, 11), T(1, 13), "b", 600, 100.0, 600.0, lambda n: 0.0)
    c = sc.TradeRow(T(1, 11, 30), T(1, 13), "c", 10, 100.0, 10.0, lambda n: 0.0)
    result = sc.replay([a, b, c], 100000, 100000)
    # a uses ₹60k; b fits 400 of 600 shares; c finds no cash.
    assert result["sized_down_for_cash"] == 1 and result["skipped_no_cash"] == 1
    assert result["net_pnl"] == 600.0 + 400.0


def test_scaled_costs_keep_the_flat_order_charge_fixed():
    cost = sc._scaled_costs(200.0, 1, 4)
    assert cost(1) == 200.0
    assert cost(3) == pytest.approx(4 * sc.FLAT_ORDER_RS + (200.0 - 4 * sc.FLAT_ORDER_RS) * 3)


def test_number_and_close_time_parsing():
    assert sc._num(b"&\x00\x00\x00\x00\x00\x00\x00") == 38.0     # numpy int64 written raw
    assert sc._num("12.5") == 12.5 and sc._num(None) is None
    opened = T(5, 11, 31)
    assert sc._close_time("2026-10-05", opened) == T(5, 15, 30)
    assert sc._close_time("2026-10-05", T(5, 15, 45)) == T(5, 15, 45)    # never before the entry


def test_view_flags_scale_and_combines_an_equal_split():
    equity = sc.BookSpec("overnight", "EDGE overnight", "EQUITY", "none", 25000.0,
                         rows=[sc.TradeRow(T(1), T(2), "x", 100, 50.0, 200.0, lambda n: 0.0)])
    fno = sc.BookSpec("fno_single", "F&O", "FNO", "gated", 250000.0, rows=[_fno(1, 100, 110)])
    empty = sc.BookSpec("penny", "Penny", "EQUITY", "off", 100000.0)
    view = sc.standard_capital_view([equity, fno, empty], capital=200000.0, since=None, now=T(20))
    by = {b["key"]: b for b in view["books"]}
    assert by["overnight"]["scale"] == 8.0 and any("scaled x8.0" in f for f in by["overnight"]["flags"])
    assert by["overnight"]["net_pnl"] == 1600.0
    assert by["penny"]["net_pnl"] is None
    assert view["equal_split"]["books"] == 2 and view["equal_split"]["per_book"] == 100000.0
    since = sc.standard_capital_view([equity, fno], capital=200000.0, since=T(2), now=T(20))
    assert all(b["trades_in_book"] == 0 for b in since["books"])


def test_loaders_read_the_books_tables_read_only(tmp_path, monkeypatch):
    db = str(tmp_path / "cache.db")
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE fno_positions (source, status, entry_time, exit_time, underlying, lots, "
                     "initial_lots, lot_size, entry_premium, exit_premium, pnl, costs, qty, initial_qty, tradingsymbol)")
        net = (110 - 100) * 75 - calc_fno_costs(100, 110, 75)
        conn.execute("INSERT INTO fno_positions VALUES ('FNO_PAPER','CLOSED',?,?, 'NIFTY',1,1,75,100,110,?,0,75,75,'N')",
                     (T(1).isoformat(), T(1, 11).isoformat(), net))
        conn.execute("CREATE TABLE positions (ticker, entry_date, exit_date, entry_price, exit_price, shares, "
                     "realised_pnl, product_type, status, source)")
        conn.execute("INSERT INTO positions VALUES ('SIGACHI','2026-10-01T06:01:30+00:00','2026-10-01',27.9,29.5,0,"
                     "12.0,'MIS','CLOSED_TIME','PENNY_PAPER')")
        conn.execute("CREATE TABLE bankroll_ledger (source, event_type)")
        conn.execute("INSERT INTO bankroll_ledger VALUES ('PENNY_PAPER','TRADE_CLOSED')")
    books = {b.key: b for b in sc.load_books(db)}
    assert len(books["fno_single"].rows) == 1 and books["fno_single"].rows[0].net_pnl == pytest.approx(net)
    [penny] = books["penny"].rows
    assert penny.units == int(settings.PENNY_PER_STOCK_CAP // 27.9) and penny.units_estimated
    assert "sized from the per-stock cap" in books["penny"].note
    assert books["expiry"].reference == 3 * settings.EXPIRY_PAPER_BUDGET / settings.FNO_MAX_RISK_PCT
    assert "unreadable" in books["fno_spreads"].note       # table absent in this fixture


@pytest.mark.asyncio
async def test_capital_and_since_are_validated():
    with pytest.raises(ValueError):
        await sc.load_standard_capital(settings.DB_PATH, capital=10.0)
    with pytest.raises(ValueError):
        await sc.load_standard_capital(settings.DB_PATH, capital=200000.0, since="Sept")
