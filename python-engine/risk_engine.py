"""
risk_engine.py -- Dynamic risk management.

Provides:
  1. Dynamic position sizing based on regime and bankroll
  2. Partial exit logic at Target 1
  3. Drawdown-contingent recovery sizing governor

This module is responsible for the "Risk Intelligence" layer of the
adaptive Trading Sentinel system.
"""

import math
import structlog
from dataclasses import dataclass

from config import settings
from models import Regime

logger = structlog.get_logger()


@dataclass
class PartialExitResult:
    """Result of a partial exit check."""
    triggered: bool
    shares_to_exit: int
    exit_price: float
    reason: str


@dataclass
class PositionSizingResult:
    """Result of position sizing calculation."""
    shares: int
    capital_deployed: float
    capital_at_risk: float
    risk_per_trade: float


class RiskEngine:
    """
    Dynamic risk management engine.

    Responsible for:
      - Converting a risk percentage into a share count
      - Managing partial exits at T1
      - Governing post-crisis recovery sizing
    """

    def __init__(
        self,
        bankroll: float,
        regime_risk_pct: float,
    ):
        """
        Args:
            bankroll: Current available capital.
            regime_risk_pct: Risk % for the current regime (e.g. 0.10 for 10%).
        """
        self.bankroll = bankroll
        self._base_risk_pct = regime_risk_pct

        # Drawdown recovery state
        self._recovery_trades_remaining: int = 0
        self._consecutive_wins_in_recovery: int = 0

    def calc_shares(
        self,
        entry: float,
        stop: float,
        max_capital_per_trade: float | None = None,
    ) -> int:
        """
        Calculate number of shares to buy given entry, stop, and risk %.

        risk_per_trade = bankroll * risk_pct
        risk_per_share = entry - stop
        shares = floor(risk_per_trade / risk_per_share)

        Args:
            entry: Entry price per share.
            stop: Stop loss price per share.
            max_capital_per_trade: Optional capital constraint (% of bankroll).

        Returns:
            Number of shares to purchase.
        """
        effective_risk_pct = self.get_effective_risk_pct(
            recovery_active=(self._recovery_trades_remaining > 0)
        )
        risk_per_trade = self.bankroll * effective_risk_pct
        risk_per_share = entry - stop

        if risk_per_share <= 0:
            logger.warning("risk_engine_negative_risk_per_share", entry=entry, stop=stop)
            return 0

        raw_shares = risk_per_trade / risk_per_share
        shares = math.floor(raw_shares)

        if shares <= 0:
            logger.info(
                "risk_engine_zero_shares",
                risk_per_trade=risk_per_trade,
                risk_per_share=risk_per_share,
            )
            return 0

        # Check capital constraint (expressed as % of bankroll)
        if max_capital_per_trade is not None:
            max_shares_by_capital = math.floor(
                (self.bankroll * max_capital_per_trade) / entry
            )
            shares = min(shares, max_shares_by_capital)

        # Check hard bankroll cap on capital required
        capital_required = shares * entry
        if capital_required > self.bankroll:
            shares = math.floor(self.bankroll / entry)

        # [ROADMAP-3.8 2026-07-12] Was `max(1, shares)`: when the capital
        # caps above correctly floored an expensive stock to 0 shares,
        # the old floor bought 1 anyway -- silently violating the very
        # cap that produced the 0. Mirror penny_risk.calc_shares: 0 means
        # "cannot afford within the caps", the caller must skip. (The
        # inline sizing in engine.evaluate_signal already rejects on 0
        # with zero_shares_calculated; this method must agree with it.)
        if shares < 1:
            logger.info(
                "risk_engine_capital_capped_to_zero",
                entry=entry,
                bankroll=self.bankroll,
            )
            return 0
        return shares

    def check_partial_exit(
        self,
        close: float,
        entry: float,
        stop: float,
        shares: int,
    ) -> PartialExitResult:
        """
        Check if partial exit at T1 should be triggered.

        Triggers when price reaches entry + (risk_per_unit * TARGET1_R).
        Exits PARTIAL_EXIT_T1_PCT of the position (default 50%).

        Args:
            close: Current closing price.
            entry: Entry price.
            stop: Stop loss price.
            shares: Total shares held.

        Returns:
            PartialExitResult with triggered flag, shares_to_exit, and exit_price.
        """
        risk_per_share = entry - stop
        t1_price = entry + (risk_per_share * settings.TARGET1_R)

        if close >= t1_price:
            shares_to_exit = math.floor(shares * settings.PARTIAL_EXIT_T1_PCT)
            logger.info(
                "partial_exit_triggered",
                t1_price=t1_price,
                close=close,
                shares_to_exit=shares_to_exit,
                total_shares=shares,
            )
            return PartialExitResult(
                triggered=True,
                shares_to_exit=shares_to_exit,
                exit_price=t1_price,
                reason=f"T1 reached ({settings.TARGET1_R}R)",
            )

        return PartialExitResult(
            triggered=False,
            shares_to_exit=0,
            exit_price=close,
            reason="T1 not yet reached",
        )

    def record_trade_outcome(
        self,
        win: bool,
        in_recovery: bool,
    ) -> None:
        """
        Record the outcome of a trade for drawdown recovery tracking.

        Args:
            win: True if the trade was profitable.
            in_recovery: True if the trade was taken during recovery mode.
        """
        if in_recovery:
            if win:
                self._consecutive_wins_in_recovery += 1
                if self._consecutive_wins_in_recovery >= 2:
                    # Recovery complete -- reset
                    logger.info("drawdown_recovery_complete")
                    self._recovery_trades_remaining = 0
                    self._consecutive_wins_in_recovery = 0
            else:
                # Loss during recovery -- reset win counter but keep recovery active
                self._consecutive_wins_in_recovery = 0
                self._recovery_trades_remaining = max(
                    0, self._recovery_trades_remaining - 1
                )

    def enter_recovery_mode(self) -> None:
        """Manually enter drawdown recovery mode (called after Regime 3 exits)."""
        self._recovery_trades_remaining = settings.DRAWDOWN_RECOVERY_TRADES
        self._consecutive_wins_in_recovery = 0
        logger.info("drawdown_recovery_started", trades=self._recovery_trades_remaining)

    def get_effective_risk_pct(self, recovery_active: bool) -> float:
        """
        Return the effective risk % (accounting for drawdown recovery).

        During recovery, risk is reduced by DRAWDOWN_RECOVERY_MULT (30% reduction).
        """
        base = self._base_risk_pct
        if recovery_active and self._recovery_trades_remaining > 0:
            return base * settings.DRAWDOWN_RECOVERY_MULT
        return base

    def update_bankroll(self, new_bankroll: float) -> None:
        """Update the bankroll after a trade closes."""
        self.bankroll = new_bankroll