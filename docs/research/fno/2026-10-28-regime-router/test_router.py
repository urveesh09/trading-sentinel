"""O28 router lab checks: conditions are causal, the router obeys its gates and priority, each leg keeps its own
component's exits, the selection rule and the null are as declared."""
from __future__ import annotations

import importlib.util
import inspect
import pickle
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
import pytz

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("o28_router", HERE / "router.py")
router = importlib.util.module_from_spec(spec)
sys.modules["o28_router"] = router
spec.loader.exec_module(router)

import fno_exit_rules  # noqa: E402
import fno_policy_replay as replay  # noqa: E402
from fno_engine_mom import MomSignal  # noqa: E402
from fno_models import FnoDirection  # noqa: E402

IST = pytz.timezone("Asia/Kolkata")
HAVE_DATA = (router.DATA / "fno-replay.sqlite").is_file()
needs_data = pytest.mark.skipif(not HAVE_DATA, reason="research dataset not exported on this machine")


@needs_data
@pytest.mark.parametrize("day", ["2026-09-10", "2026-09-24", "2026-09-30", "2026-10-08", "2026-10-23", "2026-10-26"])
def test_a_days_conditions_read_nothing_after_0945(day):
    bars = router.nifty_bars()
    cut = pd.Timestamp(f"{day} 09:45:00")
    truncated = {t: f[f.index < cut] for t, f in bars.items()}
    full, early = router.condition_table(bars)[day], router.condition_table(truncated)[day]
    assert early == full
    assert all(full[f] is not None for f in router.FEATURES) and all(full["side"].values())


def test_the_router_never_reads_hindsight():
    for obj in (router.RouterReplay, router.allowed, router.day_rows, router.with_sides):
        assert "hindsight" not in inspect.getsource(obj)


@needs_data
def test_the_condition_contract_is_the_book_s_front_future():
    data = router.grid.CachedReplayData(router.DATA, router.CACHE)
    for day in data.days:
        future = data.observations(day)[0][0].future.contract
        assert future.token == router.front_token(datetime.fromisoformat(day).date())
        assert str(future.expiry) == router.NIFTY_FUTURES[future.token]


def test_allowed_reads_only_the_declared_side():
    row = {"side": {"gap": "HIGH", "nr": "LOW", "or_width": None}}
    assert router.allowed("ALWAYS", None) and not router.allowed("NEVER", row)
    assert router.allowed("gap:HIGH", row) and not router.allowed("gap:LOW", row)
    assert router.allowed("nr:LOW", row) and not router.allowed("or_width:LOW", row)
    assert not router.allowed("gap:HIGH", None)


def _frame():
    idx = pd.date_range("2026-10-28 09:15", periods=12, freq="5min")
    return pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}, index=idx)


def _sig(direction, bar_ts):
    return MomSignal(bar_ts=bar_ts, direction=direction, close=100.0, atr=10.0, stop_underlying=90.0,
                     target_underlying=130.0)


def test_the_router_obeys_gates_then_priority_and_tags_the_component():
    now = IST.localize(datetime(2026, 10, 28, 10, 1))
    bar = "2026-10-28 09:55:00"
    memo = {("SHIPPED", bar, "R"): _sig(FnoDirection.LONG, bar), ("OR20", bar, "R"): MomSignal(bar_ts=bar),
            ("EFF", bar, "R"): MomSignal(bar_ts=bar), ("TPB", bar, "R"): _sig(FnoDirection.SHORT, bar)}
    config = {"SHIPPED": "gap:HIGH", "OR20": "ALWAYS", "EFF": "NEVER", "TPB": "ALWAYS"}
    low = {"2026-10-28": {"side": {"gap": "LOW"}}}
    high = {"2026-10-28": {"side": {"gap": "HIGH"}}}
    r = router.RouterReplay(None, config, low, memo)
    sig = r.route(_frame(), "R", now)
    assert sig.direction == FnoDirection.SHORT and r._fired == "TPB"
    r = router.RouterReplay(None, config, high, memo)
    sig = r.route(_frame(), "R", now)
    assert sig.direction == FnoDirection.LONG and r._fired == "SHIPPED"
    r = router.RouterReplay(None, {**config, "TPB": "NEVER"}, low, memo)
    sig = r.route(_frame(), "R", now)
    assert sig.direction is None and sig.reject_reason == "router:no_component" and sig.bar_ts == bar
    assert not r.notes.get("memo_miss")


def _leg(leg_id, token):
    return replay.OpenLeg(id=leg_id, tradingsymbol=f"SYM{leg_id}", token=token, direction="LONG", lots=1, lot_size=65,
                          entry_time="2026-10-28T10:00:00+05:30", entry_premium=100.0, entry_underlying=25000.0,
                          stop_underlying=24950.0, target_underlying=25150.0, premium_stop=60.0, atr_at_entry=20.0,
                          delta_at_entry=0.55, bar_ts="2026-10-28 09:55:00", initial_qty=65)


def test_each_leg_is_managed_with_its_own_component_exits(monkeypatch):
    seen = {}

    def fake(leg, *, now_ist, fut_price, exit_px_basis, hard_flat, params, lock_breach_since):
        seen[leg.id] = params
        reason = "time_stop" if leg.id == 2 else ""
        return fno_exit_rules.SingleLegExitDecision(exit_reason=reason, trail_active=False, trail_stop=None,
                                                    best_underlying=None, persist_trail=False)
    monkeypatch.setattr(fno_exit_rules, "evaluate_single_leg_exit", fake)
    r = router.RouterReplay(None, router.UNION, {}, {})
    base = r.policy
    book = replay.Book(equity=100000.0)
    book.open = {1: _leg(1, 11), 2: _leg(2, 22)}
    r.leg_component = {1: "SHIPPED", 2: "TPB"}
    quote = SimpleNamespace(bid=110.0, ltp=110.0)
    obs = SimpleNamespace(future=SimpleNamespace(ltp=25010.0), options={11: quote, 22: quote})
    r._manage(book, obs, IST.localize(datetime(2026, 10, 28, 11, 0)))
    shipped, tpb = dict(router._POLICIES["SHIPPED"].exit_overrides), dict(router._POLICIES["TPB"].exit_overrides)
    assert all(seen[1][k] == v for k, v in shipped.items()) and seen[1]["FNO_TIME_STOP_MIN"] == 45.0
    assert all(seen[2][k] == v for k, v in tpb.items()) and seen[2]["FNO_TIME_STOP_MIN"] == 120.0
    assert seen[2]["FNO_PROFIT_LOCK_ENABLED"] is False and seen[2]["FNO_TRAIL_ATR_MULT"] == 2.0
    assert list(book.open) == [1] and r.policy is base
    assert len(book.trades) == 1 and book.trades[0]["component"] == "TPB" and book.trades[0]["entry_qty"] == 65


def test_component_definitions_are_the_studied_ones():
    assert router.O27E.digest(router.EFF_GENOME) == "ed0d136bdd80ee89"
    assert router._POLICIES["TPB"].signal_variant == "FNO_TREND_PULLBACK"
    assert router._POLICIES["OR20"].signal_variant.ema_filter is False
    assert router._POLICIES["OR20"].signal_variant.opening_range_minutes == 20
    assert router._POLICIES["SHIPPED"].signal_variant is None


def test_selection_takes_the_best_training_option_and_prefers_always_on_ties():
    days = ["2026-09-10", "2026-09-11", "2026-09-15"]

    def t(day, net):
        return {"entry_time": f"{day}T10:00:00", "exit_time": f"{day}T11:00:00", "net_pnl": net, "gross_pnl": net,
                "exit_reason": "x", "entry_qty": 65}
    trades = {}
    for comp in router.COMPONENTS:
        for option in (o for o in router.OPTIONS if o != "NEVER"):
            trades[router.digest(router.single(comp, option))] = []
    # SHIPPED: gap:LOW keeps two winners (net-without-best-day 500) where ALWAYS also keeps a loser (-200)
    trades[router.digest(router.single("SHIPPED", "ALWAYS"))] = [t(days[0], 1000), t(days[1], 500), t(days[2], -700)]
    trades[router.digest(router.single("SHIPPED", "gap:LOW"))] = [t(days[0], 1000), t(days[1], 500)]
    # OR20: only losers -> NEVER; EFF: a tie with ALWAYS -> ALWAYS
    trades[router.digest(router.single("OR20", "ALWAYS"))] = [t(days[0], -100), t(days[1], -100)]
    trades[router.digest(router.single("EFF", "ALWAYS"))] = [t(days[0], 300), t(days[1], 300)]
    trades[router.digest(router.single("EFF", "nr:HIGH"))] = [t(days[0], 300), t(days[1], 300)]
    picked = router.select(trades, days)
    assert picked == {"SHIPPED": "gap:LOW", "OR20": "NEVER", "EFF": "ALWAYS", "TPB": "ALWAYS"}


def test_the_null_is_seeded_and_uses_the_declared_options():
    a, b = router.null_configs(), router.null_configs()
    assert a == b and len(a) == router.NULL["count"]
    assert all(set(c) == set(router.COMPONENTS) and set(c.values()) <= set(router.OPTIONS) for c in a)


def test_the_memo_round_trips():
    sig = _sig(FnoDirection.LONG, "2026-10-28 09:55:00")
    back = pickle.loads(pickle.dumps({("TPB", sig.bar_ts, "R"): sig}))
    assert repr(back[("TPB", sig.bar_ts, "R")]) == repr(sig)
