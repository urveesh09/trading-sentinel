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
    TOKEN_INJECTION_SECRET: str
    
    # Core Bankroll (Only used for INITIAL seeding)
    INITIAL_BANKROLL: float = 5000.0
    RISK_PCT: float = 0.01 
    
    # Portfolio Limits
    MAX_OPEN_POSITIONS: int = 4
    MAX_CAPITAL_PER_TRADE_PCT: float = 0.30
    MAX_SECTOR_EXPOSURE_PCT: float = 0.40
    MAX_CORRELATED_POSITIONS: int = 2
    MAX_TOTAL_RISK_PCT: float = 0.04
    
    # Circuit Breakers
    CB_DAILY_LOSS_PCT: float = 0.02
    CB_MAX_CONSECUTIVE_LOSSES: int = 3
    CB_MAX_DRAWDOWN_PCT: float = 0.10
    CB_FLOOR_PCT: float = 0.50

settings = Settings()
