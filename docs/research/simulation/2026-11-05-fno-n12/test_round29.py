from contextlib import closing
import sqlite3

import pytest

from round29 import bid_ask, crossing, identity


def test_crossing_matches_only_visible_source_marks():
    contract = identity("NIFTY26010924500CE")
    with closing(sqlite3.connect(":memory:")) as conn:
        conn.execute("CREATE TABLE candles(kind,expiry,strike,opt,datetime,close,volume)")
        conn.executemany("INSERT INTO candles VALUES ('option',?,?,?,?,?,?)", (
            (*contract, "2026-01-05 09:45:00", 125., 500),
            (*contract, "2026-01-05 09:50:00", 130., 500),
            (*contract, "2026-01-05 09:51:00", 100., 500),
        ))
        opened, closed = "2026-01-05T09:45:59+05:30", "2026-01-05T09:50:59+05:30"
        ask, bid = bid_ask(125.)[1], bid_ask(130.)[0]
        state, cost = crossing(conn, contract, opened, closed, ask, bid, 65)
        assert state == "matched_positive_volume"
        assert cost == pytest.approx((ask - 125. + 130. - bid) * 65)
        assert crossing(conn, contract, opened, closed, ask, 130., 65) == ("modeled_quote_mismatch", None)
