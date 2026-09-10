"""Offline reproductions for c19aec6; no broker or Telegram access.

Run with the Dev Python interpreter from python-engine. Reports observed
behavior, not assertions that these defects are desirable.
"""
import asyncio
import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python-engine"))
import aiosqlite
import pytz
import hedge_advisory as ha
from partner_bot import PartnerSendResult

NOW = pytz.timezone("Asia/Kolkata").localize(datetime(2026, 9, 4, 11))


async def run():
    results = {}
    with tempfile.TemporaryDirectory(prefix="hedge-round4-") as folder:
        db = str(Path(folder) / "probe.db")
        await ha.init_hedge_advisory_db(db)
        token = await ha._claim(db, "probe", "retired", now=NOW,
                                detail={"valid_until": (NOW + timedelta(minutes=5)).isoformat()})
        await ha._fail_claim(db, "probe", "retired", token,
                             detail={"delivery": {"state": "rate_limited"}}, now=NOW)
        await ha._retire_pending_delivery(db, "probe", "retired", {}, reason="SUPERSEDED", now=NOW)
        results["retired_record_reclaimable"] = bool(await ha._claim(
            db, "probe", "retired", now=NOW + timedelta(minutes=2)))

        await ha._claim(db, "probe", "expired", now=NOW,
                        detail={"valid_until": (NOW - timedelta(seconds=1)).isoformat()})
        results["fresh_same_decision_blocked_by_expired_record"] = (await ha._claim(
            db, "probe", "expired", now=NOW + timedelta(minutes=1),
            detail={"valid_until": (NOW + timedelta(minutes=5)).isoformat()})) is None

        original_fail = ha._fail_claim
        fail_calls = 0
        sends = 0

        async def fail_first(*args, **kwargs):
            nonlocal fail_calls
            fail_calls += 1
            if fail_calls == 1:
                raise RuntimeError("one authoritative ledger write failed")
            return await original_fail(*args, **kwargs)

        async def timeout(*args, **kwargs):
            nonlocal sends
            sends += 1
            return PartnerSendResult(False, state="ambiguous_timeout", error="timeout")

        with patch.object(ha, "_fail_claim", fail_first), patch.object(ha, "send_partner_result", timeout):
            try:
                await ha._send_claimed_review(db, "probe", "timeout-db", "offline",
                                               detail={}, now=NOW)
            except RuntimeError:
                pass
            await ha._send_claimed_review(db, "probe", "timeout-db", "offline",
                                           detail={}, now=NOW + timedelta(minutes=2))
        results["timeout_posts_after_first_ledger_write_failure"] = sends

        token = await ha._claim(db, "probe", "concurrent", now=NOW)
        await ha._mark_transport_started(db, "probe", "concurrent", token, now=NOW)
        await ha._retire_pending_delivery(db, "probe", "concurrent", {}, reason="stale worker", now=NOW)
        results["retirement_clears_other_worker_inflight_token"] = not await ha._complete_claim(
            db, "probe", "concurrent", token, detail={"acknowledged": True}, now=NOW)

        async def newer_snapshot(*args, **kwargs):
            return {"source": "probe", "complete": True, "observed_at": NOW}

        with patch.object(ha, "load_latest_partner_snapshot", newer_snapshot):
            results["explicit_missing_snapshot_reread_result"] = await ha._whole_portfolio_input_reason(
                db, (), (), NOW, snapshot=None)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(run())
