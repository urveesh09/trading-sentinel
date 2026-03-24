import aiosqlite
from datetime import datetime
import structlog
from typing import List
from models import OpenPosition

logger = structlog.get_logger()

async def init_positions_db(db_path: str):
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                ticker TEXT, exchange TEXT, entry_date TEXT, entry_price REAL, shares INTEGER,
                stop_loss_initial REAL, trailing_stop_current REAL, target_1 REAL, target_2 REAL,
                atr_14_at_entry REAL, highest_close_since_entry REAL, status TEXT, source TEXT,
                exit_price REAL, exit_date TEXT, realised_pnl REAL, r_multiple REAL
            )
        """)
        await db.commit()

async def get_open_positions(db_path: str) -> List[dict]:
    await init_positions_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM positions WHERE status='OPEN'") as cursor:
            return [dict(row) for row in await cursor.fetchall()]

async def update_daily_positions(db_path: str, kite_client, current_date_str: str, record_pnl_cb):
    open_pos = await get_open_positions(db_path)
    
    for pos in open_pos:
        ticker = pos['ticker']
        df = await kite_client.get_historical(ticker, current_date_str, current_date_str)
        if df.empty: continue
        
        today_close = df['close'].iloc[-1]
        highest_close = max(pos['highest_close_since_entry'], today_close)
        
        # [R6] Trailing Stop Update
        new_trail = highest_close - (1.5 * pos['atr_14_at_entry'])
        trailing_stop = max(pos['trailing_stop_current'], new_trail)
        
        status = "OPEN"
        exit_price = None
        
        entry_date = datetime.fromisoformat(pos['entry_date']).date()
        today = datetime.strptime(current_date_str, "%Y-%m-%d").date()
        days_held = (today - entry_date).days
        
        if today_close <= trailing_stop:
            status = "STOPPED_OUT"
            exit_price = trailing_stop
        elif today_close >= pos['target_2']:
            status = "CLOSED_T2"
            exit_price = pos['target_2']
        elif today_close >= pos['target_1']:
            status = "CLOSED_T1"
            exit_price = pos['target_1']
        elif days_held >= 15:
            status = "CLOSED_TIME"
            exit_price = today_close
            
        realised_pnl = None
        r_multiple = None
        if status != "OPEN":
            gross = (exit_price - pos['entry_price']) * pos['shares']
            costs = (pos['entry_price'] + exit_price) * pos['shares'] * 0.001
            realised_pnl = gross - costs
            risk_initial = (pos['entry_price'] - pos['stop_loss_initial']) * pos['shares']
            r_multiple = realised_pnl / risk_initial if risk_initial > 0 else 0
            await record_pnl_cb(ticker, realised_pnl)
            
        async with aiosqlite.connect(db_path) as db:
            await db.execute("""
                UPDATE positions SET highest_close_since_entry=?, trailing_stop_current=?,
                status=?, exit_price=?, exit_date=?, realised_pnl=?, r_multiple=?
                WHERE ticker=? AND entry_date=?
            """, (highest_close, trailing_stop, status, exit_price, current_date_str if exit_price else None, 
                  realised_pnl, r_multiple, ticker, pos['entry_date']))
            await db.commit()
            
        logger.info("position_update", event_type="position_update", ticker=ticker, status=status)
