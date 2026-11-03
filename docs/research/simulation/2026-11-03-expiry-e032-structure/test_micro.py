from datetime import datetime,timedelta
import micro as Q

def raw(now,bid=9.9,ask=10.,bq=195,aq=65):
    return dict(ts=now.isoformat(),ltp=10.,b=[[bid-i*.05,bq] for i in range(5)],a=[[ask+i*.05,aq] for i in range(5)])

def test_strict_five_level_freshness_no_volume_substitution():
    now=datetime(2026,11,3,13,0,tzinfo=Q.EP.IST)
    q=Q.view(raw(now),now);assert q and Q.imbalance(q)==.5
    assert Q.view(raw(now-timedelta(seconds=100)),now) is None
    r=raw(now);r['a']=r['a'][:1]
    assert Q.view(r,now) is None
    assert Q.view([9.9,65,10.,65,10.,now.isoformat()],now) is None

def rows():
    start=datetime(2026,11,3,13,0,tzinfo=Q.EP.IST)
    out=[]
    for i in range(30):
        ts=start+timedelta(seconds=i*10)
        out.append(dict(ts=ts,payload=dict(legs={'TEST':raw(ts)})))
    return out

def test_fixed_horizon_pays_spread_and_fees_and_never_same_quote():
    rr=rows();q=Q.view(rr[0]['payload']['legs']['TEST'],rr[0]['ts'])
    e=Q.event(rr,0,'TEST',q,30)
    assert e['entry_ts']==rr[1]['ts'].isoformat() and e['exit_ts']==rr[4]['ts'].isoformat()
    assert e['status']=='MEASURED' and e['net_markout']<0 and e['midpoint_markout']==0
    assert e['net_markout']==round((9.9-10.)*65-e['fees'],2)

def test_missing_exit_is_unavailable_not_zero_or_next_best_quote():
    rr=rows();q=Q.view(rr[0]['payload']['legs']['TEST'],rr[0]['ts'])
    rr[4]['payload']['legs']={}
    e=Q.event(rr,0,'TEST',q,30)
    assert e['status']=='EXIT_UNAVAILABLE' and e['net_markout'] is None and e['full_loss_bound']<0

def test_horizon_outcome_cannot_affect_entry_admission():
    rr=rows();q=Q.view(rr[0]['payload']['legs']['TEST'],rr[0]['ts'])
    a=Q.event(rr,0,'TEST',q,30)
    rr[4]['payload']['legs']['TEST']=raw(rr[4]['ts'],bid=4.9,ask=5.)
    b=Q.event(rr,0,'TEST',q,30)
    assert a['entry']==b['entry'] and a['entry_ts']==b['entry_ts'] and b['net_markout']<a['net_markout']
