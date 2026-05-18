"""
chandelier_stop.py — Chandelier trailing stop implementation.

OPEN QUESTION RESOLUTION (Task 9): GTT (Good Till Triggered) Orders
─────────────────────────────────────────────────────────────────────
Issue: The Chandelier stop exists in this module but is not wired to
       the order execution layer. Regime 3 (Crisis) needs active trailing
       stop management.
Options:
  1. Use Upstox/Kite GTT API for server-side trailing stops
  2. Manage Chandelier stop in-engine (monitor each candle, trigger close)
  3. Defer to T1 partial exit (already implemented in position_tracker)

Decision: Option 2 (recommended path) — The Chandelier stop is managed
in-engine via `position_tracker.py`'s `update_daily_positions()` function.
This function already tracks `highest_close_since_entry` and computes a
trailing stop (highest_close - 1.5 * ATR) after each daily close. This
is more reliable than GTT for the following reasons:
  - GTT orders require exact trigger prices and can miss fills in fast markets
  - In-engine management allows dynamic adjustment based on same-day price action
  - The position_tracker already persists `trailing_stop_current` in SQLite
  - At ₹5K bankroll with max 2 positions, manual monitoring per candle is feasible
  - Upstox/Kite GTT does NOT support trailing stops natively — only fixed GTT

Limitation: The current implementation uses a fixed 1.5x ATR multiplier
(standard Chandelier uses 3.0x). This is intentional — the 3.0x Chandelier
is wider than our current 1.5x initial stop, providing better win rate
at the cost of smaller average wins. When the system is upgraded to full
Chandelier management, the `CHANDELIER_ATR_MULT=3.0` from config.py will
be used instead of the hardcoded 1.5.

TODO(GTT-wiring): When Kite GTT API support for OHLC trigger conditions is
confirmed, implement GTT-based Chandelier stops to reduce manual monitoring.

The Chandelier Stop (developed by Charles LeBouef) is a trailing stop
that trails price by a multiple of Average True Range (ATR).

Formula:
    stop = highest_close_since_entry - (atr_mult * ATR_14)

Unlike a fixed stop, the Chandelier stop:
  1. ONLY moves up (tracks highest close) — never down
  2. Gives winners room to run within their natural volatility
  3. Locks in profit when a trend reverses by the ATR distance

This implementation is for LONG (buy) positions only.

Usage:
    cs = ChandelierStop(entry_price=2500.0, atr=50.0, atr_mult=3.0)
    cs.update(close=2550.0, high=2560.0, low=2530.0)
    if cs.check_stop_out(close=todays_close)[0]:
        print("Stop out!")
"""

import structlog

logger = structlog.get_logger()


class StopResult:
    """Result of a stop-out check."""
    def __init__(self, triggered: bool, price: float, stop_level: float, is_profitable: bool):
        self.triggered = triggered
        self.price = price
        self.stop_level = stop_level
        self.is_profitable = is_profitable

    def __repr__(self):
        return f"StopResult(triggered={self.triggered}, price={self.price}, stop={self.stop_level:.2f}, profitable={self.is_profitable})"


class ChandelierStop:
    """
    Chandelier trailing stop calculator for long positions.

    Tracks the highest closing price since entry and maintains a stop
    at highest_close - (atr_mult * ATR) below it. The stop only moves up.
    """

    def __init__(
        self,
        entry_price: float,
        atr: float,
        atr_mult: float = 3.0,
    ):
        """
        Args:
            entry_price: The price at which the position was entered.
            atr: The current ATR_14 value at entry.
            atr_mult: The ATR multiplier (default 3.0 as per original formula).
        """
        self.entry_price = entry_price
        self._atr = atr
        self._atr_mult = atr_mult
        self._highest_close = entry_price  # Chandelier starts from entry
        self._current_atr = atr  # ATR can be updated each candle

    def update(self, close: float, high: float, low: float, atr: float | None = None) -> None:
        """
        Update the Chandelier stop after a new candle closes.

        The highest close since entry is updated if the current close is higher.
        ATR is also updated if provided (allows for dynamic ATR recomputation).

        Args:
            close: The closing price of the current candle.
            high: The high of the current candle.
            low: The low of the current candle.
            atr: Optional new ATR value. If None, uses the last known ATR.
        """
        if atr is not None:
            self._current_atr = atr

        # Update highest close — Chandelier ONLY moves up
        if close > self._highest_close:
            self._highest_close = close
            logger.debug(
                "chandelier_new_high",
                highest_close=self._highest_close,
                atr=self._current_atr,
                stop=self.get_stop(),
            )

    def get_stop(self) -> float:
        """
        Get the current Chandelier stop level.

        Returns:
            The stop price = highest_close_since_entry - (atr_mult * ATR)
        """
        return self._highest_close - (self._atr_mult * self._current_atr)

    def get_stop_distance_from_close(self, current_close: float) -> float:
        """
        Get the distance (in rupees) between current close and the stop.

        Useful for R-multiple calculations.
        """
        return current_close - self.get_stop()

    def get_r_multiple(self, current_close: float) -> float:
        """
        Get the current R-multiple of the trade (profit measured in risk units).

        R = (current_close - entry_price) / (entry_price - initial_stop)
        """
        risk_distance = self.entry_price - (self.entry_price - (self._atr_mult * self._atr))
        if risk_distance <= 0:
            return 0.0
        return (current_close - self.entry_price) / risk_distance

    def is_profitable(self) -> bool:
        """Returns True if the stop level is now above the entry price."""
        return self.get_stop() > self.entry_price

    def check_stop_out(self, close: float) -> tuple[bool, float]:
        """
        Check if the position has been stopped out.

        A stop-out occurs when the closing price falls below the stop level.

        Args:
            close: The current closing price.

        Returns:
            (triggered: bool, price: float) — triggered is True if stopped out,
            price is the close at which stop was triggered.
        """
        stop_level = self.get_stop()
        if close <= stop_level:
            logger.info(
                "chandelier_stop_out",
                entry=self.entry_price,
                stop_level=stop_level,
                close=close,
                highest_close=self._highest_close,
            )
            return True, close
        return False, close

    def __repr__(self) -> str:
        return (
            f"ChandelierStop(entry={self.entry_price}, "
            f"highest_close={self._highest_close}, "
            f"atr={self._current_atr}, "
            f"atr_mult={self._atr_mult}, "
            f"stop={self.get_stop():.2f})"
        )