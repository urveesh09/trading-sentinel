"""Offline run-contract probes. No broker, AI or Telegram calls."""
import asyncio
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python-engine"))
import aiosqlite
import proactive_intelligence as pi

async def main():
    base = datetime.now(timezone.utc)
    bars = [{"timestamp":(base-timedelta(minutes=(20-i)*15)).isoformat(),"open":100+i*.15-.2,"high":100+i*.15+.3,"low":100+i*.15-.4,"close":100+i*.15,"volume":100} for i in range(21)]
    bars[-3].update(open=102.1,high=102.4,low=101.8,close=102)
    bars[-2].update(open=102,high=102.4,low=101.8,close=102.1)
    bars[-1].update(open=103.8,high=104.2,low=103.4,close=104,volume=300)
    future=[dict(timestamp=(base+timedelta(minutes=5)).isoformat(),open=104,high=105,low=103,close=104),dict(timestamp=(base+timedelta(minutes=10)).isoformat(),open=104,high=105,low=100,close=101)]
    out={}
    with tempfile.TemporaryDirectory(prefix="run-contract-") as folder:
        async def run(name, minute, later=future, **extra):
            return await pi.run_shadow_workflow(str(Path(folder)/(name+".db")),account_id="demo",run_id="test",universe={"DEMO":bars},now=base+timedelta(minutes=minute),future_bars={"DEMO":later},scenario_capital=1000,fee_rate=0,slippage_bps=0,**extra)
        async def query(name,sql):
            async with aiosqlite.connect(str(Path(folder)/(name+".db"))) as db:
                return await (await db.execute(sql)).fetchall()
        initial_single=await run("single",10)
        out["single_initial_free_cash"]=initial_single["free_cash"]
        await run("split",5)
        out["watchlist_when_position_open"]=await query("split","SELECT state FROM proactive_watchlist")
        await run("split",10)
        out["single_step_outcome"]=await query("single","SELECT exit_price,net_pnl FROM proactive_shadow_positions")
        out["incremental_outcome"]=await query("split","SELECT exit_price,net_pnl FROM proactive_shadow_positions")
        before=await run("clock",0)
        out["positions_before_future_bars_visible"]=await query("clock","SELECT COUNT(*) FROM proactive_shadow_positions")
        await run("pending",0,[])
        await run("pending",31,[])
        out["pending_state_after_deadline"]=await query("pending","SELECT state FROM proactive_watchlist")
        try:
            await run("split",0)
            out["backward_run_clock_rejected"]=False
        except ValueError:
            out["backward_run_clock_rejected"]=True
        out["identical_rerun_free_cash"]= (await run("single",10))["free_cash"]
        out["single_after_identical_rerun"]=await query("single","SELECT policy_id,opened_at,net_pnl FROM proactive_shadow_positions")
    print(json.dumps(out,indent=2))

if __name__=="__main__":
    asyncio.run(main())
