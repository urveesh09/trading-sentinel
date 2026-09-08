from datetime import datetime,timedelta,timezone
from proactive_exit_research import simulate_partial_target_trail
from proactive_intelligence import ShadowProposal


def test_partial_trail_uses_stop_first_for_ambiguous_target_bar_and_costs_both_exits():
    at=datetime(2026,1,1,tzinfo=timezone.utc); p=ShadowProposal("x","trend_pullback_v1","NSE:X",100,95,110,at+timedelta(minutes=30),1,100,"x",at,at,at+timedelta(minutes=30),at+timedelta(hours=1))
    bars=[{"timestamp":(at+timedelta(minutes=1)).isoformat(),"open":100,"high":111,"low":94,"close":100}]
    r=simulate_partial_target_trail(p,bars,cash=1000,fee_rate=.001,slippage_bps=0)
    assert r.status=="CLOSED" and r.reason=="STOP" and r.fees>0
