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
    MOMENTUM_ATR_FUEL_BUFFER:          float = 0.85   # [MC5] ATR exhaustion gate: target must fit within remaining_fuel * buffer
    MOMENTUM_VOL_SURGE_LUNCHTIME:      float = 1.75   # [MC3-T] Volume threshold during lunchtime dead zone (11:30–13:15 IST)
    MOMENTUM_LUNCHTIME_START_HOUR:     int   = 11     # [MC3-T] Lunchtime start hour (IST)
    MOMENTUM_LUNCHTIME_START_MIN:      int   = 30     # [MC3-T] Lunchtime start minute (IST)
    MOMENTUM_LUNCHTIME_END_HOUR:       int   = 13     # [MC3-T] Lunchtime end hour (IST)
    MOMENTUM_LUNCHTIME_END_MIN:        int   = 15     # [MC3-T] Lunchtime end minute (IST)
    MOMENTUM_MORPHOLOGY_MIN_SCORE:     float = 0.65   # [MC6] Minimum close_position_score to reject shooting-star candles
    MOMENTUM_R_TARGET_BEAR:            float = 1.5    # [MR2] R target in BEAR_RS_ONLY regime (reduced from 2.0R)



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

    # ============================================================
    # REGIME ENGINE — VIX-Free Volatility Detection
    # Replaces India VIX with ATR Compression + Realized Volatility
    # ============================================================

    # ATR Compression Ratio — replaces VIX as primary volatility driver
    # rv_ratio = ATR_14 / ATR_14_SMA_200
    # rv_ratio <= 0.70 = compressed (calm baseline → score 100)
    # rv_ratio  1.00  = normal                       → score ~50
    # rv_ratio >= 1.20 = expansion (elevated stress) → score ~20
    RV_ATR_COMPRESS_THRESHOLD: float = 0.70   # compressed = calm baseline
    RV_ATR_NORMAL:              float = 0.95   # mid-point of normal range
    RV_ATR_EXPANSION:           float = 1.20   # expansion threshold
    RV_ATR_CB_THRESHOLD:        float = 1.50   # circuit breaker — forces R3
    RV_ATR_SPAN:                float = 0.50   # (RV_ATR_EXPANSION - RV_ATR_COMPRESS_THRESHOLD)
    RV_ATR_SCORE_SCALE:         float = 200.0  # scale factor for linear mapping

    # Realized Volatility — secondary volatility signal (20-day, annualized)
    # rv_12% → score 100; rv_20% → score 60; rv_32% → score 0
    RV_NORMAL_ANNUAL:  float = 0.18   # 18% annualized = normal vol baseline
    RV_CRISIS_ANNUAL:   float = 0.28   # 28% annualized = crisis threshold
    RV_SPAN:           float = 0.16   # (RV_CRISIS_ANNUAL - RV_NORMAL_ANNUAL)
    RV_SCORE_SCALE:    float = 625.0  # scale factor: 100 / 0.16

    # Volatility component weights (must sum to 1.0)
    RV_ATR_WEIGHT: float = 0.60   # ATR compression = primary (60%)
    RV_RV_WEIGHT:  float = 0.40   # realized vol   = secondary (40%)

    # Circuit breaker override
    ATR_CB_THRESHOLD: float = 1.50   # rv_ratio > 1.50 → force REGIME_3_CRISIS

    # Nifty/BankNifty ratio — breadth proxy (replaces weak EMA50-proxy)
    # nb_ratio percentile below 0.30 → weak breadth → ×0.8 penalty
    NB_RATIO_LO_PCT:    float = 0.30   # breadth penalty threshold
    NB_RATIO_WINDOW:    int   = 60     # lookback window for percentile rank

    # VIX parameters — DECOMMISSIONED (kept for backward compat with tests)
    # India VIX unavailable via Kite → replaced by ATR compression + RV
    REGIME_VIX_BOUNDARY_12: float = 18.0
    REGIME_VIX_BOUNDARY_23: float = 25.0
    VIX_CB_THRESHOLD:        float = 40.0   # DEPRECATED — use ATR_CB_THRESHOLD

    # RSI Percentile thresholds (bottom % of 6-month rolling range)
    RSI_PERCENTILE_REGIME1: float = 20.0   # Regime 1: bottom 20%
    RSI_PERCENTILE_REGIME2: float = 15.0   # Regime 2: bottom 15% (tighter)

    # Volume Z-score thresholds
    VOL_ZSCORE_REGIME1: float = 1.5       # Regime 1: 1.5 std devs above mean
    VOL_ZSCORE_REGIME2: float = 2.0       # Regime 2: 2.0 std devs
    VOL_ZSCORE_REGIME3: float = 2.5       # Regime 3: 2.5 std devs

    # Position sizing by regime (% of bankroll per trade)
    RISK_PCT_REGIME1: float = 0.10        # 10% — normal market
    RISK_PCT_REGIME2: float = 0.07        # 7%  — elevated uncertainty
    RISK_PCT_REGIME3: float = 0.05        # 5%  — crisis

    # Stop loss by regime (ATR multipliers)
    STOP_ATR_REGIME1: float = 1.5        # 1.5x ATR
    STOP_ATR_REGIME2: float = 2.0        # 2.0x ATR
    STOP_ATR_REGIME3: float = 2.0        # 2.0x ATR

    # Stop loss by regime (% of close below price — for pct_stop branch)
    STOP_PCT_REGIME1: float = 0.05      # 5% stop
    STOP_PCT_REGIME2: float = 0.05      # 5% stop
    STOP_PCT_REGIME3: float = 0.08      # 8% stop (wider in crisis)

    # Target structure (R-multiples)
    TARGET1_R: float = 1.5                # T1 = 1.5R (all regimes)
    TARGET2_R_REGIME1: float = 3.0        # T2 = 3.0R (Regime 1)
    TARGET2_R_REGIME2: float = 3.0        # T2 = 3.0R (Regime 2)
    TARGET2_R_REGIME3: float = 1.0        # T2 = 1.0R (Regime 3 — no T2, exit at T1)

    # Partial exit at T1 (fraction of shares to exit)
    PARTIAL_EXIT_T1_PCT: float = 0.50    # Exit 50% at T1

    # Chandelier trailing stop
    CHANDELIER_ATR_MULT: float = 3.0      # Highest close since entry - (3 * ATR)

    # Regime transition guards
    REGIME_TRANSITION_SCANS: int = 2      # Score must hold for 2 consecutive scans
    REGIME_HYSTERESIS: float = 5.0       # Must cross threshold by 5 points to transition

    # RS vs Nifty filter (Regime 3 only)
    RS_VS_NIFTY_THRESHOLD: float = 0.05  # 5% outperformance required

    # Drawdown governor (post-crisis recovery)
    DRAWDOWN_RECOVERY_TRADES: int = 5    # Reduced sizing for next 5 trades post-crisis
    DRAWDOWN_RECOVERY_MULT: float = 0.7  # 30% size reduction during recovery

    # Circuit breaker override
    VIX_CB_THRESHOLD: float = 40.0       # If VIX > 40, force Regime 3 regardless of score

    # Kite endpoint — direct (prod/VPS) or via OCI relay (home desktop).
    # Relay is a path-preserving forward proxy; auth + X-Kite-Version headers pass through.
    # Override with KITE_BASE_URL in .env (e.g. http://161.118.160.180:31527).
    KITE_BASE_URL: str = "https://api.kite.trade"

    # === Breadth Enrichment (2026-06-14) ===
    BREADTH_ENRICHMENT_ENABLED:         bool  = False   # Feature flag — OFF by default
    BREADTH_UNIVERSE:                   str   = "NIFTY100"
    BREADTH_CACHE_TTL_SECONDS:          int   = 3600    # Tier 1 stale-while-revalidate window
    BREADTH_FETCH_TIMEOUT_SECONDS:      int   = 90      # Max time for Tier 1 fetch
    BREADTH_NARROW_RALLY_THRESHOLD:     float = 0.40    # R1 gate fires below this
    BREADTH_NARROW_GATE_EXEMPT_RANK:    float = 0.80    # Top quintile bypasses R1 gate
    BREADTH_RANK_BONUS_TOP:             int   = 15      # +15 if rank >= 0.80
    BREADTH_RANK_BONUS_MID:             int   = 7       # +7 if rank >= 0.60
    BREADTH_RANK_PENALTY_BOTTOM:        int   = -10     # -10 if rank < 0.20
    BREADTH_RANK_MULTIPLIER:            float = 1.2     # Top quintile score × this
    BREADTH_DATA_DEGRADED_THRESHOLD:    float = 0.10    # >10% fetch failures = degraded
    BREADTH_TIER1_PARALLELISM:          int   = 4       # Concurrent Kite historical fetches
    BREADTH_DATA_DIR:                   str   = "data"   # Path (relative to python-engine/) to nifty100.json

    # === Universe Expansion (2026-06-15) ===
    UNIVERSE_SIZE:                     int   = 500      # 100 or 500 — current trading universe size
    UNIVERSE_TICKERS_FILE:             str   = "nifty500.json"  # Filename inside BREADTH_DATA_DIR; same format as nifty100.json
    UNIVERSE_MIN_ADV_CRORE:            float = 2.0      # Drop tickers with 20-day median ADV below this (₹ crore)
    UNIVERSE_LIQUIDITY_LOOKBACK_DAYS:  int   = 20       # Lookback window for the median ADV computation


settings = Settings()
