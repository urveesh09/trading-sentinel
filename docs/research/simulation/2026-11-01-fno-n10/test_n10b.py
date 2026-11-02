"""Round two's rules, its bounded floor, its stress proxy and its verdict, against answers known in advance."""
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import n10b_rules as W  # noqa: E402
import score2 as S2  # noqa: E402
import stress_watch as SW  # noqa: E402


def test_evidence_needs_a_positive_window_and_new_trades():
    assert W.evidence_ok([1.0] * 20, 20, 20)
    assert not W.evidence_ok([1.0] * 19, 19, 20)                 # too few
    assert not W.evidence_ok([1.0] * 40, 19, 20)                 # the same evidence can't be spent twice
    assert not W.evidence_ok([-1.0] * 40, 40, 20)                # it lost
    assert not W.evidence_ok([100.0] * 20 + [-5.0] * 20, 40, 20)  # only the latest window counts
    assert not W.evidence_ok([1.0] * 10 + [-1.0] * 10, 20, 20)   # exactly flat isn't making money


def test_slices_step_down_and_stop_at_the_deepest_floor():
    assert W.lowered_floor(212500.0, 250000.0, 0.05, 0.75) == 200000.0
    assert W.lowered_floor(200000.0, 250000.0, 0.05, 0.75) == 187500.0
    assert W.lowered_floor(187500.0, 250000.0, 0.05, 0.75) is None
    assert W.lowered_floor(190000.0, 250000.0, 0.05, 0.75) == 187500.0  # clipped, never below
    assert W.lowered_floor(340000.0, 400000.0, 0.05, 0.75) == 320000.0  # scales with the best equity


def test_bad_shares_are_refused():
    with pytest.raises(ValueError):
        W.lowered_floor(212500.0, 250000.0, 0.0, 0.75)
    with pytest.raises(ValueError):
        W.lowered_floor(212500.0, 250000.0, 0.05, 1.0)


def t(day, net, reserve=5000.0):
    return {"entry_time": f"{day}T10:00", "exit_time": f"{day}T11:00", "net_pnl": net, "full_reserve": reserve}


def losing_year(prefix="2023", count=30, net=-1500.0):
    return [t(f"{prefix}-{1 + i // 28:02d}-{1 + i % 28:02d}", net) for i in range(count)]


def test_watch_never_lets_the_account_fall_below_its_deepest_floor():
    streams = {"bad": losing_year(count=200, net=-3000.0)}
    out = SW.watch_path(("bad", "bad", "bad"), streams)
    assert out["end"] >= 187500.0 - 1e-6
    assert out["low"] >= 187500.0 - 1e-6


def test_without_paper_evidence_watch_equals_the_plain_floor():
    from n091_lab_free import simulate
    streams = {"bad": losing_year(count=60, net=-1500.0)}
    assert SW.watch_path(("bad",), streams)["slices"] == 0
    assert SW.watch_path(("bad",), streams)["end"] == simulate(("bad",), streams, "CUSHION")["end"]


def test_a_trade_cant_be_its_own_evidence():
    """Twenty losers then one winner, with the floor blocking it: the winner's result is only known after its exit, so it can't justify its own entry."""
    rows = losing_year(count=20, net=-1000.0)
    rows.append({**t("2023-02-20", 90000.0), "full_reserve": 100000.0})
    out = SW.watch_path(("y",), {"y": rows})
    assert out["slices"] == 0 and out["trades"] == 20


def test_evidence_after_a_bad_stretch_buys_one_slice_and_the_account_comes_back():
    """Trades the floor refuses still count on paper: 20 refused winners are the evidence for the next refused one."""
    bad = losing_year(count=25, net=-1500.0)                      # drains free cash to the floor
    good = [t(f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}", 2000.0) for i in range(40)]
    out = SW.watch_path(("bad", "good"), {"bad": bad, "good": good})
    assert out["slices"] >= 1
    assert out["end"] > 250000.0 - 25 * 1500.0                     # it trades again, where a plain floor never would
    from n091_lab_free import simulate
    assert simulate(("bad", "good"), {"bad": bad, "good": good}, "CUSHION")["trades"] < out["trades"]


def years(net=None, day=-3000.0, fall=5.0):
    base = {"2023": -30000.0, "2024": 80000.0, "2025": 60000.0, "2026": 110000.0, **(net or {})}
    return {y: {"net": v, "worst_day": day, "worst_trade": day, "fall_pct": fall, "trades": 10} for y, v in base.items()}


def good_case():
    return dict(fresh=years(), trades={y: [{"exit_time": f"{y}-01-02T12:00", "net_pnl": 100000.0}] * 2 for y in S2.YEARS}, accounts={k: 400000.0 for k in ("base", "low", "high", *S2.NEIGHBOURS)},
                double_sum=160000.0, x_sums={"0.75": 200000.0, "1.25": 195000.0}, ref_without5=1000.0, stress={"WATCH": {"worst_end": 190000, "median_end": 350000}, "CUSHION": {"median_end": 342954}})


def test_a_clean_candidate_passes_all_ten():
    out = S2.checks(**good_case())
    assert all(out.values()), out


@pytest.mark.parametrize("change,failed", [
    (dict(fresh=years({"2024": 70000.0, "2025": 50000.0, "2026": 100000.0})), "1_sum_above_n08"),
    (dict(fresh=years(day=-6128.0)), "2_worst_day_no_larger"),
    (dict(fresh=years(fall=15.09)), "3_fall_no_larger_than_n08"),
    (dict(fresh=years({"2023": -37582.0})), "4_2023_no_worse_than_n08"),
    (dict(fresh=years({"2025": -1.0, "2026": 200000.0})), "5_years_positive_two_at_or_above"),
    (dict(accounts={"base": 400000.0, "low": 400000.0, "high": 384309.0, **{k: 400000.0 for k in S2.NEIGHBOURS}}), "6_account_all_costs"),
    (dict(double_sum=152164.0), "7_double_cost_at_or_above"),
    (dict(x_sums={"0.75": 190218.0, "1.25": 195000.0}), "8_plateau"),
    (dict(accounts={"base": 400000.0, "low": 400000.0, "high": 400000.0, "need10": 300000.0, "need30": 400000.0, "slice2.5": 400000.0, "slice10": 400000.0}), "8_plateau"),
    (dict(ref_without5=1e9), "9_without_top_five"),
    (dict(stress={"WATCH": {"worst_end": 187499, "median_end": 350000}, "CUSHION": {"median_end": 342954}}), "10_stress"),
    (dict(stress={"WATCH": {"worst_end": 190000, "median_end": 340000}, "CUSHION": {"median_end": 342954}}), "10_stress"),
])
def test_each_check_fails_alone_when_it_should(change, failed):
    assert not S2.checks(**{**good_case(), **change})[failed]


def test_the_cliff_question_needs_watch_stable_and_the_plain_floor_not():
    stress = {"WATCH": {"worst_end": 190000, "median_end": 350000}, "CUSHION": {"median_end": 342954}}
    assert S2.removes_the_cliff({"base": 400000.0, "low": 410000.0, "high": 390000.0}, {"base": 384310.0, "low": 390000.0, "high": 216000.0}, stress)["passes"]
    assert not S2.removes_the_cliff({"base": 400000.0, "low": 500000.0, "high": 390000.0}, {"base": 384310.0, "low": 390000.0, "high": 216000.0}, stress)["passes"]
    assert not S2.removes_the_cliff({"base": 400000.0, "low": 410000.0, "high": 390000.0}, {"base": 384310.0, "low": 390000.0, "high": 380000.0}, stress)["passes"]
