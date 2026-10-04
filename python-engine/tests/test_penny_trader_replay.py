"""PEN_TRADER candidates inside the Penny lifecycle replay (research only)."""
import pytest

from tests.test_penny_lifecycle_replay import _bars, _breakout_day, _run

EARLY = {"09:50": (99.5, 100.6, 99.4, 100.55, 4000.0), "09:51": (100.6, 100.9, 100.5, 100.8, 1500.0)}
HOLD = (100.8, 101.0, 100.6, 100.9, 1000.0)


def _early(**extra):
    return _bars(overrides={**EARLY, **extra.pop("overrides", {})}, post_from="09:52", post=HOLD, **extra)


def test_trader_recovers_baseline_rejected_setup_with_structural_stop():
    assert _run(_early())["trades"] == []
    result = _run(_early(), candidate_policy="PEN_TRADER_V1")
    trade = result["trades"][0]
    assert trade["entry_kind"] == "FAST_BREAKOUT"
    assert (trade["baseline_status"], trade["baseline_reject_code"]) == ("baseline_rejected", "TIME_WINDOW")
    # Fill at the next minute's LTP (open of 09:51), never the signal close.
    assert trade["entry_fill_ts"].endswith("09:51:00+05:30") and trade["entry_fill_price"] == 100.6
    # Structural stop below the frozen base high, not the breakout candle low.
    assert trade["stop_price"] == trade["initial_stop_price"] < 100.0
    assert trade["shares"] * trade["entry_fill_price"] <= 500
    assert result["candidate"]["params"]["entry"]["policy_version"] == "PEN_TRADER_V1"
    assert trade["score_components"]


def test_trader_never_bypasses_shipped_hard_constraints():
    result = _run(_early(), candidate_policy="PEN_TRADER_V1", regime="PR3_HOT")
    assert result["trades"] == []


def test_v2_requires_day_high_structure_inside_its_window():
    assert _run(_early(), candidate_policy="PEN_TRADER_V2")["trades"] == []
    surge = {"10:30": (99.5, 100.6, 99.4, 100.55, 4000.0), "10:31": (100.6, 100.9, 100.5, 100.8, 1500.0)}
    trades = _run(_bars(overrides=surge, post_from="10:32", post=HOLD), candidate_policy="PEN_TRADER_V2")["trades"]
    assert len(trades) == 1 and trades[0]["thesis_id"].startswith("PEN-")


def test_base_thesis_keeps_shipped_entries_and_changes_only_exits():
    baseline = _run(_breakout_day())["trades"]
    candidate = _run(_breakout_day(), candidate_policy="PEN_BASE_THESIS")["trades"]
    keys = ("entry_fill_ts", "entry_fill_price", "shares", "initial_stop_price")
    assert [(t["entry_fill_ts"], t["entry_fill_price"], t["shares"]) for t in baseline] == \
        [tuple(t[k] for k in keys[:3]) for t in candidate]
    assert candidate[0]["initial_stop_price"] == baseline[0]["stop_price"]
    assert candidate[0]["entry_kind"] == "SHIPPED_BREAKOUT"


def test_thesis_partial_leg_is_costed_and_r_uses_initial_stop():
    # Enter at 09:51 (100.6, stop 98.0, R=2.6); rally through 2R (105.8) then
    # fall back so the trailed stop exits the runner.
    rally = {"10:20": (101.0, 106.0, 100.9, 105.9, 3000.0), "10:21": (105.9, 106.2, 105.0, 105.5, 2000.0),
             "10:22": (105.0, 105.1, 101.0, 101.2, 2000.0), "10:23": (101.2, 101.3, 100.8, 101.0, 2000.0)}
    result = _run(_early(overrides=rally), candidate_policy="PEN_TRADER_V1_THESIS")
    trade = result["trades"][0]
    assert trade["partial_fills"][0]["quantity"] == trade["shares"] // 2
    assert trade["partial_fills"][0]["price"] == pytest.approx(100.6 + 2 * (100.6 - trade["initial_stop_price"]))
    assert trade["stop_price"] > trade["initial_stop_price"]       # trailed, never lowered
    risk = (trade["entry_fill_price"] - trade["initial_stop_price"]) * trade["shares"]
    assert trade["r_multiple"] == pytest.approx(trade["net_pnl"] / risk, rel=1e-4)
    assert trade["net_pnl"] > 0 and trade["costs"] > 0
