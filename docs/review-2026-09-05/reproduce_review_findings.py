"""Offline review probes; mock transport, temporary DB, no production access.
Run using python-engine/winvenv/Scripts/python.exe from any directory.
These record current behavior rather than asserting that defects are desired.
"""
import asyncio
import json
import runpy
import sys
import tempfile
from dataclasses import replace
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python-engine"))
import pytest
import httpx
import hedge_advisory as ha
import partner_bot as pb
from config import settings
from penny_edge_engine import compute_features_for_day_with_reason
from tools.runtime_audit import LogRecord, IST, _scheduler_progress

fixture = runpy.run_path(str(ROOT / "python-engine/tests/test_hedge_advisory.py"))
NOW = fixture["NOW"]
position = fixture["_position"]()
results = {}

pending = replace(position, verification_status="PENDING_CONFIRMATION", signed_quantity=-10000)
results["partial_reconciliation"] = ha._portfolio_input_reason([position, pending], [position], NOW)
snapshot = fixture["_snapshot"]()
with pytest.MonkeyPatch.context() as m:
    m.setattr(settings, "PARTNER_HEDGE_MIN_OI", 100000000)
    results["liquidity_blocked_review_count"] = len(ha.build_hedge_reviews([position], snapshot, now=NOW))

records = [LogRecord("synthetic", i, datetime(2026, 9, 4, hour, 0, tzinfo=IST), "info",
                     f"scheduler_progress_tick count=1 boot_id={boot}")
           for i, (hour, boot) in enumerate([(10, "a"), (11, "b")], 1)]
state, findings = _scheduler_progress(records, 180)
results["market_hour_restart"] = {"restart_gap": state["epochs"][1]["restart_gap_seconds"],
                                   "findings": [f.code for f in findings]}

bars = [dict(open=10, close=10, high=11, low=9, volume=100, date="2026-09-04") for _ in range(21)]
del bars[-1]["date"]
try:
    results["missing_bar_date"] = compute_features_for_day_with_reason(bars, 20)
except Exception as exc:
    results["missing_bar_date"] = type(exc).__name__ + ": " + str(exc)

async def probes():
    sender_calls = []
    with tempfile.TemporaryDirectory(prefix="ts-review-") as tmp:
        db = str(Path(tmp) / "probe.db")
        await ha.init_hedge_advisory_db(db)
        real_set = ha._set_service_state
        fail_once = True
        async def set_state(*args, **kwargs):
            nonlocal fail_once
            if args[1] == "last_attempted_send" and fail_once:
                fail_once = False
                raise RuntimeError("simulated state persistence failure AFTER remote acknowledgement")
            return await real_set(*args, **kwargs)
        async def sender(*args, **kwargs):
            sender_calls.append(1)
            return pb.PartnerSendResult(True, 12345, "acknowledged")
        with pytest.MonkeyPatch.context() as m:
            m.setattr(ha, "send_partner_result", sender)
            m.setattr(ha, "_set_service_state", set_state)
            for _ in range(2):
                try:
                    await ha._send_claimed_review(db, "protective_put_alert", "same-key",
                                                 "synthetic", detail={}, now=NOW)
                except RuntimeError:
                    pass
        results["remote_ack_then_state_failure_send_count"] = len(sender_calls)

    class Response:
        status_code = 403
        def json(self):
            return {"ok": False}
    class Client:
        count = 0
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, *args, **kwargs):
            Client.count += 1
            if Client.count == 1:
                raise httpx.ReadTimeout("synthetic remote acceptance unknown")
            return Response()
    with pytest.MonkeyPatch.context() as m:
        m.setattr(pb, "partner_enabled", lambda: True)
        m.setattr(settings, "PARTNER_TELEGRAM_BOT_TOKEN", "offline-test-token")
        m.setattr(settings, "PARTNER_TELEGRAM_CHAT_ID", "offline-test-chat")
        m.setattr(pb.httpx, "AsyncClient", Client)
        m.setattr(pb, "RETRY_DELAYS_SEC", (0, 0, 0))
        outcome = await pb.send_partner_result("synthetic offline probe")
        results["timeout_then_rejection"] = {"posts": Client.count, "final_state": outcome.state,
                                               "final_error": outcome.error}

asyncio.run(probes())
out = Path(__file__).with_name("python-probe-results.json")
out.write_text(json.dumps(results, indent=2, default=str) + "\n", encoding="utf-8")
print(json.dumps(results, indent=2, default=str))
