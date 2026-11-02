"""N10's rules, its cash, and its verdict against answers known in advance. The saved-trade parity run is the separate control: `driver.py parity`."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import n10_rules as R  # noqa: E402
import score as S  # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))
AT = datetime(2025, 3, 3, 11, 0, tzinfo=IST)


def test_progress_is_in_the_trades_favour_for_either_side():
    assert R.progress_r("LONG", 100.0, 10.0, 110.0) == 1.0
    assert R.progress_r("SHORT", 100.0, 10.0, 110.0) == -1.0
    assert R.progress_r("SHORT", 100.0, 10.0, 90.0) == 1.0


def test_progress_refuses_bad_inputs():
    assert R.progress_r("LONG", 100.0, 0.0, 110.0) is None
    assert R.progress_r("LONG", 100.0, 10.0, float("nan")) is None
    with pytest.raises(ValueError):
        R.progress_r("FLAT", 100.0, 10.0, 110.0)


def test_level_sits_on_the_right_side_of_entry():
    assert R.level_at("LONG", 100.0, 10.0, 0.0) == 100.0
    assert R.level_at("LONG", 100.0, 10.0, 1.0) == 110.0
    assert R.level_at("SHORT", 100.0, 10.0, 1.0) == 90.0


def test_an_earned_lot_risks_the_smaller_of_its_backstop_and_the_giveback():
    assert R.child_risk(ask=136.0, bid=134.0, reference_premium=120.0, stop_pct=0.25, qty=65) == (16 + 2) * 65
    assert R.child_risk(ask=200.0, bid=198.0, reference_premium=100.0, stop_pct=0.25, qty=65) == 50 * 65


def test_the_first_lot_risks_nothing_once_its_trail_is_beyond_entry():
    assert R.parent_risk(120.0, 0.25, 65, False) == 120 * 0.25 * 65
    assert R.parent_risk(120.0, 0.25, 65, True) == 0.0
    assert R.trail_locked("LONG", 100.0, 1, 105.0)
    assert not R.trail_locked("LONG", 100.0, 1, 95.0)
    assert not R.trail_locked("LONG", 100.0, 0, 105.0)
    assert R.trail_locked("SHORT", 100.0, 1, 95.0)


def test_the_budget_is_the_planners_own():
    assert R.budget(250000.0, 0.02, 6250.0, 1.0) == 5000.0
    assert R.budget(500000.0, 0.02, 6250.0, 1.0) == 6250.0
    assert R.budget(250000.0, 0.02, 6250.0, 0.5) == 2500.0
    assert R.budget(250000.0, 0.02, 6250.0, -1.0) == 0.0


def test_an_earned_lot_leaves_at_entry_level_or_its_backstop():
    assert R.child_out("LONG", 100.0, 100.0, 130.0, 102.0) == "n10_level"
    assert R.child_out("SHORT", 100.0, 100.0, 130.0, 102.0) == "n10_level"
    assert R.child_out("LONG", 105.0, 100.0, 101.0, 102.0) == "n10_backstop"
    assert R.child_out("LONG", 105.0, 100.0, 130.0, 102.0) is None
    assert R.child_out("SHORT", 95.0, 100.0, 130.0, 102.0) is None


def test_extra_cost_is_per_lot_per_round_trip():
    assert R.extra_cost(None, 1) == 205.0
    assert R.extra_cost([400.0, 10.0], 1) == 410.0
    assert R.extra_cost([0.0, 0.0], 2) == 0.0
    assert R.extra_cost(None, 2) == 420.0


# ---- cash, against the real planner modules, with the replay stack imported --------------------------------------------


@pytest.fixture(scope="module")
def lab():
    import n10_lab
    return n10_lab


def leg_with(lab, children=()):
    book = SimpleNamespace(equity=250000.0, closes=[], open={})
    leg = lab.replay.OpenLeg(id=1, tradingsymbol="X", token=1, direction="LONG", lots=1, lot_size=65, entry_time="t", entry_premium=100.0, entry_underlying=23000.0, stop_underlying=22950.0,
                             target_underlying=23090.0, premium_stop=75.0, atr_at_entry=10.0, delta_at_entry=0.5, bar_ts="b", initial_qty=65)
    leg._n10 = {"book": book, "cost": [200.0, 5.0], "native": 2, "risk_points": 50.0, "children": list(children), "next": 0, "stopped": False, "reference": 100.0, "refused": set()}
    book.open[1] = leg
    return leg, book


def child(ask=120.0):
    return {"step": 0, "at": "t", "ask": ask, "qty": 65, "future": 23050.0, "progress": 1.0, "level": 23000.0, "premium_stop": ask * 0.75, "risk": 1000.0, "planned_total": 2625.0, "limit": 5000.0, "exit_at": None}


def test_a_settled_earned_lot_pays_its_own_costs_into_equity_as_a_part_of_the_trade(lab):
    from fno_costs import calc_fno_costs
    c = child()
    leg, book = leg_with(lab, [c])
    lab.settle_child(leg, c, AT, 150.0, "with_first:trail_stop")
    expected = (150.0 - 120.0) * 65 - calc_fno_costs(120.0, 150.0, 65) - 205.0
    assert abs(c["net"] - expected) < 0.001
    assert abs(book.equity - (250000.0 + expected)) < 0.001
    assert book.closes[-1][2] == "SINGLE_LEG_PARTIAL"      # the brakes count one trade, not two
    assert leg.fills[-1]["kind"] == "N10_EARNED"
    assert lab.open_children(leg) == []


def test_closing_the_first_lot_takes_the_earned_lot_at_the_same_price_and_totals_both(lab):
    from fno_costs import calc_fno_costs
    c = child()
    leg, book = leg_with(lab, [c])
    before = book.equity
    record, final = lab.replay._close_record(leg, AT, 150.0, "trail_stop", 23100.0)
    assert c["bid"] == 150.0 and c["reason"] == "with_first:trail_stop"
    first = (150.0 - 100.0) * 65 - calc_fno_costs(100.0, 150.0, 65)
    earned = (150.0 - 120.0) * 65 - calc_fno_costs(120.0, 150.0, 65) - 205.0
    assert abs(book.equity - before - earned) < 0.001      # the caller adds `final` for the first lot
    assert abs(record["n10_children"][0]["net"] - earned) < 0.001
    assert abs(record["net_pnl"] - (first + earned)) < 1.0  # the extra cost on the first lot depends on the book in force
    assert final <= first


def test_a_lot_already_stopped_is_not_settled_twice(lab):
    c = child()
    leg, book = leg_with(lab, [c])
    lab.settle_child(leg, c, AT, 110.0, "n10_level")
    equity = book.equity
    lab.replay._close_record(leg, AT, 150.0, "trail_stop", 23100.0)
    assert book.equity == equity and c["bid"] == 110.0 and len(leg.fills) == 1


def test_the_reserve_counts_earned_lots(lab):
    c = child()
    leg, book = leg_with(lab, [c])
    both = lab.M.open_reserve(book, [200.0, 5.0])
    alone = lab.M.full_reserve(100.0, 65, 1, [200.0, 5.0]) + lab.M.full_reserve(120.0, 65, 1, [200.0, 5.0])
    assert abs(both - alone) < 1e-9
    lab.settle_child(leg, c, AT, 130.0, "n10_level")
    assert abs(lab.M.open_reserve(book, [200.0, 5.0]) - lab.M.full_reserve(100.0, 65, 1, [200.0, 5.0])) < 1e-9


def test_the_books_differ_only_where_the_plan_says(lab):
    p = lab.primary_books()
    assert p["EARN_N"]["n10"]["eligibility"] == "NATIVE" and p["EARN_W"]["n10"]["eligibility"] == "RISK"
    assert p["EARN_WV"]["n10"]["vol"] and not p["EARN_W"]["n10"]["vol"]
    assert p["EARN_WC"]["n091"]["mode"] == "CUSHION" and "n091" not in p["EARN_W"]
    assert p["LADDER_WC"]["n10"]["steps"] == [[1.0, 0.0], [2.0, 1.0]] and p["LADDER_WC"]["n10"]["max_total"] == 3
    assert p["HYBRID_C"]["n10"]["entry"] == "NATIVE" and p["HYBRID_C"]["n09"]["vol_size"] and p["HYBRID_C"]["n10"]["max_total"] == 3
    near = lab.neighbour_books()
    assert near["EARN_WC@0.75"]["n10"]["steps"] == [[0.75, 0.0]] and near["LADDER_WC@1.25"]["n10"]["steps"] == [[1.25, 0.0], [2.25, 1.25]]
    for name in ("EARN_N", "EARN_W", "EARN_WV", "EARN_WC", "EARN_WVC", "LADDER_WC"):
        assert p[name]["n10"]["entry"] == "ONE"


# ---- the verdict --------------------------------------------------------------------------------------------------------


def trade(day, net, entry=23000.0):
    return {"exit_time": f"{day}T12:00:00+05:30", "net_pnl": net}


def year_stats(net, worst_day=-3000.0, fall=5.0):
    return {"net": net, "worst_day": worst_day, "worst_trade": worst_day, "fall_pct": fall, "trades": 10}


def passing():
    fresh = {"2023": year_stats(-30000.0), "2024": year_stats(80000.0), "2025": year_stats(60000.0), "2026": year_stats(110000.0)}
    return {"fresh": fresh, "trades": {y: [trade(f"{y}-01-02", 100000.0)] * 2 for y in S.YEARS}, "account": 400000.0, "double_sum": 160000.0, "neighbours": {"0.75": 200000.0, "1.25": 195000.0}, "ref_without5": 1000.0}


def test_a_clean_candidate_passes_all_nine_checks():
    out = S.checks("X", **passing())
    assert out["passes"], out["checks"]


@pytest.mark.parametrize("change,failed", [
    (dict(fresh={"2023": year_stats(-30000.0), "2024": year_stats(70000.0), "2025": year_stats(50000.0), "2026": year_stats(100000.0)}), "1_sum_above_n08"),
    (dict(fresh={"2023": year_stats(-30000.0, -6128.0), "2024": year_stats(80000.0), "2025": year_stats(60000.0), "2026": year_stats(110000.0)}), "2_worst_day_no_larger"),
    (dict(fresh={"2023": year_stats(-30000.0, fall=13.14), "2024": year_stats(80000.0), "2025": year_stats(60000.0), "2026": year_stats(110000.0)}), "3_fall_no_larger"),
    (dict(fresh={"2023": year_stats(-32685.0), "2024": year_stats(80000.0), "2025": year_stats(60000.0), "2026": year_stats(110000.0)}), "4_2023_no_worse"),
    (dict(fresh={"2023": year_stats(-30000.0), "2024": year_stats(80000.0), "2025": year_stats(-1.0), "2026": year_stats(200000.0)}), "5_years_positive_two_at_or_above"),
    (dict(fresh={"2023": year_stats(-30000.0), "2024": year_stats(76000.0), "2025": year_stats(46000.0), "2026": year_stats(120000.0)}), "5_years_positive_two_at_or_above"),
    (dict(account=384309.0), "6_account_at_or_above"),
    (dict(double_sum=152164.0), "7_double_cost_at_or_above"),
    (dict(neighbours={"0.75": 190218.0, "1.25": 195000.0}), "8_plateau"),
    (dict(ref_without5=1e9), "9_without_top_five"),
])
def test_each_check_fails_alone_when_it_should(change, failed):
    out = S.checks("X", **{**passing(), **change})
    assert not out["checks"][failed] and not out["passes"]


def test_stats_measures_the_fall_from_the_running_peak_and_the_worst_day():
    out = S.stats([trade("2024-01-02", 10000.0), trade("2024-01-03", -13000.0), trade("2024-01-03", -13000.0)])
    assert out["net"] == -16000.0 and out["worst_day"] == -26000.0
    assert abs(out["fall_pct"] - 26000 / 260000 * 100) < 0.01


def test_without_best_drops_the_largest_winners_across_years():
    rows = {"2023": [trade("2023-01-02", 5.0), trade("2023-01-03", 1.0)], "2024": [trade("2024-01-02", 9.0), trade("2024-01-03", -2.0)]}
    assert S.without_best(rows, 2) == -1.0


def test_earned_lot_stats_group_exits_and_total_their_own_net():
    t = [{"n10_children": [{"reason": "with_first:trail_stop", "net": 500.0}, {"reason": "n10_level", "net": -300.0}]}, {"n10_children": []}]
    out = S.add_stats(t)
    assert out["lots_earned"] == 2 and out["trades_with_an_earned_lot"] == 1 and out["of_trades"] == 2 and out["earned_net"] == 200.0 and out["earned_wins"] == 1
    assert out["by_exit"] == {"n10_level": [1, -300.0], "with_first": [1, 500.0]}


def test_the_stress_proxy_keeps_the_permanent_stop_and_the_floor():
    sys.path.insert(0, str(HERE.parent / "2026-11-01-fno-n091"))
    import n091_lab_free as F
    t = lambda d, net: {"entry_time": f"{d}T10:00", "exit_time": f"{d}T11:00", "net_pnl": net, "full_reserve": 1000.0}  # noqa: E731
    streams = {"bad": [t("2023-01-02", -40000.0), t("2023-01-03", 5000.0)], "good": [t("2024-01-02", 5000.0)]}
    assert F.simulate(("bad", "good"), streams, "NONE")["end"] == 210000.0     # stopped, and stays stopped
    tight = {"bad": [{**t("2023-01-02", -36000.0), "full_reserve": 37000.0}, {**t("2023-01-03", -1000.0), "full_reserve": 5000.0}]}
    out = F.simulate(("bad",), tight, "CUSHION")
    assert out["end"] == 214000.0 and out["trades"] == 1                         # the second trade can't be funded above the floor
