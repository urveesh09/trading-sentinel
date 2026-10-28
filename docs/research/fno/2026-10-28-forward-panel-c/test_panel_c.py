"""Forward panel C checks: the arms are the O28 configs committed before Oct 28, the forward machinery reproduces the
O28 UNION path exactly on the study's data, the contract map follows the roll, and the extreme-loss check works."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("panel_c", HERE / "panel_c.py")
panel_c = importlib.util.module_from_spec(spec)
sys.modules["panel_c"] = panel_c
spec.loader.exec_module(panel_c)
router = panel_c.router

from config import settings  # noqa: E402

RAW = panel_c.O28_DIR / "_local/results-raw.json"


def test_the_arms_are_the_o28_configs_frozen_before_the_oct_28_open():
    o28 = json.loads((panel_c.O28_DIR / "freeze.json").read_text(encoding="utf-8"))
    assert panel_c.PANEL["UNION"] == {c: "ALWAYS" for c in o28["components"]}
    assert panel_c.PANEL["UNION_DRIVE"] == o28["theory"]["THEORY_DRIVE"]
    assert panel_c.PANEL["SHIPPED"] is None and list(panel_c.PANEL) == ["SHIPPED", "UNION", "UNION_DRIVE"]


def test_the_extreme_loss_bounds_are_the_declared_share_of_the_paper_bankroll():
    assert panel_c.BANKROLL == float(settings.FNO_PAPER_BANKROLL)
    assert panel_c.EXTREME == {"worst_day": -5000.0, "drawdown": 12500.0}


def _m(net, dd, days):
    return {"trades": 6, "net_pnl": net, "net_excluding_best_day": net - max([0.0, *days.values()]),
            "max_drawdown": dd, "by_day": days}


def test_a_day_worse_than_two_percent_fails_the_arm_and_raises_the_alarm():
    metrics = {"SHIPPED": _m(1000, 1000, {"d1": 1000}),
               "UNION": _m(9000, 5200, {"d1": -5200, "d2": 14200}),
               "UNION_DRIVE": _m(4000, 2000, {"d1": -2000, "d2": 3000, "d3": 3000})}
    decision = panel_c.decide(metrics, complete=False)
    assert decision["arms"]["UNION"]["checks"]["no_extreme_day"] is False
    assert decision["arms"]["UNION"]["promising"] is False
    assert decision["arms"]["UNION_DRIVE"]["checks"]["no_extreme_day"] is True
    assert decision["arms"]["UNION_DRIVE"]["promising"] is True
    assert set(decision["alarms"]) == {"UNION"} and decision["alarms"]["UNION"]["worst_day"] == -5200
    assert "SHIPPED" not in decision["arms"] and decision["status"] == "PROVISIONAL"


def test_the_contract_map_follows_the_roll_to_the_next_future():
    nov = SimpleNamespace(future=SimpleNamespace(contract=SimpleNamespace(token=999, expiry="2026-11-24")))
    data = SimpleNamespace(observations=lambda day: ([nov], {}))
    futures = panel_c.front_futures(data, ["2026-10-28"])
    assert futures == {**panel_c.O28_FUTURES, 999: "2026-11-24"}
    saved = dict(router.NIFTY_FUTURES)
    try:
        router.NIFTY_FUTURES.clear()
        router.NIFTY_FUTURES.update(futures)
        from datetime import date
        assert router.front_token(date(2026, 10, 27)) == 12468226
        assert router.front_token(date(2026, 10, 28)) == 999
        assert router.front_token(date(2026, 9, 29)) == 17512194
    finally:
        router.NIFTY_FUTURES.clear()
        router.NIFTY_FUTURES.update(saved)


def test_history_check_names_the_sessions_that_moved():
    history = {"2026-10-23": {f: 0.5 for f in router.FEATURES}, "2026-10-26": {f: 0.25 for f in router.FEATURES}}
    table = {"2026-10-23": {f: 0.50001 for f in router.FEATURES}, "2026-10-26": {f: 0.3 for f in router.FEATURES}}
    assert panel_c.history_check(table, history) == ["2026-10-26"]


@pytest.mark.skipif(not RAW.is_file(), reason="O28 results not on this machine")
def test_the_forward_machinery_reproduces_the_o28_union_path_exactly():
    data = router.grid.CachedReplayData(router.DATA, router.CACHE)
    saved = dict(router.NIFTY_FUTURES)
    try:
        result, table = panel_c.replay_router(data, router.DATA / "fno-replay.sqlite", panel_c.PANEL["UNION"],
                                              *router.FULL)
    finally:
        router.NIFTY_FUTURES.clear()
        router.NIFTY_FUTURES.update(saved)
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    keys = (*router.PARITY_KEYS, "component")
    want = [{k: t.get(k) for k in keys} for t in raw["trades"][router.digest(router.UNION)]]
    assert [{k: t.get(k) for k in keys} for t in result["trades"]] == want
    assert panel_c.history_check(table, panel_c.frozen_history()) == []
