import sys
from pathlib import Path
from datetime import datetime
from types import SimpleNamespace as NS
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import refine_lab as L
R=L.R
@pytest.mark.parametrize('age,eligible,minute',[(30.,True,60.),(44.999,True,60.),(45.,True,45.),(59.99,True,45.),(60.,True,60.),(45.,False,60.),(float('nan'),True,60.)])
def test_delay45_current_eligibility_boundary(age,eligible,minute):assert R.choose('DELAY45',eligible,age)[0]==minute
@pytest.mark.parametrize('direction,close,minute',[('LONG',99.,30.),('LONG',100.,60.),('LONG',101.,60.),('SHORT',101.,30.),('SHORT',100.,60.),('SHORT',99.,60.)])
def test_structure_direction_and_strict_equality(direction,close,minute):assert R.choose('STRUCT30',True,31.,{'fresh':True,'close':close},100.,direction)[0]==minute
@pytest.mark.parametrize('ctx,level',[(None,100.),({'fresh':False,'close':99.},100.),({'fresh':True,'close':99.},None),({'fresh':True,'close':float('nan')},100.),({'fresh':True,'close':99.},float('inf'))])
def test_unavailable_structure_keeps_native_clock(ctx,level):assert R.choose('STRUCT30',True,31.,ctx,level)[0]==60.
def test_unknown_mode_raises_and_base_cannot_force_early_exit():
    with pytest.raises(ValueError):R.choose('unknown',True,31.)
    assert R.choose('BASE',True,31.)==(60.,'BASE60')
def test_review_reads_immutable_level_and_current_parent_state(monkeypatch):
    leg=NS(direction='LONG',_n02_metadata={'n03_entry_context':{'broken_level':100.}});now=datetime.fromisoformat('2024-01-02T11:00:00+05:30')
    monkeypatch.setattr(L.P.E,'liquidation',lambda *a:(30.,{'age_minutes':45.,'action':'STALL30'}));monkeypatch.setattr(L.P.E,'context',lambda *a:{'fresh':True,'close':99.})
    minute,c=L.review(leg,None,now,None,'STRUCT30');assert minute==30 and c['original_retest_level']==100.
    leg._n02_metadata['n03_entry_context']['broken_level']=0.;assert c['original_retest_level']==100.
    monkeypatch.setattr(L.P.E,'liquidation',lambda *a:(60.,{'age_minutes':45.,'action':'BASE60'}));assert L.review(leg,None,now,None,'DELAY45')[0]==60.
def test_per_leg_policies_restore_on_exception(monkeypatch):
    policies=[L.Y.member_policy(L.Y.named('EFF'))];full={1:NS(mark=30.),2:NS(mark=60.)};book=NS(open=full);engine=NS(book={'n05_mode':'STRUCT30'},members=[{'name':'EFF'}],leg_member={1:0,2:0},policies=policies,_frame=None);seen=[]
    monkeypatch.setattr(L,'review',lambda leg,*a:(leg.mark,{'action':'STRUCT30' if leg.mark==30 else 'BASE60'}))
    def original(self,book,*a):
        seen.append(dict(self.policies[0].exit_overrides)['FNO_TIME_STOP_MIN'])
        if next(iter(book.open))==2:raise RuntimeError('simulated failure')
    monkeypatch.setattr(L,'_manage',original)
    with pytest.raises(RuntimeError):L.manage(engine,book,None,None)
    assert seen==[30.,60.] and book.open is full and engine.policies is policies
def test_base_delegates_once(monkeypatch):
    calls=[];engine=NS(book={'n05_mode':'BASE'});book=object();monkeypatch.setattr(L,'_manage',lambda *a:calls.append(a) or 17)
    assert L.manage(engine,book,None,None)==17 and calls==[(engine,book,None,None)]
@pytest.mark.parametrize('mode,reason,clock,future',[('DELAY45','hard_flat_1510','15:10:00',1025.),('STRUCT30','underlying_stop','10:31:00',980.)])
def test_native_urgent_exit_priority(monkeypatch,mode,reason,clock,future):
    now=datetime.fromisoformat('2024-01-02T'+clock+'+05:30');entered='2024-01-02T14:00:00+05:30' if reason.startswith('hard') else '2024-01-02T10:00:00+05:30'
    leg=L.Y.replay.OpenLeg(id=1,tradingsymbol='NIFTY2401041000CE',token=1,direction='LONG',lots=1,lot_size=65,entry_time=entered,entry_premium=100.,entry_underlying=1000.,stop_underlying=980.,target_underlying=1100.,premium_stop=70.,atr_at_entry=10.,delta_at_entry=.5,bar_ts=entered[:10]+' 09:55:00',initial_qty=65,best_underlying=1000.)
    engine=L.Y.BookReplay(None,L.books()['NORMAL|BALANCED_RETEST|'+mode],{},'year');engine.leg_member={1:2};book=L.Y.replay.Book(equity=250000.,open={1:leg});obs=NS(options={1:NS(bid=90.,ltp=90.)},future=NS(ltp=future))
    monkeypatch.setattr(L.X.settings,'FNO_HARD_FLAT_MIN',910);monkeypatch.setattr(L,'review',lambda *a:(45. if mode=='DELAY45' else 30.,{'action':mode}))
    L.manage(engine,book,obs,now);assert not book.open and book.trades[0]['exit_reason']==reason and book.equity==pytest.approx(250000.+book.trades[0]['net_pnl'],abs=.0001)
def test_matrix_and_caps_are_unchanged():
    books=L.books();assert len(books)==9 and L.Y.BookReplay._signal is L.P.E.signal
    for n,b in books.items():
        assert b['n04_mode']=='BASE'
        if n.startswith('ONE|'):assert b['cfg']=={'FNO_MAX_LOTS':1,'FNO_MAX_LOTS_PROVEN':1}
