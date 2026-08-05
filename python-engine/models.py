from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import List, Optional, Literal
from datetime import datetime
from annotated_types import Ge
from typing import Annotated
from enum import Enum


class Regime(Enum):
    """Market volatility regime. Computed each scan cycle."""
    REGIME_1_NORMAL = "REGIME_1_NORMAL"
    REGIME_2_ELEVATED = "REGIME_2_ELEVATED"
    REGIME_3_CRISIS = "REGIME_3_CRISIS"
    UNKNOWN = "UNKNOWN"


def round_float_2dp(cls, v: float | None) -> float | None:
    if v is None: return None
    return round(float(v), 2)

def round_float_4dp(cls, v: float | None) -> float | None:
    if v is None: return None
    return round(float(v), 4)

class Signal(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=False)
    
    ticker: str
    exchange: str
    signal_time: datetime
    close: float
    ema_21: float
    ema_50: float
    ema_200: float
    atr_14: float
    volume_ratio: float
    rsi_14: float
    slope_5: float
    stop_loss: float
    target_1: float
    target_2: float
    trailing_stop: float
    shares: int = Field(ge=1)
    capital_deployed: float
    capital_at_risk: float
    net_ev: float
    score: int
    sector: str
    portfolio_slot: Optional[int] = None
    stale_data: bool = False
    strategy_version: str
    strategy_type: Optional[Literal["SWING", "MOMENTUM"]] = "SWING"
    regime: Optional[Regime] = None        # Market regime at signal generation
    rsi_percentile: Optional[float] = None  # RSI percentile (0-100)
    volume_zscore: Optional[float] = None    # Volume z-score
    rs_vs_nifty: Optional[float] = None     # Relative strength vs Nifty 50 (decimal)
    regime_score: Optional[float] = None    # Continuous regime score (0-100)
    rs_score: Optional[float] = None
    volume_consistent: Optional[bool] = None
    cost_ratio: Optional[float] = None   # for momentum signals
    
    
    _round_2dp = field_validator(
        "close", "ema_21", "ema_50", "ema_200", "atr_14", "volume_ratio",
        "stop_loss", "target_1", "target_2", "trailing_stop",
        "capital_deployed", "capital_at_risk", "net_ev",
        "rsi_percentile", "volume_zscore", "rs_vs_nifty", "regime_score", mode="after"
    )(round_float_2dp)
    
    _round_4dp = field_validator("slope_5", mode="after")(round_float_4dp)

class MomentumSignal(BaseModel):
    """Intraday momentum signal. Subset of Signal fields."""
    ticker:            str
    exchange:          str = "NSE"
    signal_time:       datetime
    strategy_type:     Literal["MOMENTUM"] = "MOMENTUM"
    close:             float
    vwap:              float
    prev_day_high:     float
    stop_loss:         float
    target_1:          float
    trailing_stop:     float
    # Daily ATR at entry -- what the Chandelier trail sizes off. None when the
    # daily history was too short to compute one; never 0.0 (a 0 ATR collapses
    # the trail onto the entry price).
    atr_at_entry:      Optional[float] = None
    shares:            int = Field(ge=1)
    capital_deployed:  float
    capital_at_risk:   float
    net_ev:            float
    cost_ratio:        float
    volume_ratio:      float
    product_type:      Literal["MIS", "CNC"]
    sector:            str = "UNKNOWN"
    portfolio_slot:    Optional[int] = None
    stale_data:        bool = False
    strategy_version:  str
    regime: Optional[Regime] = None
    regime_score: Optional[float] = None

    _round_2dp = field_validator(
        "close", "vwap", "prev_day_high", "stop_loss", "target_1",
        "trailing_stop", "capital_deployed", "capital_at_risk",
        "net_ev", "cost_ratio", "volume_ratio", mode="after"
    )(round_float_2dp)

class PortfolioResponse(BaseModel):
    run_time: datetime
    market_regime: Literal["BULL", "CAUTION", "BEAR_RS_ONLY", "UNKNOWN"]
    backtest_gate: Literal["PASS", "FAIL", "NOT_RUN"]
    trading_halted: bool
    halt_reasons: List[str]
    stale_data: bool
    total_capital_at_risk: float
    total_capital_deployed: float
    bankroll_utilization_pct: float
    open_positions_count: int
    remaining_slots: int
    signals: List[Signal]
    momentum_signals: List[MomentumSignal] = []
    momentum_pool:    float = 0.0
    regime: Regime = Regime.UNKNOWN
    regime_score: float = 100.0

    _round_2dp = field_validator(
        "total_capital_at_risk", "total_capital_deployed", 
        "bankroll_utilization_pct", mode="after"
    )(round_float_2dp)

class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "halted"]
    last_run_utc: Optional[datetime]
    next_run_utc: datetime
    tickers_scanned: int
    signals_found: int
    trading_halted: bool
    backtest_gate: str
    engine_version: str
    cache_hit_rate: float
    uptime_seconds: int

    _round_2dp = field_validator("cache_hit_rate", mode="after")(round_float_2dp)

class OpenPosition(BaseModel):
    ticker: str
    exchange: str
    entry_date: datetime
    entry_price: float
    shares: int
    stop_loss_initial: float
    trailing_stop_current: float
    target_1: float
    target_2: float
    # None when the entry could not compute an ATR. Deliberately nullable rather
    # than 0.0: a 0 ATR collapses the Chandelier trail onto the entry price and
    # force-closes the position there (see position_tracker.update_daily_positions).
    atr_14_at_entry: Optional[float] = None
    highest_close_since_entry: float
    status: Literal["OPEN", "CLOSED_T1", "CLOSED_T2", "STOPPED_OUT", "CLOSED_TIME", "CLOSED_MANUAL"]
    # [PENNY-EDGE 2026-07-01] Added EDGE_PAPER and EDGE_LIVE so the
    # new adaptive signal orchestrator's positions are valid in
    # the OpenPosition response model. Without these the GET /positions
    # endpoint raises a ResponseValidationError whenever any EDGE
    # leg has an open position (the bug that broke EOD digest today).
    source: Literal["SYSTEM", "MANUAL", "MOMENTUM", "EDGE_PAPER", "EDGE_LIVE"]
    exit_price: Optional[float] = None
    exit_date: Optional[datetime] = None
    realised_pnl: Optional[float] = None
    r_multiple: Optional[float] = None
    # [TRAILING-EXITS 2026-06-16] Regime at entry -- drives the regime-aware
    # Chandelier trail (3.5x R1, 3.0x R2, 2.5x R3). NULL = legacy 3.0x trail.
    # [PENNY-EDGE 2026-07-01] Widened to Optional[str] so the new orchestrator's
    # MR/MO/BOTH codes plus any legacy CN/MIS source can write without
    # raising validation errors. The trailing-exit logic only consults
    # the three REGIME_* literals at the call site (legacy penny positions),
    # so widening the type here is safe.
    regime_at_entry: Optional[str] = None

    _round_2dp = field_validator(
        "entry_price", "stop_loss_initial", "trailing_stop_current", "target_1", 
        "target_2", "atr_14_at_entry", "highest_close_since_entry", 
        "exit_price", "realised_pnl", "r_multiple", mode="after"
    )(round_float_2dp)

class PerformanceReport(BaseModel):
    as_of: datetime
    total_trades_taken: int
    open_positions_count: int
    closed_trades_count: int
    win_count: int
    loss_count: int
    win_rate: float
    avg_r_multiple: float
    avg_winner_r: float
    avg_loser_r: float
    profit_factor: float
    total_realised_pnl: float
    current_bankroll: float
    max_drawdown_pct: float
    current_drawdown_pct: float
    consecutive_losses: int
    max_consecutive_losses: int
    best_trade_r: float
    worst_trade_r: float
    avg_hold_days: float

    _round_2dp = field_validator(
        "win_rate", "avg_r_multiple", "avg_winner_r", "avg_loser_r", 
        "profit_factor", "total_realised_pnl", "current_bankroll", 
        "max_drawdown_pct", "current_drawdown_pct", "best_trade_r", 
        "worst_trade_r", "avg_hold_days", mode="after"
    )(round_float_2dp)

class LedgerRow(BaseModel):
    id: int
    timestamp: datetime
    event_type: Literal["INITIAL", "TRADE_CLOSED", "MANUAL_DEPOSIT", "MANUAL_WITHDRAWAL", "MANUAL_ADJUSTMENT"]
    ticker: Optional[str]
    pnl: float
    bankroll_before: float
    bankroll_after: float
    notes: Optional[str]

    _round_2dp = field_validator("pnl", "bankroll_before", "bankroll_after", mode="after")(round_float_2dp)

class ManualPositionRequest(BaseModel):
    """[AUDIT-FIX-1.4 2026-06-25] Pydantic model for /positions/manual.

    Before this fix, the endpoint read each field via `data["..."]` (manual
    dict access). A missing required field raised KeyError, which FastAPI
    turned into HTTP 500 instead of HTTP 422. Now Pydantic validates
    the body up front and FastAPI returns 422 with field-level errors.

    Fields:
      Required: ticker, entry_price, shares
      Optional: exchange (default NSE), source (default SYSTEM),
                product_type (default CNC), regime_at_entry,
                stop_loss / target_1 / target_2 (derived from
                entry_price if omitted).
    """
    ticker: str = Field(min_length=1, max_length=32)
    exchange: str = "NSE"
    entry_price: float = Field(gt=0)
    shares: int = Field(gt=0)
    source: str = "SYSTEM"
    product_type: str = "CNC"
    regime_at_entry: Optional[str] = None
    stop_loss: Optional[float] = Field(default=None, gt=0)
    target_1: Optional[float] = Field(default=None, gt=0)
    target_2: Optional[float] = Field(default=None, gt=0)
    # Broker-side SL-M protecting an MIS position (Zerodha GTT is CNC-only). The
    # intraday monitor must cancel this before it takes a target or trail exit,
    # otherwise the SL-M is still resting and would sell a second time.
    sl_order_id: Optional[str] = None
    # ATR at entry, used by the Chandelier trail. None = unknown; it must NOT be
    # coerced to 0.0, which collapses the trail onto the entry price.
    atr_14_at_entry: Optional[float] = Field(default=None, gt=0)
    # [THESIS-EXIT 2026-08-04] VWAP the signal broke out from. The exit ladder
    # tests the trade against this instead of cutting on the clock -- a trade
    # still holding above it has not failed, it just has not paid yet. None on
    # callers that do not send it; the exit logic falls back to the R test.
    vwap_at_entry: Optional[float] = Field(default=None, gt=0)

class BankrollAdjustment(BaseModel):
    amount: float
    event_type: Literal["MANUAL_DEPOSIT", "MANUAL_WITHDRAWAL"]
    notes: str
