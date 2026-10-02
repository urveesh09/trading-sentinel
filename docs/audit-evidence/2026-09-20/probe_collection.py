"""Offline adversarial probes, exclusively temporary SQLite databases."""
import json
import tempfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from partner_collection_attempts import PartnerCollectionAttemptStore
from partner_decision_clock import start_clock

now = datetime(2026,9,21,9,46,50,tzinfo=ZoneInfo('Asia/Kolkata'))
def add(store,tick,state):
    clock=start_clock(underlying='NIFTY',account_id='audit-only',tick_started_at=tick)
    store.start(clock)
    store.record_public(clock.run_id,state=state,requested_at=tick,received_at=tick if state=='OBSERVED' else None,
        observed_at=tick if state=='OBSERVED' else None,source_id='audit',updated_at=tick)
    store.record_candidate(clock.run_id,state='NOT_REQUIRED',requested_at=None,received_at=None,source_id=None,updated_at=tick)
    store.finish(clock.run_id,state='NO_SETUP' if state=='OBSERVED' else 'UNAVAILABLE',reason='probe',updated_at=tick)

for case in ['mixed_unavailable','duplicate_slot']:
    with tempfile.TemporaryDirectory() as d:
        store=PartnerCollectionAttemptStore(d)
        add(store,now,'OBSERVED')
        add(store,now+timedelta(minutes=2) if case=='mixed_unavailable' else now+timedelta(microseconds=1),
            'UNAVAILABLE' if case=='mixed_unavailable' else 'OBSERVED')
        report=store.session_readiness(session_date=now.date(),now=now+timedelta(minutes=2),
            underlyings=['NIFTY'],entry_start_minute=585,entry_end_minute=885)
        print(json.dumps({'case':case,'report':report}))
