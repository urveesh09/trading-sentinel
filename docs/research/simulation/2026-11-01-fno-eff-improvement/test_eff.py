import copy,sys
from datetime import datetime,timedelta
from pathlib import Path
from types import SimpleNamespace as NS
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import eff_lab as L
R=L.R
def ctx(bar='2024-01-02 10:00:00',**kw):
    return {'bar':bar,'fresh':True,'valid_volume':True,'open':100.1,'high':101.,'low':99.9,'close':100.8,'previous_close':100.5,'atr':2.,'rvol':1.3,'vwap':100.,'prior4high':100.,'prior4low':98.,'consecutive_from':'2024-01-02 09:15:00',**kw}
def sig(direction='LONG'):
    return NS(direction=NS(value=direction),bar_ts='2024-01-02 10:00:00',atr=2.,close=100.8,rvol=1.5,stop_underlying=98. if direction=='LONG' else 102.,target_underlying=105.)
NONE=NS(direction=None)
def test_retest_waits_then_confirms_without_mutating_original():
    s=R.RetestState();a=sig();before=copy.deepcopy(a.__dict__)
    assert s.step(a,ctx(),'R')[0] is None
    got,info=s.step(NONE,ctx('2024-01-02 10:05:00'),'R')
    assert got.bar_ts=='2024-01-02 10:05:00' and got.stop_underlying==98. and got.target_underlying==pytest.approx(100.8+1.8*2.8)
    assert info['source_bar']==a.bar_ts and a.__dict__==before
    got.target_underlying=999
    assert s.step(NONE,ctx('2024-01-02 10:05:00'),'R')[0].target_underlying!=999
@pytest.mark.parametrize('bar,allowed',[('2024-01-02 10:15:00',True),('2024-01-02 10:20:00',False),('2024-01-03 10:05:00',False)])
def test_retest_window_and_day_reset(bar,allowed):
    s=R.RetestState();s.step(sig(),ctx(),'R');assert (s.step(NONE,ctx(bar),'R')[0] is not None)==allowed
@pytest.mark.parametrize('change',[{'fresh':False},{'consecutive_from':'2024-01-02 10:05:00'},{'close':99.4},{'low':97.9}])
def test_retest_invalidates_missing_old_gap_failed_level_or_stop(change):
    s=R.RetestState();s.step(sig(),ctx(),'R');assert s.step(NONE,ctx('2024-01-02 10:05:00',**change),'R')[0] is None;assert s.pending is None
def test_crisis_clears_pending():
    s=R.RetestState();s.step(sig(),ctx(),'R');assert s.step(NONE,ctx('2024-01-02 10:05:00'),'REGIME_3_CRISIS')[0] is None and s.pending is None
def test_short_retest_is_symmetric():
    s=R.RetestState();s.step(sig('SHORT'),ctx(prior4low=100.),'R')
    got,_=s.step(NONE,ctx('2024-01-02 10:05:00',open=99.9,close=99.2,previous_close=99.5,high=100.1,low=99.),'R')
    assert got.direction.value=='SHORT' and got.stop_underlying==102. and got.target_underlying<got.close
@pytest.mark.parametrize('age,net,progress,trail,minute',[(29.99,-1.,0.,False,60),(30.,0.,.49,False,30),(30.,1.,.49,False,60),(59.99,-1.,0.,True,60),(60.,1.,1.,False,90),(60.,0.,1.,False,60),(60.,1.,.99,False,60),(89.99,1.,1.,False,90),(90.,1.,1.,False,60)])
def test_horizon_boundaries(age,net,progress,trail,minute):assert R.horizon(age,trail,net,progress,ctx(), 'LONG')[0]==minute
@pytest.mark.parametrize('change',[{'fresh':False},{'valid_volume':False},{'close':99.},{'previous_close':101.}])
def test_missing_or_failed_continuation_does_not_extend(change):assert R.horizon(61,False,10.,2.,ctx(**change),'LONG')[0]==60
def test_missing_positive_bid_cannot_extend_or_stall():
    assert R.horizon(31,False,None,0.,ctx(),'LONG')[0]==60
    assert R.horizon(61,False,None,2.,ctx(),'LONG')[0]==60
def test_context_future_mutation_and_freshness_boundary():
    index=pd.date_range('2024-01-02 09:15',periods=20,freq='5min');frame=pd.DataFrame({'open':100.,'high':102.,'low':99.,'close':101.,'volume':10.},index=index)
    now=datetime.fromisoformat('2024-01-02T10:06:59+05:30');a=L.context(frame,now);changed=frame.copy();changed.loc[changed.index>=pd.Timestamp('2024-01-02 10:05'),'close']=10000.
    assert a==L.context(changed,now)
    truncated=frame[frame.index<=pd.Timestamp('2024-01-02 10:00')]
    assert L.context(truncated,datetime.fromisoformat('2024-01-02T10:09:59+05:30'))['fresh']
    assert not L.context(truncated,datetime.fromisoformat('2024-01-02T10:10:00+05:30'))['fresh']
def test_per_leg_overrides_do_not_leak_and_restore_on_error(monkeypatch):
    base=L.Y.member_policy(L.Y.named('EFF'));policies=[base,base];a=NS();b=NS();full={1:a,2:b};book=NS(open=full)
    engine=NS(book={'n03_variant':'HORIZON'},members=[{'name':'EFF'},{'name':'SHIP'}],leg_member={1:0,2:1},policies=policies,_frame=None);seen=[]
    monkeypatch.setattr(L,'liquidation',lambda *a:(30.,{'action':'STALL30'}))
    def original(self,book,*args):
        ident=next(iter(book.open));seen.append((ident,dict(self.policies[self.leg_member[ident]].exit_overrides)['FNO_TIME_STOP_MIN']))
        if ident==2:raise RuntimeError('isolated failure')
    monkeypatch.setattr(L,'_manage',original)
    with pytest.raises(RuntimeError):L.manage(engine,book,None,None)
    assert seen==[(1,30.),(2,60.)] and engine.policies is policies and book.open is full
def test_matrix_is_two_hypotheses_and_fixed_lot_only_changes_caps():
    books=L.books();assert len(books)==19
    assert {b['n03_variant'] for b in books.values()}=={'BASE','RETEST','HORIZON'}
    for name,b in books.items():
        if name.startswith('ONE|'):assert b['cfg']=={'FNO_MAX_LOTS':1,'FNO_MAX_LOTS_PROVEN':1}

def test_two_eff_legs_get_individual_clocks(monkeypatch):
    policies=[L.Y.member_policy(L.Y.named('EFF'))];full={1:NS(mark=30.),2:NS(mark=90.)};book=NS(open=full)
    engine=NS(book={'n03_variant':'HORIZON'},members=[{'name':'EFF'}],leg_member={1:0,2:0},policies=policies,_frame=None);seen=[]
    monkeypatch.setattr(L,'liquidation',lambda leg,*a:(leg.mark,{'action':'CONTINUE90' if leg.mark==90 else 'STALL30'}))
    monkeypatch.setattr(L,'_manage',lambda self,book,*a:seen.append(dict(self.policies[0].exit_overrides)['FNO_TIME_STOP_MIN']))
    L.manage(engine,book,None,None);assert seen==[30.,90.] and engine.policies is policies and book.open is full

def test_hard_flat_precedes_extended_soft_clock(monkeypatch):
    now=datetime.fromisoformat('2024-01-02T15:10:00+05:30');leg=L.Y.replay.OpenLeg(id=1,tradingsymbol='NIFTY2401041000CE',token=1,direction='LONG',lots=1,lot_size=65,
        entry_time='2024-01-02T14:00:00+05:30',entry_premium=100.,entry_underlying=1000.,stop_underlying=980.,target_underlying=1100.,premium_stop=70.,atr_at_entry=10.,delta_at_entry=.5,bar_ts='2024-01-02 13:55:00',initial_qty=65,best_underlying=1000.)
    engine=L.Y.BookReplay(None,L.books()['NORMAL|MAIN|HORIZON'],{},'year');engine.leg_member={1:2}
    book=L.Y.replay.Book(equity=250000.,open={1:leg});obs=NS(options={1:NS(bid=130.,ltp=130.)},future=NS(ltp=1025.))
    monkeypatch.setattr(L.X.settings,'FNO_HARD_FLAT_MIN',910)
    monkeypatch.setattr(L,'liquidation',lambda *a:(90.,{'action':'CONTINUE90'}))
    L.manage(engine,book,obs,now)
    assert not book.open and book.trades[0]['exit_reason']=='hard_flat_1510'
    assert book.equity==pytest.approx(250000.+book.trades[0]['net_pnl'],abs=.0001)

def test_liquidation_includes_stress_and_refuses_ltp_substitution(monkeypatch):
    now=datetime.fromisoformat('2024-01-02T10:31:00+05:30');leg=NS(token=1,lots=1,qty=65,entry_premium=100.,entry_underlying=1000.,stop_underlying=980.,direction='LONG',entry_time='2024-01-02T10:00:00+05:30',trail_active=0)
    monkeypatch.setattr(L.B.P.L,'_COST',[200.,5.]);obs=NS(options={1:NS(bid=103.,ltp=103.)},future=NS(ltp=1000.))
    minute,ctx=L.liquidation(leg,obs,now,None);assert minute==30 and ctx['net_at_bid_after_cost']<0
    obs.options[1].bid=0.;obs.options[1].ltp=1000.
    minute,ctx=L.liquidation(leg,obs,now,None);assert minute==60 and ctx['net_at_bid_after_cost'] is None
