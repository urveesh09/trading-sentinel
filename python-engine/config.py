from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import ClassVar

class Settings(BaseSettings):
    """
    POSITION SIZING PHILOSOPHY:
    At ₹5,000 bankroll:
      risk_per_trade (1%)       = ₹50
      max_positions             = 4
      max_total_risk (4%)       = ₹200  across all open trades
      max_per_trade capital     = ₹1,500 (30%)
      daily_loss_halt_threshold = ₹100  (2%)
      drawdown_halt_threshold   = ₹500  (10%)

    This is deliberately conservative. The primary goal at this
    bankroll size is capital preservation and system validation —
    not return maximisation. All limits scale naturally as bankroll
    grows because they are expressed as percentages.
    """
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    
    STRATEGY_VERSION: str = "1.0.0"
    DB_PATH: str = "/data/cache.db"
    UNIVERSE_PATH: str = "/data/nifty500.csv"
    TOKEN_INJECTION_SECRET: str = "default_secret"
    
        # Core Bankroll (Only used for INITIAL seeding)
    INITIAL_BANKROLL: float = 5000.0
    RISK_PCT: float = 0.04 # 4% Risk per Swing Trade (Optimized Aggression)
    
    # Portfolio Limits
    MAX_OPEN_POSITIONS: int = 6 
    MAX_CAPITAL_PER_TRADE_PCT: float = 0.50 # Increased to allow larger trades
    MAX_SECTOR_EXPOSURE_PCT: float = 0.40
    MAX_CORRELATED_POSITIONS: int = 2
    MAX_TOTAL_RISK_PCT: float = 0.4
    
    # Circuit Breakers
    CB_DAILY_LOSS_PCT: float = 0.10 # Allow 10% daily loss (prevents instant halt from 1 loss)
    CB_MAX_CONSECUTIVE_LOSSES: int = 5 # Allow 5 losers in a row
    CB_MAX_DRAWDOWN_PCT: float = 0.25 # Allow 25% total drawdown
    CB_FLOOR_PCT: float = 0.50

    # Momentum
    MAX_MOMENTUM_POSITIONS:   int   = 5
    MOMENTUM_POOL_PCT:        float = 0.50    # 50% of bankroll for intraday
    MOMENTUM_POOL_FREEZE_PCT: float = 0.80    # freeze if bankroll < 80% of initial
    MOMENTUM_MIN_CANDLES:     int   = 4
    MOMENTUM_VOL_SURGE_PCT:   float = 2.0     # 200% of 10-candle avg
    MOMENTUM_R_TARGET:        float = 2.0
    MOMENTUM_MAX_COST_RATIO:  float = 0.25    # reject if costs > 25% of expected profit
    MOMENTUM_RISK_PCT:        float = 0.04    # 4% risk per trade in momentum pool


    MOMENTUM_FIRST_SCAN_HOUR: int   = 10
    MOMENTUM_FIRST_SCAN_MIN:  int   = 15
    CONTAINER_A_URL:          str   = "http://node-gateway:3000"
    INTERNAL_API_SECRET:      str   = ""      # must be set in .env

    # RS Module
    RS_PERIODS:               int   = 20
    RS_MIN_THRESHOLD:         float = 5.0
    RS_MIN_DAYS_ABOVE_AVG:    int   = 3
    RS_LOOKBACK_DAYS:         int   = 5

    # Cost model
    ZERODHA_BROKERAGE_PCT:    float = 0.0003  # 0.03%
    ZERODHA_BROKERAGE_MAX:    float = 20.0    # ₹20 cap
    ZERODHA_STT_CNC:          float = 0.001   # 0.1% sell side
    ZERODHA_STT_MIS:          float = 0.00025 # 0.025% sell side
    ZERODHA_EXCHANGE_PCT:     float = 0.0000345
    ZERODHA_STAMP_DUTY_PCT:   float = 0.00015
    ZERODHA_SEBI_PCT:         float = 0.000001
    ZERODHA_GST_PCT:          float = 0.18


settings = Settings()
