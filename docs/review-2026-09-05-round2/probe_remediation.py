"""Offline regression probes for 705d23d. No network, live account, or Production writes.
Run with python-engine/winvenv/Scripts/python.exe. Outputs current behavior only.
"""
import asyncio
import json
import runpy
import sys
import tempfile
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python-engine"))
import pytest
import hedge_advisory as ha
import partner_input_refresh as pi
from hedge_analytics import create_partner_position, get_partner_position, load_partner_positions, load_reconciled_open_partner_positions
from partner_bot import PartnerSendResult
from config import settings

f = runpy.run_path(str(ROOT / "python-engine/tests/test_hedge_advisory.py"))
NOW = f["NOW"]
results = {}

async def seed(db):
    return await create_partner_position(db, f["_position"]())

def row(p, quantity=40000):
    return dict(position_id=p.position_id, observed_quantity=quantity, quantity_basis="UNITS",
                current_price=100, price_as_of=NOW.isoformat())

def snap(p, rows, **kw):
    return dict(source=p.source, observed_at=NOW.isoformat(), complete=True, positions=rows, **kw)

async def main():
    with tempfile.TemporaryDirectory(prefix="ts-review-round2-") as tmp:
        def db(name): return str(Path(tmp) / (name + ".db"))
        path = db("tick")
        p = await seed(path)
        errors, sends = [], []
        class Log:
            def info(self, *a, **k): pass
            def warning(self, *a, **k): pass
            def error(self, *a, **k): errors.append([str(x) for x in a])
        async def trading(*a, **k): return True
        async def chain(*a, **k): return f["_snapshot"]()
        async def sender(*a, **k):
            sends.append(k.get("kind"))
            return PartnerSendResult(True, 111, "acknowledged")
        with pytest.MonkeyPatch.context() as m:
            m.setattr(settings, "DB_PATH", path)
            m.setattr(settings, "PARTNER_HEDGE_ENABLED", True)
            m.setattr(settings, "PARTNER_HEDGE_PROTECTIVE_PUT", True)
            m.setattr(settings, "PARTNER_HEDGE_FUTURES", True)
            m.setattr(ha, "partner_enabled", lambda: True)
            m.setattr(ha, "logger", Log())
            m.setattr(ha, "send_partner_result", sender)
            m.setattr(ha, "take_chain_snapshot", chain)
            m.setattr(ha, "get_instruments_for", lambda _: SimpleNamespace(ready=lambda _: True, option_expiries=[f["EXPIRY"]]))
            m.setitem(sys.modules, "main", SimpleNamespace(is_trading_day=trading, kite=SimpleNamespace(access_token="offline")))
            builder_count = len(ha.build_hedge_reviews([p], f["_snapshot"](), now=NOW))
            await ha.partner_hedge_tick(NOW)
        results["phase1_valid_input_tick"] = dict(builder_reviews=builder_count, sender_calls=len(sends), errors=errors)

        path = db("atomic")
        p = await seed(path)
        try:
            await pi.apply_partner_input_snapshot(path, snap(p, [row(p, 20000), {"position_id":999999,"observed_quantity":1}]))
        except Exception as exc:
            error = str(exc)
        results["invalid_second_row"] = dict(error=error, quantity_after=(await get_partner_position(path,p.position_id)).signed_quantity)

        path = db("stale")
        p = await seed(path)
        old = snap(p, [])
        old["observed_at"] = (NOW - timedelta(days=1)).isoformat()
        outcome = await pi.apply_partner_input_snapshot(path, old)
        results["stale_complete_empty"] = dict(outcome=outcome, open_rows=len(await load_partner_positions(path)))

        path = db("vix")
        p = await seed(path)
        try:
            await pi.apply_partner_input_snapshot(path, snap(p, [], vix={"spot":-1,"observed_at":NOW.isoformat()}))
        except Exception as exc:
            error = str(exc)
        results["invalid_vix_after_close"] = dict(error=error, open_rows=len(await load_partner_positions(path)))

        path = db("partial")
        p = await seed(path)
        data = snap(p, [row(p)])
        data["complete"] = False
        await pi.apply_partner_input_snapshot(path, data)
        results["partial_snapshot_readiness"] = ha._portfolio_input_reason(await load_partner_positions(path), await load_reconciled_open_partner_positions(path), NOW)

        path = db("repeat")
        p = await seed(path)
        await pi.apply_partner_input_snapshot(path, snap(p, [row(p)]))
        before = await get_partner_position(path,p.position_id)
        data = snap(p,[row(p)])
        data["observed_at"] = (NOW + timedelta(minutes=2)).isoformat()
        await pi.apply_partner_input_snapshot(path,data)
        after = await get_partner_position(path,p.position_id)
        results["unchanged_refresh_versions_input"] = dict(quantity_unchanged=before.signed_quantity==after.signed_quantity,
                                                           updated_at_before=before.updated_at.isoformat(), updated_at_after=after.updated_at.isoformat())

        for name, initial in [("timeout",PartnerSendResult(False,state="ambiguous_timeout",error="ReadTimeout")),
                              ("rate_limit",PartnerSendResult(False,state="rate_limited",error="telegram_429_retry_after_3600"))]:
            path = db(name)
            calls=[]
            async def scripted(*a, **k):
                calls.append(1)
                return initial if len(calls)==1 else PartnerSendResult(True,222,"acknowledged")
            with pytest.MonkeyPatch.context() as m:
                m.setattr(ha,"send_partner_result",scripted)
                for _ in range(2):
                    await ha._send_claimed_review(path,"protective_put_alert","same", "offline",detail={},now=NOW)
            results[name+"_same_key_immediate_retry"] = dict(posts=len(calls))

        path=db("expired")
        calls=[]
        async def expired_send(*a,**k):
            calls.append(1)
            return PartnerSendResult(True,333,"acknowledged")
        with pytest.MonkeyPatch.context() as m:
            m.setattr(ha,"send_partner_result",expired_send)
            await ha._send_claimed_review(path,"protective_put_alert","expired","offline",
                                         detail={"valid_until":(NOW-timedelta(minutes=1)).isoformat()},now=NOW)
        results["expired_proposal_send"] = dict(posts=len(calls))

        results["incomplete_greeks"] = str(pi._greeks({"delta":0.4}))
    print(json.dumps(results,indent=2,default=str))
    Path(__file__).with_name("probe-results.json").write_text(json.dumps(results,indent=2,default=str)+"\n",encoding="utf-8")

asyncio.run(main())
