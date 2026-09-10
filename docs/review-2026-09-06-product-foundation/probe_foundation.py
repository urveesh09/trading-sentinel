"""Offline probes for 768741c; isolated SQLite, no external calls."""
import asyncio
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python-engine"))
from proactive_intelligence import *
from partner_fixture_adapter import apply_fixture_account
from hedge_analytics import load_partner_positions
from config import settings

async def main():
    now = datetime.now(timezone.utc)
    results = {}
    proposal = ShadowProposal("x", "trend", "DEMO", 100, 95, 110, now+timedelta(minutes=30), 1, 100, "test")
    bar = {"timestamp": (now+timedelta(minutes=1)).isoformat(), "open": 200, "high": 202, "low": 198, "close": 200}
    sim = simulate_shadow_trade(proposal, [bar], cash=1000)
    results["gap_entry_notional_with_1000_cash"] = sim.quantity * sim.entry_price
    oldbar = {"timestamp": (now-timedelta(days=1)).isoformat(), "open": 100, "high": 102, "low": 99, "close": 101}
    results["pre_signal_bar_status"] = simulate_shadow_trade(proposal, [oldbar], cash=1000).status
    with tempfile.TemporaryDirectory(prefix="sentinel-foundation-") as folder:
        db = str(Path(folder)/"activity.db")
        async def event(opp, stage, key):
            await record_opportunity_event(db, opportunity_id=opp, policy_id="test", policy_version="1", account_id="dev", mode="SHADOW", instrument="DEMO", stage=stage, reason_code="TEST", idempotency_key=key, observed_at=now)
        await event("a", "SETUP", "a1")
        await event("b", "REJECTED", "b1")
        results["unique_opportunities_for_two_distinct_ids"] = (await proactive_activity_report(db))["modes"]["SHADOW"]["unique_opportunities"]
        await event("a", "FILLED", "a2")
        await event("c", "RISK_APPROVED", "c1")
        results["dropped_c_hidden_by_unrelated_fill"] = not any(x["code"] == "DROPPED_RISK_APPROVED_WORKFLOW" for x in await proactive_inactivity_diagnostics(db, now=now))
        results["empty_database_diagnostics"] = await proactive_inactivity_diagnostics(str(Path(folder)/"empty.db"), now=now)
        partner = str(Path(folder)/"partner.db")
        row = {"external_position_id":"ext", "underlying":"NIFTY", "tradingsymbol":"DEMO", "quantity":10, "entry_price":100, "current_price":100}
        def fixture(seq, rows):
            return {"source":"fixture", "account_id":"demo", "snapshot_id":str(seq), "sequence":seq, "observed_at":(now+timedelta(seconds=seq)).isoformat(), "complete":True, "positions":rows}
        with patch.object(settings,"PARTNER_HEDGE_INPUT_EXPECTED_SOURCE","fixture"), patch.object(settings,"PARTNER_HEDGE_INPUT_EXPECTED_ACCOUNT_ID","demo"):
            await apply_fixture_account(partner, fixture(1,[row]), received_at=now+timedelta(seconds=1))
            await apply_fixture_account(partner, fixture(2,[]), received_at=now+timedelta(seconds=2))
            try:
                await apply_fixture_account(partner, fixture(3,[row]), received_at=now+timedelta(seconds=3))
                results["reopen"] = "accepted"
            except Exception as exc:
                results["reopen"] = str(exc)
            bad = fixture(4,[{**row,"external_position_id":"new"},{"external_position_id":"bad"}])
            try:
                await apply_fixture_account(partner,bad,received_at=now+timedelta(seconds=4))
            except Exception:
                pass
            results["open_rows_after_rejected_fixture"] = len(await load_partner_positions(partner))
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
