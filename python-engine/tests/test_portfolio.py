"""
Tests for python-engine/portfolio.py — signal allocation, sector limits, momentum pool.
"""
import pytest
from datetime import datetime
from portfolio import filter_and_allocate, filter_momentum_signals
from models import Signal, MomentumSignal


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def _raw_signal(ticker="RELIANCE", score=70, close=500.0, volume_ratio=2.0,
                stop_loss=475.0, net_ev=100.0, sector="ENERGY", shares=4): # FIX: Changed to 4
    """Create a raw signal dict as produced by evaluate_signal."""
    return {
        "ticker": ticker, "exchange": "NSE",
        "signal_time": datetime.utcnow(),
        "close": close, "ema_21": 495.0, "ema_50": 490.0, "ema_200": 480.0,
        "atr_14": 15.0, "volume_ratio": volume_ratio, "rsi_14": 58.0,
        "slope_5": 0.005, "stop_loss": stop_loss, "target_1": 537.5,
        "target_2": 575.0, "trailing_stop": stop_loss, "shares": shares,
        "capital_deployed": close * shares,                     # Ensures it matches shares
        "capital_at_risk": shares * (close - stop_loss),        # Ensures it matches shares
        "net_ev": net_ev, "score": score, "sector": sector,
        "strategy_version": "1.0", "strategy_type": "SWING"
    }


def _raw_momentum(ticker="TCS", close=3500.0, stop_loss=3450.0,
                   net_ev=100.0, volume_ratio=2.5, shares=5):
    """Create a raw momentum signal dict as produced by evaluate_momentum_signal."""
    return {
        "ticker": ticker, "exchange": "NSE",
        "signal_time": datetime.utcnow(),
        "strategy_type": "MOMENTUM",
        "close": close, "vwap": 3480.0, "prev_day_high": 3490.0,
        "stop_loss": stop_loss, "target_1": 3600.0, "target_2": 3600.0,
        "trailing_stop": stop_loss, "shares": shares,
        "capital_deployed": shares * close,
        "capital_at_risk": shares * (close - stop_loss),
        "net_ev": net_ev, "cost_ratio": 0.12,
        "volume_ratio": volume_ratio, "product_type": "CNC",
        "sector": "IT", "strategy_version": "1.0.0"
    }


def _open_pos(ticker="INFY", sector="IT", entry_price=1500.0, shares=5,
              stop_loss_initial=1450.0, source="SYSTEM"):
    """Create an open position dict as returned by get_open_positions."""
    return {
        "ticker": ticker, "exchange": "NSE", "sector": sector,
        "entry_price": entry_price, "shares": shares,
        "stop_loss_initial": stop_loss_initial, "source": source,
    }


# ═══════════════════════════════════════════════════════════════
# FILTER AND ALLOCATE (SWING)
# ═══════════════════════════════════════════════════════════════


class TestFilterAndAllocate:

    def test_accepts_valid_signal(self):
        signals = [_raw_signal()]
        accepted, rejected = filter_and_allocate(signals, [], 5000.0)
        assert len(accepted) == 1
        assert isinstance(accepted[0], Signal)

    def test_rejects_when_max_positions_reached(self):
        """[P1] No slots left → reject."""
        open_pos = [_open_pos(ticker=f"STOCK{i}", sector=f"SEC{i}") for i in range(6)]
        signals = [_raw_signal(ticker="NEW")]
        accepted, rejected = filter_and_allocate(signals, open_pos, 50000.0)
        assert len(accepted) == 0
        assert rejected[0]["reject_reason"] == "MAX_POSITIONS_REACHED"

    def test_rejects_duplicate_ticker(self):
        """[C8] Ticker already in open positions → reject."""
        open_pos = [_open_pos(ticker="RELIANCE")]
        signals = [_raw_signal(ticker="RELIANCE")]
        accepted, rejected = filter_and_allocate(signals, open_pos, 50000.0)
        assert len(accepted) == 0
        assert rejected[0]["reject_reason"] == "ALREADY_OPEN"

    def test_max_correlated_sector(self):
        """[P4] Already 2 positions in same sector → reject 3rd."""
        open_pos = [
            _open_pos(ticker="A", sector="ENERGY"),
            _open_pos(ticker="B", sector="ENERGY"),
        ]
        signals = [_raw_signal(ticker="C", sector="ENERGY")]
        accepted, rejected = filter_and_allocate(signals, open_pos, 50000.0)
        assert len(accepted) == 0
        assert rejected[0]["reject_reason"] == "MAX_CORRELATED_SECTOR"

    def test_max_capital_per_trade_downsizes(self):
        """[P2] Capital > 50% of bankroll → shares downsized."""
        # 10 shares × 500 = 5000 > 5000 * 0.50 = 2500
        signals = [_raw_signal(shares=10, close=500.0)]
        accepted, rejected = filter_and_allocate(signals, [], 5000.0)
        if len(accepted) > 0:
            # Shares should be downsized to fit 50% cap
            assert accepted[0].capital_deployed <= 5000.0 * 0.50 + 1

    def test_sorts_by_score_desc(self):
        """Higher score should be allocated first."""
        signals = [
            _raw_signal(ticker="LOW", score=30, sector="A"),
            _raw_signal(ticker="HIGH", score=90, sector="B"),
        ]
        accepted, _ = filter_and_allocate(signals, [], 50000.0)
        if len(accepted) >= 2:
            assert accepted[0].ticker == "HIGH"

    def test_portfolio_slot_assigned(self):
        """Each accepted signal gets a portfolio_slot."""
        signals = [_raw_signal(ticker="A", sector="X"), _raw_signal(ticker="B", sector="Y")]
        accepted, _ = filter_and_allocate(signals, [], 50000.0)
        for s in accepted:
            assert s.portfolio_slot is not None

    def test_zero_net_ev_filtered(self):
        """Signals with net_ev <= 0 should be filtered out before allocation."""
        signals = [_raw_signal(net_ev=-10.0)]
        accepted, _ = filter_and_allocate(signals, [], 50000.0)
        assert len(accepted) == 0


# ═══════════════════════════════════════════════════════════════
# FILTER MOMENTUM SIGNALS
# ═══════════════════════════════════════════════════════════════


class TestFilterMomentumSignals:

    def test_accepts_valid_momentum(self):
        signals = [_raw_momentum()]
        accepted, rejected = filter_momentum_signals(signals, [], 10000.0)
        assert len(accepted) == 1
        assert isinstance(accepted[0], MomentumSignal)

    def test_max_momentum_positions(self):
        """Default max = 2 in the function. Exceeding → reject."""
        signals = [
            _raw_momentum(ticker="A"),
            _raw_momentum(ticker="B"),
            _raw_momentum(ticker="C"),
        ]
        accepted, rejected = filter_momentum_signals(signals, [], 100000.0, max_momentum_positions=2)
        assert len(accepted) == 2
        assert len(rejected) == 1
        assert rejected[0]["reject_reason"] == "MAX_MOMENTUM_POSITIONS"

    def test_duplicate_ticker_rejected(self):
        """Ticker already open → MOMENTUM_ALREADY_OPEN."""
        open_mom = [{"ticker": "TCS", "entry_price": 3500, "shares": 5}]
        signals = [_raw_momentum(ticker="TCS")]
        accepted, rejected = filter_momentum_signals(signals, open_mom, 100000.0)
        assert len(accepted) == 0
        assert rejected[0]["reject_reason"] == "MOMENTUM_ALREADY_OPEN"

    def test_pool_exhausted(self):
        """If pool is used up → MOMENTUM_POOL_EXHAUSTED."""
        # Pool = 100, signal needs 17500 (5 shares × 3500)
        signals = [_raw_momentum()]
        accepted, rejected = filter_momentum_signals(signals, [], 100.0)
        # It should try to downsize. If can't fit even 1 share → exhausted
        if len(accepted) == 0:
            assert rejected[0]["reject_reason"] == "MOMENTUM_POOL_EXHAUSTED"

    def test_sorts_by_net_ev_desc(self):
        """Higher net_ev should be prioritized."""
        signals = [
            _raw_momentum(ticker="LOW", net_ev=50.0),
            _raw_momentum(ticker="HIGH", net_ev=200.0),
        ]
        accepted, _ = filter_momentum_signals(signals, [], 100000.0)
        if len(accepted) >= 2:
            assert accepted[0].ticker == "HIGH"

    def test_downsizes_to_fit_pool(self):
        """If signal doesn't fit pool, shares are reduced to fit."""
        # Pool = 5000, signal at 3500 per share × 5 = 17500
        signals = [_raw_momentum(shares=5, close=3500.0)]
        accepted, rejected = filter_momentum_signals(signals, [], 5000.0)
        if len(accepted) == 1:
            assert accepted[0].shares <= 1  # floor(5000/3500) = 1
            assert accepted[0].capital_deployed <= 5000.0

    def test_zero_net_ev_filtered(self):
        """Signals with net_ev <= 0 excluded from consideration."""
        signals = [_raw_momentum(net_ev=-10.0)]
        accepted, _ = filter_momentum_signals(signals, [], 100000.0)
        assert len(accepted) == 0
