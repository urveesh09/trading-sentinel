from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import ClassVar

class Settings(BaseSettings):
    """
    POSITION SIZING PHILOSOPHY:
    At Rs5,000 bankroll:
      risk_per_trade (1%)       = Rs50
      max_positions             = 4
      max_total_risk (4%)       = Rs200  across all open trades
      max_per_trade capital     = Rs1,500 (30%)
      daily_loss_halt_threshold = Rs100  (2%)
      drawdown_halt_threshold   = Rs500  (10%)

    This is deliberately conservative. The primary goal at this
    bankroll size is capital preservation and system validation -
    not return maximisation. All limits scale naturally as bankroll
    grows because they are expressed as percentages.
    """
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    
    STRATEGY_VERSION: str = "1.0.0"
    DB_PATH: str = "/data/cache.db"
    UNIVERSE_PATH: str = "/data/nifty500.csv"
    # [PENNY 2026-06-24] Penny universe JSON path (the static-rank JSON
    # loaded by PennyUniverse at startup, refreshed daily by
    # penny_universe.refresh_from_kite). Single source of truth so the
    # pre-market digest module reads the same file the scanner reads.
    PENNY_UNIVERSE_JSON_PATH: str = "/data/penny_static.json"
    # TOKEN_INJECTION_SECRET removed -- the /token endpoint no longer uses it.
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
    # [MOMENTUM-REGIME 2026-06-16] Legacy 10% risk per trade.
    # Kept for backward compat -- new code should use MOMENTUM_RISK_PCT_R{1,2,3}.
    # R1 default (0.07) is MORE conservative than the legacy 0.10 -- a deliberate
    # tightening since we now have regime gating to back it up.
    MOMENTUM_RISK_PCT:        float = 0.10    # Legacy 10% -- pre-regime value
    MOMENTUM_ATR_FUEL_BUFFER:          float = 0.85   # [MC5] ATR exhaustion gate: target must fit within remaining_fuel * buffer
    MOMENTUM_VOL_SURGE_LUNCHTIME:      float = 1.75   # [MC3-T] Volume threshold during lunchtime dead zone (11:30-13:15 IST)
    MOMENTUM_LUNCHTIME_START_HOUR:     int   = 11     # [MC3-T] Lunchtime start hour (IST)
    MOMENTUM_LUNCHTIME_START_MIN:      int   = 30     # [MC3-T] Lunchtime start minute (IST)
    MOMENTUM_LUNCHTIME_END_HOUR:       int   = 13     # [MC3-T] Lunchtime end hour (IST)
    MOMENTUM_LUNCHTIME_END_MIN:        int   = 15     # [MC3-T] Lunchtime end minute (IST)
    MOMENTUM_MORPHOLOGY_MIN_SCORE:     float = 0.65   # [MC6] Minimum close_position_score to reject shooting-star candles
    MOMENTUM_R_TARGET_BEAR:            float = 1.5    # [MR2] R target in BEAR_RS_ONLY regime (reduced from 2.0R)

    # [MOMENTUM-REGIME 2026-06-16] Regime-aware momentum settings.
    # Replaces the single 'market_regime' string dispatch (BULL/BEAR_RS_ONLY)
    # with the 3-regime system already used for swing. Slight-risk tilt
    # toward activity: R1/R2 sized aggressively, R3 has the *option* to trade
    # (default risk=0% is a guardrail -- flip to 0.05+ in .env to allow R3 entries).
    #
    # [MOMENTUM-AGGRESSIVE 2026-06-16] User feedback: momentum was 1-2 sigs/day,
    # wanted more P&L. Restored pre-regime sizes (10% / 7%) for R1/R2.
    # MOMENTUM_BLOCK_R3_ENTRIES default flipped to False (R3 *can* trade when
    # R3 risk > 0), defense-in-depth via MOMENTUM_RISK_PCT_R3=0% remains.
    MOMENTUM_BLOCK_R3_ENTRIES:  bool  = False   # OFF: don't hard-block R3; guardrail is RISK_PCT_R3=0.00
    MOMENTUM_RISK_PCT_R1:       float = 0.10    # 10% of momentum pool in R1 (calm, aggressive)
    MOMENTUM_RISK_PCT_R2:       float = 0.07    # 7% in R2 (elevated) -- smaller position
    MOMENTUM_RISK_PCT_R3:       float = 0.00    # 0% in R3 default (defense-in-depth: raise in .env to enable)
    MOMENTUM_R_TARGET_R1:       float = 2.0     # 2.0R target in R1 (let winners run)
    MOMENTUM_R_TARGET_R2:       float = 1.5     # 1.5R target in R2 (faster take-profit)

    # [MOMENTUM-EOD 2026-06-16] Auto-square-off at 15:15 IST is on by default
    # (MIS = intraday product; broker auto-squares anyway). Flip to True in .env
    # to let momentum winners run past 3:15 IST. Only effective when the engine
    # has switched positions to CNC (see evaluate_momentum_signal [MR3]).
    MOMENTUM_ALLOW_OVERNIGHT:   bool  = False   # False = 15:15 auto-square stays; True = hold to trailing-stop only
    MOMENTUM_R3_MAX_POSITIONS:  int   = 1       # Soft cap for R3 entries (replaces hard block)

    # [MOMENTUM-ENTRY-V2 2026-06-16] Optional additive entry filters.
    # All default OFF -- opt-in via .env. Each filter is independently gated by
    # its own MOMENTUM_USE_* flag. Skip first 15-min + last 30-min chop by default
    # (MOMENTUM_USE_TIME_GATE=True is the recommended safe default).
    # References: 4-variant ORB study (dailybulls.in 2026), Nifty 8yr backtest
    # (intradaylab.com 2026), 190k-trade ORB study (orbsetups.com 2026).
    MOMENTUM_USE_RVOL:          bool  = False   # [MC7] Relative-volume vs 20-bar 15-min avg
    MOMENTUM_RVOL_MIN_RATIO:    float = 1.5     # [MC7] RVOL threshold (last bar vol / avg)
    MOMENTUM_RVOL_LOOKBACK:     int   = 20      # [MC7] Lookback bars (15-min each)
    MOMENTUM_USE_TIME_GATE:     bool  = True    # [MC0] Skip 9:15-9:30 + 15:00-15:30
    MOMENTUM_ENTRY_START_MIN:   int   = 45      # [MC0] Minutes from 9:15 IST when entries allowed (45 = 10:00)
    MOMENTUM_ENTRY_END_MIN:     int   = 840     # [MC0] Minutes from 9:15 IST after which entries blocked (840 = 14:45)
    MOMENTUM_USE_RSI_TRIM:      bool  = False   # [MC8] Partial trim 50% at RSI(7)>=70 on 15-min
    MOMENTUM_RSI_TRIM_LENGTH:   int   = 7       # [MC8] RSI length (7 is the orbsetups sweet spot)
    MOMENTUM_RSI_TRIM_THRESHOLD: float = 70.0   # [MC8] RSI >= this -> partial trim fires

    # [MOMENTUM-LOG 2026-06-16] Append-only signal log to /data/momentum_signals.csv
    # and SQLite table `momentum_signals`. Both are opt-in so the operator can
    # disable on disk-constrained systems. The CSV is the easy one to grep /
    # backtest on; the SQLite table is for future API-driven backtest queries.
    MOMENTUM_LOG_ENABLED:       bool  = True    # Master switch -- set False to disable entirely
    MOMENTUM_LOG_CSV_PATH:      str   = "/data/momentum_signals.csv"
    MOMENTUM_LOG_DB_TABLE:      str   = "momentum_signals"

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
    ZERODHA_BROKERAGE_MAX:    float = 20.0    # Rs20 cap
    ZERODHA_STT_CNC:          float = 0.001   # 0.1% sell side

    # --- Telegram (for penny hourly report delivery) ---
    # 2026-06-23: penny hourly report now tries Telegram first, falls back
    # to PENNY_HOURLY_REPORT_WEBHOOK. Both creds are read from env.
    TELEGRAM_BOT_TOKEN:       str   = ""       # @BotFather token
    TELEGRAM_CHAT_ID:         str   = ""       # numeric chat ID (user/group)

    # --- Penny subsystem brokerage/fees (mirrored from Nifty, scoped to penny) ---
    # 2026-06-22 deviation: penny code now does its own cost accounting per
    # the isolation rule (no import from engine.calc_zerodha_costs).
    PENNY_STT_MIS:             float = 0.00025   # 0.025% sell side (intraday)
    PENNY_STT_CNC:             float = 0.001     # 0.1% sell side (delivery)
    PENNY_BROKERAGE_PCT:       float = 0.0003    # 0.03% per side
    PENNY_BROKERAGE_MAX:       float = 20.0      # Rs 20 cap per order
    PENNY_EXCHANGE_PCT:        float = 0.0000345  # 0.00345% NSE both sides
    PENNY_STAMP_DUTY_PCT:      float = 0.00015   # 0.015% buy side
    PENNY_SEBI_PCT:            float = 0.000001   # Rs 10/cr, both sides
    PENNY_GST_PCT:             float = 0.18       # 18% on brokerage+exchange
    # [PENNY-TEST 2026-06-24] When True, calc_penny_costs() returns 0.0 so
    # P&L math is isolated from Rs 2,500 brokerage erosion. Use only in
    # test/paper mode to measure system proactiveness (how many trades it
    # fires, what the gross edge would be). Live trading MUST keep this False
    # -- a zeroed-cost live run understates real P&L and breaks the ledger.
    PENNY_BROKERAGE_BYPASS:    bool  = False
    ZERODHA_STT_MIS:          float = 0.00025 # 0.025% sell side (intraday)
    ZERODHA_EXCHANGE_PCT:     float = 0.0000345
    ZERODHA_STAMP_DUTY_PCT:   float = 0.00015
    ZERODHA_SEBI_PCT:         float = 0.000001
    ZERODHA_GST_PCT:          float = 0.18

    # ============================================================
    # PENNY STOCK SUBSYSTEM (2026-06-21, spec docs/superpowers/specs/2026-06-21-penny-stock-expansion-design.md)
    # ============================================================
    # All settings default OFF / safe. Live trade is opt-in via PENNY_LIVE_TRADING=true.

    # Universe
    PENNY_PRICE_MIN:               float = 1.0
    PENNY_PRICE_MAX:               float = 55.0
    PENNY_UNIVERSE_SIZE:           int   = 100
    PENNY_MIN_20D_TV:              float = 500_000.0   # Rs 5 lakh, 20-day median traded value floor
    PENNY_MAX_PROMOTER_HOLD:       float = 0.75        # see MIN_PROMOTER_HOLD below
    PENNY_MIN_PROMOTER_HOLD:       float = 0.25        # strictly > 25% AND strictly < 75%
    PENNY_MAX_PB_RATIO:            float = 2.0         # Price-to-Book <= 2.0 (loose asset floor)
    PENNY_REFRESH_HOUR:            int   = 8

    # Connors strategy
    PENNY_CONNORS_RSI2_BUY:        float = 10.0
    PENNY_CONNORS_RSI2_SELL:       float = 65.0
    PENNY_CONNORS_T1_PCT:          float = 0.03
    PENNY_CONNORS_T2_PCT:          float = 0.06
    PENNY_CONNORS_STOP_PCT:        float = 0.03
    PENNY_CONNORS_MAX_HOLD_DAYS:   int   = 3
    # [TIER2-CONNORS-REFINEMENT 2026-06-25] Cumulative-RSI and absolute
    # floor gates (Q1+A2 from the brainstorm). Defaults preserve pre-fix
    # behaviour so we can A/B test by raising the cumulative-RSI days
    # later without redeploying code.
    #   RSI2_FLOOR: absolute minimum RSI(2) to enter. 1.0 disables
    #               (current behaviour: any RSI(2) < threshold works).
    #               Recommended value once validated: 5.0.
    #   CUMULATIVE_RSI_DAYS: minimum consecutive daily bars with
    #               RSI(2) < threshold before entry. 1 disables
    #               (current behaviour: any single-day trigger).
    #               Connors' original refinement uses 2; 1 means
    #               "the current day is enough".
    PENNY_CONNORS_RSI2_FLOOR:           float = 1.0
    PENNY_CONNORS_CUMULATIVE_RSI_DAYS:  int   = 1
    # Time-of-day gate: reject CNC signals after this many minutes past
    # market open (09:15 IST). Default 195 min = 12:30 IST. The Connors
    # mean-reversion signal fires best in the morning; signals after
    # lunch often mean-revert against the operator.
    PENNY_CONNORS_LAST_ENTRY_MIN:       int   = 195
    PENNY_CONNORS_TRAIL_ATR_MULT:  float = 2.0         # 2x ATR_1min trail after T1

    # Breakout strategy
    # [PENNY-AGGRESSIVE 2026-06-24] Relaxed from 3.0 -> 1.8 to allow more
    # entries. Web research (ORB / opening-range-breakout literature) shows
    # the 5-min ORB sweet spot is 1.5-2.0x median volume for momentum setups.
    # 3.0x was effectively blocking any setup that wasn't already in a
    # confirmed trend -- too tight for a penny subsystem that needs to
    # fire several trades per day to validate the edge.
    PENNY_BREAKOUT_VOL_MULT:       float = 1.8
    PENNY_BREAKOUT_TARGET_R:       float = 2.0
    PENNY_BREAKOUT_TIME_START:     int   = 10*60 + 30  # 10:30 IST in minutes
    PENNY_BREAKOUT_TIME_END:       int   = 14*60 + 30  # 14:30 IST in minutes
    PENNY_BREAKOUT_TIME_EXIT:      int   = 15*60       # 15:00 IST
    # [TIER3-DAILY-ATTRIBUTION 2026-06-25] 15:30 IST = 30 min after the
    # 15:00 force-close fires. Gives time for the broker to confirm
    # all MIS positions are closed and the ledger to be updated.
    PENNY_DAILY_ATTRIBUTION_TIME: int = 15*60 + 30    # 15:30 IST
    PENNY_DAILY_ATTRIBUTION_HOUR: int = 15
    PENNY_DAILY_ATTRIBUTION_MIN:  int = 30
    # [TIER2-BREAKOUT-REFINEMENT 2026-06-25] VWAP-anchored breakout and
    # adaptive threshold. Both default to False to preserve current
    # behaviour (close > day_high + 0.3%); enable via config after A/B
    # validation.
    #   USE_VWAP: replace day_high anchor with VWAP. The breakout is then
    #             "close > VWAP + 0.3%" instead of "close > day_high + 0.3%".
    #             Volume-confirmed breakout is statistically more robust.
    #   ADAPTIVE_THRESHOLD: scale the 0.3% buffer by current_volatility /
    #             typical_volatility (ATR(20) / median_ATR(20,60min)). Calm
    #             ticker -> tighter threshold; volatile ticker -> wider.
    #             Per de Prado, Advances in Financial ML ch. 16.
    PENNY_BREAKOUT_USE_VWAP:            bool  = False
    PENNY_BREAKOUT_ADAPTIVE_THRESHOLD:  bool  = False
    # Buffer pct applied as breakout margin (was hardcoded 0.3% in the
    # engine). Made a setting so adaptive mode can override it.
    PENNY_BREAKOUT_BUFFER_PCT:           float = 0.003
    # [TIER2-SECTOR-FILTER 2026-06-25] Sector-relative strength gate.
    # The filter is ALWAYS opt-in via the CSV; missing CSV == filter off.
    #   USE_SECTOR_FILTER: master toggle (default True so the CSV path is
    #     exercised; effective state is determined by CSV presence).
    #   TOP_LOSERS_PCT: how deep into "losers" we look. With 10% threshold,
    #     only sectors in the bottom decile intraday get blocked.
    #   ETF_CHANGE_THRESHOLD_PCT: minimum negative move to consider
    #     "weak" (default -1.5%). Sectors between -1.5% and severe are
    #     allowed through (preserves proactiveness).
    #   SECTORS_CSV_PATH: location of (symbol, sector) operator-curated
    #     CSV. Empty or missing file -> filter is effectively OFF.
    PENNY_USE_SECTOR_FILTER:               bool   = True
    PENNY_SECTOR_TOP_LOSERS_PCT:           float = 0.10
    PENNY_SECTOR_ETF_CHANGE_THRESHOLD_PCT: float = -0.015
    PENNY_SECTORS_CSV_PATH:                str   = "python-engine/data/penny_sectors.csv"
    # [TIER3-INTERACTIVE-COMMANDS 2026-06-25] Path to the runtime
    # override JSON. Telegram /penny skip and /penny unskip write here;
    # penny_risk.is_disabled() reads here on every call. Tests override
    # this to a tmp path.
    PENNY_DISABLE_OVERRIDES_PATH:          str   = "python-engine/data/penny_disable_overrides.json"
    # [PENNY-TIME-STOP 2026-06-24] Soft time-stop: if entry fires but the
    # position is NOT in profit within PENNY_TIME_STOP_MIN minutes, cut at
    # market (modular exit path; spec §7.2 exit chain). Default 30 min --
    # the consensus from intraday-trading literature for breakout trades
    # in less-volatile setups. 0 disables.
    PENNY_TIME_STOP_MIN:           int   = 30
    # [PENNY-PREMARKET 2026-06-24] Pre-market universe Telegram digest
    # sent at HH:MM IST every weekday. Defaults to 07:50 (10 min before
    # penny_universe_refresh at PENNY_REFRESH_HOUR=8). 0 disables.
    PENNY_PREMARKET_REPORT_HOUR:   int   = 7
    PENNY_PREMARKET_REPORT_MIN:    int   = 50
    PENNY_PREMARKET_TOP_N:         int   = 10          # how many tickers to list in the body
    PENNY_MIS_SMART_EOD_TIME:      int   = 14*60 + 30  # 14:30 IST smart-EOD check
    PENNY_MIS_SMART_EOD_WITHIN_R:  float = 0.5
    PENNY_MIS_SMART_EOD_LOSS_MIN:  int   = 30

    # Risk + bankroll
    PENNY_LIVE_BANKROLL:           float = 2000.0
    PENNY_PAPER_BANKROLL:          float = 500.0
    PENNY_RISK_PCT_PR1:            float = 0.05
    PENNY_RISK_PCT_PR2:            float = 0.025
    PENNY_RISK_PCT_PR3:            float = 0.0
    PENNY_DAILY_KILL_SWITCH_PCT:   float = 0.20
    PENNY_PER_STOCK_CAP:           float = 500.0
    PENNY_MAX_POSITIONS_TOTAL:     int   = 5
    PENNY_MAX_POSITIONS_CNC:       int   = 2
    PENNY_MAX_POSITIONS_MIS:       int   = 3
    PENNY_CIRCUIT_SKIP_DISTANCE:   float = 0.005      # 0.5% of band
    PENNY_CIRCUIT_FROM_HIGH_PCT:   float = 0.03       # 3% from day high
    # [AUDIT-FIX-2.5 2026-06-25] Penny heat-map "near SL" warn threshold.
    # When a position's current P&L % is within this distance (above)
    # of its stop_loss, the heatmap surfaces a WARN line. Previously
    # hardcoded to 1.0% in penny_heatmap.build_heatmap (operator-mandated
    # audit point). For a Rs 2,500 paper bankroll 1% may be too noisy;
    # for a Rs 50k+ account 1% may be too lax. Operator tunes here.
    PENNY_HEATMAP_WARN_PCT:        float = 0.01       # 1% from SL

    # Cadence + safety
    PENNY_SCAN_INTERVAL_SEC:       int   = 30
    PENNY_LIVE_TRADING:            bool  = True       # Uru 2026-06-22: live opt-in for testing budget (Rs 2,500)
    PENNY_DISABLE_TICKERS:         str   = ""         # comma-separated manual kill-switch
    PENNY_LOG_CSV_PATH:            str   = "/data/penny_signals.csv"
    PENNY_ENTRY_FILL_TIMEOUT_SEC:  float = 60.0      # max wait for LIMIT entry to fill before cancel
    PENNY_SL_M_MAX_ATTEMPTS:       int   = 2         # SL-M placement retries before unwind

    # Hourly report (spec §9.4)
    PENNY_HOURLY_REPORT_START_HOUR: int  = 10        # first hourly report at HH:00 IST (10 = 10:00)
    PENNY_HOURLY_REPORT_END_HOUR:   int  = 14        # last hourly report at HH:00 IST (14 = 14:00)
    PENNY_HOURLY_REPORT_WEBHOOK:   str   = ""        # optional webhook URL for delivery (Telegram/Slack)

    # ============================================================
    # REGIME ENGINE -- VIX-Free Volatility Detection
    # Replaces India VIX with ATR Compression + Realized Volatility
    # ============================================================

    # ATR Compression Ratio -- replaces VIX as primary volatility driver
    # rv_ratio = ATR_14 / ATR_14_SMA_200
    # rv_ratio <= 0.70 = compressed (calm baseline -> score 100)
    # rv_ratio  1.00  = normal                       -> score ~50
    # rv_ratio >= 1.20 = expansion (elevated stress) -> score ~20
    RV_ATR_COMPRESS_THRESHOLD: float = 0.70   # compressed = calm baseline
    RV_ATR_NORMAL:              float = 0.95   # mid-point of normal range
    RV_ATR_EXPANSION:           float = 1.20   # expansion threshold
    RV_ATR_CB_THRESHOLD:        float = 1.50   # circuit breaker -- forces R3
    RV_ATR_SPAN:                float = 0.50   # (RV_ATR_EXPANSION - RV_ATR_COMPRESS_THRESHOLD)
    RV_ATR_SCORE_SCALE:         float = 200.0  # scale factor for linear mapping

    # Realized Volatility -- secondary volatility signal (20-day, annualized)
    # rv_12% -> score 100; rv_20% -> score 60; rv_32% -> score 0
    RV_NORMAL_ANNUAL:  float = 0.18   # 18% annualized = normal vol baseline
    RV_CRISIS_ANNUAL:   float = 0.28   # 28% annualized = crisis threshold
    RV_SPAN:           float = 0.16   # (RV_CRISIS_ANNUAL - RV_NORMAL_ANNUAL)
    RV_SCORE_SCALE:    float = 625.0  # scale factor: 100 / 0.16

    # Volatility component weights (must sum to 1.0)
    RV_ATR_WEIGHT: float = 0.60   # ATR compression = primary (60%)
    RV_RV_WEIGHT:  float = 0.40   # realized vol   = secondary (40%)

    # Circuit breaker override
    ATR_CB_THRESHOLD: float = 1.50   # rv_ratio > 1.50 -> force REGIME_3_CRISIS

    # Nifty/BankNifty ratio -- breadth proxy (replaces weak EMA50-proxy)
    # nb_ratio percentile below 0.30 -> weak breadth -> x0.8 penalty
    NB_RATIO_LO_PCT:    float = 0.30   # breadth penalty threshold
    NB_RATIO_WINDOW:    int   = 60     # lookback window for percentile rank

    # VIX parameters -- DECOMMISSIONED (kept for backward compat with tests)
    # India VIX unavailable via Kite -> replaced by ATR compression + RV
    REGIME_VIX_BOUNDARY_12: float = 18.0
    REGIME_VIX_BOUNDARY_23: float = 25.0
    VIX_CB_THRESHOLD:        float = 40.0   # DEPRECATED -- use ATR_CB_THRESHOLD

    # RSI Percentile thresholds (bottom % of 6-month rolling range)
    RSI_PERCENTILE_REGIME1: float = 20.0   # Regime 1: bottom 20%
    RSI_PERCENTILE_REGIME2: float = 15.0   # Regime 2: bottom 15% (tighter)

    # Volume Z-score thresholds
    VOL_ZSCORE_REGIME1: float = 1.5       # Regime 1: 1.5 std devs above mean
    VOL_ZSCORE_REGIME2: float = 2.0       # Regime 2: 2.0 std devs
    VOL_ZSCORE_REGIME3: float = 2.5       # Regime 3: 2.5 std devs

    # Position sizing by regime (% of bankroll per trade)
    RISK_PCT_REGIME1: float = 0.10        # 10% -- normal market
    RISK_PCT_REGIME2: float = 0.07        # 7%  -- elevated uncertainty
    RISK_PCT_REGIME3: float = 0.05        # 5%  -- crisis

    # Stop loss by regime (ATR multipliers)
    STOP_ATR_REGIME1: float = 1.5        # 1.5x ATR
    STOP_ATR_REGIME2: float = 2.0        # 2.0x ATR
    STOP_ATR_REGIME3: float = 2.0        # 2.0x ATR

    # Stop loss by regime (% of close below price -- for pct_stop branch)
    STOP_PCT_REGIME1: float = 0.05      # 5% stop
    STOP_PCT_REGIME2: float = 0.05      # 5% stop
    STOP_PCT_REGIME3: float = 0.08      # 8% stop (wider in crisis)

    # Target structure (R-multiples)
    TARGET1_R: float = 1.5                # T1 = 1.5R (all regimes)
    TARGET2_R_REGIME1: float = 4.5        # T2 = 4.5R (Regime 1, was 3.0 -- let winners run)
    TARGET2_R_REGIME2: float = 3.0        # T2 = 3.0R (Regime 2)
    TARGET2_R_REGIME3: float = 1.0        # T2 = 1.0R (Regime 3 -- no T2, exit at T1)

    # Hard ceiling on Regime 1 positions -- never hold past this R-multiple.
    # Rationale: the trailing Chandelier can technically let a runaway trend
    # sit forever; this is a safety valve to ensure we bank the gains.
    HARD_CAP_R_REGIME1: float = 5.0       # Absolute ceiling in Regime 1

    # Partial exit at T1 (fraction of shares to exit)
    PARTIAL_EXIT_T1_PCT: float = 0.50    # Exit 50% at T1

    # Chandelier trailing stop -- legacy single multiplier (kept for backward compat)
    CHANDELIER_ATR_MULT: float = 3.0      # Highest close since entry - (3 * ATR)

    # Regime-aware Chandelier multipliers (override the legacy single setting)
    # Regime 1 (calm): wider trail (3.5x) -- gives mid-cap trends room to breathe
    # Regime 2 (elevated): default trail (3.0x) -- unchanged
    # Regime 3 (crisis): tighter trail (2.5x) -- cut losses fast
    CHANDELIER_ATR_REGIME1_MULT: float = 3.5
    CHANDELIER_ATR_REGIME2_MULT: float = 3.0
    CHANDELIER_ATR_REGIME3_MULT: float = 2.5

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

    # Kite endpoint -- direct (prod/VPS) or via OCI relay (home desktop).
    # Relay is a path-preserving forward proxy; auth + X-Kite-Version headers pass through.
    # Override with KITE_BASE_URL in .env (e.g. http://161.118.160.180:31527).
    KITE_BASE_URL: str = "https://api.kite.trade"

    # === Breadth Enrichment (2026-06-14) ===
    BREADTH_ENRICHMENT_ENABLED:         bool  = False   # Feature flag -- OFF by default
    BREADTH_UNIVERSE:                   str   = "NIFTY100"
    BREADTH_CACHE_TTL_SECONDS:          int   = 3600    # Tier 1 stale-while-revalidate window
    BREADTH_FETCH_TIMEOUT_SECONDS:      int   = 90      # Max time for Tier 1 fetch
    BREADTH_NARROW_RALLY_THRESHOLD:     float = 0.40    # R1 gate fires below this
    BREADTH_NARROW_GATE_EXEMPT_RANK:    float = 0.80    # Top quintile bypasses R1 gate
    BREADTH_RANK_BONUS_TOP:             int   = 15      # +15 if rank >= 0.80
    BREADTH_RANK_BONUS_MID:             int   = 7       # +7 if rank >= 0.60
    BREADTH_RANK_PENALTY_BOTTOM:        int   = -10     # -10 if rank < 0.20
    BREADTH_RANK_MULTIPLIER:            float = 1.2     # Top quintile score x this
    BREADTH_DATA_DEGRADED_THRESHOLD:    float = 0.10    # >10% fetch failures = degraded
    BREADTH_TIER1_PARALLELISM:          int   = 4       # Concurrent Kite historical fetches
    BREADTH_DATA_DIR:                   str   = "data"   # Path (relative to python-engine/) to nifty100.json

    # === Universe Expansion (2026-06-15) ===
    UNIVERSE_SIZE:                     int   = 500      # 100 or 500 — current trading universe size
    UNIVERSE_TICKERS_FILE:             str   = "nifty500.json"  # Filename inside BREADTH_DATA_DIR; same format as nifty100.json
    UNIVERSE_MIN_ADV_CRORE:            float = 2.0      # Drop tickers with 20-day median ADV below this (₹ crore)
    UNIVERSE_LIQUIDITY_LOOKBACK_DAYS:  int   = 20       # Lookback window for the median ADV computation


settings = Settings()
