from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import List, Optional, Literal
from datetime import datetime

def round_float_2dp(cls, v: float) -> float:
    return round(float(v), 2)

def round_float_4dp(cls, v: float) -> float:
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
    shares: int
    capital_deployed: float
    capital_at_risk: float
    net_ev: float
    score: int
    sector: str
    portfolio_slot: Optional[int] = None
    stale_data: bool = False
    strategy_version: str
    strategy_type: Optional[Literal["SWING", "MOMENTUM"]] = "SWING"
    rs_score: Optional[float] = None
    volume_consistent: Optional[bool] = None
    cost_ratio: Optional[float] = None   # for momentum signals
    
    
    _round_2dp = field_validator(
        "close", "ema_21", "ema_50", "ema_200", "atr_14", "volume_ratio", 
        "stop_loss", "target_1", "target_2", "trailing_stop", 
        "capital_deployed", "capital_at_risk", "net_ev", mode="after"
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
    shares:            int
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
    atr_14_at_entry: float
    highest_close_since_entry: float
    status: Literal["OPEN", "CLOSED_T1", "CLOSED_T2", "STOPPED_OUT", "CLOSED_TIME", "CLOSED_MANUAL"]
    source: Literal["SYSTEM", "MANUAL", "MOMENTUM"]
    exit_price: Optional[float] = None
    exit_date: Optional[datetime] = None
    realised_pnl: Optional[float] = None
    r_multiple: Optional[float] = None

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
    ticker: str
    exchange: str = "NSE"
    entry_price: float
    shares: int
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    notes: Optional[str] = None

class BankrollAdjustment(BaseModel):
    amount: float
    event_type: Literal["MANUAL_DEPOSIT", "MANUAL_WITHDRAWAL"]
    notes: str
