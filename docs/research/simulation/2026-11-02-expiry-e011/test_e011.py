"""Frozen checks on the lab's new parts. The lab's native parts are proven by parity.py."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

import arms as M
import e011_lab as L
import panel as P
import sept as Z
from e011_lab import EP


def position(lots=10, entry=2.9, exchange="NFO", lot=65):
    class C:
        tradingsymbol, token, strike, instrument_type, lot_size = "X", 1, 100.0, "CE", lot
    now = datetime(2026, 10, 13, 14, 0, tzinfo=EP.IST)
    return EP._new_position("2026-10-13", "NIFTY", "X", exchange, C, entry, lots, now, EP.fee_schedule(exchange)), now


def test_recover_takes_the_whole_cost_back_and_leaves_a_runner():
    pos, _ = position()
    take = L.recover_lots(pos, 8.75)
    assert take == 4                                  # 3 lots raise 1706, under the 1885 paid
    schedule = EP.fee_schedule("NFO")
    paid = 2.9 * 650 + EP.buy_charges(2.9, 650, schedule)
    assert 8.75 * 4 * 65 - EP.sell_charges(8.75, 4 * 65, schedule) - 6 * EP.order_fee(schedule) >= paid


def test_recover_falls_back_to_half_when_no_smaller_sale_covers_it():
    pos, _ = position(lots=2, entry=2.9)
    assert L.recover_lots(pos, 3.0) == 1              # one lot can't cover it: half, as the engine does
    pos, _ = position(lots=1)
    assert L.recover_lots(pos, 8.75) == 0             # a one-lot ticket can't bank, as the engine says


def test_a_renamed_play_keeps_its_stop():
    """The first genome ran with no stop at all, because the engine reads the stop by play name."""
    S = L.Recorded("2026-10-19", "NIFTY")
    a = L.run_c(S, L.E01, "X")[0]
    assert a["stop"] == round(a["entry_price"] * .7, 2)
    assert L.run_c(S, L.Ticket(), "X")[0]["stop"] == 0.0


def test_recover_only_changes_the_banked_quantity():
    S = L.Recorded("2026-10-13", "NIFTY")
    half = L.run_c(S, M.ARMS["E01"], "X")[0]
    recover = L.run_c(S, M.ARMS["RECOVER"], "X")[0]
    assert [e["lots"] for e in half["_events"] if e["action"] == "BANK_HALF"] == [5]
    assert [e["lots"] for e in recover["_events"] if e["action"] == "BANK_HALF"] == [4]
    assert half["entry_price"] == recover["entry_price"] and half["lots"] == recover["lots"]
    assert recover["lots_open"] == 0 and recover["status"] == "CLOSED"


def test_no_bank_keeps_every_lot_until_the_trail():
    S = L.Recorded("2026-10-13", "NIFTY")
    pos = L.run_c(S, M.ARMS["E011R"], "X")[0]
    assert [e["action"] for e in pos["_events"]] == ["BUY", "TRAIL"]
    assert pos["_events"][-1]["lots"] == pos["lots"]


def test_every_arm_buys_the_same_ticket_as_c():
    """E01.1's arms change exits only, so each ticket is C's own entry."""
    for day, u in L.recorded_keys():
        S = L.Recorded(day, u)
        first = [(p["symbol"], p["entry_ts"], p["lots"], p["entry_price"]) for p in L.run_c(S, L.C_NATIVE, "C")]
        for name in ("E01", "STOP25", "RECOVER", "TRAIL3X", *M.PRIMARY):
            assert [(p["symbol"], p["entry_ts"], p["lots"], p["entry_price"]) for p in L.run_c(S, M.ARMS[name], "X")] == first


def test_the_full_premium_ceiling_holds_on_every_arm():
    for day, u in L.recorded_keys():
        S = L.Recorded(day, u)
        for name, ticket in M.ARMS.items():
            for p in L.run_c(S, ticket, "X"):
                assert p["max_loss"] <= 2500.0
                assert L.net([p]) >= -p["max_loss"] - .01


def test_a_september_tick_never_sees_its_own_future():
    S = Z.Sept("2026-09-08")
    symbol = S.names[0]
    assert S.now[0].strftime("%H:%M:%S") == "12:59:00"
    q = S.quote(5, symbol)
    bar = S._bars[5]["CE"]
    half = S._half(float(bar["close"]))
    assert q.bid == Z._down(float(bar["close"]) - half)
    assert q.ask == Z._up(float(bar["close"]) + half)


def test_september_adverse_is_never_better_than_ordinary():
    a, b = Z.Sept("2026-09-22"), Z.Sept("2026-09-22", adverse=True)
    for i in range(0, a.n - 1, 37):
        for symbol in a.names:
            x, y = a.quote(i, symbol), b.quote(i, symbol)
            if x.bid is not None and y.bid is not None:
                assert y.bid <= float(a._bars[i + 1][a.kinds[symbol]]["high"])
            if y.asks:
                half = a._half(float(a._bars[i][a.kinds[symbol]]["close"]))
                assert y.ask >= float(a._bars[i + 1][a.kinds[symbol]]["high"]) + half - .001


def test_admissions_use_only_what_was_known():
    """Cutting the file short can't change an admission that came earlier."""
    full = P.admissions(Z.Sept("2026-09-22"))
    assert full
    for row in full:
        S = Z.Sept("2026-09-22")
        S.n = row[0] + 1
        assert row in P.admissions(S)


def test_the_september_snapshot_is_the_acquired_data():
    report = json.loads((L.HERE / "preflight-sept.json").read_text())
    import hashlib
    for name, value in report["hashes"].items():
        assert hashlib.sha256((Z.SNAPSHOT / name).read_bytes()).hexdigest() == value
