import aiosqlite
from datetime import datetime, timezone
import pytz
import structlog
from config import settings

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")

async def init_ledger(db_path: str):
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bankroll_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, event_type TEXT,
                ticker TEXT, pnl REAL, bankroll_before REAL, bankroll_after REAL, notes TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS backtest_results (
                timestamp TEXT, strategy_version TEXT,
                gate TEXT, metrics_json TEXT
            )
        """)
        # [BK1]
        cursor = await db.execute("SELECT COUNT(*) FROM bankroll_ledger")
        count = (await cursor.fetchone())[0]
        if count == 0:
            await db.execute(
                "INSERT INTO bankroll_ledger (timestamp, event_type, pnl, bankroll_before, bankroll_after) VALUES (?, ?, ?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), "INITIAL", 0.0, settings.INITIAL_BANKROLL, settings.INITIAL_BANKROLL)
            )
        await db.commit()

async def current_bankroll(db_path: str) -> float:
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("SELECT bankroll_after FROM bankroll_ledger ORDER BY id DESC LIMIT 1")
        row = await cursor.fetchone()
        return row[0] if row else settings.INITIAL_BANKROLL

async def record_trade_close(db_path: str, ticker: str, pnl: float):
    # [BK2]
    before = await current_bankroll(db_path)
    after = before + pnl
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO bankroll_ledger (timestamp, event_type, ticker, pnl, bankroll_before, bankroll_after) VALUES (?, ?, ?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), "TRADE_CLOSED", ticker, pnl, before, after)
        )
        await db.commit()

async def check_circuit_breakers(db_path: str) -> tuple[bool, list[str]]:
    halted = False
    reasons = []
    
    bankroll = await current_bankroll(db_path)
    
    # [CB3] & [BK5]
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("SELECT MAX(bankroll_after) FROM bankroll_ledger")
        peak = (await cursor.fetchone())[0]
        
    if bankroll < settings.INITIAL_BANKROLL * settings.CB_FLOOR_PCT:
        halted = True
        reasons.append("CB_FLOOR_BREACHED")
        logger.error("bankroll_floor_breached", current=bankroll)
        
    if peak > 0 and ((peak - bankroll) / peak) >= settings.CB_MAX_DRAWDOWN_PCT:
        halted = True
        reasons.append("CB_MAX_DRAWDOWN")

    # [CB1] Daily loss — uses IST date since trading day is defined in IST
    today = datetime.now(IST).date().isoformat()
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT SUM(pnl) FROM bankroll_ledger WHERE event_type='TRADE_CLOSED' AND date(timestamp) = ?", (today,)
        )
        daily_pnl = (await cursor.fetchone())[0] or 0.0
        if daily_pnl <= -(bankroll * settings.CB_DAILY_LOSS_PCT):
            halted = True
            reasons.append("CB_DAILY_LOSS")

    # [CB2] Consecutive losses
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("SELECT pnl FROM bankroll_ledger WHERE event_type='TRADE_CLOSED' ORDER BY id DESC LIMIT 10")
        rows = await cursor.fetchall()
        streak = 0
        for r in rows:
            if r[0] < 0: streak += 1
            else: break
        if streak >= settings.CB_MAX_CONSECUTIVE_LOSSES:
            halted = True
            reasons.append("CB_CONSECUTIVE_LOSSES")
    """
    # [CB4] Backtest Gate
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("SELECT gate FROM backtest_results ORDER BY rowid DESC LIMIT 1")
        gate_row = await cursor.fetchone()
        if not gate_row or gate_row[0] == "FAIL":
            halted = True
            reasons.append("BACKTEST_GATE_FAILED")
    """
    return halted, reasons
