"""
[PENNY-RISK 2026-06-21] Per-trade risk engine for the penny subsystem.

Spec §7. Owns:
  - position sizing by regime (5% / 2.5% / 0%)
  - per-stock cap (Rs 500 hard)
  - position caps (5 total / 2 CNC / 3 MIS)
  - 20% daily loss kill-switch (resets at midnight UTC)
  - NSE circuit-band filter (skip if at band + >3% from day high)
  - PENNY_DISABLE_TICKERS manual kill-switch
  - SL-M order validation (mandatory)

Hard architectural rule (enforced by tests/test_penny_isolation.py):
  this module MUST NOT import from engine, regime, risk_engine, portfolio,
  evaluate_signal, or evaluate_momentum_signal.

State (daily_pnl, disable_tickers) lives on the singleton instance.
"""
import logging
from datetime import datetime, timezone
from typing import List, Tuple

from penny_models import PennyRegime, PennyLeg

logger = logging.getLogger(__name__)


class PennyRiskEngine:
    def __init__(self, bankroll: float):
        from config import settings
        self.bankroll = bankroll
        self.daily_pnl: float = 0.0
        self.daily_pnl_date: str = ""
        self.disable_tickers: str = settings.PENNY_DISABLE_TICKERS

    # ---- sizing ---------------------------------------------------------

    def _risk_pct_for_regime(self, regime: PennyRegime) -> float:
        from config import settings
        return {
            PennyRegime.PR1_CALM: settings.PENNY_RISK_PCT_PR1,
            PennyRegime.PR2_ELEVATED: settings.PENNY_RISK_PCT_PR2,
            PennyRegime.PR3_HOT: settings.PENNY_RISK_PCT_PR3,
            PennyRegime.UNKNOWN: 0.0,
        }.get(regime, 0.0)

    def position_size(self, entry: float, stop_loss: float, regime: PennyRegime) -> int:
        """
        Spec §7.1 sizing.
          shares = floor(risk_per_trade / (entry - stop_loss))
          shares = min(shares, floor(per_stock_cap / entry))
        """
        from config import settings
        risk_per_share = entry - stop_loss
        if risk_per_share <= 0 or self.bankroll <= 0:
            return 0
        risk_budget = self.bankroll * self._risk_pct_for_regime(regime)
        if risk_budget <= 0:
            return 0
        shares_from_risk = int(risk_budget // risk_per_share)
        cap_shares = int(settings.PENNY_PER_STOCK_CAP // entry) if entry > 0 else 0
        return max(0, min(shares_from_risk, cap_shares))

    # ---- kill-switch ----------------------------------------------------

    def record_realized_pnl(self, pnl: float, when: datetime) -> None:
        today = when.date().isoformat()
        if self.daily_pnl_date != today:
            self.daily_pnl = 0.0
            self.daily_pnl_date = today
        self.daily_pnl += pnl
        if self.kill_switch_active(as_of=when):
            logger.warning(
                "penny_kill_switch_triggered daily_pnl=%s bankroll=%s",
                self.daily_pnl, self.bankroll,
            )

    def kill_switch_active(self, as_of: datetime = None) -> bool:
        from config import settings
        when = as_of or datetime.now(timezone.utc)
        today = when.date().isoformat()
        if self.daily_pnl_date != today:
            return False   # new day, reset
        threshold = -1.0 * self.bankroll * settings.PENNY_DAILY_KILL_SWITCH_PCT
        return self.daily_pnl <= threshold

    # ---- circuit filter -------------------------------------------------

    def circuit_blocked(self, last_price: float, day_high: float,
                        prev_close: float, band_pct: float) -> Tuple[bool, str]:
        """
        Spec §7.4: skip if (within 0.5% of band) AND (>3% below day high).
        Distance threshold scales with band_pct per Uru 2026-06-21.
        """
        from config import settings
        if prev_close <= 0 or last_price <= 0:
            return False, ""
        upper_band = prev_close * (1.0 + band_pct)
        lower_band = prev_close * (1.0 - band_pct)
        distance_to_band = min(abs(last_price - upper_band), abs(last_price - lower_band)) / prev_close
        # Scale the skip-distance with band size: 0.5% at 5% band, 1.0% at 10%, 2.0% at 20%
        scaled_skip = settings.PENNY_CIRCUIT_SKIP_DISTANCE * (band_pct / 0.05)
        if distance_to_band >= scaled_skip:
            return False, ""
        # Now check the "from day high" criterion: skip if last > 3% below day high
        if day_high <= 0:
            return False, ""
        dist_from_high = (day_high - last_price) / day_high
        if dist_from_high > settings.PENNY_CIRCUIT_FROM_HIGH_PCT:
            return True, (
                f"circuit: within {distance_to_band * 100:.2f}% of band "
                f"and {dist_from_high * 100:.2f}% below day high"
            )
        return False, ""

    # ---- position caps --------------------------------------------------

    def can_open_new(self, open_positions: List[dict], leg: PennyLeg) -> Tuple[bool, str]:
        from config import settings
        total = len(open_positions)
        cnc = sum(1 for p in open_positions if p.get("leg") == PennyLeg.CNC)
        mis = sum(1 for p in open_positions if p.get("leg") == PennyLeg.MIS)
        if total >= settings.PENNY_MAX_POSITIONS_TOTAL:
            return False, f"max positions reached ({total}/{settings.PENNY_MAX_POSITIONS_TOTAL})"
        if leg == PennyLeg.CNC and cnc >= settings.PENNY_MAX_POSITIONS_CNC:
            return False, f"max CNC positions reached ({cnc}/{settings.PENNY_MAX_POSITIONS_CNC})"
        if leg == PennyLeg.MIS and mis >= settings.PENNY_MAX_POSITIONS_MIS:
            return False, f"max MIS positions reached ({mis}/{settings.PENNY_MAX_POSITIONS_MIS})"
        return True, ""

    # ---- manual disable -------------------------------------------------

    def is_disabled(self, symbol: str) -> bool:
        if not self.disable_tickers:
            return False
        disabled = {s.strip().upper() for s in self.disable_tickers.split(",") if s.strip()}
        return symbol.upper() in disabled

    # ---- order validation ----------------------------------------------

    def validate_order(self, entry_order_type: str, sl_order_type: str) -> Tuple[bool, str]:
        """
        Spec §7.2: every penny entry MUST be paired with an SL-M. Pure market
        order with no SL = blocked. Limit + SL-M = allowed.
        """
        if sl_order_type != "SL-M":
            return False, "SL-M required for every penny entry (spec §7.2)"
        return True, ""
