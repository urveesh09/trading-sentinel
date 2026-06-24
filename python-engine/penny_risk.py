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
    def __init__(self, bankroll: float, ledger_writer=None):
        """
        Args:
            bankroll:      current penny pool bankroll (PENNY_LIVE_BANKROLL or PENNY_PAPER_BANKROLL).
            ledger_writer: Optional async callable(ticker, pnl) -> None.
                           If provided, every record_close() call also writes the
                           realized P&L to the bankroll_ledger with source='PENNY'.
                           If None (default), record_close() only updates the
                           in-memory daily_pnl counter -- no ledger write.

                           The injection pattern preserves the isolation rule
                           (penny_risk.py MUST NOT import from performance). The
                           call site in main.py wires a lambda that calls
                           performance.record_trade_close(..., source='PENNY').
        """
        from config import settings
        self.bankroll = bankroll
        self.daily_pnl: float = 0.0
        self.daily_pnl_date: str = ""
        self.disable_tickers: str = settings.PENNY_DISABLE_TICKERS
        self._ledger_writer = ledger_writer

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

    def record_close(
        self,
        entry_price: float,
        exit_price: float,
        shares: int,
        is_intraday: bool,
        when: datetime,
        ticker: str = "",
    ) -> None:
        """
        Record a penny position close: net P&L (after costs) is added to
        daily_pnl. The kill-switch warning fires if the day's loss exceeds
        20% of the bankroll.

        Per the 2026-06-22 deviation: this is the missing wiring that
        was preventing the kill-switch from ever firing.

        Per the 2026-06-24 bankroll fix: also schedules a ledger write of
        the realized P&L with source='PENNY' (via the injected ledger_writer).
        The ledger_writer is optional -- if None, only the in-memory
        daily_pnl counter is updated (preserves back-compat with existing
        tests that don't pass a writer).

        `ticker` is optional -- pass it from the call site (the scanner /
        connors / breakout engines) so the ledger row has a useful ticker
        label for /performance filtering.
        """
        gross = (exit_price - entry_price) * shares
        costs = calc_penny_costs(entry_price, exit_price, shares, is_intraday)
        net = gross - costs
        self.record_realized_pnl(net, when)
        logger.info(
            "penny_position_closed ticker=%s entry=%.2f exit=%.2f shares=%d "
            "gross=%.2f costs=%.2f net=%.2f",
            ticker or "?", entry_price, exit_price, shares, gross, costs, net,
        )
        # Persist to bankroll_ledger so the dashboard reflects penny P&L.
        # Best-effort: a ledger write failure must not silently swallow
        # the close -- log it loudly but don't raise (the daily_pnl counter
        # and kill-switch gate are still authoritative for risk decisions).
        #
        # The ledger_writer is async. record_close itself is sync (called from
        # the 30s scanner loop). Two cases:
        #   1. Inside an event loop (prod): schedule via asyncio.create_task.
        #   2. Outside a loop (tests): silently skip the write -- the test can
        #      await the writer directly if it needs to assert the ledger row.
        if self._ledger_writer is not None:
            try:
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop is not None:
                    loop.create_task(
                        self._ledger_writer(ticker or "PENNY", net)
                    )
                # If no running loop, we silently drop the write -- the
                # in-memory daily_pnl is still updated for risk gating.
            except Exception as e:
                logger.error(
                    "penny_ledger_write_failed ticker=%s net=%.2f error=%s",
                    ticker or "?", net, str(e),
                )

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


# ---- 2026-06-22: cost accounting + record_close -----------------------------

def calc_penny_costs(
    entry_price: float,
    exit_price: float,
    shares: int,
    is_intraday: bool,
) -> float:
    """
    Round-trip Zerodha cost model for the penny subsystem.

    Local implementation (does not import from engine.calc_zerodha_costs)
    per the isolation rule. Mirrors the engine's logic but uses
    PENNY_* settings instead of ZERODHA_*.

    Returns total cost in rupees (brokerage + STT + exchange + stamp +
    SEBI + GST).
    """
    from config import settings
    buy_value = entry_price * shares
    sell_value = exit_price * shares

    exchange_txn = (buy_value + sell_value) * settings.PENNY_EXCHANGE_PCT
    stamp_duty = buy_value * settings.PENNY_STAMP_DUTY_PCT
    sebi = (buy_value + sell_value) * settings.PENNY_SEBI_PCT

    brokerage_buy = min(buy_value * settings.PENNY_BROKERAGE_PCT, settings.PENNY_BROKERAGE_MAX)
    brokerage_sell = min(sell_value * settings.PENNY_BROKERAGE_PCT, settings.PENNY_BROKERAGE_MAX)

    stt_rate = settings.PENNY_STT_MIS if is_intraday else settings.PENNY_STT_CNC
    stt = sell_value * stt_rate

    gst = (brokerage_buy + brokerage_sell + exchange_txn) * settings.PENNY_GST_PCT

    return round(
        brokerage_buy + brokerage_sell + stt + exchange_txn +
        stamp_duty + sebi + gst,
        4,
    )
