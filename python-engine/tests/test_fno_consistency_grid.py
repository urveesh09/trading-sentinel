"""scripts/run_fno_consistency_grid.py (O27): the frozen grid, its consistency metrics and selection rule."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import run_fno_consistency_grid as grid  # noqa: E402
from config import settings  # noqa: E402
from tests.test_fno_policy_replay import DAY, _write_dataset  # noqa: E402


def test_the_grid_is_every_entry_with_every_exit_and_current_is_the_shipped_book():
    arms = grid.arms()
    assert len(grid.entries()) == 10 and len(grid.exits()) == 36 and len(arms) == 361
    current = arms[grid.CURRENT_ARM]
    assert current.signal_variant is None and current.manage_every_observation is True
    assert dict(current.exit_overrides) == {
        "FNO_PROFIT_LOCK_ENABLED": settings.FNO_PROFIT_LOCK_ENABLED,
        "FNO_PROFIT_LOCK_ARM_R": settings.FNO_PROFIT_LOCK_ARM_R,
        "FNO_PROFIT_LOCK_FLOOR_R": settings.FNO_PROFIT_LOCK_FLOOR_R,
        "FNO_PROFIT_LOCK_KEEP_FRACTION": settings.FNO_PROFIT_LOCK_KEEP_FRACTION,
        "FNO_TIME_STOP_MIN": settings.FNO_TIME_STOP_MIN, "FNO_TRAIL_ATR_MULT": settings.FNO_TRAIL_ATR_MULT}
    entries = grid.entries()
    for family in ("OR30", "OR20", "OR45", "CONFIRM1", "CONT"):
        free = entries[f"{family}_NOEMA"]
        assert free.ema_filter is False
        if family != "OR30":       # otherwise the recorded variant, with only the EMA check removed
            assert entries[family].ema_filter is True
            assert {**vars(free), "name": "", "ema_filter": True} == {**vars(entries[family]), "name": ""}
    parity = arms[grid.PARITY_ARM].signal_variant
    assert parity.ema_filter is True and parity.name != "FNO_BASE"     # the variant code path, EMA on
    assert grid._settings_check()["current_arm"] == grid.CURRENT_ARM


def test_neighbours_change_one_exit_axis_by_one_step():
    centre = "CONT|LOCK_LIVE|T45|TR1.0"
    assert sorted(grid.neighbours(centre)) == sorted([
        "CONT|LOCK_TIGHT|T45|TR1.0", "CONT|LOCK_LATE|T45|TR1.0", "CONT|LOCK_LIVE|T30|TR1.0",
        "CONT|LOCK_LIVE|T75|TR1.0", "CONT|LOCK_LIVE|T45|TR0.6", "CONT|LOCK_LIVE|T45|TR1.5"])
    assert sorted(grid.neighbours("OR20|LOCK_OFF|T75|TR1.5")) == sorted([
        "OR20|LOCK_LATE|T75|TR1.5", "OR20|LOCK_OFF|T45|TR1.5", "OR20|LOCK_OFF|T75|TR1.0"])
    assert all(n in grid.arms() for a in grid.arms() if not a.startswith("PARITY") for n in grid.neighbours(a))


def _trade(day, minute, pnl, lots=1):
    return {"entry_time": f"{day}T10:{minute:02d}:00+05:30", "exit_time": f"{day}T11:{minute:02d}:00+05:30",
            "net_pnl": pnl, "lots_at_exit": lots, "exit_reason": "trail_stop" if pnl > 0 else "stop"}


def test_window_metrics_measure_consistency_not_just_the_total():
    sessions = ["2026-10-12", "2026-10-13", "2026-10-19", "2026-10-20"]          # two ISO weeks
    trades = [_trade("2026-10-12", 0, 3000), _trade("2026-10-12", 30, -500), _trade("2026-10-13", 0, -800),
              _trade("2026-10-19", 0, 400, lots=2), _trade("2026-10-01", 0, 9999),       # outside the window
              {"entry_time": "2026-10-20T10:00:00+05:30", "status": "UNRESOLVED"}]
    m = grid.window_metrics(trades, sessions)
    assert (m["trades"], m["unresolved"], m["net_pnl"]) == (4, 1, 2100)
    assert m["net_excluding_best_winner"] == -900 and m["max_drawdown"] == 1300
    assert m["cs"] == pytest.approx(-900 / 1300, abs=1e-4)
    assert (m["trade_days"], m["green_days"], m["red_days"], m["worst_day"]) == (3, 2, 1, -800)
    assert (m["weeks"], m["green_weeks"], m["green_week_share"]) == (2, 2, 1.0)
    assert m["net_per_lot"] == 3000 - 500 - 800 + 200
    assert grid.window_metrics([], sessions)["cs"] == 0.0


def _blank(trades=0, net=0.0, ex_best=0.0, dd=0.0, cs=0.0, gws=0.0, red=0):
    return {"trades": trades, "net_pnl": net, "net_excluding_best_winner": ex_best, "max_drawdown": dd, "cs": cs,
            "green_week_share": gws, "red_days": red}


def test_the_rule_prefers_a_plateau_to_a_spike_and_checks_the_later_window():
    metrics = {a: {"A_select": _blank(), "B_check": _blank()} for a in grid.arms()}
    spike, plateau = "OR20|LOCK_LIVE|T45|TR1.0", "CONT|LOCK_LIVE|T45|TR1.0"
    metrics[spike]["A_select"] = _blank(12, 9000, 5000, 1000, 5.0)                 # alone among losers
    for arm in [plateau, *grid.neighbours(plateau)]:
        metrics[arm]["A_select"] = _blank(10, 4000, 2000, 1000, 2.0)
    metrics[plateau]["B_check"] = _blank(4, 500, 100, 800)
    thin = "OR45|LOCK_LIVE|T45|TR1.0"
    for arm in [thin, *grid.neighbours(thin)]:
        metrics[arm]["A_select"] = _blank(5, 9000, 8000, 100, 80.0)               # too few trades to rank
    decision = grid.decide(metrics)
    assert thin not in decision["rank"] and decision["rank"][0] == plateau
    assert decision["plateau_cs"][spike] == 0.0 and decision["recommended"] == plateau
    assert decision["verdict"] == "SHADOW_CANDIDATE" and decision["current_rank"] is None
    # The later window fails (a loss there): the next ranked arm that passes, else CURRENT is kept.
    for arm in [plateau, *grid.neighbours(plateau), spike]:
        metrics[arm]["B_check"] = _blank(3, -1, 0, 100)
    decision = grid.decide(metrics)
    assert decision["recommended"] == grid.CURRENT_ARM and decision["verdict"] == "NONE_PASSED_KEEP_CURRENT"


def test_run_scores_each_arm_once_and_refuses_changed_inputs(tmp_path, monkeypatch):
    dataset = _write_dataset(tmp_path / "data")
    monkeypatch.setattr(grid, "ROOT", tmp_path)
    monkeypatch.setattr(grid, "FULL", (DAY.isoformat(), DAY.isoformat()))
    monkeypatch.setattr(grid, "WINDOWS", {"A_select": grid.FULL, "B_check": grid.FULL})
    monkeypatch.setattr(grid, "LOCKS", {k: grid.LOCKS[k] for k in ("LOCK_LIVE", "LOCK_OFF")})
    monkeypatch.setattr(grid, "TIME_STOPS", (45,))
    monkeypatch.setattr(grid, "TRAILS", (1.0,))
    monkeypatch.setattr(grid, "neighbours", lambda arm: [])
    bound = {"sources": {"x": "1"}, "dataset": {"manifest_sha256": "f" * 64, "quote_days": [DAY.isoformat()]},
             "settings": {}}
    monkeypatch.setattr(grid, "_bound", lambda folder: bound)
    out = tmp_path / "study"
    grid.freeze(dataset, out)
    frozen = json.loads((out / "freeze.json").read_text())
    assert frozen["dataset_folder"] == "data" and frozen["arm_count"] == 21
    grid.run(out, jobs=1)
    results = json.loads((out / "results.json").read_text())
    assert results["decision"]["parity_generic_path_equals_current"] is True
    current = results["metrics"][grid.CURRENT_ARM]["A_select"]
    assert current["trades"] == 1 and current["sessions"] == 1
    assert len(list((out / "_local" / "arms").glob("*.json"))) == 21
    assert len(list((out / "_local" / "observations").rglob("*.pkl"))) == 1
    with pytest.raises(SystemExit, match="exists"):
        grid.run(out, jobs=1)                                                     # scored once
    monkeypatch.setattr(grid, "_bound", lambda folder: {**bound, "sources": {"x": "2"}})
    with pytest.raises(SystemExit, match="changed since freeze"):
        grid.run(out, jobs=1)
