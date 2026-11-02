"""O30r checks: the levels are what they claim, settings and costs are restored, the proof code catches wrong replays."""
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze_r as A  # noqa: E402
import lab_r as L  # noqa: E402


def test_all_in_levels_put_all_the_money_in_one_trade():
    lv = L.levels()
    for name, risk, stop in (("R25|OFF", 0.25, 0.25), ("ALLIN_S50", 0.5, 0.5), ("ALLIN_NOPREM", 1.0, 1.0), ("ALLIN_NOSTOP", 1.0, 1.0)):
        cfg = lv[name]["cfg"]
        assert cfg["FNO_MAX_RISK_PCT"] == risk and cfg["FNO_STOP_PREMIUM_PCT"] == stop
        assert cfg["FNO_MAX_RISK_PCT"] / cfg["FNO_STOP_PREMIUM_PCT"] == 1.0
        assert cfg["FNO_MAX_OPEN_PREMIUM_PCT"] == 1.0
    assert lv["ALLIN_NOSTOP"]["nostop"] and lv["ALLIN_NOSTOP"]["exit"] == "HOLD"
    assert lv["SHIPPED"]["cfg"] == {}


def test_r2_scaled_brakes_are_the_shipped_percentages():
    from config import settings
    cfg = L.levels()["R2|SCALED"]["cfg"]
    for k in ("FNO_DAILY_KILL_PCT", "FNO_WEEKLY_KILL_PCT", "FNO_MONTHLY_KILL_PCT", "FNO_MAX_DRAWDOWN_PCT",
              "FNO_RISK_CUT1_DRAWDOWN_PCT", "FNO_RISK_CUT2_DRAWDOWN_PCT"):
        assert abs(cfg[k] - getattr(settings, k)) < 1e-9, k


def test_the_planner_sizes_a_level_by_settings_alone():
    from config import settings
    from fno_risk import lots_for_pool
    cfg = L.levels()["R25|OFF"]["cfg"]
    assert lots_for_pool(250000.0, 150.0, 65, cfg["FNO_STOP_PREMIUM_PCT"], cfg["FNO_MAX_RISK_PCT"], cfg["FNO_MAX_LOTS"],
                         max_risk_rupees=cfg["FNO_MAX_LOSS_PER_TRADE"]) == 25     # 2,50,000 / 9,750 = 25.6
    assert settings.FNO_MAX_LOTS == 2, "tests must not leave a level's settings behind"


def test_books():
    b = L.year_books()
    assert len([n for n in b if n.endswith("|COST") and "|SENS|" not in n]) == 6 * len(L.levels())
    assert len([n for n in b if n.endswith("|AS")]) == 3 * (len(L.levels()) - 12)
    assert len([n for n in b if "|SENS|" in n]) == 22
    assert b["TPB+rule|R5|OFF|COST"]["skip"] == 0.5 and "skip" not in b["TPB|R5|OFF|COST"]
    assert b["LIVE|SHIPPED|AS"]["cfg"] == {} and "cost" not in b["LIVE|SHIPPED|AS"]
    assert b["TPB|ALLIN_NOSTOP|COST"]["members"][0]["exit"] == "HOLD"
    assert len({L.Y.digest(v) for v in b.values()}) == len(b)


def test_close_record_puts_the_cost_in_the_path():
    leg = SimpleNamespace(tradingsymbol="X", direction="LONG", bar_ts="", entry_time="", entry_premium=100.0, lots=10,
                          lot_size=65, entry_underlying=0.0, stop_underlying=0.0, fills=[], initial_qty=650, pyramided=False,
                          qty=650)
    L._COST[:] = [200.0, 5.0]
    try:
        with_cost, final = L.close_record(leg, datetime(2026, 3, 2), 110.0, "x", 1.0)
    finally:
        L._COST[:] = [0.0, 0.0]
    plain, base = L.close_record(leg, datetime(2026, 3, 2), 110.0, "x", 1.0)
    assert with_cost["extra_cost"] == (200 + 5 * 10) * 10
    assert abs((base - final) - 2500.0) < 1e-6 and abs((plain["net_pnl"] - with_cost["net_pnl"]) - 2500.0) < 1e-3


def _t(day, hour, prem, lots, exit_px, cost=None):
    from fno_costs import calc_fno_costs
    qty = lots * 65
    extra = (cost[0] + cost[1] * lots) * lots if cost else 0.0
    net = (exit_px - prem) * qty - calc_fno_costs(prem, exit_px, qty) - extra
    return {"entry_time": f"{day}T{hour:02d}:00:00+05:30", "exit_time": f"{day}T{hour:02d}:30:00+05:30", "entry_premium": prem,
            "exit_premium": exit_px, "entry_qty": qty, "lots_at_exit": lots, "net_pnl": net, "extra_cost": extra}


LEVEL = {"cfg": {"FNO_TWO_STRIKE_LOSSES": 1_000_000, "FNO_MAX_RISK_PCT": 0.05, "FNO_STOP_PREMIUM_PCT": 0.25}}


def test_check_book_passes_a_correct_replay():
    # 5% of 2,50,000 = 12,500; 100 x 65 x 25% = 1,625 a lot: 7 lots
    assert A.check_book([_t("2026-03-02", 10, 100.0, 7, 110.0)], LEVEL, 250000.0, None, 3) == {}


def test_check_book_catches_wrong_lots_cash_net_and_day_cap():
    assert "lots_not_the_formula" in A.check_book([_t("2026-03-02", 10, 100.0, 9, 110.0)], LEVEL, 250000.0, None, 3)
    assert "over_own_cash" in A.check_book([_t("2026-03-02", 10, 100.0, 40, 110.0)], None, 250000.0, None, 3)
    wrong = _t("2026-03-02", 10, 100.0, 7, 110.0)
    wrong["net_pnl"] += 50.0
    assert "net_wrong" in A.check_book([wrong], LEVEL, 250000.0, None, 3)
    many = [_t("2026-03-02", h, 100.0, 1, 100.0) for h in (9, 10, 11, 12)]
    assert "over_day_cap" in A.check_book(many, None, 250000.0, None, 3)
    assert "extra_cost_wrong" in A.check_book([_t("2026-03-02", 10, 100.0, 7, 110.0)], LEVEL, 250000.0, [200.0, 5.0], 3)
    assert "unresolved" in A.check_book([{"status": "UNRESOLVED"}], None, 250000.0, None, 3)


def test_path_measures_fall_and_wipe_out():
    tr = [_t("2026-03-02", 10, 100.0, 10, 200.0), _t("2026-03-03", 10, 100.0, 30, 0.05)]
    s = A.path(tr)
    assert s["fall_pct"] > 0.5 and s["worst_day_date"] == "2026-03-03" and s["worst_trade"] < -190000
    assert A.path([_t("2026-03-02", 10, 100.0, 38, 0.05)])["wiped_out"]


def test_balanced_rule():
    good = {"y2025": {"net": 1, "trades": 40}, "y2026": {"net": 1, "trades": 40}, "negative_halves": 1,
            "carried": {"fall_pct": 0.25, "wiped_out": False}}
    assert A.balanced_ok(good)
    for change in ({"negative_halves": 2}, {"y2025": {"net": 0, "trades": 40}}, {"y2026": {"net": 1, "trades": 39}},
                   {"carried": {"fall_pct": 0.26, "wiped_out": False}}):
        assert not A.balanced_ok({**good, **change})


def test_run_book_restores_settings_and_history():
    from config import settings
    data = SimpleNamespace(paper_closes=lambda: [])
    seen = {}

    def fake_run(self, start, end):
        seen["risk"], seen["cost"] = settings.FNO_MAX_RISK_PCT, list(L._COST)
        return {"notes": {}, "start_equity": 1.0}

    before_run, before_history = L._prev_run, L.history
    L._prev_run, L.history = fake_run, lambda key: [("at", -5.0, "SINGLE_LEG")]
    try:
        fake = SimpleNamespace(book={"cfg": {"FNO_MAX_RISK_PCT": 0.5}, "cost": [200.0, 5.0]}, data=data)
        L.run_book(fake, "a", "b")
    finally:
        L._prev_run, L.history = before_run, before_history
    assert seen == {"risk": 0.5, "cost": [200.0, 5.0]}
    assert settings.FNO_MAX_RISK_PCT == 0.02 and L._COST == [0.0, 0.0]
    assert Counter({"x": 1})["x"] == 1
