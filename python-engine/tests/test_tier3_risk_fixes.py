"""
[ROADMAP-3.4/3.6/3.7/3.8 2026-07-12] Tier-3 risk-correctness witnesses.

3.4 swing sizing assumes gap risk (stop_distance x SWING_GAP_RISK_MULT)
3.6 vol_rank scaled to daily-equivalent (bars_per_day) so the 40%-weight
    regime input stops being ~0 forever
3.7 penny kill-switch day-window keys off IST midnight, not UTC
3.8 RiskEngine.calc_shares returns 0 (not 1) when capital caps floor out
"""
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from config import settings
from engine import evaluate_signal
from models import Regime
from penny_risk import PennyRiskEngine
from risk_engine import RiskEngine


# ===================================================================
# 3.4 -- swing gap-risk sizing
# ===================================================================

@pytest.fixture
def accepted_swing_df():
    """250 daily bars engineered to be ACCEPTED by evaluate_signal in
    R1: uptrend above EMA200, RSI(14) inside 45-72 (gentle rise with
    pullbacks), final-bar volume spike for the ratio/z-score gates."""
    n = 250
    closes = [400.0]
    for i in range(1, n):
        # 3 up, 1 down pattern: net uptrend, RSI stays mid-band.
        step = 0.006 if (i % 4) else -0.008
        closes.append(closes[-1] * (1 + step))
    closes = np.array(closes)
    volumes = np.array([200_000 + (i % 5) * 10_000 for i in range(n)], dtype=float)
    volumes[-1] = 600_000.0
    df = pd.DataFrame({
        "open": np.roll(closes, 1),
        "high": closes * 1.015,
        "low": closes * 0.985,
        "close": closes,
        "volume": volumes,
    })
    df.index = pd.date_range("2025-06-01", periods=n, freq="B")
    return df


class TestSwingGapRiskSizing:
    def test_fixture_is_accepted(self, accepted_swing_df):
        """Guard: the sizing comparison below is meaningless unless the
        signal actually fires."""
        fired, res = evaluate_signal(
            "GAPTEST", accepted_swing_df, bankroll=1_000_000, risk_pct=0.02,
            regime=Regime.REGIME_1_NORMAL,
        )
        assert fired is True, f"fixture no longer accepted: {res}"

    def test_gap_mult_halves_shares(self, accepted_swing_df, monkeypatch):
        monkeypatch.setattr(settings, "SWING_GAP_RISK_MULT", 1.0)
        _, res_old = evaluate_signal(
            "GAPTEST", accepted_swing_df, bankroll=1_000_000, risk_pct=0.02,
            regime=Regime.REGIME_1_NORMAL,
        )
        monkeypatch.setattr(settings, "SWING_GAP_RISK_MULT", 2.0)
        _, res_new = evaluate_signal(
            "GAPTEST", accepted_swing_df, bankroll=1_000_000, risk_pct=0.02,
            regime=Regime.REGIME_1_NORMAL,
        )
        # floor(x/2) can be off-by-one from floor(x)/2; allow that.
        assert res_new["shares"] <= res_old["shares"] // 2 + 1
        assert res_new["shares"] >= 1

    def test_stop_and_targets_unchanged_by_gap_mult(
        self, accepted_swing_df, monkeypatch
    ):
        """The multiplier only shrinks the share count -- the stop level
        and R-multiple targets stay anchored to the raw stop distance."""
        monkeypatch.setattr(settings, "SWING_GAP_RISK_MULT", 1.0)
        _, res_old = evaluate_signal(
            "GAPTEST", accepted_swing_df, bankroll=1_000_000, risk_pct=0.02,
            regime=Regime.REGIME_1_NORMAL,
        )
        monkeypatch.setattr(settings, "SWING_GAP_RISK_MULT", 2.0)
        _, res_new = evaluate_signal(
            "GAPTEST", accepted_swing_df, bankroll=1_000_000, risk_pct=0.02,
            regime=Regime.REGIME_1_NORMAL,
        )
        assert res_new["stop_loss"] == res_old["stop_loss"]
        assert res_new["target_1"] == res_old["target_1"]


# ===================================================================
# 3.6 -- vol_rank daily-equivalent scaling
# ===================================================================

class TestVolRankScaling:
    def _one_day_1min_closes(self, per_bar_sd: float, n: int = 375):
        """Synthetic 1-min close series with a known per-bar return sd."""
        rng = np.random.default_rng(42)
        rets = rng.normal(0.0, per_bar_sd, n - 1)
        closes = 100.0 * np.exp(np.cumsum(np.insert(rets, 0, 0.0)))
        return closes.tolist()

    def test_unscaled_1min_feed_was_dead_weight(self):
        """The pre-fix behaviour: raw 1-min stdev vs the 0.10 daily cap
        pins the rank near 0 even for a violently volatile ticker."""
        from penny_regime import PennyRegimeEngine
        eng = PennyRegimeEngine()
        closes = self._one_day_1min_closes(per_bar_sd=0.004)  # wild
        assert eng.compute_vol_rank(closes) < 0.10

    def test_scaled_1min_feed_is_meaningful(self):
        """With bars_per_day=375 the same wild ticker ranks high --
        daily-equivalent sd = 0.004 * sqrt(375) ~= 7.7%."""
        from penny_regime import PennyRegimeEngine
        eng = PennyRegimeEngine()
        closes = self._one_day_1min_closes(per_bar_sd=0.004)
        rank = eng.compute_vol_rank(closes, bars_per_day=375)
        assert rank > 0.6

    def test_scaled_quiet_ticker_ranks_low(self):
        """Quiet ticker (per-bar sd 0.0005 -> ~1% daily) must NOT be
        inflated into PR2/PR3 territory by the scaling."""
        from penny_regime import PennyRegimeEngine
        eng = PennyRegimeEngine()
        closes = self._one_day_1min_closes(per_bar_sd=0.0005)
        rank = eng.compute_vol_rank(closes, bars_per_day=375)
        assert rank < 0.3


# ===================================================================
# 3.7 -- penny kill-switch IST day window
# ===================================================================

class TestPennyKillSwitchISTDay:
    def _tripped_engine(self):
        """Engine with a kill-switch-level loss recorded during the
        2026-07-08 IST session (15:25 IST = 09:55 UTC)."""
        eng = PennyRiskEngine(bankroll=10_000.0)
        loss = -(10_000.0 * settings.PENNY_DAILY_KILL_SWITCH_PCT + 1.0)
        eng.record_realized_pnl(
            loss, when=datetime(2026, 7, 8, 9, 55, tzinfo=timezone.utc)
        )
        return eng

    def test_active_through_ist_evening(self):
        eng = self._tripped_engine()
        # 23:59 IST same day = 18:29 UTC
        assert eng.kill_switch_active(
            as_of=datetime(2026, 7, 8, 18, 29, tzinfo=timezone.utc)
        ) is True

    def test_resets_at_ist_midnight_not_0530(self):
        """00:01 IST on the 9th is 18:31 UTC on the 8th -- the OLD
        UTC-keyed window kept the switch active here until 05:30 IST."""
        eng = self._tripped_engine()
        assert eng.kill_switch_active(
            as_of=datetime(2026, 7, 8, 18, 31, tzinfo=timezone.utc)
        ) is False

    def test_pnl_after_ist_midnight_lands_on_next_day(self):
        eng = PennyRiskEngine(bankroll=10_000.0)
        # 00:15 IST 2026-07-09 == 18:45 UTC 2026-07-08
        eng.record_realized_pnl(
            -100.0, when=datetime(2026, 7, 8, 18, 45, tzinfo=timezone.utc)
        )
        assert eng.daily_pnl_date == "2026-07-09"

    def test_naive_datetime_treated_as_utc(self):
        """Legacy callers pass utcnow() (naive); day-keying must not
        crash or misread it as IST."""
        eng = PennyRiskEngine(bankroll=10_000.0)
        eng.record_realized_pnl(-50.0, when=datetime(2026, 7, 8, 9, 55))
        assert eng.daily_pnl_date == "2026-07-08"


# ===================================================================
# 3.8 -- calc_shares returns 0 when capital caps floor out
# ===================================================================

class TestCalcSharesZeroFloor:
    def test_stock_pricier_than_bankroll_returns_zero(self):
        """5,000 bankroll, 6,000 stock: the old max(1, shares) bought a
        share the bankroll cannot pay for."""
        re = RiskEngine(bankroll=5_000.0, regime_risk_pct=0.10)
        assert re.calc_shares(entry=6_000.0, stop=5_700.0) == 0

    def test_capital_cap_flooring_to_zero_returns_zero(self):
        """Per-trade capital cap (10% of 50k = 5k) vs a 6k stock: the
        cap computes 0 shares and 0 must be returned, not 1."""
        re = RiskEngine(bankroll=50_000.0, regime_risk_pct=0.10)
        shares = re.calc_shares(
            entry=6_000.0, stop=5_700.0, max_capital_per_trade=0.10
        )
        assert shares == 0

    def test_normal_sizing_unaffected(self):
        re = RiskEngine(bankroll=50_000.0, regime_risk_pct=0.10)
        # risk 5000 / rps 5 = 1000 -> capital capped to 250 @ entry 200
        assert re.calc_shares(entry=200.0, stop=195.0) == 250
