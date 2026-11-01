"""The scoring code against answers known in advance: the overfitting estimate, the gates' arithmetic and the whole-year restart paths."""
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze_panel as A  # noqa: E402
import stress_years as S  # noqa: E402


def trade(day, net, entry=23000.0, stop=22900.0, delta=0.5):
    return {"exit_time": f"{day}T12:00:00+05:30", "net_pnl": net, "entry_underlying": entry, "initial_stop_underlying": stop, "delta_at_entry": delta, "entry_qty": 65}


def test_pbo_averages_a_coin_flip_on_pure_noise():
    """One random matrix can land anywhere from 0.11 to 0.94 (standard deviation about 0.18), so the estimator is checked on the average."""
    values = [A.cscv(np.random.default_rng(seed).normal(0, 1, (200, 30)), blocks=8)["pbo"] for seed in range(40)]
    assert 0.40 <= float(np.mean(values)) <= 0.65


def test_pbo_is_low_when_one_book_is_really_better():
    rng = np.random.default_rng(2)
    matrix = rng.normal(0, 1, (200, 30))
    matrix[:, 7] += 1.0
    out = A.cscv(matrix, blocks=8)
    assert out["pbo"] < 0.05
    assert max(out["picks"], key=out["picks"].get) == 7


def test_stats_measures_fall_from_the_running_peak():
    out = A.stats([trade("2024-01-02", 10000.0), trade("2024-01-03", -26000.0)], pool=250000.0)
    assert out["net"] == -16000 and out["worst_day"] == -26000
    assert abs(out["fall_pct"] - 26000 / 260000 * 100) < 0.01


def test_r_is_net_over_delta_stop_and_quantity():
    assert abs(A.r_of(trade("2024-01-02", 3250.0)) - 3250 / (0.5 * 100 * 65)) < 1e-9


def base():
    return {y: [trade(f"{y}-01-02", 1000.0)] for y in A.YEARS}


def test_gates_pass_a_clean_improvement_and_fail_a_worse_one():
    weeks = A.all_weeks()
    better = {y: [trade(f"{y}-{m:02d}-02", 1000.0 + 100.0) for m in range(1, 11)] for y in A.YEARS}
    ref = {y: [trade(f"{y}-{m:02d}-02", 1000.0) for m in range(1, 11)] for y in A.YEARS}
    assert A.part_gates(better, ref, weeks)["passes"]
    worse = {y: [trade(f"{y}-{m:02d}-02", 900.0) for m in range(1, 11)] for y in A.YEARS}
    out = A.part_gates(worse, ref, weeks)
    assert not out["passes"] and not out["gates"]["g1_2023"]


def test_a_stopped_account_stays_stopped_without_a_restart():
    stream = {"bad": [-40000.0], "good": [10000.0] * 3}
    out = S.path_end(("bad", "good"), stream, "NONE")
    assert out == {"end": 210000, "low": 210000, "restarts": 0}


def test_the_yearly_restart_waits_for_the_next_block_and_moves_the_floor():
    stream = {"bad": [-40000.0], "good": [10000.0] * 3}
    out = S.path_end(("bad", "good"), stream, "ANNUAL")
    assert out["restarts"] == 1 and out["end"] == 240000
    twice = S.path_end(("bad", "bad", "bad"), {"bad": [-40000.0]}, "ANNUAL")
    assert twice["restarts"] == 2 and twice["end"] == 130000      # each restart can lose again


def test_the_paper_restart_needs_twenty_trades_that_made_money():
    stream = {"bad": [-40000.0], "flat": [1.0] * 19, "good": [1000.0] * 5}
    assert S.path_end(("bad", "flat"), stream, "SHADOW")["restarts"] == 0      # 20 paper trades, but the -40,000 is among them
    out = S.path_end(("bad", "flat", "good"), stream, "SHADOW")
    assert out["restarts"] == 1 and out["end"] > 210000
