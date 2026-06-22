"""
[PENNY-MODELS 2026-06-21] Pydantic models for the penny-stock subsystem.

Owns:
  - PennySignal: signal record for one accepted penny trade
  - PennyRegime: per-stock market regime (PR1_CALM, PR2_ELEVATED, PR3_HOT)
  - PennyLeg: product type literal (CNC, MIS)

Hard architectural rule (enforced by tests/test_penny_isolation.py):
  this module MUST NOT import from engine, regime, risk_engine, portfolio,
  evaluate_signal, or evaluate_momentum_signal.

Allowed shared imports: kite_client, models (base only), config,
position_tracker, performance, analytics, stdlib, pydantic.
"""
from enum import Enum
from typing import Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, field_validator


class PennyRegime(Enum):
    """Per-stock volatility regime. Computed each scan cycle."""
    PR1_CALM = "PR1_CALM"
    PR2_ELEVATED = "PR2_ELEVATED"
    PR3_HOT = "PR3_HOT"
    UNKNOWN = "UNKNOWN"


class PennyLeg(str, Enum):
    """Product type for a penny position."""
    CNC = "CNC"
    MIS = "MIS"


def _round_2dp(cls, v):
    if v is None:
        return None
    return round(float(v), 2)


class PennySignal(BaseModel):
    """
    Signal record for one accepted penny trade.
    Mirrors the structure of MomentumSignal / Signal but is owned by the
    penny subsystem.
    """
    model_config = ConfigDict(coerce_numbers_to_str=False, use_enum_values=False)

    scan_id:        str
    ticker:         str
    exchange:       Literal["NSE"] = "NSE"
    signal_time:    datetime
    leg:            PennyLeg
    regime:         PennyRegime = PennyRegime.UNKNOWN

    # Price levels (entry / exit)
    close:          float
    stop_loss:      float
    target_1:       float
    target_2:       float
    trailing_stop:  float = 0.0

    # Sizing + risk
    shares:         int
    capital_deployed: float
    capital_at_risk:  float
    net_ev:           float

    # Order metadata
    entry_order_type: Literal["LIMIT", "MARKET"] = "LIMIT"
    sl_order_type:    Literal["SL-M"] = "SL-M"

    # Bookkeeping
    strategy_version:  str = "1.0.0"
    reject_reason:     Optional[str] = None  # populated for rejected signals too

    # 2dp rounding on numeric fields (mirrors Signal pattern)
    _round_2dp = field_validator(
        "close", "stop_loss", "target_1", "target_2", "trailing_stop",
        "capital_deployed", "capital_at_risk", "net_ev", mode="after"
    )(_round_2dp)
