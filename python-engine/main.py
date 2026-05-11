from fastapi import FastAPI, HTTPException, Request
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta, timezone
import pytz
import os
import asyncio
import pandas as pd
import structlog
import aiosqlite
from pydantic import BaseModel
from config import settings
from kite_client import KiteClient
from market_calendar import is_trading_day, prev_trading_day, is_market_open
from engine import evaluate_signal, calc_ema, evaluate_momentum_signal, calc_zerodha_costs
from contextlib import asynccontextmanager
from portfolio import filter_and_allocate, filter_momentum_signals
from position_tracker import update_daily_positions, get_open_positions, init_positions_db
from performance import init_ledger, current_bankroll, record_trade_close, check_circuit_breakers
from models import PortfolioResponse, HealthResponse, ManualPositionRequest, BankrollAdjustment, Signal
from backtest import run_backtest
from models import PerformanceReport, OpenPosition
# app = FastAPI(title="Quant Engine Container B")
logger = structlog.get_logger()
kite = KiteClient(settings.DB_PATH)
scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

def snap_to_tick(price: float, direction: int = -1) -> float:
    """
    Snap a price to the nearest valid NSE tick (0.10 rupee).
    0.10 is the LCM of all NSE equity tick sizes (0.05 and 0.10).
    direction=-1 → round DOWN (sell orders, ensures limit is below current price)
    direction=+1 → round UP  (buy orders)
    Uses integer arithmetic to avoid IEEE-754 floating-point drift.
    """
    import math
    in_tenths = round(price * 10 * 100) / 100  # guard against micro-errors
    fn = math.ceil if direction >= 0 else math.floor
    return fn(in_tenths) / 10

# Shared State
state_lock = asyncio.Lock()
current_signals = []
rejected_signals = []
current_momentum_signals = []
market_regime = "UNKNOWN"
last_run = None

# Guard against concurrent post_login_initialization runs.
# node-gateway retries the /token endpoint up to 4 times (3 retries + initial)
# because post_login_initialization blocks for 20+ seconds while the handler
# has a 2-second AbortController. Without this flag, 4 concurrent screener
# runs fire simultaneously, each fetching the full universe from the Kite API.
_init_running = False

# 🚨 FIX: Add short-term memory to prevent 15-minute spam
signaled_momentum_today = set()
last_momentum_date = None


# @app.on_event("startup")
# async def startup():
#     await init_positions_db(settings.DB_PATH)
#     await init_ledger(settings.DB_PATH)
#     await kite.refresh_instrument_cache()
    
    # Run backtest if not run
#    try:
 #       df = await kite.get_historical("NSE: RELIANCE", "2015-01-01", datetime.utcnow().strftime("%Y-%m-%d"))
 #       if not df.empty:
 #           await run_backtest(settings.DB_PATH, {"NSE: RELIANCE": df}, settings.STRATEGY_VERSION)
  #  except Exception as e:
  #      logger.error("initial_backtest_error", error=str(e))
        
    # scheduler.add_job(kite.refresh_instrument_cache, 'cron', hour=8, minute=0)
    # scheduler.add_job(run_screener, 'cron', hour=9, minute=20)
    # scheduler.add_job(run_screener, 'cron', hour=14, minute=45)
    # scheduler.add_job(daily_post_market, 'cron', hour=15, minute=45)
    # scheduler.start()

IST = pytz.timezone("Asia/Kolkata")

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):

    db_dir = os.path.dirname(settings.DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    await init_positions_db(settings.DB_PATH)
    await init_ledger(settings.DB_PATH)
    
    asyncio.create_task(kite.refresh_instrument_cache())
    scheduler.add_job(kite.refresh_instrument_cache, 'cron', hour=8, minute=0)
    scheduler.add_job(run_screener, 'cron', hour=9, minute=20)
    scheduler.add_job(run_screener, 'cron', hour=14, minute=45)
    scheduler.add_job(daily_post_market, 'cron', hour=15, minute=45)
    scheduler.add_job(momentum_eod_warning, 'cron', hour=15, minute=10, id="momentum_eod_warning")
    scheduler.add_job(auto_square_momentum, 'cron', hour=15, minute=15, id="momentum_auto_square")
    
    for hour in [10, 11, 12, 13, 14]:
        for minute in [0, 15, 30, 45]:
            if hour == 10 and minute == 0:
                continue
            scheduler.add_job(run_momentum_screener, 'cron', hour=hour, minute=minute, id=f"momentum_scan_{hour}{minute}")

    scheduler.add_job(kite.clear_intraday_cache, 'cron', hour=0, minute=5, id="intraday_cache_cleanup")
    scheduler.start()
    yield

app = FastAPI(title="Quant Engine Container B", lifespan=lifespan)
# (Delete the old @app.on_event("startup") and async def startup(): lines completely)

# @app.on_event("startup")
# async def startup():
#     await init_positions_db(settings.DB_PATH)
#     await init_ledger(settings.DB_PATH)
    
#     # Refresh cache on startup so it's never empty
#     asyncio.create_task(kite.refresh_instrument_cache())
    
#     scheduler.add_job(kite.refresh_instrument_cache, 'cron', hour=8, minute=0)

#     scheduler.add_job(run_screener, 'cron', hour=9, minute=20)
#     scheduler.add_job(run_screener, 'cron', hour=14, minute=45)
#     #scheduler.add_job(run_screener, 'cron', minute=0)
#     scheduler.add_job(daily_post_market, 'cron', hour=15, minute=45)
#     scheduler.add_job(
#         momentum_eod_warning, 'cron',
#         hour=15, minute=10, id="momentum_eod_warning"
#     )
#     scheduler.add_job(
#         auto_square_momentum, 'cron',
#         hour=15, minute=15, id="momentum_auto_square"
#     )
#     for hour in [10, 11, 12, 13, 14]:
#         for minute in [0, 15, 30, 45]:
#             # Skip 10:00 AM because 4 candles (09:15, 09:30, 09:45, 10:00) don't exist until 10:00:01
#             # Actually at 10:00, the 10:00 candle just STARTS. So we only have 3 COMPLETED candles.
#             if hour == 10 and minute == 0:
#                 continue
#             scheduler.add_job(
#                 run_momentum_screener, 'cron',
#                 hour=hour, minute=minute,
#                 id=f"momentum_scan_{hour}{minute}"
#             )



#     # Intraday cache cleanup at midnight
#     scheduler.add_job(
#         kite.clear_intraday_cache, 'cron',
#         hour=0, minute=5, id="intraday_cache_cleanup"
#     )
#     scheduler.start()

# async def post_login_initialization():
#     try:
#         logger.info("running_post_login_setup")
#         await kite.refresh_instrument_cache()
        
#         df = await kite.get_historical("RELIANCE", "2024-01-01", datetime.utcnow().strftime("%Y-%m-%d"))
#         if not df.empty:
#             await run_backtest(settings.DB_PATH, {"RELIANCE": df}, settings.STRATEGY_VERSION)
#             logger.info("initial_backtest_complete")
#         await run_screener()
#     except Exception as e:
#         logger.error("initial_backtest_error", error=str(e))

async def post_login_initialization():
    global _init_running
    if _init_running:
        logger.info("post_login_init_skipped_already_running")
        return
    _init_running = True
    try:
        logger.info("running_post_login_setup")
        await kite.refresh_instrument_cache()
        df = await kite.get_historical(
            "RELIANCE", "2024-01-01",
            datetime.now(IST).strftime("%Y-%m-%d")
        )
        if not df.empty:
            await run_backtest(
                settings.DB_PATH, {"RELIANCE": df}, settings.STRATEGY_VERSION
            )
        await run_screener()           # existing swing screener
        await run_momentum_screener()  # NEW: momentum scan on login
    except Exception as e:
        logger.error("post_login_init_error", error=str(e))
    finally:
        _init_running = False

NIFTY_100_TICKERS = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "HINDUNILVR", "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK",
    "LT", "BAJFINANCE", "AXISBANK", "ASIANPAINT", "MARUTI", "TITAN", "SUNPHARMA", "HCLTECH", "ADANIENT", "TATAMOTORS",
    "NTPC", "JSWSTEEL", "ONGC", "M&M", "POWERGRID", "TATASTEEL", "ADANIPORTS", "COALINDIA", "BAJAJFINSV", "NESTLEIND",
    "GRASIM", "TECHM", "EICHERMOT", "BRITANNIA", "HINDALCO", "INDUSINDBK", "ADANIPOWER", "TATACONSUM", "HDFCLIFE", "SBILIFE",
    "DRREDDY", "CIPLA", "APOLLOHOSP", "DIVISLAB", "LTIM", "BAJAJ-AUTO", "HEROMOTOCO", "ULTRACEMCO", "BPCL", "WIPRO"
]

NIFTY_100_TICKERS = [
    "ABB", "ADANIENSOL", "ADANIENT", "ADANIGREEN", "ADANIPORTS", "ADANIPOWER", "ATGL", "AMBUJACEM", "APOLLOHOSP", "ASIANPAINT",
    "DMART", "AXISBANK", "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BAJAJHLDNG", "BANKBARODA", "BERGEPAINT", "BEL", "BHARTIARTL",
    "BPCL", "BRITANNIA", "CANBK", "CHOLAFIN", "CIPLA", "COALINDIA", "COLPAL", "DLF", "DRREDDY", "EICHERMOT",
    "GAIL", "GICRE", "GODREJCP", "GRASIM", "HAVELLS", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HEROMOTOCO", "HINDALCO",
    "HAL", "HINDUNILVR", "ICICIBANK", "ICICIGI", "ICICIPRULI", "IDBI", "ITC", "IOC", "IRCTC", "IRFC",
    "INDUSINDBK", "INFY", "INDIGO", "JSWSTEEL", "JSL", "KOTAKBANK", "LT", "LTM", "LICHSGFIN", "LICI",
    "M&M", "MARICO", "MARUTI", "NTPC", "NESTLEIND", "ONGC", "PIDILITIND", "PFC", "POWERGRID", "PNB",
    "RELIANCE", "RECLTD", "SBICARD", "SBILIFE", "SRF", "MOTHERSON", "SHREECEM", "SHRIRAMFIN", "SIEMENS", "SBIN",
    "SUNPHARMA", "SUNTV", "TATACOMM", "TATACONSUM", "TATAELXSI", "TMPV", "TATAPOWER", "TATASTEEL", "TCS", "TECHM",
    "TITAN", "TRENT", "TVSMOTOR", "ULTRACEMCO", "UNITDSPR", "VBL", "VEDL", "WIPRO", "ETERNAL", "ZYDUSLIFE"
]

async def run_screener():

    global current_signals, rejected_signals, market_regime, last_run
    
    now_ist = datetime.now(IST)
    today = now_ist.date()
    
    if not await is_trading_day(today, settings.DB_PATH):
        logger.info("market_closed")
        return

        # Check for login/token
    if not kite.access_token:
        logger.warning("screener_skipped", reason="no_access_token")
        return


        # Regime Filter [MR1]
    # NIFTY 50 ticker might be different depending on Kite's instrument list
    # Usually it's "NIFTY 50" but we should be sure.
    nifty_df = await kite.get_historical("NIFTY 50", (today - pd.Timedelta(days=365)).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))
    if nifty_df.empty:
        # Fallback to "NIFTY BANK" or log error
        logger.error("nifty_data_missing", ticker="NIFTY 50")
        return

    
    nifty_close = nifty_df['close'].iloc[-1]
    nifty_ema50 = calc_ema(50, nifty_df['close']).iloc[-1]
    
    if nifty_close < nifty_ema50:
        market_regime = "BEAR_RS_ONLY"
        logger.info("regime_filter", regime="BEAR_RS_ONLY",
                    reason="Nifty below EMA50 - switching to RS-only mode")
        # DO NOT return early - fall through to screener loop
        # The screener loop will apply RS filters based on market_regime
    elif nifty_close < nifty_ema50 * 1.02:
        market_regime = "CAUTION"
    else:
        market_regime = "BULL"

    bankroll = await current_bankroll(settings.DB_PATH)
    risk_pct = settings.RISK_PCT if market_regime != "CAUTION" else settings.RISK_PCT * 0.5
    
    try:
        universe = pd.read_csv(settings.UNIVERSE_PATH)
    except Exception:
        logger.warning("universe_csv_missing_fallback")
        universe = pd.DataFrame({
            "tradingsymbol": NIFTY_100_TICKERS,
            "exchange": ["NSE"] * len(NIFTY_100_TICKERS),
            "sector": ["UNKNOWN"] * len(NIFTY_100_TICKERS)
        })


    raw_signals = []
    total_evaluated = 0
    raw_rejected = []
    for _, row in universe.iterrows():
        total_evaluated += 1
        ticker = row['tradingsymbol']
        df = await kite.get_historical(ticker, (today - pd.Timedelta(days=365)).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))
        if df.empty:
            raw_rejected.append({"ticker": ticker, "reject_reason": "historical_data_empty"})
            continue

        
        valid, sig_data = evaluate_signal(ticker, df, bankroll, risk_pct, market_regime)
        if not valid:
            sig_data["ticker"] = ticker
            raw_rejected.append(sig_data)
            continue


        # [RS-FILTER] BEAR_RS_ONLY regime: apply RS gate
        if market_regime == "BEAR_RS_ONLY":
            from engine import calc_relative_strength, calc_volume_consistency
            rs_score = calc_relative_strength(df['close'], nifty_df['close'], periods=settings.RS_PERIODS)
            vol_consistent = calc_volume_consistency(df['volume'], n_days=settings.RS_MIN_DAYS_ABOVE_AVG, lookback=settings.RS_PERIODS)

            if rs_score < settings.RS_MIN_THRESHOLD:
                logger.info("rs_filter_reject", ticker=ticker,
                            rs=rs_score, reason=f"RS below {settings.RS_MIN_THRESHOLD} in BEAR regime")
                continue

            if not vol_consistent:
                logger.info("rs_filter_reject", ticker=ticker,
                            reason="Volume inconsistency in BEAR regime")
                continue

            sig_data['rs_score'] = rs_score
            sig_data['volume_consistent'] = vol_consistent
            logger.info("rs_filter_pass", ticker=ticker, rs=rs_score)
        else:
            from engine import calc_relative_strength, calc_volume_consistency
            sig_data['rs_score'] = calc_relative_strength(df['close'], nifty_df['close'], periods=settings.RS_PERIODS)
            sig_data['volume_consistent'] = calc_volume_consistency(df['volume'], n_days=settings.RS_MIN_DAYS_ABOVE_AVG, lookback=settings.RS_PERIODS)

        # SWING WINS: skip if this ticker already has an open momentum position
        open_pos_for_swing = await get_open_positions(settings.DB_PATH) # Refetch to be safe
        open_momentum_tickers = {
            p['ticker'] for p in open_pos_for_swing if p.get('source') == 'MOMENTUM'
        }
        if ticker in open_momentum_tickers:
            logger.info("swing_priority", ticker=ticker,
                        reason="Momentum position already open - swing wins")
            continue

        sig_data.update({
            "ticker": ticker, "exchange": row.get('exchange', 'NSE'), 
            "sector": row.get('sector', 'UNKNOWN'), "signal_time": datetime.now(timezone.utc),
            "strategy_version": settings.STRATEGY_VERSION,
            "strategy_type": "SWING"
        })
        raw_signals.append(sig_data)

    open_pos = await get_open_positions(settings.DB_PATH)

    
    async with state_lock:
        current_signals, rejected_signals = filter_and_allocate(raw_signals, open_pos, bankroll)
        # Combine all rejections
        from typing import List, Dict
        all_rejected: List[Dict] = raw_rejected + rejected_signals
        last_run = datetime.now(timezone.utc)
        if is_market_open():
            await notify_screener_results("SWING", current_signals, all_rejected, market_regime, bankroll)
        else:
            logger.info("swing_scan_silent", reason="outside_market_hours_notification_suppressed",
                        signals_found=len(current_signals))


async def daily_post_market():
    today_str = datetime.now(IST).strftime("%Y-%m-%d")
    await update_daily_positions(settings.DB_PATH, kite, today_str, lambda t, p: record_trade_close(settings.DB_PATH, t, p))

@app.get("/signals", response_model=PortfolioResponse)
async def get_signals():
    async with state_lock:
        halted, reasons = await check_circuit_breakers(settings.DB_PATH)
        open_pos = await get_open_positions(settings.DB_PATH)
        bankroll = await current_bankroll(settings.DB_PATH)
        
        risk = sum((p['entry_price'] - p['stop_loss_initial']) * p['shares'] for p in open_pos)
        deployed = sum(p['entry_price'] * p['shares'] for p in open_pos)
        
        # Mark stale
        for s in current_signals:
            s.stale_data = (datetime.now(timezone.utc) - s.signal_time).total_seconds() > 3600

        return PortfolioResponse(
            run_time=last_run or datetime.now(timezone.utc),
            market_regime=market_regime,
            bankroll=bankroll,
            backtest_gate="PASS" if "BACKTEST_GATE_FAILED" not in reasons else "FAIL",
            trading_halted=halted,
            halt_reasons=reasons,
            stale_data=bool(last_run and (datetime.now(timezone.utc) - last_run).total_seconds() > 3600),
            total_capital_at_risk=risk,
            total_capital_deployed=deployed,
            bankroll_utilization_pct=deployed / bankroll if bankroll else 0,
            open_positions_count=len(open_pos),
            remaining_slots=settings.MAX_OPEN_POSITIONS - len(open_pos),
            signals=current_signals
        )

async def run_momentum_screener():
    """
    Hourly intraday momentum scanner.
    """
    global current_momentum_signals

    now_ist = datetime.now(IST)
    today = now_ist.date()
    
    if not await is_trading_day(today, settings.DB_PATH):
        logger.info("momentum_scan_skip", reason="market_closed_today")
        return

    if not kite.access_token:
        logger.warning("momentum_screener_skipped", reason="no_access_token")
        return

    bankroll       = await current_bankroll(settings.DB_PATH)
    momentum_pool  = bankroll * settings.MOMENTUM_POOL_PCT  # 50% of bankroll = ₹2,500 at ₹5k

    # Market opens at 09:15 IST, closes at 15:30 IST
    market_open  = now_ist.replace(hour=9,  minute=15, second=0, microsecond=0)
    market_close = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)

    if now_ist < market_open:
        logger.info("momentum_scan_skip", reason="before_market_open_ist")
        return

    if now_ist > market_close:
        logger.info("momentum_scan_skip", reason="after_market_close_ist")
        return

    from_dt = market_open.strftime('%Y-%m-%d %H:%M:%S')
    to_dt   = now_ist.strftime('%Y-%m-%d %H:%M:%S')

    logger.info("momentum_scan_start", from_dt=from_dt, to_dt=to_dt)



    try:
        universe = pd.read_csv(settings.UNIVERSE_PATH)
    except Exception:
        logger.warning("universe_csv_missing_fallback_momentum")
        universe = pd.DataFrame({
            "tradingsymbol": NIFTY_100_TICKERS,
            "exchange":      ["NSE"] * len(NIFTY_100_TICKERS),
            "sector":        ["UNKNOWN"] * len(NIFTY_100_TICKERS)
        })


    open_pos          = await get_open_positions(settings.DB_PATH)
    open_momentum_pos = [p for p in open_pos if p.get('source') == 'MOMENTUM']
    open_swing_tickers = {
        p['ticker'] for p in open_pos if p.get('source') != 'MOMENTUM'
    }

    raw_momentum = []
    raw_rejected_momentum = []

    # [MC3-T] Time-aware volume threshold: elevated during lunchtime dead zone
    lunchtime_start = now_ist.replace(
        hour=settings.MOMENTUM_LUNCHTIME_START_HOUR,
        minute=settings.MOMENTUM_LUNCHTIME_START_MIN,
        second=0, microsecond=0
    )
    lunchtime_end = now_ist.replace(
        hour=settings.MOMENTUM_LUNCHTIME_END_HOUR,
        minute=settings.MOMENTUM_LUNCHTIME_END_MIN,
        second=0, microsecond=0
    )
    vol_threshold = (
        settings.MOMENTUM_VOL_SURGE_LUNCHTIME
        if lunchtime_start <= now_ist <= lunchtime_end
        else settings.MOMENTUM_VOL_SURGE_PCT
    )

    for _, row in universe.iterrows():
        ticker = row['tradingsymbol']

        # SWING WINS: skip if swing position open for this ticker
        if ticker in open_swing_tickers:
            raw_rejected_momentum.append({"ticker": ticker, "reject_reason": "swing_position_exists"})
            continue

        try:
            # Get today's intraday candles
            df_intra = await kite.get_intraday(ticker, from_dt, to_dt)
            if df_intra.empty:
                raw_rejected_momentum.append({"ticker": ticker, "reject_reason": "intraday_data_empty"})
                continue
            if len(df_intra) < 4:
                raw_rejected_momentum.append({"ticker": ticker, "reject_reason": "insufficient_intraday_candles", "count": len(df_intra)})
                continue

            # Get daily OHLCV: need ≥14 trading days for MC5 ATR gate + prev_day_high.
            # 30 calendar days guarantees 14+ trading days even across long holiday runs.
            yesterday_date = await prev_trading_day(today, settings.DB_PATH)
            from_date_for_daily = (yesterday_date - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
            df_daily = await kite.get_historical(
                ticker, from_date_for_daily, today.strftime("%Y-%m-%d")
            )
            if df_daily.empty or len(df_daily) < 1:
                raw_rejected_momentum.append({"ticker": ticker, "reject_reason": "daily_data_missing_for_prev_high"})
                continue

            # Filter out today's partial candle before using daily data.
            # Today's daily high/low are incomplete mid-session and would skew ATR.
            df_prev = df_daily[df_daily.index.date < today]
            if df_prev.empty:
                raw_rejected_momentum.append({"ticker": ticker, "reject_reason": "prev_day_data_not_found"})
                continue
            prev_day_high = float(df_prev['high'].iloc[-1])

            fired, sig_data = evaluate_momentum_signal(
                ticker=ticker,
                df=df_intra,
                prev_day_high=prev_day_high,
                bankroll=bankroll,
                momentum_pool=momentum_pool,
                df_daily=df_prev,          # filtered: no partial today candle; ≥14 rows for MC5 ATR
                vol_surge_threshold=vol_threshold,
                market_regime=market_regime,
            )

            if fired:
                sig_data.update({
                    "ticker":           ticker,
                    "exchange":         row.get('exchange', 'NSE'),
                    "sector":           row.get('sector', 'UNKNOWN'),
                    "signal_time":      datetime.now(timezone.utc),
                    "strategy_version": settings.STRATEGY_VERSION,
                    "ema_21": 0.0, "ema_50": 0.0, "ema_200": 0.0,
                    "atr_14": 0.0, "rsi_14": 0.0, "slope_5": 0.0,
                    "target_2": sig_data["target_1"],
                })
                raw_momentum.append(sig_data)
            else:
                sig_data["ticker"] = ticker
                raw_rejected_momentum.append(sig_data)

        except Exception as e:
            logger.error("momentum_scan_error", ticker=ticker, error=str(e))
            raw_rejected_momentum.append({"ticker": ticker, "reject_reason": f"exception: {str(e)}"})
            continue   # NEVER crash the full scan on one ticker failure

    accepted, rejected_mom = filter_momentum_signals(
        raw_momentum, open_momentum_pos, momentum_pool,
        settings.MAX_MOMENTUM_POSITIONS
    )

    async with state_lock:
        global signaled_momentum_today, last_momentum_date
        # Clear short-term memory at the start of a new trading day
        if today != last_momentum_date:
            signaled_momentum_today.clear()
            last_momentum_date = today

        current_momentum_signals = accepted
        all_rejected_mom = raw_rejected_momentum + rejected_mom

        # Filter for completely new signals that haven't been alerted today
        new_alerts = []
        for s in accepted:
            ticker = s.ticker if hasattr(s, 'ticker') else s.get('ticker')
            if ticker not in signaled_momentum_today:
                new_alerts.append(s)
                signaled_momentum_today.add(ticker)

        # Only send Telegram notifications during market hours (BUG-001 fix: mirrors swing screener guard).
        # The Q4 ignition call still runs this function pre-market to populate the cache,
        # but we must not spam Telegram at 08:30 IST with empty scan results.
        if is_market_open():
            if len(new_alerts) > 0:
                await notify_screener_results("MOMENTUM", new_alerts, all_rejected_mom, market_regime, bankroll, momentum_pool)
            else:
                logger.info("momentum_scan_silent", reason="no_new_signals_found")
                # Heartbeat: notify user the scan ran even with no signals
                await _notify_momentum_heartbeat(
                    now_ist, len(universe), len(raw_momentum),
                    len(accepted), all_rejected_mom, momentum_pool
                )
        else:
            logger.info("momentum_scan_pre_market", reason="outside_market_hours_notification_suppressed",
                        accepted=len(accepted), scan_time=now_ist.isoformat())


    logger.info("momentum_scan_complete",
                tickers_scanned=len(universe),
                signals_found=len(accepted))


@app.get("/momentum-signals")
async def get_momentum_signals():
    async with state_lock:
        bankroll      = await current_bankroll(settings.DB_PATH)
        momentum_pool = bankroll * settings.MOMENTUM_POOL_PCT  # 50% of bankroll = ₹2,500 at ₹5k
        halted, reasons = await check_circuit_breakers(settings.DB_PATH)

        for s in current_momentum_signals:
            s.stale_data = (
                datetime.now(timezone.utc) - s.signal_time
            ).total_seconds() > 1800   # 30 min stale for intraday

        return {
            "run_time":         last_run,
            "market_regime":    market_regime,
            "momentum_pool":    round(momentum_pool, 2),
            "trading_halted":   halted,
            "halt_reasons":     reasons,
            "signals":          current_momentum_signals
        }

async def auto_square_momentum():
    """
    [AUTO-SQUARE] 15:15 IST: Square off all open MOMENTUM positions.
    Calls Container A's internal square-off API.
    Uses smart order selection based on P&L state and market conditions.
    """
    import httpx as _httpx
    from datetime import time

    open_pos = await get_open_positions(settings.DB_PATH)
    momentum_pos = [p for p in open_pos if p.get('source') == 'MOMENTUM']

    if not momentum_pos:
        logger.info("auto_square_none", message="no_momentum_positions")
        return


    container_a_url = settings.CONTAINER_A_URL

    for pos in momentum_pos:
        ticker = pos['ticker']
        try:
            # Fetch current LTP to decide order type
            async with _httpx.AsyncClient() as _client:
                ltp_resp = await _client.get(
                    f"{container_a_url}/api/orders/ltp",
                    headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
                    params={"ticker": ticker},
                    timeout=5.0
                )
            ltp_data = ltp_resp.json()
            ltp = float(ltp_data.get("ltp", pos['entry_price']))

            current_pnl   = (ltp - pos['entry_price']) * pos['shares']
            is_profitable = current_pnl > 0

            # Smart order selection [as per user-confirmed factors]:
            # 1. In profit → limit order to protect gains
            # 2. After 15:00 IST → always market order (time constraint)
            # 3. Fast-moving stock (LTP far from entry) → market order
            # 4. Low liquidity → limit order to avoid slippage
            now_ist = datetime.now(IST)

            price_movement_pct = abs(ltp - pos['entry_price']) / pos['entry_price']
            is_fast_moving     = price_movement_pct > 0.02

            # [FIX] Zerodha API rejects MARKET orders without market_protection.
            # Use LIMIT everywhere; a SELL LIMIT slightly below LTP fills essentially
            # instantly on any liquid NSE stock, so there is no EOD fill-miss risk.
            # snap_to_tick(..., -1) rounds DOWN to the nearest 0.10-rupee tick,
            # which satisfies both 0.05 and 0.10 tick-size stocks.
            if is_profitable and not is_fast_moving and now_ist.time() < time(15, 0):
                order_type  = "LIMIT"
                limit_price = snap_to_tick(ltp * 0.999, -1)  # 0.1% below LTP — protect gains
            else:
                order_type  = "LIMIT"
                limit_price = snap_to_tick(ltp * 0.995, -1)  # 0.5% below LTP — aggressive fill for EOD exit

            payload = {

                "ticker":       ticker,
                "shares":       pos['shares'],
                "order_type":   order_type,
                "limit_price":  limit_price,
                "product_type": pos.get('product_type', 'MIS'),
                "reason":       "AUTO_SQUARE_EOD"
            }

            async with _httpx.AsyncClient() as _client:
                resp = await _client.post(
                    f"{container_a_url}/api/orders/square-off",
                    json=payload,
                    headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
                    timeout=10.0
                )
            resp.raise_for_status()
            logger.info("auto_square_sent", ticker=ticker,
                        order_type=order_type, pnl_estimate=current_pnl)

            # [MED-009] Record position close in Container B's DB using LTP as the
            # estimated fill price. The square-off order was just placed; we do not
            # have broker fill confirmation, so LTP is the best estimate available.
            gross        = (ltp - pos['entry_price']) * pos['shares']
            costs        = calc_zerodha_costs(pos['entry_price'], ltp, pos['shares'], is_intraday=True)
            realised_pnl = gross - costs
            risk_initial = (pos['entry_price'] - pos.get('stop_loss_initial', pos['entry_price'] * 0.95)) * pos['shares']
            r_multiple   = realised_pnl / risk_initial if risk_initial > 0 else 0

            async with aiosqlite.connect(settings.DB_PATH) as db:
                await db.execute("""
                    UPDATE positions
                    SET status='CLOSED_MANUAL', exit_price=?, exit_date=?,
                        realised_pnl=?, r_multiple=?
                    WHERE ticker=? AND source='MOMENTUM' AND status='OPEN'
                """, (ltp, datetime.now(timezone.utc).isoformat(),
                      realised_pnl, r_multiple, ticker))
                await db.commit()

            await record_trade_close(settings.DB_PATH, ticker, realised_pnl)
            logger.info("auto_square_position_closed", ticker=ticker,
                        exit_price=ltp, pnl=round(realised_pnl, 2), r=round(r_multiple, 4))

        except Exception as e:
            logger.error("auto_square_failed", ticker=ticker, error=str(e))
            # On failure: send Telegram alert for manual intervention
            await _notify_telegram_square_off_failure(ticker, pos)


async def momentum_eod_warning():
    """15:10 IST: Send 5-minute warning before auto-square."""
    open_pos = await get_open_positions(settings.DB_PATH)
    momentum_pos = [p for p in open_pos if p.get('source') == 'MOMENTUM']
    if not momentum_pos:
        return

    tickers = ", ".join(p['ticker'] for p in momentum_pos)
    # Uses existing Telegram notification mechanism in Container A
    import httpx as _httpx
    try:
        async with _httpx.AsyncClient() as _client:
            await _client.post(
                f"{settings.CONTAINER_A_URL}/api/internal/notify",
                json={"message": f"⚠️ AUTO-SQUARE in 5 min: {tickers}"},
                headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
                timeout=5.0
            )
    except Exception as e:
        logger.error("eod_warning_failed", error=str(e))

async def _notify_telegram_square_off_failure(ticker: str, pos: dict):
    """Notify Telegram about auto-square failure for manual intervention."""
    import httpx as _httpx
    msg = f"🚨 **CRITICAL: Auto-Square Failed** 🚨\nTicker: {ticker}\nShares: {pos['shares']}\nPlease square off manually in Zerodha immediately!"
    try:
        async with _httpx.AsyncClient() as _client:
            await _client.post(
                f"{settings.CONTAINER_A_URL}/api/internal/notify",
                json={"message": msg},
                headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
                timeout=5.0
            )
    except Exception as e:
        logger.error("telegram_notification_failed", error=str(e))


async def _notify_momentum_heartbeat(
    scan_time,
    tickers_scanned: int,
    raw_signals_count: int,
    accepted_count: int,
    rejected: list,
    momentum_pool: float
):
    """Send a detailed heartbeat to Telegram showing per-gate rejection breakdown."""
    import httpx as _httpx
    time_str      = scan_time.strftime("%H:%M IST")
    rejected_count = len(rejected)

    msg = (
        f"⏱️ **Momentum Scan @ {time_str}**\n"
        f"Scanned: `{tickers_scanned}` | Raw hits: `{raw_signals_count}` | Accepted: `{accepted_count}`\n"
        f"Rejected: `{rejected_count}` | Pool: `₹{momentum_pool:,.2f}`\n"
    )
    if accepted_count == 0:
        msg += "❌ No new signals - all gates filtered out.\n"

    if rejected:
        # Group rejections by reason
        reason_counts: dict = {}
        for r in rejected:
            reason = r.get("reject_reason", "unknown")
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

        msg += "\n📊 **Gate Rejection Breakdown:**\n"
        for reason, count in sorted(reason_counts.items(), key=lambda x: x[1], reverse=True):
            display = reason.replace("_", " ").title()
            msg += f"• {display}: `{count}`\n"

        # Show up to 8 informative rejected tickers (skip trivial data-missing reasons)
        _skip = {
            "intraday_data_empty", "insufficient_intraday_candles",
            "swing_position_exists", "daily_data_missing_for_prev_high",
            "prev_day_data_not_found",
        }
        interesting = [r for r in rejected if r.get("reject_reason") not in _skip]
        if interesting:
            msg += "\n🔍 **Sample Gate Failures:**\n"
            for r in interesting[:8]:
                ticker = r.get("ticker", "???")
                reason = r.get("reject_reason", "unknown").replace("_", " ").title()
                detail = ""
                try:
                    if "ratio" in r:
                        detail = f" [vol: {r['ratio']:.2f}x]"
                    elif "intraday_high" in r:
                        detail = f" [close:{r.get('close', 0):.1f} hi:{r['intraday_high']:.1f} thr:{r.get('threshold', 0):.1f}]"
                    elif "current_vwap" in r:
                        detail = f" [close:{r.get('current_close', 0):.1f} vwap:{r['current_vwap']:.1f}]"
                    elif "prev_high" in r:
                        detail = f" [close:{r.get('close', 0):.1f} prevhi:{r['prev_high']:.1f}]"
                except (TypeError, ValueError, KeyError):
                    detail = ""
                msg += f"• **{ticker}**: {reason}{detail}\n"

    try:
        async with _httpx.AsyncClient() as _client:
            await _client.post(
                f"{settings.CONTAINER_A_URL}/api/internal/notify",
                json={"message": msg},
                headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
                timeout=5.0
            )
    except Exception as e:
        logger.error("momentum_heartbeat_failed", error=str(e))


@app.post("/positions/manual")
async def add_manual_position(request: Request):
    """
    Called by Container A after a successful execution.
    Creates a new position in the database.
    """
    data = await request.json()
    secret = request.headers.get("X-Internal-Secret", "")
    if secret != settings.INTERNAL_API_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")

    ticker      = data["ticker"]
    entry_price = float(data["entry_price"])
    shares      = int(data["shares"])
    # If source is explicitly sent (e.g. MOMENTUM), use it. 
    # Default to SYSTEM for swing.
    source      = data.get("source", "SYSTEM")
    # [MED-008] Persist product_type so auto_square_momentum() can read it correctly.
    product_type = data.get("product_type", "CNC")
    
    stop_loss   = float(data.get("stop_loss", entry_price * 0.95))
    target_1    = float(data.get("target_1", entry_price * 1.05))
    target_2    = float(data.get("target_2", entry_price * 1.10))
    
    async with aiosqlite.connect(settings.DB_PATH) as db:
        await db.execute("""
            INSERT INTO positions (
                ticker, exchange, entry_date, entry_price, shares,
                stop_loss_initial, trailing_stop_current, target_1, target_2,
                atr_14_at_entry, highest_close_since_entry, status, source, product_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (ticker, data.get("exchange", "NSE"), datetime.now(timezone.utc).isoformat(),
              entry_price, shares, stop_loss, stop_loss, target_1, target_2,
              0.0, entry_price, "OPEN", source, product_type))
        await db.commit()
    
    logger.info("position_added_manually", ticker=ticker, source=source)
    return {"status": "ok"}

@app.post("/positions/close")

async def close_position(request: Request):
    """
    Called by Container A after a square-off order is confirmed.
    Updates position status to CLOSED_MANUAL and records P&L.
    """
    data = await request.json()
    secret = request.headers.get("X-Internal-Secret", "")
    if secret != settings.INTERNAL_API_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")

    ticker     = data["ticker"]
    exit_price = float(data["exit_price"])
    order_id   = data.get("order_id", "")

    open_pos = await get_open_positions(settings.DB_PATH)
    pos = next((p for p in open_pos if p['ticker'] == ticker
                and p.get('source') == 'MOMENTUM'), None)
    if not pos:
        raise HTTPException(status_code=404,
                            detail=f"No open MOMENTUM position for {ticker}")

    gross = (exit_price - pos['entry_price']) * pos['shares']
    costs = calc_zerodha_costs(
        pos['entry_price'], exit_price, pos['shares'], is_intraday=True
    )
    realised_pnl = gross - costs
    risk_initial = (pos['entry_price'] - pos['stop_loss_initial']) * pos['shares']
    r_multiple   = realised_pnl / risk_initial if risk_initial > 0 else 0

    async with aiosqlite.connect(settings.DB_PATH) as db:
        await db.execute("""
            UPDATE positions
            SET status='CLOSED_MANUAL', exit_price=?, exit_date=?,
                realised_pnl=?, r_multiple=?
            WHERE ticker=? AND source='MOMENTUM' AND status='OPEN'
        """, (exit_price, datetime.now(timezone.utc).isoformat(),
              realised_pnl, r_multiple, ticker))
        await db.commit()

    await record_trade_close(settings.DB_PATH, ticker, realised_pnl)
    logger.info("momentum_position_closed", ticker=ticker,
                exit_price=exit_price, pnl=realised_pnl, r=r_multiple)

    return {"status": "closed", "ticker": ticker,
            "realised_pnl": round(realised_pnl, 2),
            "r_multiple":   round(r_multiple, 4)}

# @app.post("/token")
# async def inject_token(request: Request):
#     data = await request.json()
# #    if data.get("secret") != settings.TOKEN_INJECTION_SECRET:
#  #       raise HTTPException(status_code=403, detail="Unauthorized")
#     kite.set_token(data["access_token"])
#     await post_login_initialization()
#     return {"status": "ok"}


class TokenPayload(BaseModel):
    access_token: str

@app.post("/token")
async def inject_token(payload: TokenPayload):
    kite.set_token(payload.access_token)
    # Fire-and-forget: return 200 immediately so node-gateway's 2-second
    # AbortController does not trigger retries that spawn concurrent screener runs.
    # post_login_initialization runs in the background (Q4 behaviour is preserved).
    asyncio.create_task(post_login_initialization())
    return {"status": "ok"}


@app.get("/performance", response_model=PerformanceReport)
async def get_performance():
    bankroll = await current_bankroll(settings.DB_PATH)
    open_pos = await get_open_positions(settings.DB_PATH)
    
    async with aiosqlite.connect(settings.DB_PATH) as db:
        # cursor = await db.execute("SELECT * FROM positions WHERE status != 'OPEN'")
        cursor = await db.execute("SELECT * FROM positions WHERE status NOT IN ('OPEN', 'CLOSED_T1')")
        closed_trades = await cursor.fetchall()
        
    # Simple metrics for now
    total_trades = len(closed_trades) + len(open_pos)
    win_count = sum(1 for t in closed_trades if (t[14] or 0) > 0) # realised_pnl is at index 14
    loss_count = sum(1 for t in closed_trades if (t[14] or 0) < 0)
    total_pnl = sum(t[14] or 0 for t in closed_trades)
    
    return PerformanceReport(
        as_of=datetime.now(timezone.utc),
        total_trades_taken=total_trades,
        open_positions_count=len(open_pos),
        closed_trades_count=len(closed_trades),
        win_count=win_count,
        loss_count=loss_count,
        win_rate=win_count/len(closed_trades) if closed_trades else 0,
        avg_r_multiple=sum(t[15] or 0 for t in closed_trades)/len(closed_trades) if closed_trades else 0,
        avg_winner_r=0.0,
        avg_loser_r=0.0,
        profit_factor=0.0,
        total_realised_pnl=total_pnl,
        current_bankroll=bankroll,
        max_drawdown_pct=0.0,
        current_drawdown_pct=0.0,
        consecutive_losses=0,
        max_consecutive_losses=0,
        best_trade_r=0.0,
        worst_trade_r=0.0,
        avg_hold_days=0.0
    )

@app.get("/positions", response_model=list[OpenPosition])
async def get_positions_route():
    open_pos = await get_open_positions(settings.DB_PATH)
    return open_pos

@app.get("/bankroll")
async def get_bankroll_route():
    val = await current_bankroll(settings.DB_PATH)
    return {"status": "ok", "bankroll": val}

@app.get("/circuit-breaker")
async def get_circuit_breaker():
    halted, reasons = await check_circuit_breakers(settings.DB_PATH)
    return {"trading_halted": halted, "halt_reasons": reasons}

@app.get("/rejected")
async def get_rejected_signals():
    return {"data": []}
async def notify_screener_results(
    strategy_type: str,
    accepted: list,
    rejected: list,
    regime: str,
    bankroll: float,
    pool: float = None
):
    """
    Sends a detailed summary of the screener run to Telegram via Container A.
    """
    import httpx as _httpx
    
    msg = f"🔍 **{strategy_type} Screener Run**\n"
    msg += f"Regime: `{regime}` | Bankroll: `₹{bankroll:,.2f}`\n"
    if pool:
        msg += f"Strategy Pool: `₹{pool:,.2f}`\n"
    msg += "---"
    
    if accepted:
        msg += f"\n✅ **Signals Found ({len(accepted)}):**\n"
        for s in accepted:
            ticker = s.ticker if hasattr(s, 'ticker') else s.get('ticker')
            price = s.close if hasattr(s, 'close') else s.get('close')
            shares = s.shares if hasattr(s, 'shares') else s.get('shares')
            msg += f"• **{ticker}** @ {price} (Qty: {shares})\n"
    else:
        msg += "\n❌ No signals passed all filters."


    if rejected:
        # Group rejections by reason
        reason_counts = {}
        for r in rejected:
            reason = r.get('reject_reason', 'unknown')
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        
        msg += "\n\n📊 **Rejection Summary:**\n"
        # Sort by count descending
        for reason, count in sorted(reason_counts.items(), key=lambda x: x[1], reverse=True):
            # Clean up reason string for display
            display_reason = reason.replace("_", " ").title()
            msg += f"• {display_reason}: {count}\n"
        
        if len(rejected) > 0:
            # Group specific rejections by ticker for meaningful examples
            msg += "\n🔍 **Rejected Tickers:**\n"
            # Sort rejections to show the most "interesting" ones first (e.g. not empty data)
            interesting_rejections = [r for r in rejected if "empty" not in r.get('reject_reason', '').lower()]
            if not interesting_rejections:
                interesting_rejections = rejected

            # Show up to 10 examples to be comprehensive
            for r in interesting_rejections[:10]:
                ticker = r.get('ticker', '???')
                reason = r.get('reject_reason', 'unknown').replace("_", " ").title()
                msg += f"• {ticker}: {reason}\n"

            
    # Send to Container A for Telegram delivery

    try:
        async with _httpx.AsyncClient() as _client:
            await _client.post(
                f"{settings.CONTAINER_A_URL}/api/internal/notify",
                json={"message": msg},
                headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
                timeout=5.0
            )
    except Exception as e:
        logger.error("telegram_notification_failed", error=str(e))

@app.post("/test-momentum")
async def test_momentum_screener():
    """Manual trigger for testing the momentum scanner."""
    asyncio.create_task(run_momentum_screener())
    return {"status": "momentum_scan_triggered"}

@app.get("/health")


async def health_check():
    return {"status": "ok"}
