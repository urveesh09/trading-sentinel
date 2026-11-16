"""[N16-RV] The partner's review page must answer inside the gateway's wait.

Nov 16, 2026, 07:52 IST: every open of the partner's review failed with
"Quant Engine is unreachable". The engine answered, but a 30-day review took
5.6-5.9 s against the gateway's 5 s: for each of ~430 trades it re-parsed
the time of every order, stop and trade-watch message (about 1.15 million
timestamp conversions). These tests pin the fix without timing anything:
the hot loops parse only the trade's own option, and the cached parsers
give exactly the values the uncached ones did.
"""
from datetime import datetime, timedelta

import pytest
import pytz

import partner_coach as pc
import partner_insights as pi
import partner_trade_paths as ptp

IST = pytz.timezone("Asia/Kolkata")
FIRST = IST.localize(datetime(2026, 11, 13, 10, 0))
END = IST.localize(datetime(2026, 11, 13, 11, 0))
SYMBOL, OTHER = "NIFTY25NOV24000CE", "NIFTY25NOV24100PE"


@pytest.fixture
def counted(monkeypatch):
    """Count the time parses each module makes (the real parse still runs)."""
    calls = {"pc": 0, "pi": 0}
    real = pc._dt

    def counting(key):
        def wrapped(value):
            calls[key] += 1
            return real(value)
        return wrapped

    monkeypatch.setattr(pc, "_dt", counting("pc"))
    monkeypatch.setattr(pi, "_dt", counting("pi"))
    return calls


def _trade() -> dict:
    return {"exchange": "NFO", "tradingsymbol": SYMBOL, "session_date": "2026-11-13", "first_buy_at": FIRST,
            "last_sell_at": END, "open_lots": 0, "buys": [{"order_id": "B1", "price": 100.0}], "sells": []}


def test_dt_gives_the_same_values_as_before():
    assert pc._dt(None) is None and pc._dt("") is None and pc._dt("not a time") is None
    naive = pc._dt("2026-11-13 10:00:00")
    assert naive == IST.localize(datetime(2026, 11, 13, 10, 0)) and naive.utcoffset() == timedelta(hours=5, minutes=30)
    aware = pc._dt("2026-11-13T04:30:00+00:00")
    assert aware == naive and aware.utcoffset() == timedelta(hours=5, minutes=30)
    assert pc._dt("2026-11-13 10:00:00") is pc._dt("2026-11-13 10:00:00")   # cached, one shared immutable value
    assert pc._dt(datetime(2026, 11, 13, 10, 0)) == naive                     # naive datetimes still read as IST
    assert pc._dt(FIRST) is FIRST


def test_trade_stops_parse_only_this_options_stops(counted):
    stop = {"exchange": "NFO", "tradingsymbol": SYMBOL, "status": "TRIGGERED", "kind": "SL",
            "placed_at": "2026-11-13 10:05:00", "updated_at": "2026-11-13 10:40:00"}
    others = [stop | {"tradingsymbol": OTHER} for _ in range(500)]
    refused = [stop | {"status": "REJECTED"} for _ in range(50)]
    found = pc.trade_stops(_trade(), others + refused + [stop])
    assert [s["placed_dt"] for s in found] == [IST.localize(datetime(2026, 11, 13, 10, 5))]
    assert counted["pc"] == 2          # this stop's placed and updated times; before: one per stop (551+)


def test_order_events_parse_only_this_options_refusals_and_watch(counted):
    refusal = {"order_id": "R1", "exchange": "NFO", "tradingsymbol": SYMBOL, "status": "REJECTED",
               "transaction_type": "BUY", "placed_at": "2026-11-13 10:20:00", "status_message": "Price out of range"}
    orders = [refusal | {"order_id": f"X{i}", "tradingsymbol": OTHER} for i in range(500)]
    orders += [refusal | {"order_id": f"C{i}", "status": "COMPLETE"} for i in range(200)] + [refusal]
    watch = [{"position_key": "ELSE", "created_at": "2026-11-13 10:30:00", "summary": "other"}] * 500
    watch += [{"position_key": "B1", "created_at": "2026-11-13 10:30:00", "summary": "Stop is in place"}]
    ctx = pi.Context(orders=orders, watch=watch)
    events = pi._order_events(ctx, _trade(), [], FIRST, END)
    assert [e["text"] for e in events] == ["Zerodha refused your buy order: Price out of range",
                                           "Assistant: Stop is in place"]
    assert counted["pi"] <= 4          # before: one per order and per message (1,201+)


def test_cached_session_and_bar_times_match_a_fresh_parse():
    assert pi._session("2026-11-13", 9, 15) == IST.localize(datetime(2026, 11, 13, 9, 15))
    assert pi._session("2026-11-13", 9, 15) is pi._session("2026-11-13", 9, 15)
    assert ptp._bar_time("2026-11-13 09:16:00") == IST.localize(datetime(2026, 11, 13, 9, 16))
    with pytest.raises(ValueError):    # load_paths still skips a bad stamp
        ptp._bar_time("not a time")
