"""Broad-population causality, routing, selection and spread accounting checks."""
import sys
from pathlib import Path
from datetime import date,datetime,timedelta

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import lab_broad as B
import analyze_broad as A
import spread_pairs as V


def frame():
    rows=[]
    for k in range(12):
        d=date(2026,3,2)+timedelta(days=k)
        for i in range(75):
            ts=datetime.combine(d,datetime.min.time())+timedelta(minutes=555+5*i)
            c=100+.02*i+1.5*np.sin(i/4+k/3)+.4*np.sin(i)
            op=c-.2*np.cos(i)
            rows.append((ts,op,max(op,c)+.2,min(op,c)-.2,c,1000+i*10))
    return pd.DataFrame(rows,columns=['datetime','open','high','low','close','volume']).set_index('datetime')


@pytest.mark.parametrize('fam',B.FAMILIES)
@pytest.mark.parametrize('n',[10,20])
def test_family_every_prefix_and_future_tail_invariance(fam,n):
    f=frame();day=f.index[-1].date();B.O27F._FEATURES.clear();full=B.O27F.day_features(f,day)
    m=B.G.new_member(fam,B.W.CLOSED,n=n,stop_atr=1.,target_r=2.,exit='RUN')
    all_hits=B.entries(m,full,f)
    for cut in range(2,len(full['t'])+1):
        t=full['t'].iloc[:cut];short={**full,'t':t,'stamps':full['stamps'][:cut]};stamp=t.index[-1]
        want={k:v for k,v in all_hits.items() if pd.Timestamp(k)<=stamp}
        assert B.entries(m,short,f[f.index<=stamp])==want
        changed=full['t'].copy();changed.iloc[cut:,:4]*=3
        again=B.entries(m,{**full,'t':changed},f)
        assert {k:v for k,v in again.items() if pd.Timestamp(k)<=stamp}==want
    assert all(v[0] in (-1,1) and v[0]*(v[2]-v[1])>0 for v in all_hits.values())


def test_clock_does_not_read_today_or_later_sessions():
    f=frame();d=f.index[-2].date();a=B.clock_votes(f,d,10)
    f.loc[f.index.date>=d,['open','high','low','close']]*=3
    assert B.clock_votes(f,d,10)==a


def test_random_controls_are_deterministic_and_use_same_weak_day_scope():
    assert len([n for n in B.books() if n.startswith('NULL|')])==8
    f=frame();day=f.index[-1].date();B.O27F._FEATURES.clear();features=B.O27F.day_features(f,day)
    m=B.G.new_member('NULL_ENTRY',B.W.CLOSED,n=10,seed=4,stop_atr=1.5,target_r=2.,exit='RUN')
    a=B.entries(m,features,f);assert a==B.entries(m,features,f)
    cut=features['t'].index[30];short={**features,'t':features['t'].iloc[:31],'stamps':features['stamps'][:31]}
    assert B.entries(m,short,f)=={k:v for k,v in a.items() if pd.Timestamp(k)<=cut}


def test_population_is_frozen_balanced_and_full_identity():
    g=B.genomes();assert len(g)==48 and len({B.G.digest(x) for x in g.values()})==48
    assert all(sum(m['family']==f for m in g.values())==4 for f in B.FAMILIES)
    for n,b in B.books().items():
        if n.startswith('RAW|') and n[4:] in g:assert 'skip' not in b and b['cfg']['FNO_MAX_LOTS']==1
    assert B.books()['EX|MAIN']['skip']==.5


def test_selection_uses_only_fitting_years_and_one_per_family():
    members={'A':{'family':'F'},'B':{'family':'F'},'C':{'family':'G'}}
    s={}
    for n,net in [('A',1000),('B',900),('C',800)]:
        s[n]={d:{y:{'net':net,'trades':20} for y in ('2024','2025')} for d in ('BOTH','LONG','SHORT')}
        s[n]['BOTH']['2026']={'net':-1e9,'trades':0}
    p=A.select_proposals(s,members);assert len(p)==2 and p[0]['parent']=='A'
    for row in s.values():
        for d in row:row[d]['2024']['net']=-1
    assert A.select_proposals(s,members)==[]


def test_max_t_is_seeded_and_penalizes_multiple_arms():
    x=[[1.,-1.,2.,-1.]*8,[2.,1.,3.,2.]*8]
    t,p=A.max_t_adjusted(x,128,4);assert (t,p)==A.max_t_adjusted(x,128,4)
    _,alone=A.max_t_adjusted([x[0]],128,4);assert p[0]>=alone[0]


def q(mid,volume=100):return {'close':mid,'bid':mid-.1,'ask':mid+.1,'volume':volume}


@pytest.mark.parametrize('mode',['DEBIT','INVERSE_CREDIT'])
def test_spread_fees_cash_and_missing_leg(mode):
    r=V.vertical(q(100),q(120),q(70),q(85),50,mode,200)
    assert r['status']=='AVAILABLE' and r['reserved_own_cash']==3650 and r['cash_feasible']
    assert r['net']==pytest.approx(r['gross']-r['fees']-200)
    assert V.vertical(q(100),q(120),None,q(85),50,mode,200)['status']=='UNAVAILABLE'
    assert V.vertical(q(100,0),q(120),q(70),q(85),50,mode,200)['status']=='UNAVAILABLE'


def test_spread_planned_risk_uses_entry_only_and_no_free_money():
    a=V.vertical(q(100),q(120),q(70),q(85),50,'DEBIT',200)
    b=V.vertical(q(100),q(90),q(70),q(65),50,'DEBIT',200)
    assert a['planned_risk']==b['planned_risk'] and a['risk_compatible']==b['risk_compatible']
    assert V.vertical(q(100),q(120),q(110),q(85),50,'DEBIT',200)['status']=='UNAVAILABLE'


def test_no_available_pairs_are_not_reported_as_success():
    r=V.summarize([{'status':'UNAVAILABLE','reason':'missing_exact_minute_leg'}])
    assert r['available']==0 and r['money_if_no_available'] is None and r['coverage_pct']==0
    assert r['all_priced_diagnostic']['net'] is None


def test_member_specific_location_rule_keeps_main_and_restores_on_error(monkeypatch):
    from types import SimpleNamespace
    from fno_models import FnoDirection
    sig=B.G.MomSignal(bar_ts='2026-03-02 10:00:00',direction=FnoDirection.LONG)
    monkeypatch.setattr(B,'_previous_route',lambda *args:sig)
    monkeypatch.setattr(B.S,'stretch_at',lambda *args:.6)
    engine=SimpleNamespace(book={'broad_member_skip':True,'skip':.5},members=[{'kind':'NAMED'}],_fired=0)
    assert B.route(engine,None,None,None).direction is None and engine.book['skip']==.5
    engine.members=[{'kind':'NEW','family':'DONCHIAN'}]
    assert B.route(engine,None,None,None).direction==FnoDirection.LONG
    engine.book['broad_direction']='SHORT'
    assert B.route(engine,None,None,None).direction is None
    def boom(*args):raise RuntimeError('test')
    monkeypatch.setattr(B,'_previous_route',boom)
    with pytest.raises(RuntimeError):B.route(engine,None,None,None)
    assert engine.book['skip']==.5


def test_every_family_can_generate_an_entry_on_synthetic_evidence():
    fired=set()
    for seed in range(20):
        rng=np.random.default_rng(seed);idx=pd.date_range('2026-03-02 09:15',periods=75,freq='5min')
        c=100+np.cumsum(rng.normal(.025,.3,75));c[32:35]+=2;c[48:51]-=2
        t=pd.DataFrame({'open':np.r_[c[0],c[:-1]],'close':c,'volume':1000+np.arange(75)*10},index=idx)
        t['high']=t[['open','close']].max(axis=1)+.1;t['low']=t[['open','close']].min(axis=1)-.1
        t['atr']=1.;t['minute']=idx.hour*60+idx.minute
        f={'t':t,'stamps':list(idx.strftime('%Y-%m-%d %H:%M:%S')),'day':date(2026,3,2),'day_open':101.,'pdc':100.,'pdh':102.,'pdl':98.}
        for fam in B.FAMILIES:
            m=B.G.new_member(fam,B.W.CLOSED,n=10,stop_atr=1.,target_r=2.,exit='LIVE')
            if B.entries(m,f,frame()):fired.add(fam)
    # CLOCK_MOMO needs earlier sessions than the synthetic March2 example.
    h=frame();day=h.index[-1].date();B.O27F._FEATURES.clear();f=B.O27F.day_features(h,day)
    m=B.G.new_member('CLOCK_MOMO',B.W.CLOSED,n=10,stop_atr=1.,target_r=2.,exit='LIVE')
    if B.entries(m,f,h):fired.add('CLOCK_MOMO')
    # Deliberate bullish divergence: a fast first fall, a rally, then a lower
    # price low with a higher RSI and a separate confirming bar.
    idx=pd.date_range('2026-03-02 09:15',periods=55,freq='5min');c=np.full(55,100.)
    c[12:21]=np.linspace(100,95,9);c[21:30]=[96,98,99,98,97.2,96.4,95.6,94.8,96.2]
    t=pd.DataFrame({'open':np.r_[c[0],c[:-1]],'close':c,'volume':1000.},index=idx)
    t['high']=t[['open','close']].max(axis=1)+.1;t['low']=t[['open','close']].min(axis=1)-.1;t['atr']=1.;t['minute']=idx.hour*60+idx.minute
    f={'t':t,'stamps':list(idx.strftime('%Y-%m-%d %H:%M:%S')),'day':date(2026,3,2),'day_open':100.,'pdc':100.,'pdh':102.,'pdl':98.}
    m=B.G.new_member('RSI_DIVERGENCE',B.W.CLOSED,n=10,stop_atr=1.,target_r=2.,exit='LIVE')
    hit=B.entries(m,f)
    assert hit[f['stamps'][29]][0]==1
    fired.add('RSI_DIVERGENCE')
    assert fired==set(B.FAMILIES),set(B.FAMILIES)-fired
