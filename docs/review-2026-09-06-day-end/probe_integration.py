"""Offline integration probes for 1d41eb0; temporary DB, no transport."""
import asyncio
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python-engine"))
import aiosqlite
import proactive_intelligence as pi
from partner_fixture_adapter import apply_fixture_account
from hedge_analytics import load_partner_positions
from config import settings

async def main():
    now = datetime.now(timezone.utc)
    bars = []
    for i in range(21):
        close = 100 + i*.15
        bars.append(dict(timestamp=(now-timedelta(minutes=(20-i)*15)).isoformat(), open=close-.1,high=close+.3,low=close-.4,close=close,volume=100))
    bars[-1].update(open=103,high=104.2,low=102.8,close=104,volume=300)
    future = [dict(timestamp=(now+timedelta(minutes=5)).isoformat(),open=104,high=105,low=100,close=103,volume=100)]
    result = {}
    with tempfile.TemporaryDirectory(prefix="sentinel-dayend-") as folder:
        db = str(Path(folder)/"shadow.db")
        one = await pi.run_shadow_workflow(db,account_id="A",universe={"DEMO":bars},now=now, future_bars={"DEMO":future})
        await pi.run_shadow_workflow(db,account_id="B",universe={"DEMO":bars},now=now, future_bars={"DEMO":future})
        async with aiosqlite.connect(db) as conn:
            positions = await (await conn.execute("SELECT account_id,status,closed_at FROM proactive_shadow_positions")).fetchall()
            watches = await (await conn.execute("SELECT state FROM proactive_watchlist")).fetchall()
        result["position_accounts_after_A_and_B"] = [p[0] for p in positions]
        result["position_closed_after_workflow_now"] = any(p[2] and datetime.fromisoformat(p[2]) > now for p in positions)
        result["watchlist_states_after_close"] = [r[0] for r in watches]
        actual,_,_ = await pi._shadow_account_state(db,account_id="A",scenario_capital=8000)
        result["returned_cash"] = one["free_cash"]
        result["actual_cash_after_close"] = actual
        partner = str(Path(folder)/"partner.db")
        fixture = {"source":"fixture","account_id":"approved","snapshot_id":"bad","sequence":-1,"observed_at":now.isoformat(),"complete":True,"positions":[{"external_position_id":"ext","underlying":"NIFTY","tradingsymbol":"DEMO","quantity":10,"entry_price":100,"current_price":100}]}
        with patch.object(settings,"PARTNER_HEDGE_INPUT_EXPECTED_SOURCE","fixture"),patch.object(settings,"PARTNER_HEDGE_INPUT_EXPECTED_ACCOUNT_ID","approved"):
            try:
                await apply_fixture_account(partner,fixture,received_at=now)
            except Exception as exc:
                result["invalid_envelope_error"] = str(exc)
            result["positions_after_invalid_envelope"] = len(await load_partner_positions(partner))
    print(json.dumps(result,indent=2))

if __name__ == "__main__":
    asyncio.run(main())
