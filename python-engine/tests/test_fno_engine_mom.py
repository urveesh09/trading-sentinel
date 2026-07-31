"""
[FNO-MOM-TESTS 2026-07-10] FNO-MOM engine (spec §8). Includes the
strategy-level satisfiability witnesses: a constructible LONG and a
constructible SHORT input that ACCEPT -- the engine cannot ship with an
unsatisfiable breakout condition (§9.1 discipline applied to the signal
layer, not just the gates).

Bars are synthetic 5-min futures candles: 5 flat prior sessions (feed
the EMA and the per-slot RVOL baseline) + a scripted today.
"""
from datetime import datetime

import pandas as pd
import pytest
import pytz

from config import settings
from fno_engine_mom import evaluate_fno_mom, wilder_atr
from fno_models import FnoDirection

IST = pytz.timezone("Asia/Kolkata")
PRIOR_DAYS = ["2026-07-03", "2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09"]
TODAY = "2026-07-10"


def _flat_session(day: str, px: float = 25000.0, vol: float = 100.0) -> pd.DataFrame:
    idx = pd.date_range(f"{day} 09:15", periods=74, freq="5min")
    return pd.DataFrame({
        "open": px, "high": px + 5, "low": px - 5, "close": px, "volume": vol,
    }, index=idx)


def _today_bars(rows) -> pd.DataFrame:
    """rows: list of (hh:mm, open, high, low, close, volume)."""
    idx = pd.to_datetime([f"{TODAY} {hm}" for hm, *_ in rows])
    cols = list(zip(*[r[1:] for r in rows]))
    return pd.DataFrame({
        "open": cols[0], "high": cols[1], "low": cols[2],
        "close": cols[3], "volume": cols[4],
    }, index=idx)


def _frame(today_rows) -> pd.DataFrame:
    return pd.concat([_flat_session(d) for d in PRIOR_DAYS] + [_today_bars(today_rows)])


OR_ROWS = [
    # six 5-min bars 09:15-09:40 -> OR window (09:15-09:45)
    ("09:15", 25000, 25010, 24990, 25000, 100),
    ("09:20", 25000, 25008, 24992, 25000, 100),
    ("09:25", 25000, 25010, 24990, 25000, 100),
    ("09:30", 25000, 25007, 24993, 25000, 100),
    ("09:35", 25000, 25009, 24991, 25000, 100),
    ("09:40", 25000, 25010, 24990, 25000, 100),
]

LONG_BREAKOUT_ROWS = OR_ROWS + [
    ("09:45", 25000, 25008, 25000, 25005, 100),
    ("09:50", 25005, 25010, 25002, 25005, 100),
    ("09:55", 25010, 25105, 25005, 25100, 300),   # fresh break, 3x volume
]

SHORT_BREAKOUT_ROWS = OR_ROWS + [
    ("09:45", 25000, 25000, 24992, 24995, 100),
    ("09:50", 24995, 24998, 24990, 24995, 100),
    ("09:55", 24990, 24995, 24895, 24900, 300),
]

NOW = IST.localize(datetime(2026, 7, 10, 10, 3))


# ---------------------------------------------------------------------------
# satisfiability witnesses
# ---------------------------------------------------------------------------

def test_long_breakout_witness_accepts():
    sig = evaluate_fno_mom(_frame(LONG_BREAKOUT_ROWS), "REGIME_1_NORMAL", NOW)
    assert sig.reject_reason == ""
    assert sig.direction == FnoDirection.LONG
    assert sig.bar_ts == "2026-07-10 09:55:00"
    assert sig.close == 25100.0
    assert sig.or_high == 25010.0 and sig.or_low == 24990.0
    assert sig.rvol == pytest.approx(3.0)
    assert sig.ema_fast > sig.ema_slow
    # tightest stop wins: volatility stop (close - 1.5*ATR) beats OR_low
    assert sig.stop_underlying == pytest.approx(25100.0 - 1.5 * sig.atr)
    r = sig.close - sig.stop_underlying
    # [NAKED-LEG-EXPECTANCY 2026-07-31] Target multiple is configurable
    # (moved 1.5 -> 1.8); assert the relationship, not the literal.
    assert sig.target_underlying == pytest.approx(
        sig.close + settings.FNO_TARGET_R * r
    )


def test_short_breakout_witness_accepts():
    sig = evaluate_fno_mom(_frame(SHORT_BREAKOUT_ROWS), "REGIME_1_NORMAL", NOW)
    assert sig.reject_reason == ""
    assert sig.direction == FnoDirection.SHORT
    assert sig.ema_fast < sig.ema_slow
    assert sig.stop_underlying == pytest.approx(24900.0 + 1.5 * sig.atr)
    r = sig.stop_underlying - sig.close
    assert sig.target_underlying == pytest.approx(
        sig.close - settings.FNO_TARGET_R * r
    )


# ---------------------------------------------------------------------------
# rejections
# ---------------------------------------------------------------------------

def test_empty_frame_rejects():
    sig = evaluate_fno_mom(pd.DataFrame(), "REGIME_1_NORMAL", NOW)
    assert sig.reject_reason == "no_bars"
    assert sig.direction is None


def test_crisis_regime_blocks_valid_breakout():
    sig = evaluate_fno_mom(_frame(LONG_BREAKOUT_ROWS), "REGIME_3_CRISIS", NOW)
    assert sig.direction is None
    assert sig.reject_reason == "regime_crisis"


def test_no_break_rejects():
    rows = OR_ROWS + [
        ("09:45", 25000, 25008, 25000, 25005, 100),
        ("09:50", 25005, 25010, 25002, 25005, 100),
        ("09:55", 25005, 25010, 25000, 25005, 300),
    ]
    sig = evaluate_fno_mom(_frame(rows), "REGIME_1_NORMAL", NOW)
    assert sig.direction is None
    assert sig.reject_reason == "no_or_break"


def test_resident_above_level_is_not_fresh_break():
    """Re-entry rule (§8.2): only a CROSSING bar fires. A bar that merely
    stays above the level after an earlier break is rejected."""
    rows = OR_ROWS + [
        ("09:45", 25000, 25060, 25000, 25050, 100),   # first break happens here
        ("09:50", 25050, 25060, 25040, 25050, 100),   # still above level
        ("09:55", 25050, 25105, 25045, 25100, 300),   # resident, not crossing
    ]
    sig = evaluate_fno_mom(_frame(rows), "REGIME_1_NORMAL", NOW)
    assert sig.direction is None
    assert sig.reject_reason == "not_fresh_break"


def test_rvol_below_min_rejects():
    rows = LONG_BREAKOUT_ROWS[:-1] + [("09:55", 25010, 25105, 25005, 25100, 100)]
    sig = evaluate_fno_mom(_frame(rows), "REGIME_1_NORMAL", NOW)
    assert sig.direction is None
    assert sig.reject_reason == "rvol_below_min"
    assert sig.rvol == pytest.approx(1.0)


def test_ema_disagreement_rejects():
    """Prior sessions much higher -> slow EMA above fast despite the
    intraday OR break: trend filter refuses the countertrend long."""
    frame = pd.concat(
        [_flat_session(d, px=25600.0) for d in PRIOR_DAYS]
        + [_today_bars(LONG_BREAKOUT_ROWS)]
    )
    sig = evaluate_fno_mom(frame, "REGIME_1_NORMAL", NOW)
    assert sig.direction is None
    assert sig.reject_reason == "ema_trend_disagreement"


def test_opening_range_incomplete_before_0945():
    early_now = IST.localize(datetime(2026, 7, 10, 9, 32))
    sig = evaluate_fno_mom(_frame(LONG_BREAKOUT_ROWS), "REGIME_1_NORMAL", early_now)
    assert sig.direction is None
    assert sig.reject_reason == "opening_range_incomplete"


def test_in_progress_bar_is_never_evaluated():
    """At 09:59 the 09:55 bar has not closed; the last CLOSED bar is
    09:50, which has no break -> the engine must not act on a live bar."""
    now_ = IST.localize(datetime(2026, 7, 10, 9, 59))
    sig = evaluate_fno_mom(_frame(LONG_BREAKOUT_ROWS), "REGIME_1_NORMAL", now_)
    assert sig.direction is None
    assert sig.bar_ts == "2026-07-10 09:50:00"


def test_rvol_baseline_unavailable_with_thin_history():
    """<3 prior sessions of the slot -> no honest baseline -> reject
    rather than trade on a made-up number."""
    frame = pd.concat([_flat_session(PRIOR_DAYS[-1])] + [_today_bars(LONG_BREAKOUT_ROWS)])
    sig = evaluate_fno_mom(frame, "REGIME_1_NORMAL", NOW)
    assert sig.direction is None
    assert sig.reject_reason in ("rvol_baseline_unavailable", "ema_insufficient_bars")


def test_wilder_atr_needs_length_plus_one():
    df = _flat_session(TODAY).iloc[:10]
    assert wilder_atr(df, 14) is None
    assert wilder_atr(_flat_session(TODAY), 14) == pytest.approx(10.0, abs=3.0)
