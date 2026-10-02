"""Offline fault-boundary probe; no broker, no Production data."""
import asyncio
import json
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from fno_positions import init_fno_positions_db, close_position
from performance import init_ledger, record_trade_close

async def main():
    with tempfile.TemporaryDirectory() as folder:
        path=str(Path(folder)/'audit.db')
        await init_fno_positions_db(path)
        await init_ledger(path)
        result=await close_position(path,999,datetime.now(timezone.utc),90,25000,'audit',-10,0,-10,-1,None)
        for _ in range(2):
            await record_trade_close(path,ticker='AUDIT_ONLY',pnl=-10,r_multiple=-1,
                source='FNO_PAPER',origin_ref='fno_position:999')
        with sqlite3.connect(path) as c:
            count,pnl=c.execute("SELECT count(*),sum(pnl) FROM bankroll_ledger WHERE origin_ref='fno_position:999'").fetchone()
        print(json.dumps({'nonexistent_position_close_return':result,'same_origin_ledger_rows':count,'pnl':pnl}))

asyncio.run(main())
