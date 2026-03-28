from fastapi import FastAPI, HTTPException, Request
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
import asyncio
import pandas as pd
import structlog

from config import settings
from kite_client import KiteClient
from market_calendar import is_trading_day
from engine import evaluate_signal, calc_ema
from portfolio import filter_and_allocate
from position_tracker import update_daily_positions, get_open_positions, init_positions_db
from performance import init_ledger, current_bankroll, record_trade_close, check_circuit_breakers
from models import PortfolioResponse, HealthResponse, ManualPositionRequest, BankrollAdjustment, Signal
from backtest import run_backtest
from models import PerformanceReport, OpenPosition
app = FastAPI(title="Quant Engine Container B")
logger = structlog.get_logger()
kite = KiteClient(settings.DB_PATH)
scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

# Shared State
state_lock = asyncio.Lock()
current_signals = []
rejected_signals = []
market_regime = "UNKNOWN"
last_run = None

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

@app.on_event("startup")
async def startup():
    await init_positions_db(settings.DB_PATH)
    await init_ledger(settings.DB_PATH)
    
    # Removed the immediate cache refresh and backtest from here!
    
    scheduler.add_job(kite.refresh_instrument_cache, 'cron', hour=8, minute=0)
    scheduler.add_job(run_screener, 'cron', hour=9, minute=20)
    scheduler.add_job(run_screener, 'cron', hour=14, minute=45)
    #scheduler.add_job(run_screener, 'cron', minute=0)
    scheduler.add_job(daily_post_market, 'cron', hour=15, minute=45)
    scheduler.start()

async def post_login_initialization():
    try:
        logger.info("running_post_login_setup")
        await kite.refresh_instrument_cache()
        
        df = await kite.get_historical("RELIANCE", "2024-01-01", datetime.utcnow().strftime("%Y-%m-%d"))
        if not df.empty:
            await run_backtest(settings.DB_PATH, {"RELIANCE": df}, settings.STRATEGY_VERSION)
            logger.info("initial_backtest_complete")
        await run_screener()
    except Exception as e:
        logger.error("initial_backtest_error", error=str(e))

async def run_screener():
    global current_signals, rejected_signals, market_regime, last_run
    
    today = datetime.utcnow().date()
    if not await is_trading_day(today, settings.DB_PATH):
        logger.info("market_closed")
        return

    halted, reasons = await check_circuit_breakers(settings.DB_PATH)
    if halted:
        logger.warning("screener_halted", reasons=reasons)
        return

    # Regime Filter [MR1]
    nifty_df = await kite.get_historical("NIFTY 50", (today - pd.Timedelta(days=120)).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))
    if nifty_df.empty: return
    
    nifty_close = nifty_df['close'].iloc[-1]
    nifty_ema50 = calc_ema(50, nifty_df['close']).iloc[-1]
    
    if nifty_close < nifty_ema50:
        market_regime = "BEAR"
        logger.info("regime_filter", regime="BEAR", reason="Nifty below EMA50")
        return
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
        universe = pd.DataFrame({"tradingsymbol": ["RELIANCE", "TCS", "HDFCBANK", "INFY"], "exchange": ["NSE"]*4, "sector": ["Energy", "IT", "Financial", "IT"]})

    raw_signals = []
    for _, row in universe.iterrows():
        ticker = row['tradingsymbol']
        df = await kite.get_historical(ticker, (today - pd.Timedelta(days=120)).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))
        if df.empty: continue
        
        valid, sig_data = evaluate_signal(ticker, df, bankroll, risk_pct)
        if valid:
            sig_data.update({
                "ticker": ticker, "exchange": row.get('exchange', 'NSE'), 
                "sector": row.get('sector', 'UNKNOWN'), "signal_time": datetime.utcnow(),
                "strategy_version": settings.STRATEGY_VERSION
            })
            raw_signals.append(sig_data)

    open_pos = await get_open_positions(settings.DB_PATH)
    
    async with state_lock:
        current_signals, rejected_signals = filter_and_allocate(raw_signals, open_pos, bankroll)
        last_run = datetime.utcnow()

async def daily_post_market():
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
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
            s.stale_data = (datetime.utcnow() - s.signal_time).total_seconds() > 3600

        return PortfolioResponse(
            run_time=last_run or datetime.utcnow(),
            market_regime=market_regime,
            bankroll=bankroll,
            backtest_gate="PASS" if "BACKTEST_GATE_FAILED" not in reasons else "FAIL",
            trading_halted=halted,
            halt_reasons=reasons,
            stale_data=bool(last_run and (datetime.utcnow() - last_run).total_seconds() > 3600),
            total_capital_at_risk=risk,
            total_capital_deployed=deployed,
            bankroll_utilization_pct=deployed / bankroll if bankroll else 0,
            open_positions_count=len(open_pos),
            remaining_slots=settings.MAX_OPEN_POSITIONS - len(open_pos),
            signals=current_signals
        )

@app.post("/token")
async def inject_token(request: Request):
    data = await request.json()
#    if data.get("secret") != settings.TOKEN_INJECTION_SECRET:
 #       raise HTTPException(status_code=403, detail="Unauthorized")
    kite.set_token(data["access_token"])
    await post_login_initialization()
    return {"status": "ok"}
"""
@app.get("/performance")
async def get_performance():
    # Placeholder to stop 404 errors until fully implemented
    return []
"""
@app.get("/performance", response_model=PerformanceReport)
async def get_performance():
    bankroll = await current_bankroll(settings.DB_PATH)
    return PerformanceReport(
        as_of=datetime.utcnow(),
        total_trades_taken=0,
        open_positions_count=0,
        closed_trades_count=0,
        win_count=0,
        loss_count=0,
        win_rate=0.0,
        avg_r_multiple=0.0,
        avg_winner_r=0.0,
        avg_loser_r=0.0,
        profit_factor=0.0,
        total_realised_pnl=0.0,
        current_bankroll=bankroll,  # <-- THIS IS WHERE REACT FINDS YOUR 5000!
        max_drawdown_pct=0.0,
        current_drawdown_pct=0.0,
        consecutive_losses=0,
        max_consecutive_losses=0,
        best_trade_r=0.0,
        worst_trade_r=0.0,
        avg_hold_days=0.0
    )
"""
@app.get("/positions")
async def get_positions():
    # Placeholder to stop 404 errors until fully implemented
    return []
"""
# --- MISSING DASHBOARD ROUTES ---
@app.get("/positions", response_model=list[OpenPosition])
async def get_positions_route():
    # React expects a list of OpenPosition objects. An empty list is valid here.
    return []
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
@app.get("/health")
async def health_check():
    return {"status": "ok"}
