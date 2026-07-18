"""
[PENNY-CONFIG 2026-06-21] Smoke test that all PENNY_* settings exist with
their documented defaults. Catches typos and missing settings early.
"""


def test_penny_universe_settings():
    from config import settings
    assert settings.PENNY_PRICE_MIN == 1.0
    assert settings.PENNY_PRICE_MAX == 55.0
    assert settings.PENNY_UNIVERSE_SIZE == 100
    assert settings.PENNY_MIN_20D_TV == 500_000.0
    assert settings.PENNY_MAX_PROMOTER_HOLD == 0.75
    assert settings.PENNY_REFRESH_HOUR == 8


def test_penny_connors_settings():
    from config import settings
    assert settings.PENNY_CONNORS_RSI2_BUY == 10.0
    assert settings.PENNY_CONNORS_RSI2_SELL == 65.0
    assert settings.PENNY_CONNORS_T1_PCT == 0.03
    assert settings.PENNY_CONNORS_T2_PCT == 0.06
    assert settings.PENNY_CONNORS_STOP_PCT == 0.03
    assert settings.PENNY_CONNORS_MAX_HOLD_DAYS == 3
    assert settings.PENNY_CONNORS_TRAIL_ATR_MULT == 2.0


def test_penny_breakout_settings():
    from config import settings
    # [PENNY-AGGRESSIVE 2026-06-24] Relaxed from 3.0 -> 1.8 to allow more entries.
    assert settings.PENNY_BREAKOUT_VOL_MULT == 1.8
    assert settings.PENNY_BREAKOUT_TARGET_R == 2.0
    assert settings.PENNY_BREAKOUT_TIME_START == 10 * 60 + 30   # 10:30
    assert settings.PENNY_BREAKOUT_TIME_END == 14 * 60 + 30     # 14:30
    assert settings.PENNY_BREAKOUT_TIME_EXIT == 15 * 60         # 15:00
    # [PENNY-TIME-STOP 2026-06-24] new soft time-stop
    assert settings.PENNY_TIME_STOP_MIN == 30
    # [PENNY-PREMARKET 2026-06-24] pre-market digest defaults
    assert settings.PENNY_PREMARKET_REPORT_HOUR == 7
    assert settings.PENNY_PREMARKET_REPORT_MIN == 50
    assert settings.PENNY_PREMARKET_TOP_N == 10
    assert settings.PENNY_MIS_SMART_EOD_TIME == 14 * 60 + 30    # 14:30
    assert settings.PENNY_MIS_SMART_EOD_WITHIN_R == 0.5
    assert settings.PENNY_MIS_SMART_EOD_LOSS_MIN == 30


def test_penny_risk_settings():
    from config import settings
    assert settings.PENNY_LIVE_BANKROLL == 2000.0
    assert settings.PENNY_PAPER_BANKROLL == 500.0
    assert settings.PENNY_RISK_PCT_PR1 == 0.05
    assert settings.PENNY_RISK_PCT_PR2 == 0.025
    # [PR3-FALSIFIABLE] 0.01, not 0.0: PR3 trades small rather than
    # shutting off -- a 0-size regime can never produce an accept, so no
    # watchdog or backtest could ever validate it (config.py comment).
    assert settings.PENNY_RISK_PCT_PR3 == 0.01
    assert settings.PENNY_DAILY_KILL_SWITCH_PCT == 0.20
    assert settings.PENNY_PER_STOCK_CAP == 500.0
    assert settings.PENNY_MAX_POSITIONS_TOTAL == 5
    assert settings.PENNY_MAX_POSITIONS_CNC == 2
    assert settings.PENNY_MAX_POSITIONS_MIS == 3
    assert settings.PENNY_CIRCUIT_SKIP_DISTANCE == 0.005
    assert settings.PENNY_CIRCUIT_FROM_HIGH_PCT == 0.03


def test_penny_cadence_and_safety_defaults():
    from config import settings
    assert settings.PENNY_SCAN_INTERVAL_SEC == 30
    # Default live=True (Uru 2026-06-22: testing budget opt-in)
    assert settings.PENNY_LIVE_TRADING is True
    assert settings.PENNY_DISABLE_TICKERS == ""
    # Additions by Uru 2026-06-21
    assert settings.PENNY_MIN_PROMOTER_HOLD == 0.25
    assert settings.PENNY_MAX_PB_RATIO == 2.0
    # Executor flow (spec §7.2)
    assert settings.PENNY_ENTRY_FILL_TIMEOUT_SEC == 60.0
    assert settings.PENNY_SL_M_MAX_ATTEMPTS == 2
    # Hourly report (spec §9.4)
    assert settings.PENNY_HOURLY_REPORT_START_HOUR == 10
    assert settings.PENNY_HOURLY_REPORT_END_HOUR == 14
    assert settings.PENNY_HOURLY_REPORT_WEBHOOK == ""
