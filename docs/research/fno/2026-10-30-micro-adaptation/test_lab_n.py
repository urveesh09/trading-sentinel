"""Meaningful clock, policy and ledger boundary tests for research offspring."""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as S

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_n as N


def features():
    stamps = pd.date_range("2026-03-02 09:15", periods=12, freq="5min")
    closes = [99., 100., 100., 100., 99., 102., 103., 104., 103., 102., 101., 100.]
    t = pd.DataFrame({"close": closes, "high": [c + .5 for c in closes],
                      "low": [c - .5 for c in closes], "vwap": [100. + .05 * i for i in range(12)],
                      "ema20": [100.] * 12, "er4": [.5] * 12,
                      "minute": [555 + 5 * i for i in range(12)]}, index=stamps)
    return {"day": stamps[0].date(), "t": t, "stamps": list(stamps.strftime("%Y-%m-%d %H:%M:%S"))}


def leg():
    return S(direction="LONG", entry_underlying=100., stop_underlying=98.,
             entry_time="2026-03-02T09:30:00+05:30", token=1, initial_qty=65)


def test_reclaim_entry_is_prefix_causal_and_has_signal():
    f = features()
    N._ENTRIES.clear()
    full = N.entries({}, f)
    assert full
    for cut in (5, 8, 10):
        shorter = {**f, "t": f["t"].iloc[:cut], "stamps": f["stamps"][:cut]}
        N._ENTRIES.clear()
        assert N.entries({}, shorter) == {k: v for k, v in full.items() if k in shorter["stamps"]}


def test_micro_ignores_open_and_future_bars(monkeypatch):
    f = features()
    monkeypatch.setattr(N.O27F, "day_features", lambda frame, day: f)
    now = datetime(2026, 3, 2, 9, 50, tzinfo=N.Y.IST)
    before = N.micro_state(leg(), object(), now)
    assert before == (True, False)
    f["t"].loc[f["t"].index >= pd.Timestamp("2026-03-02 09:50"), ["close", "vwap", "ema20"]] = -999
    assert N.micro_state(leg(), object(), now) == before


def test_break_requires_two_post_entry_closes(monkeypatch):
    f = features()
    f["t"]["close"] = 99.
    monkeypatch.setattr(N.O27F, "day_features", lambda frame, day: f)
    l = leg()
    assert not N.micro_state(l, object(), datetime(2026, 3, 2, 9, 35, tzinfo=N.Y.IST))[1]
    assert N.micro_state(l, object(), datetime(2026, 3, 2, 9, 40, tzinfo=N.Y.IST))[1]


def engine(mode="BOTH"):
    policy = N.Y.member_policy(N.Y.named("TPB"))
    return S(book={"micro": mode}, policies=[policy], leg_member={1: 0}, _frame=object(), notes=N.Y.Counter())


def test_adaptation_keeps_safety_params_and_restores_policy(monkeypatch):
    e, b = engine(), S(open={1: leg()})
    original = e.policies
    monkeypatch.setattr(N, "micro_state", lambda *a: (True, False))
    def base(self, book, obs, now):
        overrides = dict(self.policies[0].exit_overrides)
        assert overrides["FNO_TIME_STOP_MIN"] == 120
        prior = dict(original[0].exit_overrides)
        for key in ("FNO_HARD_FLAT_MIN", "FNO_STOP_PREMIUM_PCT", "FNO_PROFIT_LOCK_ENABLED"):
            assert overrides.get(key) == prior.get(key)
    monkeypatch.setattr(N, "_manage_before", base)
    N.manage(e, b, None, None)
    assert e.policies is original


def test_shipped_safety_exit_precedes_micro_exit(monkeypatch):
    e, b = engine("BREAK"), S(open={1: leg()})
    monkeypatch.setattr(N, "micro_state", lambda *a: (False, True))
    monkeypatch.setattr(N, "_manage_before", lambda self, book, *a: book.open.clear())
    # No quote access is needed after the safety ladder already closed it.
    N.manage(e, b, None, None)
    assert not b.open


@pytest.mark.parametrize("bid", [0., 12.])
def test_micro_bid_and_cash_ledger(monkeypatch, bid):
    e = engine("BREAK")
    b = S(open={1: leg()}, equity=100., trades=[], closes=[], completed=[])
    obs = S(options={1: S(bid=bid)}, future=S(ltp=100.))
    monkeypatch.setattr(N, "micro_state", lambda *a: (False, True))
    monkeypatch.setattr(N, "_manage_before", lambda *a: None)
    monkeypatch.setattr(N.C.replay, "_close_record", lambda *a: ({"net_pnl": 7.5}, 7.5))
    N.manage(e, b, obs, datetime(2026, 3, 2, 10, tzinfo=N.Y.IST))
    assert b.equity == (107.5 if bid else 100.)
    assert len(b.trades) == len(b.closes) == len(b.completed) == (1 if bid else 0)
    assert bool(b.open) == (not bid)


def test_books_are_bounded_and_references_identical():
    b = N.books()
    assert sum(n.startswith("N|") for n in b) == 8
    assert sum(n.startswith("NULL") for n in b) == 20
    assert b["REF|LIVE"] == N.C.books()["BASE|UNION_ADX"]
    assert len(b["N|BEST+RECLAIM"]["members"]) == 5
