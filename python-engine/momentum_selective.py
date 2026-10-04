"""Selective Momentum: take a shipped Momentum signal only when the context agrees.

Pure (no I/O), shared by the research replay and, once promoted, the live
scanner. A smart intraday trader does not buy every VWAP reclaim: the
development evidence (Aug–Oct 2026, docs/2026-10-04-momentum-penny-smarter-slice.md)
showed ordinary breakouts on 15-minute bars do not beat costs. This gate keeps
only breakouts that line up with three classic conditions:

* the market is up on the day (NIFTY 50 above its session open),
* the stock is clearly stronger than the market since the open
  (relative strength >= ``min_relative_strength``),
* the stock is through yesterday's high (a real breakout, not a bounce).

Every input is a completed bar known at the decision; a missing index bar
fails closed.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional

import pandas as pd


@dataclass(frozen=True)
class SelectivePolicy:
    require_market_up: bool = True
    min_relative_strength: float = 0.003
    require_above_prev_high: bool = True


DEFAULT_POLICY = SelectivePolicy()


def _session_return(frame: pd.DataFrame) -> Optional[float]:
    if frame.empty:
        return None
    first_open, last_close = float(frame["open"].iloc[0]), float(frame["close"].iloc[-1])
    if not (math.isfinite(first_open) and math.isfinite(last_close)) or first_open <= 0:
        return None
    return last_close / first_open - 1.0


def selective_gate(stock_today: pd.DataFrame, index_today: pd.DataFrame, prev_day_high: float,
                   policy: SelectivePolicy = DEFAULT_POLICY) -> tuple[bool, Optional[str], dict]:
    """Decide on the signal bar (the last row of ``stock_today``).

    ``index_today`` holds the index's bars for the same session; only bars that
    start at or before the signal bar are used, and the signal bar's own index
    bar must be present.
    """
    signal_ts = stock_today.index[-1]
    index_known = index_today[index_today.index <= signal_ts]
    if index_known.empty or index_known.index[-1] != signal_ts:
        return False, "index_bar_unavailable", {}
    stock_ret, index_ret = _session_return(stock_today), _session_return(index_known)
    if stock_ret is None or index_ret is None:
        return False, "session_return_unavailable", {}
    evidence = {"stock_session_return": round(stock_ret, 6), "index_session_return": round(index_ret, 6),
                "relative_strength": round(stock_ret - index_ret, 6)}
    if policy.require_market_up and index_ret <= 0:
        return False, "market_not_up", evidence
    if stock_ret - index_ret < policy.min_relative_strength:
        return False, "relative_strength_too_low", evidence
    close = float(stock_today["close"].iloc[-1])
    if policy.require_above_prev_high and not (prev_day_high > 0 and close > prev_day_high):
        return False, "below_prev_day_high", {**evidence, "prev_day_high": prev_day_high}
    return True, None, evidence
