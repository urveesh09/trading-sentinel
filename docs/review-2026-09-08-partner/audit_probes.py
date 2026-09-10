"""Offline defect reproductions at e930968; never invokes a transport."""
import asyncio
import json
import sys
import tempfile
from pathlib import Path
from dataclasses import replace

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'python-engine'), str(ROOT / 'python-engine/tests')]
from test_partner_manual_advisory import _candidate, NOW
from partner_manual_advisory import (
    validate_candidate, persist_candidate, PartnerAdvisoryProfile,
    select_preferred_market_candidates, render_advisory_card,
)

async def main():
    c = _candidate('NIFTY')
    output = {'baseline': {
        'debit': c.net_debit_rs, 'max_profit': c.max_profit_rs,
        'costs': c.estimated_round_trip_cost_rs,
        'valid': validate_candidate(c, NOW).valid,
        'width_value': abs(c.legs[0].strike-c.legs[1].strike)*c.legs[0].lot_size,
    }}
    shallow = replace(c, legs=tuple(replace(l, bid_quantity=1, ask_quantity=1) for l in c.legs))
    output['one_unit_depth_valid'] = validate_candidate(shallow, NOW).valid
    malformed = replace(c, legs=(c.legs[0],), max_profit_rs=99999)
    output['single_leg_claiming_spread_valid'] = validate_candidate(malformed, NOW).valid
    with tempfile.TemporaryDirectory() as directory:
        db = str(Path(directory)/'audit.db')
        first = await persist_candidate(db, c, PartnerAdvisoryProfile(), NOW, queue_for_delivery=True)
        output['research_only_eligible'] = first['delivery_eligible']
        restrictive = PartnerAdvisoryProfile(permitted_structures=(),risk_limit_rs=1,
                                             delivery_start_minute=0,delivery_end_minute=1)
        output['restrictive_profile_eligible'] = (await persist_candidate(
            db, replace(c, thesis_id='restrictive'), restrictive, NOW, queue_for_delivery=True
        ))['delivery_eligible']
    print(json.dumps(output, indent=2))
    (Path(__file__).parent/'sample-card.txt').write_text(render_advisory_card(c,'AUDIT-SYNTHETIC-NOT-A-TRADE'),encoding='utf-8')

asyncio.run(main())
