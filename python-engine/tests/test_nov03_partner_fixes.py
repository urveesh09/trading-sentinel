"""N03: fixes from the two Nov 2 partner audits (Production evidence, 2026-11-02).

- P1: a plan prices the option on its own expiry's forward, not the monthly future's.
- L1/L2: every stop moved down is told; a stop still in profit gives back profit, it adds to no loss.
- C1: the close countdown is the time left when the message is built.
- R1, E1, K1, K2: in test_partner_watch, test_partner_buyer and test_partner_coach.
"""
import json
from datetime import date, datetime, timedelta

import aiosqlite
import pandas as pd
import pytest
import pytz

import partner_watch as pw

IST = pytz.timezone("Asia/Kolkata")
NOW = IST.localize(datetime(2026, 11, 2, 10, 37, 33))


def _fut_bars(level: float) -> pd.DataFrame:
    idx = pd.date_range("2026-11-02 09:15", periods=17, freq="5min")
    return pd.DataFrame({"open": level, "high": level + 40.0, "low": level - 40.0, "close": level}, index=idx)


def _plan(opt_type="CE", entry=329.3, mid=327.45, strike=75800.0, **kw) -> pw.Plan:
    return pw.build_plan(entry=entry, qty=20, exchange="BFO", opt_type=opt_type, strike=strike,
                         expiry=date(2026, 11, 5), now=NOW, bought_at=NOW - timedelta(seconds=1), cash=28528.8,
                         option_bars=None, fut_bars=_fut_bars(75711.05), fut_price=75711.05, option_mid=mid, **kw)


def test_a_call_plan_is_priced_on_the_options_own_forward():
    """Nov 2, SENSEX 75800 CE (5 Nov) bought at 329.30 with the Nov 26 future at 75,711: priced on the future, the
    option's volatility read about 13% and its delta about 0.46, the stop came out too low and the target too
    high (the plan said 270.20 / 450.35; the card, priced on the chain's parity, ≈272.60 / 360-423)."""
    old = _plan()
    carry = _plan(fut_expiry=date(2026, 11, 26))
    parity = _plan(fut_expiry=date(2026, 11, 26), forward=75370.0)
    assert old.iv < 0.15                                       # the fault: a weekly priced off the monthly future
    assert 0.15 < parity.iv < 0.25 and parity.delta < old.delta
    assert parity.index_stop_option > old.index_stop_option and parity.target < old.target
    assert carry.delta < old.delta and carry.index_stop_option > old.index_stop_option and carry.target < old.target
    # The levels stay on the future, as the message names them; only the option's price at them changes.
    assert (old.stop_index, old.target_index) == (parity.stop_index, parity.target_index) == (
        carry.stop_index, carry.target_index)


def test_a_put_plan_moves_the_other_way():
    old = _plan("PE", entry=420.0, mid=419.0, strike=75700.0)
    parity = _plan("PE", entry=420.0, mid=419.0, strike=75700.0, fut_expiry=date(2026, 11, 26), forward=75370.0)
    assert parity.iv < old.iv and abs(parity.delta) > abs(old.delta)
    assert parity.index_stop_option < old.index_stop_option and parity.target > old.target


def test_the_forward_falls_back_safely():
    own, basis = pw.option_forward(75711.0, now=NOW, expiry=date(2026, 11, 5), fut_expiry=date(2026, 11, 26),
                                   forward=75370.0)
    assert basis == "PARITY" and own(75711.0) == pytest.approx(75370.0) and own(75600.0) == pytest.approx(75259.0)
    # A parity read more than 2% away is not used: carry from the future's expiry instead.
    own, basis = pw.option_forward(75711.0, now=NOW, expiry=date(2026, 11, 5), fut_expiry=date(2026, 11, 26),
                                   forward=70000.0)
    assert basis == "CARRY" and 75300.0 < own(75711.0) < 75711.0
    # Without the future's expiry (or the same expiry): as before.
    assert pw.option_forward(75711.0, now=NOW, expiry=date(2026, 11, 5))[1] == "FUTURE"
    assert pw.option_forward(75711.0, now=NOW, expiry=date(2026, 11, 26), fut_expiry=date(2026, 11, 26))[1] == "FUTURE"
    # Parity: F = K + (C - P) e^(rT); nothing without both prices.
    assert pw.parity_forward(100.0, 60.0, 23300.0, 1 / 365) == pytest.approx(23340.0, abs=0.1)
    assert pw.parity_forward(100.0, None, 23300.0, 1 / 365) is None


def test_a_stop_still_in_profit_gives_back_profit_and_is_not_called_a_loss():
    """Nov 2: "you moved your stop down ₹125 → ₹121. If it is hit: +₹2,003 instead of +₹2,522. A stop moved down
    adds to the loss you chose when you placed it." (NIFTY 23250 CE, 130 at 104.95)."""
    trip = pw.Trip("1", "NFO", "NIFTY26N0323250CE", "NRML", NOW, bought=130, buy_value=130 * 104.95)
    for reason in ("FIRST", "AGAIN"):
        text = pw.lowered_text(trip, 125.0, 121.0, reason)
        assert text.endswith("A stop moved down gives back profit it had kept for you.")
        assert "adds to the loss" not in text
    # Under the buy price the old wording stays.
    assert pw.lowered_text(trip, 100.0, 95.0, "FIRST").endswith(
        "A stop moved down adds to the loss you chose when you placed it.")


@pytest.mark.parametrize("at, said", [
    ((15, 20, 0), "20 minutes to the 15:40 close"),
    ((15, 30, 28), "9 minutes to the 15:40 close"),       # Nov 2: this one said "20 minutes"
    ((15, 38, 30), "1 minute to the 15:40 close"),
    ((15, 39, 40), "Under a minute to the 15:40 close"),
])
def test_the_close_countdown_is_the_time_left_when_sent(at, said):
    now = IST.localize(datetime(2026, 11, 2, *at))
    trip = pw.Trip("1", "NFO", "NIFTY26N0323550CE", "NRML", now, bought=130, buy_value=130 * 15.3)
    assert pw.close_text(trip, expiry_today=False, theta_day=None, now=now).startswith(f"⏳ {said} and you still hold")
    assert pw.close_text(trip, expiry_today=False, theta_day=None).startswith("⏳ 20 minutes to the 15:40 close")


# ---------------------------------------------------------------------------
# N04-A: one plan for a carded buy
# ---------------------------------------------------------------------------

CARD = {"advisory_id": "0ab0de69", "underlying": "SENSEX", "at": "10:36",
        "delivered_at": "2026-11-02T10:36:52.167470+05:30", "fill_by": "2026-11-02T10:46:50.372729+05:30",
        "buy_limit": 324.2, "sl": 272.6, "target_low": 359.8, "target": 423.3, "basis": "INDEX",
        "stop_level": 75284.11, "target_level": 75654.16, "closed": None}


def _trip(at, price, qty=20, symbol="SENSEX26N0575800CE"):
    return pw.Trip("k", "BFO", symbol, "NRML", IST.localize(datetime(2026, 11, 2, *at)), bought=qty,
                   buy_value=qty * price, buy_orders=1)


def test_a_buy_stands_to_its_card_by_window_close_and_stop():
    """Nov 2: the 10:37 buy at 329.30 was inside the 10:36 card's window; the 11:37 re-entry at 283.80 was after
    its 10:46 skip-after (and before its 11:40 exit)."""
    assert pw.card_relation(CARD, _trip((10, 37, 32), 329.3)) == "ON_CARD"
    assert pw.card_relation(CARD, _trip((10, 47, 30), 329.3)) == "ON_CARD"           # filled within the grace
    assert pw.card_relation(CARD, _trip((11, 37, 0), 283.8)) == "AFTER_WINDOW"
    closed = dict(CARD, closed={"event": "INVALIDATION", "at": "2026-11-02T10:40:00+05:30"})
    assert pw.card_relation(closed, _trip((10, 41, 0), 300.0)) == "AFTER_CLOSE"
    assert pw.card_relation(CARD, _trip((10, 38, 0), 270.0)) == "UNDER_STOP"
    assert pw.card_relation(None, _trip((10, 38, 0), 300.0)) is None
    assert pw.card_relation(dict(CARD, sl=None), _trip((10, 37, 32), 329.3)) is None     # no premium stop


def test_a_buy_inside_the_card_window_takes_the_cards_stop_and_target():
    trip = _trip((10, 37, 32), 329.3)
    plan = pw.Plan(entry=329.3, qty=20, stop=270.2, stop_basis="INDEX", stop_index=75579.0, target=450.35,
                   target_index=75949.0, cash=28528.8, swing=29.17)
    carded = pw.adopt_card(plan, CARD, "BFO")
    assert (carded.stop, carded.stop_basis, carded.target) == (272.6, "CARD", 423.3)
    text = pw.plan_text(trip, carded, lots=1, card=CARD, card_relation_="ON_CARD")
    lines = text.splitlines()
    assert lines[0] == "🟢 You bought SENSEX 75800 CE · 1 lot (20) at ₹329.3 on the 10:36 card"
    assert lines[1] == "⚠️ You paid ₹329.3; the card said buy up to ₹324.2."
    assert lines[2].startswith("🛑 The card's stop ₹272.6 (or exit on a 5-min close under SENSEX ≈75,284). If it sells there:")
    assert "🎯 The card's target: option ≈₹360–423 (SENSEX ≈75,654)." in lines        # as the card says it
    assert "450.35" not in text and "270.2" not in text                       # one set of levels, the card's


def test_a_buy_outside_the_card_says_it_is_not_the_cards_trade():
    trip = _trip((11, 37, 0), 283.8, qty=40)
    plan = pw.Plan(entry=283.8, qty=40, stop=238.5, stop_basis="INDEX", stop_index=75582.0, target=372.95,
                   target_index=75870.0, cash=28528.8, loss=1881.89)
    text = pw.plan_text(trip, plan, lots=2, card=CARD, card_relation_="AFTER_WINDOW")
    assert text.splitlines()[1] == ("• Not the 10:36 card's trade: its buy window ended 10:46. This plan is for your "
                                    "own buy.")
    closed = dict(CARD, closed={"event": "INVALIDATION", "at": "2026-11-02T11:40:50+05:30"})
    assert pw._card_note(closed, "AFTER_CLOSE") == ("• Not the 10:36 card's trade: that card closed at 11:40 (stop "
                                                     "level hit). This plan is for your own buy.")
    assert "under its stop ₹272.6" in pw._card_note(CARD, "UNDER_STOP")
    assert pw.plan_text(trip, plan, lots=2).splitlines()[1].startswith("🛑 Plan stop ₹238.5")    # no card: as before


@pytest.mark.asyncio
async def test_the_card_is_read_from_the_delivered_card_and_its_updates(tmp_path):
    from hedge_advisory import init_hedge_advisory_db
    from partner_manual_advisory import init_partner_advisory_db
    db_path = str(tmp_path / "t.db")
    await init_hedge_advisory_db(db_path)
    await init_partner_advisory_db(db_path)
    view = {"symbol": "SENSEX26N0575800CE", "quote_at": "2026-11-02T10:36:50.372729+05:30",
            "fill_by": CARD["fill_by"], "buy_limit": 324.2, "sl_premium": 272.6, "target_premium_low": 359.8,
            "target_premium": 423.3, "level_basis": "INDEX", "invalidation_index": 75284.11,
            "target_index": 75654.16}
    payload = {"session_date": "2026-11-02", "buyer_view": view}
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO partner_advisory_ideas(advisory_id,economic_version,scope,underlying,exchange,status,evidence,"
            "profile_id,profile_version,quote_time,valid_until,rendered_card,payload,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("0ab0de69", "v", "MARKET_SETUP", "SENSEX", "BSE", "DELIVERED", "RESEARCH_ONLY", "default", 1,
             view["quote_at"], view["quote_at"], "card", json.dumps(payload), view["quote_at"], view["quote_at"]))
        await db.execute("INSERT INTO partner_advisory_updates(update_id,advisory_id,event_type,observed_at,"
                         "observed_underlying,rendered_update,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                         ("u1", "0ab0de69", "INVALIDATION", "2026-11-02T11:40:00+05:30", 75636.0, "exit",
                          "DELIVERED_ACKNOWLEDGED", "2026-11-02T11:40:00+05:30", "2026-11-02T11:40:50+05:30"))
        for kind, key, at in (("manual_market_advisory", "0ab0de69", "2026-11-02T10:36:52.167470+05:30"),
                              ("manual_advisory_update", "u1", "2026-11-02T11:40:50.790856+05:30")):
            await db.execute("INSERT INTO partner_hedge_messages(kind,dedup_key,sent_at,delivered) VALUES(?,?,?,1)",
                             (kind, key, at))
        await db.commit()
    card = await pw.card_for(db_path, "2026-11-02", _trip((10, 37, 32), 329.3))
    assert {k: card[k] for k in ("at", "sl", "target", "target_low", "buy_limit", "stop_level")} == {
        "at": "10:36", "sl": 272.6, "target": 423.3, "target_low": 359.8, "buy_limit": 324.2, "stop_level": 75284.11}
    assert card["closed"] == {"event": "INVALIDATION", "at": "2026-11-02T11:40:50.790856+05:30"}
    assert pw.card_relation(card, _trip((10, 37, 32), 329.3)) == "ON_CARD"           # the exit came later
    assert pw.card_relation(card, _trip((11, 41, 0), 270.0)) == "AFTER_CLOSE"
    assert await pw.card_for(db_path, "2026-11-02", _trip((10, 36, 0), 320.0)) is None       # before the card
    assert await pw.card_for(db_path, "2026-11-02", _trip((10, 40, 0), 90.0, symbol="SENSEX26N0576400CE")) is None
    assert await pw.card_for(str(tmp_path / "empty.db"), "2026-11-02", _trip((10, 37, 32), 329.3)) is None


# ---------------------------------------------------------------------------
# N04-B: the day's giveback from its best
# ---------------------------------------------------------------------------

def _closed(n, buy, sell, sold_at, qty=65):
    at = IST.localize(datetime(2026, 11, 2, *sold_at))
    return pw.Trip(str(n), "NFO", "NIFTY26N0323250CE", "NRML", at - timedelta(minutes=5), bought=qty, sold=qty,
                   buy_value=qty * buy, sell_value=qty * sell, buy_orders=1, sell_orders=1, closed_at=at)


def test_the_day_counts_what_it_gave_back_from_its_best_while_still_up():
    cash = 7536.7                                           # a step is ₹753.67
    win = _closed(1, 80.0, 100.0, (10, 5))
    trips = [win, _closed(2, 80.0, 72.0, (10, 15)), _closed(3, 80.0, 75.0, (10, 25))]
    day = pw.day_so_far(trips, cash)
    assert day["best"] == win.realised() and day["best_at"] == win.closed_at
    assert day["given"] == round(day["best"] - day["net"], 2) and day["net"] > 0
    assert day["giveback"] == int(day["given"] // (0.10 * cash)) == 1 and day["step"] == 0
    first = pw.day_text(day, cash, giveback=True).splitlines()[0]
    assert first == (f"📉 Today so far: {pw._signed(day['net'])} after charges, {pw._amt(day['given'])} under "
                     f"today's best ({pw._signed(day['best'])} at 10:05): {pw._pct_down(day['given'] / cash)} of your "
                     f"₹7,537 cash given back.")
    assert pw.day_so_far(trips[:2], cash)["giveback"] == 0                       # under one step given back
    under = pw.day_so_far(trips + [_closed(4, 80.0, 74.0, (10, 35))], cash)
    assert under["net"] < 0 and under["giveback"] == 0                          # under zero: the loss steps tell it
    losing = pw.day_so_far([_closed(5, 80.0, 70.0, (10, 5))], cash)
    assert losing["best"] == 0 and losing["giveback"] == 0                      # never up: nothing given back


# ---------------------------------------------------------------------------
# N04-D: OI walls around the chain's own forward; N04-G: every buy order costed
# ---------------------------------------------------------------------------

def test_oi_walls_are_found_around_the_chains_own_forward():
    """Nov 2: NIFTY's monthly future sat ~82 points over the index; walls found around it put "support 23,300
    held" beside NIFTY ≈23,259."""
    from types import SimpleNamespace

    import fno_analytics
    q = lambda oi: SimpleNamespace(oi=oi)
    snap = SimpleNamespace(forward=23345.0, parity_forward=23262.0, quotes={
        (23300.0, "PE"): q(9_000_000), (23200.0, "PE"): q(6_000_000), (23300.0, "CE"): q(4_000_000),
        (23400.0, "CE"): q(8_000_000), (23500.0, "CE"): q(5_000_000)})
    assert fno_analytics.oi_walls(snap) == (23300.0, 23400.0)                         # the owner's paths: as before
    assert fno_analytics.oi_walls(snap, reference=snap.parity_forward) == (23200.0, 23400.0)
    import partner_orchestrator
    assert partner_orchestrator._partner_walls(snap) == (23200.0, 23400.0)
    assert partner_orchestrator._partner_walls(SimpleNamespace(forward=23345.0, parity_forward=None,
                                                               quotes=snap.quotes)) == (23300.0, 23400.0)


def test_the_loss_at_the_stop_counts_every_buy_order():
    """Nov 2 ADDED: 40 SENSEX 75800 CE at 326.15 after two buys; at the plan stop 270.20 the message said −₹2,311
    on a two-order round trip; with the second buy order it is ₹23.60 more."""
    from partner_coach import round_trip_costs
    trip = pw.Trip("k", "BFO", "SENSEX26N0575800CE", "NRML", NOW, bought=40, buy_value=20 * 329.3 + 20 * 323.0,
                   buy_orders=2, buys={"a": {"qty": 20, "value": 20 * 329.3}, "b": {"qty": 20, "value": 20 * 323.0}})
    two = round((270.2 - 326.15) * 40 - round_trip_costs(326.15, 270.2, 40, "BFO"), 2)
    three = pw._result_at(trip, 270.2)
    assert three == round((270.2 - 326.15) * 40 - round_trip_costs(326.15, 270.2, 40, "BFO", orders=3), 2)
    assert round(two - three, 2) == 23.6
    single = pw.Trip("k", "BFO", "SENSEX26N0575800CE", "NRML", NOW, bought=20, buy_value=20 * 329.3, buy_orders=1)
    assert pw._result_at(single, 270.2) == round((270.2 - 329.3) * 20 - round_trip_costs(329.3, 270.2, 20, "BFO"), 2)


# ---------------------------------------------------------------------------
# N04-H: the card's strike is at its own expiry's money
# ---------------------------------------------------------------------------

def _card_chain(parity_index: float, fut: float = 22535.0):
    import math as _m

    from fno_chain import RISK_FREE_RATE, ChainSnapshot, years_to_expiry
    from fno_instruments import FnoInstruments
    from fno_models import Contract, ContractQuote, OptionType
    now = IST.localize(datetime(2026, 10, 9, 9, 54, 50))
    expiry = date(2026, 10, 13)
    book = FnoInstruments("NIFTY", segment="NFO")
    strikes = range(22300, 22801, 50)
    book._load_contracts([Contract(1, "NIFTY26OCTFUT", "NIFTY", date(2026, 10, 27), 0.0, "FUT", 65)] + [
        Contract(10 + i, f"NIFTY26O13{s}{k}", "NIFTY", expiry, float(s), k, 65)
        for i, (s, k) in enumerate((s, k) for s in strikes for k in ("CE", "PE"))])
    forward = parity_index * _m.exp(RISK_FREE_RATE * years_to_expiry(expiry, now))
    quotes = {}
    for s in strikes:
        for k in ("CE", "PE"):
            intrinsic = max(forward - s, 0) if k == "CE" else max(s - forward, 0)
            mid = intrinsic + 60.0
            quotes[(float(s), k)] = ContractQuote(contract=book.option(expiry, float(s), OptionType(k)), bid=mid - 0.1,
                                                  ask=mid + 0.1, ltp=mid, oi=10_000, volume=5_000,
                                                  last_trade_time=now, bid_quantity=500, ask_quantity=500)
    return ChainSnapshot(now, expiry, fut, forward, 65, None, quotes), book, now


def test_the_card_strike_is_at_the_money_of_its_own_expiry():
    """The future 22,535 sits ~110 over the index (22,425): the old "ATM" 22550 was two strikes out of the money
    for a call and two in it for a put. Now the long leg is at the parity forward's strike."""
    from fno_models import FnoDirection
    from partner_manual_advisory import build_directional_debit_spread, chain_atms
    snap, book, now = _card_chain(22425.0)
    assert chain_atms(snap, book) == [22450.0, 22550.0]
    call = build_directional_debit_spread(snap, book, FnoDirection.LONG, now, trigger_level=22522.0,
                                          invalidation_level=22475.0, target_level=22628.0)
    put = build_directional_debit_spread(snap, book, FnoDirection.SHORT, now, trigger_level=22500.0,
                                         invalidation_level=22560.0, target_level=22420.0)
    bought = lambda c: next(leg for leg in c.legs if leg.side == "BUY").strike
    assert bought(call) == 22450.0 and bought(put) == 22450.0
    # No sane parity (or one more than 2% off): the future's strike, as before.
    snap.parity_forward = None
    assert chain_atms(snap, book) == [22550.0]
    snap.parity_forward = 22535.0 * 1.05
    assert chain_atms(snap, book) == [22550.0]


# ---------------------------------------------------------------------------
# N05-R1: the wrap's card result is the card's own exit
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_wrap_ends_a_card_at_its_premium_sl_when_that_came_first(monkeypatch):
    """Nov 2: the 75800 CE crossed the card's SL 272.60 before its 11:40 index stop; the wrap said "stopped 11:40 ·
    option ₹317.45 → ₹281.25 at 11:37, just before the stop (−11%)"."""
    import fno_oi_store
    import partner_orchestrator as po
    day = "2026-11-02"
    card = {"time": "10:36", "event": "INVALIDATION", "event_time": "11:40", "event_at": f"{day}T11:40:00+05:30",
            "signal_at": f"{day}T10:36:51+05:30", "exit_by": f"{day}T15:15:00+05:30",
            "buyer_view": {"strike": 75800.0, "opt_type": "CE", "ask": 317.45, "sl_premium": 272.6,
                           "expiry": "2026-11-05"}}

    async def series(*_a, **_k):
        return [(f"{day} 10:37:00", 318.9), (f"{day} 11:37:00", 281.25), (f"{day} 11:38:00", 270.0),
                (f"{day} 11:42:00", 267.5), (f"{day} 12:16:00", 333.7)]

    monkeypatch.setattr(fno_oi_store, "strike_ltp_series", series)
    out = await po._buyer_card_outcome("SENSEX", day, card)
    assert out["outcome"] == "🛑 SL ₹272.6 hit by 11:38 (5-min prints)"
    assert out["premium"].startswith("option ₹317.45 → SL ₹272.6 by 11:38 (-14%)")
    assert "after exit (not held) peak ₹333.7" in out["premium"]

    async def held_above(*_a, **_k):                       # the SL never reached: the index stop is the exit
        return [(f"{day} 10:37:00", 318.9), (f"{day} 11:37:00", 281.25), (f"{day} 12:16:00", 333.7)]

    monkeypatch.setattr(fno_oi_store, "strike_ltp_series", held_above)
    out = await po._buyer_card_outcome("SENSEX", day, card)
    assert out["outcome"] == "🛑 stopped 11:40" and "just before the stop" in out["premium"]


# ---------------------------------------------------------------------------
# N05-PP: profit protection frozen and scored forward only
# ---------------------------------------------------------------------------

def test_the_protection_rules_fire_as_frozen():
    import partner_protect_score as pps
    t = [datetime(2026, 11, 4, 10, 0, s) for s in range(0, 60, 15)] + [datetime(2026, 11, 4, 10, 1, s)
                                                                        for s in range(0, 60, 15)]
    # P 100, S 85 (P - S 15), W 10: B arms at 115, B2 at 110.
    path = list(zip(t, [101, 108, 111, 113, 109, 104, 99, 98]))
    # B2 arms at the 111 bid (stop 101), trails to 103 after 113, and the 99 bid (index 6) is under it.
    assert pps.fired_at("B2", 100.0, 85.0, 10.0, path) == 6
    assert pps.fired_at("B", 100.0, 85.0, 10.0, path) is None         # 115 never reached
    assert pps.arm_level("B", 100.0, 85.0, 10.0) == 115.0 and pps.arm_level("B2", 100.0, 85.0, 10.0) == 110.0


def test_the_protection_spec_is_pinned():
    """Changing a rule is a new version, frozen again before the days it decides on."""
    import partner_protect_score as pps
    assert pps.SPEC["frozen_from"] == "2026-11-04" and pps.SPEC_ID == "v1-" + __import__("hashlib").sha256(
        json.dumps(pps.SPEC, sort_keys=True).encode()).hexdigest()[:12]
    assert pps.SPEC_ID == PROTECT_SPEC_ID


PROTECT_SPEC_ID = "v1-13b21f18f0f1"      # the frozen version (Nov 3); a change to SPEC fails here


def test_the_protection_score_counts_only_days_from_its_freeze(tmp_path):
    import sqlite3

    import partner_protect_score as pps
    db = str(tmp_path / "w.db")
    with sqlite3.connect(db) as c:
        c.executescript("""
        CREATE TABLE partner_watch_trips(session_date, position_key, tradingsymbol, exchange, first_at, closed_at,
          bought, entry, realised, orders, carried);
        CREATE TABLE partner_watch_plan_versions(position_key, version, session_date, plan_json);
        CREATE TABLE partner_watch_looks(position_key, at, session_date, bid);
        CREATE TABLE partner_orders(session_date, tradingsymbol, transaction_type, status, filled_quantity,
          updated_at, placed_at);""")
        for day in ("2026-11-03", "2026-11-04"):
            key = f"k{day}"
            c.execute("INSERT INTO partner_watch_trips VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      (day, key, "NIFTY26N1023300CE", "NFO", f"{day}T10:00:00+05:30", f"{day}T10:30:00+05:30", 65,
                       100.0, -500.0, 2, 0))
            c.execute("INSERT INTO partner_watch_plan_versions VALUES(?,?,?,?)",
                      (key, 1, day, json.dumps({"entry": 100.0, "stop": 85.0, "swing": 10.0})))
            for i, bid in enumerate([105, 112, 104, 101, 99, 97]):
                c.execute("INSERT INTO partner_watch_looks VALUES(?,?,?,?)",
                          (key, f"{day}T10:0{i}:00+05:30", day, bid))
            c.execute("INSERT INTO partner_orders VALUES(?,?,?,?,?,?,?)",
                      (day, "NIFTY26N1023300CE", "SELL", "COMPLETE", 65, f"{day}T10:30:00+05:30", None))
    out = pps.score(db)
    assert out["first_day"] == "2026-11-04" and out["spec_id"] == pps.SPEC_ID
    b2 = out["rules"]["B2"]
    assert b2["trips"] == 1 and b2["fired"] == 1 and b2["verdict"] == "TOO_FEW" and list(b2["days"]) == ["2026-11-04"]
    assert out["rules"]["B"]["fired"] == 0                       # 115 never reached
