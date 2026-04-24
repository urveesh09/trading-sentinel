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
    bankroll size is capital preservation and system validation -
    not return maximisation. All limits scale naturally as bankroll
    grows because they are expressed as percentages.
    """
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    
    STRATEGY_VERSION: str = "1.0.0"
    DB_PATH: str = "/data/cache.db"
    UNIVERSE_PATH: str = "/data/nifty500.csv"
    # TOKEN_INJECTION_SECRET removed — the /token endpoint no longer uses it.
    # The old commented-out endpoint that checked this secret has been removed.
    
        # Core Bankroll (Only used for INITIAL seeding)
    INITIAL_BANKROLL: float = 5000.0
    RISK_PCT: float = 0.10 # 10% Risk per Swing Trade (Hyper-Aggressive)

    # Portfolio Limits
    MAX_OPEN_POSITIONS: int = 6 
    MAX_CAPITAL_PER_TRADE_PCT: float = 0.50 # Increased to allow larger trades
    MAX_SECTOR_EXPOSURE_PCT: float = 0.40
    MAX_CORRELATED_POSITIONS: int = 2
    MAX_TOTAL_RISK_PCT: float = 0.6 # Increased to match high risk

    # Circuit Breakers
    CB_DAILY_LOSS_PCT: float = 0.20 # Allow 20% daily loss (allows 2 full stop-outs)
    CB_MAX_CONSECUTIVE_LOSSES: int = 5 
    CB_MAX_DRAWDOWN_PCT: float = 0.50 # Allow 50% total drawdown
    CB_FLOOR_PCT: float = 0.40

    # Momentum
    MAX_MOMENTUM_POSITIONS:   int   = 5
    MOMENTUM_POOL_PCT:        float = 0.50    
    MOMENTUM_POOL_FREEZE_PCT: float = 0.80    
    MOMENTUM_MIN_CANDLES:     int   = 4
    MOMENTUM_VOL_SURGE_PCT:   float = 1.5     # [Q13] Lowered from 2.0x - see Known Quirks
    MOMENTUM_R_TARGET:        float = 2.0
    MOMENTUM_MAX_COST_RATIO:  float = 0.25    
    MOMENTUM_RISK_PCT:        float = 0.10    # 10% risk per trade in momentum pool



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
