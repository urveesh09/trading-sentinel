import aiosqlite
from datetime import datetime
import structlog
from typing import List
from models import OpenPosition
from engine import calc_zerodha_costs

logger = structlog.get_logger()

async def init_positions_db(db_path: str):
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                ticker TEXT, exchange TEXT, entry_date TEXT, entry_price REAL, shares INTEGER,
                stop_loss_initial REAL, trailing_stop_current REAL, target_1 REAL, target_2 REAL,
                atr_14_at_entry REAL, highest_close_since_entry REAL, status TEXT, source TEXT,
                exit_price REAL, exit_date TEXT, realised_pnl REAL, r_multiple REAL,
                product_type TEXT DEFAULT 'CNC'
            )
        """)
        # [MED-008] Migration: add product_type column to pre-existing tables on the
        # persistent volume. ALTER TABLE silently fails if the column already exists.
        try:
            await db.execute("ALTER TABLE positions ADD COLUMN product_type TEXT DEFAULT 'CNC'")
        except Exception:
            pass  # Column already present — safe to ignore
        await db.commit()

async def get_open_positions(db_path: str) -> List[dict]:
    await init_positions_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        # Include CLOSED_T1 so the engine keeps managing the remaining 50% of the position
        async with db.execute("SELECT * FROM positions WHERE status IN ('OPEN', 'CLOSED_T1')") as cursor:
            return [dict(row) for row in await cursor.fetchall()]


async def update_daily_positions(db_path: str, kite_client, current_date_str: str, record_pnl_cb):
    open_pos = await get_open_positions(db_path)
    for pos in open_pos:
        ticker = pos['ticker']
        if pos.get('source') == 'MOMENTUM':
            continue
        df = await kite_client.get_historical(ticker, current_date_str, current_date_str)
        if df.empty: continue
        today_close = df['close'].iloc[-1]
        highest_close = max(pos['highest_close_since_entry'], today_close)
        new_trail = highest_close - (1.5 * pos['atr_14_at_entry'])
        trailing_stop = max(pos['trailing_stop_current'], new_trail)
        current_status = pos['status']
        status = current_status
        exit_price = None
        hit_t1_today = False
        entry_date = datetime.fromisoformat(pos['entry_date']).date()
        today = datetime.strptime(current_date_str, "%Y-%m-%d").date()
        days_held = (today - entry_date).days
        if today_close <= trailing_stop:
            status = "STOPPED_OUT"
            exit_price = trailing_stop
        elif today_close >= pos['target_2']:
            status = "CLOSED_T2"
            exit_price = pos['target_2']
        elif today_close >= pos['target_1'] and current_status == "OPEN":
            status = "CLOSED_T1"
            exit_price = pos['target_1']
            hit_t1_today = True
        elif days_held >= 15:
            status = "CLOSED_TIME"
            exit_price = today_close
        if status != current_status:
            if hit_t1_today:
                import math
                closed_shares = math.floor(pos['shares'] * 0.5)
                if closed_shares == 0: 
                    closed_shares = 1 # If only 1 share, sell it all
                remaining_shares = pos['shares'] - closed_shares
                gross = (exit_price - pos['entry_price']) * closed_shares
                costs = calc_zerodha_costs(pos['entry_price'], exit_price, closed_shares, is_intraday=False)
                realised_pnl = gross - costs
                await record_pnl_cb(ticker, realised_pnl)
                if remaining_shares == 0:
                    # Full close (if you only had 1 share)
                    risk_initial = (pos['entry_price'] - pos['stop_loss_initial']) * pos['shares']
                    r_multiple = realised_pnl / risk_initial if risk_initial > 0 else 0
                    async with aiosqlite.connect(db_path) as db:
                        await db.execute("""
                            UPDATE positions SET highest_close_since_entry=?, trailing_stop_current=?,
                            status=?, exit_price=?, exit_date=?, realised_pnl=?, r_multiple=?
                            WHERE ticker=? AND entry_date=?
                        """, (highest_close, trailing_stop, "CLOSED_T1", exit_price, current_date_str, 
                            realised_pnl, r_multiple, ticker, pos['entry_date']))
                        await db.commit()
                else:
                    # Partial close (Let the remaining 50% ride)
                    trailing_stop = max(trailing_stop, pos['entry_price']) # Move to breakeven
                    async with aiosqlite.connect(db_path) as db:
                        await db.execute("""
                            UPDATE positions SET highest_close_since_entry=?, trailing_stop_current=?,
                            status=?, shares=?
                            WHERE ticker=? AND entry_date=?
                        """, (highest_close, trailing_stop, "CLOSED_T1", remaining_shares, ticker, pos['entry_date']))
                        await db.commit()
            else:
                # Normal Full Close (Stop Loss, Target 2, or Time Expiry)
                gross = (exit_price - pos['entry_price']) * pos['shares']
                costs = calc_zerodha_costs(pos['entry_price'], exit_price, pos['shares'], is_intraday=False)
                realised_pnl = gross - costs
                risk_initial = (pos['entry_price'] - pos['stop_loss_initial']) * pos['shares']
                r_multiple = realised_pnl / risk_initial if risk_initial > 0 else 0
                await record_pnl_cb(ticker, realised_pnl)
                async with aiosqlite.connect(db_path) as db:
                    await db.execute("""
                        UPDATE positions SET highest_close_since_entry=?, trailing_stop_current=?,
                        status=?, exit_price=?, exit_date=?, realised_pnl=?, r_multiple=?
                        WHERE ticker=? AND entry_date=?
                    """, (highest_close, trailing_stop, status, exit_price, current_date_str, 
                        realised_pnl, r_multiple, ticker, pos['entry_date']))
                    await db.commit()
        else:
            # Just update the trailing stop and highest close for the day
            async with aiosqlite.connect(db_path) as db:
                await db.execute("""
                    UPDATE positions SET highest_close_since_entry=?, trailing_stop_current=?
                    WHERE ticker=? AND entry_date=?
                """, (highest_close, trailing_stop, ticker, pos['entry_date']))
                await db.commit()

