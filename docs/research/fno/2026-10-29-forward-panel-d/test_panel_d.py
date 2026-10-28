"""Forward panel D checks: the arms are the O29b study's picks, the forward machinery reproduces the study's path
exactly on the study's data, and the extreme-loss check works."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("panel_d", HERE / "panel_d.py")
panel_d = importlib.util.module_from_spec(spec)
sys.modules["panel_d"] = panel_d
spec.loader.exec_module(panel_d)
study = panel_d.study

from config import settings  # noqa: E402

RESULTS = panel_d.STUDY_DIR / "results.json"
EVALS = study.EVALS


def test_the_arms_are_the_o29b_final_picks():
    final = json.loads(RESULTS.read_text(encoding="utf-8"))["final_picks"]
    assert json.loads(json.dumps(panel_d.PANEL["OR20_DRIVE"])) == final["G:OR20"]["config"]
    assert json.loads(json.dumps(panel_d.PANEL["EFF_DRIVE"])) == final["G:EFF"]["config"]
    assert json.loads(json.dumps(panel_d.PANEL["DRIVE_BOOK_FADE"])) == final["S"]["config"]
    assert panel_d.PANEL["SHIPPED_DRIVE"] == study.single("SHIPPED", "drive:HIGH") and panel_d.PANEL["SHIPPED"] is None
    assert panel_d.START == "2026-10-29" and panel_d.BANKROLL == float(settings.FNO_PAPER_BANKROLL)


def _m(net, days):
    return {"trades": 6, "net_pnl": net, "net_excluding_best_day": net - max([0.0, *days.values()]),
            "max_drawdown": max(0.0, -min([0.0, *days.values()])), "by_day": days}


def test_a_day_worse_than_two_percent_fails_the_arm_and_raises_the_alarm():
    metrics = {arm: _m(1000, {"d1": 1000}) for arm in panel_d.PANEL}
    metrics["EFF_DRIVE"] = _m(9000, {"d1": -5200, "d2": 14200})
    metrics["OR20_DRIVE"] = _m(4000, {"d1": -2000, "d2": 3000, "d3": 3000})
    decision = panel_d.decide(metrics, complete=False)
    assert decision["arms"]["EFF_DRIVE"]["checks"]["no_extreme_day"] is False
    assert decision["arms"]["EFF_DRIVE"]["promising"] is False
    assert decision["arms"]["OR20_DRIVE"]["promising"] is True
    assert set(decision["alarms"]) == {"EFF_DRIVE"} and decision["status"] == "PROVISIONAL"


@pytest.mark.skipif(not (study.DATA / "manifest.json").is_file(), reason="O29b data not on this machine")
@pytest.mark.parametrize("arm", ["EFF_DRIVE", "DRIVE_BOOK_FADE"])
def test_the_forward_machinery_reproduces_the_study_path(arm):
    config = panel_d.PANEL[arm]
    stored = json.loads((EVALS / f"{study.digest(config)}.json").read_text(encoding="utf-8"))["trades"]
    data = study.grid.CachedReplayData(study.DATA, study.CACHE)
    saved = dict(study.router.NIFTY_FUTURES)
    try:
        result, states = panel_d.replay_arm(data, study.DATA / "fno-replay.sqlite", config, *study.FULL)
    finally:
        study.router.NIFTY_FUTURES.clear()
        study.router.NIFTY_FUTURES.update(saved)
    keys = ("bar_ts", "tradingsymbol", "entry_time", "entry_premium", "exit_time", "exit_premium", "exit_reason",
            "net_pnl", "component")
    assert [{k: t.get(k) for k in keys} for t in result["trades"]] == [{k: t.get(k) for k in keys} for t in stored]
    assert next(iter(states["2026-10-28"].values()))["drive"] == "LOW"
