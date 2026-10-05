"""Expiry-day paper book: pure exit/entry rules plus a simulated NIFTY expiry afternoon."""
from datetime import date, datetime, timedelta
import math
import sqlite3

import pytest

import expiry_paper as xp
from fno_instruments import FnoInstruments
from fno_models import Contract

TUESDAY = date(2026, 10, 6)
WEDNESDAY = date(2026, 10, 7)


def _at(day, hh, mm, ss=0):
    return datetime(day.year, day.month, day.day, hh, mm, ss, tzinfo=xp.IST)


def _book(expiry=TUESDAY, refreshed=TUESDAY):
    book = FnoInstruments(underlying="NIFTY", segment="NFO", json_path="unused")
    contracts, token = [], 1000
    for strike in range(24500, 25551, 50):
        for kind in ("CE", "PE"):
            token += 1
            contracts.append(Contract(token=token, tradingsymbol=f"NIFTY26OCT{strike}{kind}", name="NIFTY",
                                      expiry=expiry, strike=float(strike), instrument_type=kind,
                                      lot_size=65, tick_size=0.05))
    contracts.append(Contract(token=999, tradingsymbol="NIFTY26OCTFUT", name="NIFTY", expiry=date(2026, 10, 27),
                              strike=0.0, instrument_type="FUT", lot_size=65, tick_size=0.1))
    book._load_contracts(contracts)
    book.refreshed_on = refreshed
    return book


def _option_price(spot, strike, kind):
    intrinsic = max(0.0, spot - strike) if kind == "CE" else max(0.0, strike - spot)
    return round(intrinsic + 20.0 * math.exp(-abs(spot - strike) / 60.0), 2)


class _Market:
    """Answers documented quote requests from a scripted spot path."""

    def __init__(self, book, spot_at):
        self.access_token = "test"
        self.book = book
        self.spot_at = spot_at
        self.now = None
        self.requests = []

    async def get_quote_by_instruments(self, request):
        self.requests.append(request)
        spot = self.spot_at(self.now)
        out = {}
        for key, name in request.items():
            if key == xp.SPOT_KEY:
                out[key] = {"last_price": spot}
            elif key == xp.FUT_KEY:
                out[key] = {"last_price": spot + 20.0}
            else:
                contract = self.book.by_symbol[name.split(":", 1)[1]]
                mid = _option_price(spot, contract.strike, contract.instrument_type)
                out[key] = {"last_price": mid, "depth": {
                    "buy": [{"price": max(0.05, round(mid - 0.1, 2)), "quantity": 650, "orders": 3}],
                    "sell": [{"price": round(mid + 0.1, 2), "quantity": 650, "orders": 3}]}}
        return out


def _breakout_day(now):
    """Quiet box 24,990-25,010, a 13:40 break up to 25,100, drift back to 25,060 by 14:30."""
    minutes = now.hour * 60 + now.minute + now.second / 60.0
    if minutes < 13 * 60 + 40:
        return 25000.0 + 10.0 * math.sin(minutes)
    if minutes < 14 * 60:
        return 25030.0 + (minutes - (13 * 60 + 40)) * 3.5          # 25,030 -> 25,100
    if minutes < 14 * 60 + 30:
        return 25100.0 - (minutes - 14 * 60) * (40.0 / 30.0)        # back to 25,060
    return 25060.0


async def _run_day(tmp_path, book, spot_at, day=TUESDAY, end=(15, 40)):
    market = _Market(book, spot_at)
    db = str(tmp_path / "trading.db")
    messages = []
    now, stop = _at(day, 12, 59), _at(day, *end)
    while now <= stop:
        market.now = now
        messages += await xp.run_expiry_tick(market, db, now=now, books={"NIFTY": book})
        now += timedelta(seconds=10)
    return market, db, messages


def _positions(db):
    with sqlite3.connect(xp.expiry_db_path(db)) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT * FROM expiry_paper_positions ORDER BY id")]


# --------------------------------------------------------------------------- pure rules

def _pos(entry=20.0, lots=4, play="A", entry_ts=None):
    policy = xp.POLICIES[play]
    return {"entry_price": entry, "peak": entry, "lots_open": lots, "banked": 0,
            "stop": round(entry * (1 - policy.hard_stop), 2) if policy.hard_stop else 0.0,
            "entry_ts": (entry_ts or _at(TUESDAY, 13, 40)).isoformat()}


def test_a_hard_stop_at_minus_30_percent():
    pos = _pos()
    assert xp.manage_position(pos, xp.POLICIES["A"], 15.0, _at(TUESDAY, 13, 41)) is None
    assert xp.manage_position(pos, xp.POLICIES["A"], 13.9, _at(TUESDAY, 13, 42)) == (4, "STOP")


def test_a_banks_half_then_breakeven_protects_the_rest():
    pos = _pos()
    assert xp.manage_position(pos, xp.POLICIES["A"], 28.5, _at(TUESDAY, 13, 42)) == (2, "BANK_HALF")
    pos["lots_open"] = 2
    assert pos["banked"] and pos["stop"] == pytest.approx(21.0)
    assert xp.manage_position(pos, xp.POLICIES["A"], 21.5, _at(TUESDAY, 13, 50)) is None
    assert xp.manage_position(pos, xp.POLICIES["A"], 20.9, _at(TUESDAY, 13, 51)) == (2, "TRAIL")


def test_a_trail_tightens_with_gain_and_after_three_pm():
    pos = _pos()
    pos["banked"] = 1
    xp.manage_position(pos, xp.POLICIES["A"], 45.0, _at(TUESDAY, 14, 10))       # +125%: keep 70%
    assert pos["stop"] == pytest.approx(31.5)
    xp.manage_position(pos, xp.POLICIES["A"], 44.0, _at(TUESDAY, 15, 1))        # late: keep 85% of peak
    assert pos["stop"] == pytest.approx(38.25)
    assert xp.manage_position(pos, xp.POLICIES["A"], 38.0, _at(TUESDAY, 15, 2)) == (4, "TRAIL")


def test_a_time_stop_and_flat_time():
    pos = _pos()
    assert xp.manage_position(pos, xp.POLICIES["A"], 22.0, _at(TUESDAY, 13, 47)) is None
    assert xp.manage_position(pos, xp.POLICIES["A"], 22.0, _at(TUESDAY, 13, 48)) == (4, "TIME_STOP")
    late = _pos(entry_ts=_at(TUESDAY, 15, 8))
    assert xp.manage_position(late, xp.POLICIES["A"], 25.0, _at(TUESDAY, 15, 13)) == (4, "FLAT_TIME")


def test_a_failed_break_closes_the_leg():
    pos = _pos()
    assert xp.manage_position(pos, xp.POLICIES["A"], 19.0, _at(TUESDAY, 13, 41),
                              structure_broken=True) == (4, "FAILED_BREAK")


def test_c_lottery_has_no_stop_banks_at_3x_and_holds_into_the_auction():
    pos = _pos(entry=4.0, lots=6, play="C")
    assert xp.manage_position(pos, xp.POLICIES["C"], 0.5, _at(TUESDAY, 14, 0)) is None
    assert xp.manage_position(pos, xp.POLICIES["C"], 12.0, _at(TUESDAY, 15, 20)) == (3, "BANK_HALF")
    pos["lots_open"] = 3
    xp.manage_position(pos, xp.POLICIES["C"], 25.0, _at(TUESDAY, 15, 25))       # 6.25x: keep 60%
    assert pos["stop"] == pytest.approx(15.0)
    assert xp.manage_position(pos, xp.POLICIES["C"], 20.0, _at(TUESDAY, 15, 38)) == (3, "FLAT_TIME")


def test_box_needs_samples_and_breakout_needs_two_ticks_with_futures():
    state = xp.new_day_state()
    for i in range(10):
        xp.update_box(state, _at(TUESDAY, 13, i).time(), 25000.0, 25020.0)
    xp.update_box(state, _at(TUESDAY, 13, 30).time(), 25000.0, 25020.0)
    assert state["box_status"] == "UNUSABLE_10_SAMPLES"

    state = xp.new_day_state()
    for i in range(40):
        xp.update_box(state, (_at(TUESDAY, 13, 0) + timedelta(seconds=40 * i)).time(),
                      24990.0 + (i % 3) * 10, 25010.0 + (i % 3) * 10)
    xp.update_box(state, _at(TUESDAY, 13, 30).time(), 25000.0, 25020.0)
    assert state["box"] == {"hi": 25010.0, "lo": 24990.0, "fut_hi": 25030.0, "fut_lo": 25010.0, "n": 40}
    t = _at(TUESDAY, 13, 40).time()
    assert xp.breakout_signal(state, t, 25020.0, 25040.0) is None             # first tick
    assert xp.breakout_signal(state, t, 25020.0, 25025.0) is None             # futures disagree: reset
    assert xp.breakout_signal(state, t, 25020.0, 25040.0) is None
    assert xp.breakout_signal(state, t, 25021.0, 25041.0) == "UP"
    assert xp.breakout_signal(state, t, 25022.0, 25042.0) is None             # disarmed until back inside
    xp.breakout_signal(state, t, 25000.0, 25020.0)
    xp.breakout_signal(state, t, 25020.0, 25040.0)
    assert xp.breakout_signal(state, t, 25020.0, 25040.0) == "UP"
    assert xp.breakout_signal(state, _at(TUESDAY, 15, 5).time(), 24900.0, 24910.0) is None


def test_a_sizing_respects_budget_outlay_and_lot_cap():
    assert xp.a_lots(ask=14.4, lot_size=65, remaining_budget=2500.0) == 4      # risk 281/lot, capped at 4
    assert xp.a_lots(ask=60.0, lot_size=65, remaining_budget=2500.0) == 2      # risk 1,170/lot
    assert xp.a_lots(ask=150.0, lot_size=65, remaining_budget=2500.0) == 0     # one lot risks 2,925
    assert xp.a_lots(ask=14.4, lot_size=65, remaining_budget=500.0) == 1


# --------------------------------------------------------------------------- the tick

@pytest.mark.asyncio
async def test_no_quotes_on_a_non_expiry_day(tmp_path):
    book = _book(expiry=TUESDAY + timedelta(days=7), refreshed=WEDNESDAY)
    market, _, messages = await _run_day(tmp_path, book, _breakout_day, day=WEDNESDAY, end=(13, 5))
    assert market.requests == [] and messages == []


@pytest.mark.asyncio
async def test_simulated_breakout_expiry_runs_all_three_plays_and_ends_flat(tmp_path):
    book = _book()
    market, db, messages = await _run_day(tmp_path, book, _breakout_day)
    rows = _positions(db)
    by_play = {play: [r for r in rows if r["play"] == play] for play in "ABC"}

    (a,) = by_play["A"]
    assert a["symbol"] == "NIFTY26OCT25050CE" and a["lots"] == 4
    assert a["banked"] == 1 and a["net_pnl"] > 0
    (c,) = by_play["C"]
    assert c["opt_type"] == "CE" and 25050 < c["strike"]
    assert c["lots"] * c["entry_price"] * 65 <= 2500.0
    assert sorted(r["opt_type"] for r in by_play["B"]) == ["CE", "PE"]
    assert {r["strike"] for r in by_play["B"]} == {25050.0, 25100.0}
    assert all(r["status"] == "CLOSED" and r["lots_open"] == 0 for r in rows)
    assert sum(1 for m in messages if "to date" in m) == 1                     # one day summary

    with sqlite3.connect(xp.expiry_db_path(db)) as conn:
        last_tick = conn.execute("SELECT MAX(ts) FROM expiry_paper_ticks").fetchone()[0]
    assert last_tick.startswith("2026-10-06T15:40")                           # auction window recorded


@pytest.mark.asyncio
async def test_a_loss_shrinks_the_remaining_budget_for_the_second_trade(tmp_path):
    def whipsaw(now):
        minutes = now.hour * 60 + now.minute
        if minutes < 13 * 60 + 40:
            return 25000.0 + 10.0 * math.sin(minutes)
        if minutes < 13 * 60 + 42:
            return 25030.0                                                  # break up
        if minutes < 13 * 60 + 50:
            return 24995.0                                                  # failed: back inside
        return 25030.0                                                      # breaks again

    _, db, _ = await _run_day(tmp_path, _book(), whipsaw, end=(14, 0))
    first, second = [r for r in _positions(db) if r["play"] == "A"]
    assert first["net_pnl"] < 0
    assert second["lots"] <= xp.a_lots(second["entry_price"], 65, 2500.0 + first["net_pnl"])
