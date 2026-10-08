"""Expiry-day paper book: rules, executable fills, loss ceiling, settlement and the outbox."""
from contextlib import closing
from datetime import date, datetime, timedelta
import json
import math
import sqlite3
from types import SimpleNamespace

import pytest

import expiry_paper as xp
from fno_instruments import FnoInstruments
from fno_models import Contract

TUESDAY = date(2026, 10, 6)
WEDNESDAY = date(2026, 10, 7)
BUDGET = 2500.0


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
    """Answers documented quote requests from a scripted spot path with five-level depth."""

    def __init__(self, book, spot_at, *, lag_sec=1.0, level_qty=650, no_bid_after=None, gap_at=None, oi=False):
        self.access_token = "test"
        self.book, self.spot_at, self.oi = book, spot_at, oi
        self.lag_sec, self.level_qty = lag_sec, level_qty
        self.no_bid_after, self.gap_at = no_bid_after, gap_at
        self.now = None
        self.requests = []

    def _stamp(self):
        return (self.now - timedelta(seconds=self.lag_sec)).strftime("%Y-%m-%d %H:%M:%S")

    async def get_quote_by_instruments(self, request):
        self.requests.append(request)
        spot = self.spot_at(self.now)
        out = {}
        for key, name in request.items():
            if key == xp.SPOT_KEY:
                out[key] = {"last_price": spot, "timestamp": self._stamp()}
            elif key == xp.FUT_KEY:
                out[key] = {"last_price": spot + 20.0, "timestamp": self._stamp()}
                if self.oi:
                    out[key]["oi"] = 9_000_000 + (self.now.hour * 60 + self.now.minute) * 500
            else:
                contract = self.book.by_symbol[name.split(":", 1)[1]]
                mid = _option_price(spot, contract.strike, contract.instrument_type)
                if self.gap_at and self.now >= self.gap_at:
                    mid = 1.1
                bids = [] if self.no_bid_after and self.now.time() >= self.no_bid_after else [
                    {"price": round(max(0.05, mid - 0.1 - 0.05 * i), 2), "quantity": self.level_qty, "orders": 2}
                    for i in range(5)]
                asks = [{"price": round(mid + 0.1 + 0.05 * i, 2), "quantity": self.level_qty, "orders": 2}
                        for i in range(5)]
                out[key] = {"last_price": mid, "timestamp": self._stamp(), "depth": {"buy": bids, "sell": asks}}
                if self.oi:
                    out[key]["oi"] = _chain_oi(contract, self.now)
        return out


def _chain_oi(contract, now):
    """Put OI peaks at 24,900 and call OI at 25,200; call writers add through the afternoon."""
    peak = 24900.0 if contract.instrument_type == "PE" else 25200.0
    added = max(0, (now.hour * 60 + now.minute - 13 * 60) * 100) if contract.instrument_type == "CE" else 0
    return max(0, 500_000 - 2_000 * abs(contract.strike - peak)) + added


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


async def _run_day(tmp_path, market, day=TUESDAY, start=(12, 59), end=(15, 39, 50), reconcile_at=(15, 45)):
    tmp_path.mkdir(parents=True, exist_ok=True)
    db = str(tmp_path / "trading.db")
    now, stop = _at(day, *start), _at(day, *end)
    while now <= stop:
        market.now = now
        await xp.run_expiry_tick(market, db, now=now, books={"NIFTY": market.book})
        now += timedelta(seconds=10)
    if reconcile_at:
        xp.reconcile(db, now=_at(day, *reconcile_at))
    return db


def _positions(db):
    with sqlite3.connect(xp.expiry_db_path(db)) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT * FROM expiry_paper_positions ORDER BY id")]


def _notices(db):
    with sqlite3.connect(xp.expiry_db_path(db)) as conn:
        return conn.execute("SELECT key, message, sent_at FROM expiry_paper_notices ORDER BY created_at").fetchall()


def _quote(levels, side="asks", ts=None):
    book = tuple(levels)
    return xp.Quote(bids=book if side == "bids" else (), asks=book if side == "asks" else (),
                    ltp=levels[0][0] if levels else None, ts=ts or _at(TUESDAY, 13, 40))


# --------------------------------------------------------------------------- exit rules

def _pos(entry=20.0, lots=4, play="A", entry_ts=None):
    policy = xp.POLICIES[play]
    return {"entry_price": entry, "peak": entry, "lots_open": lots, "banked": 0,
            "stop": round(entry * (1 - policy.hard_stop), 2) if policy.hard_stop else 0.0,
            "entry_ts": (entry_ts or _at(TUESDAY, 13, 40)).isoformat()}


def test_a_planned_stop_at_minus_30_percent():
    pos = _pos()
    assert xp.manage_position(pos, xp.POLICIES["A"], 15.0, _at(TUESDAY, 13, 41)) is None
    assert xp.manage_position(pos, xp.POLICIES["A"], 13.9, _at(TUESDAY, 13, 42)) == (4, "STOP")


def test_a_banks_half_then_raises_the_stop():
    pos = _pos()
    assert xp.manage_position(pos, xp.POLICIES["A"], 28.5, _at(TUESDAY, 13, 42)) == (2, "BANK_HALF")
    pos["lots_open"], pos["bank_pending"] = 2, 0                                 # the bank filled
    assert pos["banked"] and pos["stop"] == pytest.approx(21.0)
    assert xp.manage_position(pos, xp.POLICIES["A"], 21.5, _at(TUESDAY, 13, 50)) is None
    assert xp.manage_position(pos, xp.POLICIES["A"], 20.9, _at(TUESDAY, 13, 51)) == (2, "TRAIL")


def test_one_lot_cannot_bank_half_and_only_raises_its_stop():
    pos = _pos(lots=1)
    assert xp.manage_position(pos, xp.POLICIES["A"], 28.5, _at(TUESDAY, 13, 42)) is None
    assert pos["banked"] == 1 and pos["stop"] == pytest.approx(21.0) and pos["lots_open"] == 1


def test_a_trail_tightens_with_gain_and_after_three_pm():
    pos = _pos()
    pos["banked"] = 1
    xp.manage_position(pos, xp.POLICIES["A"], 45.0, _at(TUESDAY, 14, 10))       # +125%: keep 70%
    assert pos["stop"] == pytest.approx(31.5)
    xp.manage_position(pos, xp.POLICIES["A"], 44.0, _at(TUESDAY, 15, 1))        # late: keep 85% of peak
    assert pos["stop"] == pytest.approx(38.25)
    assert xp.manage_position(pos, xp.POLICIES["A"], 38.0, _at(TUESDAY, 15, 2)) == (4, "TRAIL")


def test_a_time_stop_failed_break_and_flat_time():
    pos = _pos()
    assert xp.manage_position(pos, xp.POLICIES["A"], 22.0, _at(TUESDAY, 13, 47)) is None
    assert xp.manage_position(pos, xp.POLICIES["A"], 22.0, _at(TUESDAY, 13, 48)) == (4, "TIME_STOP")
    assert xp.manage_position(_pos(), xp.POLICIES["A"], 19.0, _at(TUESDAY, 13, 41),
                              structure_broken=True) == (4, "FAILED_BREAK")
    late = _pos(entry_ts=_at(TUESDAY, 15, 8))
    assert xp.manage_position(late, xp.POLICIES["A"], 25.0, _at(TUESDAY, 15, 13)) == (4, "FLAT_TIME")


def test_c_lottery_has_no_stop_banks_at_3x_and_holds_into_the_auction():
    pos = _pos(entry=4.0, lots=6, play="C")
    assert xp.manage_position(pos, xp.POLICIES["C"], 0.5, _at(TUESDAY, 14, 0)) is None
    assert xp.manage_position(pos, xp.POLICIES["C"], 12.0, _at(TUESDAY, 15, 20)) == (3, "BANK_HALF")
    pos["lots_open"], pos["bank_pending"] = 3, 0
    xp.manage_position(pos, xp.POLICIES["C"], 25.0, _at(TUESDAY, 15, 25))       # 6.25x: keep 60%
    assert pos["stop"] == pytest.approx(15.0)
    assert xp.manage_position(pos, xp.POLICIES["C"], 20.0, _at(TUESDAY, 15, 38)) == (3, "FLAT_TIME")


# --------------------------------------------------------------------------- entry rules

def _ready_state():
    state = xp.new_day_state()
    for i in range(40):
        xp.update_box(state, (_at(TUESDAY, 13, 0) + timedelta(seconds=40 * i)).time(),
                      24990.0 + (i % 3) * 10, 25010.0 + (i % 3) * 10)
    xp.update_box(state, _at(TUESDAY, 13, 30).time(), 25000.0, 25020.0)
    return state


def test_box_needs_fresh_index_and_future_samples():
    state = xp.new_day_state()
    for i in range(40):
        xp.update_box(state, (_at(TUESDAY, 13, 0) + timedelta(seconds=40 * i)).time(), 25000.0, None)
    xp.update_box(state, _at(TUESDAY, 13, 30).time(), 25000.0, 25020.0)
    assert state["box_status"] == "UNUSABLE_0_SAMPLES"
    assert _ready_state()["box"] == {"hi": 25010.0, "lo": 24990.0, "fut_hi": 25030.0, "fut_lo": 25010.0, "n": 40}


def test_breakout_needs_two_close_fresh_observations_with_the_future_agreeing():
    state = _ready_state()
    t0 = _at(TUESDAY, 13, 40)
    assert xp.breakout_signal(state, t0, 25020.0, 25040.0) is None                          # first
    assert xp.breakout_signal(state, t0 + timedelta(seconds=10), 25020.0, None) is None     # future missing
    assert xp.breakout_signal(state, t0 + timedelta(seconds=20), 25020.0, 25040.0) is None  # count restarted
    assert xp.breakout_signal(state, t0 + timedelta(seconds=60), 25021.0, 25041.0) is None  # 40 s gap: restart
    assert xp.breakout_signal(state, t0 + timedelta(seconds=70), 25021.0, 25025.0) is None  # future disagrees
    assert xp.breakout_signal(state, t0 + timedelta(seconds=80), 25021.0, 25041.0) is None
    assert xp.breakout_signal(state, t0 + timedelta(seconds=90), 25022.0, 25042.0) == "UP"
    assert xp.breakout_signal(state, t0 + timedelta(seconds=100), 25022.0, 25042.0) is None  # disarmed
    xp.breakout_signal(state, t0 + timedelta(seconds=110), 25000.0, 25020.0)                 # back inside: re-arm
    xp.breakout_signal(state, t0 + timedelta(seconds=120), 25020.0, 25040.0)
    assert xp.breakout_signal(state, t0 + timedelta(seconds=130), 25020.0, 25040.0) == "UP"
    late = _at(TUESDAY, 15, 5)
    xp.breakout_signal(state, late, 24900.0, 24910.0)
    assert xp.breakout_signal(state, late + timedelta(seconds=10), 24900.0, 24910.0) is None


def test_walk_fills_whole_lots_from_visible_depth_only():
    levels = ((10.0, 40), (10.5, 40), (11.0, 100))
    assert xp.walk(levels, 1, 65) == (1, pytest.approx((40 * 10.0 + 25 * 10.5) / 65, abs=1e-3))
    assert xp.walk(levels, 3, 65) == (2, pytest.approx((40 * 10 + 40 * 10.5 + 50 * 11.0) / 130, abs=1e-3))
    assert xp.walk(((10.0, 1),), 1, 65) == (0, None)


def test_affordable_fill_keeps_premium_plus_charges_inside_the_budget():
    def quote(price):
        return _quote([(price, 650)])

    assert xp.affordable_fill([(quote(60.0), 65)], BUDGET, 4) == (0, [])          # one lot is Rs 3,900
    lots, prices = xp.affordable_fill([(quote(19.0), 65)], BUDGET, 4)
    assert lots == 1                                                              # two lots + charges > 2,500
    assert xp.worst_case_loss(prices[0], 1, 65) <= BUDGET
    lots, prices = xp.affordable_fill([(quote(6.0), 65)], BUDGET, 10)
    assert lots == 5 and xp.worst_case_loss(prices[0], lots, 65) <= BUDGET       # 6 lots + exit fees > 2,500
    lots, _ = xp.affordable_fill([(quote(10.0), 65), (quote(17.0), 65)], BUDGET, 4)
    assert lots == 1


def test_sliced_exits_at_nearly_zero_stay_inside_max_loss():
    """Review repro: 2 lots at 18.80 sold one lot at a time at 0.05 lost more than the reserve.

    Sizing now reserves one sell-order fee per lot, so 2 lots at 18.80 no
    longer fit. Whatever the size, the buy is charged once at entry, each
    slice pays only its own sell order, and the result stays inside max_loss.
    """
    assert xp.affordable_fill([(_quote([(18.80, 650)]), 65)], BUDGET, 4)[0] == 1
    contract = SimpleNamespace(tradingsymbol="NIFTY26OCT25050CE", token=1, strike=25050.0,
                               instrument_type="CE", lot_size=65)
    now = _at(TUESDAY, 13, 40)
    pos = xp._new_position("2026-10-06", "NIFTY", "A", "NFO", contract, 18.80, 2, now)
    assert pos["max_loss"] > BUDGET                                              # why sizing refuses it
    assert pos["net_pnl"] == pytest.approx(-xp.buy_charges(18.80, 130), abs=0.01)
    xp._sell(pos, 1, 0.05, "STOP", now)
    xp._sell(pos, 1, 0.05, "STOP", now + timedelta(seconds=10))
    assert pos["status"] == "CLOSED" and -pos["net_pnl"] <= pos["max_loss"]
    from fno_costs import calc_fno_costs
    one_order_pair = calc_fno_costs(18.80, 0.05, 130)
    assert pos["costs"] == pytest.approx(one_order_pair + xp.order_fee(), abs=0.02)   # one buy, two sells


# --------------------------------------------------------------------------- the tick

@pytest.mark.asyncio
async def test_no_quotes_on_a_non_expiry_day(tmp_path):
    market = _Market(_book(expiry=TUESDAY + timedelta(days=7), refreshed=WEDNESDAY), _breakout_day)
    db = await _run_day(tmp_path, market, day=WEDNESDAY, end=(13, 5), reconcile_at=None)
    assert market.requests == [] and _notices(db) == []


@pytest.mark.asyncio
async def test_simulated_breakout_expiry_runs_all_three_plays_within_the_ceiling(tmp_path):
    db = await _run_day(tmp_path, _Market(_book(), _breakout_day))
    rows = [r for r in _positions(db) if r["play"] in xp.MAIN_PLAYS]
    by_play = {play: [r for r in rows if r["play"] == play] for play in "ABC"}

    (a,) = by_play["A"]
    assert a["symbol"] == "NIFTY26OCT25050CE" and a["lots"] == 2
    assert a["banked"] == 1 and a["net_pnl"] > 0
    (c,) = by_play["C"]
    assert c["opt_type"] == "CE" and c["strike"] > 25050 and c["lots"] == 5
    assert sorted(r["opt_type"] for r in by_play["B"]) == ["CE", "PE"]
    assert all(r["status"] == "CLOSED" and r["lots_open"] == 0 and r["assumed_pnl"] is None for r in rows)
    assert all(r["max_loss"] <= BUDGET for r in by_play["A"] + by_play["C"])
    assert sum(r["max_loss"] for r in by_play["B"]) <= BUDGET

    b_exit = json.loads(by_play["B"][0]["events"])[-1]
    assert b_exit["fill_model"] == "AUCTION_WINDOW"
    summaries = [m for k, m, _ in _notices(db) if k.endswith(":summary")]
    assert len(summaries) == 1 and "auction-window fills unverified" in summaries[0]
    with sqlite3.connect(xp.expiry_db_path(db)) as conn:
        last_tick = conn.execute("SELECT MAX(ts) FROM expiry_paper_ticks").fetchone()[0]
    assert last_tick.startswith("2026-10-06T15:39:50")


@pytest.mark.asyncio
async def test_a_gap_through_the_stop_never_loses_more_than_the_budget(tmp_path):
    market = _Market(_book(), _breakout_day, gap_at=_at(TUESDAY, 13, 41))
    db = await _run_day(tmp_path, market, end=(13, 50))
    a = next(r for r in _positions(db) if r["play"] == "A")
    assert a["status"] == "CLOSED" and a["net_pnl"] < -0.5 * a["max_loss"]       # far beyond the -30% plan
    assert -a["net_pnl"] <= a["max_loss"] <= BUDGET


@pytest.mark.asyncio
async def test_bank_then_gap_is_bounded_by_max_loss_not_breakeven(tmp_path):
    def spike_then_gap(now):
        minutes = now.hour * 60 + now.minute
        if minutes < 13 * 60 + 40:
            return 25000.0 + 10.0 * math.sin(minutes)
        return 25030.0 if minutes < 13 * 60 + 41 else 25060.0          # +40% on the ATM call

    market = _Market(_book(), spike_then_gap, gap_at=_at(TUESDAY, 13, 45))
    db = await _run_day(tmp_path, market, end=(13, 50))
    a = next(r for r in _positions(db) if r["play"] == "A")
    actions = [e["action"] for e in json.loads(a["events"])]
    assert actions[:2] == ["BUY", "BANK_HALF"] and actions[-1] in ("TRAIL", "STOP")
    assert a["net_pnl"] < 0 and -a["net_pnl"] <= a["max_loss"]


@pytest.mark.asyncio
async def test_stale_or_one_unit_quotes_never_open_a_position(tmp_path):
    stale = await _run_day(tmp_path / "stale", _Market(_book(), _breakout_day, lag_sec=60), end=(15, 20))
    thin = await _run_day(tmp_path / "thin", _Market(_book(), _breakout_day, level_qty=1), end=(15, 20))
    assert _positions(stale) == [] and _positions(thin) == []
    with sqlite3.connect(xp.expiry_db_path(stale)) as conn:
        state = json.loads(conn.execute("SELECT state FROM expiry_paper_days").fetchone()[0])
    assert state["box_status"] == "UNUSABLE_0_SAMPLES" and state["stale_spot"] == state["ticks"]


@pytest.mark.asyncio
async def test_missing_bids_latch_the_exit_and_settle_as_assumed_after_the_session(tmp_path):
    market = _Market(_book(), _breakout_day, no_bid_after=xp.FINAL_FLAT)
    db = await _run_day(tmp_path, market)
    c = next(r for r in _positions(db) if r["play"] == "C")
    assert c["status"] == "SETTLED_ASSUMED" and c["exit_pending"] == "FLAT_TIME"
    settle = json.loads(c["events"])[-1]
    assert settle["settlement_spot"] == pytest.approx(25060.0)
    intrinsic = max(0.0, 25060.0 - c["strike"])
    assert c["assumed_pnl"] == pytest.approx(
        (intrinsic * (1 - xp.EXERCISE_STT_PCT) - c["entry_price"]) * c["lots_open"] * 65, abs=0.01)
    assert settle["settlement_source"] == "SAMPLED_INDEX_QUOTE"


@pytest.mark.asyncio
async def test_outage_leaves_unresolved_legs_settled_next_morning(tmp_path):
    market = _Market(_book(), _breakout_day)
    db = await _run_day(tmp_path, market, end=(13, 45), reconcile_at=None)       # container dies at 13:45
    assert any(r["status"] == "OPEN" for r in _positions(db))
    assert xp.reconcile(db, now=_at(TUESDAY, 15, 30)) == 0                       # session still open
    settled = xp.reconcile(db, now=_at(WEDNESDAY, 9, 45))
    rows = _positions(db)
    assert settled >= 1 and not any(r["status"] == "OPEN" for r in rows)
    unresolved = [r for r in rows if r["status"] == "UNRESOLVED"]
    assert unresolved and all(r["assumed_pnl"] == pytest.approx(
        -(r["entry_price"] * r["lots_open"] * 65 + r["lots_open"] * xp.order_fee()), abs=0.01) for r in unresolved)
    assert all(-(r["net_pnl"] + r["assumed_pnl"]) <= r["max_loss"] + 0.01 for r in unresolved)
    assert [k for k, _, _ in _notices(db) if k.endswith(":summary")] == ["2026-10-06:NIFTY:summary"]


@pytest.mark.asyncio
async def test_notices_are_marked_sent_only_after_a_successful_send(tmp_path):
    db = await _run_day(tmp_path, _Market(_book(), _breakout_day), end=(13, 41))
    pending = len(_notices(db))
    assert pending >= 2

    async def failing(message):
        raise RuntimeError("gateway down")

    assert await xp.flush_notices(failing, db) == 0
    assert all(sent is None for _, _, sent in _notices(db))
    delivered = []

    async def ok(message):
        delivered.append(message)

    assert await xp.flush_notices(ok, db) == pending
    assert await xp.flush_notices(ok, db) == 0 and len(delivered) == pending


@pytest.mark.asyncio
async def test_an_a_loss_shrinks_the_ceiling_for_the_second_trade(tmp_path):
    def whipsaw(now):
        minutes = now.hour * 60 + now.minute
        if minutes < 13 * 60 + 40:
            return 25000.0 + 10.0 * math.sin(minutes)
        if minutes < 13 * 60 + 42:
            return 25030.0                                                  # break up
        if minutes < 13 * 60 + 50:
            return 24995.0                                                  # failed: back inside
        return 25030.0                                                      # breaks again

    db = await _run_day(tmp_path, _Market(_book(), whipsaw), end=(14, 0), reconcile_at=None)
    first, second = [r for r in _positions(db) if r["play"] == "A"]
    assert first["net_pnl"] < 0
    assert second["max_loss"] <= BUDGET + first["net_pnl"]


# --------------------------------------------------------------------------- first-day audit (Oct 6)

async def _one_tick(tmp_path, market, started, decided):
    tmp_path.mkdir(parents=True, exist_ok=True)
    db = str(tmp_path / "trading.db")
    market.now = decided
    await xp.run_expiry_tick(market, db, now=started, books={"NIFTY": market.book}, clock=lambda: decided)
    with sqlite3.connect(xp.expiry_db_path(db)) as conn:
        ts, spot, payload = conn.execute("SELECT ts, spot, quotes FROM expiry_paper_ticks").fetchone()
    return db, ts, spot, json.loads(payload)


@pytest.mark.asyncio
async def test_freshness_is_judged_when_the_quotes_arrive_not_when_the_request_started(tmp_path):
    """Audit probe: a 15 s wait for quotes made v1 refuse new packets and accept old ones."""
    started, decided = _at(TUESDAY, 13, 40), _at(TUESDAY, 13, 40, 15)
    # Stamped at receipt, 15 s after the start: v1 called it 15 s in the future.
    _, ts, spot, payload = await _one_tick(tmp_path / "new", _Market(_book(), _breakout_day, lag_sec=0),
                                           started, decided)
    assert ts == decided.isoformat() and payload["started"] == started.isoformat()
    assert spot is not None and payload["index"]["status"] == "FRESH"
    assert payload["execution"] == xp.EXECUTION_VERSION
    leg = next(iter(payload["legs"].values()))
    assert len(leg["b"]) == 5 and len(leg["a"]) == 5 and leg["ts"]                # the whole depth is kept
    # Stamped 15 s before the start: 30 s old at receipt, which v1 accepted as 15 s.
    _, _, spot, payload = await _one_tick(tmp_path / "old", _Market(_book(), _breakout_day, lag_sec=30),
                                          started, decided)
    assert spot is None and payload["index"]["status"] == "STALE"


@pytest.mark.asyncio
async def test_entry_windows_and_phase_labels_use_the_decision_time(tmp_path):
    db, *_ = await _one_tick(tmp_path / "late", _Market(_book(), _breakout_day),
                             _at(TUESDAY, 15, 14, 55), _at(TUESDAY, 15, 15, 5))
    assert _positions(db) == []                                                   # B's window closed in transit
    db, *_ = await _one_tick(tmp_path / "in", _Market(_book(), _breakout_day),
                             _at(TUESDAY, 15, 13, 25), _at(TUESDAY, 15, 13, 35))
    legs = _positions(db)
    assert [r["play"] for r in legs] == ["B", "B", "BH", "BH", "BP", "BP"]
    assert all(r["entry_ts"] == _at(TUESDAY, 15, 13, 35).isoformat() for r in legs)


def test_a_partly_filled_bank_keeps_its_remainder_pending_across_a_restart(tmp_path):
    """Audit probe: 6 lots at 4 reach 12 and the bid takes 1 of 3 lots; v1 forgot the other 2."""
    contract = SimpleNamespace(tradingsymbol="NIFTY26OCT25200CE", token=7, strike=25200.0,
                               instrument_type="CE", lot_size=65)
    t0 = _at(TUESDAY, 14, 0)
    pos = xp._new_position("2026-10-06", "NIFTY", "C", "NFO", contract, 4.0, 6, t0)
    policy = xp.POLICIES["C"]
    action = xp.manage_position(pos, policy, 12.0, t0)
    assert action == (3, "BANK_HALF")
    event = xp._try_exit(pos, xp.Quote(bids=((12.0, 65),), asks=(), ltp=12.0, ts=t0), *action, t0)
    assert event["lots"] == 1 and pos["lots_open"] == 5 and pos["bank_pending"] == 2
    assert pos["exit_pending"] is None

    store = str(tmp_path / "x.db")
    with xp._store(store) as conn:
        xp._save_position(conn, pos)
    with xp._store(store) as conn:
        (pos,) = xp._rows(conn, "SELECT * FROM expiry_paper_positions", ())
    assert pos["bank_pending"] == 2                                               # survives a restart

    t1, t2 = t0 + timedelta(seconds=10), t0 + timedelta(seconds=20)
    assert xp.manage_position(pos, policy, 11.0, t1) is None                      # under the bank level: wait
    action = xp.manage_position(pos, policy, 12.5, t2)
    assert action == (2, "BANK_HALF")
    event = xp._try_exit(pos, xp.Quote(bids=((12.5, 650),), asks=(), ltp=12.5, ts=t2), *action, t2)
    assert event["lots"] == 2 and pos["lots_open"] == 3 and pos["bank_pending"] == 0
    assert xp.manage_position(pos, policy, 13.0, t2 + timedelta(seconds=10)) is None
    expected = xp.buy_charges(4.0, 390) + xp.sell_charges(12.0, 65) + xp.sell_charges(12.5, 130)
    assert pos["costs"] == pytest.approx(expected, abs=0.02)                      # one buy, one fee per sell


@pytest.mark.asyncio
async def test_concurrent_flushes_send_each_notice_once(tmp_path):
    import asyncio

    db = await _run_day(tmp_path, _Market(_book(), _breakout_day), end=(13, 41))
    pending = len(_notices(db))
    delivered = []

    async def slow(message):
        await asyncio.sleep(0.01)
        delivered.append(message)

    counts = await asyncio.gather(xp.flush_notices(slow, db), xp.flush_notices(slow, db))
    assert sorted(counts) == [0, pending] and len(delivered) == len(set(delivered)) == pending


@pytest.mark.asyncio
async def test_an_expiry_whose_index_never_answers_is_still_recorded(tmp_path):
    class _Dark(_Market):
        async def get_quote_by_instruments(self, request):
            self.requests.append(request)
            return {}

    db = await _run_day(tmp_path, _Dark(_book(), _breakout_day), end=(13, 35))
    with sqlite3.connect(xp.expiry_db_path(db)) as conn:
        state = json.loads(conn.execute("SELECT state FROM expiry_paper_days").fetchone()[0])
        ticks = conn.execute("SELECT COUNT(*) FROM expiry_paper_ticks").fetchone()[0]
    assert state["ticks"] == ticks == 217 and state["spot_refusals"] == {"MISSING": 217}
    assert state["box_status"] == "UNUSABLE_0_SAMPLES" and _positions(db) == []
    (summary,) = [m for k, m, _ in _notices(db) if k.endswith(":summary")]
    assert "ticks 217 of 966 slots" in summary and "index refused 217 (MISSING 217)" in summary


def test_charges_follow_the_exchange_and_are_frozen_at_entry(monkeypatch):
    from config import settings

    contract = SimpleNamespace(tradingsymbol="SENSEX26OCT82000CE", token=9, strike=82000.0,
                               instrument_type="CE", lot_size=20)
    now = _at(TUESDAY, 14, 0)
    pos = xp._new_position("2026-10-08", "SENSEX", "A", "BFO", contract, 50.0, 2, now)
    frozen = json.loads(pos["fee_snapshot"])
    assert frozen["market"] == "BSE_EQUITY_OPTIONS_PREMIUM" and pos["execution"] == xp.EXECUTION_VERSION
    assert pos["costs"] < round(xp.buy_charges(50.0, 40, xp.fee_schedule("NFO")), 2)
    monkeypatch.setattr(settings, "FNO_BROKERAGE_FLAT", 40.0)                     # a rate change mid-trade
    event = xp._sell(pos, 2, 60.0, "TRAIL", now)
    assert event["charges"] == pytest.approx(xp.sell_charges(60.0, 40, frozen), abs=0.01)
    assert event["charges"] < xp.sell_charges(60.0, 40, xp.fee_schedule("BFO")) - 10


def test_a_store_from_the_first_day_gains_the_new_columns_and_still_settles(tmp_path):
    db = str(tmp_path / "trading.db")
    with closing(sqlite3.connect(xp.expiry_db_path(db))) as conn, conn:
        conn.execute("""CREATE TABLE expiry_paper_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, underlying TEXT NOT NULL, play TEXT NOT NULL,
            exchange TEXT NOT NULL, symbol TEXT NOT NULL, token INTEGER NOT NULL, strike REAL NOT NULL,
            opt_type TEXT NOT NULL, lot_size INTEGER NOT NULL, lots INTEGER NOT NULL, lots_open INTEGER NOT NULL,
            entry_ts TEXT NOT NULL, entry_price REAL NOT NULL, max_loss REAL NOT NULL, peak REAL NOT NULL,
            stop REAL NOT NULL, banked INTEGER NOT NULL DEFAULT 0, exit_pending TEXT, status TEXT NOT NULL,
            gross REAL NOT NULL DEFAULT 0, costs REAL NOT NULL DEFAULT 0, net_pnl REAL NOT NULL DEFAULT 0,
            assumed_pnl REAL, events TEXT NOT NULL DEFAULT '[]')""")
        conn.execute("INSERT INTO expiry_paper_positions (day, underlying, play, exchange, symbol, token, strike, "
                     "opt_type, lot_size, lots, lots_open, entry_ts, entry_price, max_loss, peak, stop, status, "
                     "costs, net_pnl) VALUES ('2026-10-06', 'NIFTY', 'C', 'NFO', 'NIFTY26OCT25200CE', 7, 25200, "
                     "'CE', 65, 8, 8, '2026-10-06T14:06:00+05:30', 4.1, 2345.36, 4.5, 0, 'OPEN', 24.56, -24.56)")
    assert xp.reconcile(db, now=_at(WEDNESDAY, 9, 45)) == 1
    (row,) = _positions(db)
    assert row["status"] == "UNRESOLVED" and row["bank_pending"] == 0 and row["fee_snapshot"] is None
    assert row["assumed_pnl"] == pytest.approx(-(4.1 * 520 + 8 * xp.order_fee(xp.fee_schedule("NFO"))), abs=0.01)


def test_a_day_begun_under_v1_is_marked_mixed_once(tmp_path):
    store = str(tmp_path / "x.db")
    legacy = xp.new_day_state()
    del legacy["execution"]
    now = _at(TUESDAY, 13, 0)
    with xp._store(store) as conn:
        xp._save_state(conn, "2026-10-06", "NIFTY", legacy, now)
    for _ in range(2):                                                            # load and save on each tick
        with xp._store(store) as conn:
            state = xp._load_state(conn, "2026-10-06", "NIFTY")
            xp._save_state(conn, "2026-10-06", "NIFTY", state, now)
    assert state["execution"] == "expiry-exec-v1+expiry-exec-v2"


# --------------------------------------------------------------------------- shadow plays (expiry-shadow-v1 and v2)

def _whole(rows):
    return sum(r["net_pnl"] + (r["assumed_pnl"] or 0.0) for r in rows)


@pytest.mark.asyncio
async def test_shadow_plays_run_beside_the_main_book_without_telegram_trades(tmp_path):
    db = await _run_day(tmp_path, _Market(_book(), _breakout_day))
    rows = _positions(db)
    by_play = {play: [r for r in rows if r["play"] == play] for play in xp.MAIN_PLAYS + xp.SHADOW_PLAYS}

    # BH: B's legs, held with no bank or trail, sold at 15:38
    assert [r["symbol"] for r in by_play["BH"]] == [r["symbol"] for r in by_play["B"]]
    for leg in by_play["BH"]:
        actions = [e["action"] for e in json.loads(leg["events"])]
        assert actions[0] == "BUY" and set(actions[1:]) <= {"FLAT_TIME", "SETTLED_ASSUMED"}
    # C500: C's strike inside a Rs 500 ceiling
    (c500,) = by_play["C500"]
    assert c500["symbol"] == by_play["C"][0]["symbol"] and c500["max_loss"] <= xp.C500_BUDGET
    # D: the farthest sold strikes inside the ceiling, wings one step further, settled after the session
    d = by_play["D"]
    (steps,) = {json.loads(r["events"])[0]["short_steps"] for r in d}
    atm, out = 25050.0, 50.0 * steps
    assert sorted((r["opt_type"], r["side"], r["strike"]) for r in d) == [
        ("CE", "LONG", atm + out + 50), ("CE", "SHORT", atm + out),
        ("PE", "LONG", atm - out - 50), ("PE", "SHORT", atm - out)]
    assert all(r["entry_ts"].startswith("2026-10-06T14:30") for r in d)
    assert sum(r["max_loss"] for r in d) <= BUDGET and all(r["status"] == "SETTLED_ASSUMED" for r in d)
    assert -_whole(d) <= sum(r["max_loss"] for r in d)

    messages = [m for _, m, _ in _notices(db)]
    trades = [m for m in messages if "summary" not in m and not m.startswith("Expiry paper NIFTY 2026")]
    assert trades and all(any(f"NIFTY {p}:" in m for p in xp.MAIN_PLAYS) for m in trades)
    (summary,) = [m for k, m, _ in _notices(db) if k.endswith(":summary")]
    assert "shadow plays (expiry-shadow-v2" in summary and f"sold NIFTY26OCT{atm + out:.0f}CE" in summary


@pytest.mark.asyncio
async def test_the_condor_loss_stays_inside_its_ceiling_on_a_runaway_close(tmp_path):
    def runaway(now):
        minutes = now.hour * 60 + now.minute
        if minutes < 14 * 60 + 31:
            return 25000.0 + 10.0 * math.sin(minutes)                 # quiet: no breakout, D enters at 14:30
        return 25600.0                                                # far through the call side

    db = await _run_day(tmp_path, _Market(_book(), runaway))
    d = [r for r in _positions(db) if r["play"] == "D"]
    assert len(d) == 4
    ceiling = sum(r["max_loss"] for r in d)
    assert ceiling <= BUDGET
    # Short 25,100 call loses 500, the 25,150 wing makes back 450 less exercise STT.
    assert _whole(d) < 0 and -_whole(d) <= ceiling


@pytest.mark.asyncio
async def test_an_outage_values_the_condor_at_its_maximum_settlement_loss(tmp_path):
    db = await _run_day(tmp_path, _Market(_book(), _breakout_day), end=(14, 35), reconcile_at=None)
    xp.reconcile(db, now=_at(WEDNESDAY, 9, 45))
    d = [r for r in _positions(db) if r["play"] == "D"]
    assert len(d) == 4 and all(r["status"] == "UNRESOLVED" for r in d)
    qty = d[0]["lots"] * 65
    credit = sum(r["entry_price"] * (1 if r["side"] == "SHORT" else -1) for r in d)
    fees = sum(r["costs"] for r in d)
    assert _whole(d) == pytest.approx(-(50.0 - credit) * qty - fees, abs=0.05)
    assert -_whole(d) <= sum(r["max_loss"] for r in d)


def test_condor_sizing_refuses_a_credit_too_small_for_its_charges():
    def leg(price):
        return xp.Quote(bids=((price, 650),), asks=((price + 0.05, 650),), ltp=price, ts=_at(TUESDAY, 14, 30))

    legs = [(leg(0.30), "SHORT"), (leg(0.20), "LONG"), (leg(0.30), "SHORT"), (leg(0.20), "LONG")]
    assert xp.condor_fill(legs, 65, 5.0, 25000.0, BUDGET)[3] == "CREDIT_TOO_SMALL"   # 0.10 credit vs Rs 94 fees
    narrow = [(leg(4.0), "SHORT"), (leg(2.0), "LONG"), (leg(4.0), "SHORT"), (leg(2.0), "LONG")]
    assert xp.condor_fill(narrow, 65, 50.0, 25000.0, BUDGET)[3] == "DEPTH_OR_BUDGET"   # (50 - 3.9) x 65 > 2,500
    legs = [(leg(20.0), "SHORT"), (leg(6.0), "LONG"), (leg(20.0), "SHORT"), (leg(6.0), "LONG")]
    lots, prices, max_loss, refusal = xp.condor_fill(legs, 65, 50.0, 25000.0, BUDGET)
    assert (lots, refusal) == (1, None) and max_loss <= BUDGET
    assert prices == [20.0, 6.05, 20.0, 6.05]                                     # sold on the bid, bought on the ask


# --------------------------------------------------------------------------- chain context (expiry-context-v1)

def test_max_pain_and_realized_volatility_math():
    # Settling at 105 pays 10 (the one-unit 100 call and 110 put); 100 or 110 pays 60.
    assert xp.max_pain({(100.0, "CE"): 1, (105.0, "CE"): 10, (110.0, "CE"): 0,
                        (100.0, "PE"): 0, (105.0, "PE"): 10, (110.0, "PE"): 1}) == 105.0
    assert xp.max_pain({}) is None and xp.max_pain({(100.0, "CE"): 0}) is None

    state, start = {}, _at(TUESDAY, 13, 0)
    for minute in range(11):
        xp.update_realized(state, start + timedelta(minutes=minute), 100.0 if minute % 2 == 0 else 101.0)
        xp.update_realized(state, start + timedelta(minutes=minute, seconds=30), 150.0)   # too soon: ignored
        if minute < 10:
            assert xp.realized_vol(state) is None                                        # under ten minutes
    expected = math.sqrt(10 * math.log(1.01) ** 2 / 600.0 * xp.TRADING_YEAR_SEC)
    assert xp.realized_vol(state) == pytest.approx(expected)


def test_chain_context_reads_the_straddle_walls_and_oi_change():
    now, spot = _at(TUESDAY, 14, 30), 25000.0
    straddle = math.sqrt(2 / math.pi) * spot * 0.12 * math.sqrt(65 * 60 / xp.TRADING_YEAR_SEC)

    def chain(extra_ce_oi=0):
        out = {}
        for strike in (24900.0, 25000.0, 25100.0):
            for kind in ("CE", "PE"):
                mid = straddle / 2 if strike == 25000.0 else 5.0
                oi = {24900.0: 300, 25000.0: 200, 25100.0: 100}[strike] if kind == "PE" else \
                    {24900.0: 100, 25000.0: 200, 25100.0: 400 + extra_ce_oi}[strike]
                out[(strike, kind)] = (None, xp.Quote(bids=((mid - 0.05, 650),), asks=((mid + 0.05, 650),),
                                                      ltp=mid, ts=now, oi=float(oi)))
        return out

    state = {}
    first = xp.chain_context(state, chain(), spot, 50.0, 25020.0, 9_000_000.0, now)
    assert first["iv"] == pytest.approx(0.12, abs=1e-4) and first["straddle"] == pytest.approx(straddle, abs=0.01)
    assert (first["put_wall"], first["call_wall"], first["pcr"]) == (24900.0, 25100.0, round(600 / 700, 3))
    assert first["ce_oi_chg"] == 0 and "rv" not in first
    later = xp.chain_context(state, chain(extra_ce_oi=250), spot, 50.0, 25040.0, 9_100_000.0,
                             now + timedelta(seconds=10))
    assert (later["ce_oi_chg"], later["pe_oi_chg"], later["top_ce_add"]) == (250, 0, 25100.0)
    assert later["fut_buildup"] == "LONG_BUILDUP" and later["fut_oi_chg"] == 100_000
    assert xp.chain_context({}, chain(), None, 50.0, None, None, now)["status"] == "NO_FRESH_INDEX"


@pytest.mark.asyncio
async def test_chain_context_is_recorded_and_changes_no_trade(tmp_path):
    plain = await _run_day(tmp_path / "plain", _Market(_book(), _breakout_day))
    with_oi = await _run_day(tmp_path / "oi", _Market(_book(), _breakout_day, oi=True))
    assert _positions(with_oi) == _positions(plain)                     # record-only: identical trades

    with closing(sqlite3.connect(xp.expiry_db_path(with_oi))) as conn:
        (state,) = [json.loads(r[0]) for r in conn.execute("SELECT state FROM expiry_paper_days")]
        (payload,) = [json.loads(r[0]) for r in conn.execute(
            "SELECT quotes FROM expiry_paper_ticks WHERE ts LIKE '%T14:30:00%'")]
    assert state["context"] == xp.CONTEXT_VERSION
    assert payload["context"]["status"] == "OK" and all(leg["oi"] is not None for leg in payload["legs"].values())
    assert payload["future"]["oi"] > 0                                  # a replay can rebuild the future's build-up
    snaps = state["context_at"]
    assert snaps["d_entry"]["ts"].startswith("2026-10-06T14:30:00")
    assert snaps["b_entry"]["ts"].startswith("2026-10-06T15:13:30")
    assert (snaps["d_entry"]["put_wall"], snaps["d_entry"]["call_wall"]) == (24900.0, 25200.0)
    assert snaps["d_entry"]["rv"] > 0 and snaps["d_entry"]["iv"] > 0
    assert all(s["context"]["status"] == "OK" for s in state["signals"])
    (summary,) = [m for k, m, _ in _notices(with_oi) if k.endswith(":summary")]
    assert "context (expiry-context-v1.1, record-only" in summary
    assert "walls 24,900 PE / 25,200 CE" in summary and "close 25,060.00 (our sample)" in summary
    assert "inside the walls yes" in summary


@pytest.mark.asyncio
async def test_a_context_failure_never_costs_the_tick(tmp_path, monkeypatch):
    def broken(*args):
        raise ZeroDivisionError

    monkeypatch.setattr(xp, "chain_context", broken)
    at = _at(TUESDAY, 13, 0)
    _, _, spot, payload = await _one_tick(tmp_path, _Market(_book(), _breakout_day, oi=True), at, at)
    assert spot is not None and payload["context"] == {"status": "ERROR", "ts": at.isoformat(),
                                                       "error": "ZeroDivisionError"}


@pytest.mark.asyncio
@pytest.mark.parametrize("far", [30000.0, 20000.0])                     # +20% / -20% settlement stress
async def test_a_move_beyond_the_reserve_is_recorded_as_a_breach_not_capped_t2(tmp_path, far):
    # Oct 7 audit T2: the 5% exercise-STT reserve is a bound only inside its
    # domain. Past it the loss exceeds max_loss; it is reported, never capped.
    def stress(now):
        minutes = now.hour * 60 + now.minute
        if minutes < 14 * 60 + 31:
            return 25000.0 + 10.0 * math.sin(minutes)
        return far

    db = await _run_day(tmp_path, _Market(_book(), stress))
    d = [r for r in _positions(db) if r["play"] == "D"]
    assert len(d) == 4
    ceiling = sum(r["max_loss"] for r in d)
    breaches = [e["reserve_breach"] for r in d for e in json.loads(r["events"]) if e.get("reserve_breach")]
    assert len(breaches) == 1                                            # only the ITM wing
    assert -_whole(d) > ceiling                                          # the bound is conditional
    assert -_whole(d) <= ceiling + breaches[0]["stt_beyond_reserve"] + 1.0   # and the excess is reported
    (summary,) = [m for k, m, _ in _notices(db) if k.endswith(":summary")]
    assert "RESERVE BREACH" in summary


# --------------------------------------------------------------------------- October 8 audit (first SENSEX expiry)

@pytest.mark.asyncio
async def test_the_slot_count_matches_the_ticks_the_scheduler_can_run_t5(tmp_path):
    # 12:59:00 through 15:39:50 is 966 starts; the 15:40:00 callback never runs.
    assert xp.EXPECTED_SLOTS == 966
    market = _Market(_book(), _breakout_day)
    market.now = _at(TUESDAY, 15, 40)
    await xp.run_expiry_tick(market, str(tmp_path / "t.db"), now=market.now, books={"NIFTY": market.book})
    assert market.requests == []


def test_stale_oi_is_left_out_of_the_walls_and_pcr_t4():
    now = _at(TUESDAY, 14, 30)

    def quote(oi, age=0):
        return (None, xp.Quote(bids=((5.0, 650),), asks=((5.1, 650),), ltp=5.0,
                               ts=now - timedelta(seconds=age), oi=float(oi)))

    chain = {(24900.0, "PE"): quote(300), (25000.0, "PE"): quote(5000, age=120),
             (25000.0, "CE"): quote(200), (25100.0, "CE"): quote(400)}
    ctx = xp.chain_context({}, chain, 25000.0, 50.0, None, None, now)
    assert (ctx["oi_fresh"], ctx["oi_window"]) == (3, 4)
    assert ctx["put_wall"] == 24900.0 and ctx["pcr"] == round(300 / 600, 3)      # the stale 5,000 is not read
    assert "iv" not in ctx                                                       # its ATM put is stale too


@pytest.mark.asyncio
async def test_the_expiry_quote_batch_waits_in_the_management_lane(tmp_path):
    import kite_client

    lanes = []

    class _Lane(_Market):
        async def get_quote_by_instruments(self, request):
            lanes.append(kite_client._provider_lane.get())
            return await super().get_quote_by_instruments(request)

    await _one_tick(tmp_path, _Lane(_book(), _breakout_day), _at(TUESDAY, 13, 40), _at(TUESDAY, 13, 40))
    assert lanes and set(lanes) == {"management"}
    assert kite_client._provider_lane.get() == "normal"                          # the lane ends with the batch


def test_liquidation_net_marks_the_whole_quantity_on_fresh_depth_only():
    t = _at(TUESDAY, 14, 0)

    def leg(token, side, entry, net, lots=2, status="OPEN"):
        return {"token": token, "side": side, "entry_price": entry, "net_pnl": net, "assumed_pnl": None,
                "status": status, "lots_open": lots, "lot_size": 65, "fee_snapshot": None, "exchange": "NFO"}

    legs = [leg(1, "LONG", 10.0, -25.0), leg(2, "SHORT", 8.0, -26.0), leg(3, "LONG", 4.0, 300.0, 0, "CLOSED")]
    quotes = {1: xp.Quote(bids=((12.0, 100), (11.0, 100)), asks=(), ltp=12.0, ts=t),
              2: xp.Quote(bids=(), asks=((5.0, 130),), ltp=5.0, ts=t)}
    long_price = (12.0 * 100 + 11.0 * 30) / 130                                  # walks two bid levels
    expected = (-25.0 + (long_price - 10.0) * 130 - xp.sell_charges(long_price, 130)
                - 26.0 + 3.0 * 130 - xp.buy_charges(5.0, 130) + 300.0)       # the short buys back on the ask
    assert xp.liquidation_net(legs, quotes, t) == pytest.approx(expected, abs=0.01)
    shallow = {**quotes, 1: xp.Quote(bids=((12.0, 100),), asks=(), ltp=12.0, ts=t)}
    stale = {**quotes, 2: xp.Quote(bids=(), asks=((5.0, 130),), ltp=5.0, ts=t - timedelta(seconds=60))}
    assert xp.liquidation_net(legs, shallow, t) is None                          # not enough depth: no mark
    assert xp.liquidation_net(legs, stale, t) is None
    assert xp.liquidation_net(legs, {1: quotes[1]}, t) is None                   # a missing quote is not zero


def test_al_one_lot_keeps_half_its_peak_gain_where_a_keeps_entry_x105():
    t = _at(TUESDAY, 13, 42)
    a, al = _pos(lots=1), _pos(lots=1, play="AL")
    a["lots"] = al["lots"] = 1
    assert xp.manage_position(a, xp.POLICIES["A"], 28.5, t) is None
    assert xp.manage_position(al, xp.POLICIES["AL"], 28.5, t) is None
    assert a["stop"] == pytest.approx(21.0) and al["stop"] == pytest.approx(24.25)   # 20 + half of 8.5
    later = t + timedelta(seconds=10)
    xp.manage_position(a, xp.POLICIES["A"], 32.0, later)
    xp.manage_position(al, xp.POLICIES["AL"], 32.0, later)
    assert a["stop"] == pytest.approx(21.0) and al["stop"] == pytest.approx(26.0)    # rises with the peak
    fall = later + timedelta(seconds=10)
    assert xp.manage_position(a, xp.POLICIES["A"], 25.9, fall) is None
    assert xp.manage_position(al, xp.POLICIES["AL"], 25.9, fall) == (1, "TRAIL")
    two = _pos(lots=2, play="AL")
    two["lots"] = 2
    assert xp.manage_position(two, xp.POLICIES["AL"], 28.5, t) == (1, "BANK_HALF")   # two lots: A's bank
    assert two["stop"] == pytest.approx(21.0)


@pytest.mark.asyncio
async def test_al_takes_a_entries_with_its_own_exits(tmp_path):
    db = await _run_day(tmp_path, _Market(_book(), _breakout_day))
    rows = _positions(db)
    first_a = next(r for r in rows if r["play"] == "A")
    first_al = next(r for r in rows if r["play"] == "AL")
    assert (first_al["symbol"], first_al["entry_ts"], first_al["entry_price"], first_al["lots"]) == \
        (first_a["symbol"], first_a["entry_ts"], first_a["entry_price"], first_a["lots"])
    assert not [k for k, m, _ in _notices(db) if " AL:" in m and not k.endswith(":summary")]   # summary only


@pytest.mark.asyncio
async def test_bp_sells_the_strangle_as_one_trade_at_its_target(tmp_path):
    def late_run(now):
        minutes = now.hour * 60 + now.minute
        if minutes < 15 * 60 + 16:
            return 25000.0 + 10.0 * math.sin(minutes)                 # quiet: no break, B enters at 15:13:30
        return 25150.0                                                # the call side runs

    db = await _run_day(tmp_path, _Market(_book(), late_run))
    rows = _positions(db)
    bp, bh = [r for r in rows if r["play"] == "BP"], [r for r in rows if r["play"] == "BH"]
    assert len(bp) == 2 and [r["symbol"] for r in bp] == [r["symbol"] for r in bh]
    exits = [json.loads(r["events"])[-1] for r in bp]
    assert all(r["status"] == "CLOSED" for r in bp)
    assert {e["action"] for e in exits} == {"PAIR_TARGET"} and {e["ts"] for e in exits} == {
        _at(TUESDAY, 15, 16).isoformat()}                             # both legs, the first tick at target
    paid = sum(r["entry_price"] * r["lots"] * r["lot_size"] for r in bp)
    assert _whole(bp) >= xp.BP_TARGET * paid
    assert all(json.loads(r["events"])[-1]["action"] in ("FLAT_TIME", "SETTLED_ASSUMED") for r in bh)
    with closing(sqlite3.connect(xp.expiry_db_path(db))) as conn:
        state = json.loads(conn.execute("SELECT state FROM expiry_paper_days").fetchone()[0])
    mark = state["marks"][f"BP {bp[0]['entry_ts']}"]
    assert mark["best"] == pytest.approx(_whole(bp)) and mark["best_ts"] == exits[0]["ts"]   # marked at its fills
    (summary,) = [m for k, m, _ in _notices(db) if k.endswith(":summary")]
    assert "  BP: filled net" in summary and "    entry 15:13:30: best Rs" in summary
    assert "path per entry" in summary and "D ENTRY" not in summary
    assert "D entry 14:30:00, read 14:30:00" in summary
