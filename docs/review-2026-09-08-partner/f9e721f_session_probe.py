"""Offline audit reproduction, not a passing product acceptance test."""
import asyncio
import sqlite3
import sys
import tempfile
from contextlib import closing
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'python-engine'), str(ROOT / 'python-engine/tests')]
from test_partner_manual_advisory import _candidate, NOW
from partner_manual_advisory import persist_candidate, PartnerAdvisoryProfile, queue_management_updates

async def main():
    with tempfile.TemporaryDirectory() as directory:
        db = str(Path(directory) / 'probe.db')
        result = await persist_candidate(db, _candidate(), PartnerAdvisoryProfile(holding_period='INTRADAY'), now=NOW)
        with closing(sqlite3.connect(db)) as conn:
            conn.execute("UPDATE partner_advisory_ideas SET status='DELIVERED_ACKNOWLEDGED' WHERE advisory_id=?", (result['advisory_id'],))
            conn.commit()
        updates = await queue_management_updates(db, underlying='NIFTY', observed_underlying=24900,
                                                 observed_at=NOW.replace(hour=15, minute=11))
        print('15:11 below invalidation:', [row['event_type'] for row in updates])
        await queue_management_updates(db, underlying='NIFTY', observed_underlying=24900, observed_at=NOW + timedelta(days=1))
        with closing(sqlite3.connect(db)) as conn:
            print('next-day status:', conn.execute('SELECT status FROM partner_advisory_ideas').fetchone()[0])

asyncio.run(main())
