"""SN381 synthetic cases (the auditor's list): run with `python test_fw7a.py` (or pytest)."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fw7a as A  # noqa: E402

LOT = 65
FEE = lambda px, q: 20.0 + 0.0005 * px * q  # noqa: E731  (a simple stand-in for entry charges)


def test_19500_fallback_is_inadmissible():
    # one-strike ITM at 300 x 65 = 19,500 (> 15,000); two-strike at 360 -> 23,400: neither fits
    books = {2: ([360.0] * 5, [500] * 5), 1: ([300.0] * 5, [500] * 5)}
    assert A.pick_depth(books, LOT, FEE) == (None, None, None)


def test_top_of_book_fits_but_walk_does_not():
    # 230 x 65 = 14,950 at the top, but only 30 units there; the rest at 250 -> walk 240.8 -> 15,650
    ok, px, cost = A.admissible([230.0, 250.0, 260.0, 0, 0], [30, 100, 100, 0, 0], LOT, FEE)
    assert not ok and px > 230.0 and cost > 15000.0


def test_cap_keeps_any_fill_inside_the_room():
    cap = A.order_cap(229.0, LOT, FEE)
    assert cap * LOT + FEE(cap, LOT) <= 15000.0 + 1e-6
    assert cap <= 229.0 + 2 * A.TICK + 1e-9


def test_late_packet_cannot_set_the_signal():
    rows = [{"t": -500.0, "ltp": 25171.0, "last_trade_ts": 0.0}, {"t": 80.0, "ltp": 25300.0, "last_trade_ts": 1e12}]   # first trade at 09:16:20
    price, source, at = A.auction_price(rows, decision_t=60.0, pre0_epoch=1e9)
    assert price is None and source == "NO_SIGNAL" and at == 80.0


def test_match_packet_and_first_trade_are_labelled():
    rows = [{"t": -360.0, "ltp": 25249.0, "last_trade_ts": 2e9}]
    assert A.auction_price(rows, 60.0, 1e9)[:2] == (25249.0, "MATCH")
    rows = [{"t": -500.0, "ltp": 25171.0, "last_trade_ts": 0.0}, {"t": 12.0, "ltp": 25240.0, "last_trade_ts": 2e9}]
    assert A.auction_price(rows, 60.0, 3e9)[:2] == (25240.0, "FIRST_TRADE")


def test_stale_or_missing_quote_is_not_a_fill():
    assert A.state_of(None) == "INADMISSIBLE"
    assert A.state_of({"missed": True, "why": "invalid_or_stale"}) == "MISSED"


def test_unresolved_exit_is_its_own_state():
    assert A.state_of({"missed": False, "status": "unresolved", "net205": -14000.0}) == "UNRESOLVED"


def test_one_matched_day_control_cannot_pass():
    rows = []
    for k in range(20):
        r = {"day": f"2026-12-{k + 1:02d}", "ITM": {"state": "FILLED", "net205": 500.0, "net400": 300.0},
             "ATM": {"state": "MISSED", "net205": 0.0, "net400": 0.0}, "COIN_ITM": {"state": "MISSED", "net205": 0.0, "net400": 0.0}}
        rows.append(r)
    rows[0]["ITM"] = {"state": "FILLED", "net205": -100.0, "net400": -300.0}
    rows[0]["ATM"] = {"state": "FILLED", "net205": 100.0, "net400": 0.0}
    rows[0]["COIN_ITM"] = {"state": "FILLED", "net205": 100.0, "net400": 0.0}
    out = A.judge(rows)
    assert out["paired"]["ATM"]["common_fills"] == 1 and out["paired"]["ATM"]["mean_diff_205"] == -200.0
    assert out["verdict"] == "FAIL"


def test_skips_count_as_zero_per_session():
    rows = [{"day": "d1", "ITM": {"state": "FILLED", "net205": 900.0, "net400": 700.0}, "ATM": {"state": "FILLED", "net205": 0.0, "net400": 0.0},
             "COIN_ITM": {"state": "FILLED", "net205": 0.0, "net400": 0.0}},
            {"day": "d2", "ITM": {"state": "INADMISSIBLE", "net205": 0.0, "net400": 0.0}, "ATM": {"state": "FILLED", "net205": 0.0, "net400": 0.0},
             "COIN_ITM": {"state": "FILLED", "net205": 0.0, "net400": 0.0}}]
    out = A.judge(rows)
    assert out["per_session_205"] == 450.0 and out["states"]["INADMISSIBLE"] == 1


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
