import copy

import pytest

from config import settings
from cost_schedules import (
    EQUITY_INTRADAY_SCHEDULE_VERSION,
    OPTIONS_SCHEDULE_VERSION,
    equity_intraday_cost_snapshot,
    options_cost_snapshot,
)
from engine import calc_zerodha_costs
from fno_costs import calc_fno_costs, calc_fno_costs_from_snapshot
from momentum_shadow import _declared_costs, momentum_shadow_execution_config
from penny_risk import calc_penny_costs
from penny_shadow import COST_MODEL_VERSION, _costs_from_snapshot, _execution_snapshot


def test_current_defaults_and_versioned_metadata():
    assert settings.ZERODHA_EXCHANGE_PCT == 0.0000307
    assert settings.ZERODHA_STAMP_DUTY_PCT == 0.00003
    assert settings.PENNY_EXCHANGE_PCT == 0.0000307
    assert settings.PENNY_STAMP_DUTY_PCT == 0.00003
    assert settings.FNO_STT_SELL_PCT == 0.0015
    assert settings.FNO_EXCHANGE_TXN_PCT == 0.0003553
    assert settings.FNO_STAMP_DUTY_PCT == 0.00003
    assert settings.FNO_IPFT_PCT == 0.000000001

    equity = equity_intraday_cost_snapshot()
    assert equity["schedule_version"] == EQUITY_INTRADAY_SCHEDULE_VERSION
    assert equity["effective_date"] is None
    assert equity["verified_as_of"] == "2026-08-10"
    options = options_cost_snapshot()
    assert options["schedule_version"] == OPTIONS_SCHEDULE_VERSION
    assert options["effective_date"] == "2026-04-01"


def test_equity_intraday_representative_hand_calculation():
    # Buy 500 @ Rs10, sell 500 @ Rs10.50.
    buy, sell = 5000.0, 5250.0
    brokerage = 1.5 + 1.575
    exchange = (buy + sell) * 0.0000307
    sebi = (buy + sell) * 0.000001
    ipft = (buy + sell) * 0.000000001
    expected = (
        brokerage + sell * 0.00025 + exchange + buy * 0.00003 + sebi + ipft
        + 0.18 * (brokerage + exchange + sebi + ipft)
    )
    assert calc_zerodha_costs(10.0, 10.5, 500, True) == pytest.approx(expected, abs=0.0001)
    assert calc_penny_costs(10.0, 10.5, 500, True) == pytest.approx(expected, abs=0.0001)


def test_options_representative_hand_calculation_and_snapshot():
    snapshot = options_cost_snapshot()
    # One 75-unit lot, Rs100 premium in and out.
    expected = 40 + 11.25 + 5.3295 + 0.015 + 0.225 + 0.000015
    expected += 0.18 * (40 + 5.3295 + 0.015 + 0.000015)
    assert calc_fno_costs(100.0, 100.0, 75) == pytest.approx(expected)
    assert calc_fno_costs_from_snapshot(100.0, 100.0, 75, snapshot) == pytest.approx(expected)


def test_shadow_and_replay_execution_snapshots_freeze_schedule_identity():
    penny = _execution_snapshot("TEST")
    assert penny["schedule_version"] == EQUITY_INTRADAY_SCHEDULE_VERSION
    assert penny["verified_as_of"] == "2026-08-10"
    assert penny["rates"]["ipft_pct"] == 0.000000001
    momentum = momentum_shadow_execution_config()
    assert momentum["cost_schedule_version"] == EQUITY_INTRADAY_SCHEDULE_VERSION
    assert momentum["cost_schedule_verified_as_of"] == "2026-08-10"


def test_legacy_frozen_penny_snapshot_arithmetic_is_unchanged():
    legacy = {
        "model": COST_MODEL_VERSION, "origin": "ENTRY", "is_intraday": True,
        "rates": {
            "brokerage_pct": 0.0003, "brokerage_max": 20.0,
            "stt_mis": 0.00025, "exchange_pct": 0.0000345,
            "stamp_duty_pct": 0.00015, "sebi_pct": 0.000001,
            "gst_pct": 0.18,
        },
    }
    buy, sell = 5000.0, 5250.0
    brokerage = 1.5 + 1.575
    exchange = (buy + sell) * 0.0000345
    old_expected = brokerage + sell * 0.00025 + exchange + buy * 0.00015
    old_expected += (buy + sell) * 0.000001 + 0.18 * (brokerage + exchange)
    untouched = copy.deepcopy(legacy)
    assert _costs_from_snapshot(10.0, 10.5, 500, legacy) == round(old_expected, 4)
    assert legacy == untouched


def test_legacy_frozen_momentum_snapshot_does_not_inherit_new_rates():
    legacy = momentum_shadow_execution_config()
    legacy.pop("cost_schedule_version")
    legacy.pop("cost_schedule_effective_date")
    legacy.pop("cost_schedule_verified_as_of")
    legacy.pop("ipft_pct")
    legacy["exchange_pct"] = 0.0000345
    legacy["stamp_duty_buy_pct"] = 0.00015
    before = copy.deepcopy(legacy)
    value = _declared_costs(10.0, 10.5, 500, legacy)
    brokerage, exchange = 3.075, 10250 * 0.0000345
    expected = brokerage + 5250 * 0.00025 + exchange + 5000 * 0.00015
    expected += 10250 * 0.000001 + 0.18 * (brokerage + exchange)
    assert value == round(expected, 4)
    assert legacy == before
