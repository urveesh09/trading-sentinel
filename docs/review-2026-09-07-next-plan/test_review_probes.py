"""Offline audit probes; assertions describe current defects, not desired behavior."""
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
import sqlite3
import asyncio

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python-engine'))
from proactive_intelligence import record_opportunity_event, transition_watchlist, run_shadow_workflow


def test_other_run_clock_expires_foreign_watchlist(tmp_path):
    async def probe():
        db = str(tmp_path / 'probe.sqlite3')
        earlier = datetime(2026, 9, 1, 9, tzinfo=timezone.utc)
        await record_opportunity_event(
            db, opportunity_id='foreign-pending', policy_id='trend_pullback_v1',
            policy_version='v1', account_id='account-a-run-a', mode='SHADOW',
            instrument='SYNTH:A', stage='SETUP', reason_code='AUDIT',
            idempotency_key='foreign-detected', observed_at=earlier,
            valid_until=earlier + timedelta(minutes=30),
        )
        await transition_watchlist(db, opportunity_id='foreign-pending', state='WATCHING',
                                  reason='AUDIT', now=earlier,
                                  valid_until=earlier + timedelta(minutes=30))
        await run_shadow_workflow(db, account_id='account-b', run_id='run-b',
                                  universe={}, now=earlier + timedelta(days=1))
        with sqlite3.connect(db) as conn:
            state = conn.execute('SELECT state FROM proactive_watchlist WHERE opportunity_id=?',
                                 ('foreign-pending',)).fetchone()[0]
        assert state == 'EXPIRED', 'Reproduction expects the current cross-run expiry defect'
    asyncio.run(probe())
